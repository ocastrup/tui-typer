import asyncio
from unittest.mock import MagicMock

from tui_typer.app import CLIApp


def test_exit_invokes_app_exit_directly():
    app = CLIApp()

    # Prevent any widget access — both add_output and exit are mocked
    app.add_output = MagicMock()
    app.exit = MagicMock()

    async def run():
        await app._execute_command("exit")

    asyncio.run(run())

    app.exit.assert_called_once()
