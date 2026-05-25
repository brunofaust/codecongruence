"""Rule: function/class name vs body — catches mislabelled functions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codecongruence.parsers import get_parser
from codecongruence.parsers.base import is_dataclass_init, is_overload_decorated, split_identifier
from codecongruence.rules.base import RuleViolation, strip_comments

log = logging.getLogger(__name__)

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


class NameVsBodyRule:
    """Flag ``get_user()`` that deletes, ``validate_email()`` that sends email, etc."""

    rule_id: str = "name_vs_body"
    code: str = "C001"
    description: str = "Function/class name should align with what its body does."
    default_threshold: float = 0.25
    docs_url: str = (
        "https://github.com/brunofaust/codecongruence/blob/main"
        "/src/codecongruence/rules/C001_name_vs_body/README.md"
    )

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
        """Check for name/body drift in every changed function.

        Args:
            changed_files: Files to check (staged or all).
            embedder: Shared embedder for semantic similarity.
            config: Per-rule configuration (threshold, excludes, extras).

        Returns:
            Sequence of :class:`RuleViolation` for each mismatched function.
        """
        threshold = self.default_threshold if config.threshold is None else config.threshold
        min_body_statement_count = int(getattr(config, "min_body_statement_count", 2) or 2)
        include_comments = bool(getattr(config, "include_comments", False))
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

            for func in cf.iter_functions(parser, source):
                if func.name in ignore or func.name.startswith("test_"):
                    log.debug("C001 SKIP ignored_name %s::%s", cf.path, func.qualified_name)
                    continue
                if is_overload_decorated(func.decorators) or is_dataclass_init(func):
                    log.debug(
                        "C001 SKIP overload_or_dataclass %s::%s", cf.path, func.qualified_name
                    )
                    continue
                if func.body_statements < min_body_statement_count:
                    log.debug(
                        "C001 SKIP short_body %s::%s  stmts=%d  min=%d",
                        cf.path,
                        func.qualified_name,
                        func.body_statements,
                        min_body_statement_count,
                    )
                    continue
                if cf.added_ranges and not cf.overlaps(func.line_start, func.line_end):
                    log.debug("C001 SKIP not_in_diff %s::%s", cf.path, func.qualified_name)
                    continue

                name_expanded = split_identifier(func.name)
                if not name_expanded or len(name_expanded.split()) < 1:
                    log.debug("C001 SKIP empty_name %s::%s", cf.path, func.qualified_name)
                    continue

                body = func.body_source if include_comments else strip_comments(func.body_source)
                sim = await embedder.similarity(name_expanded, body)
                log.debug(
                    "C001 %s::%s  left=%r  right=%r  sim=%.3f  threshold=%.3f  %s",
                    cf.path,
                    func.qualified_name,
                    name_expanded,
                    body[:120],
                    sim,
                    threshold,
                    "FAIL" if sim < threshold else "PASS",
                )
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
