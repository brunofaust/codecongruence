"""Language parser registry — maps file extensions to LanguageParser instances.

Adding a new language:
1. Create ``parsers/<lang>.py`` implementing ``LanguageParser``.
2. Call ``register_parser(".ext", MyParser())`` here or from the module itself.
"""

from __future__ import annotations

from codecongruence.parsers.base import LanguageParser
from codecongruence.parsers.python import PythonParser

__all__ = ["get_parser", "register_parser"]

_REGISTRY: dict[str, LanguageParser] = {
    ".py": PythonParser(),
}


def register_parser(ext: str, parser: LanguageParser) -> None:
    """Register a parser for a file extension (e.g. ``.js``).

    Args:
        ext: Dotted file extension (e.g. ``".js"``, ``".ts"``).
        parser: Parser instance satisfying :class:`~codecongruence.parsers.base.LanguageParser`.
    """
    _REGISTRY[ext] = parser


def get_parser(ext: str) -> LanguageParser | None:
    """Return the parser for this extension, or ``None`` if unsupported.

    Args:
        ext: Dotted file extension (e.g. ``".py"``, ``".ts"``).
    """
    return _REGISTRY.get(ext)


# ---------------------------------------------------------------------------
# Optional JS / TS parsers — registered only when tree-sitter packages are
# installed so the library stays usable in Python-only environments.
# ---------------------------------------------------------------------------

try:
    import tree_sitter_javascript as _tsjs
    import tree_sitter_typescript as _tsts
    from tree_sitter import Language as _Language

    from codecongruence.parsers.javascript import JavaScriptParser

    _js_parser = JavaScriptParser(_Language(_tsjs.language()))
    _ts_parser = JavaScriptParser(_Language(_tsts.language_typescript()))
    _tsx_parser = JavaScriptParser(_Language(_tsts.language_tsx()))

    register_parser(".js", _js_parser)
    register_parser(".jsx", _js_parser)
    register_parser(".ts", _ts_parser)
    register_parser(".tsx", _tsx_parser)
except ImportError:
    pass
