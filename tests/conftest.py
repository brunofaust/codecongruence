"""Shared test fixtures.

The real ``BAAI/bge-small-en-v1.5`` is ~130 MB and ONNX-heavy; tests use a
deterministic bag-of-words fake backend instead. This keeps the unit/integration
suite fast and offline-friendly while still exercising the cosine math.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from typing import TYPE_CHECKING

import numpy as np
import pytest

from codecongruence.core.embedder import Embedder, EmbeddingBackend

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from pathlib import Path

    from numpy.typing import NDArray

_TOKEN_RE = re.compile(r"[A-Za-z]+")
_STOPWORDS = frozenset({
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "for",
    "is",
    "are",
    "be",
    "was",
    "were",
    "this",
    "that",
    "with",
    "as",
    "by",
    "it",
    "if",
    "from",
    "at",
    "self",
    "def",
    "return",
    "pass",
    "not",
    "no",
    "yes",
})


_GIT_HOOK_VARS = frozenset({
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_PREFIX",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
})


def base_git_env() -> dict[str, str]:
    """Return os.environ prepared for hermetic git use in throwaway repos.

    Strips GIT_DIR / GIT_INDEX_FILE / GIT_WORK_TREE set by the prek hook
    runner so they don't leak into child git repos created during tests, and
    points global/system config at nothing so host-level settings (commit
    signing, hooks, templates) can't break test commits.
    """
    env = {k: v for k, v in os.environ.items() if k not in _GIT_HOOK_VARS}
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text) if t.lower() not in _STOPWORDS]


class BagOfWordsBackend:
    """Deterministic, offline backend used in tests.

    Builds a vocabulary on demand from the documents it sees and emits unit-norm
    bag-of-words vectors. Cosine similarity is therefore exactly the fraction
    of shared (non-stopword) tokens.
    """

    def __init__(self) -> None:
        self._vocab: dict[str, int] = {}
        self.seen_batch_sizes: list[int] = []

    def _embed_one(self, text: str) -> NDArray[np.float32]:
        toks = _tokenize(text)
        for tok in toks:
            if tok not in self._vocab:
                self._vocab[tok] = len(self._vocab)
        vec = np.zeros(max(len(self._vocab), 1), dtype=np.float32)
        for tok in toks:
            vec[self._vocab[tok]] += 1.0
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec

    def embed(self, documents: Sequence[str], batch_size: int = 16) -> list[NDArray[np.float32]]:
        self.seen_batch_sizes.append(batch_size)
        return [self._embed_one(t) for t in documents]


@pytest.fixture
def fake_backend() -> BagOfWordsBackend:
    return BagOfWordsBackend()


@pytest.fixture
def fake_embedder(fake_backend: EmbeddingBackend) -> Embedder:
    return Embedder(model_name="fake", backend=fake_backend)


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Path]:
    """A throwaway git repo for integration / git-helper tests."""
    env = {
        **base_git_env(),
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, env=env, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "README.md").write_text("readme\n")
    git("add", "README.md")
    git("commit", "-q", "-m", "init")
    yield tmp_path


@pytest.fixture
def run_async() -> Iterator[object]:
    """Provide a synchronous bridge so non-asyncio tests can await coroutines."""
    yield asyncio.run
