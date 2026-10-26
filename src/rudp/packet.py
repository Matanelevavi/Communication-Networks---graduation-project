"""
The RUDP wire format.

One module owns the layout of a packet, and both the sender and the receiver
go through it.  Before this existed each side built and parsed the header by
hand, which meant the two definitions could drift apart without anything
failing loudly.

Data packet::

    SEQ:<n>|TOTAL:<t>|CHK:<crc32>|<payload>

The checksum covers ``SEQ:<n>|TOTAL:<t>|`` **and** the payload, so corruption
of a header field is detected just like corruption of the data.  It cannot
cover itself, which is why ``CHK`` is appended after the fields it protects.

Acknowledgement::

    ACK:<n>|WIN:<rwnd>

``WIN`` is the receiver's free buffer space in packets, the flow control
window. It is optional on the wire, so an acknowledgement without it is still
valid and simply carries no advertisement.
"""
import re
import zlib
from dataclasses import dataclass

ENCODING = "utf-8"
ACK_PREFIX = "ACK:"
WINDOW_PREFIX = "WIN:"

# Every number on the wire is written one way only: ASCII digits, no sign, no
# padding, no spaces, at most twelve of them. Python's int() is far more
# generous (it reads "٣", " 3", "+3" and "0_3"), and a parser that accepts
# spellings its own encoder never produces accepts datagrams nobody sent, so
# the header must match its canonical form exactly. The bound keeps a hostile
# TOTAL from being a number the receiver would wait on for the age of the
# universe.
_NUMBER = rb"(0|[1-9][0-9]{0,11})"
HEADER = re.compile(rb"SEQ:" + _NUMBER + rb"\|TOTAL:" + _NUMBER
                    + rb"\|CHK:(0|[1-9][0-9]{0,9})\|")
ACK = re.compile(r"ACK:(0|[1-9][0-9]{0,11})(?:\|WIN:(0|[1-9][0-9]{0,11}))?(?:\|.*)?\Z",
                 re.ASCII | re.DOTALL)


class RudpPacket:
    """A single data packet, with the framing and the integrity check."""

    __slots__ = ("seq", "total", "payload")

    def __init__(self, seq: int, total: int, payload: bytes) -> None:
        self.seq = seq
        self.total = total
        self.payload = payload

    # ------------------------------------------------------------ checksum
    @staticmethod
    def checksum(seq: int, total: int, payload: bytes) -> int:
        """CRC32 over the protected header fields followed by the payload."""
        return zlib.crc32(RudpPacket._fields(seq, total) + payload) & 0xFFFFFFFF

    @staticmethod
    def _fields(seq: int, total: int) -> bytes:
        return f"SEQ:{seq}|TOTAL:{total}|".encode(ENCODING)

    # --------------------------------------------------------------- codec
    def to_bytes(self) -> bytes:
        """Serialise the packet, computing its checksum."""
        chk = self.checksum(self.seq, self.total, self.payload)
        return (self._fields(self.seq, self.total)
                + f"CHK:{chk}|".encode(ENCODING)
                + self.payload)

    @classmethod
    def from_bytes(cls, raw: bytes) -> "RudpPacket | None":
        """
        Parse and verify a datagram.

        Returns ``None`` for anything malformed or corrupted, so a caller only
        ever handles packets that are known to be intact.  A payload may itself
        contain the separator, hence the bounded split.
        """
        header = HEADER.match(raw)
        if header is None:
            return None

        seq, total, declared_chk = (int(field) for field in header.groups())
        payload = raw[header.end():]
        if cls.checksum(seq, total, payload) != declared_chk:
            return None

        return cls(seq, total, payload)

    def __repr__(self) -> str:
        return f"RudpPacket(seq={self.seq}, total={self.total}, {len(self.payload)}B)"


@dataclass(frozen=True)
class Ack:
    """One acknowledgement, and the window the receiver advertised with it."""
    seq: int
    window: int | None = None      # None: the peer advertised nothing


def encode_ack(seq: int, window: int | None = None) -> bytes:
    """Build the acknowledgement for one sequence number."""
    text = f"{ACK_PREFIX}{seq}"
    if window is not None:
        text += f"|{WINDOW_PREFIX}{window}"
    return text.encode(ENCODING)


def decode_ack(raw: bytes) -> "Ack | None":
    """Read an acknowledgement off the wire, or ``None`` if it is not one."""
    try:
        text = raw.decode(ENCODING)
    except UnicodeDecodeError:
        return None

    parsed = ACK.match(text)
    if parsed is None:
        return None

    # An unreadable window leaves the acknowledgement itself usable: it simply
    # carries no advertisement.
    seq, window = parsed.groups()
    return Ack(int(seq), int(window) if window is not None else None)


def split_into_chunks(data: bytes, chunk_size: int) -> dict[int, bytes]:
    """
    Cut a payload into numbered chunks, starting at one.

    Empty data still produces a single empty chunk: the receiver waits for
    ``TOTAL`` packets, so a transfer of nothing must still be one packet.
    """
    total = max(1, (len(data) + chunk_size - 1) // chunk_size)
    return {i + 1: data[i * chunk_size:(i + 1) * chunk_size] for i in range(total)}
