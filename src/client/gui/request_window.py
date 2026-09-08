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
    """
    Collects one request from the user.

    The two short choices sit side by side rather than stacked, which is what
    lets the whole form fit on a small or scaled display without scrolling.
    """

    title = "WeatherWear"
    min_width = 540
    min_height = 380

    def build(self) -> None:
        self.add_header("WeatherWear", "Weather, and what to wear for it")
        # bound to this window explicitly: a StringVar with no master attaches
        # to Tkinter's default root, which is a different window's interpreter
        # once more than one has been created
        self.action = tk.StringVar(master=self.root, value="FORECAST")
        self.protocol_choice = tk.StringVar(master=self.root, value="RUDP")

        # the footer first, so it keeps its place at the bottom edge
        self.add_footer("Get my forecast", self.submit)

        body = self.scrollable_body()
        pad = tk.Frame(body, bg=theme.CANVAS)
        pad.pack(fill=tk.BOTH, expand=True, padx=16, pady=(12, 4))

        self._build_choices(pad)
        self._build_details(pad)

    # ------------------------------------------------------------- pieces
    def _card_with_caption(self, parent, caption: str, **pack) -> tk.Frame:
        column = tk.Frame(parent, bg=theme.CANVAS)
        column.pack(**pack)
        self.caption(column, caption, anchor="w", pady=(0, 4))
        card = self.card(column, fill=tk.BOTH, expand=True)
        inner = tk.Frame(card, bg=theme.SURFACE)
        inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=9)
        return inner

    def _radio(self, parent, text: str, variable, value: str) -> None:
        tk.Radiobutton(parent, text=text, variable=variable, value=value,
                       bg=theme.SURFACE, fg=theme.INK, font=theme.body(),
                       activebackground=theme.SURFACE, selectcolor=theme.SURFACE,
                       cursor="hand2", anchor="w").pack(fill=tk.X, anchor="w")

    def _build_choices(self, parent) -> None:
        row = tk.Frame(parent, bg=theme.CANVAS)
        row.pack(fill=tk.X, pady=(0, 10))

        action = self._card_with_caption(row, "What do you need",
                                         side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._radio(action, "Today's forecast", self.action, "FORECAST")
        self._radio(action, "Browse the archive", self.action, "FTP_LIST")

        transport = self._card_with_caption(row, "Transport", side=tk.LEFT,
                                            fill=tk.BOTH, expand=True, padx=(10, 0))
        self._radio(transport, "RUDP", self.protocol_choice, "RUDP")
        self._radio(transport, "TCP", self.protocol_choice, "TCP")

    def _build_details(self, parent) -> None:
        inner = self._card_with_caption(parent, "Details", fill=tk.X)

        tk.Label(inner, text="City", font=theme.body_bold(), fg=theme.INK,
                 bg=theme.SURFACE, anchor="w").pack(fill=tk.X)
        self.city_entry = tk.Entry(inner, font=theme.body(), bg=theme.SURFACE_SUNK,
                                   fg=theme.INK, relief=tk.FLAT,
                                   highlightbackground=theme.BORDER,
                                   highlightcolor=theme.BRAND, highlightthickness=1,
                                   insertbackground=theme.INK)
        self.city_entry.insert(0, DEFAULT_CITY)
        self.city_entry.pack(fill=tk.X, ipady=4, pady=(3, 9))

        tk.Label(inner, text="Who is it for", font=theme.body_bold(), fg=theme.INK,
                 bg=theme.SURFACE, anchor="w").pack(fill=tk.X)
        tk.Label(inner, text="one per line:  name, gender, age, notes",
                 font=theme.small(), fg=theme.INK_FAINT, bg=theme.SURFACE,
                 anchor="w").pack(fill=tk.X, pady=(0, 3))
        self.profiles_text = tk.Text(inner, height=3, width=30, font=theme.body(),
                                     bg=theme.SURFACE_SUNK, fg=theme.INK,
                                     relief=tk.FLAT, highlightbackground=theme.BORDER,
                                     highlightcolor=theme.BRAND, highlightthickness=1,
                                     insertbackground=theme.INK, padx=6, pady=4,
                                     wrap=tk.WORD)
        self.profiles_text.insert(tk.END, DEFAULT_PROFILES)
        self.profiles_text.pack(fill=tk.X)

    # ------------------------------------------------------------- submit
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
