"""CLI console"""

# System imports

from enum import Enum

from loguru import logger

# Third party imports
from rich.console import Console
from rich.markdown import Markdown
from rich.style import Style
from rich.table import Table
from rich.theme import Theme

# Styling

PADDING = f'{" " * 5}'
console_theme = Theme({"info": "dim cyan", "warning": "magenta", "error": "bold red"})

style_table_header = Style(color="blue", bold=True)
style_section = Style(color="blue", bold=True)


class Justify(Enum):
    """Justify enum"""

    CENTER = "center"
    LEFT = "left"
    RIGHT = "right"
    FULL = "full"


class CliConsole(Console):
    """
    CLI console
    """

    def __init__(
        self,
    ):
        super().__init__(theme=console_theme)

    def print_table(self, table: Table, justify: Justify = Justify.CENTER):
        """
        Console table print method

        Args:
            justify: Justify the table in the console. Default = ``center``
            table: A Rich Table to output.

        """
        self.print("\n")
        self.print(table, justify=justify.value)
        self.print("\n")

    def print_table_row(self, table: Table, cells: list, justify: Justify = Justify.CENTER):
        """
        Console table print method

        Args:
            justify: Justify the table in the console. Default = ``center``
            table: A Rich Table to output.

        """
        table.add_row(*[str(cell) for cell in cells])
        self.print(table, justify=justify.value, show_header=False)

    def error(self, msg: str):
        """
        Console error print method

        Args:
            msg: Output message

        """
        self.print(f":cross_mark:{PADDING}{msg}", style="error")

    def info(self, msg: str | Markdown):
        """
        Console info print method

        Args:
            msg: Output message

        """
        self.print(f":information:{PADDING}{msg}", style="info")
        logger.info(msg)

    def warning(self, msg: str):
        """
        Console info print method

        Args:
            msg: Output message

        """
        self.print(f":warning:{PADDING}{msg}", style="warning")
        logger.warning(msg)

    def section(self, title: str, separator: str = "=", style: Style = style_section):
        """

        Args:
            style: The rule style
            separator: The rule characters
            title: The section title

        """
        self.rule(title=f"[bold black]{title}[/bold black]", characters=separator, style=style)
