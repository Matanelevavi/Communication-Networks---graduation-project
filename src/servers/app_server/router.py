"""
Request routing.

Turns a decoded request into an answer, and knows nothing about how it arrived.
That is what lets the same code serve a TCP connection and an RUDP transfer:
both listeners hand a dictionary here and send back whatever comes out.

A forecast answer is a JSON object rather than a paragraph, so the client can
lay the numbers out itself instead of parsing prose.
"""
import json
import logging

from src.servers.app_server.advisor import ClothingAdvisor
from src.servers.app_server.agent import FileAgent
from src.servers.app_server.external_service import ServiceError
from src.servers.app_server.weather_api import Forecast, WeatherService

log = logging.getLogger(__name__)

UNKNOWN_ACTION = "Error: Unknown action requested."
FORECAST_KIND = "forecast"


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
        action = request.get("action", "FORECAST")
        handler = self.actions.get(action)
        if handler is None:
            return UNKNOWN_ACTION

        try:
            return handler(request)
        except ServiceError as e:
            # An expected, explainable failure: show it, but never cache it.
            log.warning(f"{action} failed: {e}")
            return str(e)

    # ------------------------------------------------------------ forecast
    def forecast(self, request: dict) -> str:
        city = str(request.get("city") or "").strip()
        if not city:
            return "Error: FORECAST requires a city name."

        safe_city = city.replace(" ", "_")

        cached = self.agent.cached_forecast(safe_city)
        if cached:
            return json.dumps({**cached, "cached": True})

        forecast = self.weather.fetch(city)
        advice = self.advisor.recommend(forecast, request.get("profiles"))
        card = self.build_card(forecast, advice)

        # Only reached when the weather lookup succeeded and an advisor
        # produced something, so nothing but a real answer is written to disk.
        self.agent.store_forecast(safe_city, card)
        self._archive_report(safe_city, forecast)
        return json.dumps({**card, "cached": False})

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

    def _archive_report(self, safe_city: str, forecast: Forecast) -> None:
        csv_bytes = self.weather.download_csv_report(forecast.place)
        if csv_bytes:
            self.agent.store_report(safe_city, csv_bytes)

    # ----------------------------------------------------------------- ftp
    def list_archive(self, _request: dict) -> str:
        return self.agent.archive_listing()

    def read_archived_file(self, request: dict) -> str | bytes:
        filename = request.get("filename", "")
        if not filename:
            return "Error: FTP_GET requires a filename."
        return self.agent.archived_file(filename)
