"""Git helpers: staged files, line ranges, diffs.

All calls are read-only ``git`` invocations via ``asyncio.subprocess``. We never
mutate the working tree. Functions degrade gracefully when run outside a repo
(empty lists / empty strings) so the CLI can produce a clean "nothing to check"
message instead of a stack trace.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ChangedFile",
    "current_repo_root",
    "git_diff",
    "git_diff_unified",
    "staged_changed_files",
    "staged_changed_line_ranges",
]


@dataclass(frozen=True, slots=True)
class ChangedFile:
    """A path + its added line ranges (1-based, inclusive)."""

    path: Path
    added_ranges: tuple[tuple[int, int], ...]

    def covers(self, line: int) -> bool:
        """True if ``line`` lies inside any added range."""
        return any(lo <= line <= hi for lo, hi in self.added_ranges)

    def overlaps(self, start: int, end: int) -> bool:
        """True if ``[start, end]`` intersects any added range."""
        return any(not (end < lo or start > hi) for lo, hi in self.added_ranges)


async def _run_git(*args: str, cwd: Path | None = None) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _stderr = await proc.communicate()
    if proc.returncode != 0:
        return ""
    return stdout.decode("utf-8", errors="replace")


async def current_repo_root(cwd: Path | None = None) -> Path:
    """Return the repo root, or ``cwd`` if not in a git repo."""
    out = (await _run_git("rev-parse", "--show-toplevel", cwd=cwd)).strip()
    return Path(out) if out else (cwd or Path.cwd())


async def staged_changed_files(
    *,
    cwd: Path | None = None,
    include_unstaged: bool = False,
) -> list[Path]:
    """List files staged for commit (or staged+unstaged if asked).

    Filters out deleted paths — semantic rules need the file to read.
    """
    args = ["diff", "--name-only", "--diff-filter=ACMR"]
    if not include_unstaged:
        args.append("--cached")
    args.append("HEAD")
    raw = await _run_git(*args, cwd=cwd)
    return [Path(line) for line in raw.splitlines() if line.strip()]


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


async def staged_changed_line_ranges(
    paths: list[Path],
    *,
    cwd: Path | None = None,
) -> dict[Path, tuple[tuple[int, int], ...]]:
    """Return added-line ranges per file in the staged diff.

    The hook is interested in additions only (modifications show as add+remove
    of the same line, which still appears as an added line in the new file).
    Range tuples are ``(start_line, end_line)`` 1-based inclusive.
    """
    if not paths:
        return {}

    raw = await _run_git("diff", "--cached", "--unified=0", "--", *map(str, paths), cwd=cwd)
    out: dict[Path, list[tuple[int, int]]] = {p: [] for p in paths}

    current_file: Path | None = None
    for line in raw.splitlines():
        if line.startswith("+++ b/"):
            rel = line[len("+++ b/") :]
            for candidate in paths:
                if str(candidate) == rel:
                    current_file = candidate
                    break
            else:
                current_file = None
            continue
        if line.startswith("@@") and current_file is not None:
            match = _HUNK.match(line)
            if not match:
                continue
            start = int(match.group(1))
            length = int(match.group(2)) if match.group(2) else 1
            if length == 0:
                continue
            out[current_file].append((start, start + length - 1))

    return {p: tuple(r) for p, r in out.items()}


async def git_diff_unified(*, cwd: Path | None = None) -> str:
    """Return the full unified diff of staged changes (used by content-vs-diff rules)."""
    return await _run_git("diff", "--cached", "--unified=3", cwd=cwd)


async def git_diff(path: Path, *, cwd: Path | None = None) -> str:
    """Unified diff for a single staged file."""
    return await _run_git("diff", "--cached", "--unified=3", "--", str(path), cwd=cwd)
