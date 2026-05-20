import unittest
from unittest.mock import patch, MagicMock
from src.servers.dns_server import DNSServer


class TestDNSServer(unittest.TestCase):

    @patch('socket.socket')
    def test_init_success(self, mock_socket_class):
        server = DNSServer()

        mock_sock_instance = mock_socket_class.return_value
        mock_sock_instance.bind.assert_called_once()
        self.assertGreater(len(server.dns_records), 0)

    @patch('sys.exit')
    @patch('socket.socket')
    def test_init_port_in_use(self, mock_socket_class, mock_sys_exit):
        mock_sock_instance = MagicMock()
        mock_sock_instance.bind.side_effect = OSError
        mock_socket_class.return_value = mock_sock_instance

        server = DNSServer()

        mock_sys_exit.assert_called_once_with(1)

    @patch('socket.socket')
    def test_find_ip_resolved(self, mock_socket_class):
        server = DNSServer()
        server.dns_records = {"test.local": "192.168.1.50"}
        client_address = ("127.0.0.1", 12345)

        server.find_ip("test.local", client_address)

        expected_response = b"RESOLVED:192.168.1.50"
        server.serv_sock.sendto.assert_called_once_with(expected_response, client_address)

    @patch('socket.socket')
    def test_find_ip_not_found(self, mock_socket_class):
        server = DNSServer()
        server.dns_records = {"test.local": "192.168.1.50"}
        client_address = ("127.0.0.1", 12345)

        server.find_ip("unknown.local", client_address)

        expected_response = b"ERROR:Domain not found"
        server.serv_sock.sendto.assert_called_once_with(expected_response, client_address)


if __name__ == '__main__':
    unittest.main()