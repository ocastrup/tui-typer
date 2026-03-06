"""Directory tree browser and file picker.

Presents a :class:`~textual.widgets.DirectoryTree` inside a modal overlay.
The caller receives a :class:`FilePickerResult` via
:meth:`~textual.screen.Screen.dismiss`.

Usage
-----
::

    def _on_pick(result: FilePickerResult | None) -> None:
        if result is None:
            return
        if result.action == "edit":
            self.run_worker(self._launch_editor(result.path), name="editor")
        else:
            self._insert_path_into_input(result.path)

    self.push_screen(FilePickerScreen(start_dir=Path.cwd()), _on_pick)

Key bindings inside the modal
------------------------------
* ``Enter`` / double-click  — select the highlighted file and close
* ``Ctrl+G``                — open the highlighted file directly in the editor
* ``Escape``                — cancel (dismiss with ``None``)
* ``F5``                    — refresh the tree (re-scans the directory)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Footer, Label

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class FilePickerResult:
    """The value dismissed by :class:`FilePickerScreen`.

    Attributes
    ----------
    path:
        The selected filesystem path.
    action:
        ``"select"`` — insert the path into the command input.
        ``"edit"``   — open the path in the external editor.
    """

    path: Path
    action: str = "select"  # "select" | "edit"


# ---------------------------------------------------------------------------
# Modal screen
# ---------------------------------------------------------------------------


class FilePickerScreen(ModalScreen[FilePickerResult | None]):
    """Modal overlay for browsing a directory tree and selecting a file.

    Parameters
    ----------
    start_dir:
        The root directory shown in the tree.  Defaults to the current
        working directory.
    title:
        Optional heading displayed above the tree.
    show_files_only:
        When ``True`` (default) the ``Enter`` key only accepts plain files,
        not directories.  Set to ``False`` to allow directory selection.
    """

    DEFAULT_CSS = """
    FilePickerScreen {
        align: center middle;
    }
    #fp-dialog {
        width: 80%;
        height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 0 1;
    }
    #fp-title {
        text-style: bold;
        color: $primary;
        padding: 1 0 0 1;
        height: 3;
    }
    DirectoryTree {
        height: 1fr;
        border: solid $accent;
    }
    #fp-buttons {
        height: 3;
        align: right middle;
        padding: 0 1;
    }
    Button {
        margin: 0 1;
    }
    #fp-edit {
        display: none;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("f5", "refresh", "Refresh", show=True),
        Binding("ctrl+g", "edit", "Edit", show=True),
    ]

    def __init__(
        self,
        start_dir: Path | None = None,
        title: str = "Select a file",
        show_files_only: bool = True,
    ) -> None:
        super().__init__()
        self._start_dir = (start_dir or Path.cwd()).resolve()
        self._title = title
        self._show_files_only = show_files_only
        self._selected: Path | None = None

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(id="fp-dialog"):
            yield Label(f"📁  {self._title}", id="fp-title")
            yield DirectoryTree(str(self._start_dir), id="fp-tree")
            with Horizontal(id="fp-buttons"):
                yield Button("Select", variant="primary", id="fp-select", disabled=True)
                yield Button("✏ Edit", variant="warning", id="fp-edit", disabled=True)
                yield Button("Cancel", variant="default", id="fp-cancel")
        yield Footer()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    @on(DirectoryTree.FileSelected, "#fp-tree")
    def _on_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Track the highlighted file; enable Select and Edit buttons."""
        self._selected = Path(event.path)
        self.query_one("#fp-select", Button).disabled = False
        # Show and enable Edit only for plain files (not dirs)
        edit_btn = self.query_one("#fp-edit", Button)
        edit_btn.display = True
        edit_btn.disabled = False

    @on(DirectoryTree.DirectorySelected, "#fp-tree")
    def _on_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        """Track highlighted directory (only selectable when show_files_only=False)."""
        if not self._show_files_only:
            self._selected = Path(event.path)
            self.query_one("#fp-select", Button).disabled = False
        # Edit is not available for directories
        edit_btn = self.query_one("#fp-edit", Button)
        edit_btn.display = False
        edit_btn.disabled = True

    @on(Button.Pressed, "#fp-select")
    def _on_select(self) -> None:
        if self._selected:
            self.dismiss(FilePickerResult(path=self._selected, action="select"))

    @on(Button.Pressed, "#fp-edit")
    def _on_edit_button(self) -> None:
        self.action_edit()

    @on(Button.Pressed, "#fp-cancel")
    def _on_cancel(self) -> None:
        self.dismiss(None)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_cancel(self) -> None:
        """Dismiss without a selection."""
        self.dismiss(None)

    def action_refresh(self) -> None:
        """Reload the directory tree from disk."""
        self.query_one("#fp-tree", DirectoryTree).reload()

    def action_edit(self) -> None:
        """Open the currently selected file in the external editor."""
        if self._selected and self._selected.is_file():
            self.dismiss(FilePickerResult(path=self._selected, action="edit"))
