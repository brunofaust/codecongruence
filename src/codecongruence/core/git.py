"""Git helpers: staged files, line ranges, diffs.

All calls are read-only ``git`` invocations via ``asyncio.subprocess``. We never
mutate the working tree. Functions degrade gracefully when run outside a repo
(empty lists / empty strings) so the CLI can produce a clean "nothing to check"
message instead of a stack trace.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from codecongruence.parsers.base import CommentBlock, FunctionInfo, LanguageParser

__all__ = [
    "ChangedFile",
    "all_tracked_files",
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
    excluded_fn_ranges: tuple[tuple[int, int], ...] = ()

    def covers(self, line: int) -> bool:
        """True if ``line`` lies inside any added range.

        Returns:
            ``True`` if the line falls within at least one added range.
        """
        return any(lo <= line <= hi for lo, hi in self.added_ranges)

    def overlaps(self, start: int, end: int) -> bool:
        """True if ``[start, end]`` intersects any added range.

        Returns:
            ``True`` if the interval overlaps at least one added range.
        """
        return any(not (end < lo or start > hi) for lo, hi in self.added_ranges)

    def iter_functions(self, parser: LanguageParser, source: str) -> Iterator[FunctionInfo]:
        """Yield functions parsed from source, skipping runner-excluded ones.

        Args:
            parser: Language parser for the file's extension.
            source: Full source text of the file.

        Yields:
            :class:`~codecongruence.parsers.base.FunctionInfo` for each non-excluded function.
        """
        for func in parser.iter_functions(source, self.path):
            if not any(
                s <= func.line_start and func.line_end <= e for s, e in self.excluded_fn_ranges
            ):
                yield func

    def iter_comments(
        self,
        parser: LanguageParser,
        source: str,
        *,
        context_lines: int = 5,
    ) -> Iterator[CommentBlock]:
        """Yield comments parsed from source, skipping those inside excluded function ranges.

        Args:
            parser: Language parser for the file's extension.
            source: Full source text of the file.
            context_lines: Number of lines of following code to capture per comment.

        Yields:
            :class:`~codecongruence.parsers.base.CommentBlock` for each non-excluded comment.
        """
        for comment in parser.iter_comments(source, context_lines=context_lines):
            if not any(s <= comment.line <= e for s, e in self.excluded_fn_ranges):
                yield comment


async def _run_git(*args: str, cwd: Path | None = None) -> str:
    # Strip git hook env vars to prevent leakage (e.g., GIT_WORK_TREE from prek)
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "GIT_DIR",
            "GIT_INDEX_FILE",
            "GIT_WORK_TREE",
            "GIT_PREFIX",
            "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        }
    }
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, _stderr = await proc.communicate()
    if proc.returncode != 0:
        return ""
    return stdout.decode("utf-8", errors="replace")


async def current_repo_root(cwd: Path | None = None) -> Path:
    """Return the repo root, or ``cwd`` if not in a git repo."""
    out = (await _run_git("rev-parse", "--show-toplevel", cwd=cwd)).strip()
    return Path(out) if out else (cwd or Path.cwd())


async def all_tracked_files(*, cwd: Path | None = None) -> list[Path]:
    """List every file git knows about (tracked + untracked non-ignored).

    Uses ``git ls-files --cached --others --exclude-standard`` so the result
    honours ``.gitignore``, ``.git/info/exclude``, and global excludes without
    any hardcoded directory list. Deleted files are excluded (they have no
    on-disk content to read).

    Args:
        cwd: Directory to run git in. Defaults to current working directory.

    Returns:
        Relative paths of all files git considers part of the working tree.
    """
    raw = await _run_git("ls-files", "--cached", "--others", "--exclude-standard", cwd=cwd)
    return [Path(line) for line in raw.splitlines() if line.strip()]


async def staged_changed_files(
    *,
    cwd: Path | None = None,
    include_unstaged: bool = False,
) -> list[Path]:
    """List files staged for commit (or staged+unstaged if asked).

    Filters out deleted paths — semantic rules need the file to read.

    Args:
        cwd: Working directory for git. Defaults to current directory.
        include_unstaged: When ``True`` also includes unstaged working-tree changes.

    Returns:
        Paths of added/copied/modified/renamed staged files.
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

    Args:
        paths: Files to diff; returned dict keys match this list.
        cwd: Working directory for git. Defaults to current directory.
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
    """Return the full unified diff of staged changes (used by content-vs-diff rules).

    Args:
        cwd: Working directory for git. Defaults to current directory.
    """
    return await _run_git("diff", "--cached", "--unified=3", cwd=cwd)


async def git_diff(path: Path, *, context: int = 3, cwd: Path | None = None) -> str:
    """Unified diff for a single staged file.

    Args:
        path: File path to diff.
        context: Number of context lines on each side of each hunk. Increase
            when the header you need to detect may be far above the changed
            lines (e.g. ``## [Unreleased]`` with many existing bullets).
        cwd: Working directory override.

    Returns:
        Unified diff text, or an empty string when there are no staged changes.
    """
    return await _run_git("diff", "--cached", f"--unified={context}", "--", str(path), cwd=cwd)
