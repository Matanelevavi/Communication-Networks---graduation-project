"""
The RUDP half of the application server.

The well known port carries only handshakes and FINs.  Every answer leaves on
a socket of its own, so the acknowledgements coming back for a transfer can
never be mistaken for a new request arriving.
"""
import json
import logging
import random
import socket
import sys
import threading

from src.config import (APP_ADD, ENCODING, FIN_ACK_MSG, HANDSHAKE_ACK,
                        HANDSHAKE_PREFIX, LOSS_RATE, MAX_REQUEST_SIZE,
                        MAX_RESPONSE_SIZE, SIMULATE_LOSS)
from src.rudp import RudpSender
from src.servers.app_server.router import RequestRouter
from src.servers.app_server.wire import as_bytes

log = logging.getLogger(__name__)

Address = tuple[str, int]


class RudpListener:
    """
    Serves requests over RUDP.

    The well known port only carries handshakes and FINs.  Each answer goes out
    on a socket of its own, so the data acknowledgements coming back can never
    be confused with a new request arriving.
    """

    def __init__(self, router: RequestRouter, address: Address = APP_ADD) -> None:
        self.router = router
        self.running = True

        # One transfer per client at a time.  The lock states that invariant
        # instead of leaning on the atomicity of set operations under the GIL.
        self.active_transfers: set[Address] = set()
        self.lock = threading.Lock()

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind(address)
        except OSError:
            log.error(f"UDP port {address[1]} is already in use, App Server is exiting")
            sys.exit(1)

    def serve_forever(self) -> None:
        log.info(f"RUDP listening on {self.sock.getsockname()}")
        while self.running:
            message = self._receive()
            if message is None:
                continue
            text, addr = message

            if text.startswith("FIN"):
                log.info(f"Client {addr} is closing the session (FIN)")
                self.sock.sendto(FIN_ACK_MSG, addr)
            elif text.startswith(HANDSHAKE_PREFIX):
                self.accept_request(text, addr)

    def _receive(self) -> tuple[str, Address] | None:
        try:
            data, addr = self.sock.recvfrom(MAX_REQUEST_SIZE)
            return data.decode(ENCODING), addr
        except ConnectionResetError:
            return None            # Windows ICMP Port Unreachable, ignore
        except UnicodeDecodeError:
            log.warning("Dropped a non UTF-8 datagram")
            return None
        except OSError:
            if self.running:
                log.error("UDP receive failed")
            self.running = False
            return None

    def accept_request(self, message: str, addr: Address) -> None:
        """Validate a handshake and start the transfer it asks for."""
        if SIMULATE_LOSS and random.random() < LOSS_RATE:
            log.warning(f"Simulated drop of the request from {addr}")
            return

        try:
            request = json.loads(message.split("|", 1)[1])
        except (IndexError, ValueError) as e:
            # Parsed before the client is marked active: marking it first would
            # leave a bad request blocking that client from ever trying again.
            log.warning(f"Malformed request from {addr}: {e}")
            return

        # Acknowledged even when a transfer is already running: a repeated
        # handshake means the client never saw the first ACK, and it must not
        # start a second copy of the same transfer.
        self.sock.sendto(HANDSHAKE_ACK, addr)

        with self.lock:
            if addr in self.active_transfers:
                log.info(f"Re-acknowledged a duplicate request from {addr}")
                return
            self.active_transfers.add(addr)

        threading.Thread(target=self.answer, args=(request, addr), daemon=True).start()

    def answer(self, request: dict, addr: Address) -> None:
        """Produce the answer and send it back over its own socket."""
        transfer_sock = None
        try:
            payload = self._within_limit(self.router.handle(request), addr)
            transfer_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            RudpSender(transfer_sock).send(payload, addr)
        except Exception as e:
            log.error(f"Transfer thread for {addr} failed: {e}")
        finally:
            if transfer_sock is not None:
                transfer_sock.close()
            with self.lock:
                self.active_transfers.discard(addr)

    @staticmethod
    def _within_limit(answer, addr: Address):
        size = len(as_bytes(answer))
        if size <= MAX_RESPONSE_SIZE:
            return answer

        log.warning(f"Response for {addr} is {size} bytes, "
                    f"over the {MAX_RESPONSE_SIZE} byte limit")
        return (f"Error: the requested content is {size // 1024} KB, larger than "
                f"the {MAX_RESPONSE_SIZE // 1024} KB transfer limit.")

    def stop(self) -> None:
        self.running = False
        try:
            self.sock.close()
        except OSError:
            pass
