"""Rule protocol + shared dataclasses."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence

    from codecongruence.core.config import RuleConfig
    from codecongruence.core.embedder import Embedder
    from codecongruence.core.git import ChangedFile

__all__ = ["DOCS_BASE_URL", "Rule", "RuleViolation", "Severity", "strip_comments"]

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
