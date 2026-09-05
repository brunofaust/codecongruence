# `duplicate_functions` — **C003**

**What it catches:** Two functions with different names whose bodies do the
same thing. Classic example: `fetch_user_by_id(uid)` and `load_user(user_id)`
in different modules both query the same table with the same logic.

**Default threshold:** `0.92` (cosine). High on purpose — function bodies
share a lot of structural vocabulary; a lower threshold produces too many
false positives on legitimate similar-but-distinct functions.

## How it works

1. Collect all functions from the files in scope (see `scope` config).
1. Include or strip inline comments according to `include_comments` (comments
    are included by default for backwards compatibility).
1. Remove every `strip_before_compare` match from the body — see
    [Stripping house-style boilerplate](#stripping-house-style-boilerplate).
1. Embed all bodies in a single batch call (one ONNX pass regardless of how
    many functions are in scope).
1. Compute pairwise cosine similarity in NumPy.
1. Drop pairs excluded by an opt-in structural skip — see
    [Structural exclusions](#structural-exclusions-opt-in).
1. Flag any pair where `sim >= threshold` and the qualified names differ.

## Configuration

```toml
[rules.duplicate_functions]
enabled = true
threshold = 0.92
scope = "staged"               # "staged" (default) or "full"
min_body_statement_count = 3   # skip trivial one-liners
include_comments = true        # include inline comments (default)
skip_nested_functions = false  # opt in to drop closure-vs-parent pairs
skip_call_edges = false        # opt in to drop wrapper-vs-callee pairs
strip_min_remnant_chars = 24   # floor below which a strip is not trusted
exclude = ["tests/**"]

# Regexes removed from both sides before comparison. Use TOML *literal*
# strings (single quotes) so backslashes reach the regex engine intact.
# This flat list is UNSCOPED: it applies to every function.
strip_before_compare = [
    '^\s*raise HTTPException\(.*\)\s*$',
]

# Scoped by file glob — the key is a path glob.
[rules.duplicate_functions.strip_before_compare_by_path]
'tests/**/a*.py' = ['^\s*self\.assert\w+\(.*\)\s*$']
'src/api/**' = ['^\s*raise HTTPException\(.*\)\s*$']

# Scoped by symbol name — the key is a regex on the function's simple name.
[rules.duplicate_functions.strip_before_compare_by_symbol]
'^test_' = ['^\s*monkeypatch\.\w+\(.*\)\s*$']
'_handler$' = ['^\s*log\.\w+\(.*\)\s*$']
```

Set `include_comments = false` when comment-only edits must not change C003's
similarity input. Python `#` comments and nested definition docstrings are
removed with tree-sitter, while JavaScript/TypeScript `//` comments use the
shared line helper from C001 and D001.

### Stripping house-style boilerplate

`strip_before_compare` is a list of **regular expressions** removed from every
function body before it is embedded. It exists because the boilerplate that
makes unrelated functions look alike is project-specific: codecongruence
supplies the stripping, your project supplies its own patterns, so the tool
never has to know what FastAPI or boto3 is.

Regexes, not literal strings, because the real frames vary in their payload —
one pattern has to cover both of these:

```python
raise HTTPException(status_code=404, detail="org not found")
raise HTTPException(status_code=404, detail="plan not found")
```

#### Scoping

A pattern written for one area must not silently strip text everywhere, so
patterns come in three forms:

| Key                                                              | Applies to                   |
| ---------------------------------------------------------------- | ---------------------------- |
| `strip_before_compare` (flat list)                               | every function               |
| `[…strip_before_compare_by_path]`, key = **file glob**           | functions in matching files  |
| `[…strip_before_compare_by_symbol]`, key = **symbol-name regex** | functions whose name matches |

The kind of key is declared by the table it sits in, never guessed from the
key itself — `tests/**/a*.py` and `^test_` are both valid strings, so a single
bare mapping could not tell them apart.

Scopes **compose**: a function gets the union of the unscoped patterns and
every matching path and symbol scope, in configuration order. Nothing needs a
`**` glob to mean "everywhere" — that is what the flat list is for.

`_by_path` keys are file globs in the same `fnmatch` dialect the runner already
uses for `exclude` and `exclude_functions`, so this project has one notion of a
glob rather than two. `*` crosses `/`, so `tests/**/a*.py` and `tests/*/a*.py`
both match `tests/unit/alpha.py`. Matching is case-sensitive.

`_by_symbol` keys are regexes matched with `re.search` against the function's
**simple** name, so `^test_` and `_handler$` behave the way they read.

**Globs match the repo-relative POSIX path**, anchored on the repository root
rather than the process working directory — a glob that works from the repo
root works identically from a subdirectory. An absolute glob is rejected at
config load, since it could never match.

Notes:

- Patterns are compiled once per run with `re.MULTILINE`, so `^` and `$`
    anchor per line. A multi-line frame opts in with an inline `(?s)`.
- Globs and symbol regexes are compiled once per run too, and each function's
    resolved pattern set is memoised per `(file, symbol)`, so scope matching is
    never repeated per compared pair.
- Every occurrence is removed, and the blank lines left behind are closed up.
- Write them as TOML **literal** strings (`'…'`), or every backslash needs
    doubling.
- An invalid pattern *or glob* is rejected when the config is *loaded*, with
    the offending value in the error. It is never silently skipped.
- The default — no list, no tables — is a strict no-op.

Stripping is applied to **both** sides and excludes nothing from comparison —
only the shared frame is removed, so what gets measured is the distinctive
remainder. That raises discrimination in both directions, and a pair that
becomes *newly* reported after stripping is the feature working, not a false
positive: an identical `db.query`/`fetchone` body wrapped in signature checks
and session bookkeeping scores 0.824 with the frame and 0.922 without it, so
the boilerplate was hiding a real duplicate.

#### `strip_min_remnant_chars` (default `24`)

Over-stripping is the one way this option can *lower* the bar: if a pattern
eats almost everything, two near-empty remnants match each other on nothing at
all. When a stripped body keeps fewer than `strip_min_remnant_chars`
non-whitespace characters, any pair involving it is compared **unstripped**
instead.

Falling back rather than skipping the pair is deliberate. Skipping would be a
suppression, and C003 suppresses nothing by default; falling back also
preserves the true positive where two functions really are nothing but the
same boilerplate. The cost is that a pair whose two sides land on opposite
sides of the floor is compared unstripped, which can only *miss* a finding,
never invent one. Note that comparison mode is therefore a property of the
*pair*, not of the function: a function whose remnant clears the floor is still
compared unstripped against a partner whose remnant does not, so the same
function can be compared both ways within one run.
`min_body_statement_count` is still measured before stripping, so a
heavily-boilerplate function is never dropped from the corpus.

### Structural exclusions (opt-in)

**Both options default to `false`.** They are audit aids, not corrections. C003
exists to find equal code, and in a duplicate detector the two error directions
are not symmetric: a false positive costs one dismissal, while a suppressed
pair is an invisible, permanent false negative that nothing will ever surface
again. So nothing is suppressed unless you ask for it.

Turn one on when a particular run is drowning in that pair shape, and turn it
back off before a deduplication audit.

#### `skip_nested_functions`

Drops a pair whose two source ranges are nested — a closure and the function
that defines it, at any depth. The child's source is *textually contained* in
the parent's, so the similarity is an artifact of the parse, and the pair is
undeletable anyway because the parent defines the closure. Only
ancestor/descendant pairs are affected: sibling closures have disjoint ranges
and stay compared, so a genuine duplicate between two closures in the same
parent is still reported. Line ranges are language-agnostic, so this works for
every parser.

This one has no known true-positive cost: containment holds only between a
definition and one of its own ancestors, so a closure copy-pasted from a
still-existing original elsewhere is not a containment pair and stays reported.

#### `skip_call_edges`

Drops a pair where one function **calls** the other — a wrapper delegating to
its single owner is correct design, not duplication. Call targets come from the
parser, and only Python is resolved today: for JavaScript/TypeScript the option
is inert.

The recogniser is deliberately narrow, because a missed skip only leaves a
false positive while a wrong skip hides a real duplicate:

- Only **unqualified** `f()` calls count. Any receiver-qualified call is
    ignored, `self.f()` included — this layer does not resolve the receiver, so
    `self.render()` on one class must not be read as a call to an unrelated
    `render()` on another.
- The callee's simple name must occur **exactly once** among the compared
    functions, so two same-named methods on different classes never make a call
    edge look resolved.
- A call through an import alias or a module qualifier (`pricing.f()`) is not
    recognised, so such a pair stays reported.

Even so, this option **can hide a true positive**: a pair that is both a
genuine duplicate and a caller/callee — copy-paste followed by a partial
refactor, or mutual recursion between two duplicates — is suppressed. That is
the main reason it is off by default. Two further consequences: a bare call is
matched by simple name across files, so a caller invoking some unparsed
`helper()` can suppress its pair with an unrelated, uniquely-named `helper`
elsewhere in the set; and because the uniqueness guard is evaluated over the
compared set, `scope = "full"` can suppress fewer pairs than `scope = "staged"`.

### `scope`

| Value                | What is compared                                                                   |
| -------------------- | ---------------------------------------------------------------------------------- |
| `"staged"` (default) | Functions in staged/changed files only — fast, checks your current diff            |
| `"full"`             | Every tracked file in the repo — slow on large codebases, good as a periodic audit |

`full` mode embeds every function body in the repo. The Embedder's
content-hash disk cache means unchanged functions are not re-embedded on
subsequent runs.

### Performance note

Pairwise comparison is O(n²) in the number of functions. `full` mode on a
repo with 500 functions runs ~125,000 cosine comparisons (pure NumPy,
sub-second after embedding). The bottleneck is the initial batch embedding
on the first run; subsequent runs are fast due to caching.

## Notes

- `@overload`-decorated stubs and dataclass `__init__` methods are skipped.
- A pair is only flagged once — on the function that appears first by
    file path + line number.
- `self` / `cls` method bodies often share boilerplate; tune `threshold`
    upward (0.95+) if you see too many false positives on class methods.
