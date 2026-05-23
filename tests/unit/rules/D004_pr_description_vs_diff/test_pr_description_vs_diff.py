from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from codecongruence.core.config import RuleConfig
from codecongruence.core.git import ChangedFile
from codecongruence.rules.D004_pr_description_vs_diff import PrDescriptionVsDiffRule

if TYPE_CHECKING:
    from codecongruence.core.embedder import Embedder


def _git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", *args], cwd=repo, check=True, env=env, capture_output=True)


def _seed_with_staged_change(repo: Path) -> None:
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "a.py").write_text("# seed\n")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-q", "-m", "seed")

    # Staged change with a clear semantic theme (invoice delivery).
    (repo / "a.py").write_text(
        "def queue_invoice(transport, recipient):\n"
        "    payload = {'subject': 'invoice', 'recipient': recipient}\n"
        "    transport.deliver(payload)\n"
        "    return payload\n"
    )
    _git(repo, "add", "a.py")


def _run(repo: Path, fake: Embedder, body: str | None, *, threshold: float = 0.10):
    cwd = os.getcwd()
    if body is None:
        os.environ.pop("CODECONGRUENCE_PR_BODY", None)
    else:
        os.environ["CODECONGRUENCE_PR_BODY"] = body
    os.chdir(repo)
    try:
        cfg = RuleConfig(threshold=threshold)
        return asyncio.run(
            PrDescriptionVsDiffRule().check(
                [ChangedFile(path=Path("a.py"), added_ranges=())], fake, cfg
            )
        )
    finally:
        os.chdir(cwd)


@pytest.fixture(autouse=True)
def _cleanup_env():
    yield
    os.environ.pop("CODECONGRUENCE_PR_BODY", None)


def test_no_env_var_short_circuits(tmp_path: Path, fake_embedder: Embedder) -> None:
    _seed_with_staged_change(tmp_path)
    assert _run(tmp_path, fake_embedder, body=None) == []


def test_flags_lazy_description(tmp_path: Path, fake_embedder: Embedder) -> None:
    _seed_with_staged_change(tmp_path)
    out = _run(tmp_path, fake_embedder, body="fix bug")
    assert len(out) == 1
    assert out[0].code == "D004"
    assert out[0].rule_id == "pr_description_vs_diff"


def test_passes_aligned_description(tmp_path: Path, fake_embedder: Embedder) -> None:
    _seed_with_staged_change(tmp_path)
    out = _run(
        tmp_path,
        fake_embedder,
        body=(
            "Queue invoice payloads via transport.deliver to recipient. "
            "Adds queue_invoice helper to a.py."
        ),
        threshold=0.05,
    )
    assert out == []
