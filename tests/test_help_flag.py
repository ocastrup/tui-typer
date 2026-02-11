"""Test script to verify --help flag works correctly."""
from typer.testing import CliRunner
from cli import cli

def test_version_help():
    runner = CliRunner()
    res = runner.invoke(cli, ["version", "--help"], catch_exceptions=True)
    assert res.exit_code == 0
    assert "Usage:" in res.stdout


def test_serialize_excel_help():
    runner = CliRunner()
    res = runner.invoke(cli, ["serialize", "excel", "--help"], catch_exceptions=True)
    assert res.exit_code == 0
    assert "Usage:" in res.stdout
