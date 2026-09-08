"""
The Tkinter interface.

    theme.py     colours and fonts, named once
    base.py      the window every screen inherits from, and the shared widgets
    windows.py   the screens

The functions below are the whole public surface: the session module calls them
and never touches Tk directly.
"""


def ask_request() -> tuple:
    """
    Ask what to request.

    Returns ``(action, city, profiles, protocol)``, or four ``None`` values if
    the user closed the window instead of choosing.
    """
    from src.client.gui.windows import RequestWindow

    return RequestWindow().show() or (None, None, None, None)


def show_forecast(card: dict) -> None:
    """Lay out a forecast: the numbers, then what to wear."""
    from src.client.gui.windows import ForecastWindow

    ForecastWindow(card).show()


def show_text(heading: str, content, subtitle: str = "") -> None:
    """Display a file from the archive."""
    from src.client.gui.windows import TextWindow

    TextWindow(heading, content, subtitle).show()


def show_error(message: str) -> None:
    from src.client.gui.windows import TextWindow

    TextWindow("Something went wrong", message, tone="error").show()


def choose_archived_file(listing: str) -> str | None:
    """Show the archive and return the file the user picked, if any."""
    from src.client.gui.windows import ArchiveWindow

    return ArchiveWindow(listing).show()


def with_progress(message: str, work):
    """Run ``work`` on a thread behind a small progress window, then return it."""
    from src.client.gui.windows import BusyWindow

    window = BusyWindow(message, work)
    result = window.show()
    if window.error is not None:
        raise window.error
    return result


__all__ = ["ask_request", "choose_archived_file", "show_error", "show_forecast",
           "show_text", "with_progress"]
