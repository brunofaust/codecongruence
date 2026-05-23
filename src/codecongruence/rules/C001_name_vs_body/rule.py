"""Rule: function/class name vs body — catches mislabelled functions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from codecongruence.parsers import get_parser
from codecongruence.parsers.base import is_dataclass_init, is_overload_decorated, split_identifier
from codecongruence.rules.base import RuleViolation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from codecongruence.core.config import RuleConfig
    from codecongruence.core.embedder import Embedder
    from codecongruence.core.git import ChangedFile

__all__ = ["NameVsBodyRule"]

_GENERIC_NAMES_DEFAULT: frozenset[str] = frozenset({
    "main",
    "run",
    "setup",
    "handle",
    "process",
    "execute",
})
_MIN_BODY_STATEMENTS = 2


class NameVsBodyRule:
    """Flag ``get_user()`` that deletes, ``validate_email()`` that sends email, etc."""

    rule_id: str = "name_vs_body"
    code: str = "C001"
    description: str = "Function/class name should align with what its body does."
    default_threshold: float = 0.25

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
        threshold = self.default_threshold if config.threshold is None else config.threshold
        ignore: frozenset[str] = frozenset(
            getattr(config, "ignore_names", None) or _GENERIC_NAMES_DEFAULT
        )

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
                if func.name in ignore or func.name.startswith("test_"):
                    continue
                if is_overload_decorated(func.decorators) or is_dataclass_init(func):
                    continue
                if func.body_statements < _MIN_BODY_STATEMENTS:
                    continue
                if cf.added_ranges and not cf.overlaps(func.line_start, func.line_end):
                    continue

                name_expanded = split_identifier(func.name)
                if not name_expanded or len(name_expanded.split()) < 1:
                    continue

                sim = embedder.similarity(name_expanded, func.body_source)
                if sim < threshold:
                    violations.append(
                        RuleViolation(
                            rule_id=self.rule_id,
                            code=self.code,
                            file_path=str(cf.path),
                            line=func.line_start,
                            message=(
                                f"Name drift on `{func.qualified_name}` "
                                f"(similarity {sim:.2f} < {threshold:.2f}). "
                                "Rename it or change the body so the two agree."
                            ),
                            similarity=sim,
                            threshold=threshold,
                        )
                    )
        return violations
