from textual.widgets import RichLog


class TextualLogHandler:
    """Custom loguru sink that writes to a Textual RichLog widget."""

    LEVEL_COLORS = {
        "DEBUG": "blue",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold red",
    }

    def __init__(self, log_widget: RichLog):
        self.log_widget = log_widget

    def write(self, message) -> None:
        """Write log message to the widget."""
        record = message.record
        level = record["level"].name
        color = self.LEVEL_COLORS.get(level, "white")

        text = f"[{color}]{level: <8}[/{color}] | [cyan]{record['name']}[/cyan]:[cyan]{record['function']}[/cyan] - {record['message']}"
        self.log_widget.write(text)
