# Async Command Execution Fix

## Problem

When executing commands through the Textual command palette (e.g., `serialize excel`), the following runtime warning was displayed:

```
RuntimeWarning: coroutine 'CommandProvider._run_command' was never awaited
  strip = render_line(
RuntimeWarning: Enable tracemalloc to get the object allocation traceback
```

## Root Cause

The issue was in `tui_typer/ui/command_provider.py`. The `Hit` objects in the Textual command palette require a **synchronous callable** as the callback parameter. However, the code was passing:

```python
# BEFORE (BROKEN):
lambda parts=cmd_name: self._run_command([parts])
```

This lambda returns a **coroutine** when called, but never awaits it. The `Hit` callback system expects a synchronous function, not a coroutine.

## Solution

Created a new method `_create_command_callback()` that returns a proper synchronous wrapper:

```python
def _create_command_callback(self, cmd_parts: List[str]) -> Callable[[], None]:
    """Create a synchronous callback that runs the async command."""
    def callback() -> None:
        self.app.run_worker(self._run_command(cmd_parts))
    return callback
```

### How It Works

1. **Synchronous Wrapper**: The `callback()` function is synchronous (no `async`)
2. **Schedules Async Work**: Inside, it calls `self.app.run_worker()` with the coroutine
3. **Proper Execution**: `run_worker()` properly schedules the async `_run_command()` coroutine

### Updated Hit Callbacks

```python
# AFTER (FIXED):
Hit(
    score,
    matcher.highlight(cmd_name),
    self._create_command_callback([cmd_name]),  # ✅ Synchronous callback
    help=cmd.help or cmd.short_help or "",
)
```

## Changes Made

### File: `tui_typer/ui/command_provider.py`

1. **Removed** unused `functools.partial` import
2. **Added** `Callable` to typing imports
3. **Added** `_create_command_callback()` method
4. **Updated** all `Hit` objects to use `_create_command_callback()`

### Before vs After

**Before:**
```python
from functools import partial

# In search():
yield Hit(
    score,
    matcher.highlight(cmd_name),
    partial(self.app.run_worker, self._run_command([cmd_name])),  # ❌ Wrong
    help=cmd.help or cmd.short_help or "",
)
```

**After:**
```python
from typing import Callable

def _create_command_callback(self, cmd_parts: List[str]) -> Callable[[], None]:
    def callback() -> None:
        self.app.run_worker(self._run_command(cmd_parts))
    return callback

# In search():
yield Hit(
    score,
    matcher.highlight(cmd_name),
    self._create_command_callback([cmd_name]),  # ✅ Correct
    help=cmd.help or cmd.short_help or "",
)
```

## Testing

Run the test to verify the fix:

```bash
python test_async_fix.py
```

Expected output:
```
✅ All async tests passed!

Fix Summary:
  • CommandProvider now has _create_command_callback() method
  • This method wraps async commands in synchronous callbacks
  • The callback properly schedules async work with run_worker()
  • RuntimeWarning 'coroutine was never awaited' is now fixed
```

## Verification

To verify the fix in the TUI:

1. Start the application:
   ```bash
   python cli.py interactive
   ```

2. Open command palette (usually Ctrl+P or Ctrl+\\)

3. Type and execute: `serialize excel`

4. **No RuntimeWarning should appear**

5. The command should execute successfully without errors

## Why This Matters

### Textual's Command System

Textual's `Hit` callback expects a **synchronous callable**:
- When user selects a command from the palette
- The callback is called **synchronously**
- It should perform quick setup, then schedule async work if needed

### Proper Async Scheduling

`app.run_worker()` is the correct way to schedule async work in Textual:
- Takes a coroutine as input
- Schedules it to run in the event loop
- Manages the coroutine lifecycle properly
- Prevents "was never awaited" warnings

## Additional Benefits

This fix also:
- ✅ Prevents potential memory leaks from unawaited coroutines
- ✅ Ensures proper error handling in async command execution
- ✅ Follows Textual's best practices for command callbacks
- ✅ Makes the code more maintainable and clear

## Related Files

- `tui_typer/ui/command_provider.py` - Fixed file
- `tui_typer/commands/base.py` - Async command dispatcher
- `test_async_fix.py` - Test verification

## Summary

The async warning is now **completely resolved**. Commands executed through the command palette will run properly without any runtime warnings about unawaited coroutines.
