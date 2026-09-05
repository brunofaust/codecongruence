"""Rule: detect semantically duplicate functions."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING

from codecongruence.core.git import ChangedFile, all_tracked_files, current_repo_root
from codecongruence.parsers.base import is_dataclass_init, is_overload_decorated
from codecongruence.parsers.python import strip_comments_and_nested_docstrings
from codecongruence.rules.base import RuleViolation, iter_parsed, resolve_threshold, strip_comments

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from codecongruence.core.config import RuleConfig
    from codecongruence.core.embedder import Embedder

__all__ = ["DuplicateFunctionsRule"]

_MIN_PAIR_COUNT = 2

_UNAMBIGUOUS_NAME_COUNT = 1


@dataclass(frozen=True, slots=True)
class _FuncEntry:
    """Internal record of a parsed function ready for pairwise comparison."""

    file_path: str
    line: int
    qualified_name: str
    body: str
    line_end: int
    name: str
    called_names: tuple[str, ...]


def _encloses(left: _FuncEntry, right: _FuncEntry) -> bool:
    """True when one symbol's source range contains the other's.

    Containment happens only between a definition and one of its own ancestors:
    a closure's source is a substring of the function that defines it, so the
    pair scores near 1.0 by construction and can never be deduplicated.
    Siblings are disjoint ranges and stay comparable.

    Args:
        left: One side of the candidate pair.
        right: The other side of the candidate pair.

    Returns:
        ``True`` when the two are in the same file and one range contains the other.
    """
    if left.file_path != right.file_path:
        return False
    outer, inner = (left, right) if left.line <= right.line else (right, left)
    return outer.line <= inner.line and inner.line_end <= outer.line_end


def _calls(left: _FuncEntry, right: _FuncEntry, name_counts: Mapping[str, int]) -> bool:
    """True when one symbol delegates to the other by an unambiguous name.

    A wrapper that calls the function it resembles is single-owner design, not
    duplication.  The skip is deliberately narrow: the callee's simple name
    must occur exactly once across the compared symbols, so two same-named
    methods on different classes never make a call edge look resolved.

    Args:
        left: One side of the candidate pair.
        right: The other side of the candidate pair.
        name_counts: How often each simple name occurs among compared symbols.

    Returns:
        ``True`` when either side calls the other by an unambiguous simple name.
    """
    return any(
        callee.name in caller.called_names
        and name_counts.get(callee.name, 0) == _UNAMBIGUOUS_NAME_COUNT
        for caller, callee in ((left, right), (right, left))
    )


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
                ``skip_nested_functions`` (default ``True``) drops pairs where
                one symbol's source range encloses the other's;
                ``skip_call_edges`` (default ``True``) drops pairs where one
                symbol calls the other by an unambiguous name.

        Returns:
            One :class:`RuleViolation` per duplicate pair, reported on the
            function that appears first by file path then line number.
        """
        threshold = resolve_threshold(self, config)
        scope = str(getattr(config, "scope", "staged") or "staged")
        min_stmts = int(getattr(config, "min_body_statement_count", 3) or 3)
        include_comments = bool(getattr(config, "include_comments", True))
        skip_nested_functions = bool(getattr(config, "skip_nested_functions", True))
        skip_call_edges = bool(getattr(config, "skip_call_edges", True))

        entries = await self._collect(changed_files, scope, min_stmts, include_comments)
        if len(entries) < _MIN_PAIR_COUNT:
            return []

        name_counts = Counter(e.name for e in entries)

        bodies = [e.body for e in entries]
        mat = await embedder.embed_batch(bodies)

        violations: list[RuleViolation] = []
        for i, j in combinations(range(len(entries)), 2):
            a, b = entries[i], entries[j]
            if a.file_path == b.file_path and a.qualified_name == b.qualified_name:
                continue
            if skip_nested_functions and _encloses(a, b):
                continue
            if skip_call_edges and _calls(a, b, name_counts):
                continue
            sim = embedder.cosine(mat[i], mat[j])
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
        include_comments: bool = True,
    ) -> list[_FuncEntry]:
        """Return function entries to compare based on scope.

        Args:
            changed_files: Staged files from the runner.
            scope: ``"staged"`` or ``"full"``.
            min_stmts: Skip functions with fewer body statements than this.
            include_comments: Whether inline comments remain in embedded bodies.

        Returns:
            Deduplicated list of :class:`_FuncEntry` ready for pairwise embedding.

        The ``include_comments`` default preserves the pre-option behavior for
        direct callers; normal rule execution supplies it from configuration.
        """
        if scope == "full":
            repo_root = changed_files[0].repo_root if changed_files else await current_repo_root()
            paths = await all_tracked_files(cwd=repo_root)
            files = [
                ChangedFile(path=p, added_ranges=(), repo_root=repo_root)
                for p in paths
                if (repo_root / p).is_file()
            ]
        else:
            files = list(changed_files)

        seen: set[tuple[str, int]] = set()
        entries: list[_FuncEntry] = []

        for cf, parser, source in iter_parsed(files):
            for func in cf.iter_functions(parser, source):
                if is_overload_decorated(func.decorators) or is_dataclass_init(func):
                    continue
                if func.body_statements < min_stmts:
                    continue
                if include_comments:
                    body = func.body_source
                    statement_count = func.body_statements
                elif cf.path.suffix in {".py", ".pyi"}:
                    body, statement_count = strip_comments_and_nested_docstrings(func.body_source)
                else:
                    body = strip_comments(func.body_source)
                    statement_count = func.body_statements
                if statement_count < min_stmts:
                    continue
                body = body.strip()
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
                        line_end=func.line_end,
                        name=func.name,
                        called_names=func.called_names,
                    )
                )

        return entries
