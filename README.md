# tui-typer

A framework that combines [Typer](https://typer.tiangolo.com/) command handling with a [Textual](https://textual.textualize.io/) terminal user interface.  Commands are defined once using native Typer idioms and executed either interactively through the TUI or directly as a batch CLI — without any code duplication.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Package Layout](#package-layout)
4. [Layer Details](#layer-details)
   - [Entry Points](#1-entry-points)
   - [CLI Layer — `tui_typer/cli.py`](#2-cli-layer)
   - [TUI Application — `tui_typer/app.py`](#3-tui-application)
   - [Command Dispatcher — `tui_typer/command_dispatcher/`](#4-command-dispatcher)
   - [Context Manager — `tui_typer/context/`](#5-context-manager)
   - [Typer Sub-commands — `tui_typer/typer_subcommands/`](#6-typer-sub-commands)
   - [UI Helpers — `tui_typer/ui/`](#7-ui-helpers)
5. [Key Design Patterns](#key-design-patterns)
   - [Dual-mode Operation](#dual-mode-operation)
   - [Streaming Output Pipeline](#streaming-output-pipeline)
   - [Progress Bar Pipeline](#progress-bar-pipeline)
   - [Cancellation](#cancellation)
   - [Submodule State Registry](#submodule-state-registry)
6. [Adding a New Sub-command Group](#adding-a-new-sub-command-group)
7. [Running the Application](#running-the-application)
8. [Testing](#testing)
9. [Tooling](#tooling)

---

## Overview

`tui-typer` solves a common problem: you want the richness of a TUI (real-time output, progress bars, keyboard navigation) but also need every command to work as a plain CLI for scripting and automation.

The key insight is that Typer is built on top of Click, and Click commands are just callable Python objects.  The **command dispatcher** locates the Click command object for any Typer sub-command and invokes it directly in a thread — bypassing the normal `sys.argv` parsing path — while hooking `sys.stdout` to stream output line-by-line back to the TUI via an `asyncio.Queue`.  Help text is the one exception: `--help` uses Typer's `CliRunner` so the native formatted help is preserved exactly.

---

## Architecture Diagram

```
╔═══════════════════════════════════════════════════════════════╗
║                        USER                                   ║
║   Interactive TUI           Batch / Script                    ║
║   tui-typer interactive     uv run tui_typer/cli.py <cmd>     ║
╚══════════════╤════════════════════════╤══════════════════════╝
               │                        │
               ▼                        ▼
╔══════════════════════╗   ╔════════════════════════════════╗
║   tui_typer/app.py   ║   ║    tui_typer/cli.py            ║
║   CLIApp (Textual)   ║   ║    Typer root application      ║
║                      ║   ║    _root_callback → ctx.obj    ║
║  Input widget        ║   ╚═══════════════╤════════════════╝
║  RichLog (output)    ║                   │
║  RichLog (logger)    ║     ┌─────────────┘
║  ProgressBar         ║     │  shared cli Typer app
╚══════════╤═══════════╝     │
           │ run_worker()    │
           ▼                 ▼
╔══════════════════════════════════════════════════════════════╗
║           tui_typer/command_dispatcher/base.py               ║
║           dispatch_typer_command()                           ║
║                                                              ║
║   --help? ──► CliRunner path (captures formatted help text)  ║
║                                                              ║
║   normal ──► Direct dispatch path                            ║
║              • Resolves Click command object from Typer app  ║
║              • asyncio.to_thread(_run)                       ║
║              • sys.stdout → _StreamingWriter → output_queue  ║
║              • ctx.obj injects: context_manager              ║
║                                progress_callback             ║
║                                cancel_event                  ║
╚══════════════════════╤══════════════════════════════════════╝
                       │  ctx.obj["progress_callback"](...)
                       │  ctx.obj["cancel_event"].is_set()
                       ▼
╔══════════════════════════════════════════════════════════════╗
║         tui_typer/typer_subcommands/                         ║
║         Typer sub-application modules                        ║
║                                                              ║
║   serialize.py                                               ║
║   ├── excel          — writes reports to Excel               ║
║   └── scan-files     — scans directory, streams filenames,   ║
║                        advances progress bar, polls cancel   ║
╚══════════════════════════════════════════════════════════════╝
                       │  ctx.obj["context_manager"]
                       ▼
╔══════════════════════════════════════════════════════════════╗
║         tui_typer/context/                                   ║
║         ContextManager singleton                             ║
║                                                              ║
║   • interactive flag (TUI vs batch)                          ║
║   • pluggable state registry (thread-safe)                   ║
║     "serialize" → SerializeState(last_file, files_written…)  ║
║   • AppConfig (INI file)                                     ║
║   • CliConsole (rich output)                                 ║
╚══════════════════════════════════════════════════════════════╝
```

---

## Package Layout

```
tui_typer/
│
├── __init__.py                   # __app_name__
├── cli.py                        # Root Typer app + ContextManager singleton factory
├── app.py                        # Textual CLIApp — TUI entry point
│
├── command_dispatcher/
│   ├── base.py                   # dispatch_typer_command(), dispatch_sync(), Command, DispatchResult
│   ├── loader.py                 # load_commands() — introspects Typer app into Command descriptors
│   └── history.py                # HistoryManager — persistent command history
│
├── context/
│   ├── context_manager.py        # ContextManager — shared state registry
│   └── config.py                 # AppConfig — INI-file configuration
│
├── typer_subcommands/
│   ├── __init__.py               # re-exports `serialize` Typer instance
│   └── serialize.py              # `serialize excel` and `serialize scan-files`
│
└── ui/
    ├── __init__.py               # Lazy package exports (avoids import-time Textual cost)
    ├── command_provider.py       # Textual command palette provider (Ctrl+P)
    ├── console.py                # CliConsole — rich console wrapper
    ├── editor.py                 # EditorLauncher — open files in $EDITOR / system default
    ├── file_picker.py            # FilePickerScreen — modal directory tree browser
    ├── fuzzy_search.py           # FuzzyFileSearchScreen — live fuzzy file search modal
    ├── logging.py                # TextualLogHandler, TextualProgressSink
    └── path_suggester.py         # PathSuggester — tab-completion for path tokens
```

---

## Layer Details

### 1. Entry Points

| Entry point | Purpose |
|---|---|
| `uv run tui-typer interactive` | Launch the Textual TUI |
| `uv run tui_typer/cli.py <cmd>` | Run any command in batch mode |
| `uv run python -m tui_typer.cli <cmd>` | Same as above |

`main.py` at the project root is the installed script entry point (`tui-typer = "main:main"`).

---

### 2. CLI Layer

**`tui_typer/cli.py`**

Defines the root `typer.Typer` application (`cli`) and the `ContextManager` singleton factory.

Key responsibilities:
- Declares the root `@cli.callback()` which runs before every command and injects the `ContextManager` into `ctx.obj["context_manager"]`
- Registers built-in top-level commands: `interactive`, `version`, `list-commands`, `history`
- Attaches sub-command groups via `cli.add_typer(serialize, name="serialize")`
- Exposes `get_context_manager()` — the single factory that both TUI and batch mode call to get the shared singleton

The `ContextManager` singleton is created lazily on first call and reused across all commands in a session, ensuring cross-command state accumulates correctly.

---

### 3. TUI Application

**`tui_typer/app.py`** — `CLIApp(App)`

The Textual application.  Layout (top to bottom):

```
┌─────────────── Header ───────────────────┐
│ ┌─────────────────────────────────────┐  │
│ │  output-log  (RichLog, 2fr)         │  │
│ │  command output, streaming          │  │
│ ├─────────────────────────────────────┤  │
│ │  logger-log  (RichLog, 1fr)         │  │
│ │  loguru sink                        │  │
│ ├─────────────────────────────────────┤  │
│ │  progress-bar  (ProgressBar, h=3)   │  │
│ └─────────────────────────────────────┘  │
│ ┌─────────────────────────────────────┐  │
│ │  input-box  (Input, docked bottom)  │  │
│ └─────────────────────────────────────┘  │
└─────────────── Footer ───────────────────┘
```

**Key bindings:**

| Key | Action |
|---|---|
| `Enter` | Submit command |
| `↑` / `↓` | Navigate command history |
| `Escape` | Cancel the running command |
| `Ctrl+C` | Quit the application |
| `Ctrl+P` | Open command palette |
| `Ctrl+B` | Open directory tree file picker |
| `Ctrl+S` | Open fuzzy file search |
| `Ctrl+G` | Open file in external editor |
| `Tab` / `→` | Accept path tab-completion |

**Command execution flow** inside `_execute_command()`:

1. Parse input; handle TUI built-ins (`exit`, `history`, `help`) directly
2. Validate command exists in the loaded command registry; suggest corrections via `difflib`
3. Create a fresh `threading.Event` for cancellation and store it on `self._active_cancel_event`
4. Reset the progress bar via `TextualProgressSink.reset()`
5. Create `output_queue` and `progress_queue` (`asyncio.Queue`)
6. Start three concurrent tasks via `asyncio.ensure_future`:
   - `dispatch_typer_command(...)` — runs the command
   - `_stream_output(output_queue)` — writes lines to the output log
   - `_stream_progress(progress_queue)` — drives the progress bar
7. `await dispatch_task`, send progress sentinel, `await gather(stream_task, progress_task)`
8. On clean completion: `progress_sink.complete()` snaps bar to 100 %

---

### 4. Command Dispatcher

**`tui_typer/command_dispatcher/base.py`**

The heart of the framework.  All command execution flows through `dispatch_typer_command()`.

#### `dispatch_typer_command()` — async public API

```python
async def dispatch_typer_command(
    typer_app: typer.Typer,
    args: Sequence[str],
    context_manager: ContextManager | None = None,
    confirm_callback: Callable | None = None,
    progress_callback: Callable | None = None,
    summary_callback: Callable | None = None,
    output_queue: asyncio.Queue | None = None,
    cancel_event: threading.Event | None = None,
) -> DispatchResult
```

- If `--help` is in `args`: delegates to `_capture_help()` (CliRunner path)
- Otherwise: delegates to `_dispatch_direct()` (direct dispatch path)
- If a command fails silently (non-zero exit, no output): fetches and returns help text

#### `dispatch_sync()` — sync wrapper for batch mode

Calls `asyncio.run(dispatch_typer_command(...))`.  Use this from scripts that have no running event loop.

#### Direct dispatch path — `_dispatch_direct()`

1. Resolves the leaf `click.BaseCommand` by walking the Click group tree
2. Replaces `sys.stdout` with a `_StreamingWriter` instance
3. Calls `cmd.main(args=remaining, obj=ctx_obj, standalone_mode=False)` inside `asyncio.to_thread`
4. `_StreamingWriter.write()` splits output at newlines and calls `loop.call_soon_threadsafe(output_queue.put_nowait, line)` — each complete line is immediately available to the TUI consumer
5. Restores `sys.stdout` and puts the `None` sentinel on `output_queue`

#### `ctx_obj` — the injection dict

Every command receives this dict as `ctx.obj`:

```python
{
    "context_manager":  ContextManager,   # shared singleton
    "confirm_callback": Callable | None,  # replaces blocking typer.confirm()
    "progress_callback": Callable | None, # (advance, total, description) → None
    "summary_callback": Callable | None,  # (text) → None
    "cancel_event":     threading.Event,  # poll to support cancellation
}
```

#### `Command` — metadata descriptor

A pure dataclass produced by `load_commands()`:

```python
@dataclass
class Command:
    name: str            # full path, e.g. "serialize scan-files"
    description: str     # one-line help
    click_command: click.BaseCommand
    is_group: bool       # True for command groups
    parent: str | None   # parent group name
    params: list         # Click parameters (options + arguments)
```

#### `loader.py` — `load_commands()`

Introspects the Typer application at startup by calling `typer.main.get_group(app)` to get the Click group, then walks all commands and subcommands, building a flat `dict[str, Command]`.  The `"interactive"` command is excluded (it is the TUI entry point itself).

#### `history.py` — `HistoryManager`

Persists command history as a plain text file (one command per line, configurable maximum, deduplicates consecutive identical entries).  Loaded on startup, saved on exit.

---

### 5. Context Manager

**`tui_typer/context/context_manager.py`** — `ContextManager`

The shared state hub, created once per session and injected into every command via `ctx.obj`.

#### State registry

Any submodule can register its own state dataclass:

```python
# At command time (safe to call multiple times)
cm: ContextManager = ctx.obj["context_manager"]
if not cm.has_state("my-module"):
    cm.register_state("my-module", MyModuleState())
state: MyModuleState = cm.get_state("my-module", MyModuleState)
```

The registry is a `dict[str, object]` protected by a `threading.Lock` so it is safe to access from commands running in `asyncio.to_thread`.

#### `interactive` flag

Set to `True` by `CLIApp.__init__()` in TUI mode; remains `False` in batch mode.  Commands can branch on this flag (e.g., `history` command returns early in batch mode).

#### `AppConfig`

INI-file configuration (`~/.tui_typer.ini` by default).  Provides `history_file`, `max_history`, `log_level` and display settings.  Created as part of the `ContextManager` and saved on application exit.

---

### 6. Typer Sub-commands

**`tui_typer/typer_subcommands/`**

Each file in this directory is a self-contained Typer sub-application.  The pattern:

1. **Define state** — a `@dataclass` for cross-command state in this module
2. **Register state** — call `_ensure_state_registered(ctx)` at the top of each command (idempotent)
3. **Write commands** — standard Typer `@app.command()` functions; receive `ctx: typer.Context` as the first argument to access `ctx.obj`
4. **Expose** — attach to the root CLI in `tui_typer/cli.py` with `cli.add_typer(serialize, name="serialize")`

#### `serialize.py` — example sub-command group

| Command | Description |
|---|---|
| `serialize excel` | Writes sample report data to an Excel workbook |
| `serialize scan-files <dir>` | Scans a directory, streams filenames, drives the progress bar |

`scan-files` options:

| Option | Description |
|---|---|
| `--pattern` / `-p` | Glob filter (default: `*`) |
| `--recursive` / `-r` | Scan subdirectories |
| `--wait` / `-w` | Sleep between files to expose progress bar during fast scans |

`scan-files` demonstrates the full contract a well-behaved long-running command should implement:
- Stream output via `typer.echo()` (reaches TUI in real time via `_StreamingWriter`)
- Report progress via `ctx.obj["progress_callback"](advance, total, description)`
- Honour cancellation by polling `ctx.obj["cancel_event"].is_set()` between items
- Update `SerializeState` so other commands can see the results

---

### 7. UI Helpers

**`tui_typer/ui/`**

The package uses lazy imports via `__getattr__` so that importing a lightweight module (e.g. `CliConsole` via `cli.py`) does not pull in Textual widget code at batch-mode startup.

#### Interactive tools — modal screens

All pickers are `ModalScreen` subclasses.  They overlay the running app, return a result via `self.dismiss(value)`, and the caller receives it in a callback passed to `push_screen`.

---

**`file_picker.py` — `FilePickerScreen`**

A full-screen directory tree browser backed by Textual's built-in `DirectoryTree` widget.

```python
self.push_screen(
    FilePickerScreen(start_dir=Path.cwd(), title="Pick a file"),
    lambda path: self.add_output(f"Selected: {path}"),
)
```

| Key | Action |
|---|---|
| `Enter` | Select highlighted file |
| `F5` | Refresh tree from disk |
| `Escape` | Cancel |

Parameters: `start_dir`, `title`, `show_files_only` (default `True` — directories are not selectable).

---

**`fuzzy_search.py` — `FuzzyFileSearchScreen`**

Live fuzzy-search across all files under a root directory.  File scanning runs in a `@work(thread=True)` background worker so the UI stays responsive.  Results are re-ranked on every keystroke using a three-tier scoring algorithm:

| Priority | Match type | Score |
|---|---|---|
| 1 | Exact substring in filename | 100 + position bonus |
| 2 | Glob pattern (`*.py`) | 80 |
| 3 | Subsequence (all chars in order) | 50 |

```python
self.push_screen(
    FuzzyFileSearchScreen(root=Path.cwd(), glob="**/*.py"),
    lambda path: self.add_output(f"Picked: {path}"),
)
```

| Key | Action |
|---|---|
| `↑` / `↓` | Move selection |
| `Enter` | Confirm selection |
| `Escape` | Cancel |

Parameters: `root`, `title`, `max_results` (default 200), `glob` (default `**/*`).

---

#### Tab completion

**`path_suggester.py` — `PathSuggester`**

A `Suggester` subclass that completes filesystem paths as the user types in the command input box.  Activates when the **last whitespace-separated token** looks like a path (starts with `./`, `../`, `~/`, `/`, a Windows drive letter, or contains a path separator).

Attached to the `Input` widget at compose time:

```python
yield Input(id="input-box", suggester=PathSuggester())
```

Textual renders the suggestion as ghost text; `Tab` or `→` accepts it.  Directories are completed with a trailing `/` so the user can keep typing deeper into the tree.

---

#### Editor integration

**`editor.py` — `EditorLauncher`**

Opens files in an external editor, choosing the right strategy based on editor type:

| Editor type | Strategy |
|---|---|
| Terminal (`vim`, `nvim`, `nano`, …) | TUI **suspended** via `app.suspend()`, editor runs blocking, TUI resumes on exit |
| GUI (`code`, `notepad`, …) | Process launched **detached**, TUI keeps running immediately |

Editor resolution order: `$EDITOR` → `$VISUAL` → platform default (`notepad` on Windows, `vi` on POSIX).

```python
launcher = EditorLauncher()                      # auto-detect
launcher = EditorLauncher(editor="code")         # explicit override

# From an async worker (TUI mode):
await launcher.open_async(app, path)

# From batch/sync code:
launcher.open_blocking(path)
```

---

#### CLIApp integration — key bindings

All four tools are wired into `CLIApp` with keyboard shortcuts that appear in the Textual Footer:

| Key | Action |
|---|---|
| `Ctrl+B` | Open directory tree file picker; selected path appended to input |
| `Ctrl+S` | Open fuzzy file search; selected path appended to input |
| `Ctrl+G` | Open last path token in input (or picker first) in external editor |
| `Tab` / `→` | Accept path tab-completion suggestion |

---

#### Logging and progress

| Module | Class | Purpose |
|---|---|---|
| `logging.py` | `TextualLogHandler` | Loguru sink that writes coloured log records to the `logger-log` RichLog widget |
| `logging.py` | `TextualProgressSink` | Adapter between `(advance, total)` tuples from the progress queue and `ProgressBar.update()` calls |
| `command_provider.py` | `CommandProvider` | Textual `Provider` subclass — supplies the command palette (`Ctrl+P`) with all registered commands |
| `console.py` | `CliConsole` | Thin wrapper around Rich's `Console` for non-TUI output |

---

## Key Design Patterns

### Dual-mode Operation

The same Typer commands run identically in both modes.  The `ContextManager.interactive` flag lets commands adapt their behaviour where needed.

```
Interactive (TUI)                   Batch
─────────────────────────────────   ──────────────────────────────
CLIApp.on_input_submitted()         cli() from __main__
  └─ _execute_command()               └─ _root_callback() injects ContextManager
       └─ dispatch_typer_command()        └─ command function runs directly
            └─ asyncio.to_thread()
```

### Streaming Output Pipeline

Output from a running command reaches the TUI incrementally, not after it finishes:

```
Command thread (asyncio.to_thread)
  typer.echo("some text\n")
     └─ sys.stdout = _StreamingWriter
          └─ write("some text\n")
               └─ loop.call_soon_threadsafe(output_queue.put_nowait, "some text")
                                                    │
                    ┌───────────────────────────────┘
                    ▼  (event loop, Textual context)
            _stream_output() coroutine
              └─ line = await output_queue.get()
                   └─ self.add_output(line)  → RichLog.write()
```

### Progress Bar Pipeline

Progress updates follow the same queue pattern as text output, ensuring widget mutations happen on the event loop:

```
Command thread
  ctx.obj["progress_callback"](advance=1, total=None)
     └─ _progress_cb in _execute_command
          └─ loop.call_soon_threadsafe(progress_queue.put_nowait, (1, None))
                                              │
               ┌──────────────────────────────┘
               ▼  (event loop, Textual context)
       _stream_progress() coroutine
         └─ (advance, total) = await progress_queue.get()
              └─ progress_sink.set_total(total)   # if total is not None
              └─ progress_sink.update(advance)    → ProgressBar.update()
```

> **Why not `call_from_thread`?**  Textual's `call_from_thread()` only works from threads that Textual itself spawned via `run_worker()`.  `asyncio.to_thread()` uses a plain `ThreadPoolExecutor` thread, which Textual has no knowledge of.  The queue pattern is the correct solution in both cases.

### Cancellation

`Escape` triggers `action_cancel_command()`, which sets `self._active_cancel_event`.  That same `threading.Event` was injected into the running command via `ctx.obj["cancel_event"]`.  Commands poll it between work items:

```python
# Inside a long-running command
for item in big_list:
    if cancel_event.is_set():
        typer.echo("Cancelled.")
        break
    process(item)
```

The event is created in `_execute_command` before dispatch and cleared in the `finally` block after the command finishes, regardless of outcome.

### Submodule State Registry

Cross-command state is shared through the `ContextManager` without coupling modules together:

```python
# serialize.py — first call registers, subsequent calls are no-ops
def _ensure_state_registered(ctx: typer.Context) -> SerializeState:
    cm: ContextManager = ctx.obj["context_manager"]
    if not cm.has_state("serialize"):
        cm.register_state("serialize", SerializeState())
    return cm.get_state("serialize", SerializeState)
```

State persists across multiple commands in the same session (TUI or scripted), so `excel` can see how many files `scan-files` found, for example.

---

## Adding a New Sub-command Group

1. **Create** `tui_typer/typer_subcommands/mymodule.py`:

```python
from dataclasses import dataclass
import typer

__app_name__ = "mymodule"

@dataclass
class MyState:
    calls: int = 0

def _ensure_state(ctx: typer.Context) -> MyState:
    from tui_typer.context.context_manager import ContextManager
    cm: ContextManager = ctx.obj["context_manager"]
    if not cm.has_state(__app_name__):
        cm.register_state(__app_name__, MyState())
    return cm.get_state(__app_name__, MyState)

mymodule = typer.Typer(help="My new command group.")

@mymodule.command()
def hello(ctx: typer.Context, name: str = typer.Argument("World")) -> None:
    """Say hello."""
    state = _ensure_state(ctx)
    state.calls += 1
    typer.echo(f"Hello, {name}! (call #{state.calls})")
```

2. **Register** in `tui_typer/typer_subcommands/__init__.py`:

```python
from tui_typer.typer_subcommands.mymodule import mymodule
```

3. **Attach** in `tui_typer/cli.py`:

```python
cli.add_typer(typer_subcommands.mymodule, name="mymodule", help="My new command group.")
```

The new commands appear automatically in the command palette (`Ctrl+P`), the `list-commands` output, and are available in both TUI and batch mode.

---

## Running the Application

```bash
# Interactive TUI
uv run tui-typer interactive

# Batch — list all commands
uv run python -m tui_typer.cli list-commands

# Batch — scan files with progress simulation
uv run python -m tui_typer.cli serialize scan-files . --pattern *.py --recursive --wait 0.2

# Batch — help for any command
uv run python -m tui_typer.cli serialize scan-files --help
```

---

## Testing

```bash
# Full test suite
uv run python -m pytest

# Single test file
uv run python -m pytest tests/test_scan_files.py -v
```

Test files:

| File | Coverage |
|---|---|
| `test_scan_files.py` | Streaming output, progress callbacks, `--wait`, `--pattern`, `--recursive`, cancellation, batch sync mode, help text |
| `test_async_fix.py` | Async dispatch edge cases |
| `test_async_invoke.py` | `dispatch_typer_command` return values |
| `test_detailed_help.py` | `--help` formatting |
| `test_dispatch_help.py` | Help dispatch path |
| `test_exit.py` | Exit code handling |
| `test_help_flag.py` | `--help` flag routing |
| `test_history.py` | `HistoryManager` persistence |

The `conftest.py` fixtures `typer_cli`, `runner`, and `run_dispatch` are shared across all test modules.

---

## Tooling

| Tool | Purpose | Command |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | Package manager & virtual environment | `uv sync --extra dev` |
| [Ruff](https://docs.astral.sh/ruff/) | Linter + formatter | `uv run ruff check --fix .` |
| [pre-commit](https://pre-commit.com/) | Git hooks (ruff, whitespace, YAML) | `pre-commit run ruff --all-files` |
| [pytest](https://pytest.org/) | Test runner | `uv run python -m pytest` |
| [loguru](https://loguru.readthedocs.io/) | Structured logging | Configured in `on_mount()` |

Configuration lives in `pyproject.toml` (project metadata, ruff rules, pytest `testpaths`).
