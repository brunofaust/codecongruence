"""Tests for embedding cache persistence and garbage collection."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from codecongruence.core.embedder import Embedder
from tests.conftest import BagOfWordsBackend


async def test_embed_stays_in_memory(tmp_path: Path) -> None:
    """embed() does not touch disk — file must not exist before save()."""
    backend = BagOfWordsBackend()
    cache_dir = tmp_path / ".codecongruence-cache"
    e = Embedder(model_name="fake", backend=backend, cache_dir=cache_dir)
    _ = await e.similarity("hello world", "world hello")
    assert not (cache_dir / "embeddings.npz").exists()


async def test_save_writes_to_disk(tmp_path: Path) -> None:
    """save() is the single disk-write point."""
    backend = BagOfWordsBackend()
    cache_dir = tmp_path / ".codecongruence-cache"
    e = Embedder(model_name="fake", backend=backend, cache_dir=cache_dir)
    _ = await e.similarity("hello world", "world hello")
    e.save()
    assert (cache_dir / "embeddings.npz").exists()


async def test_cache_loads_from_disk(tmp_path: Path) -> None:
    """Embeddings saved by save() are warm on the next run."""
    backend = BagOfWordsBackend()
    cache_dir = tmp_path / ".codecongruence-cache"

    e1 = Embedder(model_name="fake", backend=backend, cache_dir=cache_dir)
    sim1 = await e1.similarity("hello world", "world hello")
    e1.save()

    backend2 = BagOfWordsBackend()
    e2 = Embedder(model_name="fake", backend=backend2, cache_dir=cache_dir)
    sim2 = await e2.similarity("hello world", "world hello")

    assert abs(sim1 - sim2) < 1e-5
    assert not backend2._vocab  # loaded from disk — backend2 never called


async def test_cache_discarded_on_model_change(tmp_path: Path) -> None:
    """Cache is invalidated when the model name changes."""
    cache_dir = tmp_path / ".codecongruence-cache"
    backend1 = BagOfWordsBackend()
    e1 = Embedder(model_name="model-A", backend=backend1, cache_dir=cache_dir)
    _ = await e1.similarity("hello", "world")
    e1.save()

    backend2 = BagOfWordsBackend()
    e2 = Embedder(model_name="model-B", backend=backend2, cache_dir=cache_dir)
    _ = await e2.similarity("hello", "world")
    assert backend2._vocab  # cache discarded — different model


async def test_save_force_cleanup_removes_unseen(tmp_path: Path) -> None:
    """save(force_cleanup=True) removes entries not accessed in this run."""
    cache_dir = tmp_path / ".codecongruence-cache"
    backend = BagOfWordsBackend()
    e1 = Embedder(model_name="fake", backend=backend, cache_dir=cache_dir)
    _ = await e1.similarity("alpha beta", "gamma delta")
    _ = await e1.similarity("foo bar", "baz qux")
    initial_count = len(e1._cache)
    e1.save()

    # New run: access only "alpha beta"
    backend2 = BagOfWordsBackend()
    e2 = Embedder(model_name="fake", backend=backend2, cache_dir=cache_dir)
    _ = await e2.similarity("alpha beta", "alpha beta")
    removed = e2.save(force_cleanup=True)

    assert removed > 0
    assert len(e2._cache) == initial_count - removed

    # Reload: disk must reflect the compaction
    backend3 = BagOfWordsBackend()
    e3 = Embedder(model_name="fake", backend=backend3, cache_dir=cache_dir)
    assert len(e3._cache) == len(e2._cache)


async def test_force_cleanup_emptying_cache_removes_disk_file(tmp_path: Path) -> None:
    """When cleanup evicts everything, the stale npz must not survive on disk."""
    cache_dir = tmp_path / ".codecongruence-cache"
    backend = BagOfWordsBackend()
    e1 = Embedder(model_name="fake", backend=backend, cache_dir=cache_dir)
    _ = await e1.similarity("alpha beta", "gamma delta")
    e1.save()
    assert (cache_dir / "embeddings.npz").exists()

    # New run: access nothing, then force cleanup — cache empties entirely.
    e2 = Embedder(model_name="fake", backend=BagOfWordsBackend(), cache_dir=cache_dir)
    removed = e2.save(force_cleanup=True)

    assert removed > 0
    assert len(e2._cache) == 0
    assert not (cache_dir / "embeddings.npz").exists()


async def test_save_without_cleanup_preserves_unseen(tmp_path: Path) -> None:
    """save() without force_cleanup keeps all cached entries on disk."""
    cache_dir = tmp_path / ".codecongruence-cache"
    backend = BagOfWordsBackend()
    e1 = Embedder(model_name="fake", backend=backend, cache_dir=cache_dir)
    _ = await e1.similarity("alpha beta", "gamma delta")
    initial_count = len(e1._cache)
    e1.save()

    # New run: access only one text, no cleanup
    backend2 = BagOfWordsBackend()
    e2 = Embedder(model_name="fake", backend=backend2, cache_dir=cache_dir)
    _ = await e2.similarity("alpha beta", "alpha beta")
    removed = e2.save(force_cleanup=False)

    assert removed == 0
    assert len(e2._cache) == initial_count  # unseen entries kept


async def test_cache_ttl_evicts_expired_entries(tmp_path: Path) -> None:
    """Entries older than cache_ttl_days are discarded at load time."""
    cache_dir = tmp_path / ".codecongruence-cache"
    backend1 = BagOfWordsBackend()
    e1 = Embedder(model_name="fake", backend=backend1, cache_dir=cache_dir, cache_ttl_days=3)
    _ = await e1.similarity("hello", "world")
    e1.save()

    # Backdate last_used timestamps by 2 days
    path = cache_dir / "embeddings.npz"
    data = np.load(path)
    np.savez_compressed(
        path,
        model=data["model"],
        hashes=data["hashes"],
        matrix=data["matrix"],
        last_used=data["last_used"] - (2 * 86400),
    )

    backend2 = BagOfWordsBackend()
    e2 = Embedder(model_name="fake", backend=backend2, cache_dir=cache_dir, cache_ttl_days=1)
    _ = await e2.similarity("hello", "world")
    assert backend2._vocab  # cache expired — had to re-embed


async def test_cache_ttl_zero_disables_eviction(tmp_path: Path) -> None:
    """cache_ttl_days=0 disables TTL eviction entirely."""
    cache_dir = tmp_path / ".codecongruence-cache"
    backend1 = BagOfWordsBackend()
    e1 = Embedder(model_name="fake", backend=backend1, cache_dir=cache_dir)
    _ = await e1.similarity("hello", "world")
    e1.save()

    # Backdate timestamps to Unix epoch
    path = cache_dir / "embeddings.npz"
    data = np.load(path)
    np.savez_compressed(
        path,
        model=data["model"],
        hashes=data["hashes"],
        matrix=data["matrix"],
        last_used=np.zeros_like(data["last_used"]),
    )

    backend2 = BagOfWordsBackend()
    e2 = Embedder(model_name="fake", backend=backend2, cache_dir=cache_dir, cache_ttl_days=0)
    _ = await e2.similarity("hello", "world")
    assert not backend2._vocab  # TTL disabled — cache still warm
