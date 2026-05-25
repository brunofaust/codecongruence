"""Core primitives: config, embedder, git/AST helpers, rule runner, baseline."""

from codecongruence.core.baseline import (
    Baseline,
    apply_baseline,
    baseline_path,
    load_baseline,
    save_baseline,
)
from codecongruence.core.config import CodeCongruenceConfig, RuleConfig, load_config
from codecongruence.core.embedder import Embedder
from codecongruence.core.runner import RuleRunner, run_rules

__all__ = [
    "Baseline",
    "CodeCongruenceConfig",
    "Embedder",
    "RuleConfig",
    "RuleRunner",
    "apply_baseline",
    "baseline_path",
    "load_baseline",
    "load_config",
    "run_rules",
    "save_baseline",
]
