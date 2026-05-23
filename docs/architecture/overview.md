# Architecture overview

See the top-level [`ARCHITECTURE.md`](../../ARCHITECTURE.md) for the full
diagram + layer descriptions. This directory is for deeper dives that are too
long to fit there.

## Currently empty

We will add the following pages as the codebase grows:

- `embedder.md` — model selection trade-offs, ONNX vs PyTorch path, cache
    invalidation strategy.
- `diff-awareness.md` — exactly how `--cached --unified=0` is parsed into
    `ChangedFile.added_ranges` and how rules intersect those with AST ranges.
- `extensibility.md` — entry-point plugin design once the v0.2 plugin system
    lands.
