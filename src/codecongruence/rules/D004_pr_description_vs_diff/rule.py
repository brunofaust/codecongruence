"""Rule: PR description vs the full diff (CI-only; opt-in)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from codecongruence.core.git import ChangedFile, git_diff_unified
from codecongruence.rules.base import RuleViolation, resolve_threshold, similarity_violation

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
    docs_url: str = (
        "https://github.com/brunofaust/codecongruence/blob/main"
        "/src/codecongruence/rules/D004_pr_description_vs_diff/README.md"
    )

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
        """Check that the PR description matches the staged diff.

        Args:
            changed_files: Files to check (staged or all).
            embedder: Shared embedder for semantic similarity.
            config: Per-rule configuration (threshold, excludes, extras).

        Returns:
            Sequence of :class:`RuleViolation`; at most one per run.
        """
        body = os.environ.get("CODECONGRUENCE_PR_BODY", "").strip()
        if not body or not changed_files:
            return []

        threshold = resolve_threshold(self, config)
        diff = (await git_diff_unified(cwd=changed_files[0].repo_root)).strip()
        if not diff:
            return []

        violation = await similarity_violation(
            embedder,
            body,
            diff,
            rule=self,
            threshold=threshold,
            file_path="<PR description>",
            line=None,
            log_context=f"D004 pr_body({len(body)} chars) vs diff({len(diff)} chars)",
            message_template=(
                "PR description doesn't match the diff "
                "(similarity {sim:.2f} < {threshold:.2f}). "
                "Expand the description so reviewers know what changed and why."
            ),
        )
        return [] if violation is None else [violation]
