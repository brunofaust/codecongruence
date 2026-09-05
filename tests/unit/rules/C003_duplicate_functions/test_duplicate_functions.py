from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import numpy as np

from codecongruence.core.config import RuleConfig
from codecongruence.core.embedder import Embedder
from codecongruence.core.git import ChangedFile
from codecongruence.rules.C003_duplicate_functions import DuplicateFunctionsRule

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

    from numpy.typing import NDArray

    from codecongruence.rules.base import RuleViolation


def _check(
    files: list[Path],
    emb: Embedder,
    threshold: float = 0.92,
    scope: str = "staged",
    **options: object,
) -> Sequence[RuleViolation]:
    rule = DuplicateFunctionsRule()
    changed = [ChangedFile(path=f, added_ranges=()) for f in files]
    cfg = RuleConfig(threshold=threshold, scope=scope, **options)
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


async def test_include_comments_defaults_true_and_false_strips_them(tmp_path: Path) -> None:
    """C003 config controls the exact body text sent to the embedder."""
    source = """
def process(value):
    result = prepare(value)  # original explanation
    result = validate(result)
    return finish(result)
"""
    path = tmp_path / "module.py"
    path.write_text(source)
    changed = [ChangedFile(path=path, added_ranges=())]

    default_entries = await DuplicateFunctionsRule._collect(changed, "staged", 3)
    included_entries = await DuplicateFunctionsRule._collect(changed, "staged", 3, True)
    stripped_entries = await DuplicateFunctionsRule._collect(changed, "staged", 3, False)

    assert default_entries[0].body == included_entries[0].body
    assert "original explanation" in included_entries[0].body
    assert "original explanation" not in stripped_entries[0].body

    path.write_text(source.replace("original explanation", "updated explanation"))
    changed_entries = await DuplicateFunctionsRule._collect(changed, "staged", 3, False)
    assert changed_entries[0].body == stripped_entries[0].body

    captured: list[str] = []

    class RecordingBackend:
        """Capture documents sent through the public rule check."""

        @staticmethod
        def embed(documents: Sequence[str], batch_size: int = 16) -> Iterable[NDArray[np.float32]]:
            captured.extend(documents)
            return [np.ones(2, dtype=np.float32) for _ in documents]

    second = tmp_path / "second.py"
    second.write_text(source.replace("process", "execute"))
    files = [ChangedFile(path=path, added_ranges=()), ChangedFile(path=second, added_ranges=())]
    embedder = Embedder(model_name="fake", backend=RecordingBackend())
    await DuplicateFunctionsRule().check(files, embedder, RuleConfig(include_comments=False))
    assert all("explanation" not in body for body in captured)

    captured.clear()
    await DuplicateFunctionsRule().check(files, embedder, RuleConfig(include_comments=True))
    assert all("explanation" in body for body in captured)


async def test_false_ignores_nested_docstring_edits_but_keeps_string_literals(
    tmp_path: Path,
) -> None:
    """Nested documentation is ignored without deleting executable strings."""
    source = """
def outer(value):
    def inner(item):
        \"\"\"first nested explanation 日本語\"\"\"
        def deep():
            \"\"\"deep explanation\"\"\"
            # deep nested comment
            return \"literal # // payload\"
        return \"literal payload\" + item + str(8 // 2) + deep()
    def sibling():
        \"\"\"sibling explanation\"\"\"
        return value
    def executable_literals():
        # This is not a docstring because the first expression is an f-string.
        f\"{value}\"
        b\"bytes payload\"
        return \"literal # // payload\"
    def assignment_first():
        marker = 1
        def deeper():
            \"\"\"deeper explanation\"\"\"
            return marker
        return deeper()
    class Nested:
        marker = 1
        def method(self):
            \"\"\"method explanation\"\"\"
            # method nested comment
            return self.marker
    result = inner(value)
    return result
"""
    changed = [ChangedFile(path=tmp_path / "module.py", added_ranges=())]
    changed[0].path.write_text(source)
    before = (await DuplicateFunctionsRule._collect(changed, "staged", 3, False))[0].body
    revised_source = (
        source
        .replace("first nested explanation", "revised nested explanation")
        .replace("deep explanation", "revised deep explanation")
        .replace("sibling explanation", "revised sibling explanation")
        .replace("deeper explanation", "revised deeper explanation")
        .replace("method explanation", "revised method explanation")
    )
    changed[0].path.write_text(revised_source)
    after = (await DuplicateFunctionsRule._collect(changed, "staged", 3, False))[0].body

    assert before == after
    assert "literal payload" in before
    assert 'f"{value}"' in before
    assert 'b"bytes payload"' in before


async def test_false_counts_code_statements_without_comments(tmp_path: Path) -> None:
    """Comment-only changes cannot make a short Python body eligible."""
    path = tmp_path / "module.py"
    path.write_text("""
def short():
    value = 1  # commentary
    return value
""")
    changed = [ChangedFile(path=path, added_ranges=())]

    assert await DuplicateFunctionsRule._collect(changed, "staged", 3, False) == []
    assert len(await DuplicateFunctionsRule._collect(changed, "staged", 2, False)) == 1

    path.write_text(path.read_text().replace("  # commentary", ""))
    assert await DuplicateFunctionsRule._collect(changed, "staged", 3, False) == []
    assert len(await DuplicateFunctionsRule._collect(changed, "staged", 2, False)) == 1


