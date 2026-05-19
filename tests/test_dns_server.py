import unittest
from unittest.mock import patch, MagicMock
from src.servers.dns_server import DNSServer

class TestDNSServer(unittest.TestCase):

    #test 1: server starts fine
    @patch('socket.socket')
    def test_init_success(self, mock_socket_class):
        server = DNSServer()

        mock_sock_instance = mock_socket_class.return_value
        mock_sock_instance.bind.assert_called_once()
        self.assertTrue(len(server.dns_records) > 0)

    #test 2: port already taken
    @patch('sys.exit')
    @patch('socket.socket')
    def test_init_port_in_use(self, mock_socket_class, mock_sys_exit):
        mock_sock_instance = MagicMock()
        mock_sock_instance.bind.side_effect = OSError
        mock_socket_class.return_value = mock_sock_instance

        server = DNSServer()
        mock_sys_exit.assert_called_once_with(1)

    #test 3: ask for a good domain and get the IP
    @patch('socket.socket')
    def test_find_ip_resolved(self, mock_socket_class):
        server = DNSServer()
        server.dns_records = {"test.local": "192.168.1.50"}

        client_address = ("127.0.0.1", 12345)
        server.find_ip("test.local", client_address)

        expected_response = b"RESOLVED:192.168.1.50"
        server.server_sock.sendto.assert_called_once_with(expected_response, client_address)

    # test 4: ask for a bad domain that does not exist
    @patch('socket.socket')
    def test_find_ip_not_found(self, mock_socket_class):
        server = DNSServer()
        server.dns_records = {"test.local": "192.168.1.50"}

        client_address = ("127.0.0.1", 12345)
        server.find_ip("unknown.local", client_address)

        expected_response = b"ERROR:Domain not found"
        server.server_sock.sendto.assert_called_once_with(expected_response, client_address)

if __name__ == '__main__':
    unittest.main()