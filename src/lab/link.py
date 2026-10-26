"""
A simulated network link, in virtual time.

Nothing here sleeps: the clock is a number that jumps to the next event, so a
transfer that would take a minute on a bad network is computed in milliseconds,
and the same inputs always give the same result.

The link has a one way delay and a loss rate, and nothing else. Loss is decided
by hashing ``(seed, direction, sequence number, attempt)`` rather than by
drawing from a shared generator. That makes the loss pattern a property of the
*packet*, not of the order things happened in, so two protocols run over the
same link lose the very same first transmissions: a fair comparison.
"""
import heapq
import random
from dataclasses import dataclass, field

# A guard against a pathological input: past this many events the run is
# abandoned and reported as not completed.
MAX_EVENTS = 400_000


class LinkExhausted(OSError):
    """The run used more events than any honest transfer needs."""


class LossModel:
    """Decides, deterministically, which transmissions the network drops."""

    def __init__(self, seed: int, rate: float) -> None:
        self.seed = seed
        self.rate = rate

    def drops(self, direction: str, key: int, attempt: int) -> bool:
        if self.rate <= 0:
            return False
        # random is fine here: it only decides which packets a demo drops
        draw = random.Random(f"{self.seed}:{direction}:{key}:{attempt}").random()  # nosec B311
        return draw < self.rate


@dataclass(order=True)
class Event:
    at: float
    order: int
    kind: str = field(compare=False)
    payload: object = field(compare=False)


class Link:
    """A virtual clock and the packets in flight on the wire."""

    def __init__(self, delay: float, max_events: int = MAX_EVENTS) -> None:
        self.delay = delay
        self.now = 0.0
        self.max_events = max_events
        self._queue: list[Event] = []
        self._counter = 0

    def schedule(self, kind: str, payload: object, after: float | None = None) -> None:
        """Put something on the wire; it arrives one delay from now."""
        self._counter += 1
        if self._counter > self.max_events:
            raise LinkExhausted("the simulation used too many events")
        heapq.heappush(self._queue, Event(
            self.now + (self.delay if after is None else after), self._counter, kind, payload))

    def next_time(self) -> float | None:
        return self._queue[0].at if self._queue else None

    def pop(self) -> Event:
        """Take the earliest event and move the clock to it."""
        event = heapq.heappop(self._queue)
        self.now = max(self.now, event.at)
        return event
