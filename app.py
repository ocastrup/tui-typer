from difflib import get_close_matches

from loguru import logger
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, ProgressBar, RichLog

from cli import cli
from tui_typer.commands.base import Command, dispatch_typer_command
from tui_typer.commands.config import AppConfig
from tui_typer.commands.history import HistoryManager
from tui_typer.commands.loader import load_commands
from tui_typer.ui.command_provider import CommandProvider
from tui_typer.ui.logging import TextualLogHandler, TextualProgressSink


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
    #progress-bar {
        height: 1;
        border: solid blue;
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

    def __init__(self):
        super().__init__()
        self.app_config = AppConfig(config_path=".cli_app.ini")
        # self._context = ContextManager(config=self.app_config, console=CliConsole())

        self.history_manager = HistoryManager(
            self.app_config.history_file, self.app_config.max_history
        )

        self.history_index: int = -1
        self.current_input: str = ""
        self._non_interactive: bool = False
        self.commands: dict[str, Command] = {}
        # self._context will be initialized when needed

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-container"):
            yield RichLog(id="output-log", highlight=True, markup=True)
            yield RichLog(id="logger-log", highlight=True, markup=True)
            yield ProgressBar(id="progress-bar", total=100, show_eta=False)
        yield Input(id="input-box", placeholder="Enter command...")
        yield Footer()

    def on_mount(self) -> None:
        """Configure loguru to use the Textual widget after mount."""
        self.log_widget = self.query_one("#logger-log", RichLog)
        self.output_widget = self.query_one("#output-log", RichLog)
        self.progress_widget = self.query_one("#progress-bar", ProgressBar)
        self.progress_sink = TextualProgressSink(self.progress_widget)

        input_widget = self.query_one("#input-box", Input)
        input_widget.focus()
        logger.remove()
        log_level = self.app_config.get("general", "log_level", fallback="INFO")

        logger.add(
            TextualLogHandler(self.log_widget).write,
            format="{message}",
            level=log_level,
            colorize=False,
        )
        logger.info("Logger initialized")

        # Load commands from the typer CLI
        self.typer_cli = cli
        self.commands = load_commands(self.typer_cli)
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
                self.current_input = str(input_widget.value)
                self.history_index = len(self.command_history) - 1
            elif self.history_index > 0:
                self.history_index -= 1
            input_widget.value = self.command_history[self.history_index]
            input_widget.cursor_position = len(str(input_widget.value))

    def _history_next(self) -> None:
        input_widget = self.query_one("#input-box", Input)
        if self.history_index != -1:
            if self.history_index < len(self.command_history) - 1:
                self.history_index += 1
                input_widget.value = self.command_history[self.history_index]
            else:
                self.history_index = -1
                input_widget.value = self.current_input
            input_widget.cursor_position = len(str(input_widget.value))

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
        if getattr(self, "_non_interactive", False):
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

        # Built-in exit command: close the application gracefully
        if cmd_name in {"exit", "quit"}:
            self.add_output("[dim]Exiting...[/dim]")
            self.exit()
            return

        # Handle built-in history command
        if cmd_name == "history":
            self.display_history()
            return

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

        # If --help was requested, show the help text
        if "--help" in parts:
            if result.help_text:
                self.add_output(result.help_text)
            elif result.stdout:
                self.add_output(result.stdout)
        else:
            # Normal command execution
            if result.stdout:
                self.add_output(result.stdout)
            if result.stderr:
                self.add_output(f"[red]Error:[/red] {result.stderr}")
            if (
                result.exit_code != 0
                and not result.stdout
                and not result.stderr
                and result.help_text
            ):
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
            if not hasattr(cmd, "parent") or cmd.parent is None
        }

        for name, cmd in top_level_commands.items():
            # Add indicator if this is a command group
            suffix = " [dim](group)[/dim]" if getattr(cmd, "is_group", False) else ""
            self.add_output(f"  [green]{name}[/green]{suffix}: {cmd.description}")

        self.add_output(
            "\n[dim]Type 'help <command>' for detailed help on a specific command[/dim]"
        )

    def _show_command_help(self, cmd_name: str) -> None:
        """Display detailed help for a specific command, including subcommands if it's a group."""
        parts = cmd_name.split()

        # Check if this is a full path (e.g., "serialize excel") or just a top-level command
        if len(parts) == 1 and parts[0] in self.commands:
            command = self.commands[parts[0]]

            # If this is a group, show custom help with subcommands
            if getattr(command, "is_group", False):
                self.add_output(f"[bold cyan]Command Group:[/bold cyan] [green]{cmd_name}[/green]")
                self.add_output(f"[bold cyan]Description:[/bold cyan] {command.description}\n")
                self.add_output("[bold cyan]Subcommands:[/bold cyan]")

                # Find all subcommands belonging to this group
                subcommands = {
                    name: cmd
                    for name, cmd in sorted(self.commands.items())
                    if hasattr(cmd, "parent") and cmd.parent == cmd_name
                }

                for sub_name, sub_cmd in subcommands.items():
                    # Display only the subcommand part (not the full path)
                    display_name = sub_name.split()[-1]
                    self.add_output(f"  [green]{display_name}[/green]: {sub_cmd.description}")

                self.add_output(
                    f"\n[dim]Type 'help {cmd_name} <subcommand>' for detailed help[/dim]"
                )
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

    def display_history(self) -> None:
        """Display the command history in the output widget."""
        self.add_output("[bold cyan]Command History:[/bold cyan]")
        if not self.history_manager.history:
            self.add_output("  [dim]No history yet.[/dim]")
            return
        for i, cmd in enumerate(self.history_manager.history, 1):
            self.add_output(f"  [green]{i:>3}[/green]: {cmd}")


if __name__ == "__main__":
    app = CLIApp()
    app.run()
