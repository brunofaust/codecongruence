"""Machine-readable JSON reporter for CI consumers."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from codecongruence.core.runner import RunResult

__all__ = ["JsonReporter"]


class JsonReporter:
    """Emit a single JSON document with violations + run metadata."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout

    def report(self, result: RunResult) -> None:
        """Write a single JSON document with violations and run metadata to ``stream``."""
        payload = {
            "ok": result.ok,
            "rules_run": list(result.rules_run),
            "files_checked": [str(p) for p in result.files_checked],
            "violations": [
                {
                    **asdict(v),
                }
                for v in result.violations
            ],
        }
        json.dump(payload, self.stream, indent=2, sort_keys=True)
        self.stream.write("\n")
