"""Tests for async command execution and CommandProvider callback presence."""

import asyncio


def test_imports():
    from tui_typer.ui.command_provider import CommandProvider

    assert hasattr(CommandProvider, "_create_command_callback")


def test_async_command_executes():
    from cli import cli
    from tui_typer.commands.base import dispatch_typer_command

    async def _run():
        result = await dispatch_typer_command(cli, ["version"])
        assert result.exit_code == 0
        assert "OCX Reader CLI" in result.stdout

    asyncio.run(_run())


def test_command_provider_has_callback():
    from tui_typer.ui.command_provider import CommandProvider

    assert hasattr(CommandProvider, "_create_command_callback")
