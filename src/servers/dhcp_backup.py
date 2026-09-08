"""
DHCP server (backup).

Same behaviour as the primary server, with three differences that are all
expressed as constructor arguments instead of duplicated code:

* a separate address pool (192.168.2.x), so the two servers can never hand out
  the same address;
* its own UDP port;
* a delay before answering a DISCOVER, which lets the primary server win the
  race whenever it is alive.  The delay is scheduled on a timer rather than a
  blocking sleep, so a second client is not queued behind the first one.
"""
import logging
from src.config import (BACKUP_IPS, BACKUP_OFFER_DELAY, DHCP_BACKUP_ADD,
                        setup_logging)
from src.servers.dhcp_server import DHCPServer

log = logging.getLogger(__name__)


class DHCPBackupServer(DHCPServer):
    def __init__(self):
        super().__init__(
            address=DHCP_BACKUP_ADD,
            pool=BACKUP_IPS,
            offer_delay=BACKUP_OFFER_DELAY,
            name="Backup DHCP",
        )


if __name__ == "__main__":
    setup_logging("BACKUP DHCP")
    DHCPBackupServer().start()
