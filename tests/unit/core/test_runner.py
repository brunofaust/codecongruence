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


def test_opt_in_rule_is_off_without_a_config_section(fake_embedder: Embedder) -> None:
    """A rule declaring default_enabled=False stays off when unconfigured.

    D005 is documented as opt-in, but an unconfigured consumer used to get it
    anyway — RuleConfig.enabled defaults to True, so an absent section read as
    "enabled". That is how a repo with no CHANGELOG.md hit a gate it never
    asked for and could not satisfy.
    """
    runner = RuleRunner(CodeCongruenceConfig(), fake_embedder)
    ids = [r.rule_id for r in runner.select_rules(None)]
    assert "docs_on_change" not in ids
    assert "docstring_vs_body" in ids


def test_opt_in_rule_runs_once_configured(fake_embedder: Embedder) -> None:
    """Writing the section opts in; `enabled = false` still wins over that."""
    on = CodeCongruenceConfig(rules={"docs_on_change": RuleConfig()})
    assert "docs_on_change" in [r.rule_id for r in RuleRunner(on, fake_embedder).select_rules(None)]

    off = CodeCongruenceConfig(rules={"docs_on_change": RuleConfig(enabled=False)})
    assert "docs_on_change" not in [
        r.rule_id for r in RuleRunner(off, fake_embedder).select_rules(None)
    ]
