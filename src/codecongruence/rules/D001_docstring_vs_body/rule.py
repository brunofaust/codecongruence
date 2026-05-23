"""Rule: docstring drift vs function body."""

from __future__ import annotations

from fnmatch import fnmatch
from typing import TYPE_CHECKING

from codecongruence.parsers import get_parser
from codecongruence.parsers.base import is_dataclass_init, is_overload_decorated
from codecongruence.rules.base import RuleViolation

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from codecongruence.core.config import RuleConfig
    from codecongruence.core.embedder import Embedder
    from codecongruence.core.git import ChangedFile

__all__ = ["DocstringVsBodyRule"]


class DocstringVsBodyRule:
    """Flag functions whose docstring diverges from the body."""

    rule_id: str = "docstring_vs_body"
    code: str = "D001"
    description: str = "Docstring should describe what the function actually does."
    default_threshold: float = 0.30

    def _excluded(self, path: Path, patterns: Sequence[str]) -> bool:
        return any(fnmatch(str(path), pat) for pat in patterns)

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
        threshold = self.default_threshold if config.threshold is None else config.threshold
        min_stmts = int(getattr(config, "body_statements_threshold", 3) or 3)
        min_doc = int(getattr(config, "min_docstring_chars", 10) or 10)
        exclude: list[str] = list(getattr(config, "exclude", []) or [])

        violations: list[RuleViolation] = []
        for cf in changed_files:
            parser = get_parser(cf.path.suffix)
            if parser is None or self._excluded(cf.path, exclude):
                continue
            try:
                source = cf.path.read_text(encoding="utf-8")
            except OSError:
                continue

            for func in parser.iter_functions(source, cf.path):
                if not func.docstring or len(func.docstring) < min_doc:
                    continue
                if func.body_statements < min_stmts:
                    continue
                if is_overload_decorated(func.decorators) or is_dataclass_init(func):
                    continue
                if cf.added_ranges and not cf.overlaps(func.line_start, func.line_end):
                    continue

                sim = embedder.similarity(func.docstring, func.body_source)
                if sim < threshold:
                    violations.append(
                        RuleViolation(
                            rule_id=self.rule_id,
                            code=self.code,
                            file_path=str(cf.path),
                            line=func.line_start,
                            message=(
                                f"Docstring drift on `{func.qualified_name}` "
                                f"(similarity {sim:.2f} < {threshold:.2f}). "
                                "Update the docstring to match what the body actually does."
                            ),
                            similarity=sim,
                            threshold=threshold,
                        )
                    )
        return violations
