"""Thin wrapper around ``fastembed`` providing batched embedding + cosine similarity.

One model instance per run is shared across all rules (model load is expensive).
Per-run content-hash cache prevents re-embedding identical text inside the same
process. ONNX-based fastembed avoids the PyTorch dependency entirely.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time
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

    def embed(self, documents: Sequence[str]) -> Iterable[NDArray[np.float32]]:
        """Embed a batch of documents into float32 vectors."""
        ...


def _hash(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


_CACHE_FILE = "embeddings.npz"


class Embedder:
    """Embed strings → float32 vectors with cosine helper.

    Defaults to ``BAAI/bge-small-en-v1.5`` (384-dim, MTEB 62.2). Lazily loads
    the underlying model on first call so unit tests can patch the backend.

    Args:
        model_name: fastembed model identifier.
        backend: Override the fastembed backend (used in tests).
        cache_dir: Directory for the per-run vector cache
            (``<cache_dir>/embeddings.npz``). Keyed by content-hash +
            model name; stale entries from a different model are discarded.
        model_cache_dir: Directory where fastembed stores downloaded model
            weights. Defaults to the fastembed system default (temp dir).
            Pass ``~/.cache/codecongruence`` for a persistent cross-run cache.
        threads: ONNX Runtime inter-op thread count forwarded to fastembed.
            ``None`` lets fastembed choose (usually one thread per CPU core).
        cache_ttl_days: Entries not accessed within this many days are
            discarded at load time. Set to ``0`` to disable TTL eviction.
            :meth:`compact` removes entries not accessed in the current run;
            call it at the end of a ``--all`` scan to evict stale embeddings.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        *,
        backend: EmbeddingBackend | None = None,
        cache_dir: Path | None = None,
        model_cache_dir: Path | None = None,
        threads: int | None = None,
        cache_ttl_days: int = 30,
    ) -> None:
        """Initialize the embedder. See class docstring for parameter details."""
        self.model_name = model_name
        self._backend: EmbeddingBackend | None = backend
        self._cache: dict[str, NDArray[np.float32]] = {}
        self._last_used: dict[str, float] = {}
        self._seen: set[str] = set()
        self._cache_dir = cache_dir
        self._model_cache_dir = model_cache_dir
        self._threads = threads
        self._cache_ttl_days = cache_ttl_days
        self._lock = threading.Lock()
        if cache_dir is not None:
            self._load_disk_cache(cache_dir)

    @staticmethod
    def _cache_path(cache_dir: Path) -> Path:
        return cache_dir / _CACHE_FILE

    @staticmethod
    def _parse_npz(
        path: Path, model_name: str, now: float
    ) -> tuple[dict[str, NDArray[np.float32]], dict[str, float]] | None:
        """Read an ``embeddings.npz`` file and return ``(cache, last_used)``.

        Returns ``None`` when the stored model name does not match.
        May raise ``OSError``, ``ValueError``, or ``KeyError`` on corrupt data.

        Args:
            path: Path to the ``.npz`` file.
            model_name: Expected model name; mismatches return ``None``.
            now: Current timestamp used when ``last_used`` is absent.

        Returns:
            A ``(cache, last_used)`` pair, or ``None`` on model mismatch.
        """
        data = np.load(path)
        if str(data["model"]) != model_name:
            return None
        hashes: list[str] = data["hashes"].tolist()
        matrix: NDArray[np.float32] = data["matrix"]
        cache: dict[str, NDArray[np.float32]] = dict(zip(hashes, matrix, strict=True))
        if "last_used" in data.files:
            timestamps: list[float] = data["last_used"].tolist()
            last_used: dict[str, float] = dict(zip(hashes, timestamps, strict=True))
        else:
            last_used = dict.fromkeys(hashes, now)
        return cache, last_used

    def _load_disk_cache(self, cache_dir: Path) -> None:
        path = self._cache_path(cache_dir)
        if not path.exists():
            return
        now = time.time()
        try:
            parsed = self._parse_npz(path, self.model_name, now)
        except (OSError, ValueError, KeyError):
            log.debug("could not load embedding cache from %s", path)
            return
        if parsed is None:
            return
        cache, last_used = parsed
        if self._cache_ttl_days > 0:
            cutoff = now - self._cache_ttl_days * 86400
            cache = {h: v for h, v in cache.items() if last_used.get(h, 0.0) >= cutoff}
            last_used = {h: ts for h, ts in last_used.items() if h in cache}
        self._cache = cache
        self._last_used = last_used

    def _save_disk_cache(self, cache_dir: Path) -> None:
        if not self._cache:
            return
        hashes = list(self._cache.keys())
        vecs = list(self._cache.values())
        max_dim = max(int(v.shape[0]) for v in vecs)
        matrix = np.zeros((len(vecs), max_dim), dtype=np.float32)
        for i, v in enumerate(vecs):
            matrix[i, : int(v.shape[0])] = v
        now = time.time()
        last_used_arr = np.array([self._last_used.get(h, now) for h in hashes], dtype=np.float64)
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(
                self._cache_path(cache_dir),
                model=np.array(self.model_name),
                hashes=np.array(hashes),
                matrix=matrix,
                last_used=last_used_arr,
            )
        except OSError:
            log.debug("could not persist embedding cache to %s", cache_dir)

    def _ensure_backend(self) -> EmbeddingBackend:
        if self._backend is None:
            # Heavy import deferred so unit tests with a fake backend never pay
            # the onnxruntime / tokenizers load cost.
            from fastembed import TextEmbedding  # noqa: PLC0415

            kwargs: dict[str, object] = {"model_name": self.model_name}
            if self._model_cache_dir is not None:
                kwargs["cache_dir"] = str(self._model_cache_dir)
            if self._threads is not None:
                kwargs["threads"] = self._threads
            self._backend = cast("EmbeddingBackend", TextEmbedding(**kwargs))  # type: ignore[arg-type]
        return self._backend

    def embed(self, texts: Sequence[str]) -> NDArray[np.float32]:
        """Embed ``texts`` → ``(n, d)`` float32 matrix.

        Stays entirely in memory — call :meth:`save` once at the end of the
        run to persist. Cached per-text by content hash. Empty strings
        short-circuit to zeros. Accessed hashes are recorded for :meth:`save`.

        Returns:
            Float32 matrix of shape ``(len(texts), embedding_dim)``.
        """
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)

        now = time.time()
        resolved: dict[int, NDArray[np.float32]] = {}
        missing_idx: list[int] = []
        missing_text: list[str] = []
        missing_keys: list[str] = []

        for i, text in enumerate(texts):
            if not text.strip():
                continue
            key = _hash(text)
            self._seen.add(key)
            cached = self._cache.get(key)
            if cached is not None:
                self._last_used[key] = now
                resolved[i] = cached
            else:
                missing_idx.append(i)
                missing_text.append(text)
                missing_keys.append(key)

        if missing_text:
            backend = self._ensure_backend()
            raw = list(backend.embed(missing_text))
            for pos, (slot, vec) in enumerate(zip(missing_idx, raw, strict=True)):
                key = missing_keys[pos]
                arr = np.asarray(vec, dtype=np.float32)
                self._cache[key] = arr
                self._last_used[key] = now
                resolved[slot] = arr

        dim = max((int(v.shape[0]) for v in resolved.values()), default=0)
        result = np.zeros((len(texts), dim), dtype=np.float32)
        for i, vec in resolved.items():
            # Pad to current max dim (handles growing-vocab fake backends in tests
            # and any future backend whose dim isn't perfectly constant per batch).
            result[i, : int(vec.shape[0])] = vec
        return result

    def save(self, *, force_cleanup: bool = False) -> int:
        """Persist the in-memory cache to disk.

        This is the single disk-write point. Call once at the end of every run
        so new embeddings survive to the next invocation. Stays in memory until
        then — no incremental writes during the run.

        Args:
            force_cleanup: When ``True`` (pass after ``--all`` scans), entries
                not accessed in this run are removed before writing, keeping
                the cache bounded as the repo evolves. When ``False``, the full
                cache is written as-is (new entries added, nothing removed).

        Returns:
            Number of entries removed (always ``0`` when ``force_cleanup=False``).
        """
        removed = 0
        if force_cleanup:
            stale = [h for h in self._cache if h not in self._seen]
            for h in stale:
                del self._cache[h]
                self._last_used.pop(h, None)
            removed = len(stale)
        if self._cache_dir is not None:
            self._save_disk_cache(self._cache_dir)
        return removed

    @staticmethod
    def cosine(a: NDArray[np.float32], b: NDArray[np.float32]) -> float:
        """Cosine similarity of two 1-D vectors. Returns 0.0 if either is zero.

        Pads the shorter vector with zeros if shapes differ so callers don't have
        to worry about backend-dim drift. Clamps to [-1.0, 1.0] to absorb
        float32 round-off on near-identical vectors.

        Args:
            a: First 1-D float32 vector.
            b: Second 1-D float32 vector.

        Returns:
            Cosine similarity in ``[-1.0, 1.0]``, or ``0.0`` for zero vectors.
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
        if not na or not nb:
            return 0.0
        return float(min(1.0, max(-1.0, np.dot(a, b) / (na * nb))))

    @property
    def cache_size(self) -> int:
        """Number of embeddings currently held in the in-memory cache."""
        return len(self._cache)

    def _embed_locked(self, texts: list[str]) -> NDArray[np.float32]:
        """Embed ``texts`` under the instance lock (thread-safe, blocking).

        Returns:
            Float32 matrix as returned by :meth:`embed`.
        """
        with self._lock:
            return self.embed(texts)

    async def embed_batch(self, texts: Sequence[str]) -> NDArray[np.float32]:
        """Embed ``texts`` in one backend call without blocking the event loop.

        Runs the embedding in a thread-pool worker so concurrent rule tasks can
        keep making progress while ONNX computes.

        Args:
            texts: Strings to embed.

        Returns:
            Float32 matrix of shape ``(len(texts), embedding_dim)``.
        """
        return await asyncio.to_thread(self._embed_locked, list(texts))

    async def warm_up(self) -> None:
        """Load the embedding backend and warm up the ONNX runtime.

        Triggers model download on first call. Safe to call multiple times.
        """
        await asyncio.to_thread(self._embed_locked, ["warm up"])

    async def similarity(self, left: str, right: str) -> float:
        """Cosine similarity between two strings, non-blocking.

        Runs the embedding in a thread-pool worker so the asyncio event loop
        stays free while ONNX computes. Concurrent rule tasks can therefore
        overlap their I/O and light CPU work while ONNX runs in the background.

        Args:
            left: First string.
            right: Second string.

        Returns:
            Cosine similarity in ``[-1.0, 1.0]``, or ``0.0`` if either string is blank.
        """
        if not left.strip() or not right.strip():
            return 0.0
        mat = await asyncio.to_thread(self._embed_locked, [left, right])
        return self.cosine(mat[0], mat[1])
