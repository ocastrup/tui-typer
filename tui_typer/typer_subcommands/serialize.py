"""Serialize sub-commands.

Demonstrates the submodule state registry pattern:

1. Define a :class:`SerializeState` dataclass for this module's cross-command
   state.
2. Register it with the shared :class:`ContextManager` via
   :func:`_ensure_state_registered`.
3. Retrieve it inside any command via ``ctx.obj["context_manager"].get_state()``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import threading
import time
from typing import Any

from loguru import logger
import pandas as pd
import typer

__app_name__ = "serialize"

# ---------------------------------------------------------------------------
# Submodule state
# ---------------------------------------------------------------------------


@dataclass
class SerializeState:
    """Cross-command state for the serialize subcommand group.

    Attributes
    ----------
    last_file:
        Path of the most recently written output file, or ``None``.
    files_written:
        Cumulative count of files written in this session.
    records_written:
        Cumulative count of data rows written in this session.
    last_scan_dir:
        Directory path used in the most recent ``scan-files`` run.
    last_scan_count:
        Number of files found in the most recent ``scan-files`` run.
    """

    last_file: str | None = None
    files_written: int = 0
    records_written: int = 0
    last_scan_dir: str | None = None
    last_scan_count: int = 0


def _ensure_state_registered(ctx: typer.Context) -> SerializeState:
    """Register :class:`SerializeState` with the ContextManager if not already present.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    from tui_typer.context.context_manager import ContextManager

    cm: ContextManager = ctx.obj["context_manager"]
    if not cm.has_state(__app_name__):
        cm.register_state(__app_name__, SerializeState())
    return cm.get_state(__app_name__, SerializeState)


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_REPORTS: list[dict[str, Any]] = [
    {
        "title": "Sample Report",
        "columns": ["Name", "Age", "City"],
        "rows": [
            {"Name": "Alice", "Age": 30, "City": "New York"},
            {"Name": "Bob", "Age": 25, "City": "Los Angeles"},
            {"Name": "Charlie", "Age": 35, "City": "Chicago"},
        ],
    }
]

# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------


class Serializer:
    """General-purpose serializer for tabular report data."""

    @staticmethod
    def serialize_to_excel(reports: list[dict[str, Any]], file_name: str) -> int:
        """Write *reports* to an Excel workbook. Returns total rows written."""
        total_rows = 0
        with pd.ExcelWriter(file_name) as writer:
            for report in reports:
                df = pd.DataFrame(report["rows"], columns=report["columns"])
                sheet_name = report.get("title", "Sheet1")
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                total_rows += len(df)
        return total_rows


# ---------------------------------------------------------------------------
# Typer sub-application
# ---------------------------------------------------------------------------

serialize = typer.Typer(help="Serialisation commands for report data.")


@serialize.command()
def excel(
    ctx: typer.Context,
    file_name: str = typer.Option(
        "report.xlsx",
        "--file-name",
        "-f",
        help="Output Excel file path.",
    ),
) -> None:
    """Serialize the sample reports to an Excel workbook."""
    state = _ensure_state_registered(ctx)

    rows_written = Serializer.serialize_to_excel(SAMPLE_REPORTS, file_name)
    logger.info(f"Serialized {rows_written} rows to '{file_name}'.")
    typer.echo(f"Written {rows_written} rows → {file_name}")

    state.last_file = file_name
    state.files_written += 1
    state.records_written += rows_written


@serialize.command(name="scan-files")
def scan_files(
    ctx: typer.Context,
    directory: str = typer.Argument(
        ".",
        help="Directory to scan. Defaults to the current working directory.",
    ),
    pattern: str = typer.Option(
        "*",
        "--pattern",
        "-p",
        help="Glob pattern to filter files (e.g. '*.py', '*.txt'). Default: all files.",
    ),
    recursive: bool = typer.Option(
        False,
        "--recursive",
        "-r",
        help="Scan sub-directories recursively.",
    ),
    wait: float = typer.Option(
        0.0,
        "--wait",
        "-w",
        help=(
            "Seconds to sleep after processing each file, simulating heavy work. "
            "Use this to observe the progress bar updating in real time. "
            "Example: --wait 0.5"
        ),
        min=0.0,
    ),
) -> None:
    """Scan a directory and list every matching file.

    Each filename is written to stdout so the TUI streaming output queue
    receives it in real time.  Progress is reported through the
    ``progress_callback`` injected via ``ctx.obj`` so the TUI progress bar
    advances as each file is processed.

    Use ``--wait`` to insert a delay between files and make the progress bar
    visible during fast scans::

        serialize scan-files . --pattern *.py --recursive --wait 0.5

    The command also respects ``ctx.obj['cancel_event']`` (a
    :class:`threading.Event`) so a TUI worker cancellation is honoured
    between files.

    Batch mode::

        python -m tui_typer.cli serialize scan-files src --pattern *.py -r --wait 0.2
    """
    state = _ensure_state_registered(ctx)

    # Retrieve callbacks injected by the dispatcher (may be None in batch mode)
    progress_cb: Callable | None = (ctx.obj or {}).get("progress_callback")
    cancel_event: threading.Event = (ctx.obj or {}).get("cancel_event", threading.Event())

    target = Path(directory).resolve()
    if not target.is_dir():
        typer.echo(f"Error: '{directory}' is not a directory.", err=True)
        raise typer.Exit(code=1)

    # Collect all matching paths first so we know the total for the progress bar
    glob_fn = target.rglob if recursive else target.glob
    all_files = [p for p in glob_fn(pattern) if p.is_file()]
    total = len(all_files)

    wait_msg = f"  (simulating {wait:.2f}s processing delay per file)" if wait > 0 else ""
    typer.echo(f"Scanning '{target}' for '{pattern}' — {total} file(s) found.{wait_msg}")
    logger.info(f"scan-files: {total} files in '{target}' matching '{pattern}'")

    if total == 0:
        typer.echo("No files matched.")
        return

    # Signal the total to the progress bar (advance=0 → just set total)
    if progress_cb is not None:
        progress_cb(0, total, target.name)

    for idx, file_path in enumerate(all_files, start=1):
        # Honour cancellation between files
        if cancel_event.is_set():
            typer.echo(f"Cancelled after {idx - 1} file(s).")
            logger.warning("scan-files cancelled by user.")
            break

        # Stream the filename to the TUI output queue via stdout
        rel = file_path.relative_to(target)
        size_kb = file_path.stat().st_size / 1024
        typer.echo(f"  [{idx:>4}/{total}]  {rel}  ({size_kb:.1f} KB)")

        # Simulate heavy processing so the progress bar is clearly visible
        if wait > 0:
            time.sleep(wait)

        # Advance the progress bar by 1 step
        if progress_cb is not None:
            progress_cb(1, None, str(rel))

    else:
        # Loop completed without break (no cancellation)
        typer.echo(f"\nDone — {total} file(s) listed.")
        logger.info(f"scan-files complete: {total} files listed from '{target}'")

        # Update session state
        state.last_scan_dir = str(target)
        state.last_scan_count = total


# ---------------------------------------------------------------------------
# CLI plugin helper
# ---------------------------------------------------------------------------


def cli_plugin() -> tuple[str, Any]:
    """Return ``(name, click_command)`` for plugin registration."""
    return __app_name__, typer.main.get_command(serialize)
