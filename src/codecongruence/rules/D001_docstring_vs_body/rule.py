"""Rule: docstring drift vs function body."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codecongruence.rules.base import (
    RuleViolation,
    iter_function_candidates,
    resolve_threshold,
    similarity_violation,
    strip_comments,
)

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
        threshold = resolve_threshold(self, config)
        min_stmts = int(getattr(config, "min_body_statement_count", 3) or 3)
        min_doc = int(getattr(config, "min_docstring_chars", 10) or 10)
        include_comments = bool(getattr(config, "include_comments", False))

        violations: list[RuleViolation] = []
        candidates = iter_function_candidates(
            changed_files, code=self.code, min_body_statement_count=min_stmts
        )
        for cf, func in candidates:
            if not func.docstring or len(func.docstring) < min_doc:
                log.debug("D001 SKIP no_docstring %s::%s", cf.path, func.qualified_name)
                continue

            body = func.body_source if include_comments else strip_comments(func.body_source)
            violation = await similarity_violation(
                embedder,
                func.docstring,
                body,
                rule=self,
                threshold=threshold,
                file_path=str(cf.path),
                line=func.line_start,
                log_context=f"D001 {cf.path}::{func.qualified_name}",
                message_template=(
                    f"Docstring drift on `{func.qualified_name}` "
                    "(similarity {sim:.2f} < {threshold:.2f}). "
                    "Update the docstring to match what the body actually does."
                ),
            )
            if violation is not None:
                violations.append(violation)
        return violations
