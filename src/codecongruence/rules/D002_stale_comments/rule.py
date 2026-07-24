"""Rule: inline comment vs the code that follows it."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codecongruence.rules.base import (
    RuleViolation,
    iter_parsed,
    resolve_threshold,
    similarity_violation,
)

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from codecongruence.core.config import RuleConfig
    from codecongruence.core.embedder import Embedder
    from codecongruence.core.git import ChangedFile

__all__ = ["StaleCommentsRule"]


class StaleCommentsRule:
    """Catch comments that describe behavior the code no longer has."""

    rule_id: str = "stale_comments"
    code: str = "D002"
    description: str = "Inline comments should describe the next few lines of code."
    default_threshold: float = 0.20
    docs_url: str = (
        "https://github.com/brunofaust/codecongruence/blob/main"
        "/src/codecongruence/rules/D002_stale_comments/README.md"
    )

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
        """Check each inline comment against the code that follows it.

        Args:
            changed_files: Files to check (staged or all).
            embedder: Shared embedder for semantic similarity.
            config: Per-rule configuration (threshold, excludes, extras).

        Returns:
            Sequence of :class:`RuleViolation` for each stale comment.
        """
        threshold = resolve_threshold(self, config)
        ctx_lines = int(getattr(config, "context_lines", 5) or 5)

        violations: list[RuleViolation] = []
        for cf, parser, source in iter_parsed(changed_files):
            for comment in cf.iter_comments(parser, source, context_lines=ctx_lines):
                if cf.added_ranges and not cf.overlaps(comment.line, comment.line + ctx_lines):
                    log.debug("D002 SKIP not_in_diff %s:%d", cf.path, comment.line)
                    continue

                violation = await similarity_violation(
                    embedder,
                    comment.text,
                    comment.following_code,
                    rule=self,
                    threshold=threshold,
                    file_path=str(cf.path),
                    line=comment.line,
                    log_context=f"D002 {cf.path}:{comment.line}",
                    message_template=(
                        f"Comment doesn't match next {ctx_lines} lines "
                        "(similarity {sim:.2f} < {threshold:.2f}). "
                        "Update or remove the comment."
                    ),
                )
                if violation is not None:
                    violations.append(violation)
        return violations
