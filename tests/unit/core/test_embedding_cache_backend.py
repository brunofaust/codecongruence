"""The vector cache is keyed by model only: ONNX and MLX share it."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from codecongruence.core.backend import ONNX, ResolvedBackend
from codecongruence.core.embedder import Embedder, hash_text
from tests.conftest import BagOfWordsBackend

if TYPE_CHECKING:
    from pathlib import Path

MLX = ResolvedBackend(kind="mlx", mlx_repo="mlx-community/fake")


async def warm_cache(cache_dir: Path, resolved: ResolvedBackend, model: str = "fake") -> None:
    embedder = Embedder(
        model_name=model, resolved=resolved, backend=BagOfWordsBackend(), cache_dir=cache_dir
    )
    await embedder.similarity("hello world", "world hello")
    embedder.save()


async def test_onnx_cache_is_reused_under_mlx(tmp_path: Path) -> None:
    await warm_cache(tmp_path, ONNX)
    mlx = Embedder(model_name="fake", resolved=MLX, backend=BagOfWordsBackend(), cache_dir=tmp_path)
    assert mlx.cache_size == 2


async def test_mlx_cache_is_reused_under_onnx(tmp_path: Path) -> None:
    await warm_cache(tmp_path, MLX)
    onnx = Embedder(
        model_name="fake", resolved=ONNX, backend=BagOfWordsBackend(), cache_dir=tmp_path
    )
    assert onnx.cache_size == 2


async def test_different_model_is_still_a_miss(tmp_path: Path) -> None:
    await warm_cache(tmp_path, ONNX, model="model-A")
    other = Embedder(
        model_name="model-B", resolved=MLX, backend=BagOfWordsBackend(), cache_dir=tmp_path
    )
    assert other.cache_size == 0


async def test_save_does_not_record_the_backend(tmp_path: Path) -> None:
    await warm_cache(tmp_path, MLX)
    assert "backend" not in np.load(tmp_path / "embeddings.npz").files


def test_legacy_cache_is_reused_by_either_backend(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        tmp_path / "embeddings.npz",
        model=np.array("fake"),
        hashes=np.array([hash_text("legacy")]),
        matrix=np.ones((1, 3), dtype=np.float32),
    )
    for resolved in (ONNX, MLX):
        embedder = Embedder(
            model_name="fake", resolved=resolved, backend=BagOfWordsBackend(), cache_dir=tmp_path
        )
        assert embedder.cache_size == 1
