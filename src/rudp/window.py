"""
The state of one transfer in flight.

Three sets and a cursor answer every question the sender asks: what still
needs an acknowledgement, what is already on the wire, what has ever been sent,
and where the window starts.
"""


class TransferWindow:
    """
    Bookkeeping for one transfer: what is unacknowledged, in flight, and sent.

    Kept apart from :class:`~src.rudp.sender.RudpSender` so the sender reads as
    a sequence of protocol steps rather than as set manipulation, and so the
    sliding rules can be tested without a socket.
    """

    def __init__(self, chunks: dict[int, bytes]) -> None:
        self.chunks = chunks
        self.pending = set(chunks)      # not yet acknowledged
        self.in_flight: set[int] = set()  # sent, waiting for an ACK
        self.ever_sent: set[int] = set()  # transmitted at least once
        self.window_start = 1
        self.timeouts = 0
        self.duplicate_acks = 0

    def window_range(self, width: int, total: int) -> range:
        return range(self.window_start, min(self.window_start + width, total + 1))

    def is_in_flight(self, seq: int) -> bool:
        return seq not in self.pending or seq in self.in_flight

    def is_first_send(self, seq: int) -> bool:
        return seq not in self.ever_sent

    def was_sent(self, seq: int) -> bool:
        return seq in self.ever_sent

    def mark_sent(self, seq: int) -> None:
        self.ever_sent.add(seq)
        self.in_flight.add(seq)

    def head_is_missing(self) -> bool:
        return self.window_start in self.pending

    def reset_duplicate_acks(self) -> None:
        self.duplicate_acks = 0

    def on_timeout(self) -> None:
        self.timeouts += 1
        self.in_flight.clear()          # everything still pending is resent
        self.duplicate_acks = 0

    def acknowledge(self, seq: int) -> bool:
        """
        Record an acknowledgement.  Returns True if it was new progress.

        An ACK beyond the head of the window while the head is still missing
        is the selective equivalent of TCP's duplicate ACK.
        """
        is_new = seq in self.pending
        if is_new:
            self.pending.discard(seq)
            self.in_flight.discard(seq)
            self.timeouts = 0

        if self.head_is_missing() and (seq > self.window_start or not is_new):
            self.duplicate_acks += 1
        elif is_new:
            self.duplicate_acks = 0

        self._slide()
        return is_new

    def _slide(self) -> None:
        while self.window_start in self.chunks and self.window_start not in self.pending:
            self.window_start += 1
            self.duplicate_acks = 0
