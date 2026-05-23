"""Rule: inline comment vs the code that follows it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from codecongruence.parsers import get_parser
from codecongruence.rules.base import RuleViolation

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

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
        threshold = self.default_threshold if config.threshold is None else config.threshold
        ctx_lines = int(getattr(config, "context_lines", 5) or 5)

        violations: list[RuleViolation] = []
        for cf in changed_files:
            parser = get_parser(cf.path.suffix)
            if parser is None:
                continue
            try:
                source = cf.path.read_text(encoding="utf-8")
            except OSError:
                continue

            for comment in parser.iter_comments(source, context_lines=ctx_lines):
                if cf.added_ranges and not cf.overlaps(comment.line, comment.line + ctx_lines):
                    continue

                sim = embedder.similarity(comment.text, comment.following_code)
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
