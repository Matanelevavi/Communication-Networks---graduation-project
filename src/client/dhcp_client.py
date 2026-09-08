"""
The client half of DHCP.

Runs DORA over the shared control socket: Discover, Offer, Request,
Acknowledge.  Every step is retried on its own, so a single lost datagram
costs one round trip instead of the whole exchange.
"""
import logging
import socket
import time
from typing import Iterator

from src.config import (ACK_MSG, BACKUP_OFFER_DELAY, BUFF_SIZE, DHCP_ADD,
                        DHCP_BACKUP_ADD, DHCP_MAX_RETRIES, DHCP_RETRY_TIMEOUT,
                        DISCOVER_MSG, ENCODING, NAK_MSG, OFFER_MSG,
                        RELEASE_MSG, REQUEST_MSG)

log = logging.getLogger(__name__)

Address = tuple[str, int]


class DhcpClient:
    """Obtains and releases a leased address, using a caller supplied socket."""

    def __init__(self, sock) -> None:
        self.sock = sock
        self.my_ip: str | None = None
        self.server_addr: Address | None = None

    # ---------------------------------------------------------------- DORA
    def acquire(self) -> bool:
        """Run the exchange until an address is confirmed.  True on success."""
        log.info("Starting DHCP DORA")

        for attempt in range(1, DHCP_MAX_RETRIES + 1):
            log.info(f"Sending DISCOVER ({attempt}/{DHCP_MAX_RETRIES})")
            self.broadcast(DISCOVER_MSG)

            # Wide enough for the backup server to answer after its deliberate
            # delay, so a single attempt already covers a full failover.
            offered_ip, server_addr, rejection = self._wait_for_offer(
                time.time() + BACKUP_OFFER_DELAY + DHCP_RETRY_TIMEOUT)

            if rejection:
                log.error(f"DHCP rejected: {rejection}")
                return False
            if not offered_ip:
                continue

            log.info(f"Got OFFER {offered_ip} from port {server_addr[1]}")
            if self._confirm(offered_ip, server_addr):
                return True

        log.error("DHCP failed: no server completed the DORA exchange")
        return False

    def _confirm(self, offered_ip: str, server_addr: Address) -> bool:
        """Send REQUEST, with retries, and wait for the matching ACK."""
        # The chosen server's port travels inside the REQUEST, and the message
        # goes to both servers.  That is what the broadcast REQUEST achieves in
        # RFC 2131: the server that was not chosen learns it lost and releases
        # its reservation instead of leaking the address.
        request = f"{REQUEST_MSG}:{offered_ip}:{server_addr[1]}"

        for attempt in range(1, DHCP_MAX_RETRIES + 1):
            log.info(f"Sending REQUEST for {offered_ip} ({attempt}/{DHCP_MAX_RETRIES})")
            self.broadcast(request)

            granted, rejection = self._wait_for_ack(
                offered_ip, time.time() + DHCP_RETRY_TIMEOUT)

            if rejection:
                log.warning(f"DHCP server refused {offered_ip}: {rejection}")
                return False
            if granted:
                self.my_ip = offered_ip
                self.server_addr = server_addr
                log.info(f"DHCP successful, my IP is {self.my_ip}")
                return True

        log.warning(f"No ACK for {offered_ip}, restarting the exchange")
        return False

    def release(self) -> None:
        """Hand the address back to whichever server is holding it."""
        if not self.my_ip:
            return
        log.info(f"Releasing IP {self.my_ip}")
        self.broadcast(f"{RELEASE_MSG}:{self.my_ip}")
        self.my_ip = None

    # ------------------------------------------------------------- replies
    def _wait_for_offer(self, deadline: float) -> tuple[str | None, Address | None, str | None]:
        """Returns (offered ip, server address, rejection reason)."""
        refusals = set()

        for message, addr in self._messages_until(deadline):
            if message.startswith(OFFER_MSG):
                parts = message.split(":")
                if len(parts) >= 2:
                    return parts[1], addr, None

            elif message.startswith(NAK_MSG):
                refusals.add(addr)
                log.warning(f"Server on port {addr[1]} refused: {message}")
                if len(refusals) >= 2:
                    return None, None, "both DHCP servers reported an empty pool"

        return None, None, None

    def _wait_for_ack(self, offered_ip: str, deadline: float) -> tuple[bool, str | None]:
        """Returns (granted, rejection reason)."""
        for message, _addr in self._messages_until(deadline):
            if message.startswith(ACK_MSG) and message.split(":")[1] == offered_ip:
                return True, None
            if message.startswith(NAK_MSG):
                return False, message
            # anything else is a late offer from the server that lost

        return False, None

    def _messages_until(self, deadline: float) -> Iterator[tuple[str, Address]]:
        """Yield every datagram that arrives on the control socket before the deadline."""
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return
            try:
                self.sock.settimeout(remaining)
                data, addr = self.sock.recvfrom(BUFF_SIZE)
            except socket.timeout:
                return
            except ConnectionResetError:
                continue          # Windows reports an unreachable server this way
            except OSError as e:
                log.error(f"Control socket error: {e}")
                return

            yield data.decode(ENCODING, errors="replace"), addr

    def broadcast(self, text: str) -> None:
        """
        Send one control message to both DHCP servers.

        A real client would broadcast to 255.255.255.255; over loopback the two
        server addresses are known in advance, so the same reach is achieved
        with two unicast sends.
        """
        payload = text.encode(ENCODING)
        for target in (DHCP_ADD, DHCP_BACKUP_ADD):
            try:
                self.sock.sendto(payload, target)
            except OSError as e:
                log.warning(f"Could not reach {target}: {e}")
