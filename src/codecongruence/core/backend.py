"""Embedding backend selection: ONNX (fastembed) or MLX (Apple GPU).

Single owner of the model → MLX repo table and of the ``auto`` / ``mlx`` /
``onnx`` resolution rules. Nothing here imports ``mlx`` — detection uses
:func:`importlib.util.find_spec`, so Linux and ONNX-only runs never pay for it.
"""

from __future__ import annotations

import importlib.util
import platform
import sys
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from codecongruence.core.config import BackendRequest

__all__ = [
    "MAX_SEQUENCE_LENGTH",
    "MLX_MODEL_MAP",
    "BackendKind",
    "BackendUnavailableError",
    "ResolvedBackend",
    "is_apple_silicon",
    "mlx_installed",
    "resolve_backend",
    "unmet_mlx_requirements",
]

type BackendKind = Literal["mlx", "onnx"]

# fastembed truncates bge-small inputs at the model's 512-token position limit.
MAX_SEQUENCE_LENGTH = 512

# Add an entry per supported model: fastembed model id -> MLX repo whose
# weights are the same checkpoint. Only the CLS-pooled BERT family is wired in
# ``mlx_backend``, so a mapped model must pool the same way as bge-small.
MLX_MODEL_MAP: MappingProxyType[str, str] = MappingProxyType({
    "BAAI/bge-small-en-v1.5": "mlx-community/bge-small-en-v1.5-bf16",
})


class BackendUnavailableError(RuntimeError):
    """An explicitly requested backend cannot run on this machine or model."""


@dataclass(frozen=True, slots=True)
class ResolvedBackend:
    """The backend a run will use and why."""

    kind: BackendKind
    mlx_repo: str | None = None
    reason: str | None = None

    def describe(self) -> str:
        """Return the one-line summary printed once per run.

        Returns:
            ``mlx`` / ``onnx``, with the fallback reason when ``auto`` fell back.
        """
        return self.kind if self.reason is None else f"{self.kind} ({self.reason})"


ONNX = ResolvedBackend(kind="onnx")


def is_apple_silicon() -> bool:
    """Return whether this interpreter runs on macOS arm64 (MLX's only target)."""
    return sys.platform == "darwin" and platform.machine() == "arm64"


def mlx_installed() -> bool:
    """Return whether both ``mlx`` and ``mlx_embeddings`` can be imported."""
    return all(importlib.util.find_spec(name) is not None for name in ("mlx", "mlx_embeddings"))


def unmet_mlx_requirements(model: str) -> list[str]:
    """List why MLX cannot embed ``model`` here; empty when it can.

    Args:
        model: The configured embedding model id.

    Returns:
        Human-readable reasons, one per unmet requirement.
    """
    reasons: list[str] = []
    if not is_apple_silicon():
        reasons.append("MLX needs macOS on Apple Silicon (darwin arm64)")
    if not mlx_installed():
        reasons.append("mlx / mlx-embeddings are not installed (pip install 'codecongruence[mlx]')")
    if model not in MLX_MODEL_MAP:
        reasons.append(
            f"model {model!r} has no MLX mapping (add it to MLX_MODEL_MAP in "
            "codecongruence/core/backend.py)"
        )
    return reasons


def resolve_backend(requested: BackendRequest, model: str) -> ResolvedBackend:
    """Pick the embedding backend for ``model``.

    ``onnx`` is always satisfiable. ``auto`` takes MLX when every requirement
    is met and otherwise falls back to ONNX, recording the reason. An explicit
    ``mlx`` never falls back silently.

    Args:
        requested: ``auto``, ``mlx`` or ``onnx``.
        model: The configured embedding model id.

    Returns:
        The resolved backend, carrying the MLX repo when MLX was chosen.

    Raises:
        BackendUnavailableError: ``mlx`` was requested but cannot be satisfied.
    """
    if requested == "onnx":
        return ONNX
    reasons = unmet_mlx_requirements(model)
    if not reasons:
        return ResolvedBackend(kind="mlx", mlx_repo=MLX_MODEL_MAP[model])
    if requested == "mlx":
        msg = "backend 'mlx' was requested but is unavailable: " + "; ".join(reasons)
        raise BackendUnavailableError(msg)
    return ResolvedBackend(kind="onnx", reason="auto: " + "; ".join(reasons))
