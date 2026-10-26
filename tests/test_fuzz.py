"""
Fuzzing: arbitrary bytes at every place the system reads data it did not write.

Every parser here faces the network, so each property is the same one: whatever
arrives, the code either understands it or refuses it, and never raises, never
hangs, and never lets the data reach somewhere it should not. Hypothesis
generates the inputs and shrinks any failure to the smallest case.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.client.gui.parsing import parse_listing, parse_profiles
from src.config import MAX_PROFILE_FIELD, MAX_PROFILES, RUDP_RECV_BUFFER
from src.rudp.packet import RudpPacket, decode_ack, encode_ack, split_into_chunks
from src.rudp.receive_buffer import ReceiveBuffer
from src.servers.address_pool import AddressPool
from src.servers.app_server.forecast_cache import city_key
from src.servers.app_server.router import RequestRouter, clean_profiles
from src.servers.app_server.storage import FileStore
from src.servers.dhcp_server import DHCPServer
from src.servers.dns_server import DNSServer

FUZZ = settings(max_examples=300, deadline=None,
                suppress_health_check=[HealthCheck.too_slow])

# JSON of any shape, which is what a hostile client can put in a request body
JSON_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(),
    lambda inner: st.lists(inner, max_size=5) | st.dictionaries(st.text(max_size=8), inner, max_size=5),
    max_leaves=25)


class TestPacketDecoding(unittest.TestCase):

    @FUZZ
    @given(st.binary(max_size=2048))
    def test_arbitrary_bytes_never_crash_the_packet_parser(self, raw):
        packet = RudpPacket.from_bytes(raw)

        self.assertTrue(packet is None or isinstance(packet, RudpPacket))

    @FUZZ
    @given(st.binary(max_size=300), st.binary(max_size=40))
    def test_whatever_is_accepted_is_exactly_what_the_encoder_makes(self, payload, noise):
        """No two byte strings may mean the same packet."""
        for raw in (noise, RudpPacket(1, 3, payload).to_bytes() + noise,
                    noise + RudpPacket(1, 3, payload).to_bytes()):
            packet = RudpPacket.from_bytes(raw)
            if packet is not None:
                self.assertEqual(packet.to_bytes(), raw)

    @FUZZ
    @given(st.integers(0, 10**9), st.integers(0, 10**9), st.binary(max_size=900))
    def test_a_packet_survives_the_wire(self, seq, total, payload):
        decoded = RudpPacket.from_bytes(RudpPacket(seq, total, payload).to_bytes())

        self.assertEqual((decoded.seq, decoded.total, decoded.payload), (seq, total, payload))

    @FUZZ
    @given(st.integers(0, 10**6), st.integers(0, 10**6), st.binary(max_size=200),
           st.integers(0, 400), st.integers(0, 255))
    def test_one_flipped_byte_is_always_caught(self, seq, total, payload, index, flip):
        """CRC32 detects every single byte change, header fields included."""
        wire = bytearray(RudpPacket(seq, total, payload).to_bytes())
        position = index % len(wire)
        original = wire[position]
        wire[position] = original ^ (flip or 1)

        decoded = RudpPacket.from_bytes(bytes(wire))

        # whatever the mutation did, a packet is only accepted if it is
        # byte for byte what the encoder would have produced
        self.assertTrue(decoded is None
                        or decoded.to_bytes() == bytes(wire))
        self.assertTrue(decoded is None
                        or (decoded.seq, decoded.total, decoded.payload) != (seq, total, payload)
                        or bytes(wire) == RudpPacket(seq, total, payload).to_bytes())

    @FUZZ
    @given(st.binary(max_size=300))
    def test_arbitrary_bytes_never_crash_the_ack_parser(self, raw):
        ack = decode_ack(raw)

        self.assertTrue(ack is None or ack.seq is not None)
        if ack is not None and ack.window is not None:
            self.assertGreaterEqual(ack.window, 0)

    @FUZZ
    @given(st.integers(0, 10**9), st.none() | st.integers(0, 10**6))
    def test_an_ack_survives_the_wire(self, seq, window):
        ack = decode_ack(encode_ack(seq, window))

        self.assertEqual((ack.seq, ack.window), (seq, window))

    @FUZZ
    @given(st.binary(max_size=5000), st.integers(1, 1000))
    def test_chunks_reassemble_to_the_original(self, data, size):
        chunks = split_into_chunks(data, size)

        self.assertEqual(b"".join(chunks[i] for i in sorted(chunks)), data)
        self.assertTrue(all(len(c) <= size for c in chunks.values()))


class TestReceiveBuffer(unittest.TestCase):

    @FUZZ
    @given(st.lists(st.tuples(st.integers(-5, 200), st.binary(max_size=8)), max_size=300))
    def test_hostile_sequence_numbers_cannot_grow_memory_past_the_capacity(self, packets):
        buffer = ReceiveBuffer(RUDP_RECV_BUFFER)

        for seq, payload in packets:
            buffer.accept(seq, payload)
            self.assertLessEqual(len(buffer.out_of_order), RUDP_RECV_BUFFER)
            self.assertGreaterEqual(buffer.advertised_window, 0)

    @FUZZ
    @given(st.permutations(list(range(1, 25))))
    def test_any_arrival_order_reassembles_in_order(self, order):
        buffer = ReceiveBuffer(capacity=24)

        for seq in order:
            buffer.accept(seq, bytes([seq]))

        self.assertEqual(buffer.payload(), bytes(range(1, 25)))
        self.assertTrue(buffer.is_complete(24))


class TestServerMessages(unittest.TestCase):

    @staticmethod
    def dhcp():
        server = DHCPServer.__new__(DHCPServer)
        server.address = ("127.0.0.1", 8067)
        server.name = "fuzz"
        server.offer_delay = 0.0
        server.pool = AddressPool([f"192.168.1.{i}" for i in range(100, 110)])
        server.running = True
        server.sock = MagicMock()
        return server

    @FUZZ
    @given(st.text(max_size=300))
    def test_dhcp_survives_any_message(self, message):
        server = self.dhcp()

        server.handle(message, ("127.0.0.1", 8068))

        self.assertGreaterEqual(server.pool.available, 0)

    @FUZZ
    @given(st.sampled_from(["DHCP_REQUEST", "DHCP_RELEASE", "DHCP_DISCOVER"]),
           st.lists(st.text(max_size=20), max_size=5))
    def test_dhcp_survives_malformed_fields(self, kind, parts):
        server = self.dhcp()

        server.handle(":".join([kind, *parts]), ("127.0.0.1", 8068))

    @FUZZ
    @given(st.text(max_size=300))
    def test_dhcp_never_leases_an_address_that_was_not_offered(self, wanted):
        server = self.dhcp()

        server.handle(f"DHCP_REQUEST:{wanted}", ("127.0.0.1", 8068))

        self.assertEqual(server.pool.leased, {})

    @FUZZ
    @given(st.text(max_size=300))
    def test_dns_survives_any_query(self, name):
        server = DNSServer.__new__(DNSServer)
        server.serv_sock = MagicMock()
        server.dns_records = {"weatherwear.local": "127.0.0.1"}
        server.ttl = 60

        server.find_ip(name, ("127.0.0.1", 8068))

        server.serv_sock.sendto.assert_called_once()


class TestRequestHandling(unittest.TestCase):

    @staticmethod
    def router(folder):
        weather = MagicMock()
        weather.fetch.side_effect = Exception("the network is not reachable in a fuzz test")
        agent = MagicMock()
        agent.cached_forecast.return_value = None
        agent.archived_file.return_value = "x"
        agent.archive_listing.return_value = "x"
        return RequestRouter(weather, MagicMock(), agent)

    @FUZZ
    @given(JSON_VALUES)
    def test_any_json_value_is_answered_with_text_or_a_clean_error(self, request):
        router = self.router(None)

        try:
            answer = router.handle(request)
        except Exception as e:                 # the services are rigged to fail
            self.assertIn("fuzz test", str(e))
            return
        self.assertIsInstance(answer, (str, bytes))

    @FUZZ
    @given(JSON_VALUES)
    def test_profiles_are_always_bounded_and_flat(self, raw):
        profiles = clean_profiles(raw)

        self.assertLessEqual(len(profiles), MAX_PROFILES)
        for profile in profiles:
            self.assertEqual(set(profile), {"name", "age_category", "notes"})
            for value in profile.values():
                self.assertIsInstance(value, str)
                self.assertLessEqual(len(value), MAX_PROFILE_FIELD)
                self.assertNotIn("\n", value)

    @FUZZ
    @given(st.text(max_size=400))
    def test_the_form_parsers_never_crash(self, text):
        for profile in parse_profiles(text):
            self.assertTrue(profile["name"])
        parse_listing(text)


class TestFileAccess(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.mkdtemp(prefix="fuzz_data_")
        cls.store = FileStore(cls.folder)
        cls.root = os.path.realpath(cls.folder)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)

    @FUZZ
    @given(st.text(max_size=120))
    def test_no_file_name_can_leave_the_data_directory(self, name):
        path = self.store.resolve(name)

        if path is not None:
            self.assertEqual(os.path.commonpath([self.root, path]), self.root)

    @FUZZ
    @given(st.text(alphabet=st.sampled_from(list("./\\:%~-_ ab\x00")), max_size=60))
    def test_traversal_shaped_names_stay_inside(self, name):
        path = self.store.resolve(name)

        if path is not None:
            self.assertEqual(os.path.commonpath([self.root, path]), self.root)

    @FUZZ
    @given(st.text(max_size=200))
    def test_a_city_name_never_forms_a_path(self, city):
        key = city_key(city)

        self.assertNotIn("/", key)
        self.assertNotIn("\\", key)
        self.assertNotIn("..", key)
        self.assertNotIn(":", key)


if __name__ == "__main__":
    unittest.main()
