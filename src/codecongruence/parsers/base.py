"""Shared types, protocol, and utilities for all language parsers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

__all__ = [
    "CommentBlock",
    "FunctionInfo",
    "LanguageParser",
    "is_dataclass_init",
    "is_overload_decorated",
    "split_identifier",
]

_OVERLOAD_DECORATORS: frozenset[str] = frozenset({"overload", "typing.overload"})


@dataclass(frozen=True, slots=True)
class FunctionInfo:
    """Information about a single function/method definition."""

    name: str
    qualified_name: str
    docstring: str | None
    body_source: str
    line_start: int
    line_end: int
    decorators: tuple[str, ...]
    is_method: bool
    parent_is_dataclass: bool
    body_statements: int
    parameters: tuple[str, ...]  # plain names; variadic prefixed with * or **


@dataclass(frozen=True, slots=True)
class CommentBlock:
    """A comment line with the code that follows it (used by D002 stale_comments)."""

    text: str
    line: int
    following_code: str


@runtime_checkable
class LanguageParser(Protocol):
    """Protocol every language parser must satisfy.

    Implement this for each language and register it in ``parsers/__init__.py``.
    """

    def iter_functions(self, source: str, path: Path) -> Iterator[FunctionInfo]:
        """Yield FunctionInfo for each function/method in source."""
        ...

    def iter_comments(self, source: str, *, context_lines: int = 5) -> Iterator[CommentBlock]:
        """Yield CommentBlock for each meaningful inline comment."""
        ...


def is_overload_decorated(decorators: tuple[str, ...]) -> bool:
    """True if any decorator marks the function as ``typing.overload``."""
    return any(d in _OVERLOAD_DECORATORS for d in decorators)


def is_dataclass_init(func: FunctionInfo) -> bool:
    """True for ``__init__`` of a dataclass — auto-generated, nothing to check."""
    return func.name == "__init__" and func.parent_is_dataclass


_CAMEL_RE = re.compile(r"(?<!^)(?=[A-Z])")
_ABBREVIATIONS: dict[str, str] = {
    "id": "identifier",
    "ids": "identifiers",
    "db": "database",
    "ctx": "context",
    "cfg": "configuration",
    "conf": "configuration",
    "config": "configuration",
    "req": "request",
    "res": "response",
    "resp": "response",
    "msg": "message",
    "msgs": "messages",
    "auth": "authentication",
    "perm": "permission",
    "perms": "permissions",
    "fn": "function",
    "func": "function",
    "obj": "object",
    "str": "string",
    "num": "number",
    "args": "arguments",
    "kwargs": "keyword arguments",
    "doc": "document",
    "docs": "documents",
    "dir": "directory",
    "pkg": "package",
    "tmp": "temporary",
    "src": "source",
    "dst": "destination",
    "addr": "address",
    "url": "uniform resource locator",
}


def split_identifier(name: str) -> str:
    """Split camelCase / snake_case / PascalCase into space-separated words.

    Expands common abbreviations. Used by C001 to embed the function name.
    """
    snake = name.replace("_", " ")
    chunks: list[str] = []
    for word in snake.split():
        chunks.append(_CAMEL_RE.sub(" ", word).lower())
    return " ".join(_ABBREVIATIONS.get(tok, tok) for tok in " ".join(chunks).split()).strip()
