# `pr_description_vs_diff` — **D004**

**What it catches:** A lazy "fix bug" / "update" PR description sitting on top
of 500 changed lines.

**Default threshold:** `0.25` (cosine). Disabled by default — opt-in for CI.

## How it works

1. Reads the PR description from environment variable `CODECONGRUENCE_PR_BODY`
    (set by your CI from `${{ github.event.pull_request.body }}` or equivalent).
1. If absent, the rule short-circuits — this rule is **CI-only**.
1. Captures the full staged diff (`git diff --cached --unified=3`).
1. Embeds the PR body vs the diff.
1. Fails below threshold with a "expand the description" message.

## Configuration

```toml
[rules.pr_description_vs_diff]
enabled = false   # opt-in
threshold = 0.25
```

## CI wiring

GitHub Actions example:

```yaml
- name: codecongruence
  env:
    CODECONGRUENCE_PR_BODY: ${{ github.event.pull_request.body }}
  run: uv run codecongruence --rule pr_description_vs_diff
```
