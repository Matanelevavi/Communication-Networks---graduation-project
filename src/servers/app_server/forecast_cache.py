"""
The daily forecast cache.

Saves a repeated request for the same city from calling the two external HTTP
services again.  Validity is decided by the modification *date* of the file:
a forecast written yesterday is stale even if it is only minutes old, because
"today's forecast" is a daily idea and not a rolling window.
"""
import logging
from datetime import date

from src.servers.app_server.storage import FileStore

log = logging.getLogger(__name__)

HEADER = "DAILY RECOMMENDATION\n\n"


class ForecastCache:
    """Stores and serves one forecast per city per day."""

    def __init__(self, store: FileStore) -> None:
        self.store = store

    @staticmethod
    def filename(city: str) -> str:
        return f"{city}_forecast.txt"

    def get(self, city: str) -> str | None:
        """Today's stored advice for a city, or ``None`` if there is none."""
        name = self.filename(city)
        modified = self.store.modified_at(name)
        if modified is None:
            return None

        if date.fromtimestamp(modified) != date.today():
            log.info(f"CACHE STALE: '{city}' was stored on an earlier day")
            return None

        raw = self.store.read_bytes(name)
        if raw is None:
            return None

        log.info(f"CACHE HIT: Served '{city}' from local storage")
        return raw.decode("utf-8", errors="replace").replace(HEADER, "", 1).strip()

    def put(self, city: str, advice: str) -> bool:
        """Store today's advice for a city."""
        return self.store.write_text(self.filename(city), HEADER + advice)
