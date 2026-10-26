"""
The website's own place on the simulated network.

The gateway runs DORA and a DNS lookup once, exactly as the desktop client
does, and then sends each request over the transport the visitor picked. It
answers with the server's reply *and* with what the transfer went through, so
the page can show the protocol working rather than only its result.
"""
import json
import logging
import threading
import time
from dataclasses import dataclass, field

from src.client.client import NetworkClient
from src.client.gui.parsing import parse_listing
from src.config import MY_DOMAIN

log = logging.getLogger(__name__)

PROTOCOLS = ("RUDP", "TCP")
ERROR_PREFIX = "Error:"


class GatewayError(Exception):
    """The request never got an answer from the application server."""


@dataclass
class Exchange:
    """One request and its answer, with what it cost on the wire."""
    protocol: str
    answer: str | bytes
    elapsed_ms: float
    size: int
    details: dict = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        return isinstance(self.answer, str) and self.answer.startswith(ERROR_PREFIX)

    @property
    def error_message(self) -> str:
        return self.answer[len(ERROR_PREFIX):].strip() if self.is_error else ""

    def transfer(self) -> dict:
        return {"protocol": self.protocol, "elapsed_ms": round(self.elapsed_ms, 1),
                "bytes": self.size, **self.details}


class NetworkGateway:
    """Joins the network once, then relays requests for every visitor."""

    def __init__(self, client_factory=NetworkClient, domain: str = MY_DOMAIN) -> None:
        self.client_factory = client_factory
        self.domain = domain
        self.client: NetworkClient | None = None
        self.joined_at: float | None = None
        # The DHCP and DNS exchanges share one control socket, so only one
        # visitor at a time may run them. The transfers themselves each open
        # a socket of their own and run side by side.
        self._lock = threading.Lock()

    # ------------------------------------------------------------- joining
    def join(self) -> bool:
        """DHCP then DNS. True when the application server can be reached."""
        with self._lock:
            if self.client is not None:
                return True
            client = self.client_factory()
            if not client.connect(self.domain):
                client.close()
                log.error("The gateway could not join the network")
                return False
            self.client = client
            self.joined_at = time.time()
            log.info(f"Gateway joined as {client.my_ip}, "
                     f"app server at {client.app_server_ip}")
            return True

    @property
    def status(self) -> dict:
        if self.client is None:
            return {"joined": False}
        return {"joined": True, "ip": self.client.my_ip,
                "app_server": self.client.app_server_ip,
                "domain": self.domain}

    def leave(self) -> None:
        with self._lock:
            if self.client is not None:
                self.client.close()
                self.client = None

    # ------------------------------------------------------------ requests
    def exchange(self, request: dict, protocol: str) -> Exchange:
        """Send one request. Raises :class:`GatewayError` if nothing came back."""
        if protocol not in PROTOCOLS:
            raise ValueError(f"unknown protocol {protocol!r}")
        if not self.join():
            raise GatewayError("the network could not be joined")

        transport = self.client.transport_for(protocol)
        started = time.perf_counter()
        answer = transport.request(json.dumps(request, ensure_ascii=False))
        elapsed = (time.perf_counter() - started) * 1000

        if answer is None:
            raise GatewayError(f"no answer over {protocol}")

        size = len(answer.encode("utf-8")) if isinstance(answer, str) else len(answer)
        return Exchange(protocol, answer, elapsed, size, dict(transport.stats))

    def forecast(self, city: str, profiles: list[dict], protocol: str) -> tuple[dict | None, Exchange]:
        """The forecast card, or ``None`` when the server answered with an error."""
        exchange = self.exchange({"action": "FORECAST", "city": city,
                                  "profiles": profiles}, protocol)
        if exchange.is_error:
            return None, exchange
        try:
            card = json.loads(exchange.answer)
        except (TypeError, ValueError):
            return None, exchange
        return (card if isinstance(card, dict) else None), exchange

    def archive(self, protocol: str) -> tuple[list[dict], Exchange]:
        exchange = self.exchange({"action": "FTP_LIST"}, protocol)
        if exchange.is_error or not isinstance(exchange.answer, str):
            return [], exchange
        files = [{"name": name, "size": size}
                 for name, size in parse_listing(exchange.answer)]
        return files, exchange

    def archived_file(self, filename: str, protocol: str) -> Exchange:
        return self.exchange({"action": "FTP_GET", "filename": filename}, protocol)
