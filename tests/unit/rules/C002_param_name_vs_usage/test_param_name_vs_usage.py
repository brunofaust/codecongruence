from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from codecongruence.core.config import RuleConfig
from codecongruence.core.git import ChangedFile
from codecongruence.rules.C002_param_name_vs_usage import ParamNameVsUsageRule

if TYPE_CHECKING:
    from pathlib import Path

    from codecongruence.core.embedder import Embedder


def _check(file: Path, emb: Embedder, threshold: float = 0.20):
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


def test_skips_overload(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = """
from typing import overload

@overload
def process_invoice(email_address: str) -> None: ...
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    assert _check(f, fake_embedder) == []
