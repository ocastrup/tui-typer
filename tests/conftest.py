import asyncio
import os
import sys

import pytest
from typer.testing import CliRunner

# Ensure project root is on sys.path so tests can import top-level modules (e.g., cli.py)
# This file lives in <project>/tests/conftest.py; we want <project> on sys.path.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from cli import cli  # Typer app instance defined at project root
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
def run_dispatch(typer_cli):
    """Helper to run async dispatch in tests: returns (exit_code, stdout, stderr, help_text)."""

    async def _run(args):
        res = await dispatch_typer_command(typer_cli, args)
        return res.exit_code, res.stdout, res.stderr, res.help_text

    def _sync(args):
        return asyncio.run(_run(args))

    return _sync
