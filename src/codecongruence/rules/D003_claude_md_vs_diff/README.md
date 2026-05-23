# `claude_md_vs_diff` — **D003**

**What it catches:** A commit that changes a lot of code AND drops in an
unrelated one-line tweak to `CLAUDE.md` to satisfy a "docs must be updated"
policy. The doc edit pretends to be related; embeddings reveal it isn't.

**Default threshold:** `0.20` (cosine).

## How it works

1. Partition staged changes into "code" (matches any `code_paths` glob) and
    "docs" (file in `docs_files`).
1. If either bucket is empty, the rule does nothing (the companion
    `changelog_exists` rule handles "code changed but docs didn't").
1. Concatenate the unified diffs in each bucket.
1. Embed code-diff vs docs-diff.
1. Fail below threshold.

## Configuration

```toml
[rules.claude_md_vs_diff]
enabled = true
threshold = 0.20
code_paths = ["src/**"]
docs_files = ["CLAUDE.md"]
```

## Why the threshold is low

Diff payloads contain repetitive `git` metadata (`@@ -1,5 +1,5 @@`, file
headers, leading `+`/`-`) that suppresses cosine; 0.20 compensates. If you
wrote substantial CLAUDE.md prose this commit, you'll comfortably clear it.
