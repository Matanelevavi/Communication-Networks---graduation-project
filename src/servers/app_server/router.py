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
import json
import logging

from src.config import MAX_PROFILE_FIELD, MAX_PROFILES
from src.servers.app_server.advisor import ClothingAdvisor
from src.servers.app_server.agent import FileAgent
from src.servers.app_server.external_service import ServiceError
from src.servers.app_server.weather_api import Forecast, WeatherService

log = logging.getLogger(__name__)

ERROR_PREFIX = "Error: "
UNKNOWN_ACTION = "Error: Unknown action requested."
FORECAST_KIND = "forecast"
PROFILE_FIELDS = ("name", "age_category", "notes")


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
            "FTP_LIST": self.list_archive,
            "FTP_GET": self.read_archived_file,
        }

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
        if not city:
            return f"{ERROR_PREFIX}FORECAST requires a city name."

        forecast, cached = self._weather_for(city)
        advice = self.advisor.recommend(forecast, clean_profiles(request.get("profiles")))
        return json.dumps({**self.build_card(forecast, advice), "cached": cached},
                          ensure_ascii=False)

    def _weather_for(self, city: str) -> tuple[Forecast, bool]:
        """The forecast for a city, from the cache when it is recent enough."""
        stored = self.agent.cached_forecast(city)
        if stored:
            try:
                return Forecast.from_dict(stored), True
            except (KeyError, TypeError):
                log.warning(f"Cache entry for '{city}' is incomplete, refetching")

        forecast = self.weather.fetch(city)
        # Only reached when the lookup succeeded, so nothing but real weather
        # is written to disk, and never the advice, which is per family.
        self.agent.store_forecast(city, forecast.to_dict())
        self._archive_report(city, forecast)
        return forecast, False

    @staticmethod
    def build_card(forecast: Forecast, advice) -> dict:
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
        }

    def _archive_report(self, city: str, forecast: Forecast) -> None:
        csv_bytes = self.weather.download_csv_report(forecast.place)
        if csv_bytes:
            self.agent.store_report(city, csv_bytes)

    # ----------------------------------------------------------------- ftp
    def list_archive(self, _request: dict) -> str:
        return self.agent.archive_listing()

    def read_archived_file(self, request: dict) -> str | bytes:
        filename = str(request.get("filename") or "")
        if not filename:
            return f"{ERROR_PREFIX}FTP_GET requires a filename."
        return self.agent.archived_file(filename)
