from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from codecongruence.core.config import RuleConfig
from codecongruence.core.git import ChangedFile
from codecongruence.rules.C003_duplicate_functions import DuplicateFunctionsRule

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from codecongruence.core.embedder import Embedder
    from codecongruence.rules.base import RuleViolation


def _check(
    files: list[Path], emb: Embedder, threshold: float = 0.92, scope: str = "staged"
) -> Sequence[RuleViolation]:
    rule = DuplicateFunctionsRule()
    changed = [ChangedFile(path=f, added_ranges=()) for f in files]
    cfg = RuleConfig(threshold=threshold, scope=scope)
    return asyncio.run(rule.check(changed, emb, cfg))


def test_flags_duplicate_pair(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = """
def fetch_user_by_id(uid):
    row = db.query("SELECT * FROM users WHERE id = %s", uid)
    result = row.fetchone()
    return result

def load_user(user_id):
    row = db.query("SELECT * FROM users WHERE id = %s", user_id)
    result = row.fetchone()
    return result
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    violations = _check([f], fake_embedder)
    assert any(v.rule_id == "duplicate_functions" for v in violations)


def test_passes_distinct_functions(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = """
def send_email(address):
    smtp.send(address, subject="hello")
    log.info("email sent")
    return True

def calculate_tax(amount):
    rate = get_tax_rate()
    total = amount * rate
    return total
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    violations = _check([f], fake_embedder)
    assert violations == []


def test_skips_short_bodies(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = """
def add(a, b):
    return a + b

def plus(x, y):
    return x + y
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    # min_body_statement_count=3 skips one-liners
    violations = _check([f], fake_embedder)
    assert violations == []


def test_skips_same_name_same_file(tmp_path: Path, fake_embedder: Embedder) -> None:
    """Two overloads with identical names in the same file are not a duplicate pair."""
    src = """
from typing import overload

@overload
def process(x: int) -> int: ...

@overload
def process(x: str) -> str: ...
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    violations = _check([f], fake_embedder)
    assert violations == []


def test_cross_file_duplicates_flagged(tmp_path: Path, fake_embedder: Embedder) -> None:
    body = """
def fetch_user(uid):
    row = db.query("SELECT * FROM users WHERE id = %s", uid)
    result = row.fetchone()
    return result
"""
    fa = tmp_path / "a.py"
    fb = tmp_path / "b.py"
    fa.write_text(body)
    fb.write_text(body.replace("fetch_user", "get_user"))
    violations = _check([fa, fb], fake_embedder)
    assert any(v.rule_id == "duplicate_functions" for v in violations)


def test_single_file_no_pair(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = """
def process_invoice(invoice_id):
    invoice = db.get(invoice_id)
    invoice.send()
    return True
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    # Only one function — no pair to compare
    assert _check([f], fake_embedder) == []


def test_high_threshold_suppresses_near_duplicates(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = """
def fetch_user(uid):
    row = db.query("SELECT * FROM users WHERE id = %s", uid)
    result = row.fetchone()
    return result

def load_user(user_id):
    row = db.query("SELECT * FROM users WHERE id = %s", user_id)
    result = row.fetchone()
    return result
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    # threshold=1.0 means nothing can match
    violations = _check([f], fake_embedder, threshold=1.0)
    assert violations == []
