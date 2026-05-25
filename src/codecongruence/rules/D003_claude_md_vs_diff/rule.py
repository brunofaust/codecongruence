"""Rule: code diff vs CLAUDE.md diff — catches doc-bypass commits."""

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

__all__ = ["ClaudeMdVsDiffRule"]


class ClaudeMdVsDiffRule:
    """If both code and docs changed, they must talk about the same thing."""

    rule_id: str = "claude_md_vs_diff"
    code: str = "D003"
    description: str = "Code diff should be semantically aligned with the docs diff."
    default_threshold: float = 0.20
    docs_url: str = (
        "https://github.com/brunofaust/codecongruence/blob/main"
        "/src/codecongruence/rules/D003_claude_md_vs_diff/README.md"
    )

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
        """Check that code and docs diffs are semantically aligned.

        Args:
            changed_files: Files to check (staged or all).
            embedder: Shared embedder for semantic similarity.
            config: Per-rule configuration (threshold, excludes, extras).

        Returns:
            Sequence of :class:`RuleViolation`; at most one per run.
        """
        threshold = self.default_threshold if config.threshold is None else config.threshold
        code_globs: list[str] = list(getattr(config, "code_paths", ["src/**"]) or ["src/**"])
        docs_files: list[str] = list(getattr(config, "docs_files", ["CLAUDE.md"]) or ["CLAUDE.md"])

        code_changes = [
            cf for cf in changed_files if any(fnmatch(str(cf.path), g) for g in code_globs)
        ]
        doc_changes = [cf for cf in changed_files if str(cf.path) in docs_files]
        if not code_changes or not doc_changes:
            return []

        code_diff_text = "\n".join([await git_diff(cf.path) for cf in code_changes]).strip()
        doc_diff_text = "\n".join([await git_diff(cf.path) for cf in doc_changes]).strip()
        if not code_diff_text or not doc_diff_text:
            return []

        sim = await embedder.similarity(code_diff_text, doc_diff_text)
        log.debug(
            "D003 code_diff_len=%d  doc_diff_len=%d  sim=%.3f  threshold=%.3f  %s",
            len(code_diff_text),
            len(doc_diff_text),
            sim,
            threshold,
            "FAIL" if sim < threshold else "PASS",
        )
        if sim >= threshold:
            return []

        return [
            RuleViolation(
                rule_id=self.rule_id,
                code=self.code,
                file_path=str(Path(docs_files[0])),
                line=None,
                message=(
                    f"Docs diff doesn't match code diff (similarity {sim:.2f} < {threshold:.2f}). "
                    "Either the CLAUDE.md update is unrelated to the code change, "
                    "or the code change wasn't documented."
                ),
                similarity=sim,
                threshold=threshold,
            )
        ]
