import unittest
from unittest.mock import patch
from src.servers.dhcp_server import DHCPServer
from src.config import ENCODING, DISCOVER_MSG, OFFER_MSG, REQUEST_MSG, ACK_MSG

class TestDHCPServer(unittest.TestCase):

    @patch('socket.socket')
    def test_init_success(self, mock_socket_class):
        server = DHCPServer()

        mock_sock_instance = mock_socket_class.return_value
        mock_sock_instance.bind.assert_called_once()
        self.assertGreater(len(server.pool_ip), 0)

    @patch('socket.socket')
    def test_discover_success(self, mock_socket_class):
        mock_sock_instance = mock_socket_class.return_value

        mock_sock_instance.recvfrom.side_effect = [
            (DISCOVER_MSG.encode(ENCODING), ("127.0.0.1", 12345)),
            KeyboardInterrupt()
        ]

        server = DHCPServer()
        server.pool_ip = ["192.168.1.100"]
        server.start()

        expected_reply = f"{OFFER_MSG}:192.168.1.100".encode(ENCODING)
        mock_sock_instance.sendto.assert_called_once_with(expected_reply, ("127.0.0.1", 12345))
        self.assertEqual(server.used_ips[("127.0.0.1", 12345)], "192.168.1.100")

    @patch('socket.socket')
    def test_discover_no_ips(self, mock_socket_class):
        mock_sock_instance = mock_socket_class.return_value
        mock_sock_instance.recvfrom.side_effect = [
            (DISCOVER_MSG.encode(ENCODING), ("127.0.0.1", 12345)),
            KeyboardInterrupt()
        ]

        server = DHCPServer()
        server.pool_ip = []
        server.start()

        expected_reply = "DHCP: No IPs available".encode(ENCODING)
        mock_sock_instance.sendto.assert_called_once_with(expected_reply, ("127.0.0.1", 12345))

    @patch('socket.socket')
    def test_request_success(self, mock_socket_class):
        mock_sock_instance = mock_socket_class.return_value
        msg = f"{REQUEST_MSG}:192.168.1.100".encode(ENCODING)

        mock_sock_instance.recvfrom.side_effect = [
            (msg, ("127.0.0.1", 12345)),
            KeyboardInterrupt()
        ]

        server = DHCPServer()
        server.used_ips = {("127.0.0.1", 12345): "192.168.1.100"}
        server.start()

        expected_reply = f"{ACK_MSG}:192.168.1.100".encode(ENCODING)
        mock_sock_instance.sendto.assert_called_once_with(expected_reply, ("127.0.0.1", 12345))

    @patch('socket.socket')
    def test_request_invalid_ip(self, mock_socket_class):
        mock_sock_instance = mock_socket_class.return_value
        msg = f"{REQUEST_MSG}:192.168.1.999".encode(ENCODING)

        mock_sock_instance.recvfrom.side_effect = [
            (msg, ("127.0.0.1", 12345)),
            KeyboardInterrupt()
        ]

        server = DHCPServer()
        server.used_ips = {("127.0.0.1", 12345): "192.168.1.100"}
        server.start()

        mock_sock_instance.sendto.assert_not_called()

    @patch('socket.socket')
    def test_dhcp_release(self, mock_socket_class):
        mock_sock_instance = mock_socket_class.return_value
        msg = b"DHCP_RELEASE:192.168.1.100"

        mock_sock_instance.recvfrom.side_effect = [
            (msg, ("127.0.0.1", 12345)),
            KeyboardInterrupt()
        ]

        server = DHCPServer()
        server.pool_ip = []
        server.used_ips = {("127.0.0.1", 12345): "192.168.1.100"}
        server.start()

        self.assertNotIn(("127.0.0.1", 12345), server.used_ips)
        self.assertIn("192.168.1.100", server.pool_ip)

if __name__ == '__main__':
    unittest.main()