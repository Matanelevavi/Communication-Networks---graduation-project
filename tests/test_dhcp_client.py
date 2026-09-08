import socket
import unittest
from unittest.mock import MagicMock

from src.client.dhcp_client import DhcpClient
from src.config import (ACK_MSG, DHCP_ADD, DHCP_BACKUP_ADD, DHCP_BACKUP_PORT,
                        DHCP_PORT, DISCOVER_MSG, ENCODING, NAK_MSG, OFFER_MSG,
                        RELEASE_MSG, REQUEST_MSG)

PRIMARY = ("127.0.0.1", DHCP_PORT)
BACKUP = ("127.0.0.1", DHCP_BACKUP_PORT)


def reply(text, addr):
    return text.encode(ENCODING), addr


class DhcpClientTestCase(unittest.TestCase):
    def client(self, *replies):
        sock = MagicMock()
        sock.recvfrom.side_effect = list(replies) + [socket.timeout()] * 20
        self.sock = sock
        return DhcpClient(sock)

    def sent(self):
        return [call[0][0].decode(ENCODING) for call in self.sock.sendto.call_args_list]


class TestSuccessfulExchange(DhcpClientTestCase):

    def test_dora_completes(self):
        dhcp = self.client(reply(f"{OFFER_MSG}:192.168.1.50", PRIMARY),
                           reply(f"{ACK_MSG}:192.168.1.50", PRIMARY))

        self.assertTrue(dhcp.acquire())
        self.assertEqual(dhcp.my_ip, "192.168.1.50")
        self.assertEqual(dhcp.server_addr, PRIMARY)

    def test_discover_reaches_both_servers(self):
        dhcp = self.client(reply(f"{OFFER_MSG}:192.168.1.50", PRIMARY),
                           reply(f"{ACK_MSG}:192.168.1.50", PRIMARY))
        dhcp.acquire()

        targets = [call[0][1] for call in self.sock.sendto.call_args_list[:2]]
        self.assertEqual(targets, [DHCP_ADD, DHCP_BACKUP_ADD])
        self.assertEqual(self.sent()[:2], [DISCOVER_MSG, DISCOVER_MSG])

    def test_the_request_names_the_chosen_server(self):
        """
        Both servers see which one was picked, the role the server identifier
        option plays in RFC 2131.  Without it the loser holds an address that
        nobody will ever claim.
        """
        dhcp = self.client(reply(f"{OFFER_MSG}:192.168.1.50", PRIMARY),
                           reply(f"{ACK_MSG}:192.168.1.50", PRIMARY))
        dhcp.acquire()

        expected = f"{REQUEST_MSG}:192.168.1.50:{DHCP_PORT}"
        self.assertEqual(self.sent()[2:4], [expected, expected])

    def test_an_offer_from_the_backup_is_accepted_when_it_arrives_first(self):
        dhcp = self.client(reply(f"{OFFER_MSG}:192.168.2.50", BACKUP),
                           reply(f"{ACK_MSG}:192.168.2.50", BACKUP))

        self.assertTrue(dhcp.acquire())
        self.assertIn(f"{REQUEST_MSG}:192.168.2.50:{DHCP_BACKUP_PORT}", self.sent())


class TestRetries(DhcpClientTestCase):

    def test_a_lost_ack_is_retried(self):
        """The original client sent each message once and then gave up."""
        dhcp = self.client(reply(f"{OFFER_MSG}:192.168.1.50", PRIMARY),
                           socket.timeout(),
                           reply(f"{ACK_MSG}:192.168.1.50", PRIMARY))

        self.assertTrue(dhcp.acquire())
        self.assertEqual(dhcp.my_ip, "192.168.1.50")

    def test_a_lost_offer_restarts_the_exchange(self):
        dhcp = self.client(socket.timeout(),
                           reply(f"{OFFER_MSG}:192.168.1.50", PRIMARY),
                           reply(f"{ACK_MSG}:192.168.1.50", PRIMARY))

        self.assertTrue(dhcp.acquire())
        self.assertEqual(self.sent().count(DISCOVER_MSG), 4)   # two attempts, two servers

    def test_a_late_offer_is_ignored(self):
        dhcp = self.client(reply(f"{OFFER_MSG}:192.168.1.50", PRIMARY),
                           reply(f"{OFFER_MSG}:192.168.2.50", BACKUP),
                           reply(f"{ACK_MSG}:192.168.1.50", PRIMARY))

        self.assertTrue(dhcp.acquire())
        self.assertEqual(dhcp.my_ip, "192.168.1.50")


class TestFailures(DhcpClientTestCase):

    def test_silence_fails_after_the_retries(self):
        dhcp = self.client()

        self.assertFalse(dhcp.acquire())
        self.assertIsNone(dhcp.my_ip)

    def test_two_empty_pools_fail_immediately(self):
        """A refusal is recognised as one, instead of waiting out a timeout."""
        dhcp = self.client(reply(f"{NAK_MSG}:No IPs available", PRIMARY),
                           reply(f"{NAK_MSG}:No IPs available", BACKUP))

        self.assertFalse(dhcp.acquire())
        self.assertEqual(self.sent().count(DISCOVER_MSG), 2)   # no pointless second attempt

    def test_a_refused_request_stops_the_attempt(self):
        dhcp = self.client(reply(f"{OFFER_MSG}:192.168.1.50", PRIMARY),
                           reply(f"{NAK_MSG}:not yours", PRIMARY))

        self.assertFalse(dhcp.acquire())


class TestRelease(DhcpClientTestCase):

    def test_the_address_goes_back_to_both_servers(self):
        dhcp = self.client()
        dhcp.my_ip = "192.168.1.50"

        dhcp.release()

        self.assertEqual(self.sent(), [f"{RELEASE_MSG}:192.168.1.50"] * 2)
        self.assertIsNone(dhcp.my_ip)

    def test_releasing_without_a_lease_sends_nothing(self):
        self.client().release()

        self.sock.sendto.assert_not_called()


if __name__ == "__main__":
    unittest.main()
