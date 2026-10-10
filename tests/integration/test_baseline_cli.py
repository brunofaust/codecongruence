"""CLI integration tests for --update-baseline and baseline suppression."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from codecongruence.cli import app
from tests.conftest import base_git_env

if TYPE_CHECKING:
    from typer.testing import Result

_D006_ONLY_TOML = """
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
enabled = false
[rules.params_in_docstring]
enabled = true
[rules.param_name_vs_usage]
enabled = false
""".strip()

_D005_ONLY_TOML = """
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
trigger_paths = ["src/**"]
docs_files = ["CHANGELOG.md"]
[rules.params_in_docstring]
enabled = false
[rules.param_name_vs_usage]
enabled = false
""".strip()


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


@pytest.fixture
def repo_with_d005_violation(tmp_path: Path) -> Path:
    """A git repo with one staged D005 (docs_on_change) violation."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "codecongruence.toml").write_text(_D005_ONLY_TOML)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "seed")

    # Stage a src change without updating CHANGELOG → D005 violation.
    (src / "feature.py").write_text("x = 1\n")
    _git(tmp_path, "add", "src/feature.py")
    return tmp_path


def test_update_baseline_creates_file(repo_with_d005_violation: Path, runner: CliRunner) -> None:
    cwd = os.getcwd()
    os.chdir(repo_with_d005_violation)
    try:
        result = runner.invoke(app, ["--update-baseline"])
    finally:
        os.chdir(cwd)

    assert result.exit_code == 0
    assert (repo_with_d005_violation / ".codecongruence" / ".codecongruence-baseline.json").exists()


def test_update_baseline_exits_zero_even_with_violations(
    repo_with_d005_violation: Path, runner: CliRunner
) -> None:
    cwd = os.getcwd()
    os.chdir(repo_with_d005_violation)
    try:
        result = runner.invoke(app, ["--update-baseline"])
    finally:
        os.chdir(cwd)

    assert result.exit_code == 0


def test_update_baseline_saves_violation_count(
    repo_with_d005_violation: Path, runner: CliRunner
) -> None:
    cwd = os.getcwd()
    os.chdir(repo_with_d005_violation)
    try:
        runner.invoke(app, ["--update-baseline"])
    finally:
        os.chdir(cwd)

    data = json.loads(
        (repo_with_d005_violation / ".codecongruence" / ".codecongruence-baseline.json").read_text()
    )
    assert len(data["violations"]) == 1
    assert data["violations"][0]["rule_id"] == "docs_on_change"


def test_baseline_suppresses_known_violation(
    repo_with_d005_violation: Path, runner: CliRunner
) -> None:
    cwd = os.getcwd()
    os.chdir(repo_with_d005_violation)
    try:
        runner.invoke(app, ["--update-baseline"])
        result = runner.invoke(app, [])
    finally:
        os.chdir(cwd)

    assert result.exit_code == 0


