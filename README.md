# codecongruence

Semantic pre-commit hook framework. Detects drift between code and surrounding artifacts (docstrings, comments, function names, CLAUDE.md, PR descriptions, CHANGELOG) using local sentence embeddings via `fastembed`.

## Features

- **9 drift detection rules** — function names vs implementation, duplicate logic, docstrings vs behavior, stale comments, missing docs, PR description alignment
- **Zero external dependencies** — ONNX-based `fastembed` (no PyTorch, no API calls)
- **Offline embeddings** — sentence embeddings run locally on your machine
- **Embedding cache** — persistent per-model cache with TTL-based garbage collection
- **Configurable thresholds** — tune similarity tolerances per rule
- **JSON output** — machine-readable violation reports

## Installation

Not on PyPI yet — install straight from GitHub with [uv](https://docs.astral.sh/uv/):

```bash
# Latest release (tracks main, where releases land)
uv tool install git+https://github.com/brunofaust/codecongruence.git

# Or pin to a specific release tag for reproducibility
uv tool install "git+https://github.com/brunofaust/codecongruence.git@vX.Y.Z"
```

This puts the `codecongruence` command on your `PATH`. Upgrade later with
`uv tool upgrade codecongruence`. Browse [releases](https://github.com/brunofaust/codecongruence/releases)
for the tag to pin.

> **Default mode checks only staged files.** If nothing is staged (`git add`),
> the tool prints a warning and exits cleanly — it does not scan the whole repo.
> Use `--all` for ad-hoc whole-repo scans.

## AI context files

`codecongruence init` installs AI-tool context files from the bundled `agents/`
directory so your AI assistant understands every rule and fix strategy without
needing to read the docs separately:

| Installed to                             | Tool                                                     |
| ---------------------------------------- | -------------------------------------------------------- |
| `.claude/skills/codecongruence/SKILL.md` | Claude Code (Anthropic) — loaded as a skill              |
| `.cursor/rules/codecongruence.mdc`       | Cursor — applied when editing `.py` or `.md` files       |
| `AGENTS.md`                              | OpenAI Codex — section appended (file created if absent) |

Files are skipped if they already exist. Pass `--force` to overwrite.
Commit them to git so every contributor's AI assistant has the context.

The template sources live in [`src/codecongruence/agents/`](src/codecongruence/agents/) — browse them to see exactly what gets installed.
Agent template files use YAML frontmatter (`---` delimiters) for metadata and are protected from markdown formatters to preserve their structure.

## Rules

Each rule has a stable short **code** (`C00x` = code-identifier drift,
`D00x` = documentation / artifact drift) shown in reports and easy to grep.

| Code     | Rule                     | What it catches                                                              | Default threshold |
| -------- | ------------------------ | ---------------------------------------------------------------------------- | ----------------- |
| **C001** | `name_vs_body`           | `get_user()` that deletes, `validate_email()` that sends email               | 0.25              |
| **C002** | `param_name_vs_usage`    | Parameter name clashes with how the parameter is used in the body            | 0.20              |
| **C003** | `duplicate_functions`    | Two functions with similar names and near-identical bodies                   | 0.92              |
| **D001** | `docstring_vs_body`      | Docstring describes one thing, function body does another                    | 0.30              |
| **D002** | `stale_comments`         | Comment describes behavior the code no longer has                            | 0.20              |
| **D003** | `claude_md_vs_diff`      | Unrelated one-line CLAUDE.md tweak buried under a 10k-LOC code change        | 0.20              |
| **D004** | `pr_description_vs_diff` | Lazy "fix bug" PR description on a 500-line change (CI-only)                 | 0.25              |
| **D005** | `docs_on_change`         | `src/` changed but none of your docs files (CHANGELOG, README…) were updated | 0.20              |
| **D006** | `params_in_docstring`    | Function has a docstring but a parameter isn't mentioned in it               | structural        |

All rules are **diff-aware** by default — they only check things that touch the
current staged diff (`git add` first). Pass `--all` to scan the whole repo
without staging anything. If nothing is staged and `--all` is not given, the
tool exits with a warning rather than silently succeeding.

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
# Check all changed files (vs main)
codecongruence

# Full repo audit
codecongruence --all

# --- output ---
codecongruence --format json            # machine-readable, for CI
codecongruence --verbose                # show violation table and OK line on success

# --- baseline ---
codecongruence --update-baseline        # save all current violations as the new baseline

# --- setup ---
codecongruence init                     # write codecongruence.toml + AI context files
codecongruence --purge-models           # delete ~/.cache/codecongruence and exit
codecongruence --version
```

## Incremental adoption

Adding `codecongruence` to an existing repo with hundreds of existing violations can
be overwhelming. The baseline feature lets you adopt it gradually — only fail on
*new* violations that appear after the baseline was saved.

```bash
# 1. Run once to capture every existing violation.
codecongruence --update-baseline        # saves .codecongruence/.codecongruence-baseline.json

# 2. Commit the baseline alongside your code.
git add .codecongruence/.codecongruence-baseline.json
git commit -m "chore: add codecongruence baseline"

# 3. From now on, every run silently ignores baseline violations.
#    Only violations that weren't in the baseline will fail.
codecongruence

# 4. When you've fixed a batch of violations, refresh the baseline.
codecongruence --update-baseline
git add .codecongruence/.codecongruence-baseline.json
git commit -m "chore: shrink codecongruence baseline"
```

The baseline file stores violations by `(rule_id, file_path, line)`. Moving a
function to a different line makes the entry stale — it falls off automatically
on the next `--update-baseline`.

## Configuration

Create `codecongruence.toml` at your repo root:

```toml
model = "BAAI/bge-small-en-v1.5"
cache_ttl_days = 30

[rules.docstring_vs_body]
threshold = 0.65

[rules.name_vs_body]
threshold = 0.70
```

## Cache Garbage Collection

Embeddings are cached in `.codecongruence/embeddings.npz` (model-specific, content-hash keyed).

Two GC mechanisms:

1. **TTL eviction** — entries not accessed within `cache_ttl_days` (default: 30) are discarded on load
1. **Compaction** — `save(force_cleanup=True)` after `--all` removes embeddings for texts no longer in the repo

To disable TTL, set `cache_ttl_days = 0`.

### Git worktrees

The cache is keyed purely by content hash, so an embedding computed in one
checkout is valid in every other checkout of the same repo. codecongruence uses
that to avoid cold-starting linked [git worktrees](https://git-scm.com/docs/git-worktree):

- The **primary worktree's** `.codecongruence/embeddings.npz` is layered
    underneath as a read-only **base**. A linked worktree reuses those warm
    embeddings and only pays to embed the text its own branch changed.
- Each worktree's `save()` writes **only its local delta** to its own
    `.codecongruence/` — base entries are never duplicated or rewritten, and a
    worktree never mutates the primary's cache.
- Writes are atomic (temp file + `os.replace`), so a worktree reading the base
    can never observe a half-written file.

The downloaded ONNX model (`~/.cache/codecongruence`) is global and shared by
every repo and worktree — it is never re-downloaded per worktree.

## Rules

| Code | Rule                   | Detects                                                    |
| ---- | ---------------------- | ---------------------------------------------------------- |
| C001 | name_vs_body           | Function name doesn't match implementation                 |
| C002 | param_name_vs_usage    | Parameter names not used in docstring                      |
| C003 | duplicate_functions    | Two functions with similar names and near-identical bodies |
| D001 | docstring_vs_body      | Docstring doesn't describe actual behavior                 |
| D002 | stale_comments         | Comments contradict code                                   |
| D003 | claude_md_vs_diff      | CLAUDE.md out of sync with code changes                    |
| D004 | pr_description_vs_diff | PR description misaligned with diff                        |
| D005 | docs_on_change         | Code changed but docs weren't updated                      |
| D006 | params_in_docstring    | Function params missing from docstring                     |

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
   RunResult ──► apply_baseline (optional) ──► TextReporter / JsonReporter
                        │
                 .codecongruence/.codecongruence-baseline.json  (committed to git)
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for details.

## Contributing

```bash
git clone https://github.com/brunofaust/codecongruence
cd codecongruence
uv sync
uv run pytest
uv run prek run --all-files
```

PRs welcome. Please make sure `codecongruence` passes on its own diff before
opening — we eat our own dogfood.

## License

[MIT](LICENSE). © 2026 Bruno Faust.
