# `duplicate_functions` — **C003**

**What it catches:** Two functions with different names whose bodies do the
same thing. Classic example: `fetch_user_by_id(uid)` and `load_user(user_id)`
in different modules both query the same table with the same logic.

**Default threshold:** `0.92` (cosine). High on purpose — function bodies
share a lot of structural vocabulary; a lower threshold produces too many
false positives on legitimate similar-but-distinct functions.

## How it works

1. Collect all functions from the files in scope (see `scope` config).
1. Strip nothing — the full body is embedded as-is (structural patterns matter
    here, unlike D001/C001 where comments inflate similarity).
1. Embed all bodies in a single batch call (one ONNX pass regardless of how
    many functions are in scope).
1. Compute pairwise cosine similarity in NumPy.
1. Flag any pair where `sim >= threshold` and the qualified names differ.

## Configuration

```toml
[rules.duplicate_functions]
enabled = true
threshold = 0.92
scope = "staged"               # "staged" (default) or "full"
min_body_statement_count = 3   # skip trivial one-liners
exclude = ["tests/**"]
```

### `scope`

| Value                | What is compared                                                                   |
| -------------------- | ---------------------------------------------------------------------------------- |
| `"staged"` (default) | Functions in staged/changed files only — fast, checks your current diff            |
| `"full"`             | Every tracked file in the repo — slow on large codebases, good as a periodic audit |

`full` mode embeds every function body in the repo. The Embedder's
content-hash disk cache means unchanged functions are not re-embedded on
subsequent runs.

### Performance note

Pairwise comparison is O(n²) in the number of functions. `full` mode on a
repo with 500 functions runs ~125,000 cosine comparisons (pure NumPy,
sub-second after embedding). The bottleneck is the initial batch embedding
on the first run; subsequent runs are fast due to caching.

## Notes

- `@overload`-decorated stubs and dataclass `__init__` methods are skipped.
- A pair is only flagged once — on the function that appears first by
    file path + line number.
- `self` / `cls` method bodies often share boilerplate; tune `threshold`
    upward (0.95+) if you see too many false positives on class methods.
