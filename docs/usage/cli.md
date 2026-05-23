# CLI reference

```text
codecongruence [OPTIONS] [COMMAND]
```

## Global options

| Flag                 | Short | Type         | Default | What it does                                                                                                                    |
| -------------------- | ----- | ------------ | ------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `--rule`             | `-r`  | str          | —       | Run only a single rule. Pass either the `rule_id` slug (`docstring_vs_body`) or the short code (`D001`, `C001`).                |
| `--config`           | `-c`  | path         | auto    | Path to a TOML config. Layout (`codecongruence.toml` vs `pyproject.toml`) is auto-detected from the section name.               |
| `--all`              |       | flag         | off     | Scan the whole repo, not just staged changes. Useful for ad-hoc audits and CI.                                                  |
| `--format`           | `-f`  | `text\|json` | `text`  | Output format. `json` is stable, see "JSON schema" below.                                                                       |
| `--verbose`          | `-v`  | flag         | off     | Print per-check details even on success.                                                                                        |
| `--include-unstaged` |       | flag         | off     | Also include unstaged working-tree changes (the hook itself never touches unstaged files; this is for one-off interactive use). |
| `--version`          |       | flag         | —       | Print the version and exit `0`.                                                                                                 |
| `--help`             |       | flag         | —       | Show help and exit `0`.                                                                                                         |

## Subcommands

### `codecongruence init`

```bash
codecongruence init                       # writes ./codecongruence.toml
codecongruence init --path /path/to.toml
codecongruence init --force               # overwrite existing
```

Writes a default `codecongruence.toml` with sensible thresholds. Refuses to
overwrite without `--force`.

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

# Use a project-specific override config.
codecongruence -c configs/codecongruence.strict.toml

# Read config from pyproject.toml at a different location.
codecongruence -c /tmp/poetry-project/pyproject.toml
```
