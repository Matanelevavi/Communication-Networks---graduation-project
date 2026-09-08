"""
The two ways the client can reach the application server.

Both transports answer the same question — "send this request, give me the
answer" — so the rest of the client never branches on which one is in use.
The difference between them is exactly the point of the project:

* :class:`TcpTransport` delegates reliability, ordering and congestion control
  to the operating system, and only has to solve message framing, which TCP
  does *not* provide.
* :class:`RudpTransport` gets none of that for free and implements it in
  :mod:`src.rudp`.
"""
import logging
import socket
from abc import ABC, abstractmethod

from src.config import (APP_PORT, BUFF_SIZE, ENCODING, HANDSHAKE_ACK,
                        HANDSHAKE_PREFIX, MAX_RESPONSE_SIZE, MAX_RETRIES,
                        RUDP_TIMEOUT, TCP_TIMEOUT)
from src.rudp import RudpReceiver

log = logging.getLogger(__name__)

Address = tuple[str, int]


class Transport(ABC):
    """A request/response channel to the application server."""

    name: str = "abstract"

    def __init__(self, server_ip: str, port: int = APP_PORT) -> None:
        self.server = (server_ip, port)

    @abstractmethod
    def request(self, payload: str) -> str | bytes | None:
        """Send one request and return the answer, or ``None`` if it failed."""

    @staticmethod
    def decode(raw: bytes) -> str | bytes:
        """Text when the answer decodes as UTF-8, raw bytes otherwise."""
        try:
            return raw.decode(ENCODING)
        except UnicodeDecodeError:
            return raw

    def __repr__(self) -> str:
        return f"{type(self).__name__}(server={self.server})"


class TcpTransport(Transport):
    """Plain TCP: the kernel handles delivery, we handle message boundaries."""

    name = "TCP"

    def request(self, payload: str) -> str | bytes | None:
        log.info("[TCP] Connecting")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(TCP_TIMEOUT)
            sock.connect(self.server)
            sock.sendall(payload.encode(ENCODING))

            answer = self._read_until_closed(sock)
            log.info(f"[TCP] Received {len(answer)} bytes")
            return self.decode(answer)

        except OSError as e:
            log.error(f"[TCP] Error: {e}")
            return None
        finally:
            sock.close()

    @staticmethod
    def _read_until_closed(sock) -> bytes:
        """
        Read to end of stream.

        The server closes the connection when the answer is complete, so EOF is
        what delimits the message.  A single ``recv`` would silently truncate
        anything larger than one buffer.
        """
        received = bytearray()
        while len(received) <= MAX_RESPONSE_SIZE:
            chunk = sock.recv(BUFF_SIZE * 8)
            if not chunk:
                break
            received += chunk
        return bytes(received)


class RudpTransport(Transport):
    """Reliable UDP: a two step handshake, then a windowed chunked answer."""

    name = "RUDP"

    def request(self, payload: str) -> str | bytes | None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            if not self._handshake(sock, payload):
                log.error("[RUDP] Server unreachable")
                return None

            answer = RudpReceiver(sock).receive()
            return self.decode(answer) if answer is not None else None
        finally:
            sock.close()

    def _handshake(self, sock, payload: str) -> bool:
        """Retransmit the request until the server acknowledges it."""
        packet = f"{HANDSHAKE_PREFIX}{payload}".encode(ENCODING)
        sock.settimeout(RUDP_TIMEOUT)

        for attempt in range(1, MAX_RETRIES + 1):
            log.info(f"[RUDP] Sending request ({attempt}/{MAX_RETRIES})")
            try:
                sock.sendto(packet, self.server)
                reply, src = sock.recvfrom(BUFF_SIZE)
            except (socket.timeout, ConnectionResetError):
                continue
            except OSError as e:
                log.error(f"[RUDP] Socket error: {e}")
                return False

            if src == self.server and reply == HANDSHAKE_ACK:
                return True

        return False


#: every transport the GUI can offer, keyed by the name it shows the user
TRANSPORTS: dict[str, type[Transport]] = {
    TcpTransport.name: TcpTransport,
    RudpTransport.name: RudpTransport,
}


def create_transport(name: str, server_ip: str) -> Transport:
    """Build the transport the user picked; RUDP is the default."""
    return TRANSPORTS.get(name, RudpTransport)(server_ip)
