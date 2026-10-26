import json
import threading
import unittest
from unittest.mock import MagicMock, patch

from src.config import HANDSHAKE_ACK
from src.servers.app_server.rudp_listener import RudpListener
from src.servers.app_server.tcp_listener import TcpListener
from src.servers.app_server.wire import as_bytes

CLIENT = ("127.0.0.1", 55555)


class TestWireConversion(unittest.TestCase):

    def test_text_becomes_bytes(self):
        self.assertEqual(as_bytes("hello"), b"hello")

    def test_bytes_pass_through(self):
        self.assertEqual(as_bytes(b"\x00raw"), b"\x00raw")

    def test_nothing_becomes_an_error(self):
        self.assertTrue(as_bytes(None).startswith(b"Error:"))


@patch("src.servers.app_server.tcp_listener.socket.socket")
class TestTcpListener(unittest.TestCase):

    def listener(self, socket_class):
        listener = TcpListener(MagicMock())
        listener.router.handle.return_value = "Wear a jacket!"
        return listener

    def test_a_request_split_across_packets_is_reassembled(self, socket_class):
        """One recv is not guaranteed to return a whole TCP message."""
        payload = json.dumps({"action": "FORECAST", "city": "Ariel"})
        half = len(payload) // 2
        connection = MagicMock()
        connection.recv.side_effect = [payload[:half].encode(), payload[half:].encode()]

        self.assertEqual(TcpListener.read_request(connection),
                         {"action": "FORECAST", "city": "Ariel"})

    def test_a_connection_closed_early_raises(self, socket_class):
        connection = MagicMock()
        connection.recv.side_effect = [b'{"action":', b""]

        with self.assertRaises(ValueError):
            TcpListener.read_request(connection)

    def test_a_probe_that_says_nothing_is_not_an_error(self, socket_class):
        """Render's health probe connects every few seconds and sends nothing."""
        listener = self.listener(socket_class)
        connection = MagicMock()
        connection.recv.side_effect = [b""]

        with self.assertLogs("src.servers.app_server.tcp_listener", level="INFO") as logs:
            listener.handle(connection, CLIENT)

        self.assertFalse([r for r in logs.records if r.levelname == "ERROR"])
        connection.sendall.assert_not_called()
        connection.close.assert_called_once()

    def test_it_answers_and_closes(self, socket_class):
        listener = self.listener(socket_class)
        connection = MagicMock()
        connection.recv.side_effect = [json.dumps({"action": "FTP_LIST"}).encode(), b""]

        listener.handle(connection, CLIENT)

        listener.router.handle.assert_called_once_with({"action": "FTP_LIST"})
        connection.sendall.assert_called_once_with(b"Wear a jacket!")
        connection.close.assert_called_once()

    def test_a_bad_request_gets_an_error_back(self, socket_class):
        listener = self.listener(socket_class)
        connection = MagicMock()
        connection.recv.side_effect = [b"not json", b""]

        listener.handle(connection, CLIENT)

        self.assertTrue(connection.sendall.call_args[0][0].startswith(b"Error:"))
        connection.close.assert_called_once()

    def test_a_busy_port_exits(self, socket_class):
        socket_class.return_value.bind.side_effect = OSError

        with self.assertRaises(SystemExit):
            TcpListener(MagicMock())

    def test_an_internal_failure_is_not_described_to_the_peer(self, socket_class):
        """The details belong in the log: an exception text can name paths and code."""
        listener = self.listener(socket_class)
        listener.router.handle.side_effect = RuntimeError("secret /srv/app/data path")
        connection = MagicMock()
        connection.recv.side_effect = [json.dumps({"action": "FTP_LIST"}).encode()]

        listener.handle(connection, CLIENT)

        sent = connection.sendall.call_args[0][0]
        self.assertTrue(sent.startswith(b"Error:"))
        self.assertNotIn(b"secret", sent)

    def test_a_request_that_trickles_in_is_cut_off(self, socket_class):
        """Slowloris: one byte per read must not hold a thread for ever."""
        connection = MagicMock()
        connection.recv.return_value = b" "          # never a complete object
        clock = iter([0.0, 1.0, 5.0, 9.0, 11.0, 12.0])

        with patch("src.servers.app_server.tcp_listener.time.monotonic",
                   side_effect=lambda: next(clock)):
            with self.assertRaises(ValueError) as caught:
                TcpListener.read_request(connection)

        self.assertIn("too long", str(caught.exception))

    def test_connections_beyond_the_ceiling_are_refused_not_queued(self, socket_class):
        listener = self.listener(socket_class)
        connections = [MagicMock() for _ in range(3)]
        socket_class.return_value.accept.side_effect = (
            [(c, ("127.0.0.1", 40000 + i)) for i, c in enumerate(connections)] + [OSError()])
        listener.slots = threading.BoundedSemaphore(1)

        with patch("src.servers.app_server.tcp_listener.threading.Thread") as thread:
            listener.serve_forever()

        self.assertEqual(thread.call_count, 1)               # only the first got a thread
        for refused in connections[1:]:
            self.assertTrue(refused.sendall.call_args[0][0].startswith(b"Error:"))
            refused.close.assert_called_once()

    def test_the_slot_is_given_back_after_every_request(self, socket_class):
        listener = self.listener(socket_class)
        listener.slots = threading.BoundedSemaphore(1)
        listener.slots.acquire()
        connection = MagicMock()
        connection.recv.side_effect = [b""]

        listener._serve(connection, CLIENT)

        self.assertTrue(listener.slots.acquire(blocking=False))


