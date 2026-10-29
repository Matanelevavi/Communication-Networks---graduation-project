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

# A file whose name starts with this is somebody's shared position. It is kept
# for the cache, and the archive neither lists it nor serves it.
PRIVATE_PREFIX = "private_"

# NUL ends a path in C, a colon names a drive or a data stream on Windows, and
# control characters have no place in a file name.
FORBIDDEN = {chr(c) for c in range(32)} | {":", "\x7f"}


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
        # Both separators are treated as separators on every platform: on Linux
        # a backslash is an ordinary character to ``basename``, and a name
        # that is harmless there is a traversal on a Windows machine.
        filename = os.path.basename(filename.replace("\\", "/"))
        if filename in ("", ".", "..") or any(c in filename for c in FORBIDDEN):
            return None

        root = os.path.realpath(self.folder)
        try:
            path = os.path.realpath(os.path.join(self.folder, filename))
            contained = os.path.commonpath([root, path]) == root
        except (ValueError, OSError):
            contained = False                # a name the platform cannot place at all
        if not contained:
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

        Directories, dotfiles and private files are left out: none of them is
        content a client asked to be able to download.
        """
        try:
            with self.lock:
                names = sorted(name for name in os.listdir(self.folder)
                               if not name.startswith((".", PRIVATE_PREFIX))
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
