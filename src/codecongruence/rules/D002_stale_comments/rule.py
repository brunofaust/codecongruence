"""Rule: inline comment vs the code that follows it."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codecongruence.parsers import get_parser
from codecongruence.rules.base import RuleViolation

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
        threshold = self.default_threshold if config.threshold is None else config.threshold
        ctx_lines = int(getattr(config, "context_lines", 5) or 5)

        violations: list[RuleViolation] = []
        for cf in changed_files:
            parser = get_parser(cf.path.suffix)
            if parser is None:
                continue
            try:
                source = cf.abs_path.read_text(encoding="utf-8")
            except OSError:
                continue

            for comment in cf.iter_comments(parser, source, context_lines=ctx_lines):
                if cf.added_ranges and not cf.overlaps(comment.line, comment.line + ctx_lines):
                    log.debug("D002 SKIP not_in_diff %s:%d", cf.path, comment.line)
                    continue

                sim = await embedder.similarity(comment.text, comment.following_code)
                log.debug(
                    "D002 %s:%d  left=%r  right=%r  sim=%.3f  threshold=%.3f  %s",
                    cf.path,
                    comment.line,
                    comment.text[:120],
                    comment.following_code[:120],
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
                            line=comment.line,
                            message=(
                                f"Comment doesn't match next {ctx_lines} lines "
                                f"(similarity {sim:.2f} < {threshold:.2f}). "
                                "Update or remove the comment."
                            ),
                            similarity=sim,
                            threshold=threshold,
                        )
                    )
        return violations
