"""
The receiver's buffer, and the flow control window that comes out of it.

Chunks that arrive in order are handed on immediately and the memory is
released; only a chunk that arrives *early*, while an earlier one is still
missing, has to be held. That held set is the receive buffer, it is bounded,
and the space left in it is exactly what the receiver advertises to the sender
as ``rwnd``.

This is the same idea as the TCP receive window: the sender may not put more
data in flight than the receiver has room to hold, no matter how much the
network could carry.

    seq == next_expected  ->  delivered right away, costs no buffer
    seq >  next_expected  ->  held, costs one slot, may be refused when full
    seq <  next_expected  ->  already delivered, a duplicate
"""
import logging

from src.config import RUDP_RECV_BUFFER

log = logging.getLogger(__name__)


class ReceiveBuffer:
    """Reassembles a stream in order while holding at most ``capacity`` gaps."""

    def __init__(self, capacity: int = RUDP_RECV_BUFFER) -> None:
        self.capacity = max(1, capacity)
        self.delivered = bytearray()      # everything already in order
        self.out_of_order: dict[int, bytes] = {}
        self.next_expected = 1

    # ---------------------------------------------------------- accounting
    @property
    def advertised_window(self) -> int:
        """Free slots in the buffer: the ``rwnd`` sent back with every ACK."""
        return self.capacity - len(self.out_of_order)

    @property
    def is_full(self) -> bool:
        return self.advertised_window <= 0

    def has_seen(self, seq: int) -> bool:
        return seq < self.next_expected or seq in self.out_of_order

    # ----------------------------------------------------------- accepting
    def accept(self, seq: int, payload: bytes) -> bool:
        """
        Take one chunk. Returns False when there is no room to hold it.

        A refused chunk is deliberately not acknowledged, so the sender treats
        it as lost and tries again once the window has opened.
        """
        if seq < self.next_expected:
            return True                   # already delivered, ACK it again

        if seq == self.next_expected:
            self._deliver(payload)
            return True

        if seq in self.out_of_order:
            return True                   # already held, ACK it again

        if self.is_full:
            log.warning(f"[RUDP] Receive buffer full, refusing chunk {seq}")
            return False

        self.out_of_order[seq] = payload
        return True

    def _deliver(self, payload: bytes) -> None:
        """Append the expected chunk, then drain whatever was waiting behind it."""
        self.delivered += payload
        self.next_expected += 1

        while self.next_expected in self.out_of_order:
            self.delivered += self.out_of_order.pop(self.next_expected)
            self.next_expected += 1

    # ------------------------------------------------------------- results
    def is_complete(self, total: int) -> bool:
        return self.next_expected > total

    def payload(self) -> bytes:
        return bytes(self.delivered)

    def __repr__(self) -> str:
        return (f"ReceiveBuffer(next={self.next_expected}, "
                f"held={len(self.out_of_order)}, rwnd={self.advertised_window})")
