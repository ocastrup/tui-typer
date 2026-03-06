"""Command dispatcher: async-safe execution of Typer sub-commands.

Dispatch strategy
-----------------
There are two execution modes, chosen per invocation:

**Direct dispatch** (default for normal commands)
    The underlying Click ``Command`` object is located and its ``main()``
    method is called directly inside ``asyncio.to_thread``.  A
    ``StreamingOutput`` queue delivers output lines to the TUI as they are
    produced.  This supports cancellation and true incremental output.

**CliRunner dispatch** (used automatically for ``--help``)
    Typer's ``CliRunner`` is used when ``--help`` is in the argument list so
    that Click's native formatted help text is captured exactly as Typer
    renders it.  No streaming is needed for help.

Batch (non-async) mode
-----------------------
Both modes can be called from synchronous code via :func:`dispatch_sync`,
which wraps the async path in ``asyncio.run()``.  This is the entry point
for pure-Typer CLI invocations (no Textual).

Cancellation
------------
The worker task wrapping :func:`dispatch_typer_command` can be cancelled at
any time.  Because the underlying work runs in a thread, a ``cancel_event``
threading.Event is passed into the command's ``ctx.obj`` dict under the key
``'cancel_event'``.  Long-running commands should poll it::

    cancel: threading.Event = ctx.obj.get("cancel_event", threading.Event())
    for item in big_list:
        if cancel.is_set():
            raise typer.Exit()
        process(item)
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
import io
import threading

import click
from loguru import logger
import typer
from typer.testing import CliRunner

from tui_typer.context.context_manager import ContextManager

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass
class DispatchResult:
    """The result of a dispatched command.

    Attributes
    ----------
    exit_code:
        The process-style exit code (0 = success).
    stdout:
        Captured standard output (empty when streaming was used).
    stderr:
        Captured standard error.
    help_text:
        The formatted help text when ``--help`` was requested.
    """

    exit_code: int
    stdout: str
    stderr: str
    help_text: str = ""


@dataclass
class Command:
    """Metadata descriptor for a CLI command loaded from a Typer app.

    This is a pure data class — execution is handled by :func:`dispatch_typer_command`.

    Attributes
    ----------
    name:
        Full command path, e.g. ``"serialize excel"``.
    description:
        One-line help string shown in the command palette / help listing.
    click_command:
        The underlying :class:`click.BaseCommand` object.
    is_group:
        ``True`` if this entry represents a command group with sub-commands.
    parent:
        Name of the parent group, or ``None`` for top-level commands.
    params:
        The list of Click parameters (options + arguments).
    """

    name: str
    description: str
    click_command: click.BaseCommand
    is_group: bool = False
    parent: str | None = None
    params: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_ctx_obj(
    context_manager: ContextManager,
    confirm_callback: Callable[[str], bool] | None,
    progress_callback: Callable | None,
    summary_callback: Callable | None,
    cancel_event: threading.Event,
) -> dict:
    """Build the ``ctx.obj`` dict injected into every command invocation."""
    return {
        "context_manager": context_manager,
        "confirm_callback": confirm_callback,
        "progress_callback": progress_callback,
        "summary_callback": summary_callback,
        "cancel_event": cancel_event,
    }


# ---------------------------------------------------------------------------
# Help capture (CliRunner path)
# ---------------------------------------------------------------------------


def _capture_help(typer_app: typer.Typer, argv: list[str]) -> DispatchResult:
    """Use CliRunner to capture Typer/Click formatted help text."""
    runner = CliRunner()
    result = runner.invoke(typer_app, argv, catch_exceptions=True)
    return DispatchResult(
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr or "",
        help_text=result.stdout,
    )


# ---------------------------------------------------------------------------
# Streaming writer — bridges thread stdout → async queue
# ---------------------------------------------------------------------------


class _StreamingWriter:
    """A ``sys.stdout`` replacement that feeds lines into an async queue in real time.

    Each call to :meth:`write` is forwarded immediately to the event loop via
    ``loop.call_soon_threadsafe(queue.put_nowait, line)`` so that the TUI
    receives output *as the command produces it*, not after it finishes.

    When *queue* is ``None`` the writer falls back to buffering all output in
    an internal :class:`io.StringIO` so the result can be returned in
    :attr:`DispatchResult.stdout` (batch / non-streaming mode).

    Deliberately does **not** inherit from ``io.TextIOBase`` — Click's internal
    ``_default_text_stdout`` probe writes ``bytes`` to detect binary mode, which
    triggers a ``TypeError`` in ``TextIOBase.write``.  This plain class accepts
    both ``str`` and ``bytes`` gracefully.
    """

    # Attributes that Click / Python internals inspect on sys.stdout
    encoding = "utf-8"
    errors = "replace"
    softspace = 0

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue | None,
        buf: io.StringIO,
    ) -> None:
        self._loop = loop
        self._queue = queue
        self._buf = buf  # always written so stdout is in DispatchResult
        self._pending = ""  # accumulates partial lines between write() calls

    # ------------------------------------------------------------------ #
    # Core file-like interface                                             #
    # ------------------------------------------------------------------ #

    def write(self, text: str | bytes) -> int:
        # Click occasionally probes stdout with bytes; decode silently.
        if isinstance(text, bytes | bytearray):
            text = text.decode(self.encoding, errors=self.errors)
        if not text:
            return 0

        self._buf.write(text)

        if self._queue is None:
            return len(text)

        # Buffer until we have complete lines; push each complete line immediately
        self._pending += text
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            self._loop.call_soon_threadsafe(self._queue.put_nowait, line)

        return len(text)

    def flush(self) -> None:
        """Push any remaining partial line (no trailing newline)."""
        if self._queue is not None and self._pending:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, self._pending)
            self._pending = ""

    def writable(self) -> bool:
        return True

    def readable(self) -> bool:
        return False

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        raise io.UnsupportedOperation("fileno")


# ---------------------------------------------------------------------------
# Direct dispatch path
# ---------------------------------------------------------------------------


async def _dispatch_direct(
    typer_app: typer.Typer,
    argv: list[str],
    ctx_obj: dict,
    output_queue: asyncio.Queue | None,
    cancel_event: threading.Event,
) -> DispatchResult:
    """Invoke the Click command directly in a thread with real-time streaming.

    ``typer.echo()`` inside the command writes to a :class:`_StreamingWriter`
    which immediately forwards each complete line to *output_queue* via
    ``loop.call_soon_threadsafe``.  The TUI therefore receives output
    incrementally as the command runs — even if the command sleeps between
    lines — rather than all at once when the thread finishes.

    If *output_queue* is ``None`` all output is buffered and returned in
    :attr:`DispatchResult.stdout`.
    """
    loop = asyncio.get_event_loop()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    streaming_writer = _StreamingWriter(loop, output_queue, stdout_buf)

    def _run() -> tuple[int, str, str]:
        """Thread worker: resolves the click command and calls its main()."""
        import sys

        click_group = typer.main.get_group(typer_app)

        # Resolve nested command path (e.g. ["serialize", "excel"])
        cmd: click.BaseCommand = click_group
        remaining = list(argv)
        while remaining and isinstance(cmd, click.Group):
            sub_name = remaining[0]
            sub = cmd.commands.get(sub_name)
            if sub is None:
                break
            cmd = sub
            remaining = remaining[1:]

        # Replace sys.stdout with our streaming writer so every typer.echo()
        # is forwarded to the queue immediately, line by line.
        _orig_stdout, _orig_stderr = sys.stdout, sys.stderr
        sys.stdout = streaming_writer  # type: ignore[assignment]
        sys.stderr = stderr_buf  # type: ignore[assignment]

        try:
            with click.Context(
                cmd,
                info_name=" ".join(argv[: len(argv) - len(remaining)]) or argv[0],
                obj=ctx_obj,
                color=False,
            ):
                cmd.main(
                    args=remaining,
                    prog_name="root",
                    standalone_mode=False,
                    obj=ctx_obj,
                )
            exit_code = 0
        except SystemExit as exc:
            exit_code = int(exc.code) if exc.code is not None else 0
        except click.exceptions.Exit as exc:
            exit_code = (
                exc.exit_code
                if hasattr(exc, "exit_code")
                else (int(exc.code) if hasattr(exc, "code") else 0)
            )
        except click.exceptions.Abort:
            exit_code = 1
            stderr_buf.write("Aborted.")
        except Exception as exc:
            logger.exception(f"Direct dispatch error: {exc}")
            stderr_buf.write(str(exc))
            exit_code = 1
        finally:
            # Flush any partial line and restore stdout/stderr
            streaming_writer.flush()
            sys.stdout, sys.stderr = _orig_stdout, _orig_stderr

        return exit_code, stdout_buf.getvalue(), stderr_buf.getvalue()

    try:
        exit_code, stdout, stderr = await asyncio.to_thread(_run)
    except asyncio.CancelledError:
        cancel_event.set()
        logger.debug("Command cancelled by TUI worker cancellation.")
        return DispatchResult(exit_code=1, stdout="", stderr="Command cancelled.", help_text="")

    # Signal end-of-stream to the consumer
    if output_queue is not None:
        await output_queue.put(None)  # sentinel

    return DispatchResult(exit_code=exit_code, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def dispatch_typer_command(
    typer_app: typer.Typer,
    args: Sequence[str],
    context_manager: ContextManager | None = None,
    confirm_callback: Callable[[str], bool] | None = None,
    progress_callback: Callable | None = None,
    summary_callback: Callable | None = None,
    output_queue: asyncio.Queue | None = None,
    cancel_event: threading.Event | None = None,
) -> DispatchResult:
    """Dispatch a Typer sub-command asynchronously.

    Parameters
    ----------
    typer_app:
        The root :class:`typer.Typer` application.
    args:
        Command arguments, e.g. ``["serialize", "excel", "--file-name", "out.xlsx"]``.
    context_manager:
        The shared :class:`~tui_typer.context.context_manager.ContextManager`
        singleton.  When ``None`` a default instance is created.
    confirm_callback:
        Optional callable ``(message: str) -> bool`` that replaces blocking
        ``typer.confirm()`` prompts in the TUI.
    progress_callback:
        Optional callable ``(advance, total, description)`` for progress bar
        updates.
    summary_callback:
        Optional callable ``(text: str)`` called when a command finishes with
        a summary message.
    output_queue:
        When provided, stdout lines are streamed into this queue as they are
        produced, with ``None`` as a sentinel value at the end.  Enables
        the TUI to display incremental output without waiting for the full
        result.
    cancel_event:
        Optional :class:`threading.Event` that callers can set to request
        cancellation of the running command.  Commands poll this event between
        work items (e.g. between files in ``scan-files``).  When ``None`` a
        fresh event is created internally.  Pass your own event when you need
        to trigger cancellation from outside (e.g. a key binding in the TUI).

    Returns
    -------
    DispatchResult
        Contains exit code, captured stdout/stderr, and help text (if ``--help``
        was requested).
    """
    argv = list(args)
    if cancel_event is None:
        cancel_event = threading.Event()

    # Lazily import the singleton factory to avoid circular imports
    if context_manager is None:
        from tui_typer.cli import get_context_manager

        context_manager = get_context_manager()

    ctx_obj = _build_ctx_obj(
        context_manager=context_manager,
        confirm_callback=confirm_callback,
        progress_callback=progress_callback,
        summary_callback=summary_callback,
        cancel_event=cancel_event,
    )

    logger.debug(f"Dispatching: {argv}")

    # --help → use CliRunner to get native Typer-formatted help
    if "--help" in argv:
        logger.debug("Help requested — using CliRunner path.")
        result = await asyncio.to_thread(_capture_help, typer_app, argv)
        return result

    # Normal command → direct dispatch with optional streaming
    try:
        result = await _dispatch_direct(typer_app, argv, ctx_obj, output_queue, cancel_event)
    except Exception as exc:
        logger.exception(f"Unhandled dispatch error: {exc}")
        result = DispatchResult(
            exit_code=1,
            stdout="",
            stderr=f"Command execution failed: {exc}",
            help_text="",
        )

    if result.exit_code != 0 and not result.stdout and not result.stderr:
        # Command failed silently → show its help
        logger.debug("Command failed silently, fetching help.")
        help_result = await asyncio.to_thread(_capture_help, typer_app, argv + ["--help"])
        result.help_text = help_result.stdout

    logger.debug(
        f"Dispatch result: exit_code={result.exit_code} "
        f"stdout_len={len(result.stdout)} stderr_len={len(result.stderr)}"
    )
    return result


def dispatch_sync(
    typer_app: typer.Typer,
    args: Sequence[str],
    context_manager: ContextManager | None = None,
    confirm_callback: Callable[[str], bool] | None = None,
    progress_callback: Callable | None = None,
    summary_callback: Callable | None = None,
) -> DispatchResult:
    """Synchronous wrapper around :func:`dispatch_typer_command`.

    Use this in pure-Typer (batch / scripted) mode where no event loop is
    running.  Internally calls ``asyncio.run()`` to spin up a temporary loop.

    Parameters mirror :func:`dispatch_typer_command` except *output_queue*
    (not meaningful in synchronous mode).
    """
    return asyncio.run(
        dispatch_typer_command(
            typer_app,
            args,
            context_manager=context_manager,
            confirm_callback=confirm_callback,
            progress_callback=progress_callback,
            summary_callback=summary_callback,
        )
    )
