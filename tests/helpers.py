"""Test doubles shared by the protocol tests."""
import socket
from collections import deque

PEER = ("127.0.0.1", 9999)
STRANGER = ("127.0.0.1", 7777)


def sequence_of(packet: bytes) -> int:
    """Read the sequence number straight off the wire, without the parser."""
    return int(packet.split(b"|")[0].split(b":")[1])


class FakeNetwork:
    """
    A minimal UDP peer that acknowledges everything it receives.

    ``drop_once`` names sequence numbers whose *first* transmission is lost, so
    a test can force a timeout and then watch the retransmission arrive.
    ``spoof`` seeds acknowledgements from another address.
    """

    def __init__(self, drop_once=(), spoof=()) -> None:
        self.sent: list[bytes] = []
        self.delivered: list[int] = []
        self.acks = deque(spoof)
        self.drop_once = set(drop_once)

    def settimeout(self, _timeout):
        pass

    def sendto(self, packet, _addr):
        self.sent.append(packet)
        seq = sequence_of(packet)
        if seq in self.drop_once:
            self.drop_once.discard(seq)     # only the first copy is lost
            return
        self.delivered.append(seq)
        self.acks.append((f"ACK:{seq}".encode(), PEER))

    def recvfrom(self, _bufsize):
        if self.acks:
            return self.acks.popleft()
        raise socket.timeout()

    def close(self):
        pass


class ThrottlingNetwork(FakeNetwork):
    """
    A peer that advertises a small receive window with every acknowledgement.

    It records the size of each burst the sender put on the wire between two
    rounds of collecting acknowledgements, so a test can assert that the sender
    respected the advertisement once it had heard it.
    """

    def __init__(self, window: int) -> None:
        super().__init__()
        self.window = window
        self.bursts = []
        self._burst = 0

    def sendto(self, packet, _addr):
        self.sent.append(packet)
        self._burst += 1
        seq = sequence_of(packet)
        self.delivered.append(seq)
        self.acks.append((f"ACK:{seq}|WIN:{self.window}".encode(), PEER))

    def recvfrom(self, _bufsize):
        if self._burst:
            self.bursts.append(self._burst)
            self._burst = 0
        if self.acks:
            return self.acks.popleft()
        raise socket.timeout()
