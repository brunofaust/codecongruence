"""Unit tests for the baseline violation-suppression module."""

from __future__ import annotations

import json
from pathlib import Path

from codecongruence.core.baseline import (
    Baseline,
    BaselineEntry,
    apply_baseline,
    baseline_path,
    load_baseline,
    save_baseline,
)
from codecongruence.core.runner import RunResult
from codecongruence.rules.base import RuleViolation


def _violation(
    rule_id: str = "name_vs_body",
    code: str = "C001",
    file_path: str = "src/foo.py",
    line: int | None = 10,
    message: str = "drift",
    similarity: float = 0.1,
    threshold: float = 0.25,
) -> RuleViolation:
    return RuleViolation(
        rule_id=rule_id,
        code=code,
        file_path=file_path,
        line=line,
        message=message,
        similarity=similarity,
        threshold=threshold,
    )


def _result(*violations: RuleViolation) -> RunResult:
    return RunResult(
        violations=violations,
        files_checked=(),
        rules_run=(),
    )


# ── BaselineEntry ────────────────────────────────────────────────────────────


def test_baseline_entry_equality() -> None:
    a = BaselineEntry(rule_id="c001", file_path="f.py", line=1)
    b = BaselineEntry(rule_id="c001", file_path="f.py", line=1)
    assert a == b


def test_baseline_entry_inequality_on_line() -> None:
    a = BaselineEntry(rule_id="c001", file_path="f.py", line=1)
    b = BaselineEntry(rule_id="c001", file_path="f.py", line=2)
    assert a != b


def test_baseline_entry_with_none_line() -> None:
    e = BaselineEntry(rule_id="d004", file_path="<PR description>", line=None)
    assert e.line is None


# ── Baseline.is_suppressed ───────────────────────────────────────────────────


def test_is_suppressed_true_when_entry_present() -> None:
    v = _violation()
    entry = BaselineEntry(rule_id=v.rule_id, file_path=v.file_path, line=v.line)
    bl = Baseline(entries=frozenset({entry}))
    assert bl.is_suppressed(v) is True


def test_is_suppressed_false_when_entry_absent() -> None:
    v = _violation()
    bl = Baseline(entries=frozenset())
    assert bl.is_suppressed(v) is False


def test_is_suppressed_false_on_line_mismatch() -> None:
    v = _violation(line=10)
    entry = BaselineEntry(rule_id=v.rule_id, file_path=v.file_path, line=99)
    bl = Baseline(entries=frozenset({entry}))
    assert bl.is_suppressed(v) is False


def test_is_suppressed_true_for_none_line_violation() -> None:
    v = _violation(line=None)
    entry = BaselineEntry(rule_id=v.rule_id, file_path=v.file_path, line=None)
    bl = Baseline(entries=frozenset({entry}))
    assert bl.is_suppressed(v) is True


# ── save_baseline / load_baseline ────────────────────────────────────────────


def test_save_creates_file(tmp_path: Path) -> None:
    v = _violation()
    path = tmp_path / ".codecongruence-baseline.json"
    save_baseline([v], path)
    assert path.exists()


def test_save_roundtrip(tmp_path: Path) -> None:
    v1 = _violation(rule_id="c001", file_path="a.py", line=5)
    v2 = _violation(rule_id="d001", file_path="b.py", line=None)
    path = tmp_path / ".codecongruence-baseline.json"
    save_baseline([v1, v2], path)

    bl = load_baseline(path)
    assert bl is not None
    assert bl.is_suppressed(v1)
    assert bl.is_suppressed(v2)


def test_save_json_is_human_readable(tmp_path: Path) -> None:
    v = _violation()
    path = tmp_path / "baseline.json"
    save_baseline([v], path)
    data = json.loads(path.read_text())
    assert data["version"] == 1
    assert "generated_at" in data
    assert isinstance(data["violations"], list)
    assert data["violations"][0]["rule_id"] == v.rule_id
    assert data["violations"][0]["message"] == v.message


def test_load_returns_none_when_file_missing(tmp_path: Path) -> None:
    result = load_baseline(tmp_path / "nonexistent.json")
    assert result is None


def test_load_returns_none_on_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not json!")
    assert load_baseline(path) is None


def test_load_returns_none_on_wrong_structure(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"wrong": "structure"}))
    bl = load_baseline(path)
    assert bl is not None
    assert len(bl.entries) == 0


def test_save_empty_violations(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    save_baseline([], path)
    bl = load_baseline(path)
    assert bl is not None
    assert len(bl.entries) == 0


# ── apply_baseline ────────────────────────────────────────────────────────────


def test_apply_baseline_removes_suppressed() -> None:
    v1 = _violation(rule_id="c001", file_path="a.py", line=10)
    v2 = _violation(rule_id="d001", file_path="b.py", line=20)
    entry = BaselineEntry(rule_id=v1.rule_id, file_path=v1.file_path, line=v1.line)
    bl = Baseline(entries=frozenset({entry}))

    filtered, suppressed = apply_baseline(_result(v1, v2), bl)
    assert suppressed == 1
    assert len(filtered.violations) == 1
    assert filtered.violations[0].rule_id == "d001"


def test_apply_baseline_empty_baseline_passes_all() -> None:
    v1 = _violation()
    bl = Baseline(entries=frozenset())
    filtered, suppressed = apply_baseline(_result(v1), bl)
    assert suppressed == 0
    assert len(filtered.violations) == 1


def test_apply_baseline_all_suppressed_makes_ok() -> None:
    v1 = _violation()
    entry = BaselineEntry(rule_id=v1.rule_id, file_path=v1.file_path, line=v1.line)
    bl = Baseline(entries=frozenset({entry}))
    filtered, suppressed = apply_baseline(_result(v1), bl)
    assert suppressed == 1
    assert filtered.ok


def test_apply_baseline_returns_suppressed_count() -> None:
    violations = [_violation(file_path=f"file{i}.py", line=i) for i in range(5)]
    suppressed_entries = frozenset(
        BaselineEntry(rule_id=v.rule_id, file_path=v.file_path, line=v.line) for v in violations[:3]
    )
    bl = Baseline(entries=suppressed_entries)
    _, count = apply_baseline(_result(*violations), bl)
    assert count == 3


# ── baseline_path ─────────────────────────────────────────────────────────────


def test_baseline_path_is_in_repo_root(tmp_path: Path) -> None:
    p = baseline_path(tmp_path)
    assert p == tmp_path / ".codecongruence-baseline.json"
