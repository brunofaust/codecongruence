"""Bundled rules.

New rules drop in by adding a ``XNNN_<name>/`` subfolder and registering in
``core/runner.py::default_rules``.
"""

from codecongruence.rules.base import Rule, RuleViolation, Severity
from codecongruence.rules.C001_name_vs_body import NameVsBodyRule
from codecongruence.rules.C002_param_name_vs_usage import ParamNameVsUsageRule
from codecongruence.rules.D001_docstring_vs_body import DocstringVsBodyRule
from codecongruence.rules.D002_stale_comments import StaleCommentsRule
from codecongruence.rules.D003_claude_md_vs_diff import ClaudeMdVsDiffRule
from codecongruence.rules.D004_pr_description_vs_diff import PrDescriptionVsDiffRule
from codecongruence.rules.D005_changelog_exists import ChangelogExistsRule
from codecongruence.rules.D006_params_in_docstring import ParamsInDocstringRule

__all__ = [
    "ChangelogExistsRule",
    "ClaudeMdVsDiffRule",
    "DocstringVsBodyRule",
    "NameVsBodyRule",
    "ParamNameVsUsageRule",
    "ParamsInDocstringRule",
    "PrDescriptionVsDiffRule",
    "Rule",
    "RuleViolation",
    "Severity",
    "StaleCommentsRule",
]
