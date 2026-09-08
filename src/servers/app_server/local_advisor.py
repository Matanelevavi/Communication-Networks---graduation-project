"""
Clothing advice derived from the forecast itself, with no external service.

The AI advisor writes nicer prose, but it needs a key and it can fail. This one
always works, is instant, and is genuinely personalised: it reads the real
temperatures, the hours rain is expected and the swing across the day, and then
says something different for a baby than for an adult.

It is the default path, not a placeholder.
"""
from src.servers.app_server.weather_api import Forecast

# Temperature bands, in Celsius, and what to wear in each.
BANDS = (
    (5, "freezing", "a heavy coat, a hat and gloves"),
    (12, "cold", "a warm coat and long sleeves"),
    (18, "cool", "a jacket or a thick jumper"),
    (24, "mild", "light layers, a long sleeve top is enough"),
    (30, "warm", "light clothes, short sleeves"),
    (99, "hot", "the lightest clothes you have, and a hat"),
)

BIG_SWING = 10          # degrees between low and high that call for a layer
STRONG_SUN = 27         # above this, sun protection is worth mentioning


class LocalAdvisor:
    """Builds a recommendation paragraph from the numbers in a forecast."""

    def recommend(self, forecast: Forecast, profiles) -> str:
        parts = [self._headline(forecast)]

        rain = self._rain(forecast)
        if rain:
            parts.append(rain)

        swing = self._swing(forecast)
        if swing:
            parts.append(swing)

        parts.extend(self._per_person(forecast, profiles))

        if forecast.max_temp >= STRONG_SUN:
            parts.append("With that much sun, water and a hat are worth taking along.")

        return " ".join(parts)

    # ------------------------------------------------------------ the day
    @staticmethod
    def band(temperature: float) -> tuple[str, str]:
        """The word for a temperature, and what it calls for."""
        for ceiling, word, clothing in BANDS:
            if temperature < ceiling:
                return word, clothing
        return BANDS[-1][1], BANDS[-1][2]

    def _headline(self, forecast: Forecast) -> str:
        word, clothing = self.band(forecast.max_temp)
        return (f"{forecast.place.name} is {word} today, "
                f"{forecast.min_temp:g}° to {forecast.max_temp:g}°, so go with {clothing}.")

    @staticmethod
    def _rain(forecast: Forecast) -> str:
        if forecast.rain_summary == "No rain expected":
            return ""
        first_hour = forecast.rain_summary.split(" ")[0]
        return (f"Rain is likely from around {first_hour}, "
                f"so take a waterproof layer or an umbrella.")

    def _swing(self, forecast: Forecast) -> str:
        if forecast.max_temp - forecast.min_temp < BIG_SWING:
            return ""
        evening_word, _ = self.band(forecast.min_temp)
        return (f"It drops to {forecast.min_temp:g}° later, which is {evening_word}, "
                f"so bring something to put on for the evening.")

    # --------------------------------------------------------- the people
    def _per_person(self, forecast: Forecast, profiles) -> list[str]:
        """One sentence for anyone who needs different treatment from an adult."""
        notes = []
        for profile in profiles or []:
            if not isinstance(profile, dict):
                continue
            sentence = self._for_profile(forecast, profile)
            if sentence:
                notes.append(sentence)
        return notes

    def _for_profile(self, forecast: Forecast, profile: dict) -> str:
        name = str(profile.get("name", "")).strip() or "everyone"
        age = str(profile.get("age_category", "")).strip().lower()
        extra = str(profile.get("notes", "")).strip()

        if age == "baby":
            advice = (f"For {name}, add one more layer than you would wear yourself, "
                      f"and keep the pram out of direct sun."
                      if forecast.max_temp >= STRONG_SUN else
                      f"For {name}, add one more layer than you would wear yourself.")
        elif age in ("child", "kid"):
            advice = (f"{name} will be moving about, so something light "
                      f"underneath a layer that comes off easily works best.")
        else:
            return f"{name} can go with the same, adjusted to taste." if extra else ""

        if extra:
            advice += f" Worth packing a spare set for {extra.lower()}."
        return advice
