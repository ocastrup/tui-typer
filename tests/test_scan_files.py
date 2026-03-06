"""End-to-end async test for the ``serialize scan-files`` command.

What this test validates
------------------------
1. **Streaming output** — filenames are emitted one-by-one through the
   async ``output_queue`` as the command runs, not all at once after it
   finishes.
2. **Progress reporting** — the ``progress_callback`` is called
   * once with ``advance=0, total=<n>`` to initialise the progress bar, and
   * once per file with ``advance=1`` to advance it.
3. **State registry** — after the command completes the ``SerializeState``
   held in the ``ContextManager`` is updated with the scanned directory and
   file count.
4. **Cancellation** — a separate test confirms that setting
   ``cancel_event`` mid-run stops the command cleanly.
5. **Batch (sync) mode** — :func:`dispatch_sync` produces the same result
   without an event loop.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import threading

import pytest

from tui_typer.cli import cli
from tui_typer.command_dispatcher.base import dispatch_sync, dispatch_typer_command
from tui_typer.context.config import AppConfig
from tui_typer.context.context_manager import ContextManager
from tui_typer.typer_subcommands.serialize import SerializeState
from tui_typer.ui.console import CliConsole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_context() -> ContextManager:
    """Return a brand-new ContextManager so tests don't share singleton state."""
    return ContextManager(console=CliConsole(), config=AppConfig())


async def _drain_queue(queue: asyncio.Queue) -> list[str]:
    """Drain all lines from *queue* until the ``None`` sentinel is received."""
    lines: list[str] = []
    while True:
        item = await queue.get()
        if item is None:
            break
        lines.append(item)
    return lines


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def python_src(tmp_path: Path) -> Path:
    """Create a small tree of fake Python files for scanning.

    Layout::

        tmp_path/
            a.py          (10 bytes)
            b.py          (20 bytes)
            sub/
                c.py      (30 bytes)
                d.txt     (5  bytes)
    """
    (tmp_path / "a.py").write_text("# file a\n")
    (tmp_path / "b.py").write_text("# file b\n# second line\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.py").write_text("# file c\n# second line\n# third line\n")
    (sub / "d.txt").write_text("text")
    return tmp_path


# ---------------------------------------------------------------------------
# Core streaming + progress test
# ---------------------------------------------------------------------------


def test_scan_files_streams_output_and_progress(python_src: Path) -> None:
    """Filenames arrive via output_queue AND progress_callback fires per file."""

    progress_calls: list[tuple] = []

    def _progress_cb(advance, total=None, description=None):
        progress_calls.append((advance, total, description))

    async def _run():  # returns (DispatchResult, list[str], ContextManager)
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        ctx_mgr = _fresh_context()

        dispatch_task = asyncio.ensure_future(
            dispatch_typer_command(
                cli,
                ["serialize", "scan-files", str(python_src), "--pattern", "*.py"],
                context_manager=ctx_mgr,
                progress_callback=_progress_cb,
                output_queue=queue,
            )
        )

        # Collect streamed lines concurrently with dispatch
        drain_task = asyncio.ensure_future(_drain_queue(queue))

        result = await dispatch_task
        lines = await drain_task
        return result, lines, ctx_mgr

    result, lines, ctx_mgr = asyncio.run(_run())

    # --- Exit code ---
    assert result.exit_code == 0, f"Command failed: stderr={result.stderr!r}"

    # --- Streaming output ---
    # Lines include the header ("Scanning…") and one line per file plus footer
    assert any("Scanning" in ln for ln in lines), "Expected header line in output"
    # Non-recursive: only a.py and b.py in the root (match listing lines, not header)
    py_lines = [
        ln
        for ln in lines
        if ".py" in ln and ln.strip().startswith("[") and "/sub/" not in ln and "\\sub\\" not in ln
    ]
    assert len(py_lines) == 2, f"Expected 2 root .py file lines, got: {py_lines}"

    # --- Progress callback ---
    # First call: advance=0, total=2 (initialise bar)
    assert progress_calls[0] == (
        0,
        2,
        python_src.name,
    ), f"Expected initialisation call (0, 2, ...), got {progress_calls[0]}"
    # Subsequent calls: advance=1 per file
    advance_calls = [c for c in progress_calls if c[0] == 1]
    assert len(advance_calls) == 2, f"Expected 2 advance calls, got {advance_calls}"

    # --- State registry ---
    state: SerializeState = ctx_mgr.get_state("serialize", SerializeState)
    assert state.last_scan_count == 2
    assert state.last_scan_dir == str(python_src)


