"""
Request routing.

Turns a decoded request into an answer, and knows nothing about how it arrived.
That is what lets the same code serve a TCP connection and an RUDP transfer:
both listeners hand a dictionary here and send back whatever comes out.

A forecast answer is a JSON object rather than a paragraph, so the client can
lay the numbers out itself instead of parsing prose. Every failure is a plain
string that starts with ``Error:``, so the client has one rule for telling an
error from a result.
"""
import dataclasses
import hashlib
import json
import logging
import math
import time

from src.config import MAX_PROFILE_FIELD, MAX_PROFILES
from src.servers.app_server.advisor import ClothingAdvisor
from src.servers.app_server.agent import FileAgent
from src.servers.app_server.external_service import ServiceError
from src.servers.app_server.forecast_cache import PRIVATE_PREFIX
from src.servers.app_server.gear import gear_for
from src.servers.app_server.weather_api import Forecast, Place, WeatherService

log = logging.getLogger(__name__)

ERROR_PREFIX = "Error: "
UNKNOWN_ACTION = "Error: Unknown action requested."
FORECAST_KIND = "forecast"
PLACES_KIND = "places"
PROFILE_FIELDS = ("name", "age_category", "notes")
LANGUAGES = ("he", "en")

MIN_QUERY = 2
MAX_QUERY = 60
SEARCH_TTL = 3600            # place names do not change, so an hour is cautious
SEARCH_CACHE_SIZE = 500
COORDINATE_DECIMALS = 2      # about a kilometre: plenty for weather, and no more precise than needed


def clean_profiles(raw) -> list[dict]:
    """
    The family description, reduced to known fields of bounded length.

    It arrives from the network and ends up in an AI prompt, so it is treated
    like any other untrusted input: unknown keys are dropped, every value
    becomes a short single line string, and only so many people are kept.
    """
    if not isinstance(raw, list):
        return []

    profiles = []
    for entry in raw[:MAX_PROFILES]:
        if not isinstance(entry, dict):
            continue
        profile = {field: " ".join(str(entry.get(field) or "").split())[:MAX_PROFILE_FIELD]
                   for field in PROFILE_FIELDS}
        if profile["name"]:
            profiles.append(profile)
    return profiles


