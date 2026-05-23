# `stale_comments` — **D002**

**What it catches:** Inline `#` comments that describe behavior the code below
them no longer has.

**Default threshold:** `0.20` (cosine).

## How it works

1. Walk staged `.py` files line-by-line.
1. For every `#` comment line, capture the next `context_lines` (default 5)
    non-blank, non-comment lines as the "following code".
1. Skip:
    - Shebangs (`#!`).
    - Pragmas: `# type: ignore`, `# noqa`, `# pylint:`, `# mypy:`, `# fmt:`,
        `# ruff:`, `# pragma:`, encoding declarations.
    - Markers: `# TODO`, `# FIXME`, `# NOTE`, `# HACK`, `# XXX` — these are
        intentionally divergent from the code.
    - Comments shorter than 4 words.
    - Comments not in the staged diff (we don't re-flag pre-existing comments
        on every commit).
1. Embed comment vs the following code window.
1. Fail below threshold.

## Configuration

```toml
[rules.stale_comments]
enabled = true
threshold = 0.20
context_lines = 5
```

## Future work

`v0.2` will extend this to JS/TS via tree-sitter, covering `//` and `/* */`.
