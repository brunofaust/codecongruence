"""Unit tests for core.runner rule selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from codecongruence.core.config import CodeCongruenceConfig, RuleConfig
from codecongruence.core.runner import RuleRunner, UnknownRuleError

if TYPE_CHECKING:
    from codecongruence.core.embedder import Embedder


def test_unknown_rule_id_raises(fake_embedder: Embedder) -> None:
    runner = RuleRunner(CodeCongruenceConfig(), fake_embedder)
    with pytest.raises(UnknownRuleError, match="docstring_vs_bdy"):
        runner.select_rules("docstring_vs_bdy")


def test_unknown_rule_error_lists_valid_ids(fake_embedder: Embedder) -> None:
    runner = RuleRunner(CodeCongruenceConfig(), fake_embedder)
    with pytest.raises(UnknownRuleError, match="docstring_vs_body"):
        runner.select_rules("nope")


def test_explicit_rule_selects_even_when_disabled(fake_embedder: Embedder) -> None:
    cfg = CodeCongruenceConfig(rules={"docstring_vs_body": RuleConfig(enabled=False)})
    runner = RuleRunner(cfg, fake_embedder)
    selected = runner.select_rules("docstring_vs_body")
    assert [r.rule_id for r in selected] == ["docstring_vs_body"]


def test_short_code_selects_rule(fake_embedder: Embedder) -> None:
    runner = RuleRunner(CodeCongruenceConfig(), fake_embedder)
    selected = runner.select_rules("D001")
    assert [r.rule_id for r in selected] == ["docstring_vs_body"]


def test_default_selection_respects_enabled_flag(fake_embedder: Embedder) -> None:
    cfg = CodeCongruenceConfig(rules={"docstring_vs_body": RuleConfig(enabled=False)})
    runner = RuleRunner(cfg, fake_embedder)
    selected = runner.select_rules(None)
    ids = [r.rule_id for r in selected]
    assert "docstring_vs_body" not in ids
    assert "name_vs_body" in ids
