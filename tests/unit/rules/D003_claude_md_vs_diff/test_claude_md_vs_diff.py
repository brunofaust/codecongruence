from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from codecongruence.core.config import RuleConfig
from codecongruence.core.git import ChangedFile
from codecongruence.rules.D003_claude_md_vs_diff import ClaudeMdVsDiffRule

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


def _seed_repo(repo: Path) -> None:
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "README.md").write_text("seed\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "seed")


def _run(repo: Path, changed: list[ChangedFile], emb: Embedder, *, threshold: float = 0.20):
    cfg = RuleConfig(
        threshold=threshold,
        code_paths=["src/**"],
        docs_files=["CLAUDE.md"],
    )
    cwd = os.getcwd()
    os.chdir(repo)
    try:
        return asyncio.run(ClaudeMdVsDiffRule().check(changed, emb, cfg))
    finally:
        os.chdir(cwd)


def test_skipped_when_no_code_change(tmp_path: Path, fake_embedder: Embedder) -> None:
    _seed_repo(tmp_path)
    out = _run(tmp_path, [ChangedFile(path=Path("CLAUDE.md"), added_ranges=())], fake_embedder)
    assert out == []


def test_skipped_when_no_doc_change(tmp_path: Path, fake_embedder: Embedder) -> None:
    _seed_repo(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    _git(tmp_path, "add", "src/a.py")
    out = _run(tmp_path, [ChangedFile(path=Path("src/a.py"), added_ranges=())], fake_embedder)
    assert out == []


def test_flags_unrelated_doc_tweak(tmp_path: Path, fake_embedder: Embedder) -> None:
    _seed_repo(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("# project\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "seed2")

    # Big unrelated code change vs. a one-liner tweak in the docs.
    (tmp_path / "src" / "a.py").write_text(
        "def queue_invoice(transport, recipient):\n"
        "    payload = {'subject': 'invoice', 'recipient': recipient}\n"
        "    transport.deliver(payload)\n"
        "    return payload\n"
    )
    (tmp_path / "CLAUDE.md").write_text("# project\nbumped\n")
    _git(tmp_path, "add", ".")

    out = _run(
        tmp_path,
        [
            ChangedFile(path=Path("src/a.py"), added_ranges=()),
            ChangedFile(path=Path("CLAUDE.md"), added_ranges=()),
        ],
        fake_embedder,
        threshold=0.30,
    )
    assert len(out) == 1
    assert out[0].code == "D003"
    assert out[0].rule_id == "claude_md_vs_diff"


def test_passes_aligned_doc_change(tmp_path: Path, fake_embedder: Embedder) -> None:
    _seed_repo(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("# project\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("# initial\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "seed2")

    # Both diffs talk about invoice delivery -> high overlap on tokens.
    (tmp_path / "src" / "a.py").write_text(
        "def queue_invoice(transport, recipient):\n"
        "    payload = {'subject': 'invoice', 'recipient': recipient}\n"
        "    transport.deliver(payload)\n"
        "    return payload\n"
    )
    (tmp_path / "CLAUDE.md").write_text(
        "# project\n\n"
        "## Invoice delivery\n"
        "Queue invoice payloads via transport.deliver to recipient.\n"
    )
    _git(tmp_path, "add", ".")

    out = _run(
        tmp_path,
        [
            ChangedFile(path=Path("src/a.py"), added_ranges=()),
            ChangedFile(path=Path("CLAUDE.md"), added_ranges=()),
        ],
        fake_embedder,
        threshold=0.05,
    )
    assert out == []
