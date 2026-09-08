"""
The window every screen is built on.

Each screen used to repeat the same setup and smuggle its answer out through a
mutable dictionary captured by a closure. A class holds that answer as an
attribute instead, which is both shorter and easier to follow.

The shared widget helpers live here too, so the three screens agree on what a
card, a caption and a button look like without saying so three times.
"""
import tkinter as tk

from src.client.gui import theme


class BaseWindow:
    """A modal Tk window that runs until it is closed and returns one result."""

    title = "WeatherWear"
    size = "620x640"
    resizable = True

    def __init__(self) -> None:
        self.result = None

        self.root = tk.Tk()
        self.root.title(self.title)
        self.root.geometry(self.size)
        self.root.configure(bg=theme.CANVAS)
        self.root.resizable(self.resizable, self.resizable)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.build()
        self.center()

    def build(self) -> None:
        """Lay out the widgets.  Every screen implements this."""
        raise NotImplementedError

    def center(self) -> None:
        """Open in the middle of the screen rather than the top left corner."""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - width) // 2
        y = max(0, (self.root.winfo_screenheight() - height) // 2 - 30)
        self.root.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------ pieces
    def add_header(self, text: str, subtitle: str = "") -> tk.Frame:
        """The coloured band across the top of a window."""
        header = tk.Frame(self.root, bg=theme.BRAND)
        header.pack(fill=tk.X)

        inner = tk.Frame(header, bg=theme.BRAND)
        inner.pack(fill=tk.X, padx=26, pady=(20, 18))

        tk.Label(inner, text=text, font=theme.title(),
                 fg=theme.ON_DARK, bg=theme.BRAND, anchor="w").pack(fill=tk.X)
        if subtitle:
            tk.Label(inner, text=subtitle, font=theme.small(),
                     fg=theme.BRAND_TINT, bg=theme.BRAND, anchor="w").pack(
                fill=tk.X, pady=(3, 0))
        return header

    @staticmethod
    def card(parent, **pack) -> tk.Frame:
        """A white panel with a hairline border."""
        frame = tk.Frame(parent, bg=theme.SURFACE,
                         highlightbackground=theme.BORDER, highlightthickness=1)
        frame.pack(**pack)
        return frame

    @staticmethod
    def caption(parent, text: str, **pack) -> tk.Label:
        """A small uppercase label above a control."""
        widget = tk.Label(parent, text=text.upper(), font=theme.label(),
                          fg=theme.INK_FAINT, bg=parent["bg"], anchor="w")
        widget.pack(**pack)
        return widget

    def primary_button(self, parent, text: str, command) -> tk.Button:
        return self._button(parent, text, command, theme.BRAND, theme.BRAND_DARK,
                            theme.ON_DARK)

    def quiet_button(self, parent, text: str, command) -> tk.Button:
        return self._button(parent, text, command, theme.SURFACE, theme.CANVAS,
                            theme.INK_SOFT, border=True)

    @staticmethod
    def _button(parent, text, command, background, hover, foreground, border=False):
        button = tk.Button(
            parent, text=text, command=command, font=theme.body_bold(),
            bg=background, fg=foreground, activebackground=hover,
            activeforeground=foreground, relief=tk.FLAT, bd=0,
            padx=22, pady=9, cursor="hand2",
            highlightbackground=theme.BORDER, highlightthickness=1 if border else 0)
        button.bind("<Enter>", lambda _e: button.configure(bg=hover))
        button.bind("<Leave>", lambda _e: button.configure(bg=background))
        return button

    # ------------------------------------------------------------ lifecycle
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
