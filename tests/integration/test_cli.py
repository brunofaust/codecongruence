"""CLI smoke tests via typer's ``CliRunner``."""

from __future__ import annotations

import json
import os
import re
import subprocess
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from codecongruence import __version__, cli
from codecongruence import version as version_module
from codecongruence.cli import app
from tests.conftest import base_git_env

if TYPE_CHECKING:
    from pathlib import Path


# Rich may force-color in CI (FORCE_COLOR) and split tokens like "--config"
# across ANSI segments; strip escapes before asserting on help text.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


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
def runner() -> CliRunner:
    return CliRunner()


def test_version_prints_and_exits_zero(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout == f"codecongruence {distribution_version('codecongruence')}\n"


def test_package_version_matches_installed_distribution_metadata() -> None:
    assert __version__ == distribution_version("codecongruence")


def test_version_degrades_when_distribution_metadata_is_unavailable(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "resolve_version", lambda: "unavailable")
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout == "codecongruence unavailable\n"


def test_resolve_version_degrades_when_distribution_metadata_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_package_not_found(_: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(version_module, "distribution_version", raise_package_not_found)
    assert version_module.resolve_version() == "unavailable"


def test_help_lists_init_subcommand(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "200")
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    plain = _ANSI_RE.sub("", result.stdout)
    assert "init" in plain
    assert "--config" in plain


def test_init_writes_default_config(tmp_path: Path, runner: CliRunner) -> None:
    target = tmp_path / "codecongruence.toml"
    result = runner.invoke(app, ["init", "--path", str(target), "--no-download"])
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


def test_unknown_rule_id_exits_2(tmp_path: Path, runner: CliRunner) -> None:
    """A typo in --rule must not silently select zero rules and pass."""
    _git(tmp_path, "init", "-q", "-b", "main")
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(app, ["--rule", "docstring_vs_bdy"])
    finally:
        os.chdir(cwd)
    assert result.exit_code == 2


def test_run_from_subdirectory_finds_files(tmp_path: Path, runner: CliRunner) -> None:
    """The CLI anchors at the repo root, so staged files are found from any subdir."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "codecongruence.toml").write_text(
        """
[codecongruence]
parallel = false

[rules.docstring_vs_body]
enabled = false
[rules.name_vs_body]
enabled = false
[rules.param_name_vs_usage]
enabled = false
[rules.duplicate_functions]
enabled = false
[rules.params_in_docstring]
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
    src = tmp_path / "src"
    src.mkdir()
    (src / "seed.py").write_text("X = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "seed")

    # Stage a src/ change without a doc update → docs_on_change must fire,
    # even when the CLI is invoked from a subdirectory.
    (src / "seed.py").write_text("X = 2\n")
    _git(tmp_path, "add", "src/seed.py")

    cwd = os.getcwd()
    os.chdir(src)
    try:
        result = runner.invoke(app, ["--format", "json"])
    finally:
        os.chdir(cwd)

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(v["rule_id"] == "docs_on_change" for v in payload["violations"])


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
