from __future__ import annotations

from pathlib import Path

import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
from tree_sitter import Language

from codecongruence.parsers.javascript import JavaScriptParser

_js = JavaScriptParser(Language(tsjs.language()))
_ts = JavaScriptParser(Language(tsts.language_typescript()))
_tsx = JavaScriptParser(Language(tsts.language_tsx()))


# ---------------------------------------------------------------------------
# Basic function detection
# ---------------------------------------------------------------------------


def test_function_declaration() -> None:
    src = "function greet(name) {\n  return 'Hello ' + name;\n}\n"
    funcs = {f.name: f for f in _js.iter_functions(src, Path("x.js"))}
    assert "greet" in funcs
    assert funcs["greet"].parameters == ("name",)


def test_arrow_function_named() -> None:
    src = "const add = (x, y) => x + y;\n"
    funcs = {f.name: f for f in _js.iter_functions(src, Path("x.js"))}
    assert "add" in funcs
    assert funcs["add"].parameters == ("x", "y")


def test_class_method() -> None:
    src = """\
class Calculator {
  multiply(a, b) {
    return a * b;
  }
}
"""
    funcs = {f.qualified_name: f for f in _js.iter_functions(src, Path("x.js"))}
    assert "Calculator.multiply" in funcs
    assert funcs["Calculator.multiply"].is_method


def test_jsdoc_extracted_as_docstring() -> None:
    src = """\
/**
 * Greets a user by name.
 * @param name The user's name.
 */
function greet(name) {
  return 'Hello ' + name;
}
"""
    funcs = {f.name: f for f in _js.iter_functions(src, Path("x.js"))}
    assert funcs["greet"].docstring is not None
    assert "name" in funcs["greet"].docstring


def test_no_jsdoc_gives_none_docstring() -> None:
    src = "// plain comment\nfunction greet(name) {\n  return name;\n}\n"
    funcs = list(_js.iter_functions(src, Path("x.js")))
    assert funcs[0].docstring is None


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------


def test_rest_parameter() -> None:
    src = "function wrap(...args) {\n  return args;\n}\n"
    funcs = list(_js.iter_functions(src, Path("x.js")))
    assert "*args" in funcs[0].parameters


def test_default_parameter() -> None:
    src = "function greet(name = 'World') {\n  return name;\n}\n"
    funcs = list(_js.iter_functions(src, Path("x.js")))
    assert "name" in funcs[0].parameters


# ---------------------------------------------------------------------------
# TypeScript
# ---------------------------------------------------------------------------


def test_typescript_typed_params() -> None:
    src = """\
function process(userId: string, amount: number): boolean {
  return true;
}
"""
    funcs = list(_ts.iter_functions(src, Path("x.ts")))
    assert len(funcs) == 1
    assert "userId" in funcs[0].parameters
    assert "amount" in funcs[0].parameters


def test_tsx_component() -> None:
    src = """\
function Button({ label }: { label: string }) {
  return <button>{label}</button>;
}
"""
    funcs = list(_tsx.iter_functions(src, Path("x.tsx")))
    assert any(f.name == "Button" for f in funcs)


# ---------------------------------------------------------------------------
# AST cache
# ---------------------------------------------------------------------------


def test_ast_cache_hit() -> None:
    parser = JavaScriptParser(Language(tsjs.language()))
    src = "function foo(x) {\n  return x;\n}\n"
    first = list(parser.iter_functions(src, Path("x.js")))
    second = list(parser.iter_functions(src, Path("x.js")))
    assert first == second
    assert len(parser._func_cache) == 1


# ---------------------------------------------------------------------------
# iter_comments
# ---------------------------------------------------------------------------


def test_iter_comments_skips_jsdoc_and_todos() -> None:
    src = """\
/** JSDoc comment — should be skipped */
// TODO fix this later
// This comment describes what comes next in detail
function foo() {
  return 1;
}
"""
    comments = list(_js.iter_comments(src, context_lines=3))
    assert len(comments) == 1
    assert "describes what comes next" in comments[0].text
