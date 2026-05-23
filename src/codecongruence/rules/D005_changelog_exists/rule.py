"""Rule: enforce a CHANGELOG ``[Unreleased]`` entry whenever src/ changes."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING

from codecongruence.core.embedder import Embedder  # noqa: TC001  (kept for protocol parity)
from codecongruence.core.git import ChangedFile, git_diff
from codecongruence.rules.base import RuleViolation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from codecongruence.core.config import RuleConfig

__all__ = ["ChangelogExistsRule"]


class ChangelogExistsRule:
    """Pure structural check — no embeddings needed.

    Fail if code changed under ``trigger_paths`` AND no new ``- `` bullet was
    added under the ``[Unreleased]`` header in CHANGELOG.md.
    """

    rule_id: str = "changelog_exists"
    code: str = "D005"
    description: str = "Code changes should be recorded under CHANGELOG `[Unreleased]`."
    default_threshold: float = 0.0  # not embedding-based

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
        triggers: list[str] = list(getattr(config, "trigger_paths", ["src/**"]) or ["src/**"])
        changelog_path = Path(getattr(config, "changelog_path", "CHANGELOG.md") or "CHANGELOG.md")
        unreleased = str(getattr(config, "unreleased_header", "## [Unreleased]"))

        triggered = any(any(fnmatch(str(cf.path), g) for g in triggers) for cf in changed_files)
        if not triggered:
            return []

        if not changelog_path.exists():  # noqa: ASYNC240 — cheap stat call, not worth aiofiles
            return [
                RuleViolation(
                    rule_id=self.rule_id,
                    code=self.code,
                    file_path=str(changelog_path),
                    line=None,
                    message=(
                        f"Code changed under {triggers} but {changelog_path} is missing. "
                        f"Add the file with an `{unreleased}` section and document this change."
                    ),
                    similarity=0.0,
                    threshold=0.0,
                )
            ]

        diff = await git_diff(changelog_path)
        added_under_unreleased = _has_added_bullet_under_header(diff, unreleased)
        if added_under_unreleased:
            return []

        return [
            RuleViolation(
                rule_id=self.rule_id,
                code=self.code,
                file_path=str(changelog_path),
                line=None,
                message=(
                    f"Code changed under {triggers} but no new bullet under "
                    f"`{unreleased}` in {changelog_path}. Document the change."
                ),
                similarity=0.0,
                threshold=0.0,
            )
        ]


def _has_added_bullet_under_header(diff: str, header: str) -> bool:
    """True if the diff adds at least one ``- `` bullet under ``header``.

    Walks the unified diff; tracks whether the current hunk has passed the
    ``[Unreleased]`` header on either the old or new side.
    """
    in_unreleased = False
    for raw in diff.splitlines():
        if raw.startswith("@@"):
            in_unreleased = False
            continue
        stripped = raw[1:] if raw[:1] in {"+", "-", " "} else raw
        if stripped.lstrip().startswith(header):
            in_unreleased = True
            continue
        if stripped.lstrip().startswith("## ") and not stripped.lstrip().startswith(header):
            in_unreleased = False
            continue
        if in_unreleased and raw.startswith("+") and not raw.startswith("+++"):
            content = raw[1:].lstrip()
            if content.startswith(("- ", "* ")):
                return True
    return False
