"""
DHCP server.

Owns the socket and the message handling; the address bookkeeping lives in
:class:`~src.servers.address_pool.AddressPool`.  The backup server is this same
class with a different address, a different pool and a delay before it answers.
"""
import logging
import socket
import sys
import threading

from src.config import (ACK_MSG, BUFF_SIZE, DHCP_ADD, DISCOVER_MSG, ENCODING,
                        LEASE_SWEEP_INTERVAL, NAK_MSG, OFFER_MSG, POOL_IP,
                        RELEASE_MSG, REQUEST_MSG, setup_logging)
from src.servers.address_pool import AddressPool

log = logging.getLogger(__name__)

Client = tuple[str, int]


class DHCPServer:
    """Serves DORA over UDP unicast."""

    def __init__(self,
                 address: tuple[str, int] = DHCP_ADD,
                 pool=POOL_IP,
                 offer_delay: float = 0.0,
                 name: str = "DHCP") -> None:
        self.address = address
        self.name = name
        self.offer_delay = offer_delay
        self.pool = AddressPool(pool)
        self.running = True

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind(self.address)
        except OSError:
            log.error(f"Port {self.address[1]} is already in use, {self.name} is exiting")
            sys.exit(1)

    # ----------------------------------------------------------- main loop
    def start(self) -> None:
        log.info(f"{self.name} listening on {self.address} "
                 f"with {self.pool.available} addresses")
        # The timeout makes the loop wake up even when nothing arrives, which
        # is what gives expired reservations and leases a chance to be swept.
        self.sock.settimeout(LEASE_SWEEP_INTERVAL)

        try:
            while self.running:
                self.pool.reclaim_expired()
                message = self._receive()
                if message:
                    self.handle(*message)
        except KeyboardInterrupt:
            log.info(f"Turn off {self.name}")
        finally:
            self.running = False
            self.sock.close()

    def _receive(self) -> tuple[str, Client] | None:
        try:
            data, client = self.sock.recvfrom(BUFF_SIZE)
            return data.decode(ENCODING), client
        except socket.timeout:
            return None
        except ConnectionResetError:
            return None          # Windows reports an unreachable destination here
        except UnicodeDecodeError:
            log.warning("Dropped a non UTF-8 datagram")
            return None

    def handle(self, message: str, client: Client) -> None:
        """Dispatch one message to the step of DORA it belongs to."""
        if message == DISCOVER_MSG:
            self.on_discover(client)
        elif message.startswith(REQUEST_MSG):
            self.on_request(message, client)
        elif message.startswith(RELEASE_MSG):
            self.on_release(message, client)
        else:
            log.warning(f"Unknown message from {client}: {message[:40]!r}")

    # ------------------------------------------------------------ discover
    def on_discover(self, client: Client) -> None:
        # A DISCOVER opens a new exchange, so any record of this client having
        # picked another server belongs to the previous one.
        self.pool.forget_decline(client)

        if self.offer_delay > 0:
            # Answering late must not block the loop, or a second client would
            # queue behind the delay of the first.
            timer = threading.Timer(self.offer_delay, self.send_offer, args=(client,))
            timer.daemon = True
            timer.start()
        else:
            self.send_offer(client)

    def send_offer(self, client: Client) -> None:
        if not self.running:
            return

        if self.pool.has_declined(client):
            log.info(f"Not offering to {client}, it already accepted another server")
            return

        already_held = self.pool.held_by(client)
        ip = self.pool.reserve(client)

        if ip is None:
            log.warning(f"IP pool exhausted, rejecting {client}")
            self.send(f"{NAK_MSG}:No IPs available", client)
            return

        if already_held:
            log.info(f"Repeating existing offer {ip} to {client}")
        else:
            log.info(f"Offered {ip} to {client} ({self.pool.available} free)")
        self.send(f"{OFFER_MSG}:{ip}", client)

    # ------------------------------------------------------------- request
    def on_request(self, message: str, client: Client) -> None:
        parts = message.split(":")
        if len(parts) < 2:
            log.warning(f"Malformed REQUEST from {client}: {message[:40]!r}")
            return

        wanted_ip = parts[1]
        chosen_port = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else None

        # The client echoes the port of the server whose offer it accepted, the
        # role the "server identifier" option plays in RFC 2131.  A server that
        # was not chosen frees its reservation instead of holding the address.
        if chosen_port is not None and chosen_port != self.address[1]:
            self.decline(client, chosen_port)
            return

        if self.pool.commit(client, wanted_ip):
            self.send(f"{ACK_MSG}:{wanted_ip}", client)
            log.info(f"ACK sent for {wanted_ip} to {client}, "
                     f"IPs remaining: {self.pool.available}")
        else:
            self.send(f"{NAK_MSG}:{wanted_ip} was never offered to you", client)
            log.warning(f"NAK sent to {client} for unoffered address {wanted_ip}")

    def decline(self, client: Client, chosen_port: int) -> None:
        self.pool.decline(client)
        withdrawn = self.pool.withdraw(client)
        if withdrawn:
            log.info(f"Withdrew offer {withdrawn} for {client}, it chose the server "
                     f"on port {chosen_port}. IPs remaining: {self.pool.available}")

    # ------------------------------------------------------------- release
    def on_release(self, message: str, client: Client) -> None:
        parts = message.split(":")
        if len(parts) < 2:
            return
        released_ip = parts[1]

        if self.pool.release(client, released_ip):
            log.info(f"Released {released_ip} from {client}, "
                     f"IPs remaining: {self.pool.available}")
            return

        # It may only have been reserved: a RELEASE that arrives before the
        # client ever sent a REQUEST still has to clean up.
        withdrawn = self.pool.withdraw(client)
        if withdrawn:
            log.info(f"Withdrew unclaimed offer {withdrawn} for {client}, "
                     f"IPs remaining: {self.pool.available}")

    # ---------------------------------------------------------------- send
    def send(self, text: str, client: Client) -> None:
        try:
            self.sock.sendto(text.encode(ENCODING), client)
        except OSError as e:
            log.warning(f"Could not reply to {client}: {e}")


if __name__ == "__main__":
    setup_logging("DHCP")
    DHCPServer().start()
