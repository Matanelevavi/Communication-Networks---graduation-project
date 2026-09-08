"""
Congestion control for RUDP.

Kept apart from the socket code on purpose: the window algorithm is pure
arithmetic over three numbers, so it can be reasoned about and tested without
a network.  The scheme follows the two phase model from the course, the same
one TCP Reno uses.

    cwnd < ssthresh   ->  slow start          cwnd += 1 per ACK   (x2 per RTT)
    cwnd >= ssthresh  ->  congestion avoidance cwnd += 1/cwnd     (+1 per RTT)
    timeout           ->  ssthresh = cwnd/2,  cwnd = 1
    3 duplicate ACKs  ->  ssthresh = cwnd/2,  cwnd = ssthresh
"""
import logging

from src.config import RUDP_INIT_SSTHRESH, RUDP_MAX_CWND

log = logging.getLogger(__name__)


class CongestionControl:
    """The sender's congestion window and the events that move it."""

    def __init__(self,
                 max_cwnd: float = RUDP_MAX_CWND,
                 ssthresh: float = RUDP_INIT_SSTHRESH) -> None:
        self.cwnd = 1.0
        self.ssthresh = float(ssthresh)
        self.max_cwnd = float(max_cwnd)

    @property
    def window(self) -> int:
        """How many packets may be in flight, as a whole number."""
        return max(1, int(self.cwnd))

    @property
    def in_slow_start(self) -> bool:
        return self.cwnd < self.ssthresh

    def on_ack(self) -> None:
        """One packet was acknowledged: open the window."""
        if self.in_slow_start:
            self.cwnd += 1.0
        else:
            self.cwnd += 1.0 / self.cwnd
        self.cwnd = min(self.cwnd, self.max_cwnd)

    def on_timeout(self) -> None:
        """No ACK arrived at all: assume severe congestion and restart."""
        self.ssthresh = max(self.cwnd / 2.0, 1.0)
        self.cwnd = 1.0
        log.warning(f"Timeout: ssthresh={self.ssthresh:.1f}, cwnd reset to 1")

    def on_triple_duplicate_ack(self) -> None:
        """Later packets are arriving, so the path still works: halve, don't collapse."""
        self.ssthresh = max(self.cwnd / 2.0, 1.0)
        self.cwnd = self.ssthresh
        log.warning(f"Fast Retransmit: ssthresh={self.ssthresh:.1f}, cwnd={self.cwnd:.1f}")

    def __repr__(self) -> str:
        phase = "slow-start" if self.in_slow_start else "avoidance"
        return f"CongestionControl(cwnd={self.cwnd:.2f}, ssthresh={self.ssthresh:.1f}, {phase})"
