# Using codecongruence with [prek](https://github.com/j178/prek)

`prek` is a fast Rust re-implementation of `pre-commit`'s runner. It reads the
exact same `.pre-commit-config.yaml` + `.pre-commit-hooks.yaml`, so the setup
is identical to the [pre-commit guide](pre-commit.md).

> The codecongruence repo itself uses `prek` with a single TOML config —
> [`prek.toml`](../../prek.toml) at the repo root. That file is the modern
> idiom (one TOML for everything, no per-hook YAML noise) and is preferred
> over the legacy `.pre-commit-config.yaml` for new projects.

## 1. Install prek

```bash
brew install j178/tap/prek      # macOS
# or
cargo install prek              # any platform with Rust
```

## 2. Add codecongruence to `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/brunofaust/codecongruence
    rev: v0.1.0
    hooks:
      - id: codecongruence
```

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
