"""
Guarded access to the data directory.

Everything that touches a file goes through here, so two rules hold everywhere
at once: a client supplied name can never escape the directory, and a reader
can never observe a file that is halfway through being rewritten.
"""
import logging
import os
import threading

log = logging.getLogger(__name__)


class FileStore:
    """One directory, one lock, and a safe way to name a file inside it."""

    def __init__(self, folder: str) -> None:
        self.folder = folder
        # Reentrant, so a method that already holds the lock can call another.
        self.lock = threading.RLock()
        os.makedirs(self.folder, exist_ok=True)

    def resolve(self, filename: str) -> str | None:
        """
        Turn a requested name into a path inside the directory, or ``None``.

        ``basename`` strips any directory component, so ``../../etc/passwd``
        becomes ``passwd``.  The containment check is the second line of
        defence: the resolved path must still sit inside the folder.
        """
        filename = os.path.basename(filename)
        if not filename:
            return None

        path = os.path.realpath(os.path.join(self.folder, filename))
        root = os.path.realpath(self.folder)
        if os.path.commonpath([root, path]) != root:
            log.warning(f"Refused a path traversal attempt: {filename!r}")
            return None
        return path

    # ------------------------------------------------------------- reading
    def read_bytes(self, filename: str) -> bytes | None:
        """The file's contents, or ``None`` if it is missing or unreadable."""
        path = self.resolve(filename)
        if not path:
            return None
        try:
            with self.lock:
                if not os.path.isfile(path):
                    return None
                with open(path, "rb") as f:
                    return f.read()
        except OSError as e:
            log.error(f"Read error on {filename}: {e}")
            return None

    def modified_at(self, filename: str) -> float | None:
        path = self.resolve(filename)
        if not path:
            return None
        with self.lock:
            return os.path.getmtime(path) if os.path.isfile(path) else None

    def list_files(self) -> list[tuple[str, int]]:
        """
        Every real file in the directory as (name, size), sorted by name.

        Directories and dotfiles are left out: neither is content a client
        asked to be able to download.
        """
        try:
            with self.lock:
                names = sorted(name for name in os.listdir(self.folder)
                               if not name.startswith(".")
                               and os.path.isfile(os.path.join(self.folder, name)))
                return [(name, os.path.getsize(os.path.join(self.folder, name)))
                        for name in names]
        except OSError as e:
            log.error(f"Listing error: {e}")
            return []

    # ------------------------------------------------------------- writing
    def write_bytes(self, filename: str, data: bytes) -> bool:
        path = self.resolve(filename)
        if not path:
            return False
        try:
            with self.lock:
                with open(path, "wb") as f:
                    f.write(data)
            log.info(f"Saved {len(data)} bytes to {path}")
            return True
        except OSError as e:
            log.error(f"Write error on {filename}: {e}")
            return False

    def write_text(self, filename: str, text: str) -> bool:
        return self.write_bytes(filename, text.encode("utf-8"))
