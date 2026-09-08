"""
The file agent.

Composes the two things the application server does with the data directory:
a daily cache in front of the external services, and the archive the client can
browse.  Both sit on the same :class:`FileStore`, so they share one lock and
one containment rule.
"""
import logging

from src.config import DATA_DIR
from src.servers.app_server.file_archive import FileArchive
from src.servers.app_server.forecast_cache import ForecastCache
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
    def cached_forecast(self, city: str) -> str | None:
        """Today's stored advice for a city, or ``None``."""
        return self.cache.get(city)

    def store_forecast(self, city: str, advice: str) -> bool:
        return self.cache.put(city, advice)

    def store_report(self, city: str, csv_bytes: bytes) -> bool:
        """Keep the raw hourly data alongside the advice, for the archive."""
        return self.store.write_bytes(f"{city}{REPORT_SUFFIX}", csv_bytes)

    # ---------------------------------------------------------------- ftp
    def archive_listing(self) -> str:
        return self.archive.listing()

    def archived_file(self, filename: str) -> str | bytes:
        return self.archive.read(filename)
