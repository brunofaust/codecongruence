"""Rule: PR description vs the full diff (CI-only; opt-in)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from codecongruence.core.git import ChangedFile, git_diff_unified
from codecongruence.rules.base import RuleViolation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from codecongruence.core.config import RuleConfig
    from codecongruence.core.embedder import Embedder

__all__ = ["PrDescriptionVsDiffRule"]


class PrDescriptionVsDiffRule:
    """Catches lazy "fix bug" descriptions on 500-line PRs."""

    rule_id: str = "pr_description_vs_diff"
    code: str = "D004"
    description: str = "PR description should describe what the diff actually changes."
    default_threshold: float = 0.25

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
        body = os.environ.get("CODECONGRUENCE_PR_BODY", "").strip()
        if not body or not changed_files:
            return []

        threshold = self.default_threshold if config.threshold is None else config.threshold
        diff = (await git_diff_unified()).strip()
        if not diff:
            return []

        sim = embedder.similarity(body, diff)
        if sim >= threshold:
            return []

        return [
            RuleViolation(
                rule_id=self.rule_id,
                code=self.code,
                file_path="<PR description>",
                line=None,
                message=(
                    f"PR description doesn't match the diff "
                    f"(similarity {sim:.2f} < {threshold:.2f}). "
                    "Expand the description so reviewers know what changed and why."
                ),
                similarity=sim,
                threshold=threshold,
            )
        ]
