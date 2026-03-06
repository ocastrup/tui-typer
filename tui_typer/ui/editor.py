"""Editor launcher — open a file in an external editor from the TUI.

Supports three launch strategies, tried in order:

1. ``$EDITOR`` environment variable (e.g. ``vim``, ``nano``, ``code``)
2. ``$VISUAL`` environment variable
3. Platform default: ``notepad`` on Windows, ``vi`` on POSIX

For terminal editors (vim, nano, …) the Textual app is **suspended** with
:meth:`~textual.app.App.suspend` so the editor gets full control of the
terminal, then the TUI resumes cleanly when the editor exits.

For GUI editors (VS Code ``code``, Notepad, …) the process is launched
detached so the TUI keeps running.

Usage
-----
::

    from tui_typer.ui.editor import EditorLauncher

    launcher = EditorLauncher()

    # From an async context (inside a Textual worker / action):
    await launcher.open_async(app, path)

    # From a synchronous context:
    launcher.open_detached(path)

The :class:`EditorLauncher` can also be used stand-alone without the TUI
by calling :meth:`open_blocking`.
"""

from __future__ import annotations

import os
from pathlib import Path
import platform
import subprocess
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from textual.app import App


# ---------------------------------------------------------------------------
# Editor detection
# ---------------------------------------------------------------------------

# Editors whose executable name implies they are terminal-based and therefore
# require Textual to suspend the TUI while they run.
_TERMINAL_EDITORS = frozenset(
    {
        "vi",
        "vim",
        "nvim",
        "nano",
        "pico",
        "emacs",
        "joe",
        "micro",
        "mcedit",
        "ne",
        "ed",
        "ex",
        "helix",
        "hx",
    }
)


def _detect_editor() -> tuple[str, bool]:
    """Return ``(editor_command, is_terminal_editor)``.

    Tries ``$EDITOR``, then ``$VISUAL``, then falls back to a
    platform-appropriate default.
    """
    for env_var in ("EDITOR", "VISUAL"):
        cmd = os.environ.get(env_var, "").strip()
        if cmd:
            name = Path(cmd).stem.lower()
            return cmd, name in _TERMINAL_EDITORS

    # Platform fallback
    if platform.system() == "Windows":
        return "notepad", False
    return "vi", True


# ---------------------------------------------------------------------------
# Launcher
# ---------------------------------------------------------------------------


class EditorLauncher:
    """Opens files in an external editor, handling TUI suspend/resume.

    Parameters
    ----------
    editor:
        Override the editor command.  When ``None`` (default) the editor is
        auto-detected from ``$EDITOR``, ``$VISUAL``, or the platform default.
    """

    def __init__(self, editor: str | None = None) -> None:
        if editor is not None:
            name = Path(editor).stem.lower()
            self._editor = editor
            self._is_terminal = name in _TERMINAL_EDITORS
        else:
            self._editor, self._is_terminal = _detect_editor()

    @classmethod
    def from_config(cls, config: object) -> EditorLauncher:
        """Construct an :class:`EditorLauncher` using the preferred editor
        stored in *config*.

        Resolution order (first non-empty value wins):

        1. ``[editor] command`` in the INI config file
        2. ``$EDITOR`` environment variable
        3. ``$VISUAL`` environment variable
        4. Platform default (``notepad`` on Windows, ``vi`` on POSIX)

        Parameters
        ----------
        config:
            An :class:`~tui_typer.context.config.AppConfig` instance (typed
            as ``object`` to avoid a circular import at module level).
        """
        # config.editor returns None when the INI key is empty/missing
        editor_cmd: str | None = getattr(config, "editor", None)
        if editor_cmd:
            logger.debug(f"EditorLauncher: using config editor '{editor_cmd}'")
        else:
            logger.debug(
                "EditorLauncher: no config editor set — falling back to env/platform default"
            )
        return cls(editor=editor_cmd)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def editor(self) -> str:
        """The resolved editor command."""
        return self._editor

    @property
    def is_terminal_editor(self) -> bool:
        """``True`` if the editor runs inside the terminal (requires TUI suspend)."""
        return self._is_terminal

    async def open_async(self, app: App, path: Path) -> int:
        """Open *path* in the editor from an async (Textual worker) context.

        For terminal editors the TUI is **suspended** via
        :meth:`~textual.app.App.suspend` so the editor gets a clean
        terminal, then the TUI resumes automatically.

        For GUI editors the process is launched detached and the TUI
        continues running immediately.

        Parameters
        ----------
        app:
            The running :class:`~textual.app.App` instance.
        path:
            The file to open.

        Returns
        -------
        int
            Exit code from the editor process (always 0 for detached GUI editors).
        """
        path = path.resolve()
        if not path.exists():
            logger.warning(f"EditorLauncher: file not found: {path}")

        if self._is_terminal:
            return await self._open_terminal_async(app, path)
        else:
            return self._open_detached(path)

    def open_blocking(self, path: Path) -> int:
        """Open *path* in the editor, blocking until it closes.

        Use this in batch / non-TUI contexts.

        Returns
        -------
        int
            Editor exit code.
        """
        path = path.resolve()
        cmd = [self._editor, str(path)]
        logger.info(f"EditorLauncher: opening '{path}' with '{self._editor}' (blocking)")
        try:
            result = subprocess.run(cmd, check=False)
            return result.returncode
        except FileNotFoundError:
            logger.error(f"EditorLauncher: editor '{self._editor}' not found on PATH.")
            return 1

    def open_detached(self, path: Path) -> int:
        """Launch the editor detached (non-blocking).  Returns 0 on success."""
        return self._open_detached(path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _open_terminal_async(self, app: App, path: Path) -> int:
        """Suspend the TUI, run the terminal editor, resume the TUI."""
        import asyncio

        cmd = [self._editor, str(path)]
        logger.info(f"EditorLauncher: suspending TUI to open '{path}' with '{self._editor}'")

        exit_code = 0

        def _run_editor() -> None:
            nonlocal exit_code
            # suspend() is a synchronous context manager; call it from the
            # thread so the blocking subprocess.run() happens while suspended.
            try:
                with app.suspend():
                    result = subprocess.run(cmd, check=False)  # noqa: S603
                    exit_code = result.returncode
            except FileNotFoundError:
                logger.error(f"EditorLauncher: editor '{self._editor}' not found on PATH.")
                exit_code = 1
            except Exception as exc:
                logger.error(f"EditorLauncher: suspend/editor error: {exc}")
                exit_code = 1

        await asyncio.to_thread(_run_editor)
        logger.info(f"EditorLauncher: TUI resumed after editor exit (code={exit_code})")
        return exit_code

    def _open_detached(self, path: Path) -> int:
        """Launch a GUI editor as a detached subprocess."""
        cmd = [self._editor, str(path)]
        logger.info(f"EditorLauncher: launching '{self._editor}' detached for '{path}'")
        try:
            if platform.system() == "Windows":
                subprocess.Popen(  # noqa: S603
                    cmd,
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                )
            else:
                subprocess.Popen(  # noqa: S603
                    cmd,
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            return 0
        except FileNotFoundError:
            logger.error(f"EditorLauncher: editor '{self._editor}' not found on PATH.")
            return 1
