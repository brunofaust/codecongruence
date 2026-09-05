# Using codecongruence with [prek](https://prek.dev)

`prek` is a hook runner that reads the same `.pre-commit-hooks.yaml` format as
`pre-commit` but also supports a single TOML config — `prek.toml` — which is
the preferred idiom for new projects (no per-hook YAML noise).

> The codecongruence repo itself uses `prek` with a single TOML config —
> [`prek.toml`](../../prek.toml) at the repo root.

## 1. Install prek

```bash
uv tool install prek
```

## 2. Add codecongruence to your config

`prek.toml` (the prek-native idiom):

```toml
[[repos]]
repo = "https://github.com/brunofaust/codecongruence"
rev = "v0.8.1"
hooks = [{ id = "codecongruence" }]
```

Or the wire-compatible `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/brunofaust/codecongruence
    rev: v0.8.1
    hooks:
      - id: codecongruence
```

> **Why pin a tag instead of `latest`?** prek (like pre-commit) caches the
> hook environment keyed by `rev`. A mutable ref such as a moving `latest`
> tag or `main` is cloned once and never refreshed — it silently freezes on
> the first-installed commit. Pin a release tag and keep it current with:
>
> ```bash
> prek auto-update    # bumps rev to the latest released tag
> ```

## 3. Install the git hook

```bash
prek install
```

## What's different vs pre-commit?

- `prek` is **much** faster on cold runs because it avoids `pip` and creates
    hook envs via `uv` or its own resolver. The codecongruence hook is a normal
    Python entry-point so it inherits that speedup transparently.
- `prek` is wire-compatible with `pre-commit` configs, so a team can mix
    members using `pre-commit` and `prek` on the same repo.

## Self setup (this repo)

The repo ships a `prek.toml` with the full lint chain (ruff, mypy, pytest,
bandit, gitleaks, typos, vulture, interrogate, markdownlint, mdformat,
pyupgrade, pre-commit-hooks, pygrep-hooks, uv-lock, codecongruence on
itself). Install once:

```bash
prek install
```

Run on demand:

```bash
prek run                       # only on staged files
prek run --all-files           # entire repo
prek run codecongruence        # one hook
prek run --hook-stage push     # the heavier "push"-staged hooks (mypy, pytest)
```

## CI

```yaml
- name: prek
  run: |
    curl -L https://github.com/j178/prek/releases/latest/download/prek-installer.sh | sh
    prek run --all-files
```
