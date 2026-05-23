"""JavaScript / TypeScript language parser backed by tree-sitter.

Handles ``.js``, ``.jsx``, ``.ts``, and ``.tsx`` files with a single class
parameterised by the tree-sitter Language object.  Instantiate once per
language variant and register each extension in ``parsers/__init__.py``.

Supported constructs:
- ``function`` declarations and generator functions
- Class ``method_definition`` (including static / async variants)
- Named arrow functions and function expressions (``const f = () => ...``)
- JSDoc comments (``/** ... */``) preceding the function are used as the
  "docstring" so D001 and D006 work for JS/TS out of the box.

TypeScript-specific parameter nodes (``required_parameter``,
``optional_parameter``) are handled in addition to the plain JS ones.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from tree_sitter import Language, Node, Parser

from codecongruence.parsers.base import CommentBlock, FunctionInfo

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

__all__ = ["JavaScriptParser"]

_MIN_COMMENT_WORDS = 4
_TODO_RE = re.compile(r"^\s*(TODO|FIXME|NOTE|HACK|XXX)\b", re.IGNORECASE)

_FUNC_DECL_TYPES = frozenset({
    "function_declaration",
    "generator_function_declaration",
})
_VAR_DECL_TYPES = frozenset({"lexical_declaration", "variable_declaration"})
_FUNC_VALUE_TYPES = frozenset({"arrow_function", "function_expression"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _text(node: Node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _parse_jsdoc(raw: str) -> str:
    """Strip ``/** ... */`` delimiters and leading ``*`` from each line.

    Args:
        raw: Raw comment text including ``/**`` and ``*/`` delimiters.

    Returns:
        Clean text with delimiters and leading asterisks removed.
    """
    inner = raw.strip()
    if inner.startswith("/**"):
        inner = inner[3:]
    if inner.endswith("*/"):
        inner = inner[:-2]
    lines = [line.lstrip().lstrip("*").strip() for line in inner.splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_js_params(node: Node, src: bytes) -> tuple[str, ...]:
    """Extract parameter names from a ``formal_parameters`` or bare identifier node.

    Handles plain JS identifiers, defaults, rest patterns, and TypeScript
    ``required_parameter`` / ``optional_parameter`` nodes.  Skips destructured
    patterns (``object_pattern``, ``array_pattern``) since they have no single name.

    Args:
        node: The function AST node whose parameters to extract.
        src: Raw source bytes of the file.

    Returns:
        Tuple of parameter name strings; variadic names are prefixed with ``*``.
    """
    params_node = node.child_by_field_name("parameters")
    if params_node is None:
        # Arrow function with a single bare parameter: ``x => x + 1``
        if node.type == "arrow_function":
            for child in node.named_children:
                if child.type == "identifier":
                    return (_text(child, src),)
        return ()

    names: list[str] = []
    for child in params_node.named_children:
        name: str | None = None
        match child.type:
            case "identifier":
                name = _text(child, src)
            case "assignment_pattern":
                left = child.child_by_field_name("left")
                if left is not None and left.type == "identifier":
                    name = _text(left, src)
            case "rest_pattern":
                inner = next((c for c in child.named_children if c.type == "identifier"), None)
                if inner is not None:
                    name = "*" + _text(inner, src)
            # TypeScript typed parameters
            case "required_parameter" | "optional_parameter":
                pattern = child.child_by_field_name("pattern") or next(
                    (c for c in child.named_children if c.type == "identifier"), None
                )
                if pattern is not None and pattern.type == "identifier":
                    name = _text(pattern, src)
        if name:
            names.append(name)
    return tuple(names)


def _js_body_source(node: Node, lines: list[str]) -> str:
    """Return the inner content of a ``statement_block``, skipping ``{``/``}``.

    Args:
        node: The body AST node (``statement_block`` or expression for arrow fns).
        lines: Source lines of the file (0-indexed).
    """
    if node.type != "statement_block":
        # Arrow function with expression body — return the whole expression text
        start = node.start_point[0]
        end = node.end_point[0]
        return "\n".join(lines[start : end + 1])

    named = node.named_children
    if not named:
        return ""
    start = named[0].start_point[0]
    end = named[-1].end_point[0]
    return "\n".join(lines[start : end + 1])


def _make_js_function(
    node: Node,
    src: bytes,
    lines: list[str],
    qualifier: str,
    is_method: bool,
    jsdoc: str | None,
    override_name: str | None = None,
) -> FunctionInfo | None:
    """Build a FunctionInfo from a JS/TS function node.

    Args:
        node: The JS/TS function AST node.
        src: Raw source bytes of the file.
        lines: Source lines of the file (0-indexed).
        qualifier: Dotted class/function prefix for the qualified name.
        is_method: Whether this function is a class method.
        jsdoc: Parsed JSDoc text preceding the node, or ``None``.
        override_name: Use this name instead of the node's own name field.

    Returns:
        A populated :class:`FunctionInfo`, or ``None`` when a required node is missing.
    """
    # Name resolution
    if override_name is not None:
        name = override_name
    else:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return None
        name = _text(name_node, src)

    body_node = node.child_by_field_name("body")
    if body_node is None:
        return None

    body_src = _js_body_source(body_node, lines)
    stmt_count = len(body_node.named_children)

    return FunctionInfo(
        name=name,
        qualified_name=f"{qualifier}{name}",
        docstring=jsdoc,
        body_source=body_src,
        line_start=node.start_point[0] + 1,
        line_end=node.end_point[0] + 1,
        decorators=(),
        is_method=is_method,
        parent_is_dataclass=False,
        body_statements=stmt_count,
        parameters=_extract_js_params(node, src),
    )


def _walk_js(
    node: Node,
    src: bytes,
    lines: list[str],
    qualifier: str,
    is_method: bool,
) -> Iterator[FunctionInfo]:
    """Recursively walk a tree node, yielding every JS/TS function found.

    Args:
        node: The current tree-sitter AST node to descend into.
        src: Raw source bytes of the file.
        lines: Source lines of the file (0-indexed).
        qualifier: Dotted class/function prefix for qualified names.
        is_method: Whether children of this node are class methods.

    Yields:
        One :class:`FunctionInfo` per function/method encountered.
    """
    prev_jsdoc: str | None = None

    for child in node.named_children:
        # Track JSDoc comments — they apply to the immediately following node.
        if child.type == "comment":
            raw = _text(child, src)
            prev_jsdoc = _parse_jsdoc(raw) if raw.lstrip().startswith("/**") else None
            continue

        jsdoc = prev_jsdoc
        prev_jsdoc = None  # consumed

        # ── standalone function declaration ──────────────────────────────
        if child.type in _FUNC_DECL_TYPES:
            info = _make_js_function(child, src, lines, qualifier, False, jsdoc)
            if info:
                yield info
                body = child.child_by_field_name("body")
                if body:
                    yield from _walk_js(body, src, lines, f"{qualifier}{info.name}.", False)

        # ── class declaration ─────────────────────────────────────────────
        elif child.type in {"class_declaration", "class"}:
            name_node = child.child_by_field_name("name")
            class_name = _text(name_node, src) if name_node else "?"
            body = child.child_by_field_name("body")
            if body:
                new_q = f"{qualifier}{class_name}." if qualifier else f"{class_name}."
                yield from _walk_js(body, src, lines, new_q, True)

        # ── method definition ─────────────────────────────────────────────
        elif child.type == "method_definition":
            info = _make_js_function(child, src, lines, qualifier, True, jsdoc)
            if info:
                yield info
                body = child.child_by_field_name("body")
                if body:
                    yield from _walk_js(body, src, lines, f"{qualifier}{info.name}.", False)

        # ── const/let/var with arrow / function expression ────────────────
        elif child.type in _VAR_DECL_TYPES:
            yield from _walk_var_decl(child, src, lines, qualifier, jsdoc)

        # ── export statement wrapping a function/class ────────────────────
        elif child.type in {"export_statement", "export_default_declaration"}:
            # Pass jsdoc through; recurse treating the export as transparent.
            yield from _walk_export(child, src, lines, qualifier, jsdoc)


def _walk_var_decl(
    node: Node,
    src: bytes,
    lines: list[str],
    qualifier: str,
    jsdoc: str | None,
) -> Iterator[FunctionInfo]:
    """Handle ``const f = () => ...`` and ``const f = function() {...}``.

    Args:
        node: The ``lexical_declaration`` or ``variable_declaration`` AST node.
        src: Raw source bytes of the file.
        lines: Source lines of the file (0-indexed).
        qualifier: Dotted prefix for qualified names.
        jsdoc: JSDoc comment preceding this declaration, or ``None``.

    Yields:
        One :class:`FunctionInfo` per named arrow/function-expression declarator.
    """
    for decl in node.named_children:
        if decl.type != "variable_declarator":
            continue
        name_node = decl.child_by_field_name("name")
        value_node = decl.child_by_field_name("value")
        if name_node is None or value_node is None:
            continue
        if name_node.type != "identifier":
            continue
        if value_node.type not in _FUNC_VALUE_TYPES:
            continue
        var_name = _text(name_node, src)
        info = _make_js_function(
            value_node, src, lines, qualifier, False, jsdoc, override_name=var_name
        )
        if info:
            yield info
            body = value_node.child_by_field_name("body")
            if body:
                yield from _walk_js(body, src, lines, f"{qualifier}{var_name}.", False)


def _walk_export(
    node: Node,
    src: bytes,
    lines: list[str],
    qualifier: str,
    jsdoc: str | None,
) -> Iterator[FunctionInfo]:
    """Unwrap an export statement and yield inner functions/classes.

    Args:
        node: The ``export_statement`` or ``export_default_declaration`` AST node.
        src: Raw source bytes of the file.
        lines: Source lines of the file (0-indexed).
        qualifier: Dotted prefix for qualified names.
        jsdoc: JSDoc comment preceding this export, or ``None``.

    Yields:
        One :class:`FunctionInfo` per exported function, class method, or variable.
    """
    for child in node.named_children:
        if child.type in _FUNC_DECL_TYPES:
            info = _make_js_function(child, src, lines, qualifier, False, jsdoc)
            if info:
                yield info
                body = child.child_by_field_name("body")
                if body:
                    yield from _walk_js(body, src, lines, f"{qualifier}{info.name}.", False)
        elif child.type in {"class_declaration", "class"}:
            name_node = child.child_by_field_name("name")
            class_name = _text(name_node, src) if name_node else "?"
            body = child.child_by_field_name("body")
            if body:
                new_q = f"{qualifier}{class_name}." if qualifier else f"{class_name}."
                yield from _walk_js(body, src, lines, new_q, True)
        elif child.type in _VAR_DECL_TYPES:
            yield from _walk_var_decl(child, src, lines, qualifier, jsdoc)


# ---------------------------------------------------------------------------
# Public parser class
# ---------------------------------------------------------------------------


class JavaScriptParser:
    """tree-sitter-backed parser for JS/TS source files.

    Pass the appropriate ``Language`` object at construction:
    - ``Language(tree_sitter_javascript.language())`` for ``.js`` / ``.jsx``
    - ``Language(tree_sitter_typescript.language_typescript())`` for ``.ts``
    - ``Language(tree_sitter_typescript.language_tsx())`` for ``.tsx``

    Parse results are cached in-memory by source hash so multiple rules in a
    single run don't pay the tree-sitter cost more than once per file.
    """

    def __init__(self, language: Language) -> None:
        self._ts_parser = Parser(language)
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
            tree = self._ts_parser.parse(src_bytes)
            self._func_cache[key] = list(
                _walk_js(tree.root_node, src_bytes, source.splitlines(), "", False)
            )
        yield from self._func_cache[key]

    def iter_comments(self, source: str, *, context_lines: int = 5) -> Iterator[CommentBlock]:
        """Yield ``//`` inline comments with the code that follows them.

        Skips JSDoc (``/**``), block comments (``/*``), TODO/FIXME markers,
        and shebangs.  Single-line comments with fewer than
        ``_MIN_COMMENT_WORDS`` words are also skipped.

        Args:
            source: Full source text of the file.
            context_lines: Lines of following code to capture per comment block.
        """
        lines = source.splitlines()
        for idx, raw in enumerate(lines):
            stripped = raw.lstrip()
            if not stripped.startswith("//"):
                continue
            if stripped.startswith("///"):  # TS triple-slash reference — skip
                continue
            text = stripped[2:].strip()
            if _TODO_RE.match(text):
                continue
            if len(text.split()) < _MIN_COMMENT_WORDS:
                continue
            following = "\n".join(
                ln
                for ln in lines[idx + 1 : idx + 1 + context_lines]
                if ln.strip() and not ln.lstrip().startswith("//")
            )
            if not following.strip():
                continue
            yield CommentBlock(text=text, line=idx + 1, following_code=following)