def test_new_violations_still_fail_with_baseline(tmp_path: Path, runner: CliRunner) -> None:
    """A new violation with a different key than the baseline must still fail.

    Uses D006 (params_in_docstring) which reports per-file, per-line keys.
    """
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    src = tmp_path / "src"
    src.mkdir()
    (tmp_path / "codecongruence.toml").write_text(_D006_ONLY_TOML)
    (src / "first.py").write_text("x = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "seed")

    # Stage first.py with a D006 violation (param 'user' missing from docstring).
    (src / "first.py").write_text('def run(user):\n    """Runs."""\n    pass\n')
    _git(tmp_path, "add", "src/first.py")

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        # Baseline first.py violation.
        runner.invoke(app, ["--update-baseline"])

        # Commit, then stage a DIFFERENT file with a NEW D006 violation.
        _git(tmp_path, "commit", "-q", "-m", "v1")
        (src / "second.py").write_text('def compute(x, y):\n    """Computes."""\n    return x\n')
        _git(tmp_path, "add", "src/second.py")

        # The second.py violation has key (params_in_docstring, src/second.py, 1)
        # which is NOT in the baseline → must exit 1.
        result = runner.invoke(app, [])
    finally:
        os.chdir(cwd)

    assert result.exit_code == 1


def test_update_baseline_on_clean_repo_creates_empty_file(
    tmp_path: Path, runner: CliRunner
) -> None:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "README.md").write_text("hi\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "seed")
    (tmp_path / "codecongruence.toml").write_text(_D005_ONLY_TOML)

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(app, ["--update-baseline"])
    finally:
        os.chdir(cwd)

    assert result.exit_code == 0
    data = json.loads((tmp_path / ".codecongruence" / ".codecongruence-baseline.json").read_text())
    assert data["violations"] == []


_FIXED_FIRST = (
    "def run(user: str) -> None:\n"
    '    """Runs.\n\n    Args:\n        user: who.\n    """\n'
    "    pass\n"
)
_BASELINE_REL = Path(".codecongruence") / ".codecongruence-baseline.json"


def _invoke(runner: CliRunner, repo: Path, *args: str) -> Result:
    cwd = os.getcwd()
    os.chdir(repo)
    try:
        return runner.invoke(app, list(args))
    finally:
        os.chdir(cwd)


@pytest.fixture
def baselined_repo(tmp_path: Path, runner: CliRunner) -> Path:
    """Repo whose committed baseline holds one D006 entry for src/first.py:1."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "src").mkdir()
    (tmp_path / "codecongruence.toml").write_text(_D006_ONLY_TOML)
    (tmp_path / "src" / "first.py").write_text("x = 1\n")
    (tmp_path / "src" / "other.py").write_text("y = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "seed")
    (tmp_path / "src" / "first.py").write_text('def run(user):\n    """Runs."""\n    pass\n')
    _git(tmp_path, "add", "src/first.py")
    assert _invoke(runner, tmp_path, "--update-baseline").exit_code == 0
    _git(tmp_path, "commit", "-q", "-m", "v1")
    return tmp_path


def _fix_first(repo: Path) -> None:
    (repo / "src" / "first.py").write_text(_FIXED_FIRST)
    _git(repo, "add", "src/first.py")


def test_stale_entry_for_checked_file_fails_and_is_reported(
    baselined_repo: Path, runner: CliRunner
) -> None:
    _fix_first(baselined_repo)
    result = _invoke(runner, baselined_repo, "--include-unstaged")

    assert result.exit_code == 1
    assert "stale" in result.output.lower()
    assert "params_in_docstring" in result.output
    assert "src/first.py" in result.output
    assert "--prune-baseline" in result.output


def test_entry_for_unchecked_file_is_not_stale(baselined_repo: Path, runner: CliRunner) -> None:
    (baselined_repo / "src" / "other.py").write_text("y = 2\n")
    _git(baselined_repo, "add", "src/other.py")

    result = _invoke(runner, baselined_repo)

    assert result.exit_code == 0
    assert "stale" not in result.output.lower()


def test_entry_of_rule_that_did_not_run_is_not_stale(
    baselined_repo: Path, runner: CliRunner
) -> None:
    path = baselined_repo / _BASELINE_REL
    data = json.loads(path.read_text())
    data["violations"].append({
        "rule_id": "docs_on_change",
        "code": "D005",
        "file_path": "src/first.py",
        "line": 1,
    })
    path.write_text(json.dumps(data))
    _fix_first(baselined_repo)

    result = _invoke(runner, baselined_repo)

    assert "docs_on_change" not in result.output


def test_entry_on_untouched_lines_is_not_stale(baselined_repo: Path, runner: CliRunner) -> None:
    (baselined_repo / "src" / "first.py").write_text(
        'def run(user):\n    """Runs."""\n    pass\n\n\nZ = 1\n'
    )
    _git(baselined_repo, "add", "src/first.py")

    result = _invoke(runner, baselined_repo)

    assert result.exit_code == 0
    assert "stale" not in result.output.lower()


def test_matched_entry_is_not_stale(baselined_repo: Path, runner: CliRunner) -> None:
    (baselined_repo / "src" / "first.py").write_text(
        'def run(user):\n    """Runs it."""\n    pass\n'
    )
    _git(baselined_repo, "add", "src/first.py")

    result = _invoke(runner, baselined_repo)

    assert result.exit_code == 0, result.output
    assert "stale" not in result.output.lower()


def test_prune_baseline_removes_only_stale_entries(baselined_repo: Path, runner: CliRunner) -> None:
    path = baselined_repo / _BASELINE_REL
    data = json.loads(path.read_text())
    keep = {"rule_id": "docs_on_change", "code": "D005", "file_path": "x.md", "line": None}
    data["violations"].append(keep)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    _fix_first(baselined_repo)

    result = _invoke(runner, baselined_repo, "--prune-baseline")

    assert result.exit_code == 0
    assert "pruned 1 " in result.output
    after = json.loads(path.read_text())
    assert after["violations"] == [keep]
    assert after["generated_at"] == data["generated_at"]
    assert _invoke(runner, baselined_repo).exit_code == 0


def test_prune_baseline_exits_nonzero_when_violations_remain(
    baselined_repo: Path, runner: CliRunner
) -> None:
    (baselined_repo / "src" / "other.py").write_text('def go(a):\n    """Go."""\n    pass\n')
    _git(baselined_repo, "add", "src/other.py")

    result = _invoke(runner, baselined_repo, "--prune-baseline")

    assert result.exit_code == 1


def test_json_output_contains_stale_key(baselined_repo: Path, runner: CliRunner) -> None:
    _fix_first(baselined_repo)
    result = _invoke(runner, baselined_repo, "--format", "json")

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["stale_baseline_entries"] == [
        {
            "rule_id": "params_in_docstring",
            "file_path": "src/first.py",
            "line": 1,
            "message": payload["stale_baseline_entries"][0]["message"],
        }
    ]


def test_update_and_prune_baseline_are_mutually_exclusive(
    baselined_repo: Path, runner: CliRunner
) -> None:
    result = _invoke(runner, baselined_repo, "--update-baseline", "--prune-baseline")

    assert result.exit_code == 2
