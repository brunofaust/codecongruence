"""Rule: all function parameters should appear somewhere in the docstring."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from codecongruence.parsers import get_parser
from codecongruence.parsers.base import is_dataclass_init, is_overload_decorated
from codecongruence.rules.base import RuleViolation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from codecongruence.core.config import RuleConfig
    from codecongruence.core.embedder import Embedder
    from codecongruence.core.git import ChangedFile

__all__ = ["ParamsInDocstringRule"]


class ParamsInDocstringRule:
    """Catches ``def process(user, record)`` with a docstring that mentions neither."""

    rule_id: str = "params_in_docstring"
    code: str = "D006"
    description: str = "Every parameter should be mentioned somewhere in the docstring."
    default_threshold: float = 0.0  # structural, no embeddings

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
        skip_variadic: bool = bool(getattr(config, "skip_variadic", True))

        violations: list[RuleViolation] = []
        for cf in changed_files:
            parser = get_parser(cf.path.suffix)
            if parser is None:
                continue
            try:
                source = cf.path.read_text(encoding="utf-8")
            except OSError:
                continue

            for func in parser.iter_functions(source, cf.path):
                if not func.docstring:
                    continue
                if is_overload_decorated(func.decorators) or is_dataclass_init(func):
                    continue
                if cf.added_ranges and not cf.overlaps(func.line_start, func.line_end):
                    continue

                params = func.parameters
                if skip_variadic:
                    params = tuple(p for p in params if not p.startswith("*"))
                if not params:
                    continue

                missing = [p for p in params if not _mentioned(p, func.docstring)]
                if missing:
                    violations.append(
                        RuleViolation(
                            rule_id=self.rule_id,
                            code=self.code,
                            file_path=str(cf.path),
                            line=func.line_start,
                            message=(
                                f"`{func.qualified_name}` has undocumented parameter(s): "
                                f"{', '.join(missing)}. "
                                "Add them to the docstring."
                            ),
                            similarity=0.0,
                            threshold=0.0,
                        )
                    )
        return violations


def _mentioned(param_name: str, docstring: str) -> bool:
    """True if param_name appears as a whole word anywhere in the docstring."""
    return bool(re.search(r"\b" + re.escape(param_name) + r"\b", docstring))
