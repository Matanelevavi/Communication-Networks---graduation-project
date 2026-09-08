import unittest

from src.rudp.window import TransferWindow


class TestTransferWindow(unittest.TestCase):

    def setUp(self):
        self.window = TransferWindow({i: b"x" for i in range(1, 6)})

    def test_everything_starts_pending(self):
        self.assertEqual(sorted(self.window.pending), [1, 2, 3, 4, 5])
        self.assertEqual(self.window.window_start, 1)

    def test_window_range_is_bounded_by_the_total(self):
        self.assertEqual(list(self.window.window_range(3, 5)), [1, 2, 3])
        self.assertEqual(list(self.window.window_range(99, 5)), [1, 2, 3, 4, 5])

    def test_a_sent_chunk_is_not_sent_again(self):
        self.window.mark_sent(1)

        self.assertTrue(self.window.is_in_flight(1))
        self.assertFalse(self.window.is_first_send(1))

    def test_acknowledging_the_head_slides_the_window(self):
        self.window.mark_sent(1)

        self.assertTrue(self.window.acknowledge(1))
        self.assertEqual(self.window.window_start, 2)

    def test_the_window_slides_over_everything_already_acknowledged(self):
        for seq in (1, 2, 3):
            self.window.mark_sent(seq)
        self.window.acknowledge(2)
        self.window.acknowledge(3)

        self.assertEqual(self.window.window_start, 1)   # the head is still missing
        self.window.acknowledge(1)
        self.assertEqual(self.window.window_start, 4)   # now it jumps past all three

    def test_acknowledgements_past_a_gap_count_as_duplicates(self):
        """The selective equivalent of TCP's duplicate ACK."""
        for seq in (1, 2, 3, 4):
            self.window.mark_sent(seq)

        self.window.acknowledge(2)
        self.window.acknowledge(3)
        self.window.acknowledge(4)

        self.assertTrue(self.window.head_is_missing())
        self.assertEqual(self.window.duplicate_acks, 3)

    def test_a_repeat_acknowledgement_is_not_progress(self):
        self.window.mark_sent(1)
        self.window.acknowledge(1)

        self.assertFalse(self.window.acknowledge(1))

    def test_a_timeout_puts_everything_back_on_the_wire(self):
        self.window.mark_sent(1)
        self.window.mark_sent(2)

        self.window.on_timeout()

        self.assertEqual(self.window.in_flight, set())
        self.assertEqual(self.window.timeouts, 1)
        self.assertEqual(self.window.duplicate_acks, 0)

    def test_progress_clears_the_timeout_count(self):
        self.window.mark_sent(1)
        self.window.on_timeout()

        self.window.mark_sent(1)
        self.window.acknowledge(1)

        self.assertEqual(self.window.timeouts, 0)


if __name__ == "__main__":
    unittest.main()
