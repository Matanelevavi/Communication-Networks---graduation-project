"""
The real RUDP sender and receiver, over a simulated link.

Nothing about the protocol is reimplemented here. ``RudpSender`` is the class
the application server uses, and the receiving side is ``RudpReceiver.process``,
the same method its ``receive`` loop calls for every datagram. All this module
supplies is a socket that is not a socket: ``sendto`` puts a packet on the
simulated link and ``recvfrom`` moves virtual time forward until an
acknowledgement arrives or the sender's own timeout expires.
"""
import logging
import socket

from src.lab.link import Link, LinkExhausted, LossModel
from src.lab.trace import RecordingCongestion, Trace
from src.rudp.packet import RudpPacket, encode_ack, split_into_chunks
from src.rudp.receive_buffer import ReceiveBuffer
from src.rudp.receiver import RudpReceiver
from src.rudp.sender import RudpSender
from src.config import RUDP_CHUNK_SIZE

# Hundreds of runs would log a line per packet. The lab is the only user of
# these loggers in the web process; the application server is a separate one.
for _name in ("src.rudp.sender", "src.rudp.congestion"):
    logging.getLogger(_name).setLevel(logging.ERROR)

PEER = ("lab", 1)


class LabSocket:
    """What RudpSender believes is a UDP socket."""

    def __init__(self, link: Link, loss: LossModel, receiver: RudpReceiver,
                 trace: Trace) -> None:
        self.link = link
        self.loss = loss
        self.receiver = receiver
        self.trace = trace
        self.timeout: float | None = None
        self.inbox: list[bytes] = []
        self.sent_count: dict[int, int] = {}
        self.acks_sent: dict[int, int] = {}

    # ----------------------------------------------------- the socket API
    def settimeout(self, timeout: float | None) -> None:
        self.timeout = timeout

    def sendto(self, packet: bytes, _addr) -> None:
        seq = RudpPacket.from_bytes(packet).seq
        attempt = self.sent_count[seq] = self.sent_count.get(seq, 0) + 1
        if attempt > 1:
            self.trace.note("retransmit", seq)

        if self.loss.drops("data", seq, attempt):
            self.trace.note("loss", seq)
            return
        self.link.schedule("data", packet)

    def recvfrom(self, _bufsize: int):
        self._deliver_due()
        if self.inbox:
            return self.inbox.pop(0), PEER

        if not self.timeout:                       # non blocking: nothing has arrived
            raise BlockingIOError()

        deadline = self.link.now + self.timeout
        while not self.inbox:
            upcoming = self.link.next_time()
            if upcoming is None or upcoming > deadline:
                self.link.now = deadline           # nobody answered in time
                raise socket.timeout()
            self._handle(self.link.pop())
        return self.inbox.pop(0), PEER

    def close(self) -> None:
        pass

    # ------------------------------------------------------------- events
    def _deliver_due(self) -> None:
        while (due := self.link.next_time()) is not None and due <= self.link.now:
            self._handle(self.link.pop())

    def _handle(self, event) -> None:
        if event.kind == "ack":
            self.inbox.append(event.payload)
            return

        # a data packet reaching the receiver
        seq = self.receiver.process(event.payload)
        if seq is None:
            return                                  # corrupted, or no room: unanswered

        attempt = self.acks_sent[seq] = self.acks_sent.get(seq, 0) + 1
        if self.loss.drops("ack", seq, attempt):
            self.trace.note("ack_loss", seq)
            return
        window = self.receiver.buffer.advertised_window
        self.trace.receiver_window.append((self.link.now, window))
        self.link.schedule("ack", encode_ack(seq, window))


def run_rudp(data: bytes, link: Link, loss: LossModel, capacity: int) -> dict:
    """Send ``data`` with the real sender and report what happened."""
    trace = Trace(clock=lambda: link.now)
    chunks = split_into_chunks(data, RUDP_CHUNK_SIZE)

    receiver = RudpReceiver(None, buffer=ReceiveBuffer(capacity), verbose=False)
    sock = LabSocket(link, loss, receiver, trace)

    sender = RudpSender(sock)
    sender.congestion = RecordingCongestion(trace)

    try:
        completed = sender.send(data, PEER)
    except LinkExhausted:
        completed = False

    return {
        "completed": completed,
        "duration": link.now,
        "chunks": len(chunks),
        "packets_sent": sender.packets_sent,
        "retransmissions": sender.retransmissions,
        "timeouts": trace.timeouts,
        "fast_retransmits": trace.fast_retransmits,
        "flow_limited": sender.flow_limited,
        "verified": completed and receiver.is_complete() and receiver.buffer.payload() == data,
        "trace": trace,
    }
