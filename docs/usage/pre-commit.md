# Using codecongruence with [pre-commit](https://pre-commit.com)

`codecongruence` ships a hook definition at `.pre-commit-hooks.yaml`, so the
standard `pre-commit` workflow Just Works.

## 1. Add the repo to your `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/brunofaust/codecongruence
    rev: v0.8.0          # or any released tag
    hooks:
      - id: codecongruence
```

## 2. Install the git hook

```bash
pre-commit install
```

## 3. Try a commit

```bash
git add path/to/file.py
git commit -m "..."
# codecongruence runs automatically on the staged diff
```

## How it integrates

The published hook is defined like this:

```yaml
- id: codecongruence
  name: codecongruence
  description: Semantic pre-commit checks (docstring/name/CLAUDE.md/PR/comment drift).
  entry: codecongruence
  language: python
  pass_filenames: false       # codecongruence inspects the staged diff itself
  stages: [pre-commit]
  require_serial: true        # only one model load per commit
```

Key choices:

- `pass_filenames: false` — `pre-commit` would otherwise call us once per
    changed file; we already use `git diff --cached` internally and want
    whole-diff awareness for `claude_md_vs_diff` / `changelog_exists`.
- `require_serial: true` — the embedding model loads once per process; running
    in parallel would multiply that cost.

## Pinning + auto-update

`pre-commit` caches the hook environment keyed by `rev`, so mutable refs
(`latest`, `main`) are unsupported — they freeze on the first-installed
commit. Pin a release tag and refresh it with:

```bash
pre-commit autoupdate           # bumps the rev to the latest tag
```

To stay current without manual runs, enable [pre-commit.ci](https://pre-commit.ci)
(weekly autoupdate PRs) or let Renovate manage the rev.

## CI

Most CI providers can run pre-commit on a PR:

```yaml
# .github/workflows/pre-commit.yml
on: [pull_request]
jobs:
  pre-commit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - uses: pre-commit/action@v3.0.1
```