@patch("src.servers.app_server.rudp_listener.socket.socket")
class TestRudpListener(unittest.TestCase):

    def listener(self, socket_class):
        listener = RudpListener(MagicMock())
        listener.router.handle.return_value = "answer"
        self.sock = socket_class.return_value
        return listener

    @patch("src.servers.app_server.rudp_listener.threading.Thread")
    def test_a_valid_handshake_is_acknowledged_and_dispatched(self, thread, socket_class):
        listener = self.listener(socket_class)

        listener.accept_request('SEQ:1|{"action": "FTP_LIST"}', CLIENT)

        listener.sock.sendto.assert_called_once_with(HANDSHAKE_ACK, CLIENT)
        thread.assert_called_once()
        self.assertIn(CLIENT, listener.active_transfers)

    @patch("src.servers.app_server.rudp_listener.threading.Thread")
    def test_a_repeat_is_re_acknowledged_without_a_second_transfer(self, thread, socket_class):
        """The client only resends because it never saw the first ACK."""
        listener = self.listener(socket_class)
        listener.active_transfers.add(CLIENT)

        listener.accept_request('SEQ:1|{"action": "FTP_LIST"}', CLIENT)

        listener.sock.sendto.assert_called_once_with(HANDSHAKE_ACK, CLIENT)
        thread.assert_not_called()

    @patch("src.servers.app_server.rudp_listener.threading.Thread")
    def test_transfers_beyond_the_ceiling_are_not_started(self, thread, socket_class):
        """UDP source addresses are free to forge, so one cap covers everyone."""
        from src.config import MAX_RUDP_TRANSFERS
        listener = self.listener(socket_class)
        listener.active_transfers.update(("10.0.0.1", port) for port in range(MAX_RUDP_TRANSFERS))

        listener.accept_request('SEQ:1|{"action": "FTP_LIST"}', CLIENT)

        listener.sock.sendto.assert_not_called()           # not even acknowledged
        thread.assert_not_called()
        self.assertNotIn(CLIENT, listener.active_transfers)

    @patch("src.servers.app_server.rudp_listener.threading.Thread")
    def test_a_client_already_served_is_still_acknowledged_at_the_ceiling(self, thread, socket_class):
        from src.config import MAX_RUDP_TRANSFERS
        listener = self.listener(socket_class)
        listener.active_transfers.update(("10.0.0.1", port) for port in range(MAX_RUDP_TRANSFERS - 1))
        listener.active_transfers.add(CLIENT)

        listener.accept_request('SEQ:1|{"action": "FTP_LIST"}', CLIENT)

        listener.sock.sendto.assert_called_once_with(HANDSHAKE_ACK, CLIENT)

    @patch("src.servers.app_server.rudp_listener.threading.Thread")
    def test_a_malformed_request_blocks_nothing(self, thread, socket_class):
        """
        The client used to be marked active before the JSON was parsed, so one
        bad request locked it out of every future transfer.
        """
        listener = self.listener(socket_class)

        listener.accept_request("SEQ:1|{not json", CLIENT)

        listener.sock.sendto.assert_not_called()
        thread.assert_not_called()
        self.assertNotIn(CLIENT, listener.active_transfers)

    @patch("src.servers.app_server.rudp_listener.RudpSender")
    def test_the_transfer_slot_is_freed_even_after_a_failure(self, sender, socket_class):
        listener = self.listener(socket_class)
        listener.active_transfers.add(CLIENT)
        listener.router.handle.side_effect = RuntimeError("boom")

        listener.answer({"action": "FTP_LIST"}, CLIENT)

        self.assertNotIn(CLIENT, listener.active_transfers)

    @patch("src.servers.app_server.rudp_listener.RudpSender")
    def test_an_oversized_answer_is_refused(self, sender, socket_class):
        listener = self.listener(socket_class)
        listener.router.handle.return_value = "X" * (1024 * 1024)

        listener.answer({"action": "FTP_GET"}, CLIENT)

        sent = sender.return_value.send.call_args[0][0]
        self.assertTrue(sent.startswith("Error:"))
        self.assertIn("limit", sent)

    @patch("src.servers.app_server.rudp_listener.RudpSender")
    def test_an_answer_within_the_limit_is_sent_unchanged(self, sender, socket_class):
        listener = self.listener(socket_class)

        listener.answer({"action": "FTP_LIST"}, CLIENT)

        self.assertEqual(sender.return_value.send.call_args[0][0], "answer")


if __name__ == "__main__":
    unittest.main()
