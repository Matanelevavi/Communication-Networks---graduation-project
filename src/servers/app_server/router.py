"""
Request routing.

Turns a decoded request into an answer, and knows nothing about how it arrived.
That is what lets the same code serve a TCP connection and an RUDP transfer:
both listeners hand a dictionary here and send back whatever comes out.
"""
import logging

from src.servers.app_server.agent import FileAgent
from src.servers.app_server.ai_advisor import AiAdvisor
from src.servers.app_server.external_service import ServiceError
from src.servers.app_server.weather_api import WeatherService

log = logging.getLogger(__name__)

UNKNOWN_ACTION = "Error: Unknown action requested."


class RequestRouter:
    """Dispatches one request to the right piece of application logic."""

    def __init__(self,
                 weather: WeatherService | None = None,
                 advisor: AiAdvisor | None = None,
                 agent: FileAgent | None = None) -> None:
        # Injected rather than constructed inline, so a test can substitute any
        # of the three without touching the network or the file system.
        self.weather = weather or WeatherService()
        self.advisor = advisor or AiAdvisor()
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
            return cached

        forecast = self.weather.fetch(city)
        advice = self.advisor.recommend(forecast, request.get("profiles"))

        # Only reached when both services succeeded, so nothing but a real
        # recommendation can ever be written to disk.
        self.agent.store_forecast(safe_city, advice)
        self._archive_report(safe_city, forecast)
        return advice

    def _archive_report(self, safe_city: str, forecast) -> None:
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
