"""
RUDP: reliability, ordering and congestion control on top of UDP.

The protocol lives beside the client and the servers rather than inside one of
them, because both ends of every transfer depend on it:

    packet.py          the wire format and the checksum, the single source of truth
    congestion.py      the congestion window: what the network can carry
    window.py          the state of one transfer in flight
    sender.py          the sliding window transmitter
    receive_buffer.py  the receiver's buffer: what the peer has room to hold
    receiver.py        reassembly and acknowledgement
"""
from src.rudp.congestion import CongestionControl
from src.rudp.packet import (Ack, RudpPacket, decode_ack, encode_ack,
                             split_into_chunks)
from src.rudp.receive_buffer import ReceiveBuffer
from src.rudp.receiver import RudpReceiver
from src.rudp.sender import RudpSender
from src.rudp.window import TransferWindow

__all__ = [
    "Ack",
    "CongestionControl",
    "ReceiveBuffer",
    "RudpPacket",
    "RudpReceiver",
    "RudpSender",
    "TransferWindow",
    "decode_ack",
    "encode_ack",
    "split_into_chunks",
]
