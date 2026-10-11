"""CLI integration tests for the three scope modes: staged diff, ``--all``, explicit files."""

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
[rules.duplicate_functions]
enabled = false
""".strip()

# D006 fires on line 1: param ``user`` is missing from the docstring.
_VIOLATING = 'def run(user):\n    """Runs."""\n    pass\n'
_CLEAN = 'def run():\n    """Runs."""\n    pass\n'
_BASELINE_REL = Path(".codecongruence") / ".codecongruence-baseline.json"


def _git(repo: Path, *args: str) -> None:
    env = {
        **base_git_env(),
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", *args], cwd=repo, check=True, env=env, capture_output=True)


def _invoke(repo: Path, *args: str, cwd: Path | None = None) -> Result:
    previous = os.getcwd()
    os.chdir(cwd or repo)
    try:
        return CliRunner().invoke(app, list(args))
    finally:
        os.chdir(previous)


@pytest.fixture
def scoped_repo(tmp_path: Path) -> Path:
    """Repo with a committed violation in ``src/old.py`` and a staged one in ``src/new.py``."""
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "src").mkdir()
    (tmp_path / "codecongruence.toml").write_text(_D006_ONLY_TOML)
    (tmp_path / "src" / "old.py").write_text(_VIOLATING)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "seed")
    (tmp_path / "src" / "new.py").write_text(_VIOLATING)
    _git(tmp_path, "add", "src/new.py")
    return tmp_path


def test_no_args_checks_only_the_staged_diff(scoped_repo: Path) -> None:
    result = _invoke(scoped_repo)

    assert result.exit_code == 1, result.output
    assert "src/new.py" in result.output
    assert "src/old.py" not in result.output


def test_all_checks_every_file(scoped_repo: Path) -> None:
    result = _invoke(scoped_repo, "--all")

    assert result.exit_code == 1, result.output
    assert "src/new.py" in result.output
    assert "src/old.py" in result.output


def test_explicit_files_check_exactly_those_files_whole_file(scoped_repo: Path) -> None:
    result = _invoke(scoped_repo, "src/old.py")

    assert result.exit_code == 1, result.output
    assert "src/old.py" in result.output
    assert "src/new.py" not in result.output


def test_explicit_clean_file_passes_even_with_staged_violations(scoped_repo: Path) -> None:
    (scoped_repo / "src" / "clean.py").write_text(_CLEAN)

    result = _invoke(scoped_repo, "src/clean.py")

    assert result.exit_code == 0, result.output


def test_explicit_files_resolve_relative_to_invocation_dir_and_absolute(
    scoped_repo: Path,
) -> None:
    from_subdir = _invoke(scoped_repo, "old.py", cwd=scoped_repo / "src")
    absolute = _invoke(scoped_repo, str(scoped_repo / "src" / "old.py"))

    for result in (from_subdir, absolute):
        assert result.exit_code == 1, result.output
        assert "src/old.py" in result.output
        assert "src/new.py" not in result.output


@pytest.mark.parametrize(
    "args",
    [
        ("--format", "json", "src/old.py"),
        ("src/old.py", "--format", "json"),
        ("-r", "D006", "src/old.py", "-f", "json"),
    ],
)
def test_options_before_or_after_files(scoped_repo: Path, args: tuple[str, ...]) -> None:
    result = _invoke(scoped_repo, *args)

    assert result.exit_code == 1, result.output
    payload = json.loads(result.stdout)
    assert {v["file_path"] for v in payload["violations"]} == {"src/old.py"}


def test_nonexistent_and_deleted_files_are_ignored(scoped_repo: Path) -> None:
    (scoped_repo / "src" / "old.py").unlink()

    result = _invoke(scoped_repo, "src/old.py", "does/not/exist.py", "src")

    assert result.exit_code == 0, result.output
    assert "Traceback" not in result.output


def test_files_with_all_is_rejected(scoped_repo: Path) -> None:
    result = _invoke(scoped_repo, "--all", "src/old.py")

    assert result.exit_code == 2
    assert "--all" in result.output
    assert "ambiguous" in result.output


@pytest.mark.parametrize("flag", ["--include-unstaged", "--update-baseline"])
def test_files_with_git_scope_or_baseline_rewrite_flag_is_rejected(
    scoped_repo: Path, flag: str
) -> None:
    result = _invoke(scoped_repo, flag, "src/old.py")

    assert result.exit_code == 2
    assert flag in result.output
    assert not (scoped_repo / _BASELINE_REL).exists()


def test_init_subcommand_still_dispatches(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q", "-b", "main")
    target = tmp_path / "cfg.toml"

    result = _invoke(tmp_path, "init", "--no-download", "--path", str(target))

    assert result.exit_code == 0, result.output
    assert target.exists()


@pytest.fixture
def two_file_baseline(scoped_repo: Path) -> Path:
    """Baseline holding resolved entries for both files: every entry is stale if judged."""
    assert _invoke(scoped_repo, "--update-baseline", "--all").exit_code == 0
    entries = json.loads((scoped_repo / _BASELINE_REL).read_text())["violations"]
    assert {e["file_path"] for e in entries} == {"src/old.py", "src/new.py"}
    (scoped_repo / "src" / "old.py").write_text(_CLEAN)
    (scoped_repo / "src" / "new.py").write_text(_CLEAN)
    return scoped_repo


def test_staleness_is_scoped_to_the_explicit_files(two_file_baseline: Path) -> None:
    result = _invoke(two_file_baseline, "src/old.py")

    assert result.exit_code == 1, result.output
    assert "stale baseline entry: params_in_docstring src/old.py:1" in result.output
    assert "src/new.py" not in result.output


def test_prune_with_explicit_files_keeps_other_files_entries(two_file_baseline: Path) -> None:
    result = _invoke(two_file_baseline, "--prune-baseline", "src/old.py")

    assert result.exit_code == 0, result.output
    entries = json.loads((two_file_baseline / _BASELINE_REL).read_text())["violations"]
    assert [e["file_path"] for e in entries] == ["src/new.py"]
