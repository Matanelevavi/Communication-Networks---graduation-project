"""
The sending half of RUDP.

Splits a payload into numbered chunks and drives a sliding window over them:
send what the window allows, collect acknowledgements, grow or shrink the
window, retransmit only what was actually lost.

Two independent limits decide how much may be in flight, and the smaller wins:

* **congestion control** — what the *network* looks able to carry, measured by
  the sender from losses and timeouts (:mod:`src.rudp.congestion`);
* **flow control** — what the *receiver* has room to hold, told to the sender
  in the ``WIN`` field of every acknowledgement.

A fast link to a slow peer is limited by the second, a slow link to a fast peer
by the first. One packet is always allowed through, so a receiver that
advertises zero is probed rather than deadlocked.
"""
import logging
import random
import socket
import time

from src.config import (DELAY_SECONDS, DELAY_SEQ, LOSS_RATE, MAX_RETRIES,
                        RUDP_ACK_TIMEOUT, RUDP_CHUNK_SIZE,
                        RUDP_DUP_ACK_THRESHOLD, RUDP_MAX_TRANSFER_TIME,
                        SIMULATE_DELAY, SIMULATE_LOSS)
from src.rudp.congestion import CongestionControl
from src.rudp.packet import RudpPacket, decode_ack, split_into_chunks
from src.rudp.window import TransferWindow

log = logging.getLogger(__name__)

Address = tuple[str, int]


class RudpSender:
    """Reliable, congestion controlled delivery of one payload to one peer."""

    def __init__(self, sock, chunk_size: int = RUDP_CHUNK_SIZE) -> None:
        self.sock = sock
        self.chunk_size = chunk_size
        self.congestion = CongestionControl()

        # the receiver's advertised window; None until it tells us
        self.peer_window: int | None = None

        # counters, so a demo can show what the protocol did without Wireshark
        self.packets_sent = 0
        self.retransmissions = 0
        self.flow_limited = 0

    # ------------------------------------------------------------- sending
    def send(self, data: str | bytes | None, addr: Address) -> bool:
        """Deliver ``data`` to ``addr``.  Returns True if everything was acknowledged."""
        chunks = split_into_chunks(self._as_bytes(data), self.chunk_size)
        total = len(chunks)
        log.info(f"Transferring {sum(len(c) for c in chunks.values())} bytes "
                 f"as {total} chunks to {addr}")

        state = TransferWindow(chunks)
        deadline = time.time() + RUDP_MAX_TRANSFER_TIME

        while state.pending and state.timeouts < MAX_RETRIES:
            if time.time() > deadline:
                log.warning(f"Transfer to {addr} exceeded {RUDP_MAX_TRANSFER_TIME}s, giving up")
                break

            self._fill_window(state, total, addr)

            acks = self._collect_acks(addr)
            if acks is None:                      # the peer is gone
                break
            if not acks:                          # nothing arrived in time
                self.congestion.on_timeout()
                state.on_timeout()
                continue

            self._apply_acks(acks, state, total, addr)

        return self._report(state, addr)

    def effective_window(self) -> int:
        """
        How many packets may be in flight: the lesser of the two limits.

        Never less than one. A receiver advertising a zero window would
        otherwise stall the transfer for good, since the chunk that would free
        its buffer is exactly the one at the head of this window.
        """
        limit = self.congestion.window
        if self.peer_window is not None and self.peer_window < limit:
            self.flow_limited += 1
            log.info(f"Flow control: receiver window {self.peer_window} is below "
                     f"cwnd {limit}, sending {max(1, self.peer_window)}")
            limit = self.peer_window
        return max(1, limit)

    def _fill_window(self, state: "TransferWindow", total: int, addr: Address) -> None:
        """
        Transmit every chunk the window allows that is not already in flight.

        The in-flight check is what keeps the sender from resending the whole
        window on each pass and flooding a link that never dropped anything.
        """
        for seq in state.window_range(self.effective_window(), total):
            if state.is_in_flight(seq):
                continue
            self._transmit(seq, total, state, addr, first_time=state.is_first_send(seq))
            state.mark_sent(seq)

    def _transmit(self, seq: int, total: int, state: "TransferWindow",
                  addr: Address, first_time: bool) -> None:
        """Put one packet on the wire, honouring the failure simulation switches."""
        if SIMULATE_LOSS and random.random() < LOSS_RATE:
            log.info(f"Packet loss simulation, dropping chunk {seq}")
            return
        if SIMULATE_DELAY and first_time and seq == DELAY_SEQ:
            log.info(f"Latency simulation, delaying chunk {seq} by {DELAY_SECONDS}s")
            time.sleep(DELAY_SECONDS)

        try:
            self.sock.sendto(RudpPacket(seq, total, state.chunks[seq]).to_bytes(), addr)
        except OSError as e:
            log.warning(f"Send of chunk {seq} failed: {e}")
            return

        self.packets_sent += 1
        if not first_time:
            self.retransmissions += 1

    # --------------------------------------------------------- acknowledging
    def _collect_acks(self, addr: Address) -> list[int] | None:
        """
        Wait for one acknowledgement, then drain any others already queued.

        Returns the sequence numbers received, an empty list on a timeout, or
        ``None`` if the peer disappeared.  Draining matters: reading a single
        ACK per pass would make a window of N packets take N passes to clear.

        Each acknowledgement also refreshes the receiver's advertised window.
        """
        acks: list[int] = []
        blocking = True

        while True:
            try:
                self.sock.settimeout(RUDP_ACK_TIMEOUT if blocking else 0.0)
                raw, src = self.sock.recvfrom(1024)
            except (socket.timeout, BlockingIOError, StopIteration):
                return acks
            except ConnectionResetError:
                log.warning(f"Client {addr} disconnected abruptly")
                return None
            except OSError as e:
                log.warning(f"ACK receive failed: {e}")
                return None

            blocking = False

            # An acknowledgement is only trusted from the peer being served.
            if src != addr:
                log.warning(f"Ignoring ACK from unexpected source {src}")
                continue

            ack = decode_ack(raw)
            if ack is not None:
                if ack.window is not None:
                    self.peer_window = ack.window
                acks.append(ack.seq)

    def _apply_acks(self, acks: list[int], state: "TransferWindow",
                    total: int, addr: Address) -> None:
        for seq in acks:
            if not state.was_sent(seq):
                log.warning(f"Ignoring ACK {seq} for a chunk that was never sent")
                continue

            if state.acknowledge(seq):
                self.congestion.on_ack()

            if state.duplicate_acks >= RUDP_DUP_ACK_THRESHOLD and state.head_is_missing():
                self.congestion.on_triple_duplicate_ack()
                self._transmit(state.window_start, total, state, addr, first_time=False)
                state.mark_sent(state.window_start)
                state.reset_duplicate_acks()

    # -------------------------------------------------------------- results
    def _report(self, state: "TransferWindow", addr: Address) -> bool:
        self._clear_timeout()
        if not state.pending:
            log.info(f"Transfer to {addr} complete: {self.packets_sent} packets sent, "
                     f"{self.retransmissions} retransmissions, "
                     f"{self.flow_limited} rounds limited by the receiver")
            return True

        log.warning(f"Transfer to {addr} aborted, "
                    f"{len(state.pending)} chunks never acknowledged")
        return False

    def _clear_timeout(self) -> None:
        try:
            self.sock.settimeout(None)
        except OSError:
            pass

    @staticmethod
    def _as_bytes(data: str | bytes | None) -> bytes:
        if data is None:
            return b""
        return data.encode("utf-8") if isinstance(data, str) else data
