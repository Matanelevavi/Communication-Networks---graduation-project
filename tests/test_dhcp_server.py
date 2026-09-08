import unittest
from unittest.mock import patch

from src.config import (ACK_MSG, DHCP_BACKUP_PORT, DHCP_PORT, DISCOVER_MSG,
                        ENCODING, NAK_MSG, OFFER_MSG, RELEASE_MSG, REQUEST_MSG)
from src.servers.dhcp_backup import DHCPBackupServer
from src.servers.dhcp_server import DHCPServer

CLIENT = ("127.0.0.1", 12345)


def datagrams(*messages):
    """Feed the server a few messages, then interrupt its loop."""
    return [(m.encode(ENCODING), CLIENT) for m in messages] + [KeyboardInterrupt()]


class DHCPServerTestCase(unittest.TestCase):
    def setUp(self):
        self.patcher = patch("socket.socket")
        self.socket_class = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.sock = self.socket_class.return_value

    def sent_messages(self):
        return [call[0][0].decode(ENCODING) for call in self.sock.sendto.call_args_list]


class TestStartup(DHCPServerTestCase):

    def test_binds_and_fills_its_pool(self):
        server = DHCPServer()

        self.sock.bind.assert_called_once()
        self.assertGreater(server.pool.available, 0)

    def test_a_busy_port_exits_with_a_message(self):
        self.sock.bind.side_effect = OSError

        with self.assertRaises(SystemExit):
            DHCPServer()


class TestDiscover(DHCPServerTestCase):

    def test_offers_an_address_without_leasing_it(self):
        self.sock.recvfrom.side_effect = datagrams(DISCOVER_MSG)
        server = DHCPServer(pool=["192.168.1.100"])

        server.start()

        self.assertEqual(self.sent_messages(), [f"{OFFER_MSG}:192.168.1.100"])
        self.assertIn(CLIENT, server.pool.reserved)
        self.assertNotIn(CLIENT, server.pool.leased)

    def test_a_repeated_discover_repeats_the_same_offer(self):
        self.sock.recvfrom.side_effect = datagrams(DISCOVER_MSG, DISCOVER_MSG)
        server = DHCPServer(pool=["192.168.1.100", "192.168.1.101"])

        server.start()

        self.assertEqual(self.sent_messages(),
                         [f"{OFFER_MSG}:192.168.1.100"] * 2)
        self.assertEqual(server.pool.available, 1)

    def test_an_empty_pool_is_refused_explicitly(self):
        self.sock.recvfrom.side_effect = datagrams(DISCOVER_MSG)
        server = DHCPServer(pool=[])

        server.start()

        self.assertEqual(self.sent_messages(), [f"{NAK_MSG}:No IPs available"])


class TestRequest(DHCPServerTestCase):

    def test_a_matching_request_is_acknowledged(self):
        self.sock.recvfrom.side_effect = datagrams(
            DISCOVER_MSG, f"{REQUEST_MSG}:192.168.1.100:{DHCP_PORT}")
        server = DHCPServer(pool=["192.168.1.100"])

        server.start()

        self.assertEqual(self.sent_messages()[-1], f"{ACK_MSG}:192.168.1.100")
        self.assertEqual(server.pool.leased[CLIENT].ip, "192.168.1.100")

    def test_an_unoffered_address_is_refused(self):
        self.sock.recvfrom.side_effect = datagrams(f"{REQUEST_MSG}:192.168.1.999:{DHCP_PORT}")

        DHCPServer().start()

        self.assertTrue(self.sent_messages()[-1].startswith(NAK_MSG))

    def test_a_request_naming_another_server_frees_the_reservation(self):
        """
        This is the fix for the backup pool leaking one address per exchange:
        the server that was not chosen learns it lost and lets go at once.
        """
        self.sock.recvfrom.side_effect = datagrams(
            DISCOVER_MSG, f"{REQUEST_MSG}:192.168.1.100:{DHCP_PORT}")
        backup = DHCPBackupServer()
        backup.offer_delay = 0.0                      # answer immediately, for the test
        backup.pool.free = ["192.168.2.100"]

        backup.start()

        self.assertEqual(backup.pool.available, 1)
        self.assertNotIn(CLIENT, backup.pool.reserved)
        self.assertEqual(self.sent_messages(), [f"{OFFER_MSG}:192.168.2.100"])

    def test_a_malformed_request_is_ignored(self):
        self.sock.recvfrom.side_effect = datagrams(REQUEST_MSG)

        DHCPServer().start()

        self.sock.sendto.assert_not_called()


class TestRelease(DHCPServerTestCase):

    def test_a_leased_address_goes_back_to_the_pool(self):
        self.sock.recvfrom.side_effect = datagrams(
            DISCOVER_MSG,
            f"{REQUEST_MSG}:192.168.1.100:{DHCP_PORT}",
            f"{RELEASE_MSG}:192.168.1.100")
        server = DHCPServer(pool=["192.168.1.100"])

        server.start()

        self.assertEqual(server.pool.available, 1)
        self.assertNotIn(CLIENT, server.pool.leased)

    def test_releasing_before_requesting_still_frees_the_reservation(self):
        self.sock.recvfrom.side_effect = datagrams(
            DISCOVER_MSG, f"{RELEASE_MSG}:192.168.1.100")
        server = DHCPServer(pool=["192.168.1.100"])

        server.start()

        self.assertEqual(server.pool.available, 1)


class TestBackupServer(DHCPServerTestCase):

    def test_it_has_its_own_port_pool_and_delay(self):
        backup = DHCPBackupServer()

        self.assertEqual(backup.address[1], DHCP_BACKUP_PORT)
        self.assertTrue(all(ip.startswith("192.168.2.") for ip in backup.pool.free))
        self.assertGreater(backup.offer_delay, 0)

    @patch("threading.Timer")
    def test_the_delay_is_scheduled_not_slept(self, timer):
        """A blocking sleep would queue a second client behind the first."""
        backup = DHCPBackupServer()

        backup.handle(DISCOVER_MSG, CLIENT)

        timer.assert_called_once()
        self.sock.sendto.assert_not_called()

    def test_it_does_not_offer_to_a_client_that_already_chose_the_primary(self):
        backup = DHCPBackupServer()
        backup.pool.decline(CLIENT)

        backup.send_offer(CLIENT)

        self.sock.sendto.assert_not_called()
        self.assertEqual(backup.pool.available, len(backup.pool.free))


if __name__ == "__main__":
    unittest.main()
