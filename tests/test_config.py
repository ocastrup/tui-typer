"""Tests for AppConfig persistence — INI file read on mount and write on exit.

Strategy
--------
We test our code directly rather than spinning up the full Textual app
(which requires a real terminal driver and is fragile in headless CI):

* **test_config_read_on_mount** — creates an INI file, constructs ``AppConfig``
  pointing at it, and asserts values are loaded exactly as ``on_mount`` would
  see them.

* **test_config_written_on_exit** — calls ``on_unmount`` directly on a
  partially-mocked ``CLIApp`` (all widget access patched out) and asserts
  the INI file is written to disk with the correct content.

This mirrors the pattern used in ``test_exit.py``.
"""

from __future__ import annotations

import configparser
from pathlib import Path
from unittest.mock import MagicMock

import tui_typer.cli as cli_module
from tui_typer.context.config import AppConfig

# ---------------------------------------------------------------------------
# Test 1 — INI values are available exactly as on_mount reads them
# ---------------------------------------------------------------------------


def test_config_read_on_mount(tmp_path: Path) -> None:
    """AppConfig loads custom INI values that on_mount uses (log_level, editor, etc.)."""
    ini_path = tmp_path / ".tui_typer_test.ini"

    # Write a pre-populated INI with recognisable custom values
    cfg = configparser.ConfigParser()
    cfg["general"] = {
        "log_level": "DEBUG",
        "max_history": "42",
        "history_file": str(tmp_path / "hist.txt"),
    }
    cfg["editor"] = {"command": "my_test_editor"}
    with open(ini_path, "w") as f:
        cfg.write(f)

    # Construct AppConfig the same way CLIApp.__init__ does
    app_config = AppConfig(config_path=str(ini_path))

    # Assert every value that on_mount reads is correct
    assert app_config.editor == "my_test_editor", "editor command was not read from INI"
    assert app_config.max_history == 42, "max_history was not read from INI"
    assert app_config.get("general", "log_level") == "DEBUG", "log_level was not read from INI"
    # history_file path must be expanded and correct
    assert app_config.history_file == tmp_path / "hist.txt", "history_file was not read from INI"


def test_config_defaults_applied_when_no_ini(tmp_path: Path) -> None:
    """When no INI file exists, all DEFAULT_CONFIG values are applied."""
    ini_path = tmp_path / "nonexistent.ini"
    assert not ini_path.exists()

    app_config = AppConfig(config_path=str(ini_path))

    # Defaults must be present
    assert app_config.get("general", "log_level") == "INFO"
    assert app_config.max_history == 100
    assert app_config.editor is None  # empty string → None


# ---------------------------------------------------------------------------
# Test 2 — on_unmount writes the INI file to disk
# ---------------------------------------------------------------------------


def test_config_written_on_exit(tmp_path: Path) -> None:
    """on_unmount calls app_config.save(); the INI file is created on disk."""
    ini_path = tmp_path / ".tui_typer_test.ini"
    assert not ini_path.exists(), "INI must not exist before the test"

    # Reset singleton so CLIApp.__init__ builds a fresh ContextManager
    cli_module._context_manager = None

    from tui_typer.app import CLIApp

    app = CLIApp()

    # Point app_config at our temp path
    app.app_config = AppConfig(config_path=str(ini_path))
    # Set a recognisable value to verify it is persisted
    app.app_config.set("editor", "command", "notepad")

    # Provide a minimal HistoryManager mock so on_unmount doesn't touch
    # the real history file
    mock_history = MagicMock()
    app.history_manager = mock_history

    # Call on_unmount directly — this is exactly what Textual calls on exit
    app.on_unmount()

    # history_manager.save() must have been called
    mock_history.save.assert_called_once()

    # INI file must now exist
    assert ini_path.exists(), "INI file was not created by on_unmount"

    # Verify content
    written = configparser.ConfigParser()
    written.read(ini_path)

    assert written.get("editor", "command") == "notepad", "editor command was not persisted to INI"
    assert written.has_option(
        "general", "log_level"
    ), "default [general] section was not written to INI"
