"""
Local DNS server.

A deliberately small authoritative server: one in-memory table, one question
type ("give me the address for this name").  Two properties of real DNS that
matter for the project are kept:

* lookups are case insensitive, as they are in RFC 1035;
* the answer carries the TTL, so the caching policy is decided by the
  authoritative server and not hard coded in the client.
"""
import socket
import logging
import sys
from src.config import (APP_SER_IP, BUFF_SIZE, DNS_ADD, DNS_RECORD_TTL,
                        ENCODING, MY_DOMAIN, setup_logging)

log = logging.getLogger(__name__)


class DNSServer:
    def __init__(self):
        self.serv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # a custom port (8053) instead of 53, which needs root privileges
            # and collides with the resolver already running on the machine
            self.serv_sock.bind(DNS_ADD)
        except OSError:
            log.error("Port Problem, DNS Server is already running or port in use so exiting")
            sys.exit(1)

        # in memory table acting as our zone file, O(1) lookup
        self.dns_records = {MY_DOMAIN.lower(): APP_SER_IP}
        self.ttl = DNS_RECORD_TTL

    def start(self):
        log.info(f"DNS Server listening on {DNS_ADD}")
        try:
            while True:
                try:
                    data, cl_add = self.serv_sock.recvfrom(BUFF_SIZE)
                except ConnectionResetError:
                    continue

                try:
                    dom_name = data.decode(ENCODING).strip()
                except UnicodeDecodeError:
                    log.warning(f"Dropped a non UTF-8 query from {cl_add}")
                    continue

                self.find_ip(dom_name, cl_add)
        except KeyboardInterrupt:
            log.info("Turn off DNS server")
        finally:
            self.serv_sock.close()

    def find_ip(self, dom, cl_add):
        """Answer one query, with the TTL included in the answer."""
        record = self.dns_records.get(dom.lower())
        if record:
            ans = f"RESOLVED:{record}:{self.ttl}"
            log.info(f"Resolved {dom} to {record} (TTL {self.ttl}s) for {cl_add}")
        else:
            ans = "ERROR:Domain not found"
            log.warning(f"Failed to resolve {dom} for {cl_add}")

        try:
            self.serv_sock.sendto(ans.encode(ENCODING), cl_add)
        except OSError as e:
            log.warning(f"Could not answer {cl_add}: {e}")


if __name__ == "__main__":
    setup_logging("DNS")
    DNSServer().start()
