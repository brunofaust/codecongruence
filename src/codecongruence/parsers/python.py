"""Python language parser backed by tree-sitter-python.

Replaces the old ``core/ast_helpers.py`` with a tree-sitter implementation so
the parsing layer is consistent across all future languages (JS, TS, Rust, …).

Key advantages over ``ast``:
- Error recovery: syntax errors produce ERROR nodes, not exceptions.
- First-class comment nodes.
- Same LanguageParser protocol as every other language.
"""

from __future__ import annotations

import ast as _ast
import re
from typing import TYPE_CHECKING

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from codecongruence.parsers.base import CommentBlock, FunctionInfo

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

__all__ = ["PythonParser"]

_LANGUAGE = Language(tspython.language())
_PARSER = Parser(_LANGUAGE)

_DATACLASS_DECORATORS: frozenset[str] = frozenset({"dataclass", "dataclasses.dataclass"})
_MIN_COMMENT_WORDS = 4
_PRAGMA_RE = re.compile(
    r"^\s*#\s*(type:\s*ignore|noqa|pylint:|mypy:|fmt:|ruff:|pragma:|coding[:=]|!|\-\*\-)"
)
_TODO_RE = re.compile(r"^\s*#\s*(TODO|FIXME|NOTE|HACK|XXX)\b", re.IGNORECASE)

