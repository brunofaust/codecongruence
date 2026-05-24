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

# Check specific file
codecongruence src/mymodule.py
```

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

See `ARCHITECTURE.md` for implementation details.
