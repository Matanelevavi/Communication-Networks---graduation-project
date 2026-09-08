"""
The screens of the client.

None of them touches a socket: they collect input and display results, and the
session module carries the values between them and the network.
"""
import tkinter as tk
from tkinter import messagebox, scrolledtext

from src.client.gui import theme
from src.client.gui.base import BaseWindow

DEFAULT_CITY = "Ariel"
DEFAULT_PROFILES = ("Dana, Female, Adult, \n"
                    "Yossi, Male, Adult, \n"
                    "Noam, Female, Baby, daycare")
SIZE_MARKER = " (Size:"


class RequestWindow(BaseWindow):
    """The dashboard: what to ask for, about which city, over which protocol."""

    title = "WeatherWear"
    size = "560x660"

    def build(self) -> None:
        self.add_header("WeatherWear", "Weather, and what to wear for it")
        self.action = tk.StringVar(value="FORECAST")
        self.protocol_choice = tk.StringVar(value="RUDP")

        body = tk.Frame(self.root, bg=theme.CANVAS)
        body.pack(fill=tk.BOTH, expand=True, padx=22, pady=(18, 0))

        self._build_action(body)
        self._build_details(body)
        self._build_protocol(body)

        footer = tk.Frame(self.root, bg=theme.CANVAS)
        footer.pack(fill=tk.X, padx=22, pady=18)
        self.primary_button(footer, "Get my forecast", self.submit).pack(fill=tk.X)

    def _section(self, parent, caption: str) -> tk.Frame:
        self.caption(parent, caption, anchor="w", pady=(0, 6))
        card = self.card(parent, fill=tk.X, pady=(0, 16))
        inner = tk.Frame(card, bg=theme.SURFACE)
        inner.pack(fill=tk.X, padx=16, pady=14)
        return inner

    def _radio(self, parent, text: str, variable, value: str, note: str = "") -> None:
        row = tk.Frame(parent, bg=theme.SURFACE)
        row.pack(fill=tk.X, anchor="w")
        tk.Radiobutton(row, text=text, variable=variable, value=value,
                       bg=theme.SURFACE, fg=theme.INK, font=theme.body(),
                       activebackground=theme.SURFACE, selectcolor=theme.SURFACE,
                       cursor="hand2", anchor="w").pack(side=tk.LEFT)
        if note:
            tk.Label(row, text=note, font=theme.small(), fg=theme.INK_FAINT,
                     bg=theme.SURFACE).pack(side=tk.LEFT, padx=(6, 0))

    def _build_action(self, parent) -> None:
        inner = self._section(parent, "What do you need")
        self._radio(inner, "Today's forecast and advice", self.action, "FORECAST")
        self._radio(inner, "Browse the archive", self.action, "FTP_LIST",
                    "past forecasts and reports")

    def _build_details(self, parent) -> None:
        inner = self._section(parent, "Details")

        tk.Label(inner, text="City", font=theme.body_bold(), fg=theme.INK,
                 bg=theme.SURFACE, anchor="w").pack(fill=tk.X)
        self.city_entry = tk.Entry(inner, font=theme.body(), bg=theme.SURFACE_SUNK,
                                   fg=theme.INK, relief=tk.FLAT,
                                   highlightbackground=theme.BORDER,
                                   highlightcolor=theme.BRAND, highlightthickness=1,
                                   insertbackground=theme.INK)
        self.city_entry.insert(0, DEFAULT_CITY)
        self.city_entry.pack(fill=tk.X, ipady=6, pady=(4, 14))

        tk.Label(inner, text="Who is it for", font=theme.body_bold(), fg=theme.INK,
                 bg=theme.SURFACE, anchor="w").pack(fill=tk.X)
        tk.Label(inner, text="One person per line:  name, gender, age, notes",
                 font=theme.small(), fg=theme.INK_FAINT, bg=theme.SURFACE,
                 anchor="w").pack(fill=tk.X, pady=(1, 4))
        self.profiles_text = tk.Text(inner, height=4, font=theme.body(),
                                     bg=theme.SURFACE_SUNK, fg=theme.INK,
                                     relief=tk.FLAT, highlightbackground=theme.BORDER,
                                     highlightcolor=theme.BRAND, highlightthickness=1,
                                     insertbackground=theme.INK, padx=8, pady=6,
                                     wrap=tk.WORD)
        self.profiles_text.insert(tk.END, DEFAULT_PROFILES)
        self.profiles_text.pack(fill=tk.X)

    def _build_protocol(self, parent) -> None:
        inner = self._section(parent, "Transport")
        self._radio(inner, "RUDP", self.protocol_choice, "RUDP",
                    "reliability built on UDP, by hand")
        self._radio(inner, "TCP", self.protocol_choice, "TCP",
                    "the operating system does it")

    def submit(self) -> None:
        action = self.action.get()
        city = self.city_entry.get().strip()

        if action == "FORECAST" and not city:
            messagebox.showwarning("City needed", "Please enter a city name.")
            return

        self.result = (action, city,
                       parse_profiles(self.profiles_text.get("1.0", tk.END)),
                       self.protocol_choice.get())
        self.close()


