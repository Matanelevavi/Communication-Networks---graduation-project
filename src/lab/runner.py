"""
Runs the lab: one transfer, or the same transfer under both protocols.

The inputs are bounded here as well as at the API, because this is code that
does real work on behalf of anyone who can reach the website.
"""
import random
from dataclasses import dataclass

from src.config import RUDP_CHUNK_SIZE
from src.lab.link import Link, LossModel
from src.lab.rudp_run import run_rudp
from src.lab.tcp_model import run_tcp

PROTOCOLS = ("RUDP", "TCP")

SIZE_KB = (1, 256)
LOSS = (0.0, 0.5)
DELAY_MS = (1, 400)      # a round trip must stay under the fixed one second timeout
BUFFER = (1, 64)

PROTOCOL_LABELS = {
    "RUDP": "the project's RUDP sender and receiver, unchanged",
    "TCP": "a TCP Reno model (not the operating system's TCP)",
}


@dataclass(frozen=True)
class LabParams:
    size_kb: int = 64
    loss: float = 0.05
    delay_ms: int = 40
    buffer: int = 8
    seed: int = 1

    def __post_init__(self) -> None:
        for name, value, (low, high) in (("size_kb", self.size_kb, SIZE_KB),
                                         ("loss", self.loss, LOSS),
                                         ("delay_ms", self.delay_ms, DELAY_MS),
                                         ("buffer", self.buffer, BUFFER)):
            if not low <= value <= high:
                raise ValueError(f"{name} must be between {low} and {high}")


def payload(params: LabParams) -> bytes:
    """The same bytes every time for a seed, so a run can be verified at the end."""
    return random.Random(params.seed).randbytes(params.size_kb * 1024)  # nosec B311


def run_one(protocol: str, params: LabParams) -> dict:
    if protocol not in PROTOCOLS:
        raise ValueError(f"unknown protocol {protocol!r}")

    data = payload(params)
    link = Link(delay=params.delay_ms / 1000)
    loss = LossModel(params.seed, params.loss)
    run = (run_rudp if protocol == "RUDP" else run_tcp)(data, link, loss, params.buffer)
    return summarise(protocol, params, len(data), run)


def run_lab(params: LabParams, protocols: tuple[str, ...] = PROTOCOLS) -> dict:
    return {protocol: run_one(protocol, params) for protocol in protocols}


def summarise(protocol: str, params: LabParams, size: int, run: dict) -> dict:
    trace = run["trace"]
    seconds = run["duration"]
    return {
        "protocol": protocol,
        "implementation": PROTOCOL_LABELS[protocol],
        "completed": run["completed"],
        "verified": run["verified"],
        "duration_ms": round(seconds * 1000, 1),
        "goodput_kbps": round(size * 8 / 1000 / seconds, 1) if run["completed"] and seconds else 0.0,
        "chunks": run["chunks"],
        "chunk_bytes": RUDP_CHUNK_SIZE,
        "packets_sent": run["packets_sent"],
        "retransmissions": run["retransmissions"],
        "timeouts": run["timeouts"],
        "fast_retransmits": run["fast_retransmits"],
        "flow_limited": run["flow_limited"],
        "series": trace.series(),
        "marks": trace.marks(),
    }
