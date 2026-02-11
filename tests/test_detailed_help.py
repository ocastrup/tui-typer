"""Unit tests for CLI help commands."""
from typer.testing import CliRunner
from cli import cli


def test_help_contains_usage_and_options():
    runner = CliRunner()
    res = runner.invoke(cli, ["serialize", "excel", "--help"], catch_exceptions=True)
    assert res.exit_code == 0
    assert "Usage:" in res.stdout
    assert "--file-name" in res.stdout
