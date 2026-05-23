# TODO

## v0.1 (MVP) — DONE

- [x] Scaffold + pyproject + uv
- [x] Embedder with fastembed + content-hash cache
- [x] Config loader (TOML → Pydantic)
- [x] Git diff + line-range helpers (async)
- [x] AST helpers (functions, comments, identifier split)
- [x] Six rules
- [x] Typer CLI + text/JSON reporters
- [x] Unit + integration tests (offline, fake backend)
- [x] Lint + typecheck clean (ruff, mypy --strict)
- [x] Pre-commit hook config
- [x] CI workflow

## v0.2

- [x] JS / TS support for `name_vs_body`, `stale_comments`, `docstring_vs_body`
      (tree-sitter-javascript + tree-sitter-typescript; JSDoc as docstring).
- [x] AST cache shared across rules to avoid double-parsing (in-memory, per-run).
- [x] Persist embeddings across runs (always-on JSON cache in `cache_dir`).
- [ ] `--baseline` mode: write current scores to a JSON file, fail only on
      regressions.
- [x] `pyproject.toml` `[tool.codecongruence]` section as an alternative to
      `codecongruence.toml`.
- [ ] Entry-point group `codecongruence.plugins` for third-party rules.
- [x] `--quiet` flag and a `pre-commit`-friendly summary-only output.

## v0.3

- [ ] Larger embedding model option (`bge-base-en-v1.5`, ~440MB) gated behind
      explicit opt-in.
- [ ] GitHub Action published to the marketplace.
- [ ] Per-language adapters: Markdown sections vs subsequent code blocks;
      OpenAPI `summary` vs implementation handler.
- [ ] Optional LLM-judge rule (`llm_judge`) using a local llama.cpp model for
      teams that want a second opinion on edge cases.

## Research / future

- [ ] Evaluate `SIDE` and `CoCC`-style threshold tuning against a labelled
      benchmark dataset.
- [ ] Cross-file consistency (e.g. interface vs implementation) — needs a
      whole-program index, probably tree-sitter + symbol resolution.
- [ ] PR-comment bot that posts the violations inline on GitHub PRs.