# ---------------------------------------------------------------------------
# Recursive scan test
# ---------------------------------------------------------------------------


def test_scan_files_recursive_finds_all_py(python_src: Path) -> None:
    """With --recursive, sub/c.py is also found."""

    progress_calls: list[tuple] = []

    def _progress_cb(advance, total=None, description=None):
        progress_calls.append((advance, total, description))

    async def _run():
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        ctx_mgr = _fresh_context()

        dispatch_task = asyncio.ensure_future(
            dispatch_typer_command(
                cli,
                ["serialize", "scan-files", str(python_src), "--pattern", "*.py", "--recursive"],
                context_manager=ctx_mgr,
                progress_callback=_progress_cb,
                output_queue=queue,
            )
        )
        drain_task = asyncio.ensure_future(_drain_queue(queue))
        result = await dispatch_task
        lines = await drain_task
        return result, lines, ctx_mgr

    result, lines, ctx_mgr = asyncio.run(_run())

    assert result.exit_code == 0
    # 3 .py files: a.py, b.py, sub/c.py
    init_call = next((c for c in progress_calls if c[0] == 0), None)
    assert init_call is not None and init_call[1] == 3, f"Expected total=3, got {init_call}"
    advance_calls = [c for c in progress_calls if c[0] == 1]
    assert len(advance_calls) == 3

    state: SerializeState = ctx_mgr.get_state("serialize", SerializeState)
    assert state.last_scan_count == 3


# ---------------------------------------------------------------------------
# Pattern filtering test
# ---------------------------------------------------------------------------


def test_scan_files_pattern_filters_correctly(python_src: Path) -> None:
    """Only .txt files are returned when pattern='*.txt'."""

    async def _run():
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        ctx_mgr = _fresh_context()
        dispatch_task = asyncio.ensure_future(
            dispatch_typer_command(
                cli,
                ["serialize", "scan-files", str(python_src), "--pattern", "*.txt", "--recursive"],
                context_manager=ctx_mgr,
                output_queue=queue,
            )
        )
        drain_task = asyncio.ensure_future(_drain_queue(queue))
        result = await dispatch_task
        lines = await drain_task
        return result, lines, ctx_mgr

    result, lines, ctx_mgr = asyncio.run(_run())

    assert result.exit_code == 0
    state: SerializeState = ctx_mgr.get_state("serialize", SerializeState)
    assert state.last_scan_count == 1


# ---------------------------------------------------------------------------
# Empty directory test
# ---------------------------------------------------------------------------


def test_scan_files_empty_directory(tmp_path: Path) -> None:
    """Scanning an empty directory exits cleanly with no progress calls."""

    progress_calls: list[tuple] = []

    async def _run():
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        ctx_mgr = _fresh_context()
        dispatch_task = asyncio.ensure_future(
            dispatch_typer_command(
                cli,
                ["serialize", "scan-files", str(tmp_path)],
                context_manager=ctx_mgr,
                progress_callback=lambda *a, **kw: progress_calls.append((a, kw)),
                output_queue=queue,
            )
        )
        drain_task = asyncio.ensure_future(_drain_queue(queue))
        result = await dispatch_task
        lines = await drain_task
        return result, lines

    result, lines = asyncio.run(_run())

    assert result.exit_code == 0
    assert any("No files matched" in ln for ln in lines)
    # No progress calls (total=0, nothing to advance)
    assert progress_calls == []


# ---------------------------------------------------------------------------
# Cancellation test
# ---------------------------------------------------------------------------


