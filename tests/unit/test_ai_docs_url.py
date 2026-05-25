"""Tests for AI-friendly docs URLs on violations and reporters."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from codecongruence.core.config import CodeCongruenceConfig, RuleConfig
from codecongruence.core.embedder import Embedder
from codecongruence.core.git import ChangedFile
from codecongruence.core.runner import RuleRunner, RunResult
from codecongruence.reporters.text import TextReporter
from codecongruence.rules.base import DOCS_BASE_URL, RuleViolation
from codecongruence.rules.C001_name_vs_body import NameVsBodyRule
from codecongruence.rules.C002_param_name_vs_usage import ParamNameVsUsageRule
from codecongruence.rules.D001_docstring_vs_body import DocstringVsBodyRule
from codecongruence.rules.D002_stale_comments import StaleCommentsRule
from codecongruence.rules.D003_claude_md_vs_diff import ClaudeMdVsDiffRule
from codecongruence.rules.D004_pr_description_vs_diff import PrDescriptionVsDiffRule
from codecongruence.rules.D005_changelog_exists import DocsOnChangeRule
from codecongruence.rules.D006_params_in_docstring import ParamsInDocstringRule
from tests.conftest import BagOfWordsBackend

if TYPE_CHECKING:
    from pathlib import Path as PathType

_ALL_RULES = [
    NameVsBodyRule(),
    ParamNameVsUsageRule(),
    DocstringVsBodyRule(),
    StaleCommentsRule(),
    ClaudeMdVsDiffRule(),
    PrDescriptionVsDiffRule(),
    DocsOnChangeRule(),
    ParamsInDocstringRule(),
]


@pytest.mark.parametrize("rule", _ALL_RULES, ids=lambda r: r.code)
def test_every_rule_has_docs_url(rule: object) -> None:
    """Every rule must have a docs_url attribute pointing to GitHub README."""
    url = getattr(rule, "docs_url", None)
    assert url is not None, f"{rule!r} missing docs_url"
    assert url.startswith(DOCS_BASE_URL), f"{rule!r} docs_url has unexpected prefix"
    assert url.endswith("/README.md"), f"{rule!r} docs_url should point to README.md"


@pytest.mark.parametrize("rule", _ALL_RULES, ids=lambda r: r.code)
def test_docs_url_contains_rule_code(rule: object) -> None:
    """Each rule's docs_url must contain its own code (C001, D005, etc)."""
    url: str = rule.docs_url
    assert rule.code in url, f"docs_url for {rule!r} missing its own code"


def test_rule_violation_accepts_docs_url() -> None:
    """RuleViolation must accept and store docs_url parameter."""
    v = RuleViolation(
        rule_id="name_vs_body",
        code="C001",
        file_path="src/foo.py",
        line=10,
        message="mismatch",
        similarity=0.1,
        threshold=0.25,
        docs_url="https://example.com/README.md",
    )
    assert v.docs_url == "https://example.com/README.md"


def test_rule_violation_defaults_docs_url_to_none() -> None:
    """RuleViolation docs_url should default to None."""
    v = RuleViolation(
        rule_id="name_vs_body",
        code="C001",
        file_path="src/foo.py",
        line=10,
        message="mismatch",
        similarity=0.1,
        threshold=0.25,
    )
    assert v.docs_url is None


def _make_result(docs_url: str | None = "https://example.com/README.md") -> RunResult:
    """Create a RunResult with a single violation for testing."""
    v = RuleViolation(
        rule_id="name_vs_body",
        code="C001",
        file_path="src/foo.py",
        line=5,
        message="name vs body drift",
        similarity=0.10,
        threshold=0.25,
        docs_url=docs_url,
    )

    return RunResult(
        violations=(v,),
        files_checked=(Path("src/foo.py"),),
        rules_run=("name_vs_body",),
    )


def test_text_reporter_shows_docs_section() -> None:
    """TextReporter must display Rule documentation section when docs_url present."""
    buf = io.StringIO()
    console = Console(file=buf, highlight=False, markup=True, width=200)
    TextReporter(console=console).report(_make_result())
    output = buf.getvalue()
    assert "Rule documentation:" in output
    assert "C001" in output
    assert "https://example.com/README.md" in output


def test_text_reporter_no_docs_section_when_urls_absent() -> None:
    """TextReporter must omit Rule documentation section when all docs_url are None."""
    buf = io.StringIO()
    console = Console(file=buf, highlight=False, markup=True, width=200)
    TextReporter(console=console).report(_make_result(docs_url=None))
    output = buf.getvalue()
    assert "Rule documentation:" not in output


def test_runner_injects_docs_url_into_violations(tmp_path: PathType) -> None:
    """Runner must set docs_url on violations returned by rules."""

    class FakeRule:
        """Fake rule for testing docs_url injection."""

        rule_id = "name_vs_body"
        code = "C001"
        description = "test"
        default_threshold = 0.25
        docs_url = "https://example.com/C001/README.md"

        async def check(
            self,
            changed_files: Sequence[ChangedFile],
            embedder: Embedder,
            config: RuleConfig,
        ) -> Sequence[RuleViolation]:
            """Return a test violation without docs_url."""
            return [
                RuleViolation(
                    rule_id=self.rule_id,
                    code=self.code,
                    file_path="f.py",
                    line=1,
                    message="drift",
                    similarity=0.05,
                    threshold=0.25,
                )
            ]

    embedder = Embedder(model_name="fake", backend=BagOfWordsBackend())
    config = CodeCongruenceConfig(
        repo_root=tmp_path,
        rules={"name_vs_body": RuleConfig(enabled=True)},
    )
    runner = RuleRunner(config, embedder, rules=[FakeRule()])  # type: ignore[list-item]
    cf = ChangedFile(path=Path("f.py"), added_ranges=())
    result = asyncio.run(runner.run(pre_gathered=[cf]))

    assert len(result.violations) == 1
    assert result.violations[0].docs_url == "https://example.com/C001/README.md"


def test_text_reporter_deduplicates_docs_by_code() -> None:
    """TextReporter must show each unique docs_url only once (per code)."""
    url = "https://example.com/C001/README.md"
    v1 = RuleViolation("name_vs_body", "C001", "a.py", 1, "m", 0.1, 0.25, docs_url=url)
    v2 = RuleViolation("name_vs_body", "C001", "b.py", 2, "m", 0.1, 0.25, docs_url=url)
    result = RunResult(
        violations=(v1, v2),
        files_checked=(Path("a.py"), Path("b.py")),
        rules_run=("name_vs_body",),
    )
    buf = io.StringIO()
    console = Console(file=buf, highlight=False, markup=True, width=200)
    TextReporter(console=console).report(result)
    output = buf.getvalue()
    assert output.count(url) == 1, "URL should appear exactly once even for two violations"
