## Summary

<!-- one paragraph: what this change does AND why. Keep it tight, but enough that
     `codecongruence --rule pr_description_vs_diff` is happy on a real diff. -->

## Changes

- [ ] Code change described in `## [Unreleased]` of `CHANGELOG.md`
- [ ] Docs updated where relevant (`README.md`, `ARCHITECTURE.md`, `CLAUDE.md`, `docs/`)
- [ ] Tests added / updated
- [ ] `uv run codecongruence --all` passes locally

## Test plan

- [ ] `uv run pytest`
- [ ] `uv run ruff check src tests && uv run ruff format --check src tests`
- [ ] `uv run mypy`
