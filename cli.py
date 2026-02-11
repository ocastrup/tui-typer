import typer
from click import pass_context
from tui_typer.commands import typer_subcommand
from typing import Optional
from pathlib import Path

cli = typer.Typer(help="An Interactive OCX Reader CLI Application")


@pass_context
@cli.callback()
def main(ctx: typer.Context):
    """Main entry point for the CLI application."""

    # context = ContextManager(
    #     console=CliConsole(),
    #     config=AppConfig(config_path=None))
    # ctx.obj = context
    pass



@cli.command()
def interactive(
        config: Optional[Path] = typer.Option(".cli_app.ini", "--config", "-c", help="Config file path"),
        debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug mode"),
):
    """Launch the interactive TUI mode."""
    from app import CLIApp
    cli_app = CLIApp()
    cli_app.run()


@cli.command()
def version():
    """Display the application version."""
    typer.echo("OCX Reader CLI v1.0.0")


@cli.command(name="list-commands")
def list_commands():
    """List all available commands."""
    from click import Group
    click_group = typer.main.get_group(cli)

    typer.echo("Available commands:")
    if isinstance(click_group, Group):
        for cmd_name in sorted(click_group.commands.keys()):
            cmd = click_group.commands[cmd_name]
            help_text = cmd.help or cmd.short_help or "No description"
            typer.echo(f"  {cmd_name:<20} {help_text}")


@cli.command()
def history():
    """Display the command history."""
    # This is a placeholder and will be handled by the TUI
    pass


# Register subcommands AFTER all direct commands
cli.add_typer(typer_subcommand.serialize, name="serialize")

if __name__ == "__main__":
    cli()