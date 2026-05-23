from __future__ import annotations

from pathlib import Path

from codecongruence.parsers.base import split_identifier
from codecongruence.parsers.python import PythonParser

_parser = PythonParser()


# ---------------------------------------------------------------------------
# split_identifier
# ---------------------------------------------------------------------------


def test_split_snake_and_camel() -> None:
    assert split_identifier("get_user_by_id") == "get user by identifier"
    assert split_identifier("validateEmailAddress") == "validate email address"
    assert "request" in split_identifier("HTTPRequest")


def test_split_handles_simple_name() -> None:
    assert split_identifier("connect") == "connect"


# ---------------------------------------------------------------------------
# iter_functions
# ---------------------------------------------------------------------------


def test_iter_functions_picks_up_docstrings() -> None:
    src = '''
def add(a, b):
    """Add two numbers and return their sum."""
    return a + b


class Calculator:
    def multiply(self, a, b):
        """Multiply two values."""
        result = a * b
        return result
'''
    funcs = {f.qualified_name: f for f in _parser.iter_functions(src, Path("dummy.py"))}
    assert "add" in funcs
    assert funcs["add"].docstring == "Add two numbers and return their sum."
    assert funcs["Calculator.multiply"].is_method


def test_iter_functions_survives_syntax_error() -> None:
    # tree-sitter recovers from errors; must not raise
    result = list(_parser.iter_functions("def broken(:\n    pass\n", Path("x.py")))
    assert isinstance(result, list)


def test_iter_functions_body_excludes_docstring() -> None:
    src = '''
def send_invoice(to):
    """Send an invoice."""
    payload = {"to": to}
    return payload
'''
    funcs = list(_parser.iter_functions(src, Path("x.py")))
    assert len(funcs) == 1
    # docstring text must NOT appear in body_source
    assert "Send an invoice" not in funcs[0].body_source
    assert "payload" in funcs[0].body_source


def test_iter_functions_detects_async() -> None:
    src = """
async def fetch_data(url):
    result = await client.get(url)
    return result
"""
    funcs = list(_parser.iter_functions(src, Path("x.py")))
    assert any(f.name == "fetch_data" for f in funcs)


def test_iter_functions_nested_class() -> None:
    src = """
class Outer:
    class Inner:
        def method(self):
            return 1
"""
    funcs = {f.qualified_name: f for f in _parser.iter_functions(src, Path("x.py"))}
    assert "Outer.Inner.method" in funcs


def test_iter_functions_decorated() -> None:
    src = """
class MyView:
    @staticmethod
    def handler(request):
        return request.data
"""
    funcs = list(_parser.iter_functions(src, Path("x.py")))
    handler = next(f for f in funcs if f.name == "handler")
    assert "staticmethod" in handler.decorators


# ---------------------------------------------------------------------------
# parameters extraction
# ---------------------------------------------------------------------------


def test_parameters_simple() -> None:
    src = """
def process(user_id, record, flag=False):
    return user_id
"""
    funcs = list(_parser.iter_functions(src, Path("x.py")))
    assert funcs[0].parameters == ("user_id", "record", "flag")


def test_parameters_skips_self_cls() -> None:
    src = """
class Foo:
    def method(self, value):
        return value

    @classmethod
    def create(cls, value):
        return value
"""
    funcs = {f.name: f for f in _parser.iter_functions(src, Path("x.py"))}
    assert "self" not in funcs["method"].parameters
    assert "cls" not in funcs["create"].parameters
    assert "value" in funcs["method"].parameters


def test_parameters_typed_and_default() -> None:
    src = """
def send(recipient: str, amount: int = 0):
    pass
"""
    funcs = list(_parser.iter_functions(src, Path("x.py")))
    assert funcs[0].parameters == ("recipient", "amount")


def test_parameters_variadic() -> None:
    src = """
def wrap(*args, **kwargs):
    pass
"""
    funcs = list(_parser.iter_functions(src, Path("x.py")))
    assert "*args" in funcs[0].parameters
    assert "**kwargs" in funcs[0].parameters


# ---------------------------------------------------------------------------
# iter_comments
# ---------------------------------------------------------------------------


def test_iter_comments_skips_pragmas_and_todos() -> None:
    src = """\
#!/usr/bin/env python
# type: ignore
# TODO this should not appear in the iteration
# This comment describes the next two real lines of code
def f():
    x = 1
    y = 2
    return x + y
"""
    comments = list(_parser.iter_comments(src, context_lines=3))
    assert len(comments) == 1
    assert "describes the next two real lines" in comments[0].text
    assert "x = 1" in comments[0].following_code
