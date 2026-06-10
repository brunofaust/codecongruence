# Architecture

## Goals

1. **Catch semantic drift** — text artifacts (docstrings, comments, names,
    docs, changelogs) should keep telling the same story as the code.
1. **Be fast enough for a pre-commit hook** — sub-second on a typical staged
    diff with the default model loaded.
1. **Run offline** — no API calls, no API keys.
1. **Be extensible** — adding a rule is one file + a registration line.

## Layered view

```
┌───────────────────────────────────────────────────────────┐
│  CLI (typer)                              cli.py          │
│   ├─ codecongruence                                       │
│   └─ codecongruence init                                  │
└──────────────────────┬────────────────────────────────────┘
                       ▼
┌───────────────────────────────────────────────────────────┐
│  Runner (asyncio.TaskGroup)               core/runner.py  │
│   ├─ gather_changed → ChangedFile[]                       │
│   ├─ select_rules    → Rule[]                             │
│   └─ run() → RunResult                                    │
└──────────┬────────────────────────────────┬───────────────┘
           │                                │
           ▼                                ▼
┌─────────────────────────┐    ┌────────────────────────────┐
│ Embedder (single load,  │    │ Rules (9×)                 │
│ ONNX, content-cached)   │    │  name_vs_body        C001  │
│       core/embedder.py  │    │  param_name_vs_usage C002  │
└─────────────────────────┘    │  duplicate_functions C003  │
                               │  docstring_vs_body   D001  │
┌─────────────────────────┐    │  stale_comments      D002  │
│ Git helpers (async)     │    │  claude_md_vs_diff   D003  │
│       core/git.py       │    │  pr_description_…    D004  │
└─────────────────────────┘    │  docs_on_change      D005  │
                               │  params_in_docstring D006  │
                               │  rules/*.py                │
                               └────────────────────────────┘

┌─────────────────────────┐    ┌────────────────────────────┐
│ AST helpers             │    │ Reporters                  │
│   funcs / comments /    │    │  text (rich), json         │
│   identifier splits     │    │       reporters/*.py       │
│   core/ast_helpers.py   │    │                            │
└─────────────────────────┘    └────────────────────────────┘
```

## Key abstractions

### `Embedder` (`core/embedder.py`)

- One instance per CLI invocation, shared across rules.
- Backend protocol (`EmbeddingBackend`) so tests inject a deterministic
    bag-of-words fake instead of downloading 130 MB of ONNX weights.
- Per-run content-hash cache: identical text embedded once.
- `cosine(a, b)` zero-pads mismatched-shape vectors and clamps to `[-1, 1]`
    to absorb float32 round-off.
- `embed()` returns an `(n, d)` `float32` matrix even when some inputs are
    empty (those rows are zero-filled).

### `RuleRunner` (`core/runner.py`)

- `gather_changed()` resolves staged files + their added line ranges via
    `git diff --cached --unified=0`. Each `ChangedFile` knows which lines were
    added — rules intersect that with AST line ranges to skip un-touched code.
- `run()` calls `rule.check()` on every enabled rule, either in parallel
    (`asyncio.TaskGroup`, the default) or serially when `parallel = false`.
- All violations are sorted by `(file, line, rule_id)` for deterministic
    output.

### `Rule` (`rules/base.py`)

A small `Protocol`: `rule_id`, `description`, `default_threshold`, and one
`async def check(changed_files, embedder, config) -> Sequence[RuleViolation]`.

`RuleConfig` is a frozen Pydantic model with `extra="allow"` so per-rule
options like `min_body_statement_count`, `exclude`, `exclude_functions`,
`context_lines`, `code_paths`, `docs_files`, `trigger_paths`, `skip_variadic`,
etc. flow through without a per-rule schema explosion. See
[`codecongruence.toml.example`](codecongruence.toml.example) for the full
option reference.

### Config discovery

`load_config()` resolves a config source in this order:

1. Explicit `--config FILE` (or `-c FILE`) — auto-detects whether the file is
    `codecongruence.toml`-shaped (top-level `[codecongruence]` + `[rules.*]`)
    or `pyproject.toml`-shaped (`[tool.codecongruence]` +
    `[tool.codecongruence.rules.*]`).
1. `pyproject.toml` at the repo root with a `[tool.codecongruence]` section.
1. `codecongruence.toml` at the repo root.
1. Defaults.

`CodeCongruenceConfig.source` records which file produced the config (or
`None` when defaults were used) — handy for debugging "why is this threshold
not what I set?".

### AI context writer (`core/ai_context.py`)

`write_ai_context_files(repo_root, *, force)` is called by `codecongruence init`. It reads templates from the bundled `src/codecongruence/agents/` directory (via `importlib.resources`) and writes them to the user's repo:

- `.claude/skills/codecongruence/SKILL.md` — Claude Code skill (YAML frontmatter)
- `.cursor/rules/codecongruence.mdc` — Cursor MDC rule with glob triggers
- `AGENTS.md` — OpenAI Codex section (appended or created)

Files are never overwritten unless `force=True`. Returns
`list[tuple[Path, bool]]` — one per file, where the bool indicates whether
the file was actually written.

### Git layer (`core/git.py`)

All git calls go through `asyncio.subprocess`, never blocking. Functions
degrade gracefully when run outside a repo (return empty lists / strings) so
the CLI produces a clean "nothing to check" message instead of a stack
trace.

### AST layer (`core/ast_helpers.py`)

- `iter_functions(source, path)` — yields `FunctionInfo` per
    `FunctionDef` / `AsyncFunctionDef`, **stripping** the `def` signature line
    and the docstring node from `body_source` (critical for honest similarity
    scores).
- `iter_comments(source, context_lines)` — yields comment + the following
    non-comment, non-blank code window. Skips shebangs, pragmas (`# type: ignore`, `# noqa:`, ...), TODO markers, and comments shorter than four
    words.
- `split_identifier(name)` — splits camelCase/snake_case/PascalCase to
    whitespace tokens and expands a small abbreviation dictionary (`db → database`, `cfg → configuration`, `id → identifier`, ...).

## Diff awareness

Each rule receives `Sequence[ChangedFile]`. A `ChangedFile` carries
`added_ranges: tuple[tuple[int, int], ...]` plus the `repo_root` its
relative `path` resolves against (`abs_path`), so rules work regardless of
the process working directory. Rules intersect those ranges
with AST line ranges (for `docstring_vs_body`, `name_vs_body`,
`stale_comments`) or with file-level membership (for `claude_md_vs_diff`,
`changelog_exists`).

`--all` swaps `gather_changed()` for a full-repo walk and clears
`added_ranges` so every artifact is checked.

## Reporting

- **Text** (`reporters/text.py`) — `rich.Table` of violations + a one-line
    red summary. Quiet on success unless `--verbose`.
- **JSON** (`reporters/json.py`) — single document with `ok`,
    `rules_run`, `files_checked`, and `violations[]`. Stable schema for CI
    consumers.

Exit code is `0` if no `error`-severity violations, else `1`.

## Performance

- One model load per CLI invocation (`Embedder._ensure_backend()` is lazy).
- Content-hash cache prevents re-embedding identical inputs across rules.
- Parallel rule execution by default (`asyncio.TaskGroup`).
- AST parse results are cached in-memory and shared across rules within a run
    (no redundant re-parsing of the same file).

## Test strategy

- **Unit tests** use a `BagOfWordsBackend` so cosine similarity is exactly
    the (stop-word-filtered) token overlap. Tests assert relative behavior:
    divergent text < threshold, aligned text ≥ threshold.
- **Integration test** initialises a real git repo in `tmp_path`, plants a
    function with a misleading docstring + a `src/` change without a CHANGELOG
    bullet, runs the full `RuleRunner`, and asserts both `docstring_vs_body`
    and `docs_on_change` fire.
- A separate **`@pytest.mark.slow`** lane (not in the default suite) will
    eventually exercise the real ONNX model end-to-end.

## Extensibility

Adding a rule = one new module + one registration line. See `CLAUDE.md`.
Third-party rules can live outside the package as long as they implement
the `Rule` protocol and are registered through the (planned)
`codecongruence.plugins` entry-point group.
