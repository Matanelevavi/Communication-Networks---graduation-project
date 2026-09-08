"""
The FTP style archive.

Two operations in the spirit of FTP, list and get, carried inside the same
JSON protocol as everything else rather than over a separate control channel.
"""
import logging

from src.servers.app_server.storage import FileStore

log = logging.getLogger(__name__)

BANNER = "--- WEATHERWEAR FTP ARCHIVE ---"
EMPTY = "FTP Directory is empty"
TABLE_WIDTH = 45


class FileArchive:
    """Lists and serves the saved forecasts and reports."""

    def __init__(self, store: FileStore) -> None:
        self.store = store

    def listing(self) -> str:
        """A human readable index of the archive."""
        files = self.store.list_files()
        if not files:
            return EMPTY

        rows = [f"- {name} (Size: {size / 1024:.1f} KB)" for name, size in files]
        log.info(f"Agent generated an FTP list of {len(files)} files")
        return "\n".join([BANNER, *rows]) + "\n"

    def read(self, filename: str) -> str | bytes:
        """
        One archived file.

        Read as bytes and decoded afterwards, so a genuinely binary file comes
        back as bytes instead of raising a decoding error.
        """
        raw = self.store.read_bytes(filename)
        if raw is None:
            log.warning(f"FTP Error: File '{filename}' not found")
            return f"Error: The file '{filename}' does not exist in the archive."

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            log.info(f"FTP served '{filename}' as binary, {len(raw)} bytes")
            return raw

        if filename.endswith(".csv"):
            return self.format_csv(filename, text)

        log.info(f"FTP read successful for {filename}")
        return text

    @staticmethod
    def format_csv(filename: str, content: str) -> str:
        """Render an Open-Meteo hourly CSV as an aligned text table."""
        rows = [f"Hourly Weather Data ({filename})", "=" * TABLE_WIDTH]

        for line in content.split("\n"):
            line = line.strip()
            if not line:
                continue

            if line.startswith("time"):
                rows.append("Date & Time         | Temp   | Rain %")
                rows.append("-" * TABLE_WIDTH)
            elif FileArchive._is_data_row(line):
                fields = line.split(",")
                if len(fields) >= 3:
                    rows.append(f"{fields[0].replace('T', '  ')} | "
                                f"{fields[1]}°C | {fields[2]}%")

        log.info(f"Parsed CSV into a table for {filename}")
        return "\n".join(rows) + "\n"

    @staticmethod
    def _is_data_row(line: str) -> bool:
        """A reading starts with an ISO date; the file also carries metadata rows."""
        return line[:2].isdigit() and "-" in line[:8]
