"""
The TCP half of the application server.

TCP hands us reliability, ordering and congestion control for free.  What it
does not hand us is message boundaries, so the only transport work left here is
deciding where one request ends.
"""
import json
import logging
import socket
import sys
import threading

from src.config import APP_ADD, ENCODING, MAX_REQUEST_SIZE, TCP_TIMEOUT
from src.servers.app_server.router import RequestRouter
from src.servers.app_server.wire import as_bytes

log = logging.getLogger(__name__)

Address = tuple[str, int]


class TcpListener:
    """Serves requests over TCP, one thread per connection."""

    def __init__(self, router: RequestRouter, address: Address = APP_ADD) -> None:
        self.router = router
        self.running = True

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(address)
        except OSError:
            log.error(f"TCP port {address[1]} is already in use, App Server is exiting")
            sys.exit(1)
        self.sock.listen(5)

    def serve_forever(self) -> None:
        log.info(f"TCP listening on {self.sock.getsockname()}")
        while self.running:
            try:
                connection, addr = self.sock.accept()
            except OSError:
                if self.running:
                    log.error("TCP accept failed")
                return

            log.info(f"TCP connection from {addr}")
            threading.Thread(target=self.handle, args=(connection, addr),
                             daemon=True).start()

    def handle(self, connection, addr: Address) -> None:
        try:
            connection.settimeout(TCP_TIMEOUT)
            answer = self.router.handle(self.read_request(connection))
            connection.sendall(as_bytes(answer))
        except Exception as e:
            log.error(f"TCP client {addr} error: {e}")
            self._try_send(connection, f"Error: {e}".encode(ENCODING))
        finally:
            connection.close()

    @staticmethod
    def read_request(connection) -> dict:
        """
        Read until a complete JSON object has arrived.

        TCP is a byte stream with no message boundaries: one ``recv`` is not
        guaranteed to return a whole request, so the parser decides when the
        message is finished.
        """
        buffer = b""
        while len(buffer) <= MAX_REQUEST_SIZE:
            if buffer:
                try:
                    return json.loads(buffer.decode(ENCODING))
                except (ValueError, UnicodeDecodeError):
                    pass                       # not a complete object yet
            chunk = connection.recv(4096)
            if not chunk:
                break
            buffer += chunk

        if len(buffer) > MAX_REQUEST_SIZE:
            raise ValueError(f"request larger than {MAX_REQUEST_SIZE} bytes")
        raise ValueError("connection closed before a complete request arrived")

    @staticmethod
    def _try_send(connection, payload: bytes) -> None:
        try:
            connection.sendall(payload)
        except OSError:
            pass

    def stop(self) -> None:
        self.running = False
        self._close()

    def _close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass
