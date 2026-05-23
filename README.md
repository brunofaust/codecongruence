# codecongruence

**Keep your repo congruent. One story, not many. Catch contradictions before your AI gets confused.**

`codecongruence` is an open-source Python pre-commit hook framework that uses
local sentence embeddings to detect **semantic drift** between code and its
surrounding artifacts: docstrings, comments, function names, CLAUDE.md, PR
descriptions, and CHANGELOG entries.

It runs entirely offline (no API calls), uses an ONNX-based embedding model
(no PyTorch), and ships as a regular `pip install` package.

**Requirements:** Python ≥ 3.11.

> Why? AI-assisted refactors change code bodies without updating the surrounding
> text. Existing linters (ruff, mypy, eslint) catch *syntax* and *types* — they
> don't notice when `validate_email()` quietly starts sending emails. That's the
> gap codecongruence fills.

## Quick start

```bash
# 1. install
pip install codecongruence

# 2. drop a default config into your repo
codecongruence init

# 3a. ad-hoc check on staged changes
git add .
codecongruence

# 3b. or wire it into pre-commit
# add to .pre-commit-config.yaml:
#   - repo: https://github.com/brunofaust/codecongruence
#     rev: v0.1.0
#     hooks:
#       - id: codecongruence
pre-commit install
```

## The six MVP rules

Each rule has a stable short **code** (`C00x` = code-identifier drift,
`D00x` = documentation / artifact drift) shown in reports and easy to grep.

| Code     | Rule                     | What it catches                                                       | Default threshold |
| -------- | ------------------------ | --------------------------------------------------------------------- | ----------------- |
| **C001** | `name_vs_body`           | `get_user()` that deletes, `validate_email()` that sends email        | 0.25              |
| **D001** | `docstring_vs_body`      | Docstring describes one thing, function body does another             | 0.30              |
| **D002** | `stale_comments`         | Comment describes behavior the code no longer has                     | 0.20              |
| **D003** | `claude_md_vs_diff`      | Unrelated one-line CLAUDE.md tweak buried under a 10k-LOC code change | 0.20              |
| **D004** | `pr_description_vs_diff` | Lazy "fix bug" PR description on a 500-line change (CI-only)          | 0.25              |
| **D005** | `changelog_exists`       | `src/` changed but `## [Unreleased]` got no new bullet                | structural        |

All rules are **diff-aware** by default — they only check things that touch the
current staged diff. Pass `--all` to scan the whole repo.

## Documentation

- [CLI reference](docs/usage/cli.md) — every flag + JSON schema.
- [Use with pre-commit](docs/usage/pre-commit.md)
- [Use with prek](docs/usage/prek.md)
- [Native git hook recipe](docs/usage/git-hook.md)
- [Linter chain (ruff/mypy/eslint/codecongruence)](docs/usage/linters.md)
- [Per-rule docs](docs/rules/)
- [Research foundation](docs/research.md)
- [Architecture](ARCHITECTURE.md)

## CLI

```bash
codecongruence                          # run all enabled rules on staged changes
codecongruence --rule docstring_vs_body
codecongruence --config custom.toml     # any TOML — codecongruence.toml or pyproject.toml
codecongruence -c pyproject.toml        # explicit pyproject.toml
codecongruence --all                    # full-repo scan
codecongruence --format json            # machine-readable, for CI
codecongruence --verbose                # show similarities even on success
codecongruence init                     # write a default codecongruence.toml
codecongruence --version
```

## Configuration

Two layouts are supported. Pick whichever fits your project — uv, Poetry,
Hatch and PDM all expose `pyproject.toml`, so most modern Python repos will
prefer that.

### Option A — `pyproject.toml` (modern, uv/Poetry-friendly)

```toml
[tool.codecongruence]
model = "BAAI/bge-small-en-v1.5"
parallel = true

[tool.codecongruence.rules.docstring_vs_body]
enabled = true
threshold = 0.30
body_statements_threshold = 3
min_docstring_chars = 10
exclude = ["tests/**", "**/__init__.py"]

[tool.codecongruence.rules.name_vs_body]
enabled = true
threshold = 0.25
ignore_names = ["main", "run", "setup", "handle"]

[tool.codecongruence.rules.claude_md_vs_diff]
enabled = true
threshold = 0.20
code_paths = ["src/**"]
docs_files = ["CLAUDE.md"]

[tool.codecongruence.rules.pr_description_vs_diff]
enabled = false                      # opt-in, CI-only
threshold = 0.25

[tool.codecongruence.rules.stale_comments]
enabled = true
threshold = 0.20
context_lines = 5

[tool.codecongruence.rules.changelog_exists]
enabled = true
changelog_path = "CHANGELOG.md"
unreleased_header = "## [Unreleased]"
trigger_paths = ["src/**"]
```

### Option B — `codecongruence.toml` (stand-alone)

```toml
[codecongruence]
model = "BAAI/bge-small-en-v1.5"
parallel = true

[rules.docstring_vs_body]
enabled = true
threshold = 0.30
exclude = ["tests/**", "**/__init__.py"]

# ... etc; same options, just one nesting level shallower
```

### Resolution order (highest priority wins)

1. `--config FILE` / `-c FILE` — explicit path. The file's layout
    (`codecongruence.toml` vs `pyproject.toml`) is auto-detected.
1. `pyproject.toml` at the repo root, *if* it contains a
    `[tool.codecongruence]` section.
1. `codecongruence.toml` at the repo root.
1. Built-in defaults.

## Supported embedding models

ONNX models via `fastembed` — no PyTorch needed, no network at runtime after the
first download.

| Model                                     | Size    | MTEB | Notes                       |
| ----------------------------------------- | ------- | ---- | --------------------------- |
| `BAAI/bge-small-en-v1.5` (default)        | ~130 MB | 62.2 | Best quality/size trade-off |
| `sentence-transformers/all-MiniLM-L6-v2`  | ~90 MB  | 56.1 | Lightest                    |
| `sentence-transformers/all-MiniLM-L12-v2` | ~120 MB | 58.7 | Mid                         |

## Academic foundation

The problem of semantic drift between code and comments/docs/names is
well-documented in the software-engineering literature:

- **CoCC** (Liu et al., 2024, [arXiv 2403.00251](https://arxiv.org/abs/2403.00251)) — detected outdated comments in 22 Java projects with >90% precision; extended to Python with similar results.
- **Co3D** (EASE 2024, [arXiv 2405.16272](https://arxiv.org/abs/2405.16272)) — word2vec + LSTM beat heavier pre-trained baselines for code–comment coherence.
- **SIDE metric** ([arXiv 2502.07611](https://arxiv.org/abs/2502.07611)) — code-summary coherence used to optimize training datasets.
- **LLM-based eval** ([arXiv 2507.05289](https://arxiv.org/abs/2507.05289)) — confirmed LLMs can evaluate "coherence between identifier names, comments, and documentation with code purpose."

See [`docs/research.md`](docs/research.md) for citations + how each rule maps to the literature.

## How it compares

| Tool                     | What it does                                        | Embeddings       | Needs API key | Pre-commit hook |
| ------------------------ | --------------------------------------------------- | ---------------- | ------------- | --------------- |
| **codecongruence**       | Semantic drift between code and docs/comments/names | **Local (ONNX)** | No            | Yes             |
| `rejot-dev/semcheck`     | LLM-based semantic linting                          | Cloud LLM        | Yes           | Manual          |
| `vulture`                | Dead-code detection                                 | None             | No            | Yes             |
| `interrogate`            | Docstring presence/coverage                         | None             | No            | Yes             |
| `ruff`, `mypy`, `eslint` | Syntax, types, style                                | None             | No            | Yes             |

## Architecture in one diagram

```
codecongruence (CLI)
        │
        ▼
   load_config (codecongruence.toml)
        │
        ▼
   Embedder (fastembed/ONNX, single load, content-hash cached)
        │
        ▼
   RuleRunner.run() ─── asyncio.TaskGroup ───► [Rule.check(...) × N]
        │                                              │
        │                          ChangedFile list ◄──┤  (diff-aware)
        ▼                                              ▼
   RunResult ──► TextReporter / JsonReporter
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for details.

## Contributing

```bash
git clone https://github.com/brunofaust/codecongruence
cd codecongruence
uv sync --extra dev
uv run pytest
uv run ruff check src tests
uv run mypy
```

PRs welcome. Please make sure `codecongruence` passes on its own diff before
opening — we eat our own dogfood.

## License

[MIT](LICENSE). © 2026 Bruno Faust.
