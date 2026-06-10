from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from codecongruence.core.config import RuleConfig
from codecongruence.core.git import ChangedFile
from codecongruence.rules.D002_stale_comments import StaleCommentsRule

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from codecongruence.core.embedder import Embedder
    from codecongruence.rules.base import RuleViolation


def _check(file: Path, emb: Embedder, threshold: float = 0.20) -> Sequence[RuleViolation]:
    return asyncio.run(
        StaleCommentsRule().check(
            [ChangedFile(path=file, added_ranges=())],
            emb,
            RuleConfig(threshold=threshold),
        )
    )


def test_flags_stale_comment(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = (
        "# compute fibonacci sequence iteratively from zero\n"
        "transport.deliver({'to': addr})\n"
        "log.info('sent welcome email')\n"
        "return True\n"
    )
    f = tmp_path / "mod.py"
    f.write_text(src)
    violations = _check(f, fake_embedder)
    assert any(v.rule_id == "stale_comments" for v in violations)


def test_passes_aligned_comment(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = (
        "# deliver the welcome email payload to the transport\n"
        "transport.deliver({'to': addr, 'subject': 'welcome email'})\n"
        "log.info('sent welcome email')\n"
        "return True\n"
    )
    f = tmp_path / "mod.py"
    f.write_text(src)
    assert _check(f, fake_embedder) == []


def test_skips_todo_marker(tmp_path: Path, fake_embedder: Embedder) -> None:
    src = (
        "# TODO refactor this entirely unrelated\n"
        "transport.deliver({'to': addr})\n"
        "log.info('sent welcome email')\n"
    )
    f = tmp_path / "mod.py"
    f.write_text(src)
    assert _check(f, fake_embedder) == []
