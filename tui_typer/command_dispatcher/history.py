"""Command history persistence."""

from __future__ import annotations

from pathlib import Path

from loguru import logger


class HistoryManager:
    """Manages command history persistence.

    History is stored as plain text, one command per line.  Errors during
    load or save are logged as warnings rather than crashing the application.
    """

    def __init__(self, history_file: Path, max_history: int = 100) -> None:
        self.history_file = history_file
        self.max_history = max_history
        self.history: list[str] = []
        self.load()

    def load(self) -> None:
        """Load history from file, silently ignoring I/O errors."""
        if not self.history_file.exists():
            return
        try:
            lines = self.history_file.read_text(encoding="utf-8").splitlines()
            self.history = [line.strip() for line in lines if line.strip()]
            self.history = self.history[-self.max_history :]
        except OSError as exc:
            logger.warning(f"Could not load history from {self.history_file}: {exc}")

    def save(self) -> None:
        """Persist history to file, silently ignoring I/O errors."""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            self.history_file.write_text(
                "\n".join(self.history[-self.max_history :]) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(f"Could not save history to {self.history_file}: {exc}")

    def add(self, command: str) -> None:
        """Append *command* to history (deduplicates consecutive identical entries)."""
        if command and (not self.history or self.history[-1] != command):
            self.history.append(command)
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history :]

    def get(self, index: int) -> str | None:
        """Return the history entry at *index*, or ``None`` if out of range."""
        if 0 <= index < len(self.history):
            return self.history[index]
        return None
