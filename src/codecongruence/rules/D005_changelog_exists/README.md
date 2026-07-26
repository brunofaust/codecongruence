# `docs_on_change` — **D005**

**What it catches:** Code changed under `trigger_paths` (default `src/**`) but
none of `docs_files` (e.g. `CHANGELOG.md`, `README.md`) were updated. This is
the **structural** companion to `claude_md_vs_diff`.

**Disabled by default.** Requiring a `docs_files` touch on every `src/`
change causes frequent merge conflicts on that file across parallel PRs, and
commit/PR history (see the Conventional Commits + `python-semantic-release`
workflow in `CLAUDE.md`) already serves as the changelog. Opt in if you still
want the structural nudge.

## How it works

1. If no staged file matches any `trigger_paths` glob → pass.
2. If none of `docs_files` have a staged diff → fail with a "document the
   change" message.
3. If `threshold > 0`, also require the combined `docs_files` diff to be
   semantically similar to the combined code diff (set `threshold = 0.0` to
   skip this and only enforce the structural check).

## Configuration

```toml
[rules.docs_on_change]
enabled = false   # opt-in
threshold = 0.20
trigger_paths = ["src/**"]
docs_files = ["CHANGELOG.md", "README.md"]
```

## Bypass

If you've opted in and hit a `src/` change that's genuinely not
docs-worthy (typo fix, comment-only, mechanical refactor), you have two
options:

1. Touch one of `docs_files` anyway (e.g. a `chore:` bullet) — it's cheap.
2. Disable the rule for that commit via `git commit --no-verify`.

We deliberately do not auto-detect "trivial" changes; the rule's purpose,
when enabled, is to nudge the muscle memory of documenting changes.
