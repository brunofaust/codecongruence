# `name_vs_body` — **C001**

**What it catches:** A function whose name says one thing and whose body does
another. Classic example: `validate_email()` that quietly sends emails;
`get_user()` that deletes; `format_price()` that does network I/O.

**Default threshold:** `0.25` (cosine).

## How it works

1. Walk staged `.py` files via the AST.
1. Skip generic names (`main`, `run`, `setup`, `handle`, `process`, `execute`)
    and `test_*` functions — they're intentionally vague.
1. Skip `@overload` and dataclass-`__init__`.
1. Skip if the body has fewer than `min_body_statement_count` AST statements (default 2).
1. Skip if the staged diff did not touch the function.
1. Expand the function name via `split_identifier()` (snake/camel split + a
    small abbreviation dictionary: `db → database`, `cfg → configuration`,
    `id → identifier`, …).
1. Embed `expanded_name` vs `body_source` (without signature/docstring).
1. Fail below threshold.

## Configuration

```toml
[rules.name_vs_body]
enabled = true
threshold = 0.25
min_body_statement_count = 2   # skip trivial bodies (AST statement count)
ignore_names = ["main", "run", "setup", "handle"]
include_comments = false       # strip # / // comments before embedding (default)
```

### `include_comments` (default `false`)

By default, inline comments are stripped from the body before embedding.
A comment like `# send invoice email` next to unrelated code would otherwise
inflate name-vs-body similarity and hide the drift.

Set to `true` if you want comments to count as part of what the body does.

## Notes

Short names produce naturally lower cosine even when aligned; that's why the
default threshold is lower than for `docstring_vs_body`. Tune up only after
you've checked a few real violations.
