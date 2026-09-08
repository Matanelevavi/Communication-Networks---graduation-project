import unittest

from src.rudp.congestion import CongestionControl


class TestSlowStart(unittest.TestCase):

    def setUp(self):
        self.cc = CongestionControl(max_cwnd=20.0, ssthresh=4.0)

    def test_starts_at_one_packet(self):
        self.assertEqual(self.cc.cwnd, 1.0)
        self.assertEqual(self.cc.window, 1)
        self.assertTrue(self.cc.in_slow_start)

    def test_grows_by_one_per_ack_below_the_threshold(self):
        """One per ACK means the window doubles every round trip."""
        self.cc.on_ack()
        self.assertEqual(self.cc.cwnd, 2.0)
        self.cc.on_ack()
        self.assertEqual(self.cc.cwnd, 3.0)

    def test_switches_to_avoidance_at_the_threshold(self):
        for _ in range(3):
            self.cc.on_ack()

        self.assertEqual(self.cc.cwnd, 4.0)
        self.assertFalse(self.cc.in_slow_start)

        self.cc.on_ack()
        self.assertAlmostEqual(self.cc.cwnd, 4.25)   # +1/cwnd, one packet per RTT

    def test_never_exceeds_the_maximum(self):
        cc = CongestionControl(max_cwnd=20.0, ssthresh=1000.0)
        for _ in range(200):
            cc.on_ack()

        self.assertEqual(cc.cwnd, 20.0)


class TestLossResponse(unittest.TestCase):

    def test_timeout_restarts_slow_start(self):
        cc = CongestionControl()
        cc.cwnd = 8.0

        cc.on_timeout()

        self.assertEqual(cc.ssthresh, 4.0)
        self.assertEqual(cc.cwnd, 1.0)
        self.assertTrue(cc.in_slow_start)

    def test_triple_duplicate_ack_halves_without_collapsing(self):
        """Later packets still arrive, so the path works: halve, do not reset."""
        cc = CongestionControl()
        cc.cwnd = 8.0

        cc.on_triple_duplicate_ack()

        self.assertEqual(cc.ssthresh, 4.0)
        self.assertEqual(cc.cwnd, 4.0)

    def test_the_window_never_drops_below_one(self):
        cc = CongestionControl()
        cc.cwnd = 1.0

        cc.on_timeout()
        cc.on_triple_duplicate_ack()

        self.assertGreaterEqual(cc.cwnd, 1.0)
        self.assertEqual(cc.window, 1)


if __name__ == "__main__":
    unittest.main()
