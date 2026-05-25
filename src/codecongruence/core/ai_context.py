"""Generate AI-tool context files during ``codecongruence init``.

Reads template files from the bundled ``agents/`` directory and writes them
to the appropriate locations in the user's repo so AI assistants understand
every rule and fix strategy without consulting external docs.

Template files live at ``<package>/agents/`` (bundled via pyproject.toml
``force-include``). Destinations when ``init`` runs in a user's repo:

- ``agents/codecongruence.md``  → ``claude/skills/codecongruence.md``
- ``agents/codecongruence.mdc`` → ``.cursor/rules/codecongruence.mdc``
- ``agents/AGENTS.md``          → appended to ``AGENTS.md`` (created if absent)
"""

from __future__ import annotations

import re
from importlib.resources import files as _pkg_files
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["write_ai_context_files"]

_AGENTS_MARKER = "## codecongruence"


def _template(filename: str) -> str:
    return (_pkg_files("codecongruence") / "agents" / filename).read_text(encoding="utf-8")


def _write_if_absent(path: Path, content: str, *, force: bool) -> bool:
    """Write *content* to *path*, creating parent dirs as needed.

    Args:
        path: Destination file path.
        content: Text to write.
        force: Overwrite even if the file already exists.

    Returns:
        ``True`` when the file was written, ``False`` when it already
        existed and *force* was not set.
    """
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _append_agents_md(path: Path, *, force: bool) -> bool:
    """Append the codecongruence section to an existing AGENTS.md.

    Args:
        path: Path to the AGENTS.md file (created if absent).
        force: When ``True`` replace an existing ``## codecongruence`` section.

    Returns:
        ``True`` when the section was written (new file or appended),
        ``False`` when the section already existed and *force* was not set.
    """
    section = _template("AGENTS.md")

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(section, encoding="utf-8")
        return True

    existing = path.read_text(encoding="utf-8")
    if _AGENTS_MARKER in existing:
        if not force:
            return False
        pattern = re.compile(
            r"## codecongruence\b.*?(?=\n## |\Z)",
            re.DOTALL,
        )
        updated = pattern.sub(section.rstrip("\n"), existing)
        path.write_text(updated, encoding="utf-8")
        return True

    path.write_text(existing.rstrip("\n") + "\n\n" + section, encoding="utf-8")
    return True


def write_ai_context_files(
    repo_root: Path,
    *,
    force: bool = False,
) -> list[tuple[Path, bool]]:
    """Write AI-tool context files for Claude Code, Cursor, and OpenAI Codex.

    Each file teaches that AI tool about codecongruence rules so it can
    interpret and fix violations without consulting external docs. Templates
    are read from the bundled ``agents/`` directory.

    Files written (relative to *repo_root*):

    - ``claude/skills/codecongruence.md`` — Claude Code skill
    - ``.cursor/rules/codecongruence.mdc`` — Cursor MDC rule
    - ``AGENTS.md`` — OpenAI Codex instructions (section appended or file created)

    Args:
        repo_root: The git repository root to write files into.
        force: Overwrite files that already exist.

    Returns:
        List of ``(path, was_written)`` tuples — one per file. ``was_written``
        is ``False`` when the file already existed and *force* was not set.
    """
    results: list[tuple[Path, bool]] = []

    claude_skill = repo_root / "claude" / "skills" / "codecongruence.md"
    results.append((
        claude_skill,
        _write_if_absent(claude_skill, _template("codecongruence.md"), force=force),
    ))

    cursor_rule = repo_root / ".cursor" / "rules" / "codecongruence.mdc"
    results.append((
        cursor_rule,
        _write_if_absent(cursor_rule, _template("codecongruence.mdc"), force=force),
    ))

    agents_md = repo_root / "AGENTS.md"
    results.append((agents_md, _append_agents_md(agents_md, force=force)))

    return results
