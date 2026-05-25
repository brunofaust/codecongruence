"""Rule: parameter name vs how the parameter is used in the function body."""

from __future__ import annotations

import logging
import re
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

__all__ = ["ParamNameVsUsageRule"]


class ParamNameVsUsageRule:
    """Flag ``save_document(user_data)`` that only manipulates billing records, etc."""

    rule_id: str = "param_name_vs_usage"
    code: str = "C002"
    description: str = "Parameter name should align with how it is used in the function body."
    default_threshold: float = 0.20
    docs_url: str = (
        "https://github.com/brunofaust/codecongruence/blob/main"
        "/src/codecongruence/rules/C002_param_name_vs_usage/README.md"
    )

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
        """Check each parameter name against how it is used in the function body.

        Args:
            changed_files: Files to check (staged or all).
            embedder: Shared embedder for semantic similarity.
            config: Per-rule configuration (threshold, excludes, extras).

        Returns:
            Sequence of :class:`RuleViolation` for each mismatched parameter.
        """
        threshold = self.default_threshold if config.threshold is None else config.threshold
        min_body_statement_count = int(getattr(config, "min_body_statement_count", 2) or 2)
        min_param_name_chars = int(getattr(config, "min_param_name_chars", 2) or 2)
        include_comments = bool(getattr(config, "include_comments", True))

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
                if is_overload_decorated(func.decorators) or is_dataclass_init(func):
                    log.debug(
                        "C002 SKIP overload_or_dataclass %s::%s", cf.path, func.qualified_name
                    )
                    continue
                if func.body_statements < min_body_statement_count:
                    log.debug(
                        "C002 SKIP short_body %s::%s  stmts=%d  min=%d",
                        cf.path,
                        func.qualified_name,
                        func.body_statements,
                        min_body_statement_count,
                    )
                    continue
                if cf.added_ranges and not cf.overlaps(func.line_start, func.line_end):
                    log.debug("C002 SKIP not_in_diff %s::%s", cf.path, func.qualified_name)
                    continue

                body = func.body_source if include_comments else strip_comments(func.body_source)
                details_map = {name: (ann, dflt) for name, ann, dflt in func.parameter_details}
                for param in func.parameters:
                    clean = param.lstrip("*")
                    if len(clean) < min_param_name_chars:
                        log.debug(
                            "C002 SKIP short_param %s::%s  param=%s",
                            cf.path,
                            func.qualified_name,
                            clean,
                        )
                        continue

                    usage = _usage_context(clean, body)
                    if not usage:
                        log.debug(
                            "C002 SKIP unused_param %s::%s  param=%s",
                            cf.path,
                            func.qualified_name,
                            clean,
                        )
                        continue

                    annotation, default = details_map.get(clean, ("", ""))
                    left = " ".join(filter(None, [split_identifier(clean), annotation, default]))
                    sim = await embedder.similarity(left, usage)
                    log.debug(
                        "C002 %s::%s  param=%s  left=%r  right=%r  sim=%.3f  threshold=%.3f  %s",
                        cf.path,
                        func.qualified_name,
                        clean,
                        left,
                        usage[:120],
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
                                    f"Parameter `{param}` in `{func.qualified_name}` "
                                    f"doesn't match its usage "
                                    f"(similarity {sim:.2f} < {threshold:.2f}). "
                                    "Rename the parameter or change how it is used."
                                ),
                                similarity=sim,
                                threshold=threshold,
                            )
                        )
        return violations


def _usage_context(param_name: str, body_source: str) -> str:
    """Return lines from body_source that reference param_name, with the name stripped out.

    Stripping the name before embedding lets us compare what the name *suggests*
    against the operations performed around the parameter, rather than matching
    the parameter's own tokens against themselves.
    """
    pattern = re.compile(r"\b" + re.escape(param_name) + r"\b")
    stripped = [pattern.sub("", line) for line in body_source.splitlines() if pattern.search(line)]
    return "\n".join(line for line in stripped if line.strip())
