"""Direct test with CliRunner in asyncio.to_thread."""
from typer.testing import CliRunner
from cli import cli

def test_help_does_not_raise_defaultplaceholder():
    runner = CliRunner()
    result = runner.invoke(cli, ["serialize", "excel", "--help"], catch_exceptions=True)
    assert result.exit_code == 0, f"unexpected exit {result.exit_code}, exception={result.exception}"
    assert "Usage:" in result.stdout
