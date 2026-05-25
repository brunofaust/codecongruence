# CLI reference

```text
codecongruence [OPTIONS] [COMMAND]
```

## Global options

| Flag                 | Short | Type         | Default | What it does                                                                                                                                 |
| -------------------- | ----- | ------------ | ------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `--rule`             | `-r`  | str          | —       | Run only a single rule. Pass either the `rule_id` slug (`docstring_vs_body`) or the short code (`D001`, `C001`).                             |
| `--config`           | `-c`  | path         | auto    | Path to a TOML config. Layout (`codecongruence.toml` vs `pyproject.toml`) is auto-detected from the section name.                            |
| `--all`              |       | flag         | off     | Scan the whole repo, not just staged changes. Useful for ad-hoc audits and CI.                                                               |
| `--format`           | `-f`  | `text\|json` | `text`  | Output format. `json` is stable, see "JSON schema" below.                                                                                    |
| `--verbose`          | `-v`  | flag         | off     | Print per-check details even on success.                                                                                                     |
| `--include-unstaged` |       | flag         | off     | Also include unstaged working-tree changes (the hook itself never touches unstaged files; this is for one-off interactive use).              |
| `--update-baseline`  |       | flag         | off     | Save all current violations as the new baseline and exit `0`. Commit `.codecongruence/.codecongruence-baseline.json` to share with the team. |
| `--debug`            |       | flag         | off     | Emit per-check similarity scores and pass/fail to stderr. Useful when tuning thresholds.                                                     |
| `--purge-models`     |       | flag         | —       | Delete the model cache (`~/.cache/codecongruence`) and exit.                                                                                 |
| `--version`          |       | flag         | —       | Print the version and exit `0`.                                                                                                              |
| `--help`             |       | flag         | —       | Show help and exit `0`.                                                                                                                      |

## Subcommands

### `codecongruence init`

```bash
codecongruence init                       # writes codecongruence.toml + AI context files
codecongruence init --path /path/to.toml
codecongruence init --force               # overwrite existing files
codecongruence init --no-download         # skip model download
codecongruence init --no-embed            # download model but skip pre-embedding
```

Writes a default `codecongruence.toml` with sensible thresholds. Also generates
AI-tool context files so assistants understand every rule without reading the docs:

| Installed to                       | Tool                                                     |
| ---------------------------------- | -------------------------------------------------------- |
| `claude/skills/codecongruence.md`  | Claude Code (Anthropic) — loaded as a skill              |
| `.cursor/rules/codecongruence.mdc` | Cursor — applied when editing `.py` or `.md` files       |
| `AGENTS.md`                        | OpenAI Codex — section appended (file created if absent) |

Files are skipped if they already exist. Pass `--force` to overwrite. Refuses to
overwrite `codecongruence.toml` without `--force`.

## Exit codes

| Code | Meaning                                                                                                      |
| ---- | ------------------------------------------------------------------------------------------------------------ |
| `0`  | All enabled rules passed.                                                                                    |
| `1`  | At least one rule produced an `error`-severity violation, OR `init` refused to overwrite an existing config. |

## Config resolution

Highest priority wins:

1. `--config FILE` — explicit, auto-detected layout.
1. `pyproject.toml` with a `[tool.codecongruence]` section.
1. `codecongruence.toml` at the repo root.
1. Built-in defaults.

The active config source is recorded in `CodeCongruenceConfig.source` and
shown in `--verbose` output for debugging.

## JSON schema

```jsonc
{
  "ok": false,                          // false if any error-severity violations
  "rules_run": ["docstring_vs_body", "name_vs_body", ...],
  "files_checked": ["src/a.py", ...],
  "violations": [
    {
      "rule_id": "docstring_vs_body",
      "code": "D001",
      "file_path": "src/a.py",
      "line": 42,
      "message": "Docstring drift on `do_thing` (similarity 0.18 < 0.30). ...",
      "similarity": 0.182,
      "threshold": 0.30,
      "severity": "error"
    }
  ]
}
```

The schema is stable across minor versions. New fields may be added; existing
fields will not change type.

## Recipes

```bash
# Pre-commit hook against staged files (default).
codecongruence

# CI-style PR audit on the whole repo, JSON for further processing.
codecongruence --all --format json > codecongruence.json

# Single rule debug, with similarity numbers on every check (not only failures).
codecongruence --rule docstring_vs_body --verbose

# Tune thresholds — see per-check scores while adjusting.
codecongruence --rule name_vs_body --debug

# Use a project-specific override config.
codecongruence -c configs/codecongruence.strict.toml

# Read config from pyproject.toml at a different location.
codecongruence -c /tmp/poetry-project/pyproject.toml

# Adopt gradually — save current violations as baseline, then only fail on new ones.
codecongruence --update-baseline
git add .codecongruence/.codecongruence-baseline.json
git commit -m "chore: add codecongruence baseline"
```
