"""Rule: documentation files must be updated when code changes."""

from __future__ import annotations

import logging
from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING

from codecongruence.core.git import ChangedFile, git_diff
from codecongruence.rules.base import RuleViolation

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from codecongruence.core.config import RuleConfig
    from codecongruence.core.embedder import Embedder

__all__ = ["DocsOnChangeRule"]


class DocsOnChangeRule:
    """Ensure documentation files are updated whenever code changes.

    Two-stage check:
    1. Structural — at least one file from ``docs_files`` must have staged
       changes when any ``trigger_paths`` file is staged.
    2. Semantic — when ``threshold > 0``, the combined doc diff must be
       semantically similar to the combined code diff (same idea, different
       words is fine; completely unrelated is not).
    """

    rule_id: str = "docs_on_change"
    code: str = "D005"
    description: str = "Documentation files should be updated when code changes."
    default_threshold: float = 0.20
    docs_url: str = (
        "https://github.com/brunofaust/codecongruence/blob/main"
        "/src/codecongruence/rules/D005_changelog_exists/README.md"
    )

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
        """Check that at least one doc file was updated alongside code changes.

        Args:
            changed_files: Files to check (staged or all).
            embedder: Shared embedder for semantic similarity.
            config: Per-rule configuration (threshold, trigger_paths, docs_files).

        Returns:
            Sequence of :class:`RuleViolation`; at most one per run.
        """
        triggers: list[str] = list(getattr(config, "trigger_paths", ["src/**"]) or ["src/**"])
        docs_files: list[Path] = [
            Path(f) for f in (getattr(config, "docs_files", ["CHANGELOG.md"]) or ["CHANGELOG.md"])
        ]
        threshold = self.default_threshold if config.threshold is None else config.threshold

        # Step 1: Any trigger_paths file in the staged set?
        code_files = [cf for cf in changed_files if any(fnmatch(str(cf.path), g) for g in triggers)]
        if not code_files:
            log.debug("D005 SKIP not_triggered  trigger_paths=%s", triggers)
            return []

        # Get code diff — if empty we are likely in --all mode with nothing staged.
        code_diff = "\n".join([await git_diff(cf.path) for cf in code_files]).strip()
        if not code_diff:
            log.debug("D005 SKIP no_staged_code_diff  (--all mode or nothing staged)")
            return []

        # Step 2: Which of the docs_files have staged changes?
        changed_doc_diffs: list[str] = []
        for doc_path in docs_files:
            diff = await git_diff(doc_path, context=200)
            if diff.strip():
                changed_doc_diffs.append(diff)

        changed_count = len(changed_doc_diffs)
        log.debug(
            "D005 code_diff_len=%d  docs_changed=%d/%d  docs=%s",
            len(code_diff),
            changed_count,
            len(docs_files),
            [str(f) for f in docs_files],
        )

        if not changed_doc_diffs:
            return [
                RuleViolation(
                    rule_id=self.rule_id,
                    code=self.code,
                    file_path=str(docs_files[0]),
                    line=None,
                    message=(
                        f"Code changed under {triggers} but none of "
                        f"{[str(f) for f in docs_files]} were updated. "
                        "Document the change."
                    ),
                    similarity=0.0,
                    threshold=threshold,
                )
            ]

        # Step 3: Optional semantic similarity check.
        if threshold <= 0.0:
            log.debug("D005 PASS docs_updated (similarity check disabled)")
            return []

        combined_doc_diff = "\n".join(changed_doc_diffs)
        sim = await embedder.similarity(code_diff, combined_doc_diff)
        log.debug(
            "D005 left=code_diff(%d chars)  right=doc_diff(%d chars)  sim=%.3f  threshold=%.3f  %s",
            len(code_diff),
            len(combined_doc_diff),
            sim,
            threshold,
            "FAIL" if sim < threshold else "PASS",
        )

        if sim < threshold:
            return [
                RuleViolation(
                    rule_id=self.rule_id,
                    code=self.code,
                    file_path=str(docs_files[0]),
                    line=None,
                    message=(
                        f"Docs updated but not aligned with the code diff "
                        f"(similarity {sim:.2f} < {threshold:.2f}). "
                        "Make sure your docs describe what actually changed."
                    ),
                    similarity=sim,
                    threshold=threshold,
                )
            ]

        return []
