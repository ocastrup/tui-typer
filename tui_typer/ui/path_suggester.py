"""Path tab-completion suggester for the command Input widget.

Provides a :class:`~textual.suggester.Suggester` subclass that completes
filesystem paths as the user types in the command input box.

The suggester activates when the last token in the input looks like a
path (starts with ``./``, ``../``, ``~/``, ``/``, or contains a path
separator).  It lists the contents of the parent directory and returns
the first alphabetically matching entry.

Textual renders the suggestion as a greyed-out ghost text; pressing
``Tab`` or ``→`` accepts it.

Usage
-----
Attach to an :class:`~textual.widgets.Input` widget::

    from tui_typer.ui.path_suggester import PathSuggester

    yield Input(
        id="input-box",
        placeholder="Enter command…",
        suggester=PathSuggester(),
    )
"""

from __future__ import annotations

from pathlib import Path

from textual.suggester import Suggester


class PathSuggester(Suggester):
    """Suggest filesystem path completions for the last token in the input.

    Parameters
    ----------
    case_sensitive:
        Whether path matching is case-sensitive.  Defaults to ``False``
        so completion works naturally on Windows.
    """

    def __init__(self, *, case_sensitive: bool = False) -> None:
        super().__init__(use_cache=False, case_sensitive=case_sensitive)

    async def get_suggestion(self, value: str) -> str | None:
        """Return the best path completion for *value*, or ``None``.

        Only the **last whitespace-separated token** is treated as a path
        candidate.  The suggestion returned is the full input string with
        the last token replaced by the completed path, so Textual shows
        the correct ghost text.
        """
        if not value:
            return None

        tokens = value.split()
        last = tokens[-1] if tokens else ""

        # Only complete tokens that look like paths
        if not _looks_like_path(last):
            return None

        completed = _complete_path(last)
        if completed is None:
            return None

        # Rebuild the full input string with the completed token
        tokens[-1] = completed
        return " ".join(tokens)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _looks_like_path(token: str) -> bool:
    """Return True if *token* should be treated as a filesystem path."""
    return (
        token.startswith(("./", "../", "~/", "/", ".\\", "..\\"))
        or "\\" in token
        or (len(token) > 1 and token[1] == ":")  # Windows drive letter: C:\…
        or "/" in token
    )


def _complete_path(partial: str) -> str | None:
    """Return the first alphabetical completion for *partial*, or ``None``."""
    path = Path(partial).expanduser()

    # If partial ends with a separator, list the directory itself
    if partial.endswith(("/", "\\")):
        parent = path
        prefix = ""
    else:
        parent = path.parent
        prefix = path.name

    if not parent.is_dir():
        return None

    try:
        entries = sorted(parent.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return None

    for entry in entries:
        if entry.name.lower().startswith(prefix.lower()):
            # Reconstruct the original partial's base so we preserve ~/  ./  etc.
            base = partial[: len(partial) - len(prefix)]
            completed = base + entry.name
            if entry.is_dir():
                completed += "/"
            return completed

    return None