class RequestRouter:
    """Dispatches one request to the right piece of application logic."""

    def __init__(self,
                 weather: WeatherService | None = None,
                 advisor: ClothingAdvisor | None = None,
                 agent: FileAgent | None = None) -> None:
        # Injected rather than constructed inline, so a test can substitute any
        # of the three without touching the network or the file system.
        self.weather = weather or WeatherService()
        self.advisor = advisor or ClothingAdvisor()
        self.agent = agent or FileAgent()

        self.actions = {
            "FORECAST": self.forecast,
            "SEARCH": self.search,
            "FTP_LIST": self.list_archive,
            "FTP_GET": self.read_archived_file,
        }
        self._searches: dict[str, tuple[float, str]] = {}

    def handle(self, request: dict) -> str | bytes:
        """Route one request.  Never raises: a failure comes back as a message."""
        if not isinstance(request, dict):
            return f"{ERROR_PREFIX}a request must be a JSON object."

        action = request.get("action", "FORECAST")
        handler = self.actions.get(action)
        if handler is None:
            return UNKNOWN_ACTION

        try:
            return handler(request)
        except ServiceError as e:
            # An expected, explainable failure: show it, but never cache it.
            log.warning(f"{action} failed: {e}")
            return f"{ERROR_PREFIX}{e}"

    # ------------------------------------------------------------ forecast
    def forecast(self, request: dict) -> str:
        city = " ".join(str(request.get("city") or "").split())
        coordinates = self._coordinates(request)
        if not city and coordinates is None:
            return f"{ERROR_PREFIX}FORECAST requires a city name."

        forecast, cached = self._weather_for(city, coordinates)
        profiles = clean_profiles(request.get("profiles"))
        language = request.get("lang") if request.get("lang") in LANGUAGES else None
        hint = {} if language is None else {"language": language}

        advice = self.advisor.recommend(forecast, profiles, **hint)
        card = self.build_card(forecast, advice, gear_for(forecast, profiles))
        return json.dumps({**card, "cached": cached}, ensure_ascii=False)

    @staticmethod
    def _coordinates(request: dict) -> tuple[float, float] | None:
        """
        The place the visitor chose or shared, rounded, or ``None`` if they sent a name.

        Rounded to about a kilometre on arrival: weather does not vary more
        finely than that, and a position kept no more precisely than it is
        needed is a smaller thing to hold.
        """
        if "lat" not in request and "lon" not in request:
            return None
        try:
            lat, lon = float(request["lat"]), float(request["lon"])
        except (KeyError, TypeError, ValueError):
            raise ServiceError("the coordinates are not valid.") from None
        if not (math.isfinite(lat) and math.isfinite(lon)
                and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ServiceError("the coordinates are not valid.")
        return round(lat, COORDINATE_DECIMALS), round(lon, COORDINATE_DECIMALS)

    @staticmethod
    def _cache_key(city: str, coordinates) -> str:
        """
        What a forecast is stored under.

        A chosen place is kept under its name *and* its coordinates, because
        "Ariel" is five different towns. A place the browser shared has no name
        and is somebody's position, so it gets a private key: a hash, which the
        archive neither lists nor serves.
        """
        if coordinates is None:
            return city
        lat, lon = coordinates
        if city:
            return f"{city} {lat:.{COORDINATE_DECIMALS}f} {lon:.{COORDINATE_DECIMALS}f}"
        digest = hashlib.sha256(f"{lat},{lon}".encode()).hexdigest()[:16]
        return f"{PRIVATE_PREFIX}{digest}"

    def _weather_for(self, city: str, coordinates=None) -> tuple[Forecast, bool]:
        """The forecast for a place, from the cache when it is recent enough."""
        key = self._cache_key(city, coordinates)
        stored = self.agent.cached_forecast(key)
        if stored:
            try:
                forecast = Forecast.from_dict(stored)
                if coordinates is not None:      # shown under this visitor's own label
                    forecast = dataclasses.replace(forecast, place=Place(city, *coordinates))
                return forecast, True
            except (KeyError, TypeError):
                log.warning(f"Cache entry for '{key}' is incomplete or old, refetching")

        if coordinates is None:
            forecast = self.weather.fetch(city)
        else:
            forecast = self.weather.fetch_at(city, *coordinates)
        # Only reached when the lookup succeeded, so nothing but real weather
        # is written to disk, and never the advice, which is per family.
        self.agent.store_forecast(key, forecast.to_dict())
        if not key.startswith(PRIVATE_PREFIX):
            self._archive_report(key, forecast)
        return forecast, False

    @staticmethod
    def build_card(forecast: Forecast, advice, gear: list[str] | None = None) -> dict:
        """The answer to a forecast request, as data rather than prose."""
        return {
            "kind": FORECAST_KIND,
            "city": forecast.place.name,
            "min_temp": forecast.min_temp,
            "max_temp": forecast.max_temp,
            "current_temp": forecast.current_temp,
            "rain": forecast.rain_summary,
            "advice": advice.text,
            "source": advice.source,
            "feels_like": forecast.feels_like,
            "humidity": forecast.humidity,
            "wind_kmh": forecast.wind_kmh,
            "weather_code": forecast.weather_code,
            "is_day": forecast.is_day,
            "uv_max": forecast.uv_max,
            "sunrise": forecast.sunrise,
            "sunset": forecast.sunset,
            "hourly": forecast.hourly,
            "daily": forecast.daily,
            "gear": gear or [],
        }

    def _archive_report(self, city: str, forecast: Forecast) -> None:
        csv_bytes = self.weather.download_csv_report(forecast.place)
        if csv_bytes:
            self.agent.store_report(city, csv_bytes)

    # -------------------------------------------------------------- search
    def search(self, request: dict) -> str:
        """Places that match what has been typed so far, for the suggestion list."""
        query = " ".join(str(request.get("query") or "").split())[:MAX_QUERY]
        if len(query) < MIN_QUERY:
            return json.dumps({"kind": PLACES_KIND, "places": []})

        key = query.casefold()
        hit = self._searches.get(key)
        if hit and time.monotonic() - hit[0] < SEARCH_TTL:
            return hit[1]

        answer = json.dumps({"kind": PLACES_KIND, "places": self.weather.search(query)},
                            ensure_ascii=False)
        if len(self._searches) >= SEARCH_CACHE_SIZE:
            self._searches.pop(next(iter(self._searches)))      # the oldest entry
        self._searches[key] = (time.monotonic(), answer)
        return answer

    # ----------------------------------------------------------------- ftp
    def list_archive(self, _request: dict) -> str:
        return self.agent.archive_listing()

    def read_archived_file(self, request: dict) -> str | bytes:
        filename = str(request.get("filename") or "")
        if not filename:
            return f"{ERROR_PREFIX}FTP_GET requires a filename."
        return self.agent.archived_file(filename)
