"""
The window every screen is built on.

Each screen used to repeat the same setup and smuggle its answer out through a
mutable dictionary captured by a closure.  A class holds that answer as an
attribute instead, which is both shorter and easier to follow.
"""
import tkinter as tk

from src.client.gui import theme


class BaseWindow:
    """A modal Tk window that runs until it is closed and returns one result."""

    title = "WeatherWear"
    size = "600x600"

    def __init__(self) -> None:
        self.result = None

        self.root = tk.Tk()
        self.root.title(self.title)
        self.root.geometry(self.size)
        self.root.configure(bg=theme.BACKGROUND)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.build()

    def build(self) -> None:
        """Lay out the widgets.  Every screen implements this."""
        raise NotImplementedError

    def add_header(self, text: str, background: str, font) -> None:
        header = tk.Frame(self.root, bg=background, pady=15)
        header.pack(fill=tk.X)
        tk.Label(header, text=text, font=font,
                 fg=theme.TEXT_ON_DARK, bg=background).pack()

    def add_button(self, text: str, command, background: str) -> tk.Button:
        button = tk.Button(self.root, text=text, command=command,
                           font=theme.BUTTON, bg=background, fg=theme.TEXT_ON_DARK,
                           relief=tk.FLAT, padx=20, pady=5)
        button.pack(pady=15)
        return button

    def on_close(self) -> None:
        """Closing the window without choosing leaves the result unset."""
        self.result = None
        self.close()

    def close(self) -> None:
        self.root.destroy()

    def show(self):
        """Display the window and block until it closes, then return its result."""
        self.root.mainloop()
        return self.result
