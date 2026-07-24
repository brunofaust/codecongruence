from __future__ import annotations

from typing import TYPE_CHECKING

from codecongruence.core.config import RuleConfig
from codecongruence.core.git import ChangedFile
from codecongruence.rules.base import iter_parsed, resolve_threshold, similarity_violation
from codecongruence.rules.C001_name_vs_body import NameVsBodyRule

if TYPE_CHECKING:
    from pathlib import Path

    from codecongruence.core.embedder import Embedder


def test_resolve_threshold_uses_rule_default() -> None:
    rule = NameVsBodyRule()
    assert resolve_threshold(rule, RuleConfig()) == rule.default_threshold


def test_resolve_threshold_prefers_config_override() -> None:
    assert resolve_threshold(NameVsBodyRule(), RuleConfig(threshold=0.9)) == 0.9


def test_iter_parsed_yields_readable_supported_files(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("def f():\n    return 1\n")
    changed = [ChangedFile(path=(tmp_path / "ok.py"), added_ranges=())]
    results = list(iter_parsed(changed))
    assert len(results) == 1
    cf, parser, source = results[0]
    assert cf is changed[0]
    assert parser is not None
    assert "def f()" in source


def test_iter_parsed_skips_unsupported_extension(tmp_path: Path) -> None:
    (tmp_path / "notes.xyz").write_text("hello")
    assert list(iter_parsed([ChangedFile(path=(tmp_path / "notes.xyz"), added_ranges=())])) == []


def test_iter_parsed_skips_unreadable_file(tmp_path: Path) -> None:
    missing = ChangedFile(path=(tmp_path / "gone.py"), added_ranges=())
    assert list(iter_parsed([missing])) == []


async def test_similarity_violation_none_when_similar(fake_embedder: Embedder) -> None:
    violation = await similarity_violation(
        fake_embedder,
        "connect to database",
        "connect to database",
        rule=NameVsBodyRule(),
        threshold=0.5,
        file_path="src/x.py",
        line=3,
        log_context="C001 src/x.py::f",
        message_template="drift (similarity {sim:.2f} < {threshold:.2f})",
    )
    assert violation is None


async def test_similarity_violation_built_on_drift(fake_embedder: Embedder) -> None:
    rule = NameVsBodyRule()
    violation = await similarity_violation(
        fake_embedder,
        "draw a triangle",
        "send an email",
        rule=rule,
        threshold=0.5,
        file_path="src/x.py",
        line=3,
        log_context="C001 src/x.py::f",
        message_template="drift (similarity {sim:.2f} < {threshold:.2f})",
    )
    assert violation is not None
    assert violation.rule_id == rule.rule_id
    assert violation.code == rule.code
    assert violation.file_path == "src/x.py"
    assert violation.line == 3
    assert violation.threshold == 0.5
    assert violation.similarity < 0.5
    assert f"{violation.similarity:.2f}" in violation.message
    assert "< 0.50" in violation.message
