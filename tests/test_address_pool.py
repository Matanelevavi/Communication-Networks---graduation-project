import time
import unittest

from src.servers.address_pool import AddressPool

ALICE = ("127.0.0.1", 12345)
BOB = ("127.0.0.1", 12346)


class TestReservation(unittest.TestCase):

    def setUp(self):
        self.pool = AddressPool(["10.0.0.1", "10.0.0.2"])

    def test_reserving_takes_an_address_out_of_the_free_list(self):
        ip = self.pool.reserve(ALICE)

        self.assertEqual(ip, "10.0.0.1")
        self.assertEqual(self.pool.available, 1)
        self.assertEqual(self.pool.held_by(ALICE), "10.0.0.1")

    def test_a_repeated_discover_does_not_consume_a_second_address(self):
        """The client retransmits now, so reserving has to be idempotent."""
        first = self.pool.reserve(ALICE)
        second = self.pool.reserve(ALICE)

        self.assertEqual(first, second)
        self.assertEqual(self.pool.available, 1)

    def test_two_clients_get_different_addresses(self):
        self.assertNotEqual(self.pool.reserve(ALICE), self.pool.reserve(BOB))

    def test_an_empty_pool_reserves_nothing(self):
        self.pool.reserve(ALICE)
        self.pool.reserve(BOB)

        self.assertIsNone(self.pool.reserve(("127.0.0.1", 9)))

    def test_withdrawing_returns_the_address(self):
        self.pool.reserve(ALICE)

        self.assertEqual(self.pool.withdraw(ALICE), "10.0.0.1")
        self.assertEqual(self.pool.available, 2)
        self.assertIsNone(self.pool.held_by(ALICE))

    def test_withdrawing_nothing_is_harmless(self):
        self.assertIsNone(self.pool.withdraw(ALICE))
        self.assertEqual(self.pool.available, 2)


class TestLease(unittest.TestCase):

    def setUp(self):
        self.pool = AddressPool(["10.0.0.1", "10.0.0.2"])

    def test_committing_turns_a_reservation_into_a_lease(self):
        ip = self.pool.reserve(ALICE)

        self.assertTrue(self.pool.commit(ALICE, ip))
        self.assertEqual(self.pool.leased[ALICE].ip, ip)
        self.assertNotIn(ALICE, self.pool.reserved)

    def test_committing_an_address_that_was_never_offered_fails(self):
        self.assertFalse(self.pool.commit(ALICE, "10.0.0.99"))

    def test_a_repeated_request_renews_instead_of_failing(self):
        """A lost ACK means the client simply asks again."""
        ip = self.pool.reserve(ALICE)
        self.pool.commit(ALICE, ip)

        self.assertTrue(self.pool.commit(ALICE, ip))

    def test_releasing_returns_the_address(self):
        ip = self.pool.reserve(ALICE)
        self.pool.commit(ALICE, ip)

        self.assertTrue(self.pool.release(ALICE, ip))
        self.assertEqual(self.pool.available, 2)

    def test_releasing_somebody_elses_address_fails(self):
        ip = self.pool.reserve(ALICE)
        self.pool.commit(ALICE, ip)

        self.assertFalse(self.pool.release(BOB, ip))
        self.assertEqual(self.pool.available, 1)


class TestExpiry(unittest.TestCase):

    def test_an_offer_nobody_claimed_comes_back(self):
        """This is what stops a lost REQUEST from leaking an address forever."""
        pool = AddressPool(["10.0.0.1"], hold_time=0.0)
        pool.reserve(ALICE)

        self.assertEqual(pool.reclaim_expired(), ["10.0.0.1"])
        self.assertEqual(pool.available, 1)

    def test_a_lease_nobody_released_comes_back(self):
        pool = AddressPool(["10.0.0.1"], lease_time=0.0)
        pool.commit(ALICE, pool.reserve(ALICE))

        self.assertEqual(pool.reclaim_expired(), ["10.0.0.1"])
        self.assertEqual(pool.available, 1)

    def test_a_live_reservation_survives(self):
        pool = AddressPool(["10.0.0.1"], hold_time=60.0)
        pool.reserve(ALICE)

        self.assertEqual(pool.reclaim_expired(), [])
        self.assertEqual(pool.available, 0)


class TestDeclines(unittest.TestCase):

    def setUp(self):
        self.pool = AddressPool(["10.0.0.1"], hold_time=60.0)

    def test_a_declined_client_is_remembered(self):
        """The backup answers late, so it has to remember that it lost."""
        self.pool.decline(ALICE)

        self.assertTrue(self.pool.has_declined(ALICE))
        self.assertFalse(self.pool.has_declined(BOB))

    def test_a_new_discover_clears_the_record(self):
        self.pool.decline(ALICE)
        self.pool.forget_decline(ALICE)

        self.assertFalse(self.pool.has_declined(ALICE))

    def test_the_record_lapses_with_time(self):
        pool = AddressPool(["10.0.0.1"], hold_time=0.0)
        pool.decline(ALICE)

        self.assertFalse(pool.has_declined(ALICE))


if __name__ == "__main__":
    unittest.main()
