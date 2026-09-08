"""The dashboard: what to ask for, about which city, over which transport."""
import tkinter as tk
from tkinter import messagebox

from src.client.gui import theme
from src.client.gui.base import BaseWindow
from src.client.gui.parsing import parse_profiles

DEFAULT_CITY = "Ariel"
DEFAULT_PROFILES = ("Dana, Female, Adult, \n"
                    "Yossi, Male, Adult, \n"
                    "Noam, Female, Baby, daycare")


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
