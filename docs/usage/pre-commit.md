# Using codecongruence with [pre-commit](https://pre-commit.com)

`codecongruence` ships a hook definition at `.pre-commit-hooks.yaml`, so the
standard `pre-commit` workflow Just Works.

## 1. Add the repo to your `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/brunofaust/codecongruence
    rev: v0.11.0          # or any released tag
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
# codecongruence runs automatically on the staged files
```

## How it integrates

The published hook is defined like this:

```yaml
- id: codecongruence
  name: codecongruence
  description: Semantic pre-commit checks (docstring/name/CLAUDE.md/PR/comment drift).
  entry: codecongruence
  language: python
  pass_filenames: true        # the runner decides which files to check
  stages: [pre-commit]
  require_serial: true        # only one model load per invocation
```

Key choices:

- `pass_filenames: true`. The runner passes the files for the current stage:
    the staged files on commit, the pushed files on `pre-push`, and every
    tracked file under `run --all-files` (CI). codecongruence checks exactly
    those files, whole-file. With `pass_filenames: false` nothing is staged on
    `pre-push` or in CI, so the hook would check nothing. Because the scope is
    whole-file, a commit that touches a file surfaces drift already present in
    it. Baseline it once with `codecongruence --update-baseline --all`.
- `require_serial: true` keeps the runner from splitting the file list across
    parallel processes, each of which would load the embedding model. A very
    long list can still be chunked into several serial invocations by the
    command-line length limit, so an explicit-file run is never treated as a
    full scan. `duplicate_functions` baseline entries are judged only on
    `--all`, and the embedding cache is compacted only on `--all`.
- Baseline staleness is scoped to the files each invocation checked. An entry
    for a file outside the list is never reported stale or pruned.

## Use MLX in a pre-commit hook (Apple Silicon)

The hook environment is built from the codecongruence repo, so request the MLX
packages through `additional_dependencies` (PEP 508 markers keep Linux CI on
ONNX):

```yaml
repos:
  - repo: https://github.com/brunofaust/codecongruence
    rev: v0.11.0
    hooks:
      - id: codecongruence
        additional_dependencies:
          - "mlx>=0.32.3; sys_platform == 'darwin' and platform_machine == 'arm64'"
          - "mlx-embeddings>=0.1.0; sys_platform == 'darwin' and platform_machine == 'arm64'"
```

The resolved backend is printed on stderr. MLX and ONNX differ by ~1e-4 cosine;
pin `backend = "onnx"` for byte-identical results across machines.

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
