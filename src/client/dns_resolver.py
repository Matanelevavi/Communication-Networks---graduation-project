"""
The client half of DNS.

Sends a name to the local DNS server and caches the answer for as long as the
server says it may be cached.  The TTL is the server's decision, exactly as it
is in real DNS, and the local constant is only a fallback.
"""
import logging
import socket
import time
from dataclasses import dataclass

from src.config import BUFF_SIZE, DNS_ADD, DNS_CACHE_TTL, ENCODING, TIMEOUT

log = logging.getLogger(__name__)

RESOLVED_PREFIX = "RESOLVED:"


@dataclass(frozen=True)
class CacheEntry:
    """One cached answer and the moment it stops being valid."""
    ip: str
    expires_at: float

    def is_valid(self, now: float) -> bool:
        return now < self.expires_at


class DnsResolver:
    """Resolves names through the local DNS server, with a TTL aware cache."""

    def __init__(self, sock) -> None:
        self.sock = sock
        self.cache: dict[str, CacheEntry] = {}

    def resolve(self, domain: str) -> str | None:
        """Return the address for a name, from the cache when it is still valid."""
        cached = self._from_cache(domain)
        if cached:
            return cached

        log.info(f"Resolving {domain} via the network")
        answer = self._query(domain)
        if answer is None:
            return None

        ip, ttl = answer
        self.cache[domain] = CacheEntry(ip, time.time() + ttl)
        log.info(f"DNS result: {ip} (TTL {ttl}s)")
        return ip

    def _from_cache(self, domain: str) -> str | None:
        entry = self.cache.get(domain)
        if entry is None:
            return None

        if entry.is_valid(time.time()):
            log.info(f"DNS resolved from cache: {entry.ip} (TTL valid)")
            return entry.ip

        log.info(f"DNS cache for {domain} expired, fetching a fresh answer")
        del self.cache[domain]
        return None

    def _query(self, domain: str) -> tuple[str, int] | None:
        """One request/response round trip.  Returns (ip, ttl)."""
        try:
            self.sock.settimeout(TIMEOUT)
            self.sock.sendto(domain.encode(ENCODING), DNS_ADD)
            data, _ = self.sock.recvfrom(BUFF_SIZE)
        except socket.timeout:
            log.error("DNS timeout")
            return None
        except OSError as e:
            log.error(f"DNS socket error: {e}")
            return None

        answer = data.decode(ENCODING, errors="replace")
        if not answer.startswith(RESOLVED_PREFIX):
            log.error(f"DNS failed: {answer}")
            return None

        parts = answer.split(":")
        ip = parts[1]
        # A server that answers without a TTL falls back to the local default.
        ttl = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else DNS_CACHE_TTL
        return ip, ttl
