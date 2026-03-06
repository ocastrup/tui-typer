"""Textual command palette provider.

Supplies commands to the Textual command palette (Ctrl+P).  The command list
is built once on first search and cached for the lifetime of the provider.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from textual.command import Hit, Hits, Provider

from tui_typer.cli import cli
from tui_typer.command_dispatcher.base import dispatch_typer_command
from tui_typer.command_dispatcher.loader import load_commands

if TYPE_CHECKING:
    from tui_typer.app import CLIApp

# Module-level cache: built once, shared across all CommandProvider instances.
_COMMAND_CACHE: dict | None = None


def _get_cached_commands() -> dict:
    global _COMMAND_CACHE
    if _COMMAND_CACHE is None:
        _COMMAND_CACHE = load_commands(cli)
    return _COMMAND_CACHE


class CommandProvider(Provider):
    """Provides registered Typer commands to the Textual command palette."""

    @property
    def app(self) -> CLIApp:
        return super().app  # type: ignore[return-value]

    def _create_command_callback(self, cmd_parts: list[str]) -> Callable[[], None]:
        """Return a sync callback that launches an async command worker."""

        def callback() -> None:
            self.app.run_worker(
                self._run_command(cmd_parts),
                exclusive=False,
                name=f"palette:{':'.join(cmd_parts)}",
            )

        return callback

    async def search(self, query: str) -> Hits:
        """Yield :class:`~textual.command.Hit` objects matching *query*."""
        matcher = self.matcher(query)
        commands = _get_cached_commands()

        for cmd_name, cmd in commands.items():
            score = matcher.match(cmd_name)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(cmd_name),
                    self._create_command_callback(cmd_name.split()),
                    help=cmd.description,
                )

    async def _run_command(self, cmd_parts: list[str]) -> None:
        """Execute a palette-selected command and display the result."""
        self.app.add_output(f"[bold cyan]>[/bold cyan] {' '.join(cmd_parts)}")
        result = await dispatch_typer_command(
            cli,
            cmd_parts,
            context_manager=self.app._context_manager,
        )
        if result.stdout:
            self.app.add_output(result.stdout)
        if result.stderr:
            self.app.add_output(f"[red]Error:[/red] {result.stderr}")
