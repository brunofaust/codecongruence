"""Tests for embedding cache persistence and garbage collection."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from codecongruence.core.embedder import Embedder
from tests.conftest import BagOfWordsBackend


async def test_cache_persists_to_disk(tmp_path: Path) -> None:
    """Embeddings persist to disk in an NPZ file."""
    backend = BagOfWordsBackend()
    cache_dir = tmp_path / ".codecongruence-cache"
    e = Embedder(model_name="fake", backend=backend, cache_dir=cache_dir)
    _ = await e.similarity("hello world", "world hello")
    assert (cache_dir / "embeddings.npz").exists()


async def test_cache_loads_from_disk(tmp_path: Path) -> None:
    """Embeddings loaded from disk produce identical results."""
    backend = BagOfWordsBackend()
    cache_dir = tmp_path / ".codecongruence-cache"

    e1 = Embedder(model_name="fake", backend=backend, cache_dir=cache_dir)
    sim1 = await e1.similarity("hello world", "world hello")

    # Second instance loads from disk — backend should not be called again.
    backend2 = BagOfWordsBackend()
    e2 = Embedder(model_name="fake", backend=backend2, cache_dir=cache_dir)
    sim2 = await e2.similarity("hello world", "world hello")

    assert abs(sim1 - sim2) < 1e-5
    # backend2 was never asked to embed because the cache was warm.
    assert not backend2._vocab


async def test_cache_discarded_on_model_change(tmp_path: Path) -> None:
    """Cache is invalidated when the model name changes."""
    cache_dir = tmp_path / ".codecongruence-cache"
    backend1 = BagOfWordsBackend()
    e1 = Embedder(model_name="model-A", backend=backend1, cache_dir=cache_dir)
    _ = await e1.similarity("hello", "world")

    # Different model — cache should be ignored and re-embedded.
    backend2 = BagOfWordsBackend()
    e2 = Embedder(model_name="model-B", backend=backend2, cache_dir=cache_dir)
    _ = await e2.similarity("hello", "world")
    assert backend2._vocab  # backend2 was actually called


async def test_compact_removes_unseen_entries(tmp_path: Path) -> None:
    """compact() removes entries not accessed in this run."""
    cache_dir = tmp_path / ".codecongruence-cache"
    backend = BagOfWordsBackend()
    e1 = Embedder(model_name="fake", backend=backend, cache_dir=cache_dir)
    _ = await e1.similarity("alpha beta", "gamma delta")
    _ = await e1.similarity("foo bar", "baz qux")
    initial_count = len(e1._cache)

    # New run: only access "alpha beta"
    backend2 = BagOfWordsBackend()
    e2 = Embedder(model_name="fake", backend=backend2, cache_dir=cache_dir)
    _ = await e2.similarity("alpha beta", "alpha beta")
    removed = e2.compact()

    assert removed > 0
    assert len(e2._cache) == initial_count - removed

    # Verify disk reflects compaction
    data = np.load(cache_dir / "embeddings.npz")
    assert len(data["hashes"].tolist()) == len(e2._cache)


async def test_compact_returns_zero_when_all_seen(tmp_path: Path) -> None:
    """compact() is a no-op when every cached entry was accessed."""
    cache_dir = tmp_path / ".codecongruence-cache"
    backend = BagOfWordsBackend()
    e1 = Embedder(model_name="fake", backend=backend, cache_dir=cache_dir)
    _ = await e1.similarity("hello", "world")
    initial_count = len(e1._cache)

    # New run accessing the same texts
    backend2 = BagOfWordsBackend()
    e2 = Embedder(model_name="fake", backend=backend2, cache_dir=cache_dir)
    _ = await e2.similarity("hello", "world")
    removed = e2.compact()

    assert removed == 0
    assert len(e2._cache) == initial_count


async def test_cache_ttl_evicts_expired_entries(tmp_path: Path) -> None:
    """Entries older than cache_ttl_days are discarded at load time."""
    cache_dir = tmp_path / ".codecongruence-cache"
    backend = BagOfWordsBackend()
    e1 = Embedder(model_name="fake", backend=backend, cache_dir=cache_dir, cache_ttl_days=1)
    _ = await e1.similarity("hello", "world")

    # Backdate the last_used timestamps by 2 days
    path = cache_dir / "embeddings.npz"
    data = np.load(path)
    np.savez_compressed(
        path,
        model=data["model"],
        hashes=data["hashes"],
        matrix=data["matrix"],
        last_used=np.full(len(data["hashes"]), time.time() - 2 * 86400, dtype=np.float64),
    )

    # New embedder with 1-day TTL — expired entries are discarded
    backend2 = BagOfWordsBackend()
    e2 = Embedder(model_name="fake", backend=backend2, cache_dir=cache_dir, cache_ttl_days=1)
    _ = await e2.similarity("hello", "world")
    assert backend2._vocab  # cache was expired; backend2 had to re-embed


async def test_cache_ttl_zero_disables_eviction(tmp_path: Path) -> None:
    """cache_ttl_days=0 disables TTL — even ancient entries survive load."""
    cache_dir = tmp_path / ".codecongruence-cache"
    backend = BagOfWordsBackend()
    e1 = Embedder(model_name="fake", backend=backend, cache_dir=cache_dir, cache_ttl_days=0)
    _ = await e1.similarity("hello", "world")

    # Backdate timestamps to the Unix epoch (effectively ancient)
    path = cache_dir / "embeddings.npz"
    data = np.load(path)
    np.savez_compressed(
        path,
        model=data["model"],
        hashes=data["hashes"],
        matrix=data["matrix"],
        last_used=np.zeros(len(data["hashes"]), dtype=np.float64),
    )

    # TTL=0 → no eviction; cache is still warm
    backend2 = BagOfWordsBackend()
    e2 = Embedder(model_name="fake", backend=backend2, cache_dir=cache_dir, cache_ttl_days=0)
    _ = await e2.similarity("hello", "world")
    assert not backend2._vocab  # cache was warm despite ancient timestamps
