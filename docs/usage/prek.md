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
rev = "v0.10.0"
hooks = [{ id = "codecongruence" }]
```

Or the wire-compatible `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/brunofaust/codecongruence
    rev: v0.10.0
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

## Use MLX in a prek hook (Apple Silicon)

prek builds the hook environment from the codecongruence repo, so the `mlx`
extra cannot be requested with `pip install 'codecongruence[mlx]'` — request
the packages through `additional_dependencies`. PEP 508 markers are honoured, so
the same config is a no-op on Linux CI (which stays on ONNX):

```toml
[[repos]]
repo = "https://github.com/brunofaust/codecongruence"
rev = "v0.10.0"
hooks = [
  { id = "codecongruence", additional_dependencies = [
    "mlx>=0.32.3; sys_platform == 'darwin' and platform_machine == 'arm64'",
    "mlx-embeddings>=0.1.0; sys_platform == 'darwin' and platform_machine == 'arm64'",
  ] },
]
```

The hook prints `codecongruence: embedding backend: mlx` (or `onnx (auto: …)` with the
reason) on stderr; run `prek run codecongruence --all-files -v` to see it on a
passing run. Because MLX and ONNX differ by ~1e-4 cosine, pin `backend = "onnx"`
in `codecongruence.toml` if findings must be identical on every machine.

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