class ForecastWindow(BaseWindow):
    """The answer: the numbers laid out, then what to wear."""

    size = "620x660"

    def __init__(self, card: dict) -> None:
        self.card_data = card
        self.title = f"WeatherWear - {card.get('city', 'Forecast')}"
        super().__init__()

    def build(self) -> None:
        city = self.card_data.get("city", "your city")
        self.add_header(city, "Today's forecast")

        body = tk.Frame(self.root, bg=theme.CANVAS)
        body.pack(fill=tk.BOTH, expand=True, padx=22, pady=18)

        self._build_temperature(body)
        self._build_stats(body)
        self._build_advice(body)

        footer = tk.Frame(self.root, bg=theme.CANVAS)
        footer.pack(fill=tk.X, padx=22, pady=(0, 18))
        self.primary_button(footer, "Done", self.close).pack(fill=tk.X)

    def _build_temperature(self, parent) -> None:
        card = self.card(parent, fill=tk.X)
        inner = tk.Frame(card, bg=theme.SURFACE)
        inner.pack(fill=tk.X, padx=20, pady=18)

        current = self.card_data.get("current_temp")
        self.caption(inner, "right now", anchor="w")
        tk.Label(inner, text=f"{_degrees(current)}", font=theme.display(),
                 fg=theme.WARM, bg=theme.SURFACE, anchor="w").pack(fill=tk.X)

    def _build_stats(self, parent) -> None:
        row = tk.Frame(parent, bg=theme.CANVAS)
        row.pack(fill=tk.X, pady=(12, 0))

        rain = self.card_data.get("rain", "unknown")
        dry = rain == "No rain expected"
        for index, (caption, value, colour) in enumerate((
                ("low", _degrees(self.card_data.get("min_temp")), theme.COOL),
                ("high", _degrees(self.card_data.get("max_temp")), theme.WARM),
                ("rain", "none expected" if dry else _first_hour(rain),
                 theme.INK_SOFT if dry else theme.COOL))):
            cell = tk.Frame(row, bg=theme.CANVAS)
            cell.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                      padx=(0 if index == 0 else 6, 0))
            card = self.card(cell, fill=tk.BOTH, expand=True)
            inner = tk.Frame(card, bg=theme.SURFACE)
            inner.pack(fill=tk.BOTH, padx=14, pady=12)
            self.caption(inner, caption, anchor="w")
            tk.Label(inner, text=value, font=theme.body_bold(), fg=colour,
                     bg=theme.SURFACE, anchor="w").pack(fill=tk.X, pady=(2, 0))

    def _build_advice(self, parent) -> None:
        card = self.card(parent, fill=tk.BOTH, expand=True, pady=(12, 0))
        inner = tk.Frame(card, bg=theme.SURFACE)
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        head = tk.Frame(inner, bg=theme.SURFACE)
        head.pack(fill=tk.X)
        tk.Label(head, text="What to wear", font=theme.heading(), fg=theme.INK,
                 bg=theme.SURFACE, anchor="w").pack(side=tk.LEFT)
        self._badge(head).pack(side=tk.RIGHT)

        text = tk.Text(inner, font=theme.body(), bg=theme.SURFACE, fg=theme.INK,
                       relief=tk.FLAT, wrap=tk.WORD, height=8,
                       padx=0, pady=8, spacing2=4, spacing3=8,
                       highlightthickness=0)
        text.insert(tk.END, self.card_data.get("advice", ""))
        text.config(state=tk.DISABLED)
        text.pack(fill=tk.BOTH, expand=True)

    def _badge(self, parent) -> tk.Label:
        """Say plainly which advisor wrote the paragraph."""
        if self.card_data.get("source") == "ai":
            text, colour = "AI advisor", theme.BRAND
        else:
            text, colour = "local advisor", theme.INK_FAINT
        if self.card_data.get("cached"):
            text += " - cached"
        return tk.Label(parent, text=text, font=theme.label(), fg=colour,
                        bg=theme.BRAND_TINT, padx=8, pady=3)


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


