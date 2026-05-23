"""Rule loader + parallel execution.

Loads the built-in rule set, filters by config, and runs them concurrently with
``asyncio.TaskGroup``. Each rule is independent and receives the shared
:class:`~codecongruence.core.embedder.Embedder` so models load once per run.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from codecongruence.core.embedder import Embedder
from codecongruence.core.git import ChangedFile, staged_changed_files, staged_changed_line_ranges
from codecongruence.rules.C001_name_vs_body import NameVsBodyRule
from codecongruence.rules.C002_param_name_vs_usage import ParamNameVsUsageRule
from codecongruence.rules.D001_docstring_vs_body import DocstringVsBodyRule
from codecongruence.rules.D002_stale_comments import StaleCommentsRule
from codecongruence.rules.D003_claude_md_vs_diff import ClaudeMdVsDiffRule
from codecongruence.rules.D004_pr_description_vs_diff import PrDescriptionVsDiffRule
from codecongruence.rules.D005_changelog_exists import ChangelogExistsRule
from codecongruence.rules.D006_params_in_docstring import ParamsInDocstringRule

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from codecongruence.core.config import CodeCongruenceConfig
    from codecongruence.rules.base import Rule, RuleViolation

__all__ = ["RuleRunner", "RunResult", "default_rules", "run_rules"]


@dataclass(frozen=True, slots=True)
class RunResult:
    """Aggregated outcome of a single run."""

    violations: tuple[RuleViolation, ...]
    files_checked: tuple[Path, ...]
    rules_run: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not any(v.severity == "error" for v in self.violations)


def default_rules() -> list[Rule]:
    """Return the built-in rule set in deterministic order."""
    return [
        DocstringVsBodyRule(),
        NameVsBodyRule(),
        ParamNameVsUsageRule(),
        ClaudeMdVsDiffRule(),
        PrDescriptionVsDiffRule(),
        StaleCommentsRule(),
        ChangelogExistsRule(),
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
        """Build the :class:`ChangedFile` list the rules consume."""
        root = self.config.repo_root
        if all_files:
            files = [p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]
            return [ChangedFile(path=p.relative_to(root), added_ranges=()) for p in files]

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
    ) -> RunResult:
        """Execute selected rules and return their combined violations."""
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
                        rule.check(changed, self.embedder, self.config.rule(rule.rule_id))
                    )
                    for rule in selected
                ]
            results = [t.result() for t in tasks]
        else:
            for rule in selected:
                results.append(
                    await rule.check(changed, self.embedder, self.config.rule(rule.rule_id))
                )

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
    """Convenience wrapper that constructs the embedder + runner for one call."""
    emb = embedder or Embedder(config.model)
    runner = RuleRunner(config, emb)
    return await runner.run(
        only=only,
        explicit_files=explicit_files,
        include_unstaged=include_unstaged,
        all_files=all_files,
    )
