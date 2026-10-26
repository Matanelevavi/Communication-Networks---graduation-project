"""
The protocol lab: a simulated link, the real RUDP sender on it, a Reno model on
the same link, and the API in front of them.

The numbers the page shows come from these runs, so what is asserted here is
what the page is allowed to claim: that data arrives intact, that a clean link
costs nothing, that loss costs something, and that the same inputs always give
the same answer.
"""
import unittest

from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from src.lab.link import Link, LinkExhausted, LossModel
from src.lab.runner import LabParams, payload, run_lab, run_one
from src.rudp.congestion import CongestionControl
from src.web.app import create_app
from src.web.limits import RateLimiter


def run(protocol="RUDP", **overrides):
    return run_one(protocol, LabParams(**{"size_kb": 32, "loss": 0.0, "delay_ms": 40,
                                          "buffer": 8, "seed": 1, **overrides}))


class TestLossModel(unittest.TestCase):

    def test_the_same_packet_gets_the_same_verdict(self):
        model = LossModel(seed=7, rate=0.3)

        self.assertEqual([model.drops("data", 5, 1) for _ in range(5)], [model.drops("data", 5, 1)] * 5)

    def test_a_retransmission_is_a_new_roll_of_the_dice(self):
        model = LossModel(seed=1, rate=0.5)

        verdicts = {model.drops("data", 9, attempt) for attempt in range(1, 40)}

        self.assertEqual(verdicts, {True, False})

    def test_the_rate_is_respected_over_many_packets(self):
        model = LossModel(seed=3, rate=0.2)

        lost = sum(model.drops("data", seq, 1) for seq in range(5000))

        self.assertAlmostEqual(lost / 5000, 0.2, delta=0.03)

    def test_no_loss_means_no_loss(self):
        model = LossModel(seed=1, rate=0.0)

        self.assertFalse(any(model.drops("data", s, 1) for s in range(500)))

    def test_a_different_seed_is_a_different_pattern(self):
        a = [LossModel(1, 0.3).drops("data", s, 1) for s in range(200)]
        b = [LossModel(2, 0.3).drops("data", s, 1) for s in range(200)]

        self.assertNotEqual(a, b)


class TestLink(unittest.TestCase):

    def test_events_come_out_in_time_order_and_the_clock_follows(self):
        link = Link(delay=0.05)
        link.schedule("a", 1, after=0.3)
        link.schedule("b", 2, after=0.1)

        first, second = link.pop(), link.pop()

        self.assertEqual((first.kind, second.kind), ("b", "a"))
        self.assertAlmostEqual(link.now, 0.3)

    def test_a_run_that_never_ends_is_cut_off(self):
        link = Link(delay=0.01, max_events=10)

        with self.assertRaises(LinkExhausted):
            for _ in range(11):
                link.schedule("x", None)


