from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from codecongruence.core.config import RuleConfig
from codecongruence.core.git import ChangedFile
from codecongruence.rules.D005_changelog_exists import DocsOnChangeRule
from tests.conftest import base_git_env

if TYPE_CHECKING:
    from codecongruence.core.embedder import Embedder


def _git(repo: Path, *args: str) -> None:
    env = {
        **base_git_env(),
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", *args], cwd=repo, check=True, env=env, capture_output=True)


def _check_in_repo(repo: Path, changed: list[ChangedFile], fake: Embedder) -> list:
    cfg = RuleConfig(
        threshold=0.0,
        **{
            "trigger_paths": ["src/**"],
            "docs_files": ["CHANGELOG.md"],
        },
    )
    cwd = os.getcwd()
    os.chdir(repo)
    try:
        return asyncio.run(DocsOnChangeRule().check(changed, fake, cfg))
    finally:
        os.chdir(cwd)


def test_no_trigger_no_violation(repo: Path, fake_embedder: Embedder) -> None:
    out = _check_in_repo(
        repo,
        [ChangedFile(path=Path("docs/x.md"), added_ranges=())],
        fake_embedder,
    )
    assert out == []


def test_missing_doc_update_fails(repo: Path, fake_embedder: Embedder) -> None:
    src = repo / "src"
    src.mkdir()
    (src / "a.py").write_text("x = 1\n")
    _git(repo, "add", "src/a.py")

    out = _check_in_repo(
        repo,
        [ChangedFile(path=Path("src/a.py"), added_ranges=())],
        fake_embedder,
    )
    assert len(out) == 1
    assert out[0].rule_id == "docs_on_change"
    assert out[0].code == "D005"


def test_passes_when_doc_changed(repo: Path, fake_embedder: Embedder) -> None:
    src = repo / "src"
    src.mkdir()
    (src / "a.py").write_text("x = 1\n")
    cl = repo / "CHANGELOG.md"
    cl.write_text("# Changelog\n\n## [Unreleased]\n\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "seed")

    # modify code AND update the changelog
    (src / "a.py").write_text("x = 2\n")
    cl.write_text("# Changelog\n\n## [Unreleased]\n- Updated a.py\n")
    _git(repo, "add", ".")

    out = _check_in_repo(
        repo,
        [
            ChangedFile(path=Path("src/a.py"), added_ranges=()),
            ChangedFile(path=Path("CHANGELOG.md"), added_ranges=()),
        ],
        fake_embedder,
    )
    assert out == []


def test_any_doc_file_satisfies_check(repo: Path, fake_embedder: Embedder) -> None:
    """Updating any file from docs_files is sufficient."""
    src = repo / "src"
    src.mkdir()
    (src / "b.py").write_text("y = 1\n")
    readme = repo / "README.md"
    readme.write_text("# Project\n\nInitial.\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "seed")

    (src / "b.py").write_text("y = 2\n")
    readme.write_text("# Project\n\nUpdated.\n")
    _git(repo, "add", ".")

    cfg = RuleConfig(
        threshold=0.0,
        **{
            "trigger_paths": ["src/**"],
            "docs_files": ["CHANGELOG.md", "README.md"],
        },
    )
    cwd = os.getcwd()
    os.chdir(repo)
    try:
        out = asyncio.run(
            DocsOnChangeRule().check(
                [
                    ChangedFile(path=Path("src/b.py"), added_ranges=()),
                    ChangedFile(path=Path("README.md"), added_ranges=()),
                ],
                fake_embedder,
                cfg,
            )
        )
    finally:
        os.chdir(cwd)

    assert out == []
