"""Rule protocol + shared dataclasses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from codecongruence.core.config import RuleConfig
    from codecongruence.core.embedder import Embedder
    from codecongruence.core.git import ChangedFile

__all__ = ["Rule", "RuleViolation", "Severity"]


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


@runtime_checkable
class Rule(Protocol):
    """Protocol every built-in or third-party rule must satisfy.

    Built-in rules use codes ``C00x`` (code-identifier drift) and ``D00x``
    (documentation / artifact drift). Third-party rules SHOULD pick a unique
    code prefix to avoid collisions (e.g. ``X001`` for an experimental plugin).
    """

    rule_id: str
    code: str
    description: str
    default_threshold: float

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
