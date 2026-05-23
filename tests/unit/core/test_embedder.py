from __future__ import annotations

import numpy as np

from codecongruence.core.embedder import Embedder
from tests.conftest import BagOfWordsBackend


def test_cosine_orthogonal_zero() -> None:
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    assert Embedder.cosine(a, b) == 0.0


def test_cosine_identical_one() -> None:
    a = np.array([0.6, 0.8], dtype=np.float32)
    assert Embedder.cosine(a, a) == 1.0


def test_cosine_zero_vector_safe() -> None:
    a = np.zeros(3, dtype=np.float32)
    b = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert Embedder.cosine(a, b) == 0.0


def test_similarity_overlapping_words(fake_embedder: Embedder) -> None:
    sim = fake_embedder.similarity("connect to database", "database connection helper")
    assert sim > 0.4


def test_similarity_disjoint_text_low(fake_embedder: Embedder) -> None:
    sim = fake_embedder.similarity("draw a triangle", "send an email")
    assert sim < 0.15


def test_cache_reuses_vectors(fake_embedder: Embedder) -> None:
    fake_embedder.embed(["one two three", "alpha beta"])
    cache_before = dict(fake_embedder._cache)
    fake_embedder.embed(["one two three"])
    assert fake_embedder._cache.keys() == cache_before.keys()


def test_empty_input_returns_zeros(fake_embedder: Embedder) -> None:
    out = fake_embedder.embed([])
    assert out.shape == (0, 0)


def test_backend_protocol_accepted() -> None:
    backend = BagOfWordsBackend()
    emb = Embedder(model_name="x", backend=backend)
    sim = emb.similarity("hello world", "hello world")
    assert sim == 1.0