_FUNC_TYPES = frozenset({"function_definition", "async_function_definition"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _text(node: Node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _decorator_name(node: Node, src: bytes) -> str:
    """Extract the callable name from a ``decorator`` node.

    Args:
        node: The ``decorator`` AST node.
        src: Raw source bytes of the file.

    Returns:
        The decorator's name string, or an empty string when not resolvable.
    """
    for child in node.children:
        if child.type == "identifier":
            return _text(child, src)
        if child.type == "attribute":
            return _text(child, src)
        if child.type == "call":
            func = child.child_by_field_name("function")
            return _text(func, src) if func else ""
    return ""


def _extract_docstring(body: Node, src: bytes) -> str | None:
    """Return docstring text if the first body statement is a string literal.

    Args:
        body: The function body AST node.
        src: Raw source bytes of the file.
    """
    named = body.named_children
    if not named or named[0].type != "expression_statement":
        return None
    for sub in named[0].named_children:
        if sub.type == "string":
            raw = _text(sub, src)
            try:
                val = _ast.literal_eval(raw)
                return val if isinstance(val, str) else None
            except (ValueError, SyntaxError):
                return None
    return None


def _body_source_skip_docstring(body: Node, lines: list[str]) -> str:
    """Return the body lines after skipping the leading docstring statement."""
    named = body.named_children
    if not named:
        return ""
    start_idx = 0
    if named[0].type == "expression_statement":
        for sub in named[0].named_children:
            if sub.type == "string":
                start_idx = 1
                break
    remaining = named[start_idx:]
    if not remaining:
        return ""
    start_line = remaining[0].start_point[0]  # 0-indexed row
    end_line = remaining[-1].end_point[0]  # 0-indexed row
    return "\n".join(lines[start_line : end_line + 1])


def _extract_parameters(
    node: Node, src: bytes
) -> tuple[tuple[str, ...], tuple[tuple[str, str, str], ...]]:
    """Extract parameter names and type/default metadata from a function node.

    Skips ``self`` and ``cls``. Variadic parameters carry their ``*`` or ``**``
    prefix in the names tuple so callers can filter them.

    Args:
        node: The function definition AST node.
        src: Raw source bytes of the file.

    Returns:
        A pair of:
        - ``names``: parameter name strings (variadic prefixed with ``*``/``**``).
        - ``details``: per-parameter ``(clean_name, annotation_text, default_text)``
          tuples; both text fields are ``""`` when absent.
    """
    params_node = node.child_by_field_name("parameters")
    if params_node is None:
        return (), ()
    names: list[str] = []
    details: list[tuple[str, str, str]] = []
    for child in params_node.named_children:
        name: str | None = None
        annotation: str = ""
        default: str = ""
        match child.type:
            case "identifier":
                name = _text(child, src)
            case "typed_parameter":
                name_node = child.child_by_field_name("name") or next(
                    (c for c in child.named_children if c.type == "identifier"), None
                )
                type_node = child.child_by_field_name("type")
                if name_node is not None:
                    name = _text(name_node, src)
                if type_node is not None:
                    annotation = _text(type_node, src)
            case "default_parameter":
                name_node = child.child_by_field_name("name") or next(
                    (c for c in child.named_children if c.type == "identifier"), None
                )
                value_node = child.child_by_field_name("value")
                if name_node is not None:
                    name = _text(name_node, src)
                if value_node is not None:
                    default = _text(value_node, src)
            case "typed_default_parameter":
                name_node = child.child_by_field_name("name") or next(
                    (c for c in child.named_children if c.type == "identifier"), None
                )
                type_node = child.child_by_field_name("type")
                value_node = child.child_by_field_name("value")
                if name_node is not None:
                    name = _text(name_node, src)
                if type_node is not None:
                    annotation = _text(type_node, src)
                if value_node is not None:
                    default = _text(value_node, src)
            case "list_splat_pattern":
                inner = next((c for c in child.named_children if c.type == "identifier"), None)
                if inner is not None:
                    name = "*" + _text(inner, src)
            case "dictionary_splat_pattern":
                inner = next((c for c in child.named_children if c.type == "identifier"), None)
                if inner is not None:
                    name = "**" + _text(inner, src)
        if name and name not in {"self", "cls"}:
            names.append(name)
            details.append((name.lstrip("*"), annotation, default))
    return tuple(names), tuple(details)


def _make_function_info(
    node: Node,
    src: bytes,
    lines: list[str],
    qualifier: str,
    parent_is_dataclass: bool,
    is_method: bool,
    decorators: tuple[str, ...],
) -> FunctionInfo | None:
    name_node = node.child_by_field_name("name")
    body_node = node.child_by_field_name("body")
    if name_node is None or body_node is None:
        return None

    name = _text(name_node, src)
    param_names, param_details = _extract_parameters(node, src)
    return FunctionInfo(
        name=name,
        qualified_name=f"{qualifier}{name}",
        docstring=_extract_docstring(body_node, src),
        body_source=_body_source_skip_docstring(body_node, lines),
        line_start=node.start_point[0] + 1,  # 1-based
        line_end=node.end_point[0] + 1,  # 1-based
        decorators=decorators,
        is_method=is_method,
        parent_is_dataclass=parent_is_dataclass,
        body_statements=len(body_node.named_children),
        parameters=param_names,
        parameter_details=param_details,
    )


def _walk(
    node: Node,
    src: bytes,
    lines: list[str],
    qualifier: str,
    parent_is_dataclass: bool,
    is_method: bool,
) -> Iterator[FunctionInfo]:
    """Recursively walk a tree node, yielding every function/method found.

    Args:
        node: The current tree-sitter AST node to descend into.
        src: Raw source bytes of the file.
        lines: Source lines of the file (0-indexed).
        qualifier: Dotted class/function prefix for qualified names.
        parent_is_dataclass: Whether the enclosing class is a dataclass.
        is_method: Whether functions at this level are class methods.

    Yields:
        One :class:`FunctionInfo` per function/method encountered in the tree.
    """
    for child in node.named_children:
        # ── decorated_definition: unwrap decorators + inner node ──────────
        decorators: tuple[str, ...] = ()
        actual = child
        if child.type == "decorated_definition":
            deco_list: list[str] = []
            inner: Node | None = None
            for sub in child.named_children:
                if sub.type == "decorator":
                    deco_list.append(_decorator_name(sub, src))
                else:
                    inner = sub
            if inner is None:
                continue
            decorators = tuple(deco_list)
            actual = inner

        # ── class_definition ──────────────────────────────────────────────
        if actual.type == "class_definition":
            name_node = actual.child_by_field_name("name")
            class_name = _text(name_node, src) if name_node else "?"
            is_dc = any(d in _DATACLASS_DECORATORS for d in decorators)
            body_node = actual.child_by_field_name("body")
            if body_node:
                new_q = f"{qualifier}{class_name}." if qualifier else f"{class_name}."
                yield from _walk(body_node, src, lines, new_q, is_dc, is_method=True)

        # ── function_definition / async_function_definition ───────────────
        elif actual.type in _FUNC_TYPES:
            info = _make_function_info(
                actual, src, lines, qualifier, parent_is_dataclass, is_method, decorators
            )
            if info:
                yield info
            body_node = actual.child_by_field_name("body")
            if body_node:
                fn_name_node = actual.child_by_field_name("name")
                fn_name = _text(fn_name_node, src) if fn_name_node else "?"
                yield from _walk(
                    body_node, src, lines, f"{qualifier}{fn_name}.", False, is_method=False
                )


# ---------------------------------------------------------------------------
# Public parser class
# ---------------------------------------------------------------------------


class PythonParser:
    """tree-sitter-backed parser for Python source files.

    Caches parsed ``FunctionInfo`` lists by source hash so multiple rules
    calling ``iter_functions`` on the same file within one run pay the
    tree-sitter parse cost only once.
    """

    def __init__(self) -> None:
        self._func_cache: dict[int, list[FunctionInfo]] = {}

    def iter_functions(self, source: str, path: Path) -> Iterator[FunctionInfo]:
        """Yield FunctionInfo for every function/method. Survives syntax errors.

        Args:
            source: Full source text of the file.
            path: File path (for qualified name prefixes and caching).
        """
        key = hash(source)
        if key not in self._func_cache:
            src_bytes = source.encode("utf-8")
            tree = _PARSER.parse(src_bytes)
            self._func_cache[key] = list(
                _walk(
                    tree.root_node,
                    src_bytes,
                    source.splitlines(),
                    qualifier="",
                    parent_is_dataclass=False,
                    is_method=False,
                )
            )
        yield from self._func_cache[key]

    def iter_comments(self, source: str, *, context_lines: int = 5) -> Iterator[CommentBlock]:
        """Yield comments + their following code window. Skips pragmas / TODOs.

        Args:
            source: Full source text of the file.
            context_lines: Lines of following code to capture per comment block.
        """
        lines = source.splitlines()
        for idx, raw in enumerate(lines):
            stripped = raw.lstrip()
            if not stripped.startswith("#"):
                continue
            if idx == 0 and stripped.startswith("#!"):
                continue
            if _PRAGMA_RE.match(raw):
                continue
            if _TODO_RE.match(raw):
                continue
            text = stripped[1:].strip()
            if len(text.split()) < _MIN_COMMENT_WORDS:
                continue
            following = "\n".join(
                ln
                for ln in lines[idx + 1 : idx + 1 + context_lines]
                if ln.strip() and not ln.lstrip().startswith("#")
            )
            if not following.strip():
                continue
            yield CommentBlock(text=text, line=idx + 1, following_code=following)