def test_skips_nested_closure_against_its_enclosing_function(
    tmp_path: Path, fake_embedder: Embedder
) -> None:
    """A closure's source is contained in its parent's, so the pair scores high by construction."""
    src = """
def build_edit_retaining_history_processor(history):
    def process(edit):
        edit = attach_history(edit, history)
        edit = normalize_ranges(edit)
        edit = drop_empty_hunks(edit)
        edit = renumber(edit)
        return edit
    register(process)
    return process
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    # Without the containment skip this pair scores 0.957 against the 0.92 default.
    assert _check([f], fake_embedder, skip_nested_functions=True) == []


def test_skips_caller_against_its_callee(tmp_path: Path, fake_embedder: Embedder) -> None:
    """A wrapper that delegates to another function is single-owner design, not duplication."""
    src = """
def resolve_price_id(plan_code, billing_cycle):
    prices = load_price_table()
    key = (plan_code, billing_cycle)
    price_id = prices[key]
    return price_id

def matching_price_for_plan(price_id, billing_cycle):
    prices = load_price_table()
    plan_code = reverse_lookup(prices, price_id)
    price_id = resolve_price_id(plan_code, billing_cycle)
    return price_id
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    # The bag-of-words fixture scores this realistic wrapper pair at 0.870, so the
    # threshold is lowered to keep the test about the call-edge skip, not tuning.
    assert _check([f], fake_embedder, threshold=0.85, skip_call_edges=True) == []


def test_still_flags_genuine_top_level_duplicates(tmp_path: Path, fake_embedder: Embedder) -> None:
    """The suppressions must not blind the rule to real duplicate pairs."""
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
    assert [
        v for v in violations if "`fetch_user_by_id`" in v.message and "`load_user`" in v.message
    ]


def test_sibling_closures_in_the_same_parent_are_still_compared(
    tmp_path: Path, fake_embedder: Embedder
) -> None:
    """Sibling closures never enclose each other, so a real duplicate between them is reported."""
    src = """
def outer(source):
    def first(record):
        row = db.query("SELECT * FROM users WHERE id = %s", record)
        result = row.fetchone()
        return result
    def second(item):
        row = db.query("SELECT * FROM users WHERE id = %s", item)
        result = row.fetchone()
        return result
    return first(source) + second(source)
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    violations = _check([f], fake_embedder)
    assert [v for v in violations if "`outer.first`" in v.message and "`outer.second`" in v.message]


def test_call_edge_skip_requires_an_unambiguous_callee_name(
    tmp_path: Path, fake_embedder: Embedder
) -> None:
    """Two classes owning a same-named method make the call target ambiguous — no skip."""
    src = """
class Alpha:
    def render(self, doc):
        doc = normalize_document(doc)
        doc = expand_macros(doc)
        doc = collapse_whitespace(doc)
        return doc

class Beta:
    def render(self, doc):
        doc = normalize_document(doc)
        doc = expand_macros(doc)
        doc = collapse_whitespace(doc)
        return doc

def emit(doc):
    doc = normalize_document(doc)
    doc = expand_macros(doc)
    doc = collapse_whitespace(doc)
    return render(doc)
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    violations = _check([f], fake_embedder, skip_call_edges=True)
    assert [v for v in violations if "`emit`" in v.message and "`Alpha.render`" in v.message]


def test_self_call_is_not_treated_as_a_call_edge(tmp_path: Path, fake_embedder: Embedder) -> None:
    """``self.render`` cannot resolve to another class's ``render`` — no skip."""
    src = """
class Alpha:
    def render(self, doc):
        doc = normalize_document(doc)
        doc = expand_macros(doc)
        doc = collapse_whitespace(doc)
        return doc

class Gamma:
    def emit(self, doc):
        doc = normalize_document(doc)
        doc = expand_macros(doc)
        doc = collapse_whitespace(doc)
        return self.render(doc)
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    violations = _check([f], fake_embedder, skip_call_edges=True)
    assert [v for v in violations if "`Alpha.render`" in v.message and "`Gamma.emit`" in v.message]


def test_nested_function_pairs_are_reported_unless_the_skip_is_opted_into(
    tmp_path: Path, fake_embedder: Embedder
) -> None:
    """The containment skip is off by default and stays off when set explicitly."""
    src = """
def build_edit_retaining_history_processor(history):
    def process(edit):
        edit = attach_history(edit, history)
        edit = normalize_ranges(edit)
        edit = drop_empty_hunks(edit)
        edit = renumber(edit)
        return edit
    register(process)
    return process
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    assert _check([f], fake_embedder)
    assert _check([f], fake_embedder, skip_nested_functions=False)


