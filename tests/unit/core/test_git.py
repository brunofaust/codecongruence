from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from codecongruence.core.git import (
    current_repo_root,
    staged_changed_files,
    staged_changed_line_ranges,
)
from tests.conftest import base_git_env


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env=base_git_env(),
    )


def test_no_git_returns_cwd(tmp_path: Path) -> None:
    out = asyncio.run(current_repo_root(cwd=tmp_path))
    # rev-parse fails when not in a git repo → falls back to cwd
    assert out == tmp_path


def test_staged_files_and_ranges(repo: Path) -> None:
    target = repo / "module.py"
    target.write_text("def a():\n    return 1\n\ndef b():\n    return 2\n")
    _git(repo, "add", "module.py")

    files = asyncio.run(staged_changed_files(cwd=repo))
    assert Path("module.py") in files

    ranges = asyncio.run(staged_changed_line_ranges([Path("module.py")], cwd=repo))
    assert Path("module.py") in ranges
    assert ranges[Path("module.py")]  # at least one hunk
