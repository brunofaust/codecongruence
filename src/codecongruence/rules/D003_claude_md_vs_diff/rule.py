"""Rule: code diff vs CLAUDE.md diff — catches doc-bypass commits."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING

from codecongruence.core.git import ChangedFile, git_diff
from codecongruence.rules.base import resolve_threshold, similarity_violation

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
        threshold = resolve_threshold(self, config)
        code_globs: list[str] = list(getattr(config, "code_paths", ["src/**"]) or ["src/**"])
        docs_files: list[str] = list(getattr(config, "docs_files", ["CLAUDE.md"]) or ["CLAUDE.md"])

        code_changes = [
            cf for cf in changed_files if any(fnmatch(str(cf.path), g) for g in code_globs)
        ]
        doc_changes = [cf for cf in changed_files if str(cf.path) in docs_files]
        if not code_changes or not doc_changes:
            return []

        root = code_changes[0].repo_root
        code_diff_text = "\n".join([
            await git_diff(cf.path, cwd=root) for cf in code_changes
        ]).strip()
        doc_diff_text = "\n".join([await git_diff(cf.path, cwd=root) for cf in doc_changes]).strip()
        if not code_diff_text or not doc_diff_text:
            return []

        violation = await similarity_violation(
            embedder,
            code_diff_text,
            doc_diff_text,
            rule=self,
            threshold=threshold,
            file_path=str(Path(docs_files[0])),
            line=None,
            log_context=f"D003 code_diff({len(code_diff_text)} chars) vs doc_diff({len(doc_diff_text)} chars)",
            message_template=(
                "Docs diff doesn't match code diff (similarity {sim:.2f} < {threshold:.2f}). "
                "Either the CLAUDE.md update is unrelated to the code change, "
                "or the code change wasn't documented."
            ),
        )
        return [] if violation is None else [violation]
