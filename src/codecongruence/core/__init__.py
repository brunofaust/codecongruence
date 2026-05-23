"""Core primitives: config, embedder, git/AST helpers, rule runner."""

from codecongruence.core.config import CodeCongruenceConfig, RuleConfig, load_config
from codecongruence.core.embedder import Embedder
from codecongruence.core.runner import RuleRunner, run_rules

__all__ = [
    "CodeCongruenceConfig",
    "Embedder",
    "RuleConfig",
    "RuleRunner",
    "load_config",
    "run_rules",
]
