"""
The forecast cache.

Saves a repeated request for the same city from calling Open-Meteo again.

Only the *weather* is cached, never the advice. The advice is written for the
family in one particular request, so a cached copy would hand one user's
recommendation, names included, to the next person who asked about the same
city. Writing it again from cached numbers is instant for the local advisor.

An entry is valid for ``FORECAST_CACHE_TTL`` seconds after it was written. A
whole day was too long: the "right now" temperature stayed frozen at whatever
it was in the morning.
"""
import json
import logging
import re
import time

from src.config import FORECAST_CACHE_TTL
from src.servers.app_server.storage import PRIVATE_PREFIX, FileStore  # noqa: F401 - re-exported

log = logging.getLogger(__name__)

SUFFIX = "_forecast.json"

# Anything that is not a letter or a digit, in any script, becomes a separator.
_SEPARATORS = re.compile(r"[^\w]+|_+", re.UNICODE)


def city_key(city: str) -> str:
    """
    The name a city is stored under.

    Case and spacing are folded so "ariel", "Ariel" and " ARIEL " share one
    entry, and punctuation is dropped so a name can never form a path.
    """
    return _SEPARATORS.sub("_", city.strip().casefold()).strip("_")


class ForecastCache:
    """Stores and serves recent forecasts, one per city."""

    def __init__(self, store: FileStore, ttl: float = FORECAST_CACHE_TTL) -> None:
        self.store = store
        self.ttl = ttl

    @staticmethod
    def filename(city: str) -> str:
        return f"{city_key(city)}{SUFFIX}"

    def age(self, city: str) -> float | None:
        """Seconds since this city's forecast was stored, or ``None`` if there is none."""
        modified = self.store.modified_at(self.filename(city))
        return None if modified is None else max(0.0, time.time() - modified)

    def get(self, city: str, max_age: float | None = None) -> dict | None:
        """
        A recent forecast for a city, or ``None`` if there is none.

        ``max_age`` widens what counts as recent. The normal answer is the one
        half an hour old; a caller whose provider has just failed asks for the
        last one it ever got, within a limit, and says so to the user.
        """
        name = self.filename(city)
        age = self.age(city)
        if age is None:
            return None

        limit = self.ttl if max_age is None else max_age
        if age > limit:
            log.info(f"CACHE STALE: '{city}' is older than {limit:.0f}s")
            return None

        raw = self.store.read_bytes(name)
        if raw is None:
            return None

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            log.warning(f"Discarding an unreadable cache entry for '{city}': {e}")
            return None

        if not isinstance(payload, dict):
            return None

        log.info(f"CACHE HIT: Served '{city}' from local storage")
        return payload

    def put(self, city: str, payload: dict) -> bool:
        """Store a forecast for a city."""
        return self.store.write_text(
            self.filename(city), json.dumps(payload, indent=2, ensure_ascii=False))
