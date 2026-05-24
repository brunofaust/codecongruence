"""Rule loader + parallel execution.

Loads the built-in rule set, filters by config, and runs them concurrently with
``asyncio.TaskGroup``. Each rule is independent and receives the shared
:class:`~codecongruence.core.embedder.Embedder` so models load once per run.
"""

from __future__ import annotations

import asyncio
import dataclasses
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import TYPE_CHECKING

from codecongruence.core.embedder import Embedder
from codecongruence.core.git import (
    ChangedFile,
    all_tracked_files,
    staged_changed_files,
    staged_changed_line_ranges,
)
from codecongruence.parsers import get_parser
from codecongruence.rules.C001_name_vs_body import NameVsBodyRule
from codecongruence.rules.C002_param_name_vs_usage import ParamNameVsUsageRule
from codecongruence.rules.C003_duplicate_functions import DuplicateFunctionsRule
from codecongruence.rules.D001_docstring_vs_body import DocstringVsBodyRule
from codecongruence.rules.D002_stale_comments import StaleCommentsRule
from codecongruence.rules.D003_claude_md_vs_diff import ClaudeMdVsDiffRule
from codecongruence.rules.D004_pr_description_vs_diff import PrDescriptionVsDiffRule
from codecongruence.rules.D005_changelog_exists import DocsOnChangeRule
from codecongruence.rules.D006_params_in_docstring import ParamsInDocstringRule

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from codecongruence.core.config import CodeCongruenceConfig
    from codecongruence.rules.base import Rule, RuleViolation

__all__ = ["RuleRunner", "RunResult", "default_rules", "run_rules"]


def _apply_file_excludes(changed: list[ChangedFile], patterns: list[str]) -> list[ChangedFile]:
    if not patterns:
        return changed
    return [cf for cf in changed if not any(fnmatch(str(cf.path), pat) for pat in patterns)]


def _apply_function_excludes(
    changed: list[ChangedFile], exclude_fns: list[str]
) -> list[ChangedFile]:
    if not exclude_fns:
        return changed
    result: list[ChangedFile] = []
    for cf in changed:
        parser = get_parser(cf.path.suffix)
        if parser is None:
            result.append(cf)
            continue
        try:
            source = cf.path.read_text(encoding="utf-8")
        except OSError:
            result.append(cf)
            continue
        excluded = tuple(
            (func.line_start, func.line_end)
            for func in parser.iter_functions(source, cf.path)
            if any(fnmatch(func.qualified_name, pat) for pat in exclude_fns)
        )
        result.append(dataclasses.replace(cf, excluded_fn_ranges=excluded) if excluded else cf)
    return result


@dataclass(frozen=True, slots=True)
class RunResult:
    """Aggregated outcome of a single run."""

    violations: tuple[RuleViolation, ...]
    files_checked: tuple[Path, ...]
    rules_run: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """True when no violation has ``severity == "error"``."""
        return not any(v.severity == "error" for v in self.violations)


def default_rules() -> list[Rule]:
    """Return the built-in rule set in deterministic order."""
    return [
        DocstringVsBodyRule(),
        NameVsBodyRule(),
        ParamNameVsUsageRule(),
        DuplicateFunctionsRule(),
        ClaudeMdVsDiffRule(),
        PrDescriptionVsDiffRule(),
        StaleCommentsRule(),
        DocsOnChangeRule(),
        ParamsInDocstringRule(),
    ]


