import asyncio
import pytest
from typer.testing import CliRunner
from cli import cli
from tui_typer.commands.base import dispatch_typer_command

@pytest.fixture(scope="session")
def typer_cli():
    """Provide the Typer CLI app instance."""
    return cli

@pytest.fixture()
def runner():
    """Provide a Click/Typer CLI runner."""
    return CliRunner()

@pytest.fixture()
def run_dispatch():
    """Helper to run async dispatch in tests: returns (exit_code, stdout, stderr, help_text)."""
    async def _run(args):
        res = await dispatch_typer_command(cli, args)
        return res.exit_code, res.stdout, res.stderr, res.help_text
    def _sync(args):
        return asyncio.run(_run(args))
    return _sync
