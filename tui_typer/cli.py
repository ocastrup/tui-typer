"""Root Typer CLI definition.

This module defines the top-level :data:`cli` Typer application and the
shared :class:`~tui_typer.context.context_manager.ContextManager` singleton
factory.

Adding new sub-command groups
------------------------------
1. Create a :class:`typer.Typer` instance in a submodule under
   ``tui_typer/typer_subcommands/``.
2. Import it here and call ``cli.add_typer(...)`` **below** all direct
   command definitions (to avoid decorator-order issues).

Batch vs interactive mode
--------------------------
When running without the TUI (pure Typer / scripted), invoke commands
directly via::

    python -m tui_typer.cli <command> [options]

or use :func:`tui_typer.command_dispatcher.base.dispatch_sync` in your own
scripts.  The :data:`cli` callback sets ``ctx.obj['context_manager']`` so
that all commands receive the same singleton regardless of invocation path.
"""

from __future__ import annotations

from loguru import logger
import typer

from tui_typer import typer_subcommands
from tui_typer.context.config import AppConfig
from tui_typer.context.context_manager import ContextManager
from tui_typer.ui.console import CliConsole

# Remove loguru's default stderr sink so that batch CLI invocations don't emit
# DEBUG noise.  The TUI app re-adds a sink in CLIApp.on_mount(); batch mode
# can add its own sink if needed (e.g., for --verbose support).
logger.remove()

# ---------------------------------------------------------------------------
# Root CLI application
# ---------------------------------------------------------------------------

cli = typer.Typer(
    name="tui-typer",
    help="Interactive TUI application with Typer-powered sub-commands.",
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Singleton ContextManager factory
# ---------------------------------------------------------------------------

_context_manager: ContextManager | None = None


def get_context_manager() -> ContextManager:
    """Return (or lazily create) the application-wide :class:`ContextManager` singleton.

    In TUI mode the singleton is created once when the :class:`~tui_typer.app.CLIApp`
    starts and then injected into every command via ``ctx.obj``.  In batch /
    scripted mode this factory is called on demand.

    If you need to reset the singleton in tests, set
    ``tui_typer.cli._context_manager = None`` before calling this function.
    """
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager(
            console=CliConsole(),
            config=AppConfig(),
        )
    return _context_manager


# ---------------------------------------------------------------------------
# Root callback — runs before every command
# ---------------------------------------------------------------------------


@cli.callback()
def _root_callback(ctx: typer.Context) -> None:
    """Initialise shared context before any sub-command runs."""
    if ctx.obj is None:
        ctx.obj = {}
    # Preserve an already-injected ContextManager (e.g. from the TUI dispatcher)
    # so that state is not reset between commands.
    if "context_manager" not in ctx.obj:
        ctx.obj["context_manager"] = get_context_manager()
    logger.debug(
        f"CLI callback: context_manager id={id(ctx.obj['context_manager'])} "
        f"interactive={ctx.obj['context_manager'].interactive}"
    )


# ---------------------------------------------------------------------------
# Built-in top-level commands
# ---------------------------------------------------------------------------


@cli.command()
def interactive() -> None:
    """Launch the interactive Textual TUI."""
    from tui_typer.app import CLIApp

    app = CLIApp()
    app.run()


@cli.command()
def version() -> None:
    """Display the application version."""
    from tui_typer import __app_name__

    typer.echo(f"{__app_name__} v0.1.0")


@cli.command(name="list-commands")
def list_commands() -> None:
    """List all registered commands."""
    from click import Group

    click_group = typer.main.get_group(cli)
    typer.echo("Available commands:")
    if isinstance(click_group, Group):
        for cmd_name in sorted(click_group.commands.keys()):
            cmd = click_group.commands[cmd_name]
            help_text = cmd.help or cmd.short_help or "No description"
            typer.echo(f"  {cmd_name:<22} {help_text}")


@cli.command()
def history(ctx: typer.Context) -> None:
    """Display the command history (TUI mode only)."""
    # In batch mode there is no TUI history to show.
    context_manager: ContextManager = ctx.obj["context_manager"]
    if not context_manager.interactive:
        typer.echo("History is only available in interactive (TUI) mode.")


# ---------------------------------------------------------------------------
# Sub-command groups
# ---------------------------------------------------------------------------

cli.add_typer(
    typer_subcommands.serialize,
    name="serialize",
    help="Commands to serialize data into various formats.",
)

# ---------------------------------------------------------------------------
# Direct script entry point (batch mode)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
