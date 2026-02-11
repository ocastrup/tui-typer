import asyncio
from unittest.mock import MagicMock

from app import CLIApp


def test_exit_invokes_app_exit_directly():
    app = CLIApp()
    # Avoid touching UI widgets in tests
    app._non_interactive = True
    # Mock exit to verify it's called
    app.exit = MagicMock()

    async def run():
        await app._execute_command("exit")

    asyncio.run(run())

    app.exit.assert_called_once()
