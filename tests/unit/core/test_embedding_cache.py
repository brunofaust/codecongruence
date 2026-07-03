"""Tests for embedding cache persistence and garbage collection."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from codecongruence.core.embedder import Embedder
from tests.conftest import BagOfWordsBackend


def load_hashes(cache_dir: Path) -> set[str]:
    """Return the content-hash keys persisted in ``cache_dir``'s npz, if any."""
    path = cache_dir / "embeddings.npz"
    if not path.exists():
        return set()
    return set(np.load(path)["hashes"].tolist())


def load_model(cache_dir: Path) -> str | None:
    """Return the model name recorded in ``cache_dir``'s npz, or ``None``."""
    path = cache_dir / "embeddings.npz"
    if not path.exists():
        return None
    return str(np.load(path)["model"])


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


async def test_base_cache_warms_local_without_rewrite(tmp_path: Path) -> None:
    """A read-only base warms a linked worktree; save() writes only local deltas."""
    base_dir = tmp_path / "main" / ".codecongruence"
    local_dir = tmp_path / "wt" / ".codecongruence"

    # Primary worktree embeds the shared corpus into the base.
    e_base = Embedder(model_name="fake", backend=BagOfWordsBackend(), cache_dir=base_dir)
    _ = await e_base.similarity("shared alpha", "shared beta")
    e_base.save()
    base_keys = load_hashes(base_dir)
    assert base_keys  # base was populated

    # Linked worktree: the base warms it, so the shared text is not re-embedded.
    backend = BagOfWordsBackend()
    e_local = Embedder(
        model_name="fake", backend=backend, cache_dir=local_dir, base_cache_dir=base_dir
    )
    _ = await e_local.similarity("shared alpha", "shared beta")
    assert not backend._vocab  # served from the base — no re-embed

    # A worktree-only text is computed and persisted locally.
    _ = await e_local.similarity("worktree only text", "worktree only text")
    e_local.save()

    local_keys = load_hashes(local_dir)
    # Local file holds only the new key — never the base keys (no duplication).
    assert local_keys
    assert local_keys.isdisjoint(base_keys)
    # The base file is left untouched.
    assert load_hashes(base_dir) == base_keys


async def test_base_equal_local_is_ignored(tmp_path: Path) -> None:
    """When the base resolves to the local dir, everything is locally owned."""
    cache_dir = tmp_path / ".codecongruence"
    e = Embedder(
        model_name="fake",
        backend=BagOfWordsBackend(),
        cache_dir=cache_dir,
        base_cache_dir=cache_dir,
    )
    _ = await e.similarity("hello world", "world hello")
    e.save()
    # Base did not swallow the entries — the primary worktree owns its cache.
    assert load_hashes(cache_dir)


async def test_force_cleanup_preserves_base(tmp_path: Path) -> None:
    """``--all`` in a linked worktree never evicts base-owned entries."""
    base_dir = tmp_path / "main" / ".codecongruence"
    local_dir = tmp_path / "wt" / ".codecongruence"

    e_base = Embedder(model_name="fake", backend=BagOfWordsBackend(), cache_dir=base_dir)
    _ = await e_base.similarity("base one", "base two")
    e_base.save()
    base_keys = load_hashes(base_dir)

    # Linked worktree touches only its own text, then force-cleans.
    e_local = Embedder(
        model_name="fake",
        backend=BagOfWordsBackend(),
        cache_dir=local_dir,
        base_cache_dir=base_dir,
    )
    _ = await e_local.similarity("worktree text", "worktree text")
    removed = e_local.save(force_cleanup=True)

    # Base keys were unseen this run but are not this worktree's to evict.
    assert removed == 0
    assert load_hashes(base_dir) == base_keys
    local_keys = load_hashes(local_dir)
    assert local_keys
    assert local_keys.isdisjoint(base_keys)


async def test_base_cache_ignored_on_model_change(tmp_path: Path) -> None:
    """A base built with model X is ignored when the run switches to model Y.

    The per-layer model guard means a stale-model base is discarded wholesale
    (never mixed with model-Y vectors), the run re-embeds with Y, and the base
    file is left untouched until the primary worktree rebuilds it. Cache keys
    are content hashes (model-independent), so the X and Y caches share keys —
    what changes is the stored ``model`` field and the vectors behind each key.
    """
    base_dir = tmp_path / "main" / ".codecongruence"
    local_dir = tmp_path / "wt" / ".codecongruence"

    # Primary worktree builds a base with model X.
    e_x = Embedder(model_name="model-X", backend=BagOfWordsBackend(), cache_dir=base_dir)
    _ = await e_x.similarity("shared alpha", "shared beta")
    e_x.save()
    assert load_model(base_dir) == "model-X"

    # Linked worktree now runs model Y with the model-X base underneath.
    backend_y = BagOfWordsBackend()
    e_y = Embedder(
        model_name="model-Y", backend=backend_y, cache_dir=local_dir, base_cache_dir=base_dir
    )
    _ = await e_y.similarity("shared alpha", "shared beta")
    # The X base did not warm the Y run — the text had to be re-embedded.
    assert backend_y._vocab
    e_y.save()

    # The stale-model base is left intact (only the primary rewrites it)...
    assert load_model(base_dir) == "model-X"
    # ...and the Y run persisted its own cache locally under model Y.
    assert load_model(local_dir) == "model-Y"


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
