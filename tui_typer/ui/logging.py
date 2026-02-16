from textual.widgets import ProgressBar, RichLog


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


class TextualProgressSink:
    """Async-safe sink for progress updates to a Textual ProgressBar widget."""

    def __init__(self, progress_widget: ProgressBar):
        self.progress_widget = progress_widget
        self._total = 100.0
        self._current = 0.0

    def set_total(self, total: float) -> None:
        """Set the total for progress calculation."""
        self._total = total
        self.progress_widget.update(total=total)

    def update(self, advance: float = 1.0, description: str | None = None) -> None:
        """Update progress by advancing the specified amount."""
        self._current = min(self._current + advance, self._total)
        self.progress_widget.update(progress=self._current)

    def set_progress(self, value: float, description: str | None = None) -> None:
        """Set progress to a specific value."""
        self._current = min(value, self._total)
        self.progress_widget.update(progress=self._current)

    def reset(self) -> None:
        """Reset progress to zero."""
        self._current = 0.0
        self.progress_widget.update(progress=0.0)

    def complete(self) -> None:
        """Mark progress as complete."""
        self._current = self._total
        self.progress_widget.update(progress=self._total)
