import socket
import unittest
from unittest.mock import MagicMock, patch

from src.rudp.sender import RudpSender
from tests.helpers import PEER, STRANGER, FakeNetwork, ThrottlingNetwork


@patch("src.rudp.sender.SIMULATE_DELAY", False)
@patch("src.rudp.sender.SIMULATE_LOSS", False)
class TestTransfer(unittest.TestCase):

    def test_chunks_are_numbered_and_carry_the_total(self, *_):
        net = FakeNetwork()

        self.assertTrue(RudpSender(net, chunk_size=10).send("Hello World 123", PEER))

        self.assertTrue(net.sent[0].startswith(b"SEQ:1|TOTAL:2|"))
        self.assertIn(b"Hello Worl", net.sent[0])
        self.assertTrue(net.sent[1].startswith(b"SEQ:2|TOTAL:2|"))
        self.assertIn(b"d 123", net.sent[1])

    def test_every_chunk_is_sent_once_when_nothing_is_lost(self, *_):
        """
        Without the in-flight guard the sender resends the whole window on
        every pass, a retransmission storm it inflicts on itself.
        """
        net = FakeNetwork()
        sender = RudpSender(net, chunk_size=10)

        self.assertTrue(sender.send("A" * 100, PEER))

        self.assertEqual(len(net.sent), 10)
        self.assertEqual(sender.retransmissions, 0)
        self.assertEqual(sorted(net.delivered), list(range(1, 11)))

    def test_a_lost_chunk_is_retransmitted(self, *_):
        net = FakeNetwork(drop_once=[2])
        sender = RudpSender(net, chunk_size=10)

        self.assertTrue(sender.send("A" * 50, PEER))

        self.assertGreaterEqual(sender.retransmissions, 1)
        self.assertEqual(sorted(set(net.delivered)), [1, 2, 3, 4, 5])

    def test_acknowledgements_from_a_stranger_are_ignored(self, *_):
        """A forged ACK from another address must not acknowledge a chunk."""
        net = FakeNetwork(spoof=[(b"ACK:1", STRANGER), (b"ACK:2", STRANGER)])

        self.assertTrue(RudpSender(net, chunk_size=10).send("Hello World 123", PEER))

        self.assertEqual(sorted(set(net.delivered)), [1, 2])

    def test_the_transfer_is_abandoned_when_nothing_comes_back(self, *_):
        sock = MagicMock()
        sock.recvfrom.side_effect = socket.timeout

        self.assertFalse(RudpSender(sock, chunk_size=10).send("Hello World 123", PEER))

    def test_a_disconnected_peer_stops_the_transfer(self, *_):
        sock = MagicMock()
        sock.recvfrom.side_effect = ConnectionResetError

        self.assertFalse(RudpSender(sock, chunk_size=10).send("data", PEER))

    def test_the_window_opens_during_a_long_transfer(self, *_):
        net = FakeNetwork()
        sender = RudpSender(net, chunk_size=10)

        sender.send("A" * 400, PEER)

        self.assertGreater(sender.congestion.cwnd, 1.0)


@patch("src.rudp.sender.SIMULATE_DELAY", False)
@patch("src.rudp.sender.SIMULATE_LOSS", False)
class TestPayloadTypes(unittest.TestCase):

    def test_text(self, *_):
        net = FakeNetwork()
        self.assertTrue(RudpSender(net, chunk_size=1000).send("hello", PEER))
        self.assertIn(b"hello", net.sent[0])

    def test_bytes(self, *_):
        net = FakeNetwork()
        self.assertTrue(RudpSender(net, chunk_size=1000).send(b"\x00\x01binary", PEER))
        self.assertIn(b"\x00\x01binary", net.sent[0])

    def test_none_is_sent_as_one_empty_chunk(self, *_):
        net = FakeNetwork()
        self.assertTrue(RudpSender(net, chunk_size=1000).send(None, PEER))
        self.assertEqual(len(net.sent), 1)