def test_scan_files_cancellation_stops_early(python_src: Path) -> None:
    """Setting cancel_event mid-run stops the scan before all files are done."""

    cancel_event = threading.Event()
    processed: list[str] = []

    def _progress_cb(advance, total=None, description=None):
        if advance == 1:
            processed.append(description or "")
            # Cancel after processing the first file
            if len(processed) == 1:
                cancel_event.set()

    async def _run():
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        ctx_mgr = _fresh_context()

        # We have to pass cancel_event via ctx_obj manually since
        # dispatch_typer_command creates its own — use dispatch directly via
        # the internal helper by passing the event through a wrapper.
        # Simplest: monkey-patch the queue sentinel after one item.
        from tui_typer.command_dispatcher import base as disp_base

        # Temporarily override _build_ctx_obj to inject our cancel_event
        original = disp_base._build_ctx_obj

        def _patched(**kwargs):
            # Build normally, then override cancel_event with ours
            obj = original(**kwargs)
            obj["cancel_event"] = cancel_event
            return obj

        disp_base._build_ctx_obj = _patched
        try:
            dispatch_task = asyncio.ensure_future(
                dispatch_typer_command(
                    cli,
                    [
                        "serialize",
                        "scan-files",
                        str(python_src),
                        "--pattern",
                        "*.py",
                        "--recursive",
                    ],
                    context_manager=ctx_mgr,
                    progress_callback=_progress_cb,
                    output_queue=queue,
                )
            )
            drain_task = asyncio.ensure_future(_drain_queue(queue))
            result = await dispatch_task
            lines = await drain_task
        finally:
            disp_base._build_ctx_obj = original

        return result, lines

    result, lines = asyncio.run(_run())

    # Command exits cleanly (cancel produces exit_code=0 via the for/else break)
    assert result.exit_code == 0
    # Only 1 file was processed before cancellation
    assert len(processed) == 1
    assert any("Cancelled" in ln for ln in lines)


# ---------------------------------------------------------------------------
# Batch (sync) mode test
# ---------------------------------------------------------------------------


def test_scan_files_batch_sync_mode(python_src: Path) -> None:
    """dispatch_sync works without an event loop (pure Typer batch mode)."""

    ctx_mgr = _fresh_context()
    result = dispatch_sync(
        cli,
        ["serialize", "scan-files", str(python_src), "--pattern", "*.py"],
        context_manager=ctx_mgr,
    )

    assert result.exit_code == 0
    # In sync mode output goes to stdout buffer, not a queue
    assert "Scanning" in result.stdout
    assert "a.py" in result.stdout or "b.py" in result.stdout

    state: SerializeState = ctx_mgr.get_state("serialize", SerializeState)
    assert state.last_scan_count == 2


# ---------------------------------------------------------------------------
# Help flag test
# ---------------------------------------------------------------------------


def test_scan_files_help(runner) -> None:
    """--help shows usage with all options documented."""
    result = runner.invoke(cli, ["serialize", "scan-files", "--help"], catch_exceptions=True)
    assert result.exit_code == 0
    assert "Usage:" in result.stdout
    assert "--pattern" in result.stdout
    assert "--recursive" in result.stdout
    assert "--wait" in result.stdout


# ---------------------------------------------------------------------------
# Wait / simulated processing delay test
# ---------------------------------------------------------------------------


def test_scan_files_wait_delays_between_files(python_src: Path) -> None:
    """--wait inserts a sleep between files; total elapsed time reflects the delay."""
    import time

    # Two .py files in root, 0.1 s delay each → expect at least 0.2 s total
    delay = 0.1
    start = time.monotonic()

    ctx_mgr = _fresh_context()
    result = dispatch_sync(
        cli,
        ["serialize", "scan-files", str(python_src), "--pattern", "*.py", "--wait", str(delay)],
        context_manager=ctx_mgr,
    )

    elapsed = time.monotonic() - start

    assert result.exit_code == 0
    # Elapsed must be at least 2 * delay (one sleep per file)
    assert elapsed >= 2 * delay, f"Expected at least {2 * delay:.2f}s elapsed, got {elapsed:.3f}s"
    # Output should mention the delay
    assert "simulating" in result.stdout

    state: SerializeState = ctx_mgr.get_state("serialize", SerializeState)
    assert state.last_scan_count == 2


def test_scan_files_wait_zero_is_default_behaviour(python_src: Path) -> None:
    """Omitting --wait (default 0.0) behaves identically to the no-wait baseline."""
    ctx_mgr = _fresh_context()
    result = dispatch_sync(
        cli,
        ["serialize", "scan-files", str(python_src), "--pattern", "*.py"],
        context_manager=ctx_mgr,
    )
    assert result.exit_code == 0
    # No delay message in output
    assert "simulating" not in result.stdout
