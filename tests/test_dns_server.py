import unittest
from unittest.mock import patch, MagicMock

from src.servers.dns_server import DNSServer
from src.config import DNS_RECORD_TTL

CLIENT = ("127.0.0.1", 12345)


class TestDNSServer(unittest.TestCase):

    @patch('socket.socket')
    def test_init_success(self, mock_socket_class):
        server = DNSServer()

        mock_socket_class.return_value.bind.assert_called_once()
        self.assertGreater(len(server.dns_records), 0)

    @patch('sys.exit')
    @patch('socket.socket')
    def test_init_port_in_use(self, mock_socket_class, mock_sys_exit):
        mock_sock_instance = MagicMock()
        mock_sock_instance.bind.side_effect = OSError
        mock_socket_class.return_value = mock_sock_instance

        DNSServer()

        mock_sys_exit.assert_called_once_with(1)

    @patch('socket.socket')
    def test_answer_carries_the_ttl(self, mock_socket_class):
        """The authoritative server decides the caching policy, not the client."""
        server = DNSServer()
        server.dns_records = {"test.local": "192.168.1.50"}

        server.find_ip("test.local", CLIENT)

        server.serv_sock.sendto.assert_called_once_with(
            f"RESOLVED:192.168.1.50:{DNS_RECORD_TTL}".encode('utf-8'), CLIENT)

    @patch('socket.socket')
    def test_lookup_is_case_insensitive(self, mock_socket_class):
        server = DNSServer()
        server.dns_records = {"test.local": "192.168.1.50"}

        server.find_ip("TEST.Local", CLIENT)

        sent = server.serv_sock.sendto.call_args[0][0].decode('utf-8')
        self.assertTrue(sent.startswith("RESOLVED:192.168.1.50"))

    @patch('socket.socket')
    def test_find_ip_not_found(self, mock_socket_class):
        server = DNSServer()
        server.dns_records = {"test.local": "192.168.1.50"}

        server.find_ip("unknown.local", CLIENT)

        server.serv_sock.sendto.assert_called_once_with(
            b"ERROR:Domain not found", CLIENT)


if __name__ == '__main__':
    unittest.main()
