"""Rule: docstring drift vs function body."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codecongruence.parsers import get_parser
from codecongruence.parsers.base import is_dataclass_init, is_overload_decorated
from codecongruence.rules.base import RuleViolation, strip_comments

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from codecongruence.core.config import RuleConfig
    from codecongruence.core.embedder import Embedder
    from codecongruence.core.git import ChangedFile

__all__ = ["DocstringVsBodyRule"]


class DocstringVsBodyRule:
    """Flag functions whose docstring diverges from the body."""

    rule_id: str = "docstring_vs_body"
    code: str = "D001"
    description: str = "Docstring should describe what the function actually does."
    default_threshold: float = 0.30
    docs_url: str = (
        "https://github.com/brunofaust/codecongruence/blob/main"
        "/src/codecongruence/rules/D001_docstring_vs_body/README.md"
    )

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
        """Check each function whose docstring diverges from its body.

        Args:
            changed_files: Files to check (staged or all).
            embedder: Shared embedder for semantic similarity.
            config: Per-rule configuration (threshold, excludes, extras).

        Returns:
            Sequence of :class:`RuleViolation` for each drifted docstring.
        """
        threshold = self.default_threshold if config.threshold is None else config.threshold
        min_stmts = int(getattr(config, "min_body_statement_count", 3) or 3)
        min_doc = int(getattr(config, "min_docstring_chars", 10) or 10)
        include_comments = bool(getattr(config, "include_comments", False))

        violations: list[RuleViolation] = []
        for cf in changed_files:
            parser = get_parser(cf.path.suffix)
            if parser is None:
                continue
            try:
                source = cf.path.read_text(encoding="utf-8")
            except OSError:
                continue

            for func in cf.iter_functions(parser, source):
                if not func.docstring or len(func.docstring) < min_doc:
                    log.debug("D001 SKIP no_docstring %s::%s", cf.path, func.qualified_name)
                    continue
                if func.body_statements < min_stmts:
                    log.debug(
                        "D001 SKIP short_body %s::%s  stmts=%d  min=%d",
                        cf.path,
                        func.qualified_name,
                        func.body_statements,
                        min_stmts,
                    )
                    continue
                if is_overload_decorated(func.decorators) or is_dataclass_init(func):
                    log.debug(
                        "D001 SKIP overload_or_dataclass %s::%s", cf.path, func.qualified_name
                    )
                    continue
                if cf.added_ranges and not cf.overlaps(func.line_start, func.line_end):
                    log.debug("D001 SKIP not_in_diff %s::%s", cf.path, func.qualified_name)
                    continue

                body = func.body_source if include_comments else strip_comments(func.body_source)
                sim = await embedder.similarity(func.docstring, body)
                log.debug(
                    "D001 %s::%s  left=%r  right=%r  sim=%.3f  threshold=%.3f  %s",
                    cf.path,
                    func.qualified_name,
                    func.docstring[:120],
                    body[:120],
                    sim,
                    threshold,
                    "FAIL" if sim < threshold else "PASS",
                )
                if sim < threshold:
                    violations.append(
                        RuleViolation(
                            rule_id=self.rule_id,
                            code=self.code,
                            file_path=str(cf.path),
                            line=func.line_start,
                            message=(
                                f"Docstring drift on `{func.qualified_name}` "
                                f"(similarity {sim:.2f} < {threshold:.2f}). "
                                "Update the docstring to match what the body actually does."
                            ),
                            similarity=sim,
                            threshold=threshold,
                        )
                    )
        return violations
