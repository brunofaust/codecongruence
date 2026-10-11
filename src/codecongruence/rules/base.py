"""Rule protocol + shared dataclasses and the helpers every rule builds on."""

from __future__ import annotations

import dataclasses
import logging  # guard:allow — repo-wide convention is stdlib logging
import re
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from codecongruence.parsers import get_parser
from codecongruence.parsers.base import is_dataclass_init, is_overload_decorated

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from codecongruence.core.config import RuleConfig
    from codecongruence.core.embedder import Embedder
    from codecongruence.core.git import ChangedFile
    from codecongruence.parsers.base import FunctionInfo, LanguageParser

__all__ = [
    "DOCS_BASE_URL",
    "Rule",
    "RuleViolation",
    "Severity",
    "apply_excludes",
    "iter_function_candidates",
    "iter_parsed",
    "resolve_threshold",
    "similarity_violation",
    "strip_comments",
]

log = logging.getLogger(__name__)

DOCS_BASE_URL = "https://github.com/brunofaust/codecongruence/blob/main/src/codecongruence/rules"

# Matches inline and full-line comments for Python (#) and JS/TS (//).
# (?<!:) preserves https:// URLs.
INLINE_COMMENT_RE = re.compile(r"(?<!:)\s*(?:#|//).*$", re.MULTILINE)


def strip_comments(source: str) -> str:
    """Remove inline and full-line comments, then drop resulting blank lines.

    Handles Python ``#`` and JS/TS ``//`` style comments.  Block-style
    ``/* … */`` comments are not stripped.

    Args:
        source: Raw function body source text.

    Returns:
        Source with ``#`` and ``//`` comments removed and blank lines stripped.
    """
    cleaned = INLINE_COMMENT_RE.sub("", source)
    return "\n".join(line for line in cleaned.splitlines() if line.strip())


Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class RuleViolation:
    """A single semantic-drift finding from a rule.

    ``code`` is the short stable identifier shown in reports (``C001``,
    ``D001``..``D005``). ``rule_id`` is the human-readable slug used in config
    and CLI flags. Both identify the same rule; ``code`` is what users grep
    logs for, ``rule_id`` is what they type.
    """

    rule_id: str
    code: str
    file_path: str
    line: int | None
    message: str
    similarity: float
    threshold: float
    severity: Severity = "error"
    docs_url: str | None = None


@runtime_checkable
class Rule(Protocol):
    """Protocol every built-in or third-party rule must satisfy.

    Built-in rules use codes ``C00x`` (code-identifier drift) and ``D00x``
    (documentation / artifact drift). Third-party rules SHOULD pick a unique
    code prefix to avoid collisions (e.g. ``X001`` for an experimental plugin).

    A rule MAY additionally define ``default_enabled: bool`` to declare itself
    opt-in (``False``). It applies only when the consumer's config has no
    ``[rules.<rule_id>]`` section; rules that omit the attribute default to
    enabled. It is deliberately not a required member of this protocol so that
    existing third-party rules keep satisfying it unchanged.
    """

    rule_id: str
    code: str
    description: str
    default_threshold: float
    docs_url: str

    async def check(
        self,
        changed_files: Sequence[ChangedFile],
        embedder: Embedder,
        config: RuleConfig,
    ) -> Sequence[RuleViolation]:
        """Return violations for ``changed_files``. Empty sequence means OK.

        Args:
            changed_files: Files to check (staged or all).
            embedder: Shared embedder instance for semantic similarity.
            config: Per-rule configuration (threshold, excludes, extras).
        """
        ...


def resolve_threshold(rule: Rule, config: RuleConfig) -> float:
    """Return the effective threshold: the config override or the rule default.

    Args:
        rule: The rule whose ``default_threshold`` applies when unconfigured.
        config: Per-rule configuration; ``threshold`` may be ``None``.

    Returns:
        The threshold this run should compare similarities against.
    """
    return rule.default_threshold if config.threshold is None else config.threshold


def iter_parsed(
    changed_files: Sequence[ChangedFile],
) -> Iterator[tuple[ChangedFile, LanguageParser, str]]:
    """Yield ``(changed_file, parser, source)`` for every parseable, readable file.

    Files with an unsupported extension or that cannot be read are skipped —
    the shared preamble of every per-function rule.

    Args:
        changed_files: Files to iterate (staged or all).

    Yields:
        One ``(changed_file, parser, source)`` triple per usable file.
    """
    for cf in changed_files:
        parser = get_parser(cf.path.suffix)
        if parser is None:
            continue
        try:
            source = cf.abs_path.read_text(encoding="utf-8")
        except OSError:
            continue
        yield cf, parser, source


