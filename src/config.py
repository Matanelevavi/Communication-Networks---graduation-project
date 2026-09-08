"""
Central configuration for the WeatherWear project.

Every tunable value (ports, timeouts, protocol parameters, failure-simulation
switches) lives here so that no magic number is buried inside the network code.
"""
import logging
import os
import sys


def _load_dotenv(path):
    """
    Read simple KEY=VALUE lines from a local .env into the environment.

    Keeps a secret out of both the source and the shell profile, without
    pulling in a dependency for four lines of parsing. Existing environment
    variables always win, so an explicit export still overrides the file.
    """
    try:
        with open(path, encoding="utf-8") as env_file:
            lines = env_file.readlines()
    except OSError:
        return

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


def _flag(name, default=False):
    """Read a boolean switch from the environment, falling back to the default."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------- network ---
HOST = '127.0.0.1'          # everything runs over the loopback interface
BUFF_SIZE = 1024
ENCODING = 'utf-8'
TIMEOUT = 5.0               # generic socket timeout for the client control socket

# ------------------------------------------------------------- dhcp: main ---
DHCP_PORT = 8067
CLIENT_PORT = 8068          # fixed source port for the client control socket
DHCP_ADD = (HOST, DHCP_PORT)
CLIENT_ADD = (HOST, CLIENT_PORT)

# --------------------------------------------------------- dhcp: messages ---
DISCOVER_MSG = "DHCP_DISCOVER"
OFFER_MSG = "DHCP_OFFER"
REQUEST_MSG = "DHCP_REQUEST"
ACK_MSG = "DHCP_ACK"
NAK_MSG = "DHCP_NAK"        # explicit rejection, so the client never waits for a timeout
RELEASE_MSG = "DHCP_RELEASE"
POOL_IP = [f"192.168.1.{i}" for i in range(100, 151)]

# DORA reliability, client side: how many times each message is retransmitted
DHCP_MAX_RETRIES = 3
DHCP_RETRY_TIMEOUT = 1.5

# DORA reliability, server side: an offered IP is only reserved temporarily,
# and an acknowledged IP is only leased for a limited time.
OFFER_HOLD_TIME = 5.0       # seconds an OFFER is reserved before returning to the pool
LEASE_TIME = 300.0          # seconds a granted IP stays leased without a RELEASE
LEASE_SWEEP_INTERVAL = 1.0  # how often the server reclaims expired offers/leases

# ----------------------------------------------------------------- dhcp: backup ---
DHCP_BACKUP_PORT = 8069
DHCP_BACKUP_ADD = (HOST, DHCP_BACKUP_PORT)
BACKUP_IPS = [f"192.168.2.{i}" for i in range(100, 151)]
BACKUP_OFFER_DELAY = 2.0    # give the primary server a head start before offering

# -------------------------------------------------------------------- dns ---
DNS_SERVER_PORT = 8053
DNS_ADD = (HOST, DNS_SERVER_PORT)
MY_DOMAIN = "weatherwear.local"
APP_SER_IP = HOST
DNS_RECORD_TTL = 60         # authoritative TTL, sent to the client inside the answer
DNS_CACHE_TTL = 60          # fallback TTL used only if the server does not send one

# ------------------------------------------------------------- app server ---
APP_PORT = 8080
APP_ADD = (HOST, APP_PORT)
HTTP_TIMEOUT = 10
TCP_TIMEOUT = 20.0
MAX_REQUEST_SIZE = 64 * 1024        # largest request accepted from a client
MAX_RESPONSE_SIZE = 512 * 1024      # largest payload one RUDP transfer may carry

# ------------------------------------------------------------- api config ---
# The Gemini key is optional. Without one the app still produces a real,
# personalised forecast from live weather data; a key only upgrades the wording
# to an AI written paragraph.
#
# A key must never be committed: Google scans public code for its own keys and
# revokes any it finds, so a hardcoded key stops working on its own. Put it in
# a local .env file (git ignored) or in the environment.
API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ------------------------------------------------------------ custom rudp ---
RUDP_TIMEOUT = 3.0          # client-side timeout while waiting for the handshake ACK
RUDP_ACK_TIMEOUT = 1.0      # sender-side timeout while waiting for a data ACK
MAX_RETRIES = 4             # consecutive timeouts before a transfer is abandoned
RUDP_CHUNK_SIZE = 800       # payload bytes per datagram (well under the 64KB UDP limit)
RUDP_MAX_CWND = 20.0        # upper bound on the congestion window, in packets
RUDP_INIT_SSTHRESH = 8.0    # slow-start threshold: above it we switch to congestion avoidance
RUDP_DUP_ACK_THRESHOLD = 3  # duplicate ACKs that trigger a Fast Retransmit
RUDP_LINGER = 0.5           # seconds the receiver keeps re-ACKing after the last chunk
# Flow control: how many out-of-order packets the receiver can hold. The free
# space in this buffer is what it advertises to the sender as rwnd, so a small
# value is the way to demonstrate a receiver throttling a fast sender.
RUDP_RECV_BUFFER = int(os.environ.get("RUDP_RECV_BUFFER", 8))
RUDP_MAX_TRANSFER_TIME = 60.0   # hard upper bound on a single transfer

# RUDP control messages, shared by both sides of the connection
HANDSHAKE_PREFIX = "SEQ:1|"     # the initial request carries its payload inline
HANDSHAKE_ACK = b"ACK:1"
FIN_MSG = b"FIN"
FIN_ACK_MSG = b"FIN-ACK"

# ---------------------------------------------------- failure simulation ----
# Both switches are off by default.  Turn them on to demonstrate how the
# protocol recovers from loss and from latency, either by editing the value
# here or, without touching the code, through an environment variable:
#     SIMULATE_LOSS=1 python -m src.servers.app_server.app
SIMULATE_LOSS = _flag("SIMULATE_LOSS", False)
LOSS_RATE = float(os.environ.get("LOSS_RATE", 0.2))
SIMULATE_DELAY = _flag("SIMULATE_DELAY", False)   # delay one packet to force a retransmit
DELAY_SEQ = int(os.environ.get("DELAY_SEQ", 2))   # which sequence number to delay
DELAY_SECONDS = float(os.environ.get("DELAY_SECONDS", 2.0))

# ------------------------------------------------------ file system paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")


def setup_logging(tag):
    """
    Configure the root logger for one process.

    Called from the ``__main__`` block of every entry point rather than at
    import time, so that importing a module (in a test, for example) never
    hijacks the logging configuration of the process that imported it.
    """
    logging.basicConfig(
        level=logging.INFO,
        format=f'%(asctime)s -{tag}- %(message)s',
        datefmt='%H:%M:%S',
        stream=sys.stdout,
        force=True,
    )
