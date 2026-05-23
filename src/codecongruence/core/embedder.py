"""Thin wrapper around ``fastembed`` providing batched embedding + cosine similarity.

One model instance per run is shared across all rules (model load is expensive).
Per-run content-hash cache prevents re-embedding identical text inside the same
process. ONNX-based fastembed avoids the PyTorch dependency entirely.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
from typing import TYPE_CHECKING, Protocol, cast

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

    from numpy.typing import NDArray


__all__ = ["Embedder", "EmbeddingBackend"]

log = logging.getLogger(__name__)


class EmbeddingBackend(Protocol):
    """Minimal protocol implemented by ``fastembed.TextEmbedding``."""

    def embed(self, documents: Sequence[str]) -> Iterable[NDArray[np.float32]]: ...


def _hash(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


_CACHE_FILE = "embeddings.json.gz"


class Embedder:
    """Embed strings → float32 vectors with cosine helper.

    Defaults to ``BAAI/bge-small-en-v1.5`` (384-dim, MTEB 62.2). Lazily loads
    the underlying model on first call so unit tests can patch the backend.

    When ``cache_dir`` is provided the in-memory cache is loaded from
    ``<cache_dir>/embeddings.json.gz`` at construction and flushed back after
    every new batch of embeddings, so repeated runs never re-embed unchanged
    text.  The cache is keyed by content-hash and tagged with the model name;
    entries from a different model are silently discarded.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        *,
        backend: EmbeddingBackend | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.model_name = model_name
        self._backend: EmbeddingBackend | None = backend
        self._cache: dict[str, NDArray[np.float32]] = {}
        self._cache_dir = cache_dir
        if cache_dir is not None:
            self._load_disk_cache(cache_dir)

    def _cache_path(self, cache_dir: Path) -> Path:
        return cache_dir / _CACHE_FILE

    def _load_disk_cache(self, cache_dir: Path) -> None:
        path = self._cache_path(cache_dir)
        if not path.exists():
            return
        try:
            with gzip.open(path, "rb") as fh:
                data: dict = json.loads(fh.read())
            if data.get("model") != self.model_name:
                return  # different model — discard stale cache
            for key, vec in data.get("embeddings", {}).items():
                self._cache[key] = np.array(vec, dtype=np.float32)
        except (OSError, json.JSONDecodeError, ValueError):
            log.debug("could not load embedding cache from %s", path)

    def _save_disk_cache(self, cache_dir: Path) -> None:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "model": self.model_name,
                "embeddings": {k: v.tolist() for k, v in self._cache.items()},
            }
            with gzip.open(self._cache_path(cache_dir), "wb") as fh:
                fh.write(json.dumps(payload, separators=(",", ":")).encode())
        except OSError:
            log.debug("could not persist embedding cache to %s", cache_dir)

    def _ensure_backend(self) -> EmbeddingBackend:
        if self._backend is None:
            # Heavy import deferred so unit tests with a fake backend never pay
            # the onnxruntime / tokenizers load cost.
            from fastembed import TextEmbedding  # noqa: PLC0415

            self._backend = cast("EmbeddingBackend", TextEmbedding(model_name=self.model_name))
        return self._backend

    def embed(self, texts: Sequence[str]) -> NDArray[np.float32]:
        """Embed ``texts`` → ``(n, d)`` float32 matrix.

        Cached per-text by content hash. Empty strings short-circuit to zeros.
        """
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)

        resolved: dict[int, NDArray[np.float32]] = {}
        missing_idx: list[int] = []
        missing_text: list[str] = []

        for i, text in enumerate(texts):
            if not text.strip():
                continue
            key = _hash(text)
            cached = self._cache.get(key)
            if cached is not None:
                resolved[i] = cached
            else:
                missing_idx.append(i)
                missing_text.append(text)

        if missing_text:
            backend = self._ensure_backend()
            raw = list(backend.embed(missing_text))
            for pos, (slot, vec) in enumerate(zip(missing_idx, raw, strict=True)):
                arr = np.asarray(vec, dtype=np.float32)
                self._cache[_hash(missing_text[pos])] = arr
                resolved[slot] = arr
            if self._cache_dir is not None:
                self._save_disk_cache(self._cache_dir)

        dim = max((int(v.shape[0]) for v in resolved.values()), default=0)
        result = np.zeros((len(texts), dim), dtype=np.float32)
        for i, vec in resolved.items():
            # Pad to current max dim (handles growing-vocab fake backends in tests
            # and any future backend whose dim isn't perfectly constant per batch).
            result[i, : int(vec.shape[0])] = vec
        return result

    @staticmethod
    def cosine(a: NDArray[np.float32], b: NDArray[np.float32]) -> float:
        """Cosine similarity of two 1-D vectors. Returns 0.0 if either is zero.

        Pads the shorter vector with zeros if shapes differ so callers don't have
        to worry about backend-dim drift. Clamps to [-1.0, 1.0] to absorb
        float32 round-off on near-identical vectors.
        """
        if a.shape != b.shape:
            n = max(int(a.shape[0]), int(b.shape[0]))
            a_pad = np.zeros(n, dtype=np.float32)
            b_pad = np.zeros(n, dtype=np.float32)
            a_pad[: int(a.shape[0])] = a
            b_pad[: int(b.shape[0])] = b
            a, b = a_pad, b_pad
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return float(min(1.0, max(-1.0, np.dot(a, b) / (na * nb))))

    def similarity(self, left: str, right: str) -> float:
        """Convenience: cosine similarity between two strings."""
        if not left.strip() or not right.strip():
            return 0.0
        mat = self.embed([left, right])
        return self.cosine(mat[0], mat[1])
