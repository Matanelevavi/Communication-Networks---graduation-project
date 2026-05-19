import socket
import sys
import logging
from src.config import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s -BACKUP DHCP- %(message)s', datefmt='%H:%M:%S', stream=sys.stdout)

class DHCPBackupServer:
    def __init__(self):
        self.sock=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(DHCP_BACKUP_ADD)
        self.pool_ip=list(BACKUP_IPS)
        self.used_ips={}

    def start(self):
        logging.info(f"Backup DHCP Server listening on {DHCP_BACKUP_ADD}")
        try:
            while True:
                data,client_add = self.sock.recvfrom(BUFF_SIZE)
                msg=data.decode(ENCODING)

                if msg==DISCOVER_MSG:
                    if not self.pool_ip:
                        logging.warning(f"Backup IP pool finished, Rejecting {client_add}")
                        self.sock.sendto("DHCP: No IPs".encode(ENCODING),client_add)
                        continue

                    new_ip=self.pool_ip.pop(0)
                    self.used_ips[client_add]=new_ip
                    reply=f"{OFFER_MSG}:{new_ip}"
                    self.sock.sendto(reply.encode(ENCODING),client_add)
                    logging.info(f"Offered {new_ip} to {client_add}")

                elif msg.startswith(REQUEST_MSG):
                    wanted_ip = msg.split(":")[1]
                    if self.used_ips.get(client_add)==wanted_ip:
                        reply=f"{ACK_MSG}:{wanted_ip}"
                        self.sock.sendto(reply.encode(ENCODING), client_add)
                        logging.info(f"ACK sent for {wanted_ip}, IPs remaining: {len(self.pool_ip)}")
                    else:
                        #Client accepted the primary server offer so silently ignore
                        pass
        except KeyboardInterrupt:
            logging.info("Turn off Backup DHCP Server")
        except Exception as e:
            logging.error(f"Backup Server error: {e}")
        finally:
            self.sock.close()

if __name__ == "__main__":
    DHCPBackupServer().start()