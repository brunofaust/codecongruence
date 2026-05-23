# `docstring_vs_body` — **D001**

**What it catches:** A function whose docstring no longer describes what the
body does — the classic AI-refactor failure mode where the implementation was
swapped but the docstring was forgotten.

**Severity:** error. This rule is the highest-value check in the suite.

**Default threshold:** `0.30` (cosine).

## How it works

1. Walk every staged `.py` file with `ast.parse`.
1. For each `FunctionDef`/`AsyncFunctionDef`:
    - Skip if the body has fewer than `min_body_statement_count` AST statements (default 3).
    - Skip if the docstring is shorter than `min_docstring_chars` characters (default 10).
    - Skip if decorated with `@overload` / `@typing.overload`.
    - Skip `__init__` of `@dataclass` classes.
    - Skip if the staged diff did not touch this function's line range.
1. Embed `docstring` vs `body_source` (body source is computed *without* the
    `def` signature line and *without* the docstring node itself — otherwise
    the docstring would trivially match itself).
1. Fail with the cosine similarity and a "update the docstring" message if the
    similarity is below the configured threshold.

## Configuration

```toml
[rules.docstring_vs_body]
enabled = true
threshold = 0.30
min_body_statement_count = 3   # skip trivial bodies (AST statement count)
min_docstring_chars = 10       # skip one-liners like "TODO"
include_comments = false       # strip # / // comments before embedding (default)
exclude = ["tests/**", "**/__init__.py"]
```

### `include_comments` (default `false`)

By default inline comments (`#` for Python, `//` for JS/TS) are stripped from
the body before embedding. A comment that repeats the docstring verbatim would
otherwise inflate similarity and hide real drift between the docstring and the
actual logic.

Set to `true` only if you want comments to count as part of the "what the code
does" signal — for example, when your codebase relies heavily on in-body
annotations that are genuinely authoritative.

## False-positive escape hatches

- Lower the threshold for a particular path with a custom config file.
- Add the path to `exclude`.
- Disable per-function by deleting the docstring (the rule only checks
    functions that have one).
