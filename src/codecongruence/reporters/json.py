"""Machine-readable JSON reporter for CI consumers."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from collections.abc import Sequence

    from codecongruence.core.backend import ResolvedBackend
    from codecongruence.core.baseline import BaselineEntry
    from codecongruence.core.runner import RunResult

__all__ = ["JsonReporter"]


class JsonReporter:
    """Emit a single JSON document with violations + run metadata."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout

    def report(
        self,
        result: RunResult,
        *,
        stale_baseline: Sequence[BaselineEntry] = (),
        backend: ResolvedBackend | None = None,
    ) -> None:
        """Write a single JSON document with violations and run metadata to ``stream``.

        Args:
            result: The run result to serialise.
            stale_baseline: Baseline entries whose violation no longer exists; any
                entry makes ``ok`` false.
            backend: The run's resolved embedding backend; recorded as ``backend``
                (and ``backend_reason`` after an ``auto`` fallback). Omitted when ``None``.
        """
        payload = {
            "ok": result.ok and not stale_baseline,
            "rules_run": list(result.rules_run),
            "stale_baseline_entries": [asdict(e) for e in stale_baseline],
            "files_checked": [str(p) for p in result.files_checked],
            "violations": [
                {
                    **asdict(v),
                }
                for v in result.violations
            ],
        }
        if backend is not None:
            payload["backend"] = backend.kind
            if backend.reason is not None:
                payload["backend_reason"] = backend.reason
        json.dump(payload, self.stream, indent=2, sort_keys=True)
        self.stream.write("\n")
