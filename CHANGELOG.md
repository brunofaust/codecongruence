# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- Fixed: the release workflow ran `semantic-release version --no-commit`, so
    the version bump and CHANGELOG that PSR generated never landed back on
    `main` — `pyproject.toml` was stuck at 0.1.1 while releases advanced to
    v0.5.0. The workflow now checks out `main` explicitly and lets PSR commit
    and push; `pyproject.toml` is realigned to the already-released 0.5.0.

- Fixed: an unknown `--rule` id silently selected zero rules and exited 0 — a
    typo in a pre-commit hook would disable checking without anyone noticing.
    Unknown rules now exit `2` with the list of valid ids. `--rule` also
    accepts short codes (`D001`) as the docs always claimed, and explicitly
    runs the rule even when disabled in config.

- `RuleRunner` and the rules no longer depend on the process working directory:
    `ChangedFile` carries its `repo_root` (with an `abs_path` helper), file
    reads resolve against it, and every git invocation inside rules passes an
    explicit `cwd`. Library callers can now run from any directory; reported
    paths stay repo-relative so baselines remain machine-independent (C003
    `scope = "full"` previously reported absolute paths).

- Fixed: emptying the embedding cache via `save(force_cleanup=True)` left the
    stale `embeddings.npz` on disk, resurrecting evicted entries on the next
    run. An emptied cache now removes the file.

- CI workflows upgraded off deprecated Node 20 actions
    (`actions/checkout@v6`, pinned `astral-sh/setup-uv@v8.2.0`).

- `mypy --strict` now covers `tests/` as well as `src/` (the gate previously
    checked `src/` only despite the docs claiming repo-wide strictness).

- Fixed: `cache_ttl_days` set in `codecongruence.toml` / `pyproject.toml` was
    silently ignored — `load_config` never read it from the TOML section, so the
    embedding-cache TTL was always the 30-day default.

- Fixed: `codecongruence init` wrote the Claude Code context file to
    `claude/skills/codecongruence.md`, a path Claude Code never reads. It now
    lands at the standard skill location `.claude/skills/codecongruence/SKILL.md`.

- Fixed: running the CLI from a subdirectory of the repo silently checked
    nothing — git reported paths relative to the repo root while rules read them
    relative to the invocation directory. The CLI now anchors itself at the repo
    root before running rules.

- `Embedder` gained a public async `embed_batch()` method and a `cache_size`
    property, replacing private-attribute access from rule C003 and the CLI.

- Test suite is now hermetic against host git configuration: throwaway repos
    ignore global/system git config (commit signing, hooks, templates) and the
    `init` CLI test no longer downloads the real embedding model.

- Embedding cache garbage collection: two-layer GC strategy via TTL eviction
    and compaction. Entries not accessed within `cache_ttl_days` (default: 30)
    are discarded at load time. `Embedder.compact()` called after `--all` runs
    removes embeddings for texts no longer in the repo. Tracks `last_used`
    timestamps in NPZ metadata; configurable via `cache_ttl_days` in config
    (0 disables TTL). Significant space savings on repeated runs and model
    switches.

- Embedder cache format changed from `embeddings.json.gz` to `embeddings.npz`
    (NumPy compressed binary). Binary float32 storage is ~2-3× smaller and
    faster to load than JSON-encoded floats. Existing `embeddings.json.gz`
    files are ignored on first run; the cache rebuilds automatically.

- Automated release pipeline: `python-semantic-release` runs on push to main,
    reads conventional commits, bumps `pyproject.toml`, writes `CHANGELOG.md`,
    and creates a GitHub release + git tag. No manual version bumps or CHANGELOG
    edits required. `commitizen` prek hook validates conventional commit format
    on every commit. D005 (`docs_on_change`) updated to require only `README.md`
    (not `CHANGELOG.md`, which PSR now owns).

- Rule C001 (`name_vs_body`) and C002 (`param_name_vs_usage`): added
    `include_comments` config option (default `False` for C001, `True` for C002).
    C001 strips `#` and `//` inline comments from function body before embedding
    to prevent stray comments from inflating name-vs-body similarity. C002 keeps
    comments in usage context by default because comments like "# validate
    user_id" are valid semantic signal about what the parameter represents.
    Extracted shared `strip_comments()` and `INLINE_COMMENT_RE` from D001 to
    `rules/base.py` for reuse across rules.

- Rule D001 (`docstring_vs_body`): added `include_comments` config option
    (default `False`) that strips `#` and `//` inline comments from function
    body before embedding. Prevents comment text from inflating similarity
    scores and masking real docstring drift. Updated `cli.py`: renamed
    `_DEFAULT_TOML` → `DEFAULT_TOML` per style guide (no `_` prefix on
    module-level exports).

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
