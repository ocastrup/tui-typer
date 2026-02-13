# Progress Bar Usage Guide

## Overview

The TUI-Typer app includes a progress bar widget and a `TextualProgressSink` class that enables async-safe progress updates during command execution.

## Components

### ProgressBar Widget

The progress bar is displayed in the UI between the logger log and the input box. It's styled with a blue border and occupies 1 line of height.

### TextualProgressSink Class

Located in `tui_typer/ui/logging.py`, this class provides a simple interface for updating progress:

```python
from tui_typer.ui.logging import TextualProgressSink

# The sink is automatically initialized in CLIApp.on_mount()
# Access it via: self.progress_sink
```

## API Methods

### `set_total(total: float)`
Set the total value for progress calculation.

```python
self.progress_sink.set_total(100.0)
```

### `update(advance: float = 1.0, description: str | None = None)`
Advance progress by a specified amount.

```python
# Advance by 1 (default)
self.progress_sink.update()

# Advance by 10
self.progress_sink.update(advance=10.0)
```

### `set_progress(value: float, description: str | None = None)`
Set progress to a specific value.

```python
self.progress_sink.set_progress(50.0)
```

### `reset()`
Reset progress to zero.

```python
self.progress_sink.reset()
```

### `complete()`
Mark progress as complete (sets to total).

```python
self.progress_sink.complete()
```

## Usage Example

### In a Command

```python
import asyncio

async def process_files(app, files):
    """Process multiple files with progress tracking."""
    # Set up progress
    app.progress_sink.reset()
    app.progress_sink.set_total(len(files))

    for i, file in enumerate(files):
        # Process the file
        await asyncio.sleep(0.1)  # Simulated work

        # Update progress
        app.progress_sink.update(advance=1.0)
        app.add_output(f"Processed: {file}")

    # Mark as complete
    app.progress_sink.complete()
```

### In the Main App

The `CLIApp` instance provides access to the progress sink:

```python
class CLIApp(App):
    def on_mount(self) -> None:
        # ...
        self.progress_widget = self.query_one("#progress-bar", ProgressBar)
        self.progress_sink = TextualProgressSink(self.progress_widget)
```

### Async Safety

The `TextualProgressSink` is designed to work safely with Textual's async event loop. All updates are applied directly to the widget, which Textual handles internally.

## Demo Script

Run the included demo to see the progress bar in action:

```bash
python demo_progress.py
```

The demo shows:
1. Incremental progress updates
2. Setting specific progress values
3. Simulated file processing with progress tracking

## Best Practices

1. **Always reset before use**: Call `reset()` at the start of a new operation
2. **Set appropriate totals**: Use `set_total()` to match your operation's scale
3. **Complete when done**: Call `complete()` to show 100% completion
4. **Avoid blocking**: Progress updates work best in async contexts
5. **Reset after completion**: Clear progress for the next operation

## Integration with Commands

Commands can access the progress sink through the app instance:

```python
async def my_command(app: CLIApp, args: list[str]) -> None:
    """Example command with progress tracking."""
    items = range(100)

    app.progress_sink.reset()
    app.progress_sink.set_total(len(items))

    for i in items:
        # Do work
        await asyncio.sleep(0.01)

        # Update progress
        app.progress_sink.update(advance=1.0)

    app.progress_sink.complete()
    app.add_output("[green]Operation complete![/green]")
```

## Technical Details

- **Widget Type**: `textual.widgets.ProgressBar`
- **Default Total**: 100.0
- **Show ETA**: Disabled by default
- **Thread Safety**: Designed for Textual's async model
- **State Tracking**: Maintains internal `_current` and `_total` values

## Troubleshooting

### Progress not updating
- Ensure you're calling updates from within async contexts
- Verify the progress sink is initialized (after `on_mount()`)

### Progress exceeds 100%
- The sink automatically clamps progress to the total value
- Check that `set_total()` matches your actual operation count

### Progress bar not visible
- Verify the CSS styling is correct
- Check that the widget is properly composed in the layout
