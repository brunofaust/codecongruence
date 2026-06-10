from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from codecongruence.core.config import RuleConfig
from codecongruence.core.git import ChangedFile
from codecongruence.rules.C002_param_name_vs_usage import ParamNameVsUsageRule

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from codecongruence.core.embedder import Embedder
    from codecongruence.rules.base import RuleViolation


def _check(file: Path, emb: Embedder, threshold: float = 0.20) -> Sequence[RuleViolation]:
    rule = ParamNameVsUsageRule()
    return asyncio.run(
        rule.check([ChangedFile(path=file, added_ranges=())], emb, RuleConfig(threshold=threshold))
    )


def test_flags_mismatched_param(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = """
def process_invoice(email_address):
    invoice.send(email_address)
    log.info("invoice sent to email_address")
    return True
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    violations = _check(f, fake_embedder)
    assert any(v.rule_id == "param_name_vs_usage" for v in violations)


def test_passes_aligned_param(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = """
def send_invoice(invoice_id):
    invoice = db.get_invoice(invoice_id)
    invoice.send()
    return True
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    violations = _check(f, fake_embedder)
    assert violations == []


def test_skips_unused_param(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = """
def compute(totally_unused):
    result = 1 + 1
    return result
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    # unused param has no usage lines — rule skips it
    assert _check(f, fake_embedder) == []


def test_skips_single_letter_param(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = """
def square(x):
    total = x * x
    return total
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    assert _check(f, fake_embedder) == []


def test_param_only_in_comment_skipped_when_comments_stripped(
    tmp_path: Path, fake_embedder: Embedder
) -> None:
    """With include_comments=false, a param only in an inter-statement comment is unused.

    The comment is between two statements so it falls inside the body_source
    line range.  With include_comments=false that line is stripped before
    _usage_context runs, leaving no references to user_data → skipped.
    """
    src = """
def process_billing(user_data):
    invoice = load_invoice()
    # handle user_data here
    total = invoice.calculate_total()
    return total
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    cfg = RuleConfig(threshold=0.20, include_comments=False)
    violations = asyncio.run(
        ParamNameVsUsageRule().check([ChangedFile(path=f, added_ranges=())], fake_embedder, cfg)
    )
    assert violations == []


def test_param_in_comment_included_by_default(tmp_path: Path, fake_embedder: Embedder) -> None:
    """With default (include_comments=true), a comment referencing the param counts as usage."""
    src = """
def process_billing(user_data):
    invoice = load_invoice()
    # handle user_data here
    total = invoice.calculate_total()
    return total
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    # default include_comments=True → comment line is in body_source →
    # _usage_context finds "handle here" (user_data stripped) →
    # "user data" vs "handle here" → no overlap → violation
    violations = _check(f, fake_embedder)
    assert any(v.rule_id == "param_name_vs_usage" for v in violations)


def test_skips_overload(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = """
from typing import overload

@overload
def process_invoice(email_address: str) -> None: ...
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    assert _check(f, fake_embedder) == []
