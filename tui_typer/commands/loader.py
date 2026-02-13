from click import Group
from loguru import logger
import typer

from tui_typer.commands.base import Command


def load_commands(typer_app: typer.Typer) -> dict[str, Command]:
    """Load all commands from a Typer application instance."""
    commands = {}
    click_group = typer.main.get_group(typer_app)

    if isinstance(click_group, Group):
        for cmd_name, cmd in click_group.commands.items():
            logger.debug(f"Loading command: {cmd_name}")
            help_text = cmd.help or cmd.short_help or ""
            is_group = isinstance(cmd, Group)

            command_obj = Command(
                name=cmd_name,
                description=help_text,
                typer_command=cmd,
                is_group=is_group,
                params=cmd.params,
            )
            if (
                command_obj.name == "interactive"
            ):  # Don't include the interactive command in the command palette
                logger.debug("Skipping 'interactive' command for command palette")
                continue
            commands[cmd_name] = command_obj

            if is_group:
                for sub_name, sub_cmd in cmd.commands.items():
                    full_name = f"{cmd_name} {sub_name}"
                    sub_help = sub_cmd.help or sub_cmd.short_help or ""

                    sub_command_obj = Command(
                        name=full_name,
                        description=sub_help,
                        typer_command=sub_cmd,
                        is_group=False,
                        parent=cmd_name,
                        params=sub_cmd.params,
                    )
                    commands[full_name] = sub_command_obj

    return commands
