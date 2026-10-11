# CLI reference

```text
codecongruence [OPTIONS] [FILES]...
codecongruence [OPTIONS] COMMAND [ARGS]...
```

## Scope

| Invocation                       | Checks                                                                         |
| -------------------------------- | ------------------------------------------------------------------------------ |
| `codecongruence`                 | The staged diff: added lines of staged files (`--include-unstaged` adds more). |
| `codecongruence --all`           | Every tracked and untracked non-ignored file, whole-file.                      |
| `codecongruence FILE [FILE ...]` | Exactly those files, whole-file (like `--all` restricted to the list).         |

With explicit files every line is in scope. Paths resolve against the current
directory and may be absolute. Missing or deleted paths, directories and paths
outside the repo are skipped, so a hook that passes a deleted file does not
crash the run. Files no parser supports are ignored as under `--all`. The first
positional that names a subcommand (`init`) runs that subcommand; use
`codecongruence -- init` to check a file literally named `init`.

FILES cannot be combined with `--all`, `--include-unstaged` or
`--update-baseline`. Each pairing is ambiguous, or would rewrite the whole
baseline from a partial run, so it exits `2`.

## Global options

| Flag                 | Short | Type          | Default | What it does                                                                                                                                                                                                                                                                                          |
| -------------------- | ----- | ------------- | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--rule`             | `-r`  | str           | —       | Run only a single rule, even if disabled in config. Pass either the `rule_id` slug (`docstring_vs_body`) or the short code (`D001`, `C001`). Unknown rules exit `2`.                                                                                                                                  |
| `--config`           | `-c`  | path          | auto    | Path to a TOML config. Layout (`codecongruence.toml` vs `pyproject.toml`) is auto-detected from the section name.                                                                                                                                                                                     |
| `--all`              |       | flag          | off     | Scan the whole repo, not just staged changes. Useful for ad-hoc audits and CI.                                                                                                                                                                                                                        |
| `--format`           | `-f`  | `text\|json`  | `text`  | Output format. `json` is stable, see "JSON schema" below.                                                                                                                                                                                                                                             |
| `--verbose`          | `-v`  | flag          | off     | Print per-check details even on success.                                                                                                                                                                                                                                                              |
| `--include-unstaged` |       | flag          | off     | Also include unstaged working-tree changes (the hook itself never touches unstaged files; this is for one-off interactive use).                                                                                                                                                                       |
| `--update-baseline`  |       | flag          | off     | Save all current violations as the new baseline and exit `0`. Commit `.codecongruence/.codecongruence-baseline.json` to share with the team.                                                                                                                                                          |
| `--prune-baseline`   |       | flag          | off     | Remove baseline entries whose violation no longer exists (only entries for checked files, lines and rules that ran). Never adds entries. Exits non-zero only if unsuppressed violations remain. Mutually exclusive with `--update-baseline`. Without it, stale entries are reported and fail the run. |
| `--backend`          |       | auto/mlx/onnx | config  | Embedding engine, overriding `backend` in the config. `auto` uses MLX on Apple Silicon when the `mlx` extra is installed and the model is mapped, else ONNX. `mlx` exits `2` if unavailable. The resolved backend is printed once to stderr.                                                          |
| `--debug`            |       | flag          | off     | Emit per-check similarity scores and pass/fail to stderr. Useful when tuning thresholds.                                                                                                                                                                                                              |
| `--purge-models`     |       | flag          | —       | Delete the model cache (`~/.cache/codecongruence`) and exit.                                                                                                                                                                                                                                          |
| `--version`          |       | flag          | —       | Print the version and exit `0`.                                                                                                                                                                                                                                                                       |
| `--help`             |       | flag          | —       | Show help and exit `0`.                                                                                                                                                                                                                                                                               |

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

| Installed to                             | Tool                                                     |
| ---------------------------------------- | -------------------------------------------------------- |
| `.claude/skills/codecongruence/SKILL.md` | Claude Code (Anthropic) — loaded as a skill              |
| `.cursor/rules/codecongruence.mdc`       | Cursor — applied when editing `.py` or `.md` files       |
| `AGENTS.md`                              | OpenAI Codex — section appended (file created if absent) |

Files are skipped if they already exist. Pass `--force` to overwrite. Refuses to
overwrite `codecongruence.toml` without `--force`.

## Exit codes

| Code | Meaning                                                                                                                               |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `0`  | All enabled rules passed.                                                                                                             |
| `2`  | Invalid invocation: unknown `--rule`, conflicting baseline flags, or `--backend mlx` (or `backend = "mlx"`) that cannot be satisfied. |
| `1`  | At least one rule produced an `error`-severity violation, OR `init` refused to overwrite an existing config.                          |

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
  "backend": "onnx",                    // resolved embedding backend: "mlx" or "onnx"
  "backend_reason": "auto: ...",        // only present when auto fell back to onnx
  "stale_baseline_entries": [],         // baseline entries whose violation is gone; any entry makes ok false
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

# Exactly these files, whole-file (what the published hook runs).
codecongruence src/app.py src/util.py

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
