from textual.app import App, ComposeResult
from textual.widgets import RichLog, Header, Footer, Input
from textual.containers import Vertical, Horizontal
from textual.command import Provider, Hits, Hit
from typer_tui.commands.config import AppConfig
from typer_tui.commands.history import HistoryManager
from typer_tui.commands.console import CliConsole
from typer_tui.commands.base import dispatch_typer_command, Command
from difflib import get_close_matches
from functools import partial
from typing import List
import typer
from io import StringIO
import sys
from cli import cli, dispatch_typer_command
from loguru import logger
from configparser import ConfigParser





class ContextManager:
    """
    Provide context between sub commands.

    Args:
        console: The main CLI console
        config: The app configuration

    """

    def __init__(self, console: CliConsole, config: ConfigParser):
        self._console:CliConsole = console
        self._config:ConfigParser = config



    @property
    def console(self) -> CliConsole:
        return self._console

    @property
    def config(self,) -> ConfigParser:
        return self._config


class CommandProvider(Provider):
    """Provides commands to the Textual command palette."""

    @property
    def app(self) -> "CLIApp":
        return super().app

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
                        partial(self.app.run_worker, self._run_command([cmd_name])),
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
                                partial(self.app.run_worker, self._run_command([cmd_name, sub_name])),
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


def load_commands(typer_app: typer.Typer, context: ContextManager) -> dict[str, 'Command']:
    """
    Load all commands from a Typer application instance.
    Returns a flat dict with both top-level and nested commands.
    """
    from typer_tui.commands.base import Command
    from click import Group

    commands = {}

    # Get the Click group from Typer
    click_group = typer.main.get_group(typer_app)

    if isinstance(click_group, Group):
        for cmd_name, cmd in click_group.commands.items():
            help_text = cmd.help or cmd.short_help or ""

            # Store metadata about whether this is a group
            is_group = isinstance(cmd, Group)

            commands[cmd_name] = Command(
                name=cmd_name,
                description=help_text,
                context=context,
                typer_command=cmd,
                is_group=is_group
            )

            # If it's a group, load its subcommands with parent reference
            if is_group:
                for sub_name, sub_cmd in cmd.commands.items():
                    full_name = f"{cmd_name} {sub_name}"
                    sub_help = sub_cmd.help or sub_cmd.short_help or ""

                    commands[full_name] = Command(
                        name=full_name,
                        description=sub_help,
                        context=context,
                        typer_command=sub_cmd,
                        is_group=False,
                        parent=cmd_name
                    )

    return commands


class TextualLogHandler:
    """Custom loguru sink that writes to a Textual RichLog widget."""

    LEVEL_COLORS = {
        "DEBUG": "blue",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold red",
    }

    def __init__(self, log_widget: RichLog):
        self.log_widget = log_widget

    def write(self, message) -> None:
        """Write log message to the widget."""
        record = message.record
        level = record["level"].name
        color = self.LEVEL_COLORS.get(level, "white")

        text = f"[{color}]{level: <8}[/{color}] | [cyan]{record['name']}[/cyan]:[cyan]{record['function']}[/cyan] - {record['message']}"
        self.log_widget.write(text)