class TestFailureSimulation(unittest.TestCase):

    @patch("src.rudp.sender.SIMULATE_DELAY", False)
    @patch("src.rudp.sender.LOSS_RATE", 1.0)
    @patch("src.rudp.sender.SIMULATE_LOSS", True)
    def test_total_loss_gives_up_instead_of_looping(self):
        net = FakeNetwork()

        self.assertFalse(RudpSender(net, chunk_size=10).send("data", PEER))

    @patch("src.rudp.sender.SIMULATE_LOSS", False)
    @patch("src.rudp.sender.DELAY_SECONDS", 0.05)
    @patch("src.rudp.sender.DELAY_SEQ", 2)
    @patch("src.rudp.sender.SIMULATE_DELAY", True)
    def test_the_configured_packet_is_delayed(self):
        net = FakeNetwork()

        with patch("src.rudp.sender.time.sleep") as sleep:
            RudpSender(net, chunk_size=10).send("A" * 30, PEER)

        sleep.assert_called_once_with(0.05)


if __name__ == "__main__":
    unittest.main()


@patch("src.rudp.sender.SIMULATE_DELAY", False)
@patch("src.rudp.sender.SIMULATE_LOSS", False)
class TestFlowControl(unittest.TestCase):
    """
    Two limits decide how much may be in flight, and the smaller one wins:
    congestion control measures the network, flow control obeys the receiver.
    """

    def sender(self, cwnd=10.0, peer_window=None):
        sender = RudpSender(MagicMock(), chunk_size=10)
        sender.congestion.cwnd = cwnd
        sender.peer_window = peer_window
        return sender

    def test_without_an_advertisement_only_congestion_control_applies(self, *_):
        self.assertEqual(self.sender(cwnd=10.0).effective_window(), 10)

    def test_a_smaller_receiver_window_wins(self, *_):
        self.assertEqual(self.sender(cwnd=10.0, peer_window=3).effective_window(), 3)

    def test_a_larger_receiver_window_leaves_congestion_control_in_charge(self, *_):
        self.assertEqual(self.sender(cwnd=4.0, peer_window=99).effective_window(), 4)

    def test_a_zero_window_still_lets_one_packet_through(self, *_):
        """
        Stopping completely would deadlock: the chunk that frees the receiver's
        buffer is exactly the one at the head of this window.
        """
        self.assertEqual(self.sender(cwnd=10.0, peer_window=0).effective_window(), 1)

    def test_being_receiver_limited_is_counted(self, *_):
        sender = self.sender(cwnd=10.0, peer_window=2)

        sender.effective_window()
        sender.effective_window()

        self.assertEqual(sender.flow_limited, 2)

    def test_an_advertisement_is_read_off_every_acknowledgement(self, *_):
        net = FakeNetwork()
        sender = RudpSender(net, chunk_size=10)

        sender.send("A" * 30, PEER)

        # FakeNetwork answers with a bare ACK, so nothing was ever advertised
        self.assertIsNone(sender.peer_window)

    def test_a_slow_receiver_throttles_a_fast_sender(self, *_):
        """
        End to end. The first burst goes out before the receiver has said
        anything, exactly as an initial window does in TCP; every burst after
        that has to respect the advertisement.
        """
        net = ThrottlingNetwork(window=2)
        sender = RudpSender(net, chunk_size=10)
        sender.congestion.cwnd = 20.0

        self.assertTrue(sender.send("A" * 1000, PEER))

        self.assertEqual(sender.peer_window, 2)
        self.assertGreater(sender.flow_limited, 0)
        self.assertGreater(len(net.bursts), 1)
        self.assertLessEqual(max(net.bursts[1:]), 2)

    def test_a_generous_receiver_does_not_throttle_anything(self, *_):
        net = ThrottlingNetwork(window=50)
        sender = RudpSender(net, chunk_size=10)

        self.assertTrue(sender.send("A" * 1000, PEER))
        self.assertEqual(sender.flow_limited, 0)
