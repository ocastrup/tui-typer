import configparser
from pathlib import Path


class AppConfig:
    """Application configuration manager."""

    DEFAULT_CONFIG = {
        "general": {
            "app_name": "CLI App",
            "history_file": "~/.cli_app_history",
            "max_history": "100",
        },
        "display": {
            "theme": "default",
            "show_timestamps": "false",
        },
    }

    def __init__(self, config_path: str = None):
        self.config = configparser.ConfigParser()
        self.config_path = Path(config_path or "~/.cli_app.ini").expanduser()
        self._load_defaults()
        self.load()

    def _load_defaults(self) -> None:
        """Load default configuration."""
        for section, options in self.DEFAULT_CONFIG.items():
            self.config[section] = options

    def load(self) -> None:
        """Load configuration from file."""
        if self.config_path.exists():
            self.config.read(self.config_path)

    def save(self) -> None:
        """Save configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            self.config.write(f)

    def get(self, section: str, key: str, fallback: str = None) -> str:
        return self.config.get(section, key, fallback=fallback)

    def getint(self, section: str, key: str, fallback: int = 0) -> int:
        return self.config.getint(section, key, fallback=fallback)

    def getboolean(self, section: str, key: str, fallback: bool = False) -> bool:
        return self.config.getboolean(section, key, fallback=fallback)

    def set(self, section: str, key: str, value: str) -> None:
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = str(value)

    @property
    def history_file(self) -> Path:
        return Path(self.get("general", "history_file")).expanduser()

    @property
    def max_history(self) -> int:
        return self.getint("general", "max_history", 100)
