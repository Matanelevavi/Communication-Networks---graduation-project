import socket
import unittest
from unittest.mock import MagicMock, patch

from src.client.transport import (RudpTransport, TcpTransport, Transport,
                                  create_transport)
from src.config import APP_PORT, ENCODING, HANDSHAKE_ACK
from src.rudp.packet import RudpPacket

SERVER_IP = "127.0.0.1"
SERVER = (SERVER_IP, APP_PORT)
TRANSFER = (SERVER_IP, 55001)


class TestFactory(unittest.TestCase):

    def test_names_map_to_implementations(self):
        self.assertIsInstance(create_transport("TCP", SERVER_IP), TcpTransport)
        self.assertIsInstance(create_transport("RUDP", SERVER_IP), RudpTransport)

    def test_an_unknown_name_falls_back_to_rudp(self):
        self.assertIsInstance(create_transport("carrier pigeon", SERVER_IP), RudpTransport)

    def test_both_honour_the_same_interface(self):
        for transport in (TcpTransport(SERVER_IP), RudpTransport(SERVER_IP)):
            self.assertIsInstance(transport, Transport)
            self.assertEqual(transport.server, SERVER)

    def test_decoding_falls_back_to_bytes_for_binary(self):
        self.assertEqual(Transport.decode(b"hello"), "hello")
        self.assertEqual(Transport.decode(b"\xff\xfe"), b"\xff\xfe")


@patch("src.client.transport.socket.socket")
class TestTcpTransport(unittest.TestCase):

    def test_a_request_and_its_answer(self, socket_class):
        sock = socket_class.return_value
        sock.recv.side_effect = [b'{"status": "ok"}', b""]

        answer = TcpTransport(SERVER_IP).request('{"action": "FORECAST"}')

        self.assertEqual(answer, '{"status": "ok"}')
        sock.connect.assert_called_once_with(SERVER)
        sock.sendall.assert_called_once_with(b'{"action": "FORECAST"}')
        sock.close.assert_called_once()

    def test_an_answer_spanning_several_reads_is_not_truncated(self, socket_class):
        """
        TCP is a byte stream: a single recv used to cut off anything past one
        buffer, which silently truncated large downloads.
        """
        body = "X" * 40000
        sock = socket_class.return_value
        sock.recv.side_effect = [body[:8192].encode(), body[8192:20000].encode(),
                                 body[20000:].encode(), b""]

        answer = TcpTransport(SERVER_IP).request('{"action": "FTP_GET"}')

        self.assertEqual(len(answer), 40000)

    def test_a_refused_connection_is_reported(self, socket_class):
        socket_class.return_value.connect.side_effect = ConnectionRefusedError

        self.assertIsNone(TcpTransport(SERVER_IP).request("{}"))


@patch("src.client.transport.socket.socket")
class TestRudpTransport(unittest.TestCase):

    def test_handshake_then_transfer(self, socket_class):
        sock = socket_class.return_value
        sock.recvfrom.side_effect = [
            (HANDSHAKE_ACK, SERVER),
            (RudpPacket(1, 1, b"advice").to_bytes(), TRANSFER),
            socket.timeout(),
        ]

        self.assertEqual(RudpTransport(SERVER_IP).request('{"action":"FORECAST"}'), "advice")

    def test_the_request_is_retransmitted_until_acknowledged(self, socket_class):
        sock = socket_class.return_value
        sock.recvfrom.side_effect = [
            socket.timeout(),
            (HANDSHAKE_ACK, SERVER),
            (RudpPacket(1, 1, b"ok").to_bytes(), TRANSFER),
            socket.timeout(),
        ]

        self.assertEqual(RudpTransport(SERVER_IP).request("{}"), "ok")
        self.assertEqual(sock.sendto.call_args_list[0][0][1], SERVER)

    def test_an_acknowledgement_from_a_stranger_is_ignored(self, socket_class):
        sock = socket_class.return_value
        sock.recvfrom.side_effect = [
            (HANDSHAKE_ACK, ("127.0.0.1", 4444)),      # not the app server
            (HANDSHAKE_ACK, SERVER),
            (RudpPacket(1, 1, b"ok").to_bytes(), TRANSFER),
            socket.timeout(),
        ]

        self.assertEqual(RudpTransport(SERVER_IP).request("{}"), "ok")

    def test_an_unreachable_server_is_reported(self, socket_class):
        socket_class.return_value.recvfrom.side_effect = socket.timeout

        self.assertIsNone(RudpTransport(SERVER_IP).request("{}"))


if __name__ == "__main__":
    unittest.main()
