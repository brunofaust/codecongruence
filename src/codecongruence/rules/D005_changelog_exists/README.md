# `changelog_exists` — **D005**

**What it catches:** Code changed under `trigger_paths` (default `src/**`) but
nobody added a bullet under `## [Unreleased]` in `CHANGELOG.md`. This is the
**structural** companion to `claude_md_vs_diff`.

**No embeddings used.** Pure diff parse.

## How it works

1. If no staged file matches any `trigger_paths` glob → pass.
2. If `CHANGELOG.md` doesn't exist → fail with a "create it" message.
3. Otherwise inspect the unified diff of `CHANGELOG.md`. Walk it; track
   whether we're under the `## [Unreleased]` header on either the old or new
   side. Pass if at least one `+ - ` or `+ * ` bullet was added in that
   region.

## Configuration

```toml
[rules.changelog_exists]
enabled = true
changelog_path = "CHANGELOG.md"
unreleased_header = "## [Unreleased]"
trigger_paths = ["src/**"]
```

## Bypass

If a `src/` change is genuinely not changelog-worthy (typo fix, comment-only,
mechanical refactor), you have two options:

1. Add a `chore:` bullet to the section anyway — it's cheap.
2. Disable the rule for that commit via `git commit --no-verify`.

We deliberately do not auto-detect "trivial" changes; the rule's purpose is to
nudge the muscle memory of always writing a changelog entry.
