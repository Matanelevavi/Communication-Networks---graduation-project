"""
Application server.

Listens for TCP and for RUDP on the same port number — two separate namespaces
in the operating system — and hands every request that arrives to the same
router.  Each listener is its own class, so neither has to know the other
exists, and the router never learns how a request reached it.
"""
import logging
import threading

from src.config import setup_logging
from src.servers.app_server.router import RequestRouter
from src.servers.app_server.rudp_listener import RudpListener
from src.servers.app_server.tcp_listener import TcpListener

log = logging.getLogger(__name__)


class AppServer:
    """Runs both listeners over one shared router."""

    def __init__(self) -> None:
        self.router = RequestRouter()
        self.tcp = TcpListener(self.router)
        self.rudp = RudpListener(self.router)

    def start(self) -> None:
        log.info("Starting Multi-Threaded App Server (WeatherWear)")
        threading.Thread(target=self.tcp.serve_forever, daemon=True).start()
        try:
            self.rudp.serve_forever()          # the main thread stays here
        except KeyboardInterrupt:
            log.info("Shutting down App Server gracefully")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self.tcp.stop()
        self.rudp.stop()


if __name__ == "__main__":
    setup_logging("SERVER")
    AppServer().start()
