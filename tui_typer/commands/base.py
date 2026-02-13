from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from loguru import logger
import typer
from typer.testing import CliRunner


@dataclass
class DispatchResult:
    exit_code: int
    stdout: str
    stderr: str
    help_text: str


async def dispatch_typer_command(
    app: typer.Typer,
    args: Sequence[str],
) -> DispatchResult:
    """
    Dispatch a Typer command asynchronously using CliRunner.

    Args:
        app: The Typer application instance
        args: Command arguments to pass (e.g., ["serialize", "excel", "--file-name", "test.xlsx"])

    Returns:
        DispatchResult containing exit code, stdout, stderr, and help text
    """
    runner = CliRunner()

    def _invoke(argv: list[str]):
        logger.debug(f"Invoking with argv: {argv}")
        # Avoid passing a problematic prog_name that can be a DefaultPlaceholder in Typer/Click
        # which breaks help rendering with AttributeError: 'DefaultPlaceholder' has no attribute 'lstrip'
        result = runner.invoke(app, argv, catch_exceptions=True)
        logger.debug(f"Result: exit_code={result.exit_code}")
        if result.exception:
            logger.error(f"Exception during invoke: {result.exception}")
        if not result.stdout and not result.stderr and result.exit_code != 0:
            logger.warning(f"Command failed silently: exit_code={result.exit_code}")
        return result

    try:
        # Execute the command
        result = await asyncio.to_thread(_invoke, list(args))

        logger.debug(
            f"Command result: exit_code={result.exit_code}, "
            f"stdout_len={len(result.stdout)}, "
            f"stderr_len={len(result.stderr) if result.stderr else 0}"
        )

        # Only get help text if the command failed or if explicitly requested
        help_text = ""
        if "--help" in args:
            help_text = result.stdout
            logger.debug(f"Help requested, help_text length: {len(help_text)}")
        elif result.exit_code != 0 and not result.stdout and not result.stderr:
            # Only fetch help if command failed silently
            help_result = await asyncio.to_thread(_invoke, list(args) + ["--help"])
            help_text = help_result.stdout
            logger.debug(f"Command failed, fetched help_text length: {len(help_text)}")

        return DispatchResult(
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr or "",
            help_text=help_text,
        )
    except Exception as e:
        logger.exception(f"Error dispatching command: {e}")
        # Return a user-friendly error message
        return DispatchResult(
            exit_code=1,
            stdout="",
            stderr=f"Command execution failed: {str(e)}",
            help_text="",
        )


class Command:
    """Represents a CLI command."""

    def __init__(
        self,
        name: str,
        description: str,
        typer_command=None,
        is_group: bool = False,
        parent: str = None,
        params: list = None,
    ):
        self.name = name
        self.description = description
        self._typer_command = typer_command
        self.is_group = is_group
        self.parent = parent
        self.params = params or []

    async def execute(self, app: CLIApp, args: list[str]) -> None:
        """Execute the command via Typer dispatch."""
        if self._typer_command:
            # For subcommands (e.g., "serialize excel"), split the name
            cmd_parts = self.name.split()

            # Combine command parts with any additional arguments
            full_args = cmd_parts + args

            # Execute through the Typer CLI
            result = await dispatch_typer_command(app.typer_cli, full_args)

            if result.stdout:
                app.add_output(result.stdout)
            if result.stderr:
                app.add_output(f"[red]Error:[/red] {result.stderr}")
            if result.exit_code != 0 and not result.stdout and not result.stderr:
                # Show help if command failed silently
                app.add_output(result.help_text)
        else:
            app.add_output("[yellow]Command not implemented[/yellow]")
