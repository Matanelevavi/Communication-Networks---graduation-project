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
import time

from src.config import (APP_ADD, ENCODING, MAX_REQUEST_SIZE,
                        MAX_TCP_CONNECTIONS, REQUEST_READ_DEADLINE, TCP_TIMEOUT)
from src.servers.app_server.router import RequestRouter
from src.servers.app_server.wire import as_bytes

log = logging.getLogger(__name__)

Address = tuple[str, int]


class SilentConnection(ValueError):
    """The peer connected and closed without sending a single byte."""


class TcpListener:
    """Serves requests over TCP, one thread per connection."""

    def __init__(self, router: RequestRouter, address: Address = APP_ADD) -> None:
        self.router = router
        self.running = True
        self.slots = threading.BoundedSemaphore(MAX_TCP_CONNECTIONS)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(address)
        except OSError:
            log.error(f"TCP port {address[1]} is already in use, App Server is exiting")
            sys.exit(1)
        self.sock.listen(128)

    def serve_forever(self) -> None:
        log.info(f"TCP listening on {self.sock.getsockname()}")
        while self.running:
            try:
                connection, addr = self.sock.accept()
            except OSError:
                if self.running:
                    log.error("TCP accept failed")
                return

            # A thread per connection is only safe with a ceiling: without one,
            # a few thousand idle connections are a few thousand threads.
            if not self.slots.acquire(blocking=False):
                log.warning(f"Refusing {addr}: {MAX_TCP_CONNECTIONS} connections already open")
                self._try_send(connection, b"Error: the server is busy, try again shortly.")
                connection.close()
                continue

            log.info(f"TCP connection from {addr}")
            threading.Thread(target=self._serve, args=(connection, addr),
                             daemon=True).start()

    def _serve(self, connection, addr: Address) -> None:
        try:
            self.handle(connection, addr)
        finally:
            self.slots.release()

    def handle(self, connection, addr: Address) -> None:
        try:
            connection.settimeout(TCP_TIMEOUT)
            answer = self.router.handle(self.read_request(connection))
            connection.sendall(as_bytes(answer))
        except SilentConnection:
            # A health check or port scan: it connected and left without a
            # word. Nothing went wrong, so it is not logged as an error.
            log.info(f"TCP connection from {addr} closed without a request")
        except ValueError as e:
            # Raised by read_request with a message written for the client.
            log.warning(f"TCP client {addr} sent a bad request: {e}")
            self._try_send(connection, f"Error: {e}".encode(ENCODING))
        except Exception as e:
            # Anything else is ours: the details go to the log, not to the peer.
            log.error(f"TCP client {addr} error: {e!r}")
            self._try_send(connection, b"Error: the server could not handle the request.")
        finally:
            connection.close()

    @staticmethod
    def read_request(connection) -> dict:
        """
        Read until a complete JSON object has arrived.

        TCP is a byte stream with no message boundaries: one ``recv`` is not
        guaranteed to return a whole request, so the parser decides when the
        message is finished.

        The whole request has ``REQUEST_READ_DEADLINE`` seconds, not each read:
        a client that sends one byte every few seconds would otherwise hold its
        thread for as long as it likes.
        """
        buffer = b""
        deadline = time.monotonic() + REQUEST_READ_DEADLINE
        while len(buffer) <= MAX_REQUEST_SIZE:
            if buffer:
                try:
                    return json.loads(buffer.decode(ENCODING))
                except (ValueError, UnicodeDecodeError):
                    pass                       # not a complete object yet
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("the request took too long to arrive")
            connection.settimeout(remaining)
            chunk = connection.recv(4096)
            if not chunk:
                break
            buffer += chunk

        if len(buffer) > MAX_REQUEST_SIZE:
            raise ValueError(f"request larger than {MAX_REQUEST_SIZE} bytes")
        if not buffer:
            raise SilentConnection()
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
