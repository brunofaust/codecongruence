# codecongruence

Semantic pre-commit hook framework. Detects drift between code and surrounding artifacts (docstrings, comments, function names, CLAUDE.md, PR descriptions, CHANGELOG) using local sentence embeddings via `fastembed`.

## Features

- **8 drift detection rules** — function names vs implementation, docstrings vs behavior, stale comments, missing docs, PR description alignment
- **Zero external dependencies** — ONNX-based `fastembed` (no PyTorch, no API calls)
- **Offline embeddings** — sentence embeddings run locally on your machine
- **Embedding cache** — persistent per-model cache with TTL-based garbage collection
- **Configurable thresholds** — tune similarity tolerances per rule
- **JSON output** — machine-readable violation reports

## Installation

```bash
pip install codecongruence
# or with uv
uv pip install codecongruence
```

## Quick Start

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
codecongruence init                     # write a default codecongruence.toml
codecongruence --purge-models           # delete ~/.cache/codecongruence and exit
codecongruence --version
```

## Incremental adoption

Adding `codecongruence` to an existing repo with hundreds of existing violations can
be overwhelming. The baseline feature lets you adopt it gradually — only fail on
*new* violations that appear after the baseline was saved.

```bash
# 1. Run once to capture every existing violation.
codecongruence --update-baseline        # saves .codecongruence-baseline.json

# 2. Commit the baseline alongside your code.
git add .codecongruence-baseline.json
git commit -m "chore: add codecongruence baseline"

# 3. From now on, every run silently ignores baseline violations.
#    Only violations that weren't in the baseline will fail.
codecongruence

# 4. When you've fixed a batch of violations, refresh the baseline.
codecongruence --update-baseline
git add .codecongruence-baseline.json
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
2. **Compaction** — `compact()` called after `--all` removes embeddings for texts no longer in the repo

To disable TTL, set `cache_ttl_days = 0`.

## Rules

| Code | Rule | Detects |
|------|------|---------|
| C001 | name_vs_body | Function name doesn't match implementation |
| C002 | param_name_vs_usage | Parameter names not used in docstring |
| D001 | docstring_vs_body | Docstring doesn't describe actual behavior |
| D002 | stale_comments | Comments contradict code |
| D003 | claude_md_vs_diff | CLAUDE.md out of sync with code changes |
| D004 | pr_description_vs_diff | PR description misaligned with diff |
| D005 | docs_on_change | Code changed but docs weren't updated |
| D006 | params_in_docstring | Function params missing from docstring |

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
                 .codecongruence-baseline.json  (committed to git)
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
