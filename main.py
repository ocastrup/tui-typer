"""tui-typer application entry point.

Run the interactive TUI::

    python main.py

Run a single command in batch mode (no TUI)::

    python main.py version
    python main.py serialize excel --file-name out.xlsx
    python main.py list-commands

When no arguments are given the interactive Textual TUI is launched.
When arguments are provided they are forwarded to the Typer CLI directly
(pure-batch mode, no event loop, no Textual).
"""

from __future__ import annotations

import sys


def main() -> None:
    """Unified entry point for both TUI and batch modes."""
    # If no arguments are passed, launch the interactive TUI directly.
    if len(sys.argv) == 1:
        from tui_typer.app import CLIApp

        CLIApp().run()
        return

    # Otherwise hand control to the Typer CLI (batch / scripted mode).
    from tui_typer.cli import cli

    cli()


if __name__ == "__main__":
    main()
