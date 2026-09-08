"""
The daily forecast cache.

Saves a repeated request for the same city from calling the external services
again. Validity is decided by the modification *date* of the file: a forecast
written yesterday is stale even if it is only minutes old, because "today's
forecast" is a daily idea and not a rolling window.

The whole answer is stored, not just the advice, so a cache hit can rebuild the
same card the first request produced.
"""
import json
import logging
from datetime import date

from src.servers.app_server.storage import FileStore

log = logging.getLogger(__name__)

SUFFIX = "_forecast.json"


class ForecastCache:
    """Stores and serves one forecast per city per day."""

    def __init__(self, store: FileStore) -> None:
        self.store = store

    @staticmethod
    def filename(city: str) -> str:
        return f"{city}{SUFFIX}"

    def get(self, city: str) -> dict | None:
        """Today's stored forecast for a city, or ``None`` if there is none."""
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

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            log.warning(f"Discarding an unreadable cache entry for '{city}': {e}")
            return None

        log.info(f"CACHE HIT: Served '{city}' from local storage")
        return payload

    def put(self, city: str, payload: dict) -> bool:
        """Store today's forecast for a city."""
        return self.store.write_text(
            self.filename(city), json.dumps(payload, indent=2, ensure_ascii=False))