class RuleRunner:
    """Coordinates rule execution. One instance per CLI invocation."""

    def __init__(
        self,
        config: CodeCongruenceConfig,
        embedder: Embedder,
        rules: Sequence[Rule] | None = None,
    ) -> None:
        self.config = config
        self.embedder = embedder
        self.rules: list[Rule] = list(rules) if rules is not None else default_rules()

    async def gather_changed(
        self,
        *,
        explicit_files: Sequence[Path] | None = None,
        include_unstaged: bool = False,
        all_files: bool = False,
    ) -> list[ChangedFile]:
        """Build the :class:`ChangedFile` list the rules consume.

        Args:
            explicit_files: When set, check exactly these paths instead of querying git.
            include_unstaged: Also include unstaged working-tree changes.
            all_files: Scan every tracked file regardless of staged status.

        Returns:
            Resolved list of changed files with their added line ranges.
        """
        root = self.config.repo_root
        if all_files:
            paths = await all_tracked_files(cwd=root)
            return [ChangedFile(path=p, added_ranges=()) for p in paths if (root / p).is_file()]

        if explicit_files:
            paths = list(explicit_files)
        else:
            paths = await staged_changed_files(cwd=root, include_unstaged=include_unstaged)

        ranges = await staged_changed_line_ranges(paths, cwd=root)
        return [ChangedFile(path=p, added_ranges=ranges.get(p, ())) for p in paths]

    def _select_rules(self, only: str | None) -> list[Rule]:
        enabled_ids = {r.rule_id for r in self.rules if self.config.rule(r.rule_id).enabled}
        if only is not None:
            return [r for r in self.rules if r.rule_id == only]
        return [r for r in self.rules if r.rule_id in enabled_ids]

    async def run(
        self,
        *,
        only: str | None = None,
        explicit_files: Sequence[Path] | None = None,
        include_unstaged: bool = False,
        all_files: bool = False,
        pre_gathered: Sequence[ChangedFile] | None = None,
    ) -> RunResult:
        """Execute selected rules and return their combined violations.

        Args:
            only: Run only the rule with this id.
            explicit_files: Paths to check instead of git-staged files.
            include_unstaged: Also include unstaged working-tree changes.
            all_files: Scan the whole repo (no staged-file filter).
            pre_gathered: Pre-computed file list from :meth:`gather_changed`.
                When provided, ``explicit_files`` / ``include_unstaged`` /
                ``all_files`` are ignored — the caller owns the discovery step.

        Returns:
            Aggregated :class:`RunResult` with all violations sorted by file + line.
        """
        if pre_gathered is not None:
            changed = list(pre_gathered)
        else:
            changed = await self.gather_changed(
                explicit_files=explicit_files,
                include_unstaged=include_unstaged,
                all_files=all_files,
            )
        selected = self._select_rules(only)

        results: list[Sequence[RuleViolation]] = []
        if self.config.parallel and selected:
            async with asyncio.TaskGroup() as group:
                tasks = [
                    group.create_task(
                        rule.check(
                            _apply_function_excludes(
                                _apply_file_excludes(
                                    changed, self.config.rule(rule.rule_id).exclude
                                ),
                                self.config.rule(rule.rule_id).exclude_functions,
                            ),
                            self.embedder,
                            self.config.rule(rule.rule_id),
                        )
                    )
                    for rule in selected
                ]
            results = [t.result() for t in tasks]
        else:
            for rule in selected:
                rule_cfg = self.config.rule(rule.rule_id)
                filtered = _apply_function_excludes(
                    _apply_file_excludes(changed, rule_cfg.exclude),
                    rule_cfg.exclude_functions,
                )
                results.append(await rule.check(filtered, self.embedder, rule_cfg))

        flat: list[RuleViolation] = []
        for r in results:
            flat.extend(r)
        flat.sort(key=lambda v: (v.file_path, v.line or 0, v.rule_id))

        return RunResult(
            violations=tuple(flat),
            files_checked=tuple(c.path for c in changed),
            rules_run=tuple(r.rule_id for r in selected),
        )


async def run_rules(
    config: CodeCongruenceConfig,
    *,
    only: str | None = None,
    explicit_files: Sequence[Path] | None = None,
    include_unstaged: bool = False,
    all_files: bool = False,
    embedder: Embedder | None = None,
) -> RunResult:
    """Convenience wrapper that constructs the embedder + runner for one call.

    Args:
        config: Top-level configuration (model, rules, excludes).
        only: When set, run only the rule with this ID.
        explicit_files: Check exactly these paths instead of querying git.
        include_unstaged: Also include unstaged working-tree changes.
        all_files: Scan every tracked file regardless of staged status.
        embedder: Pre-constructed embedder; one is created from ``config.model`` when omitted.

    Returns:
        Aggregated :class:`RunResult` from a single-use :class:`RuleRunner`.
    """
    emb = embedder or Embedder(config.model)
    runner = RuleRunner(config, emb)
    return await runner.run(
        only=only,
        explicit_files=explicit_files,
        include_unstaged=include_unstaged,
        all_files=all_files,
    )