def test_caller_callee_pairs_are_reported_unless_the_skip_is_opted_into(
    tmp_path: Path, fake_embedder: Embedder
) -> None:
    """The call-edge skip is off by default and stays off when set explicitly."""
    src = """
def resolve_price_id(plan_code, billing_cycle):
    prices = load_price_table()
    key = (plan_code, billing_cycle)
    price_id = prices[key]
    return price_id

def matching_price_for_plan(price_id, billing_cycle):
    prices = load_price_table()
    plan_code = reverse_lookup(prices, price_id)
    price_id = resolve_price_id(plan_code, billing_cycle)
    return price_id
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    assert _check([f], fake_embedder, threshold=0.85)
    assert _check([f], fake_embedder, threshold=0.85, skip_call_edges=False)


_HOUSE_STYLE_PATTERNS = [
    r"^\s*(?:validate_request_signature|audit_log|session\.\w+)\(.*\)\s*$",
    r"^\s*(?:\w+ = )?mailer\.\w+\(.*\)\s*$",
    r"^\s*return record\s*$",
]

_SHARED_FRAME = """
def create_org(payload, session):
    validate_request_signature(payload)
    audit_log("create", payload)
    session.begin()
    session.flush()
    record = Org(name=payload.name)
    session.add(record)
    session.refresh(record)
    session.commit()
    audit_log("created", payload)
    return record

def create_plan(payload, session):
    validate_request_signature(payload)
    audit_log("create", payload)
    session.begin()
    session.flush()
    record = Plan(code=payload.code)
    session.add(record)
    session.refresh(record)
    session.commit()
    audit_log("created", payload)
    return record
"""


def test_strip_before_compare_removes_the_shared_frame(
    tmp_path: Path, fake_embedder: Embedder
) -> None:
    """Two functions differing only in boilerplate stop matching once it is stripped."""
    f = tmp_path / "mod.py"
    f.write_text(_SHARED_FRAME)
    # Unstripped the frame carries the pair to 0.938; the remnants score 0.286.
    assert _check([f], fake_embedder)
    assert _check([f], fake_embedder, strip_before_compare=_HOUSE_STYLE_PATTERNS) == []


def test_strip_before_compare_keeps_genuine_duplicates_reported(
    tmp_path: Path, fake_embedder: Embedder
) -> None:
    """Stripping removes the shared frame, never the distinctive remainder.

    Stripping raises discrimination in both directions: a frameless duplicate
    stays reported, and one whose frame diluted it becomes reported.
    """
    plain = """
def fetch_user_by_id(uid):
    row = db.query("SELECT * FROM users WHERE id = %s", uid)
    result = row.fetchone()
    return result

def load_user(user_id):
    row = db.query("SELECT * FROM users WHERE id = %s", user_id)
    result = row.fetchone()
    return result
"""
    frameless = tmp_path / "plain.py"
    frameless.write_text(plain)
    assert _check([frameless], fake_embedder, strip_before_compare=_HOUSE_STYLE_PATTERNS)

    src = """
def fetch_user_by_id(uid, session):
    validate_request_signature(uid)
    session.begin()
    row = db.query("SELECT * FROM users WHERE id = %s", uid)
    result = row.fetchone()
    session.commit()
    return result

def load_user(user_id, session):
    validate_request_signature(user_id)
    session.begin()
    row = db.query("SELECT * FROM users WHERE id = %s", user_id)
    result = row.fetchone()
    session.commit()
    return result
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    # The shared frame drags this genuine duplicate down to 0.824; the remnants
    # score 0.922, so stripping surfaces a pair the boilerplate was hiding.
    assert _check([f], fake_embedder) == []
    violations = _check([f], fake_embedder, strip_before_compare=_HOUSE_STYLE_PATTERNS)
    assert [
        v for v in violations if "`fetch_user_by_id`" in v.message and "`load_user`" in v.message
    ]


def test_strip_min_remnant_chars_guards_over_stripping(
    tmp_path: Path, fake_embedder: Embedder
) -> None:
    """Two near-empty remnants match trivially, so the pair is compared unstripped."""
    src = """
def archive_org(payload, session):
    validate_request_signature(payload)
    audit_log("archive", payload)
    session.begin()
    session.commit()
    record = None
    return record

def render_invoice(user, mailer, template, locale):
    page = mailer.render(template, locale)
    stamped = mailer.stamp(page, user, locale)
    mailer.deliver(stamped, user)
    record = None
    return record
"""
    f = tmp_path / "mod.py"
    f.write_text(src)
    # Both remnants collapse to `record = None` (11 chars): stripped they score
    # 1.000, unstripped 0.187. Without the floor the strip invents a match.
    assert _check(
        [f],
        fake_embedder,
        strip_before_compare=_HOUSE_STYLE_PATTERNS,
        strip_min_remnant_chars=0,
    )
    assert _check([f], fake_embedder, strip_before_compare=_HOUSE_STYLE_PATTERNS) == []


def test_strip_before_compare_absent_or_empty_is_a_no_op(
    tmp_path: Path, fake_embedder: Embedder
) -> None:
    """No patterns must reproduce the pre-option result exactly."""
    f = tmp_path / "mod.py"
    f.write_text(_SHARED_FRAME)
    baseline = _check([f], fake_embedder)
    assert [v.message for v in _check([f], fake_embedder, strip_before_compare=[])] == [
        v.message for v in baseline
    ]
