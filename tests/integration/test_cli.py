"""CLI smoke tests via typer's ``CliRunner``."""

from __future__ import annotations

import json
import os
import subprocess
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from codecongruence.cli import app

if TYPE_CHECKING:
    from pathlib import Path


def _git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", *args], cwd=repo, check=True, env=env, capture_output=True)


@pytest.fixture
def runner() -> CliRunner:
    # Force deterministic terminal width and no ANSI codes so help-text
    # assertions work the same in CI (no TTY, unknown COLUMNS) and locally.
    return CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1"})


def test_version_prints_and_exits_zero(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "codecongruence" in result.stdout


def test_help_lists_init_subcommand(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "--config" in result.stdout


def test_init_writes_default_config(tmp_path: Path, runner: CliRunner) -> None:
    target = tmp_path / "codecongruence.toml"
    result = runner.invoke(app, ["init", "--path", str(target)])
    assert result.exit_code == 0
    assert target.exists()
    body = target.read_text()
    assert "[codecongruence]" in body
    assert "docstring_vs_body" in body


def test_init_refuses_to_overwrite_without_force(tmp_path: Path, runner: CliRunner) -> None:
    target = tmp_path / "codecongruence.toml"
    target.write_text("pre-existing\n")
    result = runner.invoke(app, ["init", "--path", str(target)])
    assert result.exit_code == 1
    assert target.read_text() == "pre-existing\n"


def test_json_format_in_clean_repo(tmp_path: Path, runner: CliRunner) -> None:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "README.md").write_text("hi\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "seed")

    # Disable all embedding rules so we don't load the real model.
    (tmp_path / "codecongruence.toml").write_text(
        """
[codecongruence]
parallel = false

[rules.docstring_vs_body]
enabled = false
[rules.name_vs_body]
enabled = false
[rules.claude_md_vs_diff]
enabled = false
[rules.pr_description_vs_diff]
enabled = false
[rules.stale_comments]
enabled = false
[rules.docs_on_change]
enabled = true
        """.strip()
    )

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(app, ["--format", "json"])
    finally:
        os.chdir(cwd)

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["violations"] == []
    assert "docs_on_change" in payload["rules_run"]