class CLIApp(App):
    """A CLI application with output window and command prompt."""

    CSS = """
    #main-container {
        height: 1fr;
    }
    #output-log {
        height: 2fr;
        border: solid green;
    }
    #logger-log {
        height: 1fr;
        border: solid yellow;
    }
    #input-box {
        dock: bottom;
        height: 3;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
    ]
    COMMANDS = App.COMMANDS | {CommandProvider}

    def __init__(self, config_path: str = None):
        super().__init__()

        self.app_config = AppConfig(config_path)
        self.history_manager = HistoryManager(
            self.app_config.history_file,
            self.app_config.max_history
        )

        self.history_index: int = -1
        self.current_input: str = ""
        self._non_interactive: bool = False
        self.commands: dict[str, Command] = {}


    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-container"):
            yield RichLog(id="output-log", highlight=True, markup=True)
            yield RichLog(id="logger-log", highlight=True, markup=True)
        yield Input(id="input-box", placeholder="Enter command...")
        yield Footer()

    def on_mount(self) -> None:
        """Configure loguru to use the Textual widget after mount."""
        self.log_widget = self.query_one("#logger-log", RichLog)
        self.output_widget = self.query_one("#output-log", RichLog)
        input_widget = self.query_one("#input-box", Input)
        input_widget.focus()
        logger.remove()

        logger.add(
            TextualLogHandler(self.log_widget).write,
            format="{message}",
            level="DEBUG",
            colorize=False,
        )
        logger.info("Logger initialized")

        # Load commands from the typer CLI
        from cli import cli
        self.typer_cli = cli
        self.commands = load_commands(self.typer_cli, ContextManager(
            console=CliConsole(),
            config=AppConfig().config
        ))
        logger.info(f"Loaded {len(self.commands)} commands")

    def on_key(self, event) -> None:
        if event.key == "up":
            self._history_prev()
            event.prevent_default()
        elif event.key == "down":
            self._history_next()
            event.prevent_default()

    def _history_prev(self) -> None:
        input_widget = self.query_one("#input-box", Input)
        if self.command_history:
            if self.history_index == -1:
                self.current_input = input_widget.value
                self.history_index = len(self.command_history) - 1
            elif self.history_index > 0:
                self.history_index -= 1
            input_widget.value = self.command_history[self.history_index]
            input_widget.cursor_position = len(input_widget.value)

    def _history_next(self) -> None:
        input_widget = self.query_one("#input-box", Input)
        if self.history_index != -1:
            if self.history_index < len(self.command_history) - 1:
                self.history_index += 1
                input_widget.value = self.command_history[self.history_index]
            else:
                self.history_index = -1
                input_widget.value = self.current_input
            input_widget.cursor_position = len(input_widget.value)

    @property
    def command_history(self) -> list[str]:
        return self.history_manager.history

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command submission when Enter is pressed."""
        command = event.value.strip()
        if command:
            self.add_output(f"[bold cyan]>[/bold cyan] {command}")
            self.history_manager.add(command)
            self.history_index = -1
            self.current_input = ""
            self.run_worker(self._execute_command(command))
        event.input.value = ""

    def add_output(self, text: str) -> None:
        if getattr(self, '_non_interactive', False):
            from rich import print as rprint
            rprint(text)
        else:
            self.output_widget.write(text)

    async def _execute_command(self, command_line: str) -> None:
        """Execute command using Typer CLI dispatch."""
        parts = command_line.strip().split()
        if not parts:
            return

        cmd_name = parts[0].lower()

        # Handle built-in help command
        if cmd_name == "help":
            if len(parts) > 1:
                help_target = " ".join(parts[1:])
                self._show_command_help(help_target)
            else:
                self._show_all_commands_help()
            return

        # Check if command exists before dispatching
        cmd_parts = " ".join(parts[:2]) if len(parts) > 1 else parts[0]
        if parts[0] not in self.commands and cmd_parts not in self.commands:
            self.add_output(f"[bold red]Unknown command:[/bold red] {parts[0]}")

            # Suggest similar commands
            from difflib import get_close_matches
            all_command_names = list(self.commands.keys())
            suggestions = get_close_matches(parts[0], all_command_names, n=3, cutoff=0.6)
            if suggestions:
                self.add_output(f"[yellow]Did you mean:[/yellow] {', '.join(suggestions)}?")
            return

        # Dispatch through typer CLI
        result = await dispatch_typer_command(self.typer_cli, parts)

        if result.stdout:
            self.add_output(result.stdout)
        if result.stderr:
            self.add_output(f"[red]Error:[/red] {result.stderr}")
        if result.exit_code != 0 and not result.stderr and result.help_text:
            self.add_output(result.help_text)

    async def _dispatch_with_help(self, args: list[str]) -> None:
        """Show help for a specific command."""
        result = await dispatch_typer_command(self.typer_cli, args + ["--help"])
        self.add_output(result.stdout)

    def _show_all_commands_help(self) -> None:
        """Display help for top-level commands only (Typer-style)."""
        self.add_output("[bold cyan]Available Commands:[/bold cyan]\n")

        # Filter to show only top-level commands (no parent)
        top_level_commands = {
            name: cmd
            for name, cmd in sorted(self.commands.items())
            if not hasattr(cmd, 'parent') or cmd.parent is None
        }

        for name, cmd in top_level_commands.items():
            # Add indicator if this is a command group
            suffix = " [dim](group)[/dim]" if getattr(cmd, 'is_group', False) else ""
            self.add_output(f"  [green]{name}[/green]{suffix}: {cmd.description}")

        self.add_output("\n[dim]Type 'help <command>' for detailed help on a specific command[/dim]")

    def _show_command_help(self, cmd_name: str) -> None:
        """Display detailed help for a specific command, including subcommands if it's a group."""
        parts = cmd_name.split()

        # Check if this is a full path (e.g., "serialize excel") or just a top-level command
        if len(parts) == 1 and parts[0] in self.commands:
            command = self.commands[parts[0]]

            # If this is a group, show custom help with subcommands
            if getattr(command, 'is_group', False):
                self.add_output(f"[bold cyan]Command Group:[/bold cyan] [green]{cmd_name}[/green]")
                self.add_output(f"[bold cyan]Description:[/bold cyan] {command.description}\n")
                self.add_output("[bold cyan]Subcommands:[/bold cyan]")

                # Find all subcommands belonging to this group
                subcommands = {
                    name: cmd
                    for name, cmd in sorted(self.commands.items())
                    if hasattr(cmd, 'parent') and cmd.parent == cmd_name
                }

                for sub_name, sub_cmd in subcommands.items():
                    # Display only the subcommand part (not the full path)
                    display_name = sub_name.split()[-1]
                    self.add_output(f"  [green]{display_name}[/green]: {sub_cmd.description}")

                self.add_output(f"\n[dim]Type 'help {cmd_name} <subcommand>' for detailed help[/dim]")
            else:
                # For leaf commands, show Typer's help
                self.run_worker(self._dispatch_with_help([cmd_name]))

        elif " ".join(parts) in self.commands:
            # Full subcommand path provided (e.g., "serialize excel")
            self.run_worker(self._dispatch_with_help(parts))
        else:
            self.add_output(f"[bold red]Unknown command:[/bold red] {cmd_name}")

    def process_command(self, command: str) -> None:
        """Synchronous command processing (deprecated, use _execute_command)."""
        parts = command.strip().split()
        cmd_name = parts[0].lower()
        args = parts[1:]

        if cmd_name in self.commands:
            self.commands[cmd_name].execute(self, args)
        else:
            self.add_output(f"[bold red]Unknown command:[/bold red] {cmd_name}")
            suggestions = get_close_matches(cmd_name, self.commands.keys(), n=3, cutoff=0.6)
            if suggestions:
                self.add_output(f"[yellow]Did you mean:[/yellow] {', '.join(suggestions)}?")

    def execute_command_non_interactive(self, command: str, args: list[str]) -> None:
        if command in self.commands:
            self._non_interactive = True
            self.commands[command].execute(self, args)
        else:
            print(f"Unknown command: {command}")

    def action_quit(self) -> None:
        """Save history and config on exit."""
        self.history_manager.save()
        self.app_config.save()
        self.exit()

    def exit(self, result=None) -> None:
        """Save history and config before exiting."""
        self.history_manager.save()
        self.app_config.save()
        super().exit(result)


if __name__ == "__main__":
    app = CLIApp()
    app.run()
