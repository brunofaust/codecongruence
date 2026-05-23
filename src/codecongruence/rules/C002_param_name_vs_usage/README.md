# `param_name_vs_usage` — **C002**

**What it catches:** A parameter whose name implies one thing but whose usage
in the function body does something else. Classic example:
`save_document(user_data)` that reads and manipulates billing records, not
user data.

**Default threshold:** `0.20` (cosine).

## How it works

For each parameter in a changed function:

1. Skip single-letter and very short names (controlled by
    `min_param_name_chars`, default 2 characters).
1. Find every line in the body that references the parameter (by whole-word
    match).
1. Strip the parameter name from those lines — this gives the *usage context*:
    what the surrounding code does *around* the parameter, without the name
    itself biasing the embedding.
1. Expand the parameter name via `split_identifier()` (snake/camel split +
    abbreviation dictionary: `db → database`, `cfg → configuration`, …).
1. Embed `expanded_name` vs `usage_context`.
1. Fail below threshold.

### Why strip the name from the usage context?

If the name were left in, the embedder would always find "repo_root" in both
the left side ("repo root") and the right side (the usage lines), giving an
artificially high similarity regardless of what the body actually does.
Stripping forces the comparison to be: *what the name suggests* vs *what the
surrounding code does*.

### Fragment-collision caveat

Stripping is done on the full identifier. If a local variable shares a token
with the parameter name — e.g. parameter `repo_root` stripped from
`root = (repo_root or Path.cwd()).resolve()` leaves `root = (...)` — the
word "root" is still present in the usage context and inflates the similarity.
If you see a surprisingly high score, check the `left=` / `right=` values in
`--debug` output to confirm.

## Configuration

```toml
[rules.param_name_vs_usage]
enabled = true
threshold = 0.20
min_body_statement_count = 2   # skip trivial bodies (AST statement count)
min_param_name_chars = 2       # skip single-letter params like i, n, x
include_comments = true        # include # / // comments in usage context (default)
```

### `include_comments` (default `true`)

By default, comment lines that reference a parameter are included in the usage
context. A comment like `# validate user_id before processing` is a real signal
about what the parameter represents and should count toward the embedding.

Set to `false` to restrict the check to executable lines only — useful if your
codebase has many auto-generated or stale comments that you don't want
influencing the score.

## Notes

- Unused parameters are silently skipped — that is a linter's job, not ours.
- `*args` and `**kwargs` are stripped of their leading `*` before the check.
- `self` and `cls` are effectively skipped via `min_param_name_chars` (they
    ARE 4 chars — but `self` rarely appears in body lines as a bare name without
    attribute access, so the usage context is usually empty and skipped).
