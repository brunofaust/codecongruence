# CLAUDE.md — codecongruence

This file tells Claude Code how to work in this repo. Keep it short; link out for detail.

## What this is

`codecongruence` is a semantic pre-commit hook framework. It detects drift
between code and surrounding artifacts (docstrings, comments, function names,
CLAUDE.md, PR descriptions, CHANGELOG) using **local** sentence embeddings via
`fastembed` (ONNX, no PyTorch, no API calls).

## Conventions

- **Python 3.12+** syntax. Async-first where I/O happens. `asyncio.TaskGroup`
    for parallel rules; never `gather` without a TaskGroup.
- **Type hints on everything.** `mypy --strict` must pass.
- **Frozen dataclasses** for internal data structures.
- **Pydantic** for config parsing; **tomllib** for the TOML read.
- **Config sources** (priority order): explicit `--config FILE` →
    `pyproject.toml [tool.codecongruence]` → `codecongruence.toml` → defaults.
    See `core/config.py::discover_config_path`.
- **`__all__`** in every module; no `_`-prefix for module-level private names.
- **No `dict[str, Any]`** in function signatures outside the TOML load.
- **No bare `except Exception`** unless re-raised with context.

## Architecture (one paragraph)

`cli.py` → `load_config()` → `Embedder` (one instance per run, content-hash
cached) → `RuleRunner` (uses `asyncio.TaskGroup`) → each `Rule` returns a
`Sequence[RuleViolation]` → reporter prints text or JSON.

Each rule lives in its own **code-named subfolder** under
`src/codecongruence/rules/`. Example: `C001_name_vs_body/rule.py`. The
eight rules are:

| Code | Folder                         | Rule id                  |
| ---- | ------------------------------ | ------------------------ |
| C001 | `C001_name_vs_body/`           | `name_vs_body`           |
| C002 | `C002_param_name_vs_usage/`    | `param_name_vs_usage`    |
| D001 | `D001_docstring_vs_body/`      | `docstring_vs_body`      |
| D002 | `D002_stale_comments/`         | `stale_comments`         |
| D003 | `D003_claude_md_vs_diff/`      | `claude_md_vs_diff`      |
| D004 | `D004_pr_description_vs_diff/` | `pr_description_vs_diff` |
| D005 | `D005_changelog_exists/`       | `docs_on_change`         |
| D006 | `D006_params_in_docstring/`    | `params_in_docstring`    |

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for details.

## Adding a new rule

1. Create `src/codecongruence/rules/<CODE>_<name>/` with three files:
    - `rule.py` — implementation (the `Rule` protocol class)
    - `__init__.py` — re-exports the rule class
    - `README.md` — explains what it catches, how it works, and config options
1. Implement the `Rule` protocol from `rules/base.py`: class with `rule_id`,
    `code`, `description`, `default_threshold`, and an
    `async def check(changed_files, embedder, config) -> Sequence[RuleViolation]`.
1. Register it in `core/runner.py::default_rules()`.
1. Add a section to `codecongruence.toml`, `codecongruence.toml.example`, and
    to the spec block in `cli.py`'s `_DEFAULT_TOML`.
1. Write a unit test under `tests/unit/rules/<CODE>_<name>/test_<name>.py`
    and extend `tests/integration/test_full_run.py`.

## Eat own dogfood

The repo runs `codecongruence` on itself in CI. Any PR must:

- Pass all eight rules on the diff.
- Add a bullet under `## [Unreleased]` in `CHANGELOG.md`.
- Update docs (this file, `ARCHITECTURE.md`, `README.md`) when the change
    affects architecture or public API.

## Local commands

```bash
uv sync --extra dev
uv run pytest                       # 93 tests, <2s
uv run ruff check src tests
uv run ruff format src tests
uv run mypy
uv run codecongruence --all         # full-repo self check
```

## Don't

- **Don't** call the real embedding model in tests — use the `fake_embedder`
    fixture (bag-of-words backend) so the suite stays offline + sub-second.
- **Don't** hardcode thresholds inside rules — they read from `RuleConfig`.
- **Don't** add new top-level rules to `__init__` of `rules/` — register them
    only in `runner.default_rules()`.
