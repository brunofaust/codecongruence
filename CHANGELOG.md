# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- `init` now passes the git-discovered repo root to `default_config_path`,
    fixing incorrect config paths when invoked from a subdirectory.

### Fixed

- CLI now uses Click's default error handling (`standalone_mode=True`). User
    errors like typos in subcommand names now produce clean error messages with
    suggestions (e.g. "Did you mean 'init'?") instead of raw Python tracebacks.

### Added

- `prek.toml` with a busydone-style lint chain at the repo root: ruff,
    ruff-format, mypy, pytest, pyupgrade, bandit, gitleaks, typos, vulture,
    interrogate, markdownlint, mdformat, pre-commit-hooks, pygrep-hooks,
    uv-lock, validate-pyproject, pyproject-fmt, and codecongruence on itself.
- `pyproject.toml` extended with `[tool.typos]`, `[tool.bandit]`,
    `[tool.coverage]`, `[tool.interrogate]`, `[tool.markdownlint]`, and
    `[tool.vulture]` sections; existing `[tool.ruff]` / `[tool.mypy]` were
    aligned to the busydone style (`C4`, `S`, isort first-party,
    `disallow_incomplete_defs`, `mypy_path = "src"`, etc.).
- Legacy `.pre-commit-config.yaml` removed (replaced by `prek.toml`).
- Usage docs under `docs/usage/`: CLI reference, pre-commit guide, prek guide,
    native git-hook recipe, and a linter-chain integration table.
- Tests: unit coverage for `claude_md_vs_diff` and `pr_description_vs_diff`,
    plus `typer.testing.CliRunner` smoke tests for the CLI (`--version`,
    `--help`, `init`, `--format json`).
- Stable rule **codes**: `C001` (`name_vs_body`), `D001` (`docstring_vs_body`),
    `D002` (`stale_comments`), `D003` (`claude_md_vs_diff`),
    `D004` (`pr_description_vs_diff`), `D005` (`changelog_exists`). Codes appear
    in both text and JSON reporters; `RuleViolation` gained a `code` field.
- `pyproject.toml` config support via `[tool.codecongruence]` (and nested
    `[tool.codecongruence.rules.*]` sections). Compatible with uv, Poetry,
    Hatch, PDM and any other PEP 518 toolchain.
- `--config` / `-c` flag accepts both `codecongruence.toml` and
    `pyproject.toml` layouts; the format is auto-detected.
- `CodeCongruenceConfig.source` records which file produced the loaded
    config (or `None` when defaults were used).
- `discover_config_path()` helper exposing the new resolution order:
    `pyproject.toml` > `codecongruence.toml` > defaults.
- Initial MVP scaffold.
- Six built-in rules: `docstring_vs_body`, `name_vs_body`, `claude_md_vs_diff`,
    `pr_description_vs_diff`, `stale_comments`, `changelog_exists`.
- Local ONNX embeddings via `fastembed` (default model `BAAI/bge-small-en-v1.5`).
- `asyncio.TaskGroup`-based parallel rule execution.
- Typer CLI with `--rule`, `--config`, `--all`, `--format`, `--verbose`,
    `--include-unstaged`, `--version` and the `init` subcommand.
- Text reporter (rich) + JSON reporter.
- Pre-commit hook entry (`.pre-commit-hooks.yaml`).
- GitHub Actions CI: ruff + mypy + pytest + codecongruence-on-itself.
- 32 unit + integration tests using a deterministic bag-of-words fake backend
    so the suite is offline + sub-second.

## [0.1.0] — TBD

- First tagged release.
