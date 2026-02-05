from pathlib import Path


class HistoryManager:
    """Manages command history persistence."""

    def __init__(self, history_file: Path, max_history: int = 100):
        self.history_file = history_file
        self.max_history = max_history
        self.history: list[str] = []
        self.load()

    def load(self) -> None:
        """Load history from file."""
        if self.history_file.exists():
            with open(self.history_file, "r") as f:
                self.history = [line.strip() for line in f if line.strip()]
                self.history = self.history[-self.max_history:]

    def save(self) -> None:
        """Save history to file."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, "w") as f:
            for cmd in self.history[-self.max_history:]:
                f.write(f"{cmd}\n")

    def add(self, command: str) -> None:
        """Add command to history."""
        if command and (not self.history or self.history[-1] != command):
            self.history.append(command)
            if len(self.history) > self.max_history:
                self.history = self.history[-self.max_history:]

    def get(self, index: int) -> str | None:
        """Get command at index."""
        if 0 <= index < len(self.history):
            return self.history[index]
        return None
