"""Load commands from a Typer application into Command descriptors."""

from click import Group
from loguru import logger
import typer

from tui_typer.command_dispatcher.base import Command


def load_commands(typer_app: typer.Typer) -> dict[str, Command]:
    """Introspect a Typer application and return a flat map of :class:`Command` descriptors.

    The returned dict uses the full command path as the key, e.g.::

        {
            "version": Command(name="version", ...),
            "serialize": Command(name="serialize", is_group=True, ...),
            "serialize excel": Command(name="serialize excel", parent="serialize", ...),
        }

    The ``"interactive"`` command is excluded — it is the TUI entry point
    itself and should not appear in the command palette.

    Parameters
    ----------
    typer_app:
        The root :class:`typer.Typer` instance.

    Returns
    -------
    dict[str, Command]
        Mapping of full command name → :class:`Command`.
    """
    commands: dict[str, Command] = {}
    click_group = typer.main.get_group(typer_app)

    if not isinstance(click_group, Group):
        logger.warning("Typer app did not produce a Click Group — no commands loaded.")
        return commands

    for cmd_name, click_cmd in click_group.commands.items():
        if cmd_name == "interactive":
            logger.debug("Skipping 'interactive' command (TUI entry point).")
            continue

        logger.debug(f"Loading command: {cmd_name}")
        is_group = isinstance(click_cmd, Group)

        commands[cmd_name] = Command(
            name=cmd_name,
            description=click_cmd.help or click_cmd.short_help or "",
            click_command=click_cmd,
            is_group=is_group,
            params=click_cmd.params,
        )

        if is_group and isinstance(click_cmd, Group):
            for sub_name, sub_cmd in click_cmd.commands.items():
                full_name = f"{cmd_name} {sub_name}"
                logger.debug(f"  Loading subcommand: {full_name}")
                commands[full_name] = Command(
                    name=full_name,
                    description=sub_cmd.help or sub_cmd.short_help or "",
                    click_command=sub_cmd,
                    is_group=False,
                    parent=cmd_name,
                    params=sub_cmd.params,
                )

    return commands
