import unittest
import zlib

from src.rudp.packet import (Ack, RudpPacket, decode_ack, encode_ack,
                             split_into_chunks)


class TestFraming(unittest.TestCase):

    def test_wire_format(self):
        packet = RudpPacket(3, 7, b"data").to_bytes()

        self.assertTrue(packet.startswith(b"SEQ:3|TOTAL:7|CHK:"))
        self.assertTrue(packet.endswith(b"|data"))

    def test_round_trip(self):
        parsed = RudpPacket.from_bytes(RudpPacket(2, 5, b"weather").to_bytes())

        self.assertEqual((parsed.seq, parsed.total, parsed.payload), (2, 5, b"weather"))

    def test_a_payload_containing_the_separator_survives(self):
        parsed = RudpPacket.from_bytes(RudpPacket(1, 1, b"a|b|c").to_bytes())

        self.assertEqual(parsed.payload, b"a|b|c")

    def test_empty_payload(self):
        parsed = RudpPacket.from_bytes(RudpPacket(1, 1, b"").to_bytes())

        self.assertEqual(parsed.payload, b"")


class TestIntegrity(unittest.TestCase):

    def setUp(self):
        self.packet = RudpPacket(2, 5, b"weather").to_bytes()

    def test_corrupted_payload_is_rejected(self):
        tampered = bytearray(self.packet)
        tampered[-1] ^= 0xFF

        self.assertIsNone(RudpPacket.from_bytes(bytes(tampered)))

    def test_corrupted_sequence_number_is_rejected(self):
        """The checksum covers the header, so a changed SEQ does not slip through."""
        self.assertIsNone(RudpPacket.from_bytes(self.packet.replace(b"SEQ:2", b"SEQ:3")))

    def test_corrupted_total_is_rejected(self):
        self.assertIsNone(RudpPacket.from_bytes(self.packet.replace(b"TOTAL:5", b"TOTAL:8")))

    def test_the_checksum_is_not_a_plain_payload_crc(self):
        chk = int(self.packet.split(b"|CHK:")[1].split(b"|")[0])

        self.assertNotEqual(chk, zlib.crc32(b"weather") & 0xFFFFFFFF)

    def test_garbage_is_rejected(self):
        self.assertIsNone(RudpPacket.from_bytes(b"not a packet"))
        self.assertIsNone(RudpPacket.from_bytes(b"SEQ:x|TOTAL:y|CHK:z|data"))
        self.assertIsNone(RudpPacket.from_bytes(b"SEQ:1|TOTAL:1|data"))


class TestAcknowledgements(unittest.TestCase):

    def test_round_trip_without_a_window(self):
        self.assertEqual(decode_ack(encode_ack(42)), Ack(42, None))

    def test_round_trip_with_an_advertised_window(self):
        self.assertEqual(encode_ack(42, 5), b"ACK:42|WIN:5")
        self.assertEqual(decode_ack(b"ACK:42|WIN:5"), Ack(42, 5))

    def test_a_zero_window_is_a_real_advertisement(self):
        """Zero means stop, which is different from advertising nothing at all."""
        self.assertEqual(decode_ack(b"ACK:7|WIN:0"), Ack(7, 0))
        self.assertIsNone(decode_ack(b"ACK:7").window)

    def test_an_unreadable_window_leaves_the_ack_usable(self):
        self.assertEqual(decode_ack(b"ACK:7|WIN:abc"), Ack(7, None))

    def test_rejects_anything_else(self):
        for raw in (b"NACK:1", b"ACK:x", b"ACK:", b"", b"\xff\xfe"):
            self.assertIsNone(decode_ack(raw), raw)


class TestChunking(unittest.TestCase):

    def test_splits_on_the_boundary(self):
        chunks = split_into_chunks(b"A" * 25, chunk_size=10)

        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[1], b"A" * 10)
        self.assertEqual(chunks[3], b"A" * 5)

    def test_numbering_starts_at_one(self):
        self.assertEqual(sorted(split_into_chunks(b"abc", 1)), [1, 2, 3])

    def test_empty_data_is_still_one_chunk(self):
        """The receiver waits for TOTAL packets, so zero packets would hang it."""
        self.assertEqual(split_into_chunks(b"", 10), {1: b""})


if __name__ == "__main__":
    unittest.main()
