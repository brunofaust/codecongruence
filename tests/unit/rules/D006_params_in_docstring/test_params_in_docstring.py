from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from codecongruence.core.config import RuleConfig
from codecongruence.core.git import ChangedFile
from codecongruence.rules.D006_params_in_docstring import ParamsInDocstringRule
from codecongruence.rules.D006_params_in_docstring.rule import mentioned

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from codecongruence.core.embedder import Embedder
    from codecongruence.rules.base import RuleViolation


def _check(file: Path, emb: Embedder, **kwargs: object) -> Sequence[RuleViolation]:
    rule = ParamsInDocstringRule()
    cfg = RuleConfig(**kwargs)
    return asyncio.run(rule.check([ChangedFile(path=file, added_ranges=())], emb, cfg))


# ---------------------------------------------------------------------------
# _mentioned unit tests (no I/O, no embedder)
# ---------------------------------------------------------------------------


def test_mentioned_exact_match() -> None:
    assert mentioned("user_id", "user_id: The identifier of the user.")


def test_mentioned_in_prose() -> None:
    assert mentioned("record", "Pass the record and it will be saved.")


def test_mentioned_sphinx_style() -> None:
    assert mentioned("user_id", ":param user_id: The user identifier.")


def test_mentioned_numpy_style() -> None:
    assert mentioned("user_id", "user_id : int\n    The user identifier.")


def test_notmentioned() -> None:
    assert not mentioned("record", "Saves the user to the database.")


def test_mentioned_word_boundary() -> None:
    # "records" should NOT count as mentioning "record"
    assert not mentioned("record", "Processes all records in the batch.")


# ---------------------------------------------------------------------------
# Rule integration tests
# ---------------------------------------------------------------------------


def test_flags_undocumented_param(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = '''
def process(user_id, record):
    """Save the user to the database."""
    db.save(user_id, record)
    return True
'''
    f = tmp_path / "mod.py"
    f.write_text(src)
    violations = _check(f, fake_embedder)
    # both user_id and record are missing from the docstring
    assert any(v.rule_id == "params_in_docstring" for v in violations)


def test_passes_all_paramsmentioned(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = '''
def process(user_id, record):
    """Save the user_id and the record to the database."""
    db.save(user_id, record)
    return True
'''
    f = tmp_path / "mod.py"
    f.write_text(src)
    assert _check(f, fake_embedder) == []


def test_passes_google_style(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = '''
def process(user_id, record):
    """Save the user.

    Args:
        user_id: The user identifier.
        record: The billing record.
    """
    db.save(user_id, record)
    return True
'''
    f = tmp_path / "mod.py"
    f.write_text(src)
    assert _check(f, fake_embedder) == []


def test_passes_arguments_style(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = '''
def process(user_id, record):
    """Save the user.

    Arguments:
        user_id: The user identifier.
        record: The billing record.
    """
    db.save(user_id, record)
    return True
'''
    f = tmp_path / "mod.py"
    f.write_text(src)
    assert _check(f, fake_embedder) == []


def test_passes_sphinx_style(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = '''
def process(user_id, record):
    """Save the user.

    :param user_id: The user identifier.
    :param record: The billing record.
    """
    db.save(user_id, record)
    return True
'''
    f = tmp_path / "mod.py"
    f.write_text(src)
    assert _check(f, fake_embedder) == []


def test_skips_no_docstring(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = """
def process(user_id, record):
    db.save(user_id, record)
    return True
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    assert _check(f, fake_embedder) == []


def test_skips_variadic_by_default(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = '''
def process(*args, **kwargs):
    """Do something."""
    do_work(*args, **kwargs)
    return True
'''
    f = tmp_path / "mod.py"
    f.write_text(src)
    assert _check(f, fake_embedder) == []


def test_variadic_flagged_when_skip_disabled(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = '''
def process(*args, **kwargs):
    """Do something."""
    do_work(*args, **kwargs)
    return True
'''
    f = tmp_path / "mod.py"
    f.write_text(src)
    violations = _check(f, fake_embedder, skip_variadic=False)
    assert any(v.rule_id == "params_in_docstring" for v in violations)
