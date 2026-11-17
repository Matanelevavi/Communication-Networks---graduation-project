"""
Two weather providers behind one interface.

Open-Meteo answers first. If it cannot (throttled, erroring, unreachable), the
same place is asked of MET Norway, so a limit on a shared address costs the
visitor nothing but a credit line saying which provider the weather came from.

What does *not* fall back: a city that does not exist. That is an answer, not an
outage, and no second provider should be asked to second-guess it. Finding a
place and searching for one stay with Open-Meteo's geocoder, which has a quota
of its own and is not what gets throttled.
"""
import logging

from src.servers.app_server.external_service import ProviderUnavailable, ServiceError
from src.servers.app_server.met_norway import MetNorway
from src.servers.app_server.weather_api import Forecast, Place, WeatherService

log = logging.getLogger(__name__)


class FailoverWeather:
    """The interface the router uses: ``fetch``, ``fetch_at`` and ``search``."""

    def __init__(self, primary: WeatherService | None = None,
                 fallback: MetNorway | None = None) -> None:
        self.primary = primary or WeatherService()
        self.fallback = fallback or MetNorway()

    def fetch(self, city_name: str) -> Forecast:
        return self._forecast(self.primary.locate(city_name))

    def fetch_at(self, name: str, latitude: float, longitude: float,
                 tz: str | None = None) -> Forecast:
        return self._forecast(Place(name, latitude, longitude, tz))

    def search(self, query: str) -> list[dict]:
        return self.primary.search(query)

    def _forecast(self, place: Place) -> Forecast:
        try:
            return self.primary.forecast_for(place)
        except ProviderUnavailable as unavailable:
            log.warning(f"{type(unavailable).__name__} from the first provider, "
                        f"asking {self.fallback.__class__.__name__}")
            try:
                return self.fallback.forecast_for(place)
            except ServiceError as also_failed:
                log.error(f"The fallback failed as well: {also_failed}")
                # The first provider's explanation is the one worth showing: it
                # says what happened to the request the visitor actually made.
                raise unavailable from also_failed