class BusyWindow(BaseWindow):
    """
    Shown while a request is on the wire.

    Without it the interface simply disappears for a couple of seconds while
    the server talks to two external services, which reads as a freeze. The
    work runs on a thread and the window polls it, so Tk keeps redrawing.
    """

    size = "360x150"
    resizable = False

    def __init__(self, message: str, work) -> None:
        self.message = message
        self.work = work
        self.error = None
        self.finished = False
        self.title = "WeatherWear"
        super().__init__()

    def build(self) -> None:
        frame = tk.Frame(self.root, bg=theme.SURFACE)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text=self.message, font=theme.body_bold(), fg=theme.INK,
                 bg=theme.SURFACE).pack(pady=(34, 6))
        self.dots = tk.Label(frame, text="", font=theme.heading(), fg=theme.BRAND,
                             bg=theme.SURFACE)
        self.dots.pack()

        self.root.after(60, self._start)
        self._animate(0)

    def _start(self) -> None:
        import threading

        def run():
            try:
                self.result = self.work()
            except Exception as e:                       # surfaced by the caller
                self.error = e
            finally:
                self.finished = True

        threading.Thread(target=run, daemon=True).start()
        self._poll()

    def _poll(self) -> None:
        if self.finished:
            self.close()
        else:
            self.root.after(80, self._poll)

    def _animate(self, step: int) -> None:
        if self.finished:
            return
        self.dots.config(text="● " * (step % 4))
        self.root.after(320, self._animate, step + 1)

    def on_close(self) -> None:
        """The work cannot be cancelled, so closing early is ignored."""


# ------------------------------------------------------------------ helpers
def _degrees(value) -> str:
    if value is None:
        return "--"
    return f"{value:g}°"


def _first_hour(rain_summary: str) -> str:
    """The server sends "07:00 (40%), 08:00 (55%)"; the tile shows the first."""
    return f"from {rain_summary.split(' ')[0]}"


def parse_profiles(raw: str) -> list[dict]:
    """Read the free text box as one profile per comma separated line."""
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


def parse_listing(listing: str) -> list[tuple[str, str]]:
    """
    Read the file names and sizes out of the archive listing.

    Each row is ``- <name> (Size: N KB)``. Splitting on the size marker rather
    than on whitespace keeps names that contain a space intact.
    """
    entries = []
    for line in listing.split("\n"):
        if not line.startswith("- "):
            continue
        name, _, size = line[2:].partition(SIZE_MARKER)
        name = name.strip()
        if name:
            entries.append((name, size.rstrip(")").strip()))
    return entries


def readable(content) -> str:
    """Text widgets cannot display bytes, so describe a binary answer instead."""
    if isinstance(content, (bytes, bytearray)):
        return f"Binary file, {len(content)} bytes.\nIt cannot be displayed as text."
    return content
