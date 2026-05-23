"""Colorized terminal reporter using ``rich``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from codecongruence.core.runner import RunResult

__all__ = ["TextReporter"]


class TextReporter:
    """Print violations to the terminal.

    Default (quiet) mode: silent on success, prints only the count line on failure.
    Verbose mode (``--verbose``): prints an OK line on success; prints the full
    violation table before the count line on failure.
    """

    def __init__(
        self,
        *,
        verbose: bool = False,
        console: Console | None = None,
    ) -> None:
        self.verbose = verbose
        self.console = console or Console()

    def report(self, result: RunResult) -> None:
        """Render ``result`` to the console."""
        if not result.files_checked:
            self.console.print(
                "[yellow]codecongruence: nothing to check[/yellow] — "
                "no staged files found. Stage changes first or run with [bold]--all[/bold]."
            )
            return

        if not result.violations:
            if self.verbose:
                self.console.print(
                    f"[green]codecongruence: OK[/green] "
                    f"({len(result.rules_run)} rules, {len(result.files_checked)} files)"
                )
            return

        if self.verbose:
            table = Table(
                title="codecongruence violations",
                show_lines=False,
                title_style="bold red",
                header_style="bold",
            )
            table.add_column("code", style="bold red", no_wrap=True)
            table.add_column("rule", style="cyan", no_wrap=True)
            table.add_column("file:line", style="magenta")
            table.add_column("sim", justify="right", style="yellow")
            table.add_column("threshold", justify="right")
            table.add_column("message")

            for v in result.violations:
                loc = f"{v.file_path}:{v.line}" if v.line is not None else v.file_path
                table.add_row(
                    v.code,
                    v.rule_id,
                    loc,
                    f"{v.similarity:.2f}",
                    f"{v.threshold:.2f}",
                    v.message,
                )
            self.console.print(table)

        self.console.print(
            f"[red]codecongruence: {len(result.violations)} violation(s)[/red] "
            f"across {len(result.files_checked)} file(s); "
            f"rules: {', '.join(result.rules_run)}."
        )
