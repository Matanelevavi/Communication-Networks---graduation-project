"""
The network client.

Composes the three pieces a host needs to reach the service — a DHCP client, a
DNS resolver and a transport — over one shared UDP control socket.  The
interactive loop that drives it lives in :mod:`src.client.session`.
"""
import logging
import socket

from src.client.dhcp_client import DhcpClient
from src.client.dns_resolver import DnsResolver
from src.client.transport import Transport, create_transport
from src.config import (APP_PORT, BUFF_SIZE, CLIENT_ADD, CLIENT_PORT,
                        ENCODING, FIN_ACK_MSG, FIN_MSG, HOST, MY_DOMAIN,
                        TIMEOUT)

log = logging.getLogger(__name__)


class NetworkClient:
    """Everything the client does on the network, from DORA to teardown."""

    def __init__(self) -> None:
        self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._bind_control_socket()
        self.control_socket.settimeout(TIMEOUT)

        self.dhcp = DhcpClient(self.control_socket)
        self.dns = DnsResolver(self.control_socket)
        self.app_server_ip: str | None = None

    def _bind_control_socket(self) -> None:
        """
        Bind to the documented client port, 8068.

        Falling back to an ephemeral port keeps a second client, used to
        demonstrate concurrency, from failing outright when 8068 is taken.
        """
        try:
            self.control_socket.bind(CLIENT_ADD)
            log.info(f"Client control socket bound to {CLIENT_ADD}")
        except OSError:
            self.control_socket.bind((HOST, 0))
            log.warning(f"Port {CLIENT_PORT} is busy, using ephemeral port "
                        f"{self.control_socket.getsockname()[1]} instead")

    # ------------------------------------------------------------- joining
    @property
    def my_ip(self) -> str | None:
        return self.dhcp.my_ip

    def connect(self, domain: str = MY_DOMAIN) -> bool:
        """Get an address, then resolve the application server. True if both worked."""
        if not self.dhcp.acquire():
            return False

        self.app_server_ip = self.dns.resolve(domain)
        if not self.app_server_ip:
            log.error(f"Could not resolve {domain}")
            return False

        return True

    # ------------------------------------------------------------ requests
    def transport_for(self, protocol: str) -> Transport:
        """The transport object for a protocol name, ready to send a request."""
        return create_transport(protocol, self.app_server_ip)

    def request(self, payload: str, protocol: str) -> str | bytes | None:
        """Send one request over the protocol the user chose."""
        return self.transport_for(protocol).request(payload)

    # ------------------------------------------------------------ teardown
    def close(self) -> None:
        """Say goodbye to the application server, then give the address back."""
        try:
            self._say_goodbye()
            self.dhcp.release()
        except OSError as e:
            log.warning(f"[TEARDOWN] Error while closing: {e}")
        finally:
            self.control_socket.close()

    def _say_goodbye(self) -> None:
        """
        Application level FIN / FIN-ACK.

        It always travels over UDP, even after TCP requests: every TCP request
        opens and closes its own connection, so there is no lasting session for
        the operating system to tear down.
        """
        if not self.app_server_ip:
            return

        log.info("[TEARDOWN] Sending FIN to the server")
        self.control_socket.settimeout(2.0)
        self.control_socket.sendto(FIN_MSG, (self.app_server_ip, APP_PORT))
        try:
            reply, _ = self.control_socket.recvfrom(BUFF_SIZE)
            if reply == FIN_ACK_MSG:
                log.info("[TEARDOWN] Received FIN-ACK, connection closed cleanly")
        except socket.timeout:
            log.warning("[TEARDOWN] No FIN-ACK, forcing the close")


if __name__ == "__main__":
    from src.client.session import main

    main()
