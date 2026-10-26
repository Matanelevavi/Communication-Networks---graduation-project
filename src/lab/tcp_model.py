"""
A TCP Reno sender, as a model, over the same simulated link.

This one is **not** the operating system's TCP, and the page says so. The
kernel's TCP cannot be put on a lossy virtual link, so what is compared with
RUDP is the algorithm TCP Reno follows, written out here from its textbook
description:

* cumulative acknowledgements: an ACK names the highest sequence number
  received *in order*, so the sender learns about a hole only from duplicates;
* slow start and congestion avoidance, using the same ``CongestionControl`` as
  RUDP, so the two differ in how they find out about loss and not in how they
  react to it;
* fast retransmit after three duplicate ACKs, and a retransmission timeout.

It is Reno, not NewReno or SACK: after a retransmission it recovers one hole
per round trip or per timeout, which is exactly the weakness the selective
acknowledgements in RUDP avoid. The timeout is the same fixed second RUDP uses,
so the comparison does not turn on a tuning difference.
"""
from src.config import RUDP_ACK_TIMEOUT, RUDP_CHUNK_SIZE
from src.lab.link import Link, LinkExhausted, LossModel
from src.lab.trace import RecordingCongestion, Trace
from src.rudp.packet import split_into_chunks
from src.rudp.receive_buffer import ReceiveBuffer

RTO = RUDP_ACK_TIMEOUT
DUPLICATE_ACKS = 3
MAX_CONSECUTIVE_TIMEOUTS = 12      # real TCP gives up far later than RUDP's four


def run_tcp(data: bytes, link: Link, loss: LossModel, capacity: int) -> dict:
    trace = Trace(clock=lambda: link.now)
    chunks = split_into_chunks(data, RUDP_CHUNK_SIZE)
    total = len(chunks)

    congestion = RecordingCongestion(trace)
    receiver = ReceiveBuffer(capacity)

    una = 1                    # the oldest segment not yet acknowledged
    nxt = 1                    # the next new segment to send
    peer_window: int | None = None
    duplicates = 0
    timer: float | None = None
    in_a_row = 0
    sent = retransmissions = flow_limited = 0
    attempts: dict[int, int] = {}
    ack_attempts: dict[int, int] = {}

    def transmit(seq: int) -> None:
        nonlocal sent, retransmissions
        attempt = attempts[seq] = attempts.get(seq, 0) + 1
        sent += 1
        if attempt > 1:
            retransmissions += 1
            trace.note("retransmit", seq)
        if loss.drops("data", seq, attempt):
            trace.note("loss", seq)
            return
        link.schedule("data", seq)

    def fill() -> None:
        nonlocal nxt, timer, flow_limited
        window = congestion.window
        if peer_window is not None and peer_window < window:
            flow_limited += 1
            window = peer_window
        window = max(1, window)                      # a zero window is still probed
        while nxt <= total and nxt - una < window:
            transmit(nxt)
            nxt += 1
        if timer is None and una < nxt:
            timer = link.now + RTO

    def on_data(seq: int) -> None:
        receiver.accept(seq, chunks[seq])            # a full buffer drops it, and still ACKs
        ack_no = receiver.next_expected - 1
        attempt = ack_attempts[ack_no] = ack_attempts.get(ack_no, 0) + 1
        if loss.drops("ack", ack_no, attempt):
            trace.note("ack_loss", ack_no)
            return
        trace.receiver_window.append((link.now, receiver.advertised_window))
        link.schedule("ack", (ack_no, receiver.advertised_window))

    def on_ack(ack_no: int, window: int) -> None:
        nonlocal una, peer_window, duplicates, timer, in_a_row
        peer_window = window
        if ack_no >= una:                            # new progress
            una = ack_no + 1
            duplicates = 0
            in_a_row = 0
            congestion.on_ack()
            timer = link.now + RTO if una < nxt else None
        elif una < nxt:                              # the same ACK again: a hole
            duplicates += 1
            if duplicates == DUPLICATE_ACKS:
                congestion.on_triple_duplicate_ack()
                transmit(una)
                duplicates = 0
                timer = link.now + RTO

    def on_timeout() -> bool:
        nonlocal timer, in_a_row, duplicates
        in_a_row += 1
        if in_a_row > MAX_CONSECUTIVE_TIMEOUTS:
            return False
        congestion.on_timeout()
        transmit(una)
        duplicates = 0
        timer = link.now + RTO
        return True

    completed = True
    try:
        while True:
            fill()
            if una > total:
                break

            upcoming = link.next_time()
            if timer is not None and (upcoming is None or timer <= upcoming):
                link.now = max(link.now, timer)
                if not on_timeout():
                    completed = False
                    break
            elif upcoming is not None:
                event = link.pop()
                if event.kind == "data":
                    on_data(event.payload)
                else:
                    on_ack(*event.payload)
            else:
                completed = False                    # nothing in flight and no timer
                break
    except LinkExhausted:
        completed = False

    return {
        "completed": completed,
        "duration": link.now,
        "chunks": total,
        "packets_sent": sent,
        "retransmissions": retransmissions,
        "timeouts": trace.timeouts,
        "fast_retransmits": trace.fast_retransmits,
        "flow_limited": flow_limited,
        "verified": completed and receiver.is_complete(total)
                    and receiver.payload() == data,
        "trace": trace,
    }
