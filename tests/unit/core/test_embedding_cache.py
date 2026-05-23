from __future__ import annotations

from pathlib import Path

from codecongruence.core.embedder import Embedder
from tests.conftest import BagOfWordsBackend


def test_cache_persists_to_disk(tmp_path: Path) -> None:
    backend = BagOfWordsBackend()
    cache_dir = tmp_path / ".codecongruence-cache"
    e = Embedder(model_name="fake", backend=backend, cache_dir=cache_dir)
    _ = e.similarity("hello world", "world hello")
    assert (cache_dir / "embeddings.json.gz").exists()


def test_cache_loads_from_disk(tmp_path: Path) -> None:
    backend = BagOfWordsBackend()
    cache_dir = tmp_path / ".codecongruence-cache"

    e1 = Embedder(model_name="fake", backend=backend, cache_dir=cache_dir)
    sim1 = e1.similarity("hello world", "world hello")

    # Second instance loads from disk — backend should not be called again.
    backend2 = BagOfWordsBackend()
    e2 = Embedder(model_name="fake", backend=backend2, cache_dir=cache_dir)
    sim2 = e2.similarity("hello world", "world hello")

    assert abs(sim1 - sim2) < 1e-5
    # backend2 was never asked to embed because the cache was warm.
    assert not backend2._vocab


def test_cache_discarded_on_model_change(tmp_path: Path) -> None:
    cache_dir = tmp_path / ".codecongruence-cache"
    backend1 = BagOfWordsBackend()
    e1 = Embedder(model_name="model-A", backend=backend1, cache_dir=cache_dir)
    _ = e1.similarity("hello", "world")

    # Different model — cache should be ignored and re-embedded.
    backend2 = BagOfWordsBackend()
    e2 = Embedder(model_name="model-B", backend=backend2, cache_dir=cache_dir)
    _ = e2.similarity("hello", "world")
    assert backend2._vocab  # backend2 was actually called
