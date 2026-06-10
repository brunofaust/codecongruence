"""End-to-end integration: planted violations in a real git repo."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from codecongruence.core.config import load_config
from codecongruence.core.runner import RuleRunner
from tests.conftest import base_git_env

if TYPE_CHECKING:
    from collections.abc import Iterator

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


@pytest.fixture
def staged_repo(tmp_path: Path) -> Iterator[Path]:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")

    (tmp_path / "codecongruence.toml").write_text(
        """
[codecongruence]
parallel = false

[rules.docstring_vs_body]
enabled = true
threshold = 0.30

[rules.name_vs_body]
enabled = true
threshold = 0.25

[rules.claude_md_vs_diff]
enabled = false

[rules.pr_description_vs_diff]
enabled = false

[rules.stale_comments]
enabled = true
threshold = 0.20

[rules.docs_on_change]
enabled = true
trigger_paths = ["src/**"]
docs_files = ["CHANGELOG.md"]
        """.strip()
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "good.py").write_text("def main():\n    return 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "seed")

    # Plant violations
    (src / "bad.py").write_text(
        '''
def send_invoice_email(to):
    """Compute the n-th Fibonacci number recursively using memoisation."""
    payload = {"recipient": to, "subject": "invoice"}
    transport.deliver(payload)
    log.info("sent invoice")
    return payload
'''
    )
    _git(tmp_path, "add", "src/bad.py")
    yield tmp_path


def test_full_run_flags_planted_violations(
    staged_repo: Path,
    fake_embedder: Embedder,
) -> None:
    cfg = load_config(repo_root=staged_repo)
    runner = RuleRunner(cfg, fake_embedder)

    cwd = os.getcwd()
    os.chdir(staged_repo)
    try:
        result = asyncio.run(runner.run())
    finally:
        os.chdir(cwd)

    assert not result.ok, f"expected planted violation, got: {result.violations}"
    rule_ids = {v.rule_id for v in result.violations}
    # docstring_vs_body must fire on bad.py
    assert "docstring_vs_body" in rule_ids
    # docs_on_change fires because we touched src/ but did not bump CHANGELOG
    assert "docs_on_change" in rule_ids


def test_library_run_from_foreign_cwd(
    staged_repo: Path,
    fake_embedder: Embedder,
) -> None:
    """RuleRunner must not depend on the process cwd being the repo root."""
    cfg = load_config(repo_root=staged_repo)
    runner = RuleRunner(cfg, fake_embedder)

    # Deliberately do NOT chdir into staged_repo: paths come from config.repo_root.
    result = asyncio.run(runner.run())

    assert not result.ok, f"expected planted violation, got: {result.violations}"
    rule_ids = {v.rule_id for v in result.violations}
    assert "docstring_vs_body" in rule_ids
    assert "docs_on_change" in rule_ids
    # Reported paths stay repo-relative so baselines are machine-independent.
    assert all(not Path(v.file_path).is_absolute() for v in result.violations)


def test_clean_repo_passes(tmp_path: Path, fake_embedder: Embedder) -> None:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "README.md").write_text("readme\n")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-q", "-m", "init")

    cfg = load_config(repo_root=tmp_path)
    runner = RuleRunner(cfg, fake_embedder)
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = asyncio.run(runner.run())
    finally:
        os.chdir(cwd)
    assert result.ok
    assert result.violations == ()
