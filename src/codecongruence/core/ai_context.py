"""Generate AI-tool context files during ``codecongruence init``.

Writes skill / rules / agent-instructions for Claude Code, Cursor, and
OpenAI Codex so those AI agents understand what codecongruence violations
mean and how to fix them — without needing to read the docs separately.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["write_ai_context_files"]

_RULES_REFERENCE = """\
## Rules

| Code | Rule                     | What it catches                                               |
|------|--------------------------|---------------------------------------------------------------|
| C001 | `name_vs_body`           | Function name contradicts what the body actually does         |
| C002 | `param_name_vs_usage`    | Parameter name clashes with how it is used in the body        |
| D001 | `docstring_vs_body`      | Docstring describes stale behaviour after a refactor          |
| D002 | `stale_comments`         | Inline comment describes behaviour the code no longer has     |
| D003 | `claude_md_vs_diff`      | Unrelated CLAUDE.md edit buried inside a large code change    |
| D004 | `pr_description_vs_diff` | PR description does not match the actual diff (CI-only)       |
| D005 | `docs_on_change`         | `src/` changed but no docs file updated (CHANGELOG, README…)  |
| D006 | `params_in_docstring`    | Docstring exists but a parameter is not documented in it      |

### Fix strategies

- **C001** — rename the function to match what it does, OR rewrite the body to match the declared intent.
- **C002** — rename the parameter to reflect its actual role in the body, OR restructure the usage.
- **D001** — update the docstring to describe what the function currently does.
- **D002** — delete the stale comment or rewrite it to describe the current behaviour.
- **D003** — split the commit (CLAUDE.md change alone), or expand CLAUDE.md to actually document the code change.
- **D004** — write a PR description that covers every meaningful change in the diff.
- **D005** — add a CHANGELOG entry or README note explaining what changed in `src/`.
- **D006** — add the missing parameter to the `Args:` section of the docstring.

## Reading violations

```
src/auth/token.py:42  C001  name_vs_body  similarity=0.18 < 0.25
  Function name suggests one behaviour, body does another.
```

Fields: `file:line  CODE  rule_id  similarity=<score> < <threshold>`

Lower similarity = more drift. Threshold is configurable per rule in
`codecongruence.toml` or `pyproject.toml [tool.codecongruence]`.

## Commands

```bash
codecongruence              # check staged changes (runs on git commit)
codecongruence --all        # scan whole repo without staging
codecongruence --rule docstring_vs_body  # single rule
codecongruence --format json             # machine-readable (CI)
```

## Config tuning

```toml
# codecongruence.toml — lower threshold = stricter (fewer violations reported)
[rules.docstring_vs_body]
threshold = 0.30        # raise to 0.40 if too noisy on short functions

[rules.name_vs_body]
threshold = 0.25
ignore_names = ["main", "run", "setup"]  # skip these names entirely
```
"""

_CLAUDE_SKILL = """\
---
name: codecongruence
description: >
  Use when codecongruence pre-commit violations appear. codecongruence
  detects semantic drift between code and its surrounding text artifacts
  (docstrings, comments, function names, CLAUDE.md, CHANGELOG). Apply
  this skill to understand what each rule checks and how to fix violations.
---

# codecongruence — semantic drift checker

codecongruence detects **semantic drift** between code and surrounding
artifacts. It uses local sentence embeddings (ONNX, offline) — no API calls,
no PyTorch. It is NOT a syntax linter; ruff/mypy catch syntax. This catches
things they miss: a `validate_email()` that quietly started sending emails, or
a docstring that describes the behaviour before a recent refactor.

{rules}
"""

_CURSOR_RULE = """\
---
description: codecongruence semantic drift violations — how to interpret and fix each rule
globs: ["**/*.py", "**/*.md"]
alwaysApply: false
---

# codecongruence — semantic drift checker

This repo runs [codecongruence](https://github.com/brunofaust/codecongruence)
as a pre-commit hook. It detects **semantic drift** between code and surrounding
artifacts (docstrings, comments, function names, CLAUDE.md, CHANGELOG) using
local sentence embeddings — offline, no API calls.

When you see a codecongruence violation in pre-commit output, apply the fix
strategy below for that rule code.

{rules}
"""

_AGENTS_SECTION = """\
## codecongruence

This repository uses [codecongruence](https://github.com/brunofaust/codecongruence)
as a pre-commit hook to detect **semantic drift** between code and surrounding
text artifacts (docstrings, comments, function names, CLAUDE.md, CHANGELOG).
It uses local sentence embeddings (ONNX, offline) — no API calls, no PyTorch.

When you see a codecongruence violation, read the rule code and apply the
matching fix strategy below.

{rules}
"""


def _claude_skill_content() -> str:
    return _CLAUDE_SKILL.format(rules=_RULES_REFERENCE)


def _cursor_rule_content() -> str:
    return _CURSOR_RULE.format(rules=_RULES_REFERENCE)


def _agents_section_content() -> str:
    return _AGENTS_SECTION.format(rules=_RULES_REFERENCE)


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
    section = _agents_section_content()
    marker = "## codecongruence"

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(section, encoding="utf-8")
        return True

    existing = path.read_text(encoding="utf-8")
    if marker in existing:
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
    interpret and fix violations without consulting external docs.

    Files written (relative to *repo_root*):

    - ``.claude/skills/codecongruence.md`` — Claude Code skill
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

    claude_skill = repo_root / ".claude" / "skills" / "codecongruence.md"
    results.append((
        claude_skill,
        _write_if_absent(claude_skill, _claude_skill_content(), force=force),
    ))

    cursor_rule = repo_root / ".cursor" / "rules" / "codecongruence.mdc"
    results.append((
        cursor_rule,
        _write_if_absent(cursor_rule, _cursor_rule_content(), force=force),
    ))

    agents_md = repo_root / "AGENTS.md"
    results.append((agents_md, _append_agents_md(agents_md, force=force)))

    return results
