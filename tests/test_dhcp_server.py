import unittest
from unittest.mock import patch
from src.servers.dhcp_server import DHCPServer
from src.config import ENCODING, DISCOVER_MSG, OFFER_MSG, REQUEST_MSG, ACK_MSG


class TestDHCPServer(unittest.TestCase):

    # test 1: server starts fine
    @patch('socket.socket')
    def test_init_success(self, mock_socket_class):
        server = DHCPServer()

        mock_sock_instance = mock_socket_class.return_value
        mock_sock_instance.bind.assert_called_once()
        self.assertTrue(len(server.pool_ip) > 0)

    # test 2: handle discover msg and offer an ip
    @patch('socket.socket')
    def test_discover_success(self, mock_socket_class):
        mock_sock_instance = mock_socket_class.return_value

        # return mock data on first loop, then simulate Ctrl+C to break the loop
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

    # test 3: handle discover when pool is empty
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

    # test 4: handle request for the correct ip
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

    # test 5: handle request for the wrong ip
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

        # check that sendto was never called because the IP was wrong
        mock_sock_instance.sendto.assert_not_called()


if __name__ == '__main__':
    unittest.main()