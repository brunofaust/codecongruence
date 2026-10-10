"""Baseline violation suppression.

Allows teams to adopt ``codecongruence`` incrementally by saving the current
set of violations as a baseline and only failing future runs on *new* violations
that were not in the baseline.

Usage:

1. ``codecongruence --update-baseline`` — run all rules, save all findings to
   ``.codecongruence/.codecongruence-baseline.json``, and exit 0.  Commit this
   file so every team member shares the same baseline.
2. Subsequent runs load the baseline automatically and suppress any violation
   that matches a saved entry.  Only *new* violations (not in the baseline) cause
   a non-zero exit.

Matching is exact on ``(rule_id, file_path, line)``.  Moving a function to a
different line, or fixing the violation, makes the old entry *stale*.  A stale
entry could later absorb a new finding that lands on the same key, so every run
reports stale entries and exits non-zero; ``--prune-baseline`` removes exactly
those entries and nothing else.

An entry is judged only when the rules could have re-found it: its file is in the
run's checked set (the ``ChangedFile`` list the runner fed the rules), its line
lies in that file's added line ranges (rules skip untouched code in diff mode;
an empty range list means the whole file was scanned), and its rule actually ran
(``RunResult.rules_run``).  File-scoped hook runs therefore never judge entries
for files or lines they did not look at.
Rules whose findings are not a function of one file are judged conservatively:
diff-scoped rules (``claude_md_vs_diff``, ``pr_description_vs_diff``,
``docs_on_change``) never, and the pairwise ``duplicate_functions`` only on a
full ``--all`` scan.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from codecongruence.core.git import ChangedFile
    from codecongruence.core.runner import RunResult
    from codecongruence.rules.base import RuleViolation

__all__ = [
    "Baseline",
    "BaselineEntry",
    "apply_baseline",
    "baseline_path",
    "find_stale",
    "load_baseline",
    "prune_baseline",
    "save_baseline",
]

_BASELINE_FILENAME = ".codecongruence-baseline.json"
_FORMAT_VERSION = 1
# Findings that depend on the staged diff / PR body, not on the file's content.
_DIFF_SCOPED_RULES = frozenset({"claude_md_vs_diff", "pr_description_vs_diff", "docs_on_change"})
# Findings that pair two files; complete only when every tracked file was checked.
_PAIRWISE_RULES = frozenset({"duplicate_functions"})


@dataclass(frozen=True, slots=True)
class BaselineEntry:
    """Uniquely identifies one violation in the saved baseline."""

    rule_id: str
    file_path: str
    line: int | None
    message: str | None = field(default=None, compare=False)


@dataclass(frozen=True, slots=True)
class Baseline:
    """Immutable snapshot of suppressed violations.

    Args:
        entries: Frozen set of all suppressed violation identities.
    """

    entries: frozenset[BaselineEntry]

    def is_suppressed(self, violation: RuleViolation) -> bool:
        """Return ``True`` if this violation matches a saved baseline entry.

        Args:
            violation: The violation to look up.

        Returns:
            ``True`` when the (rule_id, file_path, line) triple is in the baseline.
        """
        return (
            BaselineEntry(
                rule_id=violation.rule_id,
                file_path=violation.file_path,
                line=violation.line,
            )
            in self.entries
        )


def load_baseline(path: Path) -> Baseline | None:
    """Load a baseline from *path*, returning ``None`` when absent or unreadable.

    Args:
        path: Path to a ``.codecongruence/.codecongruence-baseline.json`` file.

    Returns:
        A :class:`Baseline` with the saved entries, or ``None`` if the file is
        missing or cannot be parsed.
    """
    if not path.exists():
        return None
    try:
        data: dict[object, object] = json.loads(path.read_text(encoding="utf-8"))
        violations = data.get("violations", [])
        if not isinstance(violations, list):
            return None
        entries = frozenset(
            BaselineEntry(
                rule_id=str(e["rule_id"]),
                file_path=str(e["file_path"]),
                line=int(e["line"]) if e.get("line") is not None else None,
                message=str(e["message"]) if e.get("message") is not None else None,
            )
            for e in violations
        )
        return Baseline(entries=entries)
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None


def save_baseline(violations: Sequence[RuleViolation], path: Path) -> None:
    """Persist *violations* as a baseline JSON file at *path*.

    Creates parent directories as needed.  The file records enough context
    (message, code) for human review, but only (rule_id, file_path, line) is
    used for suppression matching.

    Args:
        violations: All violations from the current run to save as accepted.
        path: Destination path (usually ``<repo_root>/.codecongruence/.codecongruence-baseline.json``).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _FORMAT_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "violations": [
            {
                "rule_id": v.rule_id,
                "code": v.code,
                "file_path": v.file_path,
                "line": v.line,
                "message": v.message,
            }
            for v in violations
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def apply_baseline(result: RunResult, baseline: Baseline) -> tuple[RunResult, int]:
    """Remove baseline violations from *result*, returning the filtered result.

    Args:
        result: The raw run result from the rule runner.
        baseline: The loaded baseline to apply.

    Returns:
        A ``(filtered_result, suppressed_count)`` pair.  ``suppressed_count``
        is the number of violations removed by the baseline.
    """
    new_violations = tuple(v for v in result.violations if not baseline.is_suppressed(v))
    suppressed = len(result.violations) - len(new_violations)
    return dataclasses.replace(result, violations=new_violations), suppressed


def _in_ranges(cf: ChangedFile, line: int | None) -> bool:
    return line is not None and cf.covers(line)


def find_stale(
    baseline: Baseline,
    result: RunResult,
    changed: Sequence[ChangedFile],
    *,
    full_scan: bool,
) -> tuple[BaselineEntry, ...]:
    """Return baseline entries whose violation no longer exists.

    An entry is stale iff it is in scope (see the module docstring: file in
    *changed*, line inside the file's added ranges or the file fully scanned, rule
    in ``result.rules_run``) and no violation in ``result`` has the same key.
    Call this on the *unfiltered* result.

    Args:
        baseline: The loaded baseline.
        result: The raw run result, before :func:`apply_baseline`.
        changed: The exact file list passed to the runner for this run.
        full_scan: ``True`` when every tracked file was checked (``--all``).

    Returns:
        Stale entries sorted by file, line and rule.
    """
    scope = {str(cf.path): cf for cf in changed}
    ran = set(result.rules_run) - _DIFF_SCOPED_RULES
    if not full_scan:
        ran -= _PAIRWISE_RULES
    live = {(v.rule_id, v.file_path, v.line) for v in result.violations}
    stale = [
        e
        for e in baseline.entries
        if e.rule_id in ran
        and e.file_path in scope
        and (not scope[e.file_path].added_ranges or _in_ranges(scope[e.file_path], e.line))
        and (e.rule_id, e.file_path, e.line) not in live
    ]
    return tuple(sorted(stale, key=lambda e: (e.file_path, e.line or 0, e.rule_id)))


def prune_baseline(path: Path, stale: Sequence[BaselineEntry]) -> int:
    """Remove exactly the *stale* entries from the baseline file at *path*.

    Remaining entries and top-level fields are written back unchanged.

    Args:
        path: The baseline JSON file.
        stale: Entries to drop, as returned by :func:`find_stale`.

    Returns:
        The number of entries removed.
    """
    drop = {(e.rule_id, e.file_path, e.line) for e in stale}
    data = json.loads(path.read_text(encoding="utf-8"))  # guard:allow
    kept = [
        v
        for v in data["violations"]
        if (str(v["rule_id"]), str(v["file_path"]), v.get("line")) not in drop
    ]
    removed = len(data["violations"]) - len(kept)
    if removed:
        data["violations"] = kept
        text = json.dumps(data, indent=2, sort_keys=True)  # guard:allow
        path.write_text(text + "\n", encoding="utf-8")
    return removed


def baseline_path(repo_root: Path) -> Path:
    """Return the canonical baseline file path for *repo_root*.

    Args:
        repo_root: Repository root directory.

    Returns:
        ``<repo_root>/.codecongruence/.codecongruence-baseline.json``
    """
    return repo_root / ".codecongruence" / _BASELINE_FILENAME
