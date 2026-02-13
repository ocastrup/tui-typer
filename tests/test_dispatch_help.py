import re

import pytest
from typer.testing import CliRunner

from cli import cli
from tui_typer.commands.base import dispatch_typer_command

runner = CliRunner()


@pytest.mark.parametrize(
    "args",
    [
        ["version", "--help"],
        ["serialize", "excel", "--help"],
    ],
)
def test_help_shows_usage(runner: CliRunner, args):
    result = runner.invoke(cli, args, catch_exceptions=True)
    assert (
        result.exit_code == 0
    ), f"Expected exit_code 0, got {result.exit_code}; exception={result.exception}"
    assert result.stdout, "Expected help text in stdout"
    assert re.search(r"Usage:\s+root\s+", result.stdout), "Usage header missing in help output"


def test_serialize_excel_options_present(runner: CliRunner):
    result = runner.invoke(cli, ["serialize", "excel", "--help"], catch_exceptions=True)
    assert result.exit_code == 0
    text = result.stdout
    assert "--file-name" in text and "report.xlsx" in text


def test_dispatch_async_help():
    async def _run():
        res = await dispatch_typer_command(cli, ["serialize", "excel", "--help"])
        assert res.exit_code == 0
        text = res.help_text or res.stdout
        assert text and "Usage:" in text

    import asyncio

    asyncio.run(_run())
