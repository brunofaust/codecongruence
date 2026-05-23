# Research foundation

`codecongruence` is grounded in published software-engineering research on
semantic alignment between code and natural-language artifacts. We cite the
papers below and explain how each rule maps to the literature.

## Core references

### CoCC — Code-comment Consistency

Liu et al., 2024 — *Detecting Outdated Comments through Semantic Drift*.
[arXiv:2403.00251](https://arxiv.org/abs/2403.00251)

> Trains a sentence-pair classifier over (comment, code body) and detects
> outdated comments in 22 Java projects with **>90% precision**. The authors
> also reproduce the result on Python with comparable numbers.

**Maps to:** `docstring_vs_body`, `stale_comments`.

### Co3D — Code-comment coherence with simple embeddings

EASE 2024 — *Code-comment Coherence Detection with Lightweight Embeddings*.
[arXiv:2405.16272](https://arxiv.org/abs/2405.16272)

> A `word2vec + LSTM` pipeline beats heavier pre-trained baselines (CodeBERT,
> GraphCodeBERT) on code–comment coherence. Argues that compact embeddings
> are sufficient when the task is short-text alignment rather than full
> semantic understanding.

**Maps to:** every embedding-based rule. Justifies our choice of a small
`bge-small-en-v1.5` model (~130 MB) rather than a 400+ MB encoder.

### SIDE — Code-summary coherence metric

2025 — *SIDE: Code-Summary Coherence as a Signal for Dataset Curation*.
[arXiv:2502.07611](https://arxiv.org/abs/2502.07611)

> Defines a continuous "coherence" score between code and its natural-language
> summary, and uses it to *filter* training datasets for code LLMs. The same
> signal can be repurposed as a pre-commit gate.

**Maps to:** `docstring_vs_body`, `name_vs_body`. Validates that a single
cosine threshold can encode "this summary still describes this code."

### LLMs as code-doc coherence judges

2025 — *Evaluating Code-Documentation Coherence with Large Language Models*.
[arXiv:2507.05289](https://arxiv.org/abs/2507.05289)

> Shows that frontier LLMs reliably evaluate "coherence between identifier
> names, comments, and documentation with code purpose." Provides a labelled
> benchmark that we can use to validate threshold choices.

**Maps to:** future `llm_judge` rule (planned for v0.3) as a fallback for
edge cases where the embedding-only score is borderline.

## Why local embeddings rather than an LLM

1. **Determinism.** A pre-commit hook must give the same answer twice. Local
    ONNX inference is deterministic; cloud LLMs drift.
1. **Cost.** Pre-commit runs on every commit. Even with caching, an LLM-based
    check creates ongoing API spend per contributor.
1. **Privacy.** Many enterprise codebases legally cannot send code to a
    third-party API.
1. **Speed.** `bge-small-en-v1.5` embeds dozens of short texts per second on
    a CPU; an LLM round-trip is hundreds of milliseconds *per pair*.

The trade-off is **expressivity**: an embedding model can't reason about
"this function deletes a row but its name says it gets one" the way a frontier
LLM can. Our rules compensate by combining embeddings with **structural
filters** (AST, diff ranges, decorator skipping, ignore lists) so the false-
positive rate stays low.

## Threshold defaults — how they were chosen

The defaults below are conservative starting points biased toward **low false
positives** so the hook does not become annoying. Tune up over time.

| Rule                     | Default | Rationale                                                                                                                            |
| ------------------------ | ------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `docstring_vs_body`      | 0.30    | bge-small cosine on aligned docstring/body pairs sits ~0.45-0.60; misaligned pairs cluster \<0.20. 0.30 leaves a comfortable buffer. |
| `name_vs_body`           | 0.25    | Names are very short → low absolute cosine even when aligned. Pairs paraphrased names with body via abbreviation expansion.          |
| `claude_md_vs_diff`      | 0.20    | Diffs include git markers + filenames that artificially boost similarity; lower threshold compensates.                               |
| `pr_description_vs_diff` | 0.25    | Same dynamics as `claude_md_vs_diff`, slightly tighter because PR descriptions are usually higher-quality prose.                     |
| `stale_comments`         | 0.20    | Inline comments are very short; aligned pairs sit ~0.30-0.50. 0.20 catches the egregious cases without flagging good code.           |

A future v0.2 milestone is to validate these against the CoCC + LLM-judge
labelled datasets.
