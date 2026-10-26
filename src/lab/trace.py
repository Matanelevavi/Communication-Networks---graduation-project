"""
What a simulated transfer records, and the congestion window that records it.

The graph on the page is drawn from these samples, one per acknowledgement or
loss event, so it shows what the algorithm did and not what a textbook says it
should do.
"""
from dataclasses import dataclass, field

from src.rudp.congestion import CongestionControl

MAX_SAMPLES = 800
MAX_EVENTS_SHOWN = 400


def _thin(items: list, limit: int) -> list:
    """At most ``limit`` items, spread evenly over the whole list."""
    if len(items) <= limit:
        return items
    if limit <= 0:
        return []
    step = len(items) / limit
    return [items[int(i * step)] for i in range(limit)]


@dataclass
class Trace:
    """Everything a run saw, in the order it saw it."""
    clock: object = None                       # a callable returning virtual seconds
    samples: list = field(default_factory=list)        # (t, cwnd, ssthresh)
    events: list = field(default_factory=list)         # (t, kind, seq)
    receiver_window: list = field(default_factory=list)  # (t, rwnd)
    timeouts: int = 0
    fast_retransmits: int = 0

    def now(self) -> float:
        return self.clock() if self.clock else 0.0

    def note(self, kind: str, seq: int = 0) -> None:
        self.events.append((self.now(), kind, seq))

    def sample(self, congestion: CongestionControl) -> None:
        self.samples.append((self.now(), congestion.cwnd, congestion.ssthresh))

    # ------------------------------------------------------------- output
    def series(self) -> list[dict]:
        """The window over time, thinned if a long run produced too many points."""
        samples = self.samples
        if len(samples) > MAX_SAMPLES:
            stride = -(-len(samples) // MAX_SAMPLES)
            samples = samples[::stride] + [samples[-1]]
        return [{"t": round(t * 1000, 1), "cwnd": round(cwnd, 2), "ssthresh": round(ssthresh, 2)}
                for t, cwnd, ssthresh in samples]

    def marks(self) -> list[dict]:
        """Losses, timeouts and retransmissions, for the markers on the graph."""
        events = self.events
        if len(events) > MAX_EVENTS_SHOWN:
            # Timeouts and fast retransmits are what the graph is about, so
            # they get most of the room; the packet level noise fills the rest.
            # Both are thinned evenly, so the total is a hard ceiling.
            rare = [e for e in events if e[1] in ("timeout", "fast_retransmit")]
            common = [e for e in events if e[1] not in ("timeout", "fast_retransmit")]
            rare = _thin(rare, MAX_EVENTS_SHOWN * 3 // 4)
            common = _thin(common, MAX_EVENTS_SHOWN - len(rare))
            events = sorted(rare + common)
        return [{"t": round(t * 1000, 1), "kind": kind, "seq": seq} for t, kind, seq in events]


class RecordingCongestion(CongestionControl):
    """The real congestion window, with a note taken each time it moves."""

    def __init__(self, trace: Trace) -> None:
        super().__init__()
        self.trace = trace
        trace.sample(self)                      # the starting point: cwnd = 1

    def on_ack(self) -> None:
        super().on_ack()
        self.trace.sample(self)

    def on_timeout(self) -> None:
        before = self.cwnd
        super().on_timeout()
        self.trace.timeouts += 1
        # two points at the same time draw the drop as a cliff, not a slope
        self.trace.samples.append((self.trace.now(), before, self.ssthresh))
        self.trace.note("timeout")
        self.trace.sample(self)

    def on_triple_duplicate_ack(self) -> None:
        before = self.cwnd
        super().on_triple_duplicate_ack()
        self.trace.fast_retransmits += 1
        self.trace.samples.append((self.trace.now(), before, self.ssthresh))
        self.trace.note("fast_retransmit")
        self.trace.sample(self)
