"""Reading: a file from the archive, an error, or the archive listing itself."""
import tkinter as tk
from tkinter import scrolledtext

from src.client.gui import theme
from src.client.gui.base import BaseWindow
from src.client.gui.parsing import parse_listing, readable


class TextWindow(BaseWindow):
    """A read only view of a file from the archive, or of an error."""

    size = "700x620"

    def __init__(self, heading: str, content, subtitle: str = "",
                 tone: str = "normal") -> None:
        self.heading = heading
        self.subtitle = subtitle
        self.tone = tone
        self.content = readable(content)
        self.title = f"WeatherWear - {heading}"
        super().__init__()

    def build(self) -> None:
        self.add_header(self.heading, self.subtitle)

        card = self.card(self.root, fill=tk.BOTH, expand=True, padx=22, pady=18)
        area = scrolledtext.ScrolledText(
            card, font=theme.code() if self.tone == "normal" else theme.body(),
            bg=theme.SURFACE, fg=theme.DANGER if self.tone == "error" else theme.INK,
            relief=tk.FLAT, wrap=tk.WORD, padx=18, pady=16, highlightthickness=0)
        area.insert(tk.END, self.content)
        area.config(state=tk.DISABLED)
        area.pack(fill=tk.BOTH, expand=True)

        footer = tk.Frame(self.root, bg=theme.CANVAS)
        footer.pack(fill=tk.X, padx=22, pady=(0, 18))
        self.primary_button(footer, "Close", self.close).pack(fill=tk.X)


class ArchiveWindow(BaseWindow):
    """The archive listing: pick a file to open."""

    size = "480x520"

    def __init__(self, listing: str) -> None:
        self.entries = parse_listing(listing)
        self.title = "WeatherWear - Archive"
        super().__init__()

    def build(self) -> None:
        self.add_header("Archive", "Forecasts and reports saved by the server")

        card = self.card(self.root, fill=tk.BOTH, expand=True, padx=22, pady=18)
        inner = tk.Frame(card, bg=theme.SURFACE)
        inner.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)

        self.listbox = tk.Listbox(
            inner, font=theme.body(), bg=theme.SURFACE, fg=theme.INK,
            selectbackground=theme.BRAND, selectforeground=theme.ON_DARK,
            relief=tk.FLAT, highlightthickness=0, activestyle="none")
        self.listbox.pack(fill=tk.BOTH, expand=True)

        for name, size in self.entries:
            self.listbox.insert(tk.END, f"  {name}    {size}")

        if not self.entries:
            self.listbox.insert(tk.END, "  The archive is empty.")
            self.listbox.config(state=tk.DISABLED, fg=theme.INK_FAINT)
        else:
            self.listbox.selection_set(0)
        self.listbox.bind("<Double-1>", self.select)

        footer = tk.Frame(self.root, bg=theme.CANVAS)
        footer.pack(fill=tk.X, padx=22, pady=(0, 18))
        self.primary_button(footer, "Open", self.select).pack(fill=tk.X)

    def select(self, _event=None) -> None:
        selection = self.listbox.curselection()
        if selection and self.entries:
            self.result = self.entries[selection[0]][0]
            self.close()
