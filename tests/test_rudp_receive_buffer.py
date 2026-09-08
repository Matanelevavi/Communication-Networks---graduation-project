import unittest

from src.rudp.receive_buffer import ReceiveBuffer


class TestInOrderDelivery(unittest.TestCase):

    def setUp(self):
        self.buffer = ReceiveBuffer(capacity=4)

    def test_an_expected_chunk_is_delivered_immediately(self):
        """In-order data costs no buffer at all, so the window stays open."""
        self.assertTrue(self.buffer.accept(1, b"abc"))

        self.assertEqual(self.buffer.payload(), b"abc")
        self.assertEqual(self.buffer.next_expected, 2)
        self.assertEqual(self.buffer.advertised_window, 4)

    def test_a_whole_stream_in_order(self):
        for seq, part in enumerate([b"aa", b"bb", b"cc"], start=1):
            self.buffer.accept(seq, part)

        self.assertEqual(self.buffer.payload(), b"aabbcc")
        self.assertTrue(self.buffer.is_complete(total=3))

    def test_an_incomplete_stream_is_not_complete(self):
        self.buffer.accept(1, b"aa")

        self.assertFalse(self.buffer.is_complete(total=3))


class TestOutOfOrder(unittest.TestCase):

    def setUp(self):
        self.buffer = ReceiveBuffer(capacity=4)

    def test_an_early_chunk_is_held_and_costs_a_slot(self):
        self.assertTrue(self.buffer.accept(2, b"bb"))

        self.assertEqual(self.buffer.payload(), b"")
        self.assertEqual(self.buffer.advertised_window, 3)

    def test_filling_the_gap_drains_everything_behind_it(self):
        self.buffer.accept(3, b"cc")
        self.buffer.accept(2, b"bb")
        self.assertEqual(self.buffer.advertised_window, 2)

        self.buffer.accept(1, b"aa")

        self.assertEqual(self.buffer.payload(), b"aabbcc")
        self.assertEqual(self.buffer.next_expected, 4)
        self.assertEqual(self.buffer.advertised_window, 4)   # the buffer emptied

    def test_reassembly_does_not_depend_on_arrival_order(self):
        for seq, part in ((4, b"dd"), (1, b"aa"), (3, b"cc"), (2, b"bb")):
            self.buffer.accept(seq, part)

        self.assertEqual(self.buffer.payload(), b"aabbccdd")


class TestBackpressure(unittest.TestCase):

    def test_a_full_buffer_refuses_a_new_chunk(self):
        """Refusing is the signal: an unacknowledged chunk gets resent later."""
        buffer = ReceiveBuffer(capacity=2)
        self.assertTrue(buffer.accept(2, b"bb"))
        self.assertTrue(buffer.accept(3, b"cc"))

        self.assertTrue(buffer.is_full)
        self.assertEqual(buffer.advertised_window, 0)
        self.assertFalse(buffer.accept(4, b"dd"))

    def test_a_full_buffer_still_accepts_the_chunk_it_is_waiting_for(self):
        """
        The head of the window is what unblocks everything, so it must always
        get through. This is what keeps a zero window from deadlocking.
        """
        buffer = ReceiveBuffer(capacity=2)
        buffer.accept(2, b"bb")
        buffer.accept(3, b"cc")

        self.assertTrue(buffer.accept(1, b"aa"))
        self.assertEqual(buffer.payload(), b"aabbcc")
        self.assertEqual(buffer.advertised_window, 2)

    def test_a_capacity_of_zero_is_raised_to_one(self):
        self.assertEqual(ReceiveBuffer(capacity=0).capacity, 1)


class TestDuplicates(unittest.TestCase):

    def setUp(self):
        self.buffer = ReceiveBuffer(capacity=4)

    def test_a_redelivered_chunk_is_accepted_but_changes_nothing(self):
        self.buffer.accept(1, b"aa")

        self.assertTrue(self.buffer.accept(1, b"aa"))
        self.assertEqual(self.buffer.payload(), b"aa")

    def test_a_repeated_held_chunk_does_not_take_a_second_slot(self):
        self.buffer.accept(2, b"bb")
        self.buffer.accept(2, b"bb")

        self.assertEqual(self.buffer.advertised_window, 3)

    def test_it_knows_what_it_has_already_seen(self):
        self.buffer.accept(1, b"aa")
        self.buffer.accept(3, b"cc")

        self.assertTrue(self.buffer.has_seen(1))     # delivered
        self.assertTrue(self.buffer.has_seen(3))     # held
        self.assertFalse(self.buffer.has_seen(2))    # still missing


if __name__ == "__main__":
    unittest.main()
