"""tui_typer.ui — interactive UI tools and helpers.

All sub-modules are imported lazily so that importing a lightweight module
(e.g. ``tui_typer.ui.console``) does not pull in Textual widget code at
CLI startup time.

Public surface
--------------
* :class:`FilePickerScreen`      — modal directory tree browser / file picker
* :class:`FuzzyFileSearchScreen` — modal live fuzzy file searcher
* :class:`PathSuggester`         — tab-completion suggester for path tokens
* :class:`EditorLauncher`        — open files in an external editor
* :class:`CommandProvider`       — Textual command-palette provider
* :class:`TextualLogHandler`     — loguru → RichLog sink
* :class:`TextualProgressSink`   — progress-queue → ProgressBar adapter
* :class:`CliConsole`            — Rich console wrapper for batch output
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tui_typer.ui.command_provider import CommandProvider
    from tui_typer.ui.console import CliConsole
    from tui_typer.ui.editor import EditorLauncher
    from tui_typer.ui.file_picker import FilePickerResult, FilePickerScreen
    from tui_typer.ui.fuzzy_search import FuzzyFileSearchScreen
    from tui_typer.ui.logging import TextualLogHandler, TextualProgressSink
    from tui_typer.ui.path_suggester import PathSuggester

__all__ = [
    "CommandProvider",
    "CliConsole",
    "EditorLauncher",
    "FilePickerResult",
    "FilePickerScreen",
    "FuzzyFileSearchScreen",
    "PathSuggester",
    "TextualLogHandler",
    "TextualProgressSink",
]

_MODULE_MAP = {
    "CommandProvider": "tui_typer.ui.command_provider",
    "CliConsole": "tui_typer.ui.console",
    "EditorLauncher": "tui_typer.ui.editor",
    "FilePickerResult": "tui_typer.ui.file_picker",
    "FilePickerScreen": "tui_typer.ui.file_picker",
    "FuzzyFileSearchScreen": "tui_typer.ui.fuzzy_search",
    "TextualLogHandler": "tui_typer.ui.logging",
    "TextualProgressSink": "tui_typer.ui.logging",
    "PathSuggester": "tui_typer.ui.path_suggester",
}


def __getattr__(name: str) -> object:
    if name in _MODULE_MAP:
        import importlib

        module = importlib.import_module(_MODULE_MAP[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
