from textual.command import Provider, Hits, Hit
from typing import List, TYPE_CHECKING, Callable
import typer
from cli import cli

from tui_typer.commands.base import dispatch_typer_command

if TYPE_CHECKING:
    from app import CLIApp


class CommandProvider(Provider):
    """Provides commands to the Textual command palette."""

    @property
    def app(self) -> "CLIApp":
        return super().app

    def _create_command_callback(self, cmd_parts: List[str]) -> Callable[[], None]:
        """Create a synchronous callback that runs the async command."""
        def callback() -> None:
            self.app.run_worker(self._run_command(cmd_parts))
        return callback

    async def search(self, query: str) -> Hits:
        """Search for matching commands."""
        matcher = self.matcher(query)

        # Get Click group to access commands
        from click import Group
        click_group = typer.main.get_group(cli)

        if isinstance(click_group, Group):
            for cmd_name, cmd in click_group.commands.items():
                score = matcher.match(cmd_name)
                if score > 0:
                    yield Hit(
                        score,
                        matcher.highlight(cmd_name),
                        self._create_command_callback([cmd_name]),
                        help=cmd.help or cmd.short_help or "",
                    )
                # Search subcommands if this is a group
                if isinstance(cmd, Group):
                    for sub_name, sub_cmd in cmd.commands.items():
                        full_name = f"{cmd_name} {sub_name}"
                        score = matcher.match(full_name)
                        if score > 0:
                            yield Hit(
                                score,
                                matcher.highlight(full_name),
                                self._create_command_callback([cmd_name, sub_name]),
                                help=sub_cmd.help or sub_cmd.short_help or "",
                            )

    async def _run_command(self, cmd_parts: List[str]) -> None:
        """Execute the selected command and display the result."""
        self.app.add_output(f"[bold cyan]>[/bold cyan] {' '.join(cmd_parts)}")
        result = await dispatch_typer_command(cli, cmd_parts)
        if result.stdout:
            self.app.add_output(result.stdout)
        if result.stderr:
            self.app.add_output(f"[red]Error:[/red] {result.stderr}")
