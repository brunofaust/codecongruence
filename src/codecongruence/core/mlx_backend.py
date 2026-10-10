"""MLX (Apple GPU) implementation of the ``EmbeddingBackend`` protocol.

``mlx`` and ``mlx_embeddings`` are imported lazily in ``__init__`` through
:func:`importlib.import_module`, so merely importing this module is safe on
Linux. Pooling matches the CLS-pooled bge family: first token of the last
hidden state, then L2 normalisation — the same vectors fastembed emits.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import numpy as np

from codecongruence.core.backend import MAX_SEQUENCE_LENGTH
from codecongruence.core.config import DEFAULT_EMBED_BATCH_SIZE

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from numpy.typing import NDArray

__all__ = ["MlxEmbeddingBackend"]


class MlxEmbeddingBackend:
    """Embed documents on the Apple GPU with an MLX port of the model."""

    def __init__(self, repo: str) -> None:
        """Load the MLX model and tokenizer for ``repo`` (downloads on first use).

        Args:
            repo: Hugging Face repo id of the MLX weights.
        """
        self._mx = importlib.import_module("mlx.core")
        loader = importlib.import_module("mlx_embeddings.utils").load
        self._model, self._tokenizer = loader(repo)

    def embed(
        self, documents: Sequence[str], batch_size: int = DEFAULT_EMBED_BATCH_SIZE
    ) -> Iterator[NDArray[np.float32]]:
        """Embed ``documents`` into L2-normalised float32 vectors, in order.

        Args:
            documents: Texts to embed.
            batch_size: Maximum documents per forward pass.

        Yields:
            One ``(dim,)`` float32 vector per document.
        """
        for start in range(0, len(documents), batch_size):
            yield from self._embed_batch(list(documents[start : start + batch_size]))

    def _embed_batch(self, texts: list[str]) -> NDArray[np.float32]:
        mx = self._mx
        enc = self._tokenizer(
            texts,
            return_tensors="mlx",
            padding=True,
            truncation=True,
            max_length=MAX_SEQUENCE_LENGTH,
        )
        hidden = self._model(enc["input_ids"], attention_mask=enc["attention_mask"])
        cls = hidden.last_hidden_state[:, 0, :].astype(mx.float32)
        normed = cls / mx.maximum(mx.linalg.norm(cls, axis=-1, keepdims=True), 1e-12)
        mx.eval(normed)
        return np.array(normed, dtype=np.float32)
