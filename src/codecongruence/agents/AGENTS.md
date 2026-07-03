## codecongruence

This repository uses [codecongruence](https://github.com/brunofaust/codecongruence)
as a pre-commit hook to detect **semantic drift** between code and surrounding
text artifacts (docstrings, comments, function names, CLAUDE.md, CHANGELOG).
It uses local sentence embeddings (ONNX, offline) — no API calls, no PyTorch.

When you see a codecongruence violation, read the rule code and apply the
matching fix strategy below.

## Rules

| Code | Rule                     | What it catches                                              |
| ---- | ------------------------ | ------------------------------------------------------------ |
| C001 | `name_vs_body`           | Function name contradicts what the body actually does        |
| C002 | `param_name_vs_usage`    | Parameter name clashes with how it is used in the body       |
| C003 | `duplicate_functions`    | Two functions with similar names and near-identical bodies   |
| D001 | `docstring_vs_body`      | Docstring describes stale behaviour after a refactor         |
| D002 | `stale_comments`         | Inline comment describes behaviour the code no longer has    |
| D003 | `claude_md_vs_diff`      | Unrelated CLAUDE.md edit buried inside a large code change   |
| D004 | `pr_description_vs_diff` | PR description does not match the actual diff (CI-only)      |
| D005 | `docs_on_change`         | `src/` changed but no docs file updated (CHANGELOG, README…) |
| D006 | `params_in_docstring`    | Docstring exists but a parameter is not documented in it     |

### Fix strategies

- **C001** — rename the function to match what it does, OR rewrite the body to match the declared intent.
- **C002** — rename the parameter to reflect its actual role in the body, OR restructure the usage.
- **C003** — merge the duplicate into one function (add a parameter if behavior varies), OR rename them to make their distinct roles explicit.
- **D001** — update the docstring to describe what the function currently does.
- **D002** — delete the stale comment or rewrite it to describe the current behaviour.
- **D003** — split the commit (CLAUDE.md change alone), or expand CLAUDE.md to actually document the code change.
- **D004** — write a PR description that covers every meaningful change in the diff.
- **D005** — add a CHANGELOG entry or README note explaining what changed in `src/`.
- **D006** — add the missing parameter to the `Args:` section of the docstring.

## Reading violations

```
src/auth/token.py:42  C001  name_vs_body  similarity=0.18 < 0.25
  Function name suggests one behaviour, body does another.
```

Fields: `file:line  CODE  rule_id  similarity=<score> < <threshold>`

Lower similarity = more drift. Threshold is configurable per rule in
`codecongruence.toml` or `pyproject.toml [tool.codecongruence]`.

## Acting on a violation — never confabulate the path

The default terminal report is a `rich` table. When codecongruence runs as a
pre-commit hook its output is **captured, not a TTY**, so `rich` falls back to
an 80-column width and long cells wrap across lines — a C003 message carries
**two** `file:line` pairs and folds mid-path. A wrapped path is easy to
misread and reconstruct wrong (e.g. inventing a `core/ai/llm/ai_model.py`
segment when the real file is `core/ai/ai_model.py`).

Before you edit anything a violation points at:

1. **Re-run for authoritative locations:** `codecongruence --format json`. The
    `violations[].file_path` and `violations[].line` fields are exact,
    unwrapped, and taken straight from git's tracked-file list.
2. **Copy the path verbatim** from that JSON (or from the un-wrapped `file:line`
    column) — do **not** reconstruct it from your mental model of the repo
    layout.
3. **Confirm it exists** before editing. If your recollection of the path
    differs from the tool's, the tool is authoritative — it only reports files
    git is tracking.

## Commands

```bash
codecongruence              # check staged changes (runs on git commit)
codecongruence --all        # scan whole repo without staging
codecongruence --rule docstring_vs_body  # single rule
codecongruence --format json             # machine-readable (CI)
```

## Config tuning

```toml
# codecongruence.toml — lower threshold = stricter (fewer violations reported)
[rules.docstring_vs_body]
threshold = 0.30        # raise to 0.40 if too noisy on short functions

[rules.name_vs_body]
threshold = 0.25
ignore_names = ["main", "run", "setup"]  # skip these names entirely
```