def iter_function_candidates(
    changed_files: Sequence[ChangedFile],
    *,
    code: str,
    min_body_statement_count: int,
) -> Iterator[tuple[ChangedFile, FunctionInfo]]:
    """Yield ``(changed_file, function)`` pairs that pass the shared per-function skips.

    Skips ``@overload`` stubs and dataclass ``__init__``, bodies shorter than
    ``min_body_statement_count`` statements, and (in diff mode) functions that do
    not overlap the file's added lines. Each skip is debug-logged under ``code``.

    Args:
        changed_files: Files to iterate (staged or all).
        code: Rule code used as the debug-log prefix (e.g. ``"C001"``).
        min_body_statement_count: Minimum body statements a function needs.

    Yields:
        One ``(changed_file, function)`` pair per function worth checking.
    """
    for cf, parser, source in iter_parsed(changed_files):
        for func in cf.iter_functions(parser, source):
            if is_overload_decorated(func.decorators) or is_dataclass_init(func):
                log.debug(
                    "%s SKIP overload_or_dataclass %s::%s", code, cf.path, func.qualified_name
                )
                continue
            if func.body_statements < min_body_statement_count:
                log.debug(
                    "%s SKIP short_body %s::%s  stmts=%d  min=%d",
                    code,
                    cf.path,
                    func.qualified_name,
                    func.body_statements,
                    min_body_statement_count,
                )
                continue
            if cf.added_ranges and not cf.overlaps(func.line_start, func.line_end):
                log.debug("%s SKIP not_in_diff %s::%s", code, cf.path, func.qualified_name)
                continue
            yield cf, func


async def similarity_violation(
    embedder: Embedder,
    left: str,
    right: str,
    *,
    rule: Rule,
    threshold: float,
    file_path: str,
    line: int | None,
    log_context: str,
    message_template: str,
) -> RuleViolation | None:
    """Embed ``left``/``right``, log the verdict, and build a violation on drift.

    The shared tail of every similarity rule: compute cosine similarity, emit
    the standard debug line, and return a :class:`RuleViolation` when the
    similarity falls below ``threshold`` (``None`` otherwise).

    Args:
        embedder: Shared embedder for semantic similarity.
        left: First text (name, docstring, comment, doc diff, …).
        right: Second text (body, following code, code diff, …).
        rule: The rule reporting the violation (supplies ``rule_id``/``code``).
        threshold: Effective threshold from :func:`resolve_threshold`.
        file_path: File the violation is reported on.
        line: Line the violation anchors to, or ``None`` for whole-run checks.
        log_context: Prefix for the debug line (e.g. ``"C001 src/x.py::f"``).
        message_template: Violation message; ``{sim}`` and ``{threshold}``
            placeholders are filled with the computed values.

    Returns:
        A :class:`RuleViolation` when ``sim < threshold``, else ``None``.
    """
    sim = await embedder.similarity(left, right)
    log.debug(
        "%s  left=%r  right=%r  sim=%.3f  threshold=%.3f  %s",
        log_context,
        left[:120],
        right[:120],
        sim,
        threshold,
        "FAIL" if sim < threshold else "PASS",
    )
    if sim >= threshold:
        return None
    return RuleViolation(
        rule_id=rule.rule_id,
        code=rule.code,
        file_path=file_path,
        line=line,
        message=message_template.format(sim=sim, threshold=threshold),
        similarity=sim,
        threshold=threshold,
    )


def apply_excludes(changed: Sequence[ChangedFile], config: RuleConfig) -> list[ChangedFile]:
    """Drop files matching ``exclude`` and mark functions matching ``exclude_functions``.

    Args:
        changed: Files a rule would check.
        config: The rule's configuration (global excludes already merged in).

    Returns:
        The kept files, each carrying its excluded function ranges.
    """
    kept = [cf for cf in changed if not any(fnmatch(str(cf.path), p) for p in config.exclude)]
    if not config.exclude_functions:
        return kept
    result: list[ChangedFile] = []
    for cf in kept:
        parser = get_parser(cf.path.suffix)
        if parser is None:
            result.append(cf)
            continue
        try:
            source = cf.abs_path.read_text(encoding="utf-8")
        except OSError:
            result.append(cf)
            continue
        excluded = tuple(
            (func.line_start, func.line_end)
            for func in parser.iter_functions(source, cf.path)
            if any(fnmatch(func.qualified_name, pat) for pat in config.exclude_functions)
        )
        result.append(dataclasses.replace(cf, excluded_fn_ranges=excluded) if excluded else cf)
    return result
