"""
The address bookkeeping behind a DHCP server.

Separated from the socket loop because it is the part with the interesting
rules, and because it can then be tested without a network.  An address moves
through three states, and every one of them can time out:

    free  --reserve-->  reserved  --commit-->  leased
      ^                    |                     |
      |                    |                     |
      +---- hold expires --+---- lease expires --+
      +------------------- release --------------+

Reserving on OFFER rather than leasing on OFFER is what keeps a lost REQUEST
or a lost ACK from taking an address out of circulation for good.
"""
import logging
import threading
import time
from dataclasses import dataclass

from src.config import LEASE_TIME, OFFER_HOLD_TIME

log = logging.getLogger(__name__)

Client = tuple[str, int]


@dataclass(frozen=True)
class Allocation:
    """One address held by one client, and the moment that hold lapses."""
    ip: str
    expires_at: float

    def has_expired(self, now: float) -> bool:
        return now >= self.expires_at


class AddressPool:
    """Free addresses, temporary reservations and active leases, under one lock."""

    def __init__(self,
                 addresses,
                 hold_time: float = OFFER_HOLD_TIME,
                 lease_time: float = LEASE_TIME) -> None:
        self.free: list[str] = list(addresses)
        self.reserved: dict[Client, Allocation] = {}
        self.leased: dict[Client, Allocation] = {}
        self.declined: dict[Client, float] = {}

        self.hold_time = hold_time
        self.lease_time = lease_time
        self._lock = threading.RLock()

    @property
    def available(self) -> int:
        with self._lock:
            return len(self.free)

    def held_by(self, client: Client) -> str | None:
        """The address this client already has reserved or leased, if any."""
        with self._lock:
            allocation = self.reserved.get(client) or self.leased.get(client)
            return allocation.ip if allocation else None

    # ------------------------------------------------------------- reserve
    def reserve(self, client: Client) -> str | None:
        """
        Hold an address for a client that just sent a DISCOVER.

        Repeating a DISCOVER returns the same address rather than consuming a
        second one, which matters now that the client retransmits.
        Returns ``None`` when the pool is empty.
        """
        with self._lock:
            existing = self.held_by(client)
            if existing:
                return existing

            if not self.free:
                return None

            ip = self.free.pop(0)
            self.reserved[client] = Allocation(ip, time.time() + self.hold_time)
            return ip

    def withdraw(self, client: Client) -> str | None:
        """Give up a reservation that has not been committed.  Returns the address."""
        with self._lock:
            allocation = self.reserved.pop(client, None)
            if not allocation:
                return None
            self.free.append(allocation.ip)
            return allocation.ip

    # -------------------------------------------------------------- commit
    def commit(self, client: Client, ip: str) -> bool:
        """
        Turn a reservation into a lease, on REQUEST.

        A repeated REQUEST for an address already leased to the same client
        renews it, so a lost ACK can simply be asked for again.
        """
        with self._lock:
            reservation = self.reserved.get(client)
            lease = self.leased.get(client)

            if reservation and reservation.ip == ip:
                del self.reserved[client]
            elif not (lease and lease.ip == ip):
                return False

            self.leased[client] = Allocation(ip, time.time() + self.lease_time)
            return True

    def release(self, client: Client, ip: str) -> bool:
        """Return a leased address to the pool, on RELEASE."""
        with self._lock:
            lease = self.leased.get(client)
            if not lease or lease.ip != ip:
                return False
            del self.leased[client]
            self.free.append(ip)
            return True

    # ------------------------------------------------------------- decline
    def decline(self, client: Client) -> None:
        """
        Note that this client accepted some other server's offer.

        The backup server answers on a delay, so it may not have offered
        anything yet when it learns it lost; without this note it would wake up
        and reserve an address nobody will ever claim.
        """
        with self._lock:
            self.declined[client] = time.time()

    def has_declined(self, client: Client) -> bool:
        with self._lock:
            when = self.declined.get(client)
            return when is not None and time.time() - when < self.hold_time

    def forget_decline(self, client: Client) -> None:
        """A new DISCOVER starts a new exchange, so the old outcome is irrelevant."""
        with self._lock:
            self.declined.pop(client, None)

    # ------------------------------------------------------------- reclaim
    def reclaim_expired(self) -> list[str]:
        """Return every lapsed reservation and lease to the pool."""
        now = time.time()
        reclaimed = []

        with self._lock:
            for client, allocation in list(self.reserved.items()):
                if allocation.has_expired(now):
                    del self.reserved[client]
                    self.free.append(allocation.ip)
                    reclaimed.append(allocation.ip)
                    log.info(f"Offer {allocation.ip} to {client} expired without a "
                             f"REQUEST, returned to the pool")

            for client, allocation in list(self.leased.items()):
                if allocation.has_expired(now):
                    del self.leased[client]
                    self.free.append(allocation.ip)
                    reclaimed.append(allocation.ip)
                    log.info(f"Lease {allocation.ip} for {client} expired, "
                             f"returned to the pool")

            for client, when in list(self.declined.items()):
                if now - when >= self.hold_time:
                    del self.declined[client]

        return reclaimed

    def __repr__(self) -> str:
        return (f"AddressPool(free={len(self.free)}, "
                f"reserved={len(self.reserved)}, leased={len(self.leased)})")
