from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from codecongruence.core.config import RuleConfig
from codecongruence.core.git import ChangedFile
from codecongruence.rules.C001_name_vs_body import NameVsBodyRule

if TYPE_CHECKING:
    from pathlib import Path

    from codecongruence.core.embedder import Embedder


def _check(file: Path, emb: Embedder, threshold: float = 0.25):
    rule = NameVsBodyRule()
    return asyncio.run(
        rule.check([ChangedFile(path=file, added_ranges=())], emb, RuleConfig(threshold=threshold))
    )


def test_flags_name_drift(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = """
def validate_email(addr):
    transport.deliver({"to": addr, "subject": "welcome"})
    log.info("sent welcome email")
    return True
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    violations = _check(f, fake_embedder)
    assert any(v.rule_id == "name_vs_body" for v in violations)


def test_passes_aligned_name(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = """
def send_welcome_email(addr):
    transport.deliver({"to": addr, "subject": "welcome email"})
    log.info("sent welcome email")
    return True
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    violations = _check(f, fake_embedder)
    assert violations == []


def test_comment_matching_name_does_not_suppress_violation(
    tmp_path: Path, fake_embedder: Embedder
) -> None:
    """A comment mirroring the function name must not hide body drift (default).

    The comment is placed between two statements so it falls inside the
    body_source line range (tree-sitter excludes leading-only comments).
    """
    src = """
def send_invoice_email(to):
    fib = 1
    # send invoice email to recipient
    result = fib + fib
    log.info("computed fibonacci")
    return result
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    violations = _check(f, fake_embedder)
    assert any(v.rule_id == "name_vs_body" for v in violations)


def test_include_comments_true_allows_comment_to_boost_similarity(
    tmp_path: Path, fake_embedder: Embedder
) -> None:
    """With include_comments=true a matching comment can satisfy the threshold."""
    src = """
def send_invoice_email(to):
    fib = 1
    # send invoice email to recipient
    result = fib + fib
    log.info("computed fibonacci")
    return result
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    cfg = RuleConfig(threshold=0.25, include_comments=True)
    violations = asyncio.run(
        NameVsBodyRule().check([ChangedFile(path=f, added_ranges=())], fake_embedder, cfg)
    )
    assert violations == []


def test_skips_generic_names(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = """
def main():
    transport.deliver({"to": "x", "subject": "y"})
    log.info("did stuff")
    return True
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    assert _check(f, fake_embedder) == []
