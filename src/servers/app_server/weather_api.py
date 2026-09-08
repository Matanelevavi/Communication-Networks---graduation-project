"""
Open-Meteo client.

Two calls make a forecast: geocoding turns a city name into coordinates, and
the forecast endpoint returns the next 24 hours for them.  A third call fetches
the same data as CSV for the archive.
"""
import logging
from dataclasses import dataclass

import requests

from src.config import HTTP_TIMEOUT
from src.servers.app_server.external_service import ExternalService, ServiceError

log = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

RAIN_THRESHOLD = 10          # percent, above which an hour is worth mentioning
FORECAST_HOURS = 24


@dataclass(frozen=True)
class Place:
    """A city resolved to coordinates."""
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Forecast:
    """The next 24 hours for one place, reduced to what the advice needs."""
    place: Place
    min_temp: float
    max_temp: float
    current_temp: float | None
    rain_summary: str


class WeatherService(ExternalService):
    """Fetches forecasts from Open-Meteo."""

    def fetch(self, city_name: str) -> Forecast:
        """Resolve a city and return its forecast.  Raises :class:`ServiceError`."""
        self.require_english(city_name, "the city name")
        place = self._geocode(city_name)
        return self._forecast(place)

    def _geocode(self, city_name: str) -> Place:
        # Parameters go to requests rather than into an f-string, so a name
        # such as "Tel Aviv" is percent encoded correctly.
        payload = self._get(GEOCODING_URL, {
            "name": city_name, "count": 1, "language": "en", "format": "json",
        })

        results = payload.get("results")
        if not results:
            raise ServiceError(f"City Error: '{city_name}' was not found.")

        first = results[0]
        try:
            return Place(first.get("name", city_name), first["latitude"], first["longitude"])
        except (KeyError, TypeError) as e:
            raise ServiceError("Data Error: the geocoding service returned "
                               "an unexpected answer.") from e

    def _forecast(self, place: Place) -> Forecast:
        payload = self._get(FORECAST_URL, {
            "latitude": place.latitude,
            "longitude": place.longitude,
            "current_weather": "true",
            "hourly": "temperature_2m,precipitation_probability",
            "timezone": "auto",
        })

        hourly = payload.get("hourly", {})
        temps = [t for t in hourly.get("temperature_2m", [])[:FORECAST_HOURS] if t is not None]
        if not temps:
            raise ServiceError(f"Data Error: no forecast is available for '{place.name}'.")

        return Forecast(
            place=place,
            min_temp=min(temps),
            max_temp=max(temps),
            current_temp=payload.get("current_weather", {}).get("temperature"),
            rain_summary=self._summarise_rain(
                hourly.get("precipitation_probability", [])[:FORECAST_HOURS],
                hourly.get("time", [])[:FORECAST_HOURS]),
        )

    @staticmethod
    def _summarise_rain(probabilities, times) -> str:
        """List the hours likely to be wet, or say that none are."""
        alerts = [
            f"{times[i].split('T')[1]} ({probabilities[i]}%)"
            for i in range(min(len(probabilities), len(times)))
            if probabilities[i] is not None and probabilities[i] > RAIN_THRESHOLD
        ]
        return ", ".join(alerts) if alerts else "No rain expected"

    # ------------------------------------------------------------------ csv
    def download_csv_report(self, place: Place) -> bytes | None:
        """The raw hourly data as CSV, for the archive.  ``None`` if unavailable."""
        try:
            log.info(f"Downloading CSV weather report for {place.name}")
            response = requests.get(FORECAST_URL, timeout=HTTP_TIMEOUT, params={
                "latitude": place.latitude,
                "longitude": place.longitude,
                "hourly": "temperature_2m,precipitation_probability",
                "format": "csv",
            })
        except requests.RequestException as e:
            log.error(f"HTTP download error: {e}")
            return None

        if response.status_code != 200:
            log.warning(f"Failed to download CSV, status {response.status_code}")
            return None

        log.info("CSV file downloaded successfully")
        return response.content

    # --------------------------------------------------------------- shared
    @staticmethod
    def _get(url: str, params: dict) -> dict:
        """One GET returning JSON, with network failures turned into ServiceError."""
        try:
            return requests.get(url, params=params, timeout=HTTP_TIMEOUT).json()
        except requests.RequestException as e:
            log.error(f"Weather service unreachable: {e}")
            raise ServiceError("Connection Error: Failed to reach weather service.") from e
        except ValueError as e:
            log.error(f"Weather service returned invalid JSON: {e}")
            raise ServiceError("Data Error: the weather service returned "
                               "an unexpected answer.") from e
