import unittest
from unittest.mock import patch, MagicMock
import socket
import time

from src.client.client import NetworkClient
from src.config import ENCODING, DISCOVER_MSG, OFFER_MSG, REQUEST_MSG, ACK_MSG, APP_PORT, DHCP_ADD, DHCP_BACKUP_ADD


class TestNetworkClient(unittest.TestCase):

    @patch('socket.socket')
    def test_dhcp_success(self, mock_socket_class):
        mock_sock = mock_socket_class.return_value

        mock_sock.recvfrom.side_effect = [
            (f"{OFFER_MSG}:192.168.1.50".encode(ENCODING), ("127.0.0.1", 8067)),
            (f"{ACK_MSG}:192.168.1.50".encode(ENCODING), ("127.0.0.1", 8067))
        ]

        client = NetworkClient()
        result = client.get_ip_via_dhcp()

        self.assertTrue(result)
        self.assertEqual(client.my_ip, "192.168.1.50")

    @patch('socket.socket')
    def test_dhcp_timeout(self, mock_socket_class):
        mock_sock = mock_socket_class.return_value
        mock_sock.recvfrom.side_effect = socket.timeout

        client = NetworkClient()
        result = client.get_ip_via_dhcp()

        self.assertFalse(result)
        self.assertIsNone(client.my_ip)

    @patch('socket.socket')
    def test_resolve_dns_network(self, mock_socket_class):
        mock_sock = mock_socket_class.return_value
        mock_sock.recvfrom.return_value = ("RESOLVED:10.0.0.5".encode(ENCODING), ("127.0.0.1", 8053))

        client = NetworkClient()
        ip = client.resolve_dns("weatherwear.local")

        self.assertEqual(ip, "10.0.0.5")
        self.assertEqual(client.app_server_ip, "10.0.0.5")
        self.assertIn("weatherwear.local", client.dns_cache)

    @patch('socket.socket')
    def test_resolve_dns_cache_valid(self, mock_socket_class):
        client = NetworkClient()
        client.dns_cache["weatherwear.local"] = ("192.168.1.99", time.time())

        ip = client.resolve_dns("weatherwear.local")

        self.assertEqual(ip, "192.168.1.99")
        mock_socket_class.return_value.sendto.assert_not_called()

    @patch('socket.socket')
    def test_resolve_dns_cache_expired(self, mock_socket_class):
        client = NetworkClient()
        mock_sock = mock_socket_class.return_value
        mock_sock.recvfrom.return_value = ("RESOLVED:10.0.0.5".encode(ENCODING), ("127.0.0.1", 8053))

        # simulate expired TTL
        client.dns_cache["weatherwear.local"] = ("192.168.1.99", time.time() - 100)

        ip = client.resolve_dns("weatherwear.local")

        self.assertEqual(ip, "10.0.0.5")
        mock_sock.sendto.assert_called_once()

    @patch('socket.socket')
    def test_tcp_send_and_receive(self, mock_socket_class):
        mock_tcp_sock = MagicMock()
        mock_socket_class.return_value = mock_tcp_sock
        mock_tcp_sock.recv.return_value = '{"status": "ok"}'.encode(ENCODING)

        client = NetworkClient()
        client.app_server_ip = "127.0.0.1"

        res = client.tcp_send_and_receive('{"action": "FORECAST"}')

        self.assertEqual(res, '{"status": "ok"}')
        mock_tcp_sock.connect.assert_called_once_with(("127.0.0.1", APP_PORT))
        mock_tcp_sock.sendall.assert_called_once()
        mock_tcp_sock.close.assert_called_once()

    @patch('socket.socket')
    def test_close_teardown(self, mock_socket_class):
        mock_sock = mock_socket_class.return_value
        mock_sock.recvfrom.return_value = (b"FIN-ACK", ("127.0.0.1", APP_PORT))

        client = NetworkClient()
        client.app_server_ip = "127.0.0.1"
        client.my_ip = "192.168.1.50"
        client.client_socket = mock_sock

        client.close()

        mock_sock.sendto.assert_any_call(b"FIN", ("127.0.0.1", APP_PORT))

        release_msg = b"DHCP_RELEASE:192.168.1.50"
        mock_sock.sendto.assert_any_call(release_msg, DHCP_ADD)
        mock_sock.sendto.assert_any_call(release_msg, DHCP_BACKUP_ADD)

        mock_sock.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()