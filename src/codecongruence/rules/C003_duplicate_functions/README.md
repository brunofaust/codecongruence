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
exclude = ["tests/**"]
```

Set `include_comments = false` when comment-only edits must not change C003's
similarity input. Python `#` comments and nested definition docstrings are
removed with tree-sitter, while JavaScript/TypeScript `//` comments use the
shared line helper from C001 and D001.

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