class TestRealRudpOnTheLink(unittest.TestCase):

    def test_a_clean_link_delivers_everything_for_free(self):
        result = run("RUDP")

        self.assertTrue(result["completed"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["retransmissions"], 0)
        self.assertEqual(result["timeouts"], 0)
        self.assertEqual(result["packets_sent"], result["chunks"])

    def test_the_payload_arrives_byte_for_byte_even_with_heavy_loss(self):
        for seed in (1, 2, 3):
            result = run("RUDP", loss=0.15, seed=seed)

            if result["completed"]:
                self.assertTrue(result["verified"], seed)

    def test_loss_costs_retransmissions_and_time(self):
        clean, lossy = run("RUDP"), run("RUDP", loss=0.1)

        self.assertGreater(lossy["retransmissions"], 0)
        self.assertGreater(lossy["duration_ms"], clean["duration_ms"])

    def test_a_longer_delay_is_a_longer_transfer(self):
        self.assertGreater(run("RUDP", delay_ms=200)["duration_ms"],
                           run("RUDP", delay_ms=20)["duration_ms"])

    def test_a_small_receive_buffer_throttles_the_sender(self):
        """Flow control: two packets per round trip, whatever the network could carry."""
        slow, fast = run("RUDP", buffer=2), run("RUDP", buffer=32)

        self.assertGreater(slow["duration_ms"], fast["duration_ms"] * 2)
        self.assertGreater(slow["flow_limited"], 0)

    def test_the_time_matches_what_the_buffer_allows(self):
        """chunks / buffer round trips, within a round trip of rounding."""
        result = run("RUDP", size_kb=32, buffer=2, delay_ms=50)

        expected = result["chunks"] / 2 * 100          # 100 ms round trip
        self.assertAlmostEqual(result["duration_ms"], expected, delta=300)

    def test_it_gives_up_after_four_timeouts_in_a_row_and_says_so(self):
        result = run("RUDP", loss=0.5, seed=3)

        self.assertFalse(result["completed"])
        self.assertFalse(result["verified"])
        self.assertGreaterEqual(result["timeouts"], 4)

    def test_the_window_in_the_trace_obeys_the_algorithm(self):
        """Slow start grows by one per ACK and a timeout collapses the window to 1."""
        summary = run_one("RUDP", LabParams(32, 0.1, 40, 8, 1))
        series = summary["series"]

        self.assertEqual(series[0]["cwnd"], 1.0)
        self.assertTrue(all(p["cwnd"] >= 1 for p in series))
        self.assertTrue(all(p["cwnd"] <= CongestionControl().max_cwnd for p in series))
        if summary["timeouts"]:
            drops = [(a, b) for a, b in zip(series, series[1:]) if b["cwnd"] < a["cwnd"]]
            self.assertTrue(drops)
            self.assertTrue(any(b["cwnd"] == 1.0 for _, b in drops))

    def test_time_never_runs_backwards(self):
        series = run_one("RUDP", LabParams(64, 0.1, 40, 8, 2))["series"]

        self.assertEqual([p["t"] for p in series], sorted(p["t"] for p in series))


class TestRenoModel(unittest.TestCase):

    def test_a_clean_link_costs_nothing(self):
        result = run("TCP")

        self.assertTrue(result["completed"] and result["verified"])
        self.assertEqual(result["retransmissions"], 0)
        self.assertEqual(result["timeouts"], 0)

    def test_both_protocols_take_the_same_time_on_a_clean_link(self):
        """Same window arithmetic, no loss: nothing for them to disagree about."""
        self.assertAlmostEqual(run("TCP")["duration_ms"], run("RUDP")["duration_ms"], delta=1)

    def test_loss_is_survived_and_the_data_is_intact(self):
        result = run("TCP", loss=0.1)

        self.assertTrue(result["completed"] and result["verified"])
        self.assertGreater(result["retransmissions"], 0)

    def test_three_duplicate_acks_trigger_a_fast_retransmit(self):
        found = [run("TCP", size_kb=64, loss=0.05, seed=s)["fast_retransmits"] for s in range(1, 8)]

        self.assertTrue(any(found))

    def test_the_receive_buffer_throttles_it_too(self):
        slow, fast = run("TCP", buffer=2), run("TCP", buffer=32)

        self.assertGreater(slow["duration_ms"], fast["duration_ms"] * 2)


class TestFairComparison(unittest.TestCase):

    def test_both_protocols_lose_the_same_first_transmissions(self):
        """The loss belongs to the packet, not to the order things happened in."""
        runs = run_lab(LabParams(32, 0.1, 40, 8, 4))
        lost = {name: sorted(m["seq"] for m in r["marks"] if m["kind"] == "loss" and m["t"] == m["t"])
                for name, r in runs.items()}

        first = {name: {s for s in seqs if s <= 5} for name, seqs in lost.items()}
        self.assertEqual(first["RUDP"], first["TCP"])

    def test_the_same_inputs_give_the_same_answer(self):
        params = LabParams(48, 0.08, 60, 6, 9)

        self.assertEqual(run_lab(params), run_lab(params))

    def test_a_different_seed_changes_the_run(self):
        a = run_one("RUDP", LabParams(48, 0.1, 40, 8, 1))
        b = run_one("RUDP", LabParams(48, 0.1, 40, 8, 2))

        self.assertNotEqual(a["marks"], b["marks"])

    def test_the_payload_is_the_same_bytes_for_a_seed(self):
        self.assertEqual(payload(LabParams(seed=5)), payload(LabParams(seed=5)))
        self.assertNotEqual(payload(LabParams(seed=5)), payload(LabParams(seed=6)))

    def test_the_output_stays_small_whatever_the_run(self):
        result = run_one("TCP", LabParams(256, 0.45, 400, 1, 3))

        self.assertLessEqual(len(result["series"]), 802)
        self.assertLessEqual(len(result["marks"]), 400)

    def test_thinning_keeps_the_timeouts_visible(self):
        marks = run_one("TCP", LabParams(256, 0.45, 400, 1, 3))["marks"]

        self.assertTrue(any(m["kind"] == "timeout" for m in marks))
        self.assertEqual([m["t"] for m in marks], sorted(m["t"] for m in marks))


class TestBounds(unittest.TestCase):

    def test_values_outside_the_limits_are_refused(self):
        for bad in ({"size_kb": 0}, {"size_kb": 257}, {"loss": -0.1}, {"loss": 0.51},
                    {"delay_ms": 0}, {"delay_ms": 401}, {"buffer": 0}, {"buffer": 65}):
            with self.assertRaises(ValueError, msg=bad):
                LabParams(**bad)

    def test_an_unknown_protocol_is_refused(self):
        with self.assertRaises(ValueError):
            run_one("SCTP", LabParams())

    def test_the_worst_case_is_cheap(self):
        """Public code that does real work: even the nastiest input must be quick."""
        import time
        started = time.perf_counter()
        for seed in (1, 2, 3):
            run_lab(LabParams(256, 0.45, 400, 1, seed))

        self.assertLess(time.perf_counter() - started, 3.0)


class TestLabApi(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(create_app(MagicMock(), RateLimiter(1000), RateLimiter(1000)))

    def post(self, **body):
        return self.client.post("/api/lab", json=body)

    def test_a_default_run_answers_for_both_protocols(self):
        response = self.post()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body["runs"]), {"RUDP", "TCP"})
        self.assertEqual(body["params"]["seed"], 1)
        for run_ in body["runs"].values():
            self.assertTrue(run_["series"])
            self.assertIn("implementation", run_)

    def test_one_protocol_can_be_asked_for_alone(self):
        self.assertEqual(set(self.post(protocols=["TCP"]).json()["runs"]), {"TCP"})

    def test_the_api_says_which_one_is_a_model(self):
        runs = self.post().json()["runs"]

        self.assertIn("model", runs["TCP"]["implementation"])
        self.assertIn("unchanged", runs["RUDP"]["implementation"])

    def test_every_bound_is_enforced_before_any_work_is_done(self):
        for bad in ({"size_kb": 100000}, {"loss": 1}, {"delay_ms": 10**6}, {"buffer": 10**6},
                    {"seed": -1}, {"seed": 2**40}, {"protocols": []}, {"protocols": ["SCTP"]},
                    {"protocols": ["TCP", "RUDP", "TCP"]}, {"loss": "lots"}):
            self.assertEqual(self.post(**bad).status_code, 422, bad)

    def test_the_lab_has_a_budget_of_its_own(self):
        """Playing with sliders must not use up the budget for real forecasts."""
        from src.web.gateway import Exchange
        gateway = MagicMock()
        gateway.archive.return_value = ([], Exchange("TCP", "x", 1.0, 1))
        client = TestClient(create_app(gateway, RateLimiter(1), RateLimiter(3)))

        lab_codes = [client.post("/api/lab", json={}).status_code for _ in range(4)]
        # the lab budget is spent, but the forecast budget is untouched
        archive_code = client.get("/api/archive").status_code

        self.assertEqual(lab_codes, [200, 200, 200, 429])
        self.assertEqual(archive_code, 200)


if __name__ == "__main__":
    unittest.main()
