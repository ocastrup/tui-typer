"""Central context manager with pluggable state registry.

Design pattern
--------------
Any submodule that needs to share state across Typer commands should:

1. Define a plain dataclass (or any object) to hold its state::

       @dataclass
       class SerializeState:
           last_file: str | None = None
           records_written: int = 0

2. Register it once (e.g., at module import time or app start-up)::

       ctx = get_context_manager()
       ctx.register_state("serialize", SerializeState())

3. Retrieve it in any command::

       state: SerializeState = ctx.get_state("serialize", SerializeState)

The registry is intentionally untyped at the container level so that any
submodule can register without modifying this file.  The typed ``get_state``
helper re-establishes type-safety at the call site.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from tui_typer.context.config import AppConfig
    from tui_typer.ui.console import CliConsole

T = TypeVar("T")


class StateNotFoundError(KeyError):
    """Raised when a requested state key has not been registered."""


class ContextManager:
    """Central context manager providing shared state across sub-commands.

    Attributes
    ----------
    console:
        The active :class:`~tui_typer.ui.console.CliConsole` instance used for
        rich-formatted output.
    config:
        The :class:`~tui_typer.context.config.AppConfig` configuration store.
    interactive:
        ``True`` when the application is running inside the Textual TUI;
        ``False`` for pure-Typer batch / scripted operation.
    """

    def __init__(self, console: CliConsole, config: AppConfig) -> None:
        self._console: CliConsole = console
        self._config: AppConfig = config
        self._interactive: bool = False
        self._lock = threading.Lock()
        # Keyed registry of submodule state objects
        self._state_registry: dict[str, object] = {}

    # ------------------------------------------------------------------
    # Core properties
    # ------------------------------------------------------------------

    @property
    def console(self) -> CliConsole:
        """Active rich console."""
        return self._console

    @property
    def config(self) -> AppConfig:
        """Application configuration."""
        return self._config

    @property
    def interactive(self) -> bool:
        """Whether the TUI is active."""
        return self._interactive

    @interactive.setter
    def interactive(self, value: bool) -> None:
        self._interactive = value

    # ------------------------------------------------------------------
    # State registry
    # ------------------------------------------------------------------

    def register_state(self, key: str, state: object, *, overwrite: bool = False) -> None:
        """Register a submodule state object under *key*.

        Parameters
        ----------
        key:
            A unique string identifier for this state (e.g. ``"serialize"``).
        state:
            Any object that holds the submodule's cross-command state.
        overwrite:
            If ``False`` (default) and *key* is already registered, raises
            ``ValueError``.  Set to ``True`` to replace an existing entry.
        """
        with self._lock:
            if key in self._state_registry and not overwrite:
                raise ValueError(
                    f"State key '{key}' is already registered. Use overwrite=True to replace it."
                )
            self._state_registry[key] = state

    def get_state(self, key: str, state_type: type[T]) -> T:
        """Retrieve a registered state object as the given type.

        Parameters
        ----------
        key:
            The key used in :meth:`register_state`.
        state_type:
            The expected type — used only for type-checker satisfaction at the
            call site; no runtime isinstance check is performed.

        Raises
        ------
        StateNotFoundError
            If *key* has not been registered.
        """
        with self._lock:
            if key not in self._state_registry:
                raise StateNotFoundError(
                    f"No state registered under key '{key}'. "
                    "Call register_state() before get_state()."
                )
            return self._state_registry[key]  # type: ignore[return-value]

    def has_state(self, key: str) -> bool:
        """Return ``True`` if *key* is present in the registry."""
        with self._lock:
            return key in self._state_registry

    def unregister_state(self, key: str) -> None:
        """Remove a state entry from the registry (useful in tests)."""
        with self._lock:
            self._state_registry.pop(key, None)

    def registered_keys(self) -> list[str]:
        """Return a snapshot of all currently registered state keys."""
        with self._lock:
            return list(self._state_registry.keys())

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover
        keys = self.registered_keys()
        return f"<ContextManager interactive={self._interactive} states={keys}>"
