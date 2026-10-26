"""
The file agent.

Composes the two things the application server does with the data directory:
a weather cache in front of the external services, and the archive the client can
browse.  Both sit on the same :class:`FileStore`, so they share one lock and
one containment rule.
"""
import logging

from src.config import DATA_DIR
from src.servers.app_server.file_archive import FileArchive
from src.servers.app_server.forecast_cache import ForecastCache, city_key
from src.servers.app_server.storage import FileStore

log = logging.getLogger(__name__)

REPORT_SUFFIX = "_full_report.csv"


class FileAgent:
    """The application server's view of local storage, in the caller's terms."""

    def __init__(self, data_folder: str = DATA_DIR) -> None:
        self.store = FileStore(data_folder)
        self.cache = ForecastCache(self.store)
        self.archive = FileArchive(self.store)
        log.info("Agent initialized and data folder is ready")

    @property
    def data_folder(self) -> str:
        return self.store.folder

    # -------------------------------------------------------------- cache
    def cached_forecast(self, city: str) -> dict | None:
        """A recent forecast for a city, as stored data, or ``None``."""
        return self.cache.get(city)

    def store_forecast(self, city: str, forecast: dict) -> bool:
        """Store the weather for a city. Never the advice, which is per family."""
        return self.cache.put(city, forecast)

    def store_report(self, city: str, csv_bytes: bytes) -> bool:
        """Keep the raw hourly data alongside the forecast, for the archive."""
        return self.store.write_bytes(f"{city_key(city)}{REPORT_SUFFIX}", csv_bytes)

    # ---------------------------------------------------------------- ftp
    def archive_listing(self) -> str:
        return self.archive.listing()

    def archived_file(self, filename: str) -> str | bytes:
        return self.archive.read(filename)
