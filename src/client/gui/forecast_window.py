"""The answer: the numbers laid out, then what to wear."""
import tkinter as tk

from src.client.gui import theme
from src.client.gui.base import BaseWindow
from src.client.gui.parsing import degrees, first_hour


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
        tk.Label(inner, text=f"{degrees(current)}", font=theme.display(),
                 fg=theme.WARM, bg=theme.SURFACE, anchor="w").pack(fill=tk.X)

    def _build_stats(self, parent) -> None:
        row = tk.Frame(parent, bg=theme.CANVAS)
        row.pack(fill=tk.X, pady=(12, 0))

        rain = self.card_data.get("rain", "unknown")
        dry = rain == "No rain expected"
        for index, (caption, value, colour) in enumerate((
                ("low", degrees(self.card_data.get("min_temp")), theme.COOL),
                ("high", degrees(self.card_data.get("max_temp")), theme.WARM),
                ("rain", "none expected" if dry else first_hour(rain),
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
