"""Unit tests for core.ai_context — AI-tool context file generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from codecongruence.core.ai_context import write_ai_context_files


def test_returns_three_entries(tmp_path: Path) -> None:
    result = write_ai_context_files(tmp_path)
    assert len(result) == 3


def test_all_written_on_fresh_dir(tmp_path: Path) -> None:
    result = write_ai_context_files(tmp_path)
    assert all(written for _, written in result)


def test_claude_skill_path(tmp_path: Path) -> None:
    result = write_ai_context_files(tmp_path)
    paths = [p for p, _ in result]
    assert any(str(p).endswith(".claude/skills/codecongruence/SKILL.md") for p in paths)


def test_cursor_rule_path(tmp_path: Path) -> None:
    result = write_ai_context_files(tmp_path)
    paths = [p for p, _ in result]
    assert any(str(p).endswith(".cursor/rules/codecongruence.mdc") for p in paths)


def test_agents_md_path(tmp_path: Path) -> None:
    result = write_ai_context_files(tmp_path)
    paths = [p for p, _ in result]
    assert any(p.name == "AGENTS.md" for p in paths)


def test_files_exist_on_disk(tmp_path: Path) -> None:
    result = write_ai_context_files(tmp_path)
    for path, _ in result:
        assert path.exists(), f"{path} was not created"


def test_idempotent_no_force(tmp_path: Path) -> None:
    write_ai_context_files(tmp_path)
    result2 = write_ai_context_files(tmp_path)
    assert all(not written for _, written in result2)


def test_force_overwrites(tmp_path: Path) -> None:
    write_ai_context_files(tmp_path)
    result2 = write_ai_context_files(tmp_path, force=True)
    assert all(written for _, written in result2)


def test_parent_dirs_created(tmp_path: Path) -> None:
    write_ai_context_files(tmp_path)
    assert (tmp_path / ".claude" / "skills" / "codecongruence").is_dir()
    assert (tmp_path / ".cursor" / "rules").is_dir()


def test_claude_skill_has_frontmatter(tmp_path: Path) -> None:
    write_ai_context_files(tmp_path)
    content = (tmp_path / ".claude" / "skills" / "codecongruence" / "SKILL.md").read_text()
    assert content.startswith("---")
    assert "name: codecongruence" in content


def test_cursor_rule_has_frontmatter(tmp_path: Path) -> None:
    write_ai_context_files(tmp_path)
    content = (tmp_path / ".cursor" / "rules" / "codecongruence.mdc").read_text()
    assert content.startswith("---")
    assert "globs:" in content


def test_agents_md_created_when_absent(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    assert not agents.exists()
    write_ai_context_files(tmp_path)
    assert agents.exists()


def test_agents_md_appended_to_existing(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Existing\n\nSome content.\n")
    write_ai_context_files(tmp_path)
    content = agents.read_text()
    assert "# Existing" in content
    assert "## codecongruence" in content


def test_agents_md_not_duplicated(tmp_path: Path) -> None:
    write_ai_context_files(tmp_path)
    write_ai_context_files(tmp_path)
    content = (tmp_path / "AGENTS.md").read_text()
    assert content.count("## codecongruence") == 1


def test_agents_md_force_replaces_section(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("## codecongruence\n\nDEADBEEF_REPLACED_CONTENT\n")
    write_ai_context_files(tmp_path, force=True)
    content = (tmp_path / "AGENTS.md").read_text()
    assert "DEADBEEF_REPLACED_CONTENT" not in content


@pytest.mark.parametrize(
    "code",
    ["C001", "C002", "C003", "D001", "D002", "D003", "D004", "D005", "D006"],
)
def test_rule_codes_in_all_files(tmp_path: Path, code: str) -> None:
    write_ai_context_files(tmp_path)
    files_to_check = [
        tmp_path / ".claude" / "skills" / "codecongruence" / "SKILL.md",
        tmp_path / ".cursor" / "rules" / "codecongruence.mdc",
        tmp_path / "AGENTS.md",
    ]
    for fpath in files_to_check:
        content = fpath.read_text()
        assert code in content, f"{code} missing from {fpath.name}"
