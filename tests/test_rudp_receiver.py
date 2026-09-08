import socket
import unittest
from unittest.mock import MagicMock

from src.config import RUDP_RECV_BUFFER
from src.rudp.packet import RudpPacket, decode_ack
from src.rudp.receive_buffer import ReceiveBuffer
from src.rudp.receiver import RudpReceiver

TRANSFER = ("127.0.0.1", 55001)
STRANGER = ("127.0.0.1", 7777)


def packets(data: bytes, chunk_size: int) -> list[bytes]:
    total = (len(data) + chunk_size - 1) // chunk_size
    return [RudpPacket(i + 1, total, data[i * chunk_size:(i + 1) * chunk_size]).to_bytes()
            for i in range(total)]


class TestReceiver(unittest.TestCase):

    @staticmethod
    def receiver(*datagrams):
        sock = MagicMock()
        sock.recvfrom.side_effect = list(datagrams) + [socket.timeout()]
        return RudpReceiver(sock), sock

    @staticmethod
    def acked(sock):
        """The sequence numbers acknowledged, in order."""
        return [decode_ack(call[0][0]).seq for call in sock.sendto.call_args_list]

    def test_a_single_chunk_transfer(self):
        rx, sock = self.receiver((RudpPacket(1, 1, b"hello").to_bytes(), TRANSFER))

        self.assertEqual(rx.receive(), b"hello")
        sock.sendto.assert_any_call(f"ACK:1|WIN:{RUDP_RECV_BUFFER}".encode(), TRANSFER)

    def test_out_of_order_chunks_are_reassembled_in_order(self):
        data = b"WeatherWear reliable transfer"
        one, two, three = packets(data, 10)
        rx, _ = self.receiver((one, TRANSFER), (three, TRANSFER), (two, TRANSFER))

        self.assertEqual(rx.receive(), data)

    def test_a_corrupted_chunk_is_dropped_and_not_acknowledged(self):
        good = RudpPacket(1, 1, b"0123456789").to_bytes()
        corrupted = bytearray(good)
        corrupted[-1] ^= 0xFF

        rx, sock = self.receiver((bytes(corrupted), TRANSFER), (good, TRANSFER))

        self.assertEqual(rx.receive(), b"0123456789")
        self.assertEqual(self.acked(sock).count(1), 1)     # only the intact copy

    def test_a_duplicate_chunk_is_acknowledged_again(self):
        """The sender only repeats itself because it never saw the first ACK."""
        one, two = packets(b"0123456789ab", 10)
        rx, sock = self.receiver((one, TRANSFER), (one, TRANSFER), (two, TRANSFER))

        self.assertEqual(rx.receive(), b"0123456789ab")
        self.assertEqual(self.acked(sock).count(1), 2)

    def test_packets_from_another_address_are_ignored(self):
        one, two = packets(b"0123456789ab", 10)
        injected = RudpPacket(2, 2, b"EVIL").to_bytes()

        rx, _ = self.receiver((one, TRANSFER), (injected, STRANGER), (two, TRANSFER))

        self.assertEqual(rx.receive(), b"0123456789ab")

    def test_a_stalled_transfer_times_out(self):
        one, _two = packets(b"0123456789ab", 10)
        rx, _ = self.receiver((one, TRANSFER))

        self.assertIsNone(rx.receive())

    def test_malformed_datagrams_are_skipped(self):
        rx, _ = self.receiver((b"garbage", TRANSFER),
                              (RudpPacket(1, 1, b"ok").to_bytes(), TRANSFER))

        self.assertEqual(rx.receive(), b"ok")


if __name__ == "__main__":
    unittest.main()


class TestFlowControl(unittest.TestCase):
    """The receiver tells the sender how much room it has left."""

    @staticmethod
    def windows(sock):
        return [decode_ack(call[0][0]).window for call in sock.sendto.call_args_list]

    def test_an_in_order_chunk_costs_no_buffer(self):
        sock = MagicMock()
        one, two = packets(b"0123456789ab", 10)
        sock.recvfrom.side_effect = [(one, TRANSFER), (two, TRANSFER), socket.timeout()]

        RudpReceiver(sock, buffer=ReceiveBuffer(capacity=4)).receive()

        self.assertEqual(self.windows(sock)[:2], [4, 4])

    def test_an_early_chunk_shrinks_the_advertised_window(self):
        """Chunk 2 arrives while 1 is missing, so it has to be held."""
        one, two, three = packets(b"0123456789abcdefghij" + b"klmno", 10)
        sock = MagicMock()
        sock.recvfrom.side_effect = [(two, TRANSFER), (three, TRANSFER),
                                     (one, TRANSFER), socket.timeout()]

        RudpReceiver(sock, buffer=ReceiveBuffer(capacity=4)).receive()

        windows = self.windows(sock)
        self.assertEqual(windows[0], 3)      # holding chunk 2
        self.assertEqual(windows[1], 2)      # holding 2 and 3
        self.assertEqual(windows[2], 4)      # 1 arrived, all three drained

    def test_a_chunk_that_does_not_fit_is_left_unacknowledged(self):
        """Refusing to ACK is how the receiver makes the sender wait."""
        chunks = packets(b"A" * 40, 10)
        sock = MagicMock()
        # chunks 2, 3 fill a buffer of two; chunk 4 has nowhere to go
        sock.recvfrom.side_effect = [(chunks[1], TRANSFER), (chunks[2], TRANSFER),
                                     (chunks[3], TRANSFER), socket.timeout()]

        RudpReceiver(sock, buffer=ReceiveBuffer(capacity=2)).receive()

        self.assertEqual([decode_ack(c[0][0]).seq for c in sock.sendto.call_args_list],
                         [2, 3])              # chunk 4 was never acknowledged
