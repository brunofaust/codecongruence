"""MLX vs ONNX equivalence on the real model. Runs only where MLX is installed.

This is what justifies sharing one embedding cache across both backends for the
same model: if the engines drift apart, shared cache entries stop being valid.
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

import numpy as np
import pytest

from codecongruence.core.backend import (
    MLX_MODEL_MAP,
    ONNX,
    ResolvedBackend,
    is_apple_silicon,
    mlx_installed,
)
from codecongruence.core.config import DEFAULT_MODEL
from codecongruence.core.embedder import Embedder

if TYPE_CHECKING:
    from numpy.typing import NDArray

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not (is_apple_silicon() and mlx_installed()),
        reason="MLX needs Apple Silicon with the codecongruence[mlx] extra",
    ),
]

SNIPPETS = (
    "def add(a, b):\n    return a + b",
    "Return the sum of two numbers.",
    "async def fetch_user(session, user_id):\n    return await session.get(user_id)",
    "Fetch a user record from the database by identifier.",
    "class RetryPolicy:\n    max_attempts = 3\n    backoff = 2.0",
    "Configuration for how many times a failed request is retried.",
    "for line in open(path):\n    total += len(line)",
    "Count the characters in every line of a file.",
    "SELECT name, email FROM users WHERE active = 1 ORDER BY name",
    "List the active users alphabetically.",
    "The quick brown fox jumps over the lazy dog.",
    "Photosynthesis converts sunlight, water and carbon dioxide into glucose.",
    "def is_prime(n):\n    return n > 1 and all(n % i for i in range(2, int(n**0.5) + 1))",
    "Check whether a number is prime.",
    "git rebase --onto main feature~3 feature",
    "Move the last three commits of a branch onto main.",
    "# TODO: remove this once the migration is finished",
    "Delete the temporary workaround after the migration completes.",
    "Pydantic validates data at the boundary of the system.",
    "x",
)


def embed_all(resolved: ResolvedBackend) -> NDArray[np.float32]:
    return Embedder(model_name=DEFAULT_MODEL, resolved=resolved).embed(SNIPPETS)


def grid_of(vectors: NDArray[np.float32]) -> NDArray[np.float32]:
    grid: NDArray[np.float32] = vectors @ vectors.T
    np.fill_diagonal(grid, -1.0)
    return grid


def test_mlx_matches_onnx() -> None:
    onnx = embed_all(ONNX)
    mlx = embed_all(ResolvedBackend(kind="mlx", mlx_repo=MLX_MODEL_MAP[DEFAULT_MODEL]))
    assert onnx.shape == mlx.shape

    per_text = [Embedder.cosine(a, b) for a, b in zip(onnx, mlx, strict=True)]
    assert min(per_text) >= 0.995, per_text

    # Pairwise similarity ordering must survive: rank every pair under each engine.
    pairs = list(itertools.combinations(range(len(SNIPPETS)), 2))
    onnx_sims = np.array([Embedder.cosine(onnx[i], onnx[j]) for i, j in pairs])
    mlx_sims = np.array([Embedder.cosine(mlx[i], mlx[j]) for i, j in pairs])
    # Near-ties may swap under ~1e-3 noise; only pairs further apart than the
    # noise floor have to keep their order.
    noise = 5e-3
    flipped = [
        (pairs[a], pairs[b])
        for a, b in itertools.combinations(np.argsort(onnx_sims), 2)
        if onnx_sims[b] - onnx_sims[a] > noise and mlx_sims[b] <= mlx_sims[a]
    ]
    assert not flipped, flipped[:5]

    # Retrieval-style check: every text keeps the same nearest neighbour.
    assert np.array_equal(np.argmax(grid_of(onnx), axis=1), np.argmax(grid_of(mlx), axis=1))
