# How codecongruence fits among other linters

codecongruence does **not** replace syntax / type / style linters. It plugs a
different hole — *semantic* drift — so it belongs alongside them in your
pre-commit chain.

## Suggested chain (Python project)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff             # syntax, lint
      - id: ruff-format      # formatting

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy             # types

  - repo: https://github.com/brunofaust/codecongruence
    rev: v0.1.0
    hooks:
      - id: codecongruence   # semantic
```

Run order in the chain matters less than coverage; `pre-commit` will run all
hooks and report failures from each.

## What each tool catches

| Tool                   | What it catches                                                                                 | What it does **not** catch                             |
| ---------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| **ruff**               | Syntax errors, unused imports, simplifications, style, isort, bug-prone patterns (B-rules)      | Whether the function does what its name/docstring says |
| **ruff-format**        | Whitespace, line length, quote style                                                            | Anything semantic                                      |
| **mypy**               | Type errors, missing type hints, signature mismatches                                           | Whether a typed function is honest about its purpose   |
| **pyright/pylance**    | Same as mypy, plus more inference                                                               | Same gap                                               |
| **eslint** / **biome** | JS/TS syntax + style + a few semantic anti-patterns                                             | Same gap, for JS/TS                                    |
| **vulture**            | Dead code                                                                                       | Drift in live code                                     |
| **interrogate**        | Docstring **presence** (coverage)                                                               | Whether the docstring is *true*                        |
| **bandit**             | Security anti-patterns                                                                          | Semantic drift                                         |
| **prettier**           | Formatting                                                                                      | Anything semantic                                      |
| **codecongruence**     | Semantic drift between code and docstrings / names / CLAUDE.md / PR text / changelog / comments | Syntax, types, style                                   |

## Known-good linter combos

### Lightweight (most projects)

`ruff` + `mypy` + `codecongruence`.

### Frontend (React / Next.js / TS)

`biome` (or `eslint` + `prettier`) + `tsc --noEmit` + `codecongruence`
(JS/TS support shipped in v0.2 — `name_vs_body`, `stale_comments`, `docstring_vs_body` via JSDoc).

### Strict (regulated / large repos)

`ruff` + `mypy --strict` + `bandit` + `interrogate` + `vulture` +
`codecongruence`.

### Mono-repo with mixed languages

Run language-specific linters per package (`ruff` in `services/python/*`,
`biome` in `services/ts/*`) and `codecongruence` repo-wide for the docs /
changelog / CLAUDE.md cross-cutting rules.

## Why "semantic" is a separate axis

Existing linters analyse **structure** (AST, types, lexer). codecongruence
analyses **meaning** via local sentence embeddings. The two categories don't
overlap and don't substitute for each other:

- A function can pass `ruff` + `mypy --strict` and still lie via its
    docstring or its name. codecongruence catches that.
- codecongruence won't tell you about an undefined variable. ruff/mypy will.

This is why we strongly recommend running them **all** in the same hook
chain. Pre-commit makes that one-line cheap.
