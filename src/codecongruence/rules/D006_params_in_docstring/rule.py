"""Rule: all function parameters should appear somewhere in the docstring."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from codecongruence.parsers import get_parser
from codecongruence.parsers.base import is_dataclass_init, is_overload_decorated
from codecongruence.rules.base import RuleViolation

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from codecongruence.core.config import RuleConfig
    from codecongruence.core.embedder import Embedder
    from codecongruence.core.git import ChangedFile

__all__ = ["ParamsInDocstringRule", "mentioned"]


class ParamsInDocstringRule:
    """Catches ``def process(user, record)`` with a docstring that mentions neither."""

    rule_id: str = "params_in_docstring"
    code: str = "D006"
    description: str = "Every parameter should be mentioned somewhere in the docstring."
    default_threshold: float = 0.0  # structural, no embeddings
    docs_url: str = (
        "https://github.com/brunofaust/codecongruence/blob/main"
        "/src/codecongruence/rules/D006_params_in_docstring/README.md"
    )

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
        """Check that every parameter is mentioned somewhere in the docstring.

        Args:
            changed_files: Files to check (staged or all).
            embedder: Shared embedder (unused by this structural rule).
            config: Per-rule configuration (skip_variadic, ignore_dunders, excludes).

        Returns:
            Sequence of :class:`RuleViolation` for each undocumented parameter.
        """
        skip_variadic: bool = bool(getattr(config, "skip_variadic", True))
        ignore_dunders: bool = bool(getattr(config, "ignore_dunders", True))

        violations: list[RuleViolation] = []
        for cf in changed_files:
            parser = get_parser(cf.path.suffix)
            if parser is None:
                continue
            try:
                source = cf.path.read_text(encoding="utf-8")
            except OSError:
                continue

            for func in cf.iter_functions(parser, source):
                if not func.docstring:
                    log.debug("D006 SKIP no_docstring %s::%s", cf.path, func.qualified_name)
                    continue
                if is_overload_decorated(func.decorators) or is_dataclass_init(func):
                    log.debug(
                        "D006 SKIP overload_or_dataclass %s::%s", cf.path, func.qualified_name
                    )
                    continue
                is_dunder = func.name.startswith("__") and func.name.endswith("__")
                if ignore_dunders and is_dunder:
                    log.debug("D006 SKIP dunder %s::%s", cf.path, func.name)
                    continue
                if cf.added_ranges and not cf.overlaps(func.line_start, func.line_end):
                    log.debug("D006 SKIP not_in_diff %s::%s", cf.path, func.qualified_name)
                    continue

                params = func.parameters
                if skip_variadic:
                    params = tuple(p for p in params if not p.startswith("*"))
                if not params:
                    log.debug("D006 SKIP no_params %s::%s", cf.path, func.qualified_name)
                    continue

                missing = [p for p in params if not mentioned(p, func.docstring)]
                log.debug(
                    "D006 %s::%s  params=%s  missing=%s  %s",
                    cf.path,
                    func.name,
                    list(params),
                    missing,
                    "FAIL" if missing else "PASS",
                )
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


def mentioned(param_name: str, docstring: str) -> bool:
    """True if param_name appears as a whole word anywhere in the docstring.

    Returns:
        ``True`` when ``param_name`` matches at a word boundary inside ``docstring``.
    """
    return bool(re.search(r"\b" + re.escape(param_name) + r"\b", docstring))
