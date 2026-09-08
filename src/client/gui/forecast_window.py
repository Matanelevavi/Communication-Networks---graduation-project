"""The answer: the numbers laid out, then what to wear."""
import tkinter as tk

from src.client.gui import theme
from src.client.gui.base import BaseWindow
from src.client.gui.parsing import degrees, first_hour


class ForecastWindow(BaseWindow):
    """Shows one forecast card."""

    min_width = 460
    min_height = 400

    def __init__(self, card: dict) -> None:
        self.card_data = card
        self.title = f"WeatherWear - {card.get('city', 'Forecast')}"
        super().__init__()

    def build(self) -> None:
        self.add_header(self.card_data.get("city", "your city"), "Today's forecast")
        self.add_footer("Done", self.close)

        body = self.scrollable_body()
        pad = tk.Frame(body, bg=theme.CANVAS)
        pad.pack(fill=tk.BOTH, expand=True, padx=18, pady=(14, 4))

        self._build_temperature(pad)
        self._build_stats(pad)
        self._build_advice(pad)

    def _build_temperature(self, parent) -> None:
        card = self.card(parent, fill=tk.X)
        inner = tk.Frame(card, bg=theme.SURFACE)
        inner.pack(fill=tk.X, padx=16, pady=12)

        self.caption(inner, "right now", anchor="w")
        tk.Label(inner, text=degrees(self.card_data.get("current_temp")),
                 font=theme.display(), fg=theme.WARM, bg=theme.SURFACE,
                 anchor="w").pack(fill=tk.X)

    def _build_stats(self, parent) -> None:
        row = tk.Frame(parent, bg=theme.CANVAS)
        row.pack(fill=tk.X, pady=(10, 0))

        rain = self.card_data.get("rain", "unknown")
        dry = rain == "No rain expected"
        tiles = (
            ("low", degrees(self.card_data.get("min_temp")), theme.COOL),
            ("high", degrees(self.card_data.get("max_temp")), theme.WARM),
            ("rain", "none" if dry else first_hour(rain),
             theme.INK_SOFT if dry else theme.COOL),
        )
        for index, (caption, value, colour) in enumerate(tiles):
            cell = tk.Frame(row, bg=theme.CANVAS)
            cell.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                      padx=(0 if index == 0 else 6, 0))
            card = self.card(cell, fill=tk.BOTH, expand=True)
            inner = tk.Frame(card, bg=theme.SURFACE)
            inner.pack(fill=tk.BOTH, padx=11, pady=9)
            self.caption(inner, caption, anchor="w")
            tk.Label(inner, text=value, font=theme.body_bold(), fg=colour,
                     bg=theme.SURFACE, anchor="w").pack(fill=tk.X, pady=(1, 0))

    def _build_advice(self, parent) -> None:
        card = self.card(parent, fill=tk.BOTH, expand=True, pady=(10, 0))
        inner = tk.Frame(card, bg=theme.SURFACE)
        inner.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        head = tk.Frame(inner, bg=theme.SURFACE)
        head.pack(fill=tk.X)
        tk.Label(head, text="What to wear", font=theme.heading(), fg=theme.INK,
                 bg=theme.SURFACE, anchor="w").pack(side=tk.LEFT)
        self._badge(head).pack(side=tk.RIGHT)

        # The paragraph is the point of the screen, so it is the part that
        # grows; a Label would not wrap to the window width.
        text = tk.Message(inner, text=self.card_data.get("advice", ""),
                          font=theme.body(), bg=theme.SURFACE, fg=theme.INK,
                          justify=tk.LEFT, anchor="w", width=420)
        text.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        inner.bind("<Configure>",
                   lambda e: text.configure(width=max(260, e.width - 8)))

    def _badge(self, parent) -> tk.Label:
        """Say plainly which advisor wrote the paragraph."""
        if self.card_data.get("source") == "ai":
            text, colour = "AI advisor", theme.BRAND
        else:
            text, colour = "local advisor", theme.INK_FAINT
        if self.card_data.get("cached"):
            text += " - cached"
        return tk.Label(parent, text=text, font=theme.label(), fg=colour,
                        bg=theme.BRAND_TINT, padx=7, pady=2)
