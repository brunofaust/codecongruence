"""Rule: code diff vs CLAUDE.md diff — catches doc-bypass commits."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING

from codecongruence.core.git import ChangedFile, git_diff
from codecongruence.rules.base import RuleViolation

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

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
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

        sim = embedder.similarity(code_diff_text, doc_diff_text)
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
