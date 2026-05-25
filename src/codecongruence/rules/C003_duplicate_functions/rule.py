"""Rule: detect semantically duplicate functions."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING

from codecongruence.core.git import ChangedFile, all_tracked_files, current_repo_root
from codecongruence.parsers import get_parser
from codecongruence.parsers.base import is_dataclass_init, is_overload_decorated
from codecongruence.rules.base import RuleViolation

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from codecongruence.core.config import RuleConfig
    from codecongruence.core.embedder import Embedder

__all__ = ["DuplicateFunctionsRule"]

_MIN_PAIR_COUNT = 2


@dataclass(frozen=True, slots=True)
class _FuncEntry:
    """Internal record of a parsed function ready for pairwise comparison."""

    file_path: str
    line: int
    qualified_name: str
    body: str


class DuplicateFunctionsRule:
    """Flag pairs of functions with different names whose bodies mean the same thing."""

    rule_id: str = "duplicate_functions"
    code: str = "C003"
    description: str = "Two functions with different names have nearly identical bodies."
    default_threshold: float = 0.92
    docs_url: str = (
        "https://github.com/brunofaust/codecongruence/blob/main"
        "/src/codecongruence/rules/C003_duplicate_functions/README.md"
    )

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
        """Compare function bodies pairwise and flag near-identical pairs.

        ``staged`` scope (default) compares only functions from the provided
        ``changed_files``.  ``full`` scope walks every tracked file in the repo
        and compares all pairs — useful as a periodic audit but slow on large
        codebases.

        All bodies are embedded in a single batch call so the ONNX runtime
        runs once, then pairwise cosines are computed in pure NumPy.

        Args:
            changed_files: Staged (or all) files supplied by the runner.
            embedder: Shared embedder for semantic similarity.
            config: Per-rule configuration (threshold, scope, excludes).

        Returns:
            One :class:`RuleViolation` per duplicate pair, reported on the
            function that appears first by file path then line number.
        """
        threshold = self.default_threshold if config.threshold is None else config.threshold
        scope = str(getattr(config, "scope", "staged") or "staged")
        min_stmts = int(getattr(config, "min_body_statement_count", 3) or 3)

        entries = await self._collect(changed_files, scope, min_stmts)
        if len(entries) < _MIN_PAIR_COUNT:
            return []

        bodies = [e.body for e in entries]
        mat = await asyncio.to_thread(embedder._embed_locked, bodies)

        violations: list[RuleViolation] = []
        for i, j in combinations(range(len(entries)), 2):
            a, b = entries[i], entries[j]
            if a.file_path == b.file_path and a.qualified_name == b.qualified_name:
                continue
            from codecongruence.core.embedder import Embedder as _Emb  # noqa: PLC0415

            sim = _Emb.cosine(mat[i], mat[j])
            log.debug(
                "C003  %s::%s  vs  %s::%s  sim=%.3f  threshold=%.3f  %s",
                a.file_path,
                a.qualified_name,
                b.file_path,
                b.qualified_name,
                sim,
                threshold,
                "FAIL" if sim >= threshold else "PASS",
            )
            if sim >= threshold:
                violations.append(
                    RuleViolation(
                        rule_id=self.rule_id,
                        code=self.code,
                        file_path=a.file_path,
                        line=a.line,
                        message=(
                            f"`{a.qualified_name}` ({a.file_path}:{a.line}) and "
                            f"`{b.qualified_name}` ({b.file_path}:{b.line}) "
                            f"have similar bodies (similarity {sim:.2f} >= {threshold:.2f}). "
                            "Consider merging or extracting shared logic."
                        ),
                        similarity=sim,
                        threshold=threshold,
                    )
                )
        return violations

    @staticmethod
    async def _collect(
        changed_files: Sequence[ChangedFile],
        scope: str,
        min_stmts: int,
    ) -> list[_FuncEntry]:
        """Return function entries to compare based on scope.

        Args:
            changed_files: Staged files from the runner.
            scope: ``"staged"`` or ``"full"``.
            min_stmts: Skip functions with fewer body statements than this.

        Returns:
            Deduplicated list of :class:`_FuncEntry` ready for pairwise embedding.
        """
        if scope == "full":
            repo_root = await current_repo_root()
            paths = await all_tracked_files(cwd=repo_root)
            files = [
                ChangedFile(path=repo_root / p, added_ranges=())
                for p in paths
                if (repo_root / p).is_file()
            ]
        else:
            files = list(changed_files)

        seen: set[tuple[str, int]] = set()
        entries: list[_FuncEntry] = []

        for cf in files:
            parser = get_parser(cf.path.suffix)
            if parser is None:
                continue
            try:
                source = cf.path.read_text(encoding="utf-8")
            except OSError:
                continue
            for func in cf.iter_functions(parser, source):
                if is_overload_decorated(func.decorators) or is_dataclass_init(func):
                    continue
                if func.body_statements < min_stmts:
                    continue
                body = func.body_source.strip()
                if not body:
                    continue
                key = (str(cf.path), func.line_start)
                if key in seen:
                    continue
                seen.add(key)
                entries.append(
                    _FuncEntry(
                        file_path=str(cf.path),
                        line=func.line_start,
                        qualified_name=func.qualified_name,
                        body=body,
                    )
                )

        return entries
