"""Test script to verify history command and command execution work correctly."""

import asyncio

from typer.testing import CliRunner

from cli import cli
from tui_typer.commands.base import dispatch_typer_command
from tui_typer.commands.config import AppConfig
from tui_typer.commands.history import HistoryManager


def test_history_manager_basic():
    config = AppConfig(config_path=None)
    history = HistoryManager(config.history_file, max_history=10)
    history.add("version")
    history.add("help")
    history.add("list-commands")
    assert len(history.history) >= 3
    assert history.history[-1] == "list-commands"


def test_cli_commands_invoke(runner: CliRunner):
    result = runner.invoke(cli, ["version"], catch_exceptions=True)
    assert result.exit_code == 0
    assert "OCX Reader CLI" in result.stdout

    result = runner.invoke(cli, ["history"], catch_exceptions=True)
    assert result.exit_code == 0

    result = runner.invoke(cli, ["list-commands"], catch_exceptions=True)
    assert result.exit_code == 0


def test_async_dispatch_version_and_history():
    async def _run():
        res = await dispatch_typer_command(cli, ["version"])
        assert res.exit_code == 0
        assert "OCX Reader CLI" in res.stdout

        res = await dispatch_typer_command(cli, ["history"])
        assert res.exit_code == 0

    asyncio.run(_run())
