"""Reading: a file from the archive, an error, or the archive listing itself."""
import tkinter as tk
from tkinter import scrolledtext

from src.client.gui import theme
from src.client.gui.base import BaseWindow
from src.client.gui.parsing import parse_listing, readable


class TextWindow(BaseWindow):
    """A read only view of a file from the archive, or of an error."""

    min_width = 480
    min_height = 340

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
        self.add_footer("Close", self.close)

        # The text widget scrolls itself, so this body does not need to.
        card = self.card(self.root, fill=tk.BOTH, expand=True, side=tk.TOP,
                         padx=18, pady=(14, 4))
        area = scrolledtext.ScrolledText(
            card, font=theme.code() if self.tone == "normal" else theme.body(),
            bg=theme.SURFACE, fg=theme.DANGER if self.tone == "error" else theme.INK,
            relief=tk.FLAT, wrap=tk.WORD, padx=14, pady=12, highlightthickness=0,
            width=1, height=1)
        area.insert(tk.END, self.content)
        area.config(state=tk.DISABLED)
        area.pack(fill=tk.BOTH, expand=True)

    def fit_to_screen(self) -> None:
        """A file viewer wants room, not a snug fit around one line of text."""
        self.root.update_idletasks()
        available_w = self.root.winfo_screenwidth() - 60
        available_h = self.root.winfo_screenheight() - 110
        width = min(760, available_w)
        height = min(620, available_h)
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 2 - 20)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(self.min_width, min(self.min_height, available_h))


class ArchiveWindow(BaseWindow):
    """The archive listing: pick a file to open."""

    min_width = 420
    min_height = 340

    def __init__(self, listing: str) -> None:
        self.entries = parse_listing(listing)
        self.title = "WeatherWear - Archive"
        super().__init__()

    def build(self) -> None:
        self.add_header("Archive", "Forecasts and reports saved by the server")
        self.add_footer("Open", self.select)

        card = self.card(self.root, fill=tk.BOTH, expand=True, side=tk.TOP,
                         padx=18, pady=(14, 4))
        inner = tk.Frame(card, bg=theme.SURFACE)
        inner.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.listbox = tk.Listbox(
            inner, font=theme.body(), bg=theme.SURFACE, fg=theme.INK,
            selectbackground=theme.BRAND, selectforeground=theme.ON_DARK,
            relief=tk.FLAT, highlightthickness=0, activestyle="none",
            width=1, height=1)
        bar = tk.Scrollbar(inner, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=bar.set)
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for name, size in self.entries:
            self.listbox.insert(tk.END, f"  {name}    {size}")

        if not self.entries:
            self.listbox.insert(tk.END, "  The archive is empty.")
            self.listbox.config(state=tk.DISABLED, fg=theme.INK_FAINT)
        else:
            self.listbox.selection_set(0)
        self.listbox.bind("<Double-1>", self.select)

    def fit_to_screen(self) -> None:
        self.root.update_idletasks()
        available_h = self.root.winfo_screenheight() - 110
        width = min(520, self.root.winfo_screenwidth() - 60)
        height = min(460, available_h)
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 2 - 20)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(self.min_width, min(self.min_height, available_h))

    def select(self, _event=None) -> None:
        selection = self.listbox.curselection()
        if selection and self.entries:
            self.result = self.entries[selection[0]][0]
            self.close()
