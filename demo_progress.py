#!/usr/bin/env python3
"""Demo script to show the progress bar working with async operations."""

import asyncio

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, ProgressBar, RichLog

from tui_typer.ui.logging import TextualProgressSink


class ProgressDemo(App):
    """Demo app showing progress bar usage."""

    CSS = """
    #log {
        height: 1fr;
        border: solid green;
    }
    #progress {
        height: 1;
        border: solid blue;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield RichLog(id="log", markup=True)
            yield ProgressBar(id="progress", total=100, show_eta=False)
        yield Footer()

    def on_mount(self) -> None:
        """Start demo when app mounts."""
        self.log_widget = self.query_one("#log", RichLog)
        self.progress_widget = self.query_one("#progress", ProgressBar)
        self.progress_sink = TextualProgressSink(self.progress_widget)

        # Start demo task
        self.run_worker(self.demo_progress())

    async def demo_progress(self) -> None:
        """Demonstrate progress bar updates."""
        self.log_widget.write("[cyan]Starting progress demo...[/cyan]")

        # Demo 1: Simple progress
        self.progress_sink.reset()
        self.progress_sink.set_total(50)
        self.log_widget.write("[green]Demo 1:[/green] Incrementing by 10")
        for i in range(5):
            await asyncio.sleep(0.5)
            self.progress_sink.update(advance=10.0)
            self.log_widget.write(f"  Progress: {(i + 1) * 10}/50")

        await asyncio.sleep(1)

        # Demo 2: Set specific progress values
        self.progress_sink.reset()
        self.progress_sink.set_total(100)
        self.log_widget.write("[green]Demo 2:[/green] Setting specific values")
        for value in [25, 50, 75, 100]:
            await asyncio.sleep(0.5)
            self.progress_sink.set_progress(value)
            self.log_widget.write(f"  Progress set to: {value}/100")

        await asyncio.sleep(1)

        # Demo 3: Simulated file processing
        self.progress_sink.reset()
        num_files = 10
        self.progress_sink.set_total(num_files)
        self.log_widget.write(f"[green]Demo 3:[/green] Processing {num_files} files")
        for i in range(num_files):
            await asyncio.sleep(0.3)
            self.progress_sink.update(advance=1.0)
            self.log_widget.write(f"  Processed file {i + 1}/{num_files}")

        self.progress_sink.complete()
        self.log_widget.write("[bold green]All demos complete![/bold green]")


if __name__ == "__main__":
    app = ProgressDemo()
    app.run()
