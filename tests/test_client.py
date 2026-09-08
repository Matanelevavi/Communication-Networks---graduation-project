import socket
import unittest
from unittest.mock import MagicMock, patch

from src.client.client import NetworkClient
from src.client.transport import RudpTransport, TcpTransport
from src.config import APP_PORT, CLIENT_ADD, FIN_ACK_MSG, FIN_MSG, HOST

SERVER = ("127.0.0.1", APP_PORT)


@patch("src.client.client.socket.socket")
class TestControlSocket(unittest.TestCase):

    def test_it_uses_the_documented_client_port(self, socket_class):
        NetworkClient()

        socket_class.return_value.bind.assert_called_once_with(CLIENT_ADD)

    def test_it_falls_back_when_the_port_is_busy(self, socket_class):
        """A second client, used to demonstrate concurrency, must still start."""
        sock = socket_class.return_value
        sock.bind.side_effect = [OSError, None]
        sock.getsockname.return_value = (HOST, 54321)

        NetworkClient()

        self.assertEqual(sock.bind.call_args[0][0], (HOST, 0))


@patch("src.client.client.socket.socket")
class TestJoiningTheNetwork(unittest.TestCase):

    def test_connect_runs_dhcp_then_dns(self, _socket_class):
        client = NetworkClient()
        client.dhcp = MagicMock(**{"acquire.return_value": True, "my_ip": "192.168.1.50"})
        client.dns = MagicMock(**{"resolve.return_value": "127.0.0.1"})

        self.assertTrue(client.connect("weatherwear.local"))
        self.assertEqual(client.app_server_ip, "127.0.0.1")
        self.assertEqual(client.my_ip, "192.168.1.50")

    def test_a_failed_dora_stops_before_dns(self, _socket_class):
        client = NetworkClient()
        client.dhcp = MagicMock(**{"acquire.return_value": False})
        client.dns = MagicMock()

        self.assertFalse(client.connect())
        client.dns.resolve.assert_not_called()

    def test_a_failed_lookup_fails_the_connection(self, _socket_class):
        client = NetworkClient()
        client.dhcp = MagicMock(**{"acquire.return_value": True})
        client.dns = MagicMock(**{"resolve.return_value": None})

        self.assertFalse(client.connect())


@patch("src.client.client.socket.socket")
class TestRequests(unittest.TestCase):

    def test_the_protocol_name_selects_the_transport(self, _socket_class):
        client = NetworkClient()
        client.app_server_ip = "127.0.0.1"

        self.assertIsInstance(client.transport_for("TCP"), TcpTransport)
        self.assertIsInstance(client.transport_for("RUDP"), RudpTransport)

    def test_a_request_is_handed_to_the_transport(self, _socket_class):
        client = NetworkClient()
        client.app_server_ip = "127.0.0.1"
        transport = MagicMock(**{"request.return_value": "advice"})
        client.transport_for = MagicMock(return_value=transport)

        self.assertEqual(client.request("{}", "TCP"), "advice")
        transport.request.assert_called_once_with("{}")


@patch("src.client.client.socket.socket")
class TestTeardown(unittest.TestCase):

    def test_it_says_goodbye_and_gives_the_address_back(self, socket_class):
        sock = socket_class.return_value
        sock.recvfrom.return_value = (FIN_ACK_MSG, SERVER)

        client = NetworkClient()
        client.app_server_ip = "127.0.0.1"
        client.dhcp = MagicMock()

        client.close()

        sock.sendto.assert_any_call(FIN_MSG, SERVER)
        client.dhcp.release.assert_called_once()
        sock.close.assert_called_once()

    def test_a_missing_fin_ack_does_not_stop_the_teardown(self, socket_class):
        sock = socket_class.return_value
        sock.recvfrom.side_effect = socket.timeout

        client = NetworkClient()
        client.app_server_ip = "127.0.0.1"
        client.dhcp = MagicMock()

        client.close()

        client.dhcp.release.assert_called_once()
        sock.close.assert_called_once()

    def test_closing_before_connecting_is_harmless(self, socket_class):
        client = NetworkClient()
        client.dhcp = MagicMock()

        client.close()

        socket_class.return_value.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
