"""codecongruence — semantic pre-commit hooks via local sentence embeddings."""

from codecongruence.core.config import CodeCongruenceConfig, RuleConfig, load_config
from codecongruence.core.embedder import Embedder
from codecongruence.core.runner import RuleRunner, run_rules
from codecongruence.rules.base import Rule, RuleViolation, Severity

__all__ = [
    "CodeCongruenceConfig",
    "Embedder",
    "Rule",
    "RuleConfig",
    "RuleRunner",
    "RuleViolation",
    "Severity",
    "__version__",
    "load_config",
    "run_rules",
]

__version__ = "0.1.0"
