import socket
import sys
import logging
from src.config import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s -DHCP- %(message)s', datefmt='%H:%M:%S', stream=sys.stdout)

class DHCPServer:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(DHCP_ADD)
        self.pool_ip= list(POOL_IP)
        self.used_ips = {}

    def start(self):
        logging.info(f"DHCP Server listening on {DHCP_ADD}")
        try:
            while True:
                data,client_add = self.sock.recvfrom(BUFF_SIZE)
                msg=data.decode(ENCODING)
                if msg==DISCOVER_MSG:
                    if not self.pool_ip:
                        logging.warning(f"IP pool finished, Rejecting {client_add}")
                        self.sock.sendto("DHCP: No IPs available".encode(ENCODING),client_add)
                        continue

                    new_ip=self.pool_ip.pop(0)
                    self.used_ips[client_add]=new_ip
                    reply=f"{OFFER_MSG}:{new_ip}"
                    self.sock.sendto(reply.encode(ENCODING),client_add)
                    logging.info(f"Offered {new_ip} to {client_add}")

                elif msg.startswith(REQUEST_MSG):
                    wanted_ip=msg.split(":")[1]
                    if self.used_ips.get(client_add)==wanted_ip:
                        reply=f"{ACK_MSG}:{wanted_ip}"
                        self.sock.sendto(reply.encode(ENCODING),client_add)
                        logging.info(f"ACK sent for {wanted_ip}, IPs remaining: {len(self.pool_ip)}")
                    else:
                        logging.warning(f"Invalid IP request from {client_add}: {wanted_ip}")

                elif msg.startswith("DHCP_RELEASE"):
                    released_ip = msg.split(":")[1]
                    if client_add in self.used_ips and self.used_ips[client_add] == released_ip:
                        del self.used_ips[client_add]
                        self.pool_ip.append(released_ip)
                        logging.info(f"Released IP {released_ip} from {client_add}. IPs remaining: {len(self.pool_ip)}")
        except KeyboardInterrupt:
            logging.info("Turn off DHCP Server.")
        finally:
            self.sock.close()

if __name__ == "__main__":
    DHCPServer().start()