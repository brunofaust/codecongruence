"""The vector cache is keyed on the backend: vectors from two engines never mix."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from codecongruence.core.backend import ONNX, ResolvedBackend
from codecongruence.core.embedder import Embedder, hash_text
from tests.conftest import BagOfWordsBackend

if TYPE_CHECKING:
    from pathlib import Path

MLX = ResolvedBackend(kind="mlx", mlx_repo="mlx-community/fake")


async def warm_cache(cache_dir: Path, resolved: ResolvedBackend) -> None:
    embedder = Embedder(
        model_name="fake", resolved=resolved, backend=BagOfWordsBackend(), cache_dir=cache_dir
    )
    await embedder.similarity("hello world", "world hello")
    embedder.save()


async def test_cache_written_by_another_backend_is_a_miss(tmp_path: Path) -> None:
    await warm_cache(tmp_path, ONNX)
    mlx_embedder = Embedder(
        model_name="fake", resolved=MLX, backend=BagOfWordsBackend(), cache_dir=tmp_path
    )
    assert mlx_embedder.cache_size == 0


async def test_cache_from_same_backend_is_a_hit(tmp_path: Path) -> None:
    await warm_cache(tmp_path, MLX)
    again = Embedder(
        model_name="fake", resolved=MLX, backend=BagOfWordsBackend(), cache_dir=tmp_path
    )
    assert again.cache_size == 2


async def test_save_records_the_backend(tmp_path: Path) -> None:
    await warm_cache(tmp_path, MLX)
    assert str(np.load(tmp_path / "embeddings.npz")["backend"]) == "mlx"


def write_legacy_cache(cache_dir: Path) -> None:
    """Write a cache in the pre-backend layout (no ``backend`` array)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        cache_dir / "embeddings.npz",
        model=np.array("fake"),
        hashes=np.array([hash_text("legacy")]),
        matrix=np.ones((1, 3), dtype=np.float32),
    )


def test_legacy_cache_without_backend_counts_as_onnx(tmp_path: Path) -> None:
    write_legacy_cache(tmp_path)
    onnx = Embedder(
        model_name="fake", resolved=ONNX, backend=BagOfWordsBackend(), cache_dir=tmp_path
    )
    mlx = Embedder(model_name="fake", resolved=MLX, backend=BagOfWordsBackend(), cache_dir=tmp_path)
    assert onnx.cache_size == 1
    assert mlx.cache_size == 0


def test_base_cache_of_another_backend_is_ignored(tmp_path: Path) -> None:
    base = tmp_path / "base"
    write_legacy_cache(base)
    embedder = Embedder(
        model_name="fake",
        resolved=MLX,
        backend=BagOfWordsBackend(),
        cache_dir=tmp_path / "local",
        base_cache_dir=base,
    )
    assert embedder.cache_size == 0
