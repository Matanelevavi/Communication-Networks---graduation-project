"""
The receiving half of RUDP.

Collects the chunks of one transfer, discards anything corrupted or from the
wrong source, and hands the bytes on in order through a bounded
:class:`~src.rudp.receive_buffer.ReceiveBuffer`.

Every acknowledgement carries the space left in that buffer, which is how the
receiver tells the sender to slow down: flow control, separate from and in
addition to the congestion control the sender runs on its own.
"""
import logging
import socket
import time

from src.config import BUFF_SIZE, RUDP_CHUNK_SIZE, RUDP_LINGER, TCP_TIMEOUT
from src.rudp.packet import RudpPacket, encode_ack
from src.rudp.receive_buffer import ReceiveBuffer

log = logging.getLogger(__name__)

Address = tuple[str, int]

# a datagram is one chunk plus the header, with room to spare
DATAGRAM_SIZE = RUDP_CHUNK_SIZE + BUFF_SIZE


class RudpReceiver:
    """Reassembles one transfer arriving on a socket."""

    def __init__(self, sock, timeout: float = TCP_TIMEOUT,
                 buffer: ReceiveBuffer | None = None, verbose: bool = True) -> None:
        self.sock = sock
        self.timeout = timeout
        self.verbose = verbose
        self.buffer = buffer or ReceiveBuffer()
        self.total: int | None = None
        self.sender_addr: Address | None = None

        # counters, so the interface can show what the transfer went through
        self.datagrams = 0
        self.duplicates = 0
        self.corrupted = 0

    def stats(self) -> dict:
        return {"chunks": self.total or 0, "datagrams": self.datagrams,
                "duplicates": self.duplicates, "corrupted": self.corrupted}

    def receive(self, linger: bool = True) -> bytes | None:
        """
        Block until the whole payload has arrived, or the transfer stalls.

        With ``linger=False`` the payload is returned the moment it is
        complete, and the caller runs :meth:`linger` itself, typically on a
        thread: otherwise every answer waits ``RUDP_LINGER`` seconds for
        retransmissions that almost never come.
        """
        log.info("[RUDP] Waiting for chunks")
        self.sock.settimeout(self.timeout)

        while True:
            datagram = self._read()
            if datagram is None:
                return None
            raw, src = datagram

            if not self._is_expected_sender(src):
                continue

            seq = self.process(raw)
            if seq is None:
                continue

            # Every accepted packet is acknowledged, duplicates included: the
            # sender only repeats itself because it never saw the first ACK.
            self._acknowledge(seq)

            if self.is_complete():
                if linger:
                    self.linger()
                payload = self.buffer.payload()
                log.info(f"[RUDP] Transfer complete, {len(payload)} bytes")
                return payload

    def process(self, raw: bytes) -> int | None:
        """
        Take one datagram. Returns the sequence number to acknowledge, or
        ``None`` when the datagram must go unanswered.

        Everything the receiver decides lives here, apart from the socket, so
        the protocol lab drives the very same logic over a simulated link.
        """
        self.datagrams += 1

        packet = RudpPacket.from_bytes(raw)
        if packet is None:
            self.corrupted += 1
            if self.verbose:
                log.warning("[RUDP] Corrupted or malformed packet dropped")
            return None

        self.total = packet.total
        first_time = not self.buffer.has_seen(packet.seq)
        if not first_time:
            self.duplicates += 1

        # A chunk the buffer has no room for is left unacknowledged on
        # purpose: the sender will resend it once the window reopens.
        if not self.buffer.accept(packet.seq, packet.payload):
            return None

        if first_time and self.verbose:
            log.info(f"[RUDP] Chunk {packet.seq}/{packet.total} received "
                     f"(rwnd {self.buffer.advertised_window})")
        return packet.seq

    # -------------------------------------------------------------- helpers
    def _read(self) -> tuple[bytes, Address] | None:
        while True:
            try:
                return self.sock.recvfrom(DATAGRAM_SIZE)
            except socket.timeout:
                log.error(f"[RUDP] Timeout at chunk {self.buffer.next_expected}")
                return None
            except ConnectionResetError:
                continue
            except OSError as e:
                log.error(f"[RUDP] Socket error: {e}")
                return None

    def _is_expected_sender(self, src: Address) -> bool:
        """
        A transfer arrives from one ephemeral server socket and only that one.

        Locking onto the first source is what stops another process from
        injecting chunks into somebody else's download.
        """
        if self.sender_addr is None:
            self.sender_addr = src
            return True
        if src != self.sender_addr:
            log.warning(f"[RUDP] Ignoring a packet from unexpected source {src}")
            return False
        return True

    def _acknowledge(self, seq: int) -> None:
        """Acknowledge one chunk, advertising the room left in the buffer."""
        try:
            self.sock.sendto(encode_ack(seq, self.buffer.advertised_window),
                             self.sender_addr)
        except OSError as e:
            log.warning(f"[RUDP] Could not acknowledge chunk {seq}: {e}")

    def is_complete(self) -> bool:
        return self.total is not None and self.buffer.is_complete(self.total)

    def linger(self) -> None:
        """
        Keep answering retransmissions briefly after the last chunk.

        If the final ACK is lost the sender retransmits; without this window it
        would spend its whole retry budget talking to a closed socket.
        """
        deadline = time.time() + RUDP_LINGER
        while time.time() < deadline:
            try:
                self.sock.settimeout(deadline - time.time())
                raw, src = self.sock.recvfrom(DATAGRAM_SIZE)
            except (socket.timeout, OSError, StopIteration):
                return

            if src != self.sender_addr:
                continue
            packet = RudpPacket.from_bytes(raw)
            if packet is not None:
                self._acknowledge(packet.seq)
