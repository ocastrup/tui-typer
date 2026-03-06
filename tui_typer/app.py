"""Textual TUI application.

This module contains :class:`CLIApp`, the Textual ``App`` subclass that
provides the interactive UI.  Command execution is delegated to
:func:`~tui_typer.command_dispatcher.base.dispatch_typer_command`, which
runs the underlying Click command directly in a thread and streams output
lines back to the TUI via an :class:`asyncio.Queue`.

Architecture
------------
::

    User input (Input widget)
         │
         ▼
    _execute_command()        ← dispatches a Textual worker
         │
         ▼
    dispatch_typer_command()  ← resolves Click command, runs in thread
         │        │
         │        └─ output_queue  ←  lines streamed back
         │
         ▼
    _stream_output_worker()   ← reads queue, writes to RichLog
"""

from __future__ import annotations

import asyncio
from difflib import get_close_matches
from pathlib import Path
import threading

from loguru import logger
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, ProgressBar, RichLog

from tui_typer.cli import cli, get_context_manager
from tui_typer.command_dispatcher.base import dispatch_typer_command
from tui_typer.command_dispatcher.history import HistoryManager
from tui_typer.command_dispatcher.loader import load_commands
from tui_typer.context.config import AppConfig
from tui_typer.ui.command_provider import CommandProvider
from tui_typer.ui.logging import TextualLogHandler, TextualProgressSink


