from tui_typer.ui.console import CliConsole
from .config import AppConfig


class ContextManager:
    """Provide context between sub commands."""

    def __init__(self, console: CliConsole, config: AppConfig):
        self._console: CliConsole = console
        self._config: AppConfig = config
        self._interactive: bool = False


    @property
    def console(self) -> CliConsole:
        return self._console

    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def interactive(self) -> bool:
        return self._interactive
    @interactive.setter
    def interactive(self, value: bool) -> None:
        self._interactive = value
