"""
What to bring, as a short list of keys.

The clothing paragraph is prose, which is good to read and bad to draw. This is
the same judgement as a list, so the page can show it as icons and the two
cannot disagree: both read the same forecast through the same thresholds.

The keys are stable names, not display text. The page turns ``umbrella`` into an
icon and a word in the visitor's language.
"""
from src.servers.app_server.weather_api import Forecast

NO_RAIN = "No rain expected"

# Temperature, in Celsius, below which each layer is called for.
COAT_BELOW = 12
JACKET_BELOW = 18
GLOVES_BELOW = 8
HOT_FROM = 27
WATER_FROM = 28
STRONG_UV = 6
UV_FOR_SUNGLASSES = 4
WINDY_FROM = 30           # km/h
EVENING_DROP = 10         # degrees between the high and the low


def gear_for(forecast: Forecast, profiles=None) -> list[str]:
    """The things worth taking, in the order the page shows them."""
    gear: list[str] = []
    wind = forecast.peak_wind_kmh

    if forecast.rain_summary != NO_RAIN:
        gear.append("umbrella")

    if forecast.max_temp < COAT_BELOW:
        gear.append("warm_coat")
    elif forecast.max_temp < JACKET_BELOW or (
            forecast.max_temp - forecast.min_temp >= EVENING_DROP
            and forecast.min_temp < COAT_BELOW + 4):
        gear.append("jacket")

    if forecast.max_temp < GLOVES_BELOW:
        gear.append("gloves")
    if wind >= WINDY_FROM:
        gear.append("windbreaker")

    uv = forecast.uv_max or 0
    if forecast.max_temp >= HOT_FROM or uv >= STRONG_UV:
        gear.append("hat")
    if uv >= STRONG_UV:
        gear.append("sunscreen")
    if uv >= UV_FOR_SUNGLASSES or forecast.max_temp >= HOT_FROM:
        gear.append("sunglasses")
    if forecast.max_temp >= WATER_FROM:
        gear.append("water")

    if _has_young_child(profiles):
        gear.append("spare_clothes")

    return list(dict.fromkeys(gear))


def _has_young_child(profiles) -> bool:
    from src.servers.app_server.local_advisor import BABY_WORDS, CHILD_WORDS
    young = BABY_WORDS | CHILD_WORDS
    return any(isinstance(p, dict)
               and str(p.get("age_category", "")).strip().lower() in young
               for p in profiles or [])
