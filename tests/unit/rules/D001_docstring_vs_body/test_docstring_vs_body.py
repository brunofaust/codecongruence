from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from codecongruence.core.config import RuleConfig
from codecongruence.core.git import ChangedFile
from codecongruence.rules.D001_docstring_vs_body import DocstringVsBodyRule

if TYPE_CHECKING:
    from pathlib import Path

    from codecongruence.core.embedder import Embedder


def _check(rule: DocstringVsBodyRule, file: Path, emb: Embedder, threshold: float = 0.30):
    cfg = RuleConfig(threshold=threshold)
    cf = ChangedFile(path=file, added_ranges=())
    return asyncio.run(rule.check([cf], emb, cfg))


def test_flags_misleading_docstring(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = '''
def send_invoice_email(to):
    """Compute the n-th Fibonacci number recursively."""
    payload = {"recipient": to, "subject": "invoice"}
    transport.deliver(payload)
    log.info("sent invoice")
    return payload
'''
    f = tmp_path / "mod.py"
    f.write_text(src)
    violations = _check(DocstringVsBodyRule(), f, fake_embedder)
    assert len(violations) == 1
    assert violations[0].rule_id == "docstring_vs_body"
    assert violations[0].similarity < 0.30


def test_passes_aligned_docstring(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = '''
def send_invoice_email(to):
    """Send an invoice email to the recipient via the transport."""
    payload = {"recipient": to, "subject": "invoice"}
    transport.deliver(payload)
    log.info("sent invoice email")
    return payload
'''
    f = tmp_path / "mod.py"
    f.write_text(src)
    violations = _check(DocstringVsBodyRule(), f, fake_embedder)
    assert violations == []


def test_skips_short_body(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = '''
def trivial():
    """This is a very long docstring describing complicated logic."""
    return 1
'''
    f = tmp_path / "mod.py"
    f.write_text(src)
    assert _check(DocstringVsBodyRule(), f, fake_embedder) == []
