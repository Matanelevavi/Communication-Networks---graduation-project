"""
The Tkinter interface.

    theme.py     colours and fonts, named once
    base.py      the window every screen inherits from
    windows.py   the three screens

The functions below are the whole public surface: the session module calls
them and never touches Tk directly.
"""


def get_user_data_gui() -> tuple:
    """
    Ask what to request.

    Returns ``(action, city, profiles, protocol)``, or four ``None`` values if
    the user closed the window instead of choosing.
    """
    from src.client.gui.windows import RequestWindow

    return RequestWindow().show() or (None, None, None, None)


def show_ftp_list_gui(listing: str) -> str | None:
    """Show the archive and return the file the user picked, if any."""
    from src.client.gui.windows import ArchiveWindow

    return ArchiveWindow(listing).show()


def show_result_gui(action: str, subject: str, content) -> None:
    """Display an answer from the server, or an error message."""
    from src.client.gui.windows import ResultWindow

    ResultWindow(action, subject, content).show()


__all__ = ["get_user_data_gui", "show_ftp_list_gui", "show_result_gui"]
