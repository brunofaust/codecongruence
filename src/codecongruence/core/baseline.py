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
different line makes the old entry stale — it falls off the baseline on the next
``--update-baseline``.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from codecongruence.core.runner import RunResult
    from codecongruence.rules.base import RuleViolation

__all__ = [
    "Baseline",
    "BaselineEntry",
    "apply_baseline",
    "baseline_path",
    "load_baseline",
    "save_baseline",
]

_BASELINE_FILENAME = ".codecongruence-baseline.json"
_FORMAT_VERSION = 1


@dataclass(frozen=True, slots=True)
class BaselineEntry:
    """Uniquely identifies one violation in the saved baseline."""

    rule_id: str
    file_path: str
    line: int | None


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


def baseline_path(repo_root: Path) -> Path:
    """Return the canonical baseline file path for *repo_root*.

    Args:
        repo_root: Repository root directory.

    Returns:
        ``<repo_root>/.codecongruence/.codecongruence-baseline.json``
    """
    return repo_root / ".codecongruence" / _BASELINE_FILENAME
