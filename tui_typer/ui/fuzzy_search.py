"""Fuzzy file searcher and picker.

Presents a modal with a live-filtering ``Input`` and a ``ListView`` of
matched paths.  Matching uses a simple substring / initialism algorithm
so results feel instant even in large trees.

Usage
-----
::

    def _on_pick(path: Path | None) -> None:
        if path:
            self.add_output(f"Picked: {path}")

    self.push_screen(FuzzyFileSearchScreen(root=Path.cwd()), _on_pick)

Key bindings inside the modal
------------------------------
* ``↑`` / ``↓``    — move selection in the results list
* ``Enter``         — confirm selection
* ``Escape``        — cancel
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Label, ListItem, ListView

# ---------------------------------------------------------------------------
# Fuzzy matching helper
# ---------------------------------------------------------------------------


def _fuzzy_score(query: str, candidate: str) -> int:
    """Return a non-negative score for how well *query* matches *candidate*.

    Higher score = better match.  Returns 0 for no match.

    Strategy (in priority order):
    1. Exact substring match in the filename portion   → score 100 + position bonus
    2. All query characters appear in order (subsequence) → score 50
    3. No match                                         → score 0
    """
    if not query:
        return 1  # empty query matches everything with minimal score

    name = Path(candidate).name.lower()
    q = query.lower()

    # Exact substring in filename
    idx = name.find(q)
    if idx != -1:
        return 100 + (len(name) - idx)  # earlier position → higher bonus

    # Glob-style wildcard (e.g. "*.py")
    if "*" in q or "?" in q:
        if fnmatch.fnmatch(name, q):
            return 80
        return 0

    # Subsequence: every character of query appears in order
    it = iter(candidate.lower())
    if all(c in it for c in q):
        return 50

    return 0


# ---------------------------------------------------------------------------
# Modal screen
# ---------------------------------------------------------------------------


class FuzzyFileSearchScreen(ModalScreen[Path | None]):
    """Modal overlay that fuzzy-searches files under *root* in real time.

    Parameters
    ----------
    root:
        Directory to search recursively.  Defaults to ``Path.cwd()``.
    title:
        Heading shown above the search box.
    max_results:
        Cap on results shown in the list (default 200).
    glob:
        Optional glob pattern to pre-filter files (e.g. ``"*.py"``).
    """

    DEFAULT_CSS = """
    FuzzyFileSearchScreen {
        align: center middle;
    }
    #fz-dialog {
        width: 80%;
        height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 0 1;
    }
    #fz-title {
        text-style: bold;
        color: $primary;
        padding: 1 0 0 1;
        height: 3;
    }
    #fz-input {
        margin: 0 0 1 0;
    }
    #fz-count {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }
    ListView {
        height: 1fr;
        border: solid $accent;
    }
    ListItem {
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("enter", "select", "Select", show=True),
    ]

    def __init__(
        self,
        root: Path | None = None,
        title: str = "Fuzzy file search",
        max_results: int = 200,
        glob: str = "**/*",
    ) -> None:
        super().__init__()
        self._root = (root or Path.cwd()).resolve()
        self._title = title
        self._max_results = max_results
        self._glob = glob
        self._all_files: list[str] = []  # populated by background worker
        self._results: list[str] = []

    # ------------------------------------------------------------------
    # Compose & mount
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(id="fz-dialog"):
            yield Label(f"🔍  {self._title}", id="fz-title")
            yield Input(placeholder="Type to filter…", id="fz-input")
            yield Label("Scanning…", id="fz-count")
            yield ListView(id="fz-list")
        yield Footer()

    def on_mount(self) -> None:
        """Start the background scan and focus the search box."""
        self.query_one("#fz-input", Input).focus()
        self._scan_files()

    # ------------------------------------------------------------------
    # Background file scan
    # ------------------------------------------------------------------

    @work(thread=True, name="fz-scan")
    def _scan_files(self) -> None:
        """Collect all files under root in a background thread."""
        try:
            files = [
                str(p.relative_to(self._root)) for p in self._root.glob(self._glob) if p.is_file()
            ]
        except PermissionError:
            files = []
        self._all_files = sorted(files)
        # Trigger initial render on the event loop via the app's call_from_thread
        self.app.call_from_thread(self._apply_filter, "")

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def _apply_filter(self, query: str) -> None:
        """Re-rank *all_files* against *query* and rebuild the ListView."""
        if query:
            scored = [(score, f) for f in self._all_files if (score := _fuzzy_score(query, f)) > 0]
            scored.sort(key=lambda t: -t[0])
            self._results = [f for _, f in scored[: self._max_results]]
        else:
            self._results = self._all_files[: self._max_results]

        list_view = self.query_one("#fz-list", ListView)
        list_view.clear()
        for path_str in self._results:
            list_view.append(ListItem(Label(path_str)))

        count = len(self._results)
        total = len(self._all_files)
        suffix = f" of {total}" if count < total else ""
        self.query_one("#fz-count", Label).update(f"{count}{suffix} file(s) matched")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    @on(Input.Changed, "#fz-input")
    def _on_input_changed(self, event: Input.Changed) -> None:
        self._apply_filter(event.value.strip())

    @on(Input.Submitted, "#fz-input")
    def _on_input_submitted(self, _: Input.Submitted) -> None:
        self.action_select()

    @on(ListView.Selected, "#fz-list")
    def _on_list_selected(self, event: ListView.Selected) -> None:
        """Double-click or Enter on a list item."""
        self._confirm_index(event.list_view.index)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_select(self) -> None:
        """Confirm the currently highlighted list item."""
        list_view = self.query_one("#fz-list", ListView)
        self._confirm_index(list_view.index)

    def action_cancel(self) -> None:
        self.dismiss(None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _confirm_index(self, index: int | None) -> None:
        if index is not None and 0 <= index < len(self._results):
            full_path = self._root / self._results[index]
            self.dismiss(full_path)
        else:
            self.dismiss(None)
