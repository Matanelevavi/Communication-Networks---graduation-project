import socket
import sys
import logging
import time
from src.config import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s -BACKUP DHCP- %(message)s', datefmt='%H:%M:%S', stream=sys.stdout)

class DHCPBackupServer:
    #set up the backup UDP socket and prepare a list of backup IP addresses.
    def __init__(self):
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.sock.bind(DHCP_BACKUP_ADD)
        self.pool_ip=list(BACKUP_IPS)
        self.used_ips={}

    # Listen for clients. Wait 2 seconds to let the main server answer first then offer a backup IP if needed.
    def start(self):
        logging.info(f"Backup DHCP Server listening on {DHCP_BACKUP_ADD}")
        try:
            while True:
                data,cl_add = self.sock.recvfrom(BUFF_SIZE)
                msg=data.decode(ENCODING)

                if msg==DISCOVER_MSG:
                    time.sleep(2) #Lets the main server answer first
                    if not self.pool_ip:
                        logging.warning(f"Backup IP pool finished, Rejecting {cl_add}")
                        self.sock.sendto("DHCP: No IPs".encode(ENCODING),cl_add)
                        continue

                    new_ip=self.pool_ip.pop(0)
                    self.used_ips[cl_add]=new_ip
                    reply=f"{OFFER_MSG}:{new_ip}"
                    self.sock.sendto(reply.encode(ENCODING),cl_add)
                    logging.info(f"Offered {new_ip} to {cl_add}")

                elif msg.startswith(REQUEST_MSG):
                    wanted_ip = msg.split(":")[1]
                    if self.used_ips.get(cl_add)==wanted_ip:
                        reply=f"{ACK_MSG}:{wanted_ip}"
                        self.sock.sendto(reply.encode(ENCODING), cl_add)
                        logging.info(f"ACK sent for {wanted_ip}, IPs remaining: {len(self.pool_ip)}")
                    else:
                        #Client accepted the primary server offer so silently ignore
                        pass

                elif msg.startswith("DHCP_RELEASE"):
                    released_ip = msg.split(":")[1]
                    if cl_add in self.used_ips and self.used_ips[cl_add] == released_ip:
                        del self.used_ips[cl_add]
                        self.pool_ip.append(released_ip)
                        logging.info(f"Released IP {released_ip} from {cl_add}. IPs remaining: {len(self.pool_ip)}")
        except KeyboardInterrupt:
            logging.info("Turn off Backup DHCP Server")
        except Exception as e:
            logging.error(f"Backup Server error: {e}")
        finally:
            self.sock.close()

if __name__ == "__main__":
    DHCPBackupServer().start()