class CLIApp(App):
    """Interactive TUI application combining Textual and Typer.

    The app composes a two-pane layout:

    * **Output log** — rich-marked-up command results.
    * **Logger log** — loguru log stream.
    * **Progress bar** — driven by the ``progress_callback`` injected into commands.
    * **Input box** — command prompt at the bottom.

    History navigation (up/down arrows) is supported via
    :class:`~tui_typer.command_dispatcher.history.HistoryManager`.
    """

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
        height: 3;
        border: tall blue;
    }
    #input-box {
        dock: bottom;
        height: 3;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("escape", "cancel_command", "Cancel"),
    ]
    COMMANDS = App.COMMANDS | {CommandProvider}

    def __init__(self) -> None:
        super().__init__()
        self.app_config = AppConfig(config_path=str(Path.home() / ".tui_typer.ini"))
        self.history_manager = HistoryManager(
            self.app_config.history_file,
            self.app_config.max_history,
        )
        self.history_index: int = -1
        self.current_input: str = ""
        self.commands = {}

        # Cancel event for the currently-running command (None when idle)
        self._active_cancel_event: threading.Event | None = None

        # Mark the shared ContextManager as interactive
        self._context_manager = get_context_manager()
        self._context_manager.interactive = True

    # ------------------------------------------------------------------
    # Compose & lifecycle
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-container"):
            yield RichLog(id="output-log", highlight=True, markup=True)
            yield RichLog(id="logger-log", highlight=True, markup=True)
            yield ProgressBar(id="progress-bar", total=100, show_eta=False)
        yield Input(id="input-box", placeholder="Enter command...")
        yield Footer()

    def on_mount(self) -> None:
        """Wire up widgets and configure loguru after mount."""
        self.log_widget = self.query_one("#logger-log", RichLog)
        self.output_widget = self.query_one("#output-log", RichLog)
        self.progress_widget = self.query_one("#progress-bar", ProgressBar)
        self.progress_sink = TextualProgressSink(self.progress_widget)

        self.query_one("#input-box", Input).focus()

        # Route loguru → Textual log widget
        logger.remove()
        log_level = self.app_config.get("general", "log_level", fallback="INFO")
        logger.add(
            TextualLogHandler(self.log_widget).write,
            format="{message}",
            level=log_level,
            colorize=False,
        )
        logger.info("Logger initialized.")

        # Introspect the Typer CLI and build the command registry
        self.typer_cli = cli
        self.commands = load_commands(self.typer_cli)
        logger.info(f"Loaded {len(self.commands)} commands.")

    # ------------------------------------------------------------------
    # Keyboard history navigation
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Cancel action
    # ------------------------------------------------------------------

    def action_cancel_command(self) -> None:
        """Signal the running command to stop (bound to Escape).

        Sets the :class:`threading.Event` that is passed into every command via
        ``ctx.obj['cancel_event']``.  Long-running commands (e.g. ``scan-files``)
        poll this event between work items and exit early when it is set.

        If no command is currently running, a message is shown in the output log.
        """
        if self._active_cancel_event is not None:
            self._active_cancel_event.set()
            self.add_output(
                "[bold yellow]⚠ Cancellation requested — stopping after current item…[/bold yellow]"
            )
            logger.info("User requested cancellation via Escape.")
        else:
            self.add_output("[dim]No command is currently running.[/dim]")

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter — dispatch the entered command."""
        command = event.value.strip()
        if command:
            self.add_output(f"[bold cyan]>[/bold cyan] {command}")
            self.history_manager.add(command)
            self.history_index = -1
            self.current_input = ""
            self.run_worker(
                self._execute_command(command),
                exclusive=False,
                name=f"cmd:{command.split()[0]}",
            )
        event.input.value = ""

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def add_output(self, text: str) -> None:
        """Write a rich-marked-up line to the output log."""
        self.output_widget.write(text)

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    async def _execute_command(self, command_line: str) -> None:
        """Resolve and run a command entered in the TUI input box."""
        parts = command_line.strip().split()
        if not parts:
            return

        cmd_name = parts[0].lower()

        # --- Built-ins handled in the TUI layer ---
        if cmd_name in {"exit", "quit"}:
            self.add_output("[dim]Exiting…[/dim]")
            self.exit()
            return

        if cmd_name == "history":
            self._display_history()
            return

        if cmd_name == "help":
            if len(parts) > 1:
                self._show_command_help(" ".join(parts[1:]))
            else:
                self._show_all_commands_help()
            return

        # --- Validate command exists ---
        cmd_key = " ".join(parts[:2]) if len(parts) > 1 else parts[0]
        if parts[0] not in self.commands and cmd_key not in self.commands:
            self.add_output(f"[bold red]Unknown command:[/bold red] {parts[0]}")
            suggestions = get_close_matches(parts[0], list(self.commands.keys()), n=3, cutoff=0.6)
            if suggestions:
                self.add_output(f"[yellow]Did you mean:[/yellow] {', '.join(suggestions)}?")
            return

        # --- Streaming output via queue ---
        output_queue: asyncio.Queue[str | None] = asyncio.Queue()

        # Create and register the cancel event so action_cancel_command can set it
        cancel_event = threading.Event()
        self._active_cancel_event = cancel_event

        # Progress updates are delivered through a queue for the same reason as
        # text output: asyncio.to_thread() runs in a plain ThreadPoolExecutor
        # thread, and Textual widget mutations must happen on the event loop.
        # Putting a tuple on an asyncio.Queue via call_soon_threadsafe and
        # consuming it in a coroutine is the only pattern that is provably safe.
        # (call_soon_threadsafe alone is not sufficient because ProgressBar.update
        # is not re-entrant from an arbitrary thread context.)
        progress_queue: asyncio.Queue[tuple | None] = asyncio.Queue()

        loop = asyncio.get_event_loop()

        def _progress_cb(
            advance: float, total: float | None = None, description: str | None = None
        ) -> None:
            loop.call_soon_threadsafe(progress_queue.put_nowait, (advance, total))

        # Reset the progress bar before each command run
        self.progress_sink.reset()

        # Run dispatch + stream output + stream progress concurrently
        dispatch_task = asyncio.ensure_future(
            dispatch_typer_command(
                self.typer_cli,
                parts,
                context_manager=self._context_manager,
                progress_callback=_progress_cb,
                output_queue=output_queue,
                cancel_event=cancel_event,
            )
        )
        stream_task = asyncio.ensure_future(self._stream_output(output_queue))
        progress_task = asyncio.ensure_future(self._stream_progress(progress_queue))

        try:
            result = await dispatch_task
            await progress_queue.put(None)  # sentinel — stop the progress consumer
            await asyncio.gather(stream_task, progress_task)
        finally:
            # Command finished (normally or via cancellation) — clear the active event
            self._active_cancel_event = None
            # Snap bar to 100 % on clean completion; leave it where it stopped on cancel
            if not cancel_event.is_set():
                self.progress_sink.complete()

        # Handle --help output (delivered via result not queue)
        if "--help" in parts:
            if result.help_text:
                self.add_output(result.help_text)
            elif result.stdout:
                self.add_output(result.stdout)
            return

        # Streaming delivered output via the queue; only show stderr / help fallback
        if result.stderr:
            self.add_output(f"[red]Error:[/red] {result.stderr}")
        if result.exit_code != 0 and not result.stdout and not result.stderr and result.help_text:
            self.add_output(result.help_text)

    async def _stream_output(self, queue: asyncio.Queue[str | None]) -> None:
        """Consume lines from *queue* and write them to the output log.

        The producer puts ``None`` as a sentinel when done.
        """
        while True:
            line = await queue.get()
            if line is None:
                break
            self.add_output(line)

    async def _stream_progress(self, queue: asyncio.Queue[tuple | None]) -> None:
        """Consume progress tuples from *queue* and drive the progress bar.

        Each item is ``(advance, total)`` where *total* is ``None`` after the
        initial set-total call.  ``None`` itself is the end-of-stream sentinel.
        Running entirely on the event loop makes all ProgressBar mutations safe.
        """
        while True:
            item = await queue.get()
            if item is None:
                break
            advance, total = item
            if total is not None:
                self.progress_sink.set_total(total)
            self.progress_sink.update(advance)

    # ------------------------------------------------------------------
    # Help display
    # ------------------------------------------------------------------

    def _show_all_commands_help(self) -> None:
        """Display top-level commands in the output log."""
        self.add_output("[bold cyan]Available Commands:[/bold cyan]\n")
        top_level = {name: cmd for name, cmd in sorted(self.commands.items()) if cmd.parent is None}
        for name, cmd in top_level.items():
            suffix = " [dim](group)[/dim]" if cmd.is_group else ""
            self.add_output(f"  [green]{name}[/green]{suffix}: {cmd.description}")
        self.add_output(
            "\n[dim]Type 'help <command>' for detailed help on a specific command.[/dim]"
        )

    def _show_command_help(self, cmd_name: str) -> None:
        """Display detailed help for a specific command or group."""
        parts = cmd_name.split()

        if " ".join(parts) in self.commands:
            # Full path provided (e.g., "serialize excel") — show Typer help
            self.run_worker(self._dispatch_help(parts), name="help")
            return

        if len(parts) == 1 and parts[0] in self.commands:
            command = self.commands[parts[0]]
            if command.is_group:
                # Show group summary + subcommand list
                self.add_output(f"[bold cyan]Command Group:[/bold cyan] [green]{cmd_name}[/green]")
                self.add_output(f"[bold cyan]Description:[/bold cyan] {command.description}\n")
                self.add_output("[bold cyan]Subcommands:[/bold cyan]")
                subcommands = {
                    name: cmd
                    for name, cmd in sorted(self.commands.items())
                    if cmd.parent == cmd_name
                }
                for sub_full, sub_cmd in subcommands.items():
                    display_name = sub_full.split()[-1]
                    self.add_output(f"  [green]{display_name}[/green]: {sub_cmd.description}")
                self.add_output(
                    f"\n[dim]Type 'help {cmd_name} <subcommand>' for detailed help.[/dim]"
                )
                return
            # Leaf command → Typer help
            self.run_worker(self._dispatch_help([cmd_name]), name="help")
            return

        self.add_output(f"[bold red]Unknown command:[/bold red] {cmd_name}")

    async def _dispatch_help(self, cmd_parts: list[str]) -> None:
        """Fetch and display Typer-formatted help for *cmd_parts*."""
        result = await dispatch_typer_command(
            self.typer_cli,
            cmd_parts + ["--help"],
            context_manager=self._context_manager,
        )
        self.add_output(result.help_text or result.stdout)

    # ------------------------------------------------------------------
    # History display
    # ------------------------------------------------------------------

    def _display_history(self) -> None:
        """Show command history in the output log."""
        self.add_output("[bold cyan]Command History:[/bold cyan]")
        if not self.history_manager.history:
            self.add_output("  [dim]No history yet.[/dim]")
            return
        for i, cmd in enumerate(self.history_manager.history, 1):
            self.add_output(f"  [green]{i:>3}[/green]: {cmd}")

    # ------------------------------------------------------------------
    # Exit
    # ------------------------------------------------------------------

    def action_quit(self) -> None:
        """Save state and exit."""
        self._save_and_exit()

    def exit(self, result=None, return_code: int = 0, message=None) -> None:  # type: ignore[override]
        """Save history and config before exiting."""
        self._save_and_exit(result)

    def _save_and_exit(self, result=None) -> None:
        self.history_manager.save()
        self.app_config.save()
        super().exit(result)


if __name__ == "__main__":
    CLIApp().run()
