"""command_dispatcher package.

Public API
----------
- :class:`~tui_typer.command_dispatcher.base.Command`
- :class:`~tui_typer.command_dispatcher.base.DispatchResult`
- :func:`~tui_typer.command_dispatcher.base.dispatch_typer_command`
- :func:`~tui_typer.command_dispatcher.base.dispatch_sync`
- :func:`~tui_typer.command_dispatcher.loader.load_commands`
- :class:`~tui_typer.command_dispatcher.history.HistoryManager`
"""

from tui_typer.command_dispatcher.base import (
    Command,
    DispatchResult,
    dispatch_sync,
    dispatch_typer_command,
)
from tui_typer.command_dispatcher.history import HistoryManager
from tui_typer.command_dispatcher.loader import load_commands

__all__ = [
    "Command",
    "DispatchResult",
    "HistoryManager",
    "dispatch_sync",
    "dispatch_typer_command",
    "load_commands",
]
