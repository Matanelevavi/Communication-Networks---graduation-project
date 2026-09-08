import socket
import time
import unittest
from unittest.mock import MagicMock

from src.client.dns_resolver import CacheEntry, DnsResolver
from src.config import DNS_ADD, DNS_CACHE_TTL, ENCODING

SERVER = ("127.0.0.1", 8053)
DOMAIN = "weatherwear.local"


class DnsResolverTestCase(unittest.TestCase):
    def resolver(self, answer=None):
        sock = MagicMock()
        if isinstance(answer, Exception):
            sock.recvfrom.side_effect = answer
        elif answer is not None:
            sock.recvfrom.return_value = (answer.encode(ENCODING), SERVER)
        self.sock = sock
        return DnsResolver(sock)


class TestResolution(DnsResolverTestCase):

    def test_a_successful_lookup(self):
        dns = self.resolver("RESOLVED:10.0.0.5:120")

        self.assertEqual(dns.resolve(DOMAIN), "10.0.0.5")
        self.sock.sendto.assert_called_once_with(DOMAIN.encode(ENCODING), DNS_ADD)

    def test_the_ttl_comes_from_the_server(self):
        """Real DNS lets the authoritative server set the caching policy."""
        dns = self.resolver("RESOLVED:10.0.0.5:120")
        before = time.time()

        dns.resolve(DOMAIN)

        self.assertAlmostEqual(dns.cache[DOMAIN].expires_at - before, 120, delta=1)

    def test_an_answer_without_a_ttl_falls_back_to_the_local_default(self):
        dns = self.resolver("RESOLVED:10.0.0.5")
        before = time.time()

        dns.resolve(DOMAIN)

        self.assertAlmostEqual(dns.cache[DOMAIN].expires_at - before,
                               DNS_CACHE_TTL, delta=1)

    def test_an_unknown_domain_is_reported(self):
        dns = self.resolver("ERROR:Domain not found")

        self.assertIsNone(dns.resolve("nope.local"))
        self.assertEqual(dns.cache, {})

    def test_a_timeout_is_reported(self):
        dns = self.resolver(socket.timeout())

        self.assertIsNone(dns.resolve(DOMAIN))


class TestCache(DnsResolverTestCase):

    def test_a_valid_entry_skips_the_network(self):
        dns = self.resolver()
        dns.cache[DOMAIN] = CacheEntry("192.168.1.99", time.time() + 60)

        self.assertEqual(dns.resolve(DOMAIN), "192.168.1.99")
        self.sock.sendto.assert_not_called()

    def test_an_expired_entry_is_looked_up_again(self):
        dns = self.resolver("RESOLVED:10.0.0.5:60")
        dns.cache[DOMAIN] = CacheEntry("192.168.1.99", time.time() - 1)

        self.assertEqual(dns.resolve(DOMAIN), "10.0.0.5")
        self.sock.sendto.assert_called_once()

    def test_entry_validity(self):
        entry = CacheEntry("1.2.3.4", 100.0)

        self.assertTrue(entry.is_valid(99.0))
        self.assertFalse(entry.is_valid(100.0))


if __name__ == "__main__":
    unittest.main()
