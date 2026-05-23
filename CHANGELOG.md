# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- `--purge-models` flag added to the CLI: removes `~/.cache/codecongruence` and
    exits. Useful after switching models or freeing disk space.

- `codecongruence.toml.example` added — a fully commented reference config
    covering every global and per-rule option with examples, calibration tips,
    and CI guidance. Serves as the canonical documentation for configuration.

- Rule D005 renamed from `changelog_exists` to `docs_on_change`; redesigned as
    a two-stage check (structural: at least one doc file changed; semantic: doc
    diff must align with code diff). Configurable `docs_files` and
    `trigger_paths` replace the old `changelog_path` / `unreleased_header`.

- Complete Google-style `Args:` coverage across all `src/` functions — every
    parameter now appears in its function's formal Args section, satisfying both
    D006 (word-boundary mention) and ruff D417 (pydoclint Args completeness).

- `pyproject.toml` ruff config: added `PLR0912` ignore for `parsers/python.py`
    (match statement in param extraction has many branches by necessity).

- `[rules.params_in_docstring]` in `codecongruence.toml`: added
    `exclude = ["tests/**"]` (pytest fixtures are injected, not user params) and
    `exclude_functions = ["main"]` (Typer CLI params are self-documenting).

- `TextReporter` now warns when no staged files are found instead of exiting
    silently, making the "nothing to check" state obvious to users.

- Text reporter: violation table always shown (not just in --verbose); summary
    line no longer lists rule names.

- `init` now passes the git-discovered repo root to `default_config_path`,
    fixing incorrect config paths when invoked from a subdirectory.

- Enhance embedder with async similarity and add model cache directory support.

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
