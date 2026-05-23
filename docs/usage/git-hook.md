# Native git hook (without pre-commit / prek)

If you don't want to introduce `pre-commit` / `prek` just for this, you can
wire codecongruence directly into `.git/hooks/pre-commit`.

## Recipe

```bash
# .git/hooks/pre-commit
#!/usr/bin/env bash
set -euo pipefail

# pick how you launch the package (any of these is fine)
if command -v uv >/dev/null 2>&1 && [ -f pyproject.toml ]; then
  uv run codecongruence --format text
elif [ -x .venv/bin/codecongruence ]; then
  .venv/bin/codecongruence --format text
else
  codecongruence --format text
fi
```

Make it executable:

```bash
chmod +x .git/hooks/pre-commit
```

## CI counterpart

In CI you usually want to scan against the PR's base ref rather than rely on
the index, so:

```bash
git fetch origin "$BASE_REF" --depth=1
git diff --name-only --diff-filter=ACMR "origin/$BASE_REF...HEAD" \
  | xargs -r git add --
uv run codecongruence --format json | tee codecongruence.json
```

This stages everything the PR changed, then runs the same diff-aware checks
your hooks run locally.

## Why pre-commit / prek is still nicer

- Manages the hook env for you (no need to keep `.venv/` in sync).
- Auto-updates the hook version via `pre-commit autoupdate`.
- Skips automatically on commits the user explicitly marks as bypassing hooks
    (`git commit --no-verify`).

Use the native-hook recipe only if your repo can't depend on either
framework.
