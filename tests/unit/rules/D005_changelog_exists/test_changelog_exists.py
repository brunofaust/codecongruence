from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from codecongruence.core.config import RuleConfig
from codecongruence.core.git import ChangedFile
from codecongruence.rules.D005_changelog_exists import ChangelogExistsRule

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


def _check_in_repo(repo: Path, changed: list[ChangedFile], fake: Embedder, *, changelog: bool):
    cfg = RuleConfig(
        threshold=0.0,
        **{
            "trigger_paths": ["src/**"],
            "changelog_path": "CHANGELOG.md",
            "unreleased_header": "## [Unreleased]",
        },
    )
    cwd = os.getcwd()
    os.chdir(repo)
    try:
        return asyncio.run(ChangelogExistsRule().check(changed, fake, cfg))
    finally:
        os.chdir(cwd)


def test_no_trigger_no_violation(repo: Path, fake_embedder: Embedder) -> None:
    out = _check_in_repo(
        repo,
        [ChangedFile(path=Path("docs/x.md"), added_ranges=())],
        fake_embedder,
        changelog=False,
    )
    assert out == []


def test_missing_changelog_fails(repo: Path, fake_embedder: Embedder) -> None:
    src = repo / "src"
    src.mkdir()
    (src / "a.py").write_text("x = 1\n")
    _git(repo, "add", "src/a.py")

    out = _check_in_repo(
        repo,
        [ChangedFile(path=Path("src/a.py"), added_ranges=())],
        fake_embedder,
        changelog=False,
    )
    assert len(out) == 1
    assert out[0].rule_id == "changelog_exists"


def test_passes_with_new_bullet_under_unreleased(repo: Path, fake_embedder: Embedder) -> None:
    src = repo / "src"
    src.mkdir()
    (src / "a.py").write_text("x = 1\n")
    cl = repo / "CHANGELOG.md"
    cl.write_text("# Changelog\n\n## [Unreleased]\n\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "seed")

    # modify code AND add a bullet under [Unreleased]
    (src / "a.py").write_text("x = 2\n")
    cl.write_text("# Changelog\n\n## [Unreleased]\n- Tweaked a.py\n")
    _git(repo, "add", ".")

    out = _check_in_repo(
        repo,
        [
            ChangedFile(path=Path("src/a.py"), added_ranges=()),
            ChangedFile(path=Path("CHANGELOG.md"), added_ranges=()),
        ],
        fake_embedder,
        changelog=True,
    )
    assert out == []
