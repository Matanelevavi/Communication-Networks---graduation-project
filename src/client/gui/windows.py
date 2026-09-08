"""
The three screens of the client.

None of them touches a socket: they collect input and display text, and the
session module carries the values between them and the network.
"""
import tkinter as tk
from tkinter import messagebox, scrolledtext

from src.client.gui import theme
from src.client.gui.base import BaseWindow

DEFAULT_CITY = "Ariel"
DEFAULT_PROFILES = ("Man, Male, Adult, \n"
                    "Women, Female, Adult, \n"
                    "child, Female, Baby, Daycare")
SIZE_MARKER = " (Size:"


class RequestWindow(BaseWindow):
    """The dashboard: what to ask for, about which city, over which protocol."""

    title = "WeatherWear - Dashboard"
    size = "550x550"

    def build(self) -> None:
        self.add_header("WeatherWear Command Center", theme.HEADER_DARK, theme.TITLE)
        self.action = tk.StringVar(value="FORECAST")
        self.protocol_choice = tk.StringVar(value="RUDP")

        self._build_action_card()
        self._build_details_card()
        self._build_protocol_card()
        self.add_button("Send Request", self.submit, theme.ACCENT_GREEN)

    def _card(self, label: str) -> tk.LabelFrame:
        frame = tk.LabelFrame(self.root, text=label, font=theme.SECTION,
                              bg=theme.SURFACE, padx=10, pady=10)
        frame.pack(fill=tk.X, padx=20, pady=10)
        return frame

    def _radio(self, parent, text: str, variable, value: str) -> None:
        tk.Radiobutton(parent, text=text, variable=variable, value=value,
                       bg=theme.SURFACE, font=theme.BODY).pack(anchor=tk.W)

    def _build_action_card(self) -> None:
        card = self._card(" 1. Choose Action ")
        self._radio(card, "Get AI Weather & Forecast", self.action, "FORECAST")
        self._radio(card, "View History Archive", self.action, "FTP_LIST")

    def _build_details_card(self) -> None:
        card = self._card(" 2. Details (For Forecast) ")

        tk.Label(card, text="City:", font=theme.BODY, bg=theme.SURFACE).pack(anchor=tk.W)
        self.city_entry = tk.Entry(card, font=theme.BODY, width=30, bg=theme.FIELD,
                                   relief=tk.SOLID, borderwidth=1)
        self.city_entry.insert(0, DEFAULT_CITY)
        self.city_entry.pack(anchor=tk.W, pady=(0, 10))

        tk.Label(card, text="Family (Name, Gender, Age, Notes):",
                 font=theme.BODY, bg=theme.SURFACE).pack(anchor=tk.W)
        self.profiles_text = tk.Text(card, height=4, width=55, font=theme.BODY,
                                     bg=theme.FIELD, relief=tk.SOLID, borderwidth=1)
        self.profiles_text.insert(tk.END, DEFAULT_PROFILES)
        self.profiles_text.pack(anchor=tk.W)

    def _build_protocol_card(self) -> None:
        card = self._card(" 3. Network Protocol ")
        self._radio(card, "RUDP", self.protocol_choice, "RUDP")
        self._radio(card, "TCP", self.protocol_choice, "TCP")

    def submit(self) -> None:
        action = self.action.get()
        city = self.city_entry.get().strip()

        if action == "FORECAST" and not city:
            messagebox.showwarning("Error", "Please enter a city.")
            return

        self.result = (action, city,
                       parse_profiles(self.profiles_text.get("1.0", tk.END)),
                       self.protocol_choice.get())
        self.close()


class ArchiveWindow(BaseWindow):
    """The archive listing: pick a file to download."""

    title = "FTP Archive, Select a File"
    size = "400x400"

    def __init__(self, listing: str) -> None:
        self.filenames = parse_listing(listing)
        super().__init__()

    def build(self) -> None:
        tk.Label(self.root, text="Double click a file to open", font=theme.LIST_ITEM,
                 bg=theme.BACKGROUND, pady=10).pack()

        self.listbox = tk.Listbox(self.root, font=theme.LIST_ITEM,
                                  selectbackground=theme.SELECTION, relief=tk.FLAT)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        for name in self.filenames:
            self.listbox.insert(tk.END, name)

        if not self.filenames:
            self.listbox.insert(tk.END, "No files found in archive.")
            self.listbox.config(state=tk.DISABLED)

        self.listbox.bind("<Double-1>", self.select)
        self.add_button("Open Selected File", self.select, theme.ACCENT_MINT)

    def select(self, _event=None) -> None:
        selection = self.listbox.curselection()
        if selection and self.filenames:
            self.result = self.filenames[selection[0]]
            self.close()


class ResultWindow(BaseWindow):
    """A read only view of whatever the server sent back."""

    title = "WeatherWear"
    size = "700x600"

    def __init__(self, action: str, subject: str, content) -> None:
        self.heading = self._heading(action, subject)
        self.content = readable(content)
        super().__init__()

    @staticmethod
    def _heading(action: str, subject: str) -> str:
        if action == "FORECAST":
            return f"Plan for {subject}"
        if action == "ERROR":
            return "Something went wrong"
        return "File Viewer"

    def build(self) -> None:
        self.root.title(self.heading)
        self.add_header(self.heading, theme.HEADER_BLUE, theme.BIG_TITLE)

        text_area = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, font=theme.CONTENT,
                                              bg=theme.SURFACE, fg=theme.TEXT,
                                              padx=15, pady=15, relief=tk.FLAT)
        text_area.insert(tk.END, self.content)
        text_area.config(state=tk.DISABLED)
        text_area.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)

        self.add_button("Close", self.close, theme.ACCENT_RED)


# ------------------------------------------------------------------ helpers
def parse_profiles(raw: str) -> list[dict]:
    """Read the free text family box as one profile per comma separated line."""
    profiles = []
    for line in raw.strip().split("\n"):
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 3:
            profiles.append({
                "name": parts[0],
                "gender": parts[1],
                "age_category": parts[2],
                "notes": parts[3] if len(parts) > 3 else "",
            })
    return profiles


def parse_listing(listing: str) -> list[str]:
    """
    Read the file names out of the archive listing.

    Each row is ``- <name> (Size: N KB)``.  Splitting on the size marker rather
    than on whitespace keeps names that contain a space intact.
    """
    names = []
    for line in listing.split("\n"):
        if not line.startswith("- "):
            continue
        name = line[2:].split(SIZE_MARKER)[0].strip()
        if name:
            names.append(name)
    return names


def readable(content) -> str:
    """Text widgets cannot display bytes, so describe a binary answer instead."""
    if isinstance(content, (bytes, bytearray)):
        return f"Binary file, {len(content)} bytes.\nIt cannot be displayed as text."
    return content
