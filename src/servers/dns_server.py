import socket
import logging
import sys
from src.config import *

logging.basicConfig(level=logging.INFO,format='%(asctime)s -DNS- %(message)s',datefmt='%H:%M:%S',stream=sys.stdout)

class DNSServer:
    def __init__(self):
        #init the UDP socket and create a dictionary to save the IP for our domain
        self.server_sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            #we use a custom port (8053) instead of 53 to avoid errors
            self.server_sock.bind(DNS_ADD)
        except OSError:
            logging.error("Port Problem, DNS Server is already running or port in use so exiting")
            sys.exit(1)
        #in memory dictionary acting as our DNS table for fast O(1)
        self.dns_records={MY_DOMAIN:APP_SER_IP}

    #listen for client requests in a loop and close the socket safely
    def start(self):
        logging.info(f"DNS Server listen on {DNS_ADD}")
        try:
            while True:
                data,client_add=self.server_sock.recvfrom(BUFF_SIZE)
                domain_name=data.decode(ENCODING).strip()
                self.find_ip(domain_name,client_add)
        except KeyboardInterrupt:
            logging.info("Turn off DNS server")
        finally:
            self.server_sock.close()

    #check if the domain exists in our dictionary and send the IP or an error back
    def find_ip(self,domain,client_add):
        if domain in self.dns_records:
            resolved_ip=self.dns_records[domain]
            ans=f"RESOLVED:{resolved_ip}"
            logging.info(f"Resolved {domain} to {resolved_ip} for {client_add}")
        else:
            ans="ERROR:Domain not found"
            logging.warning(f"Failed to resolve {domain} for {client_add}")
        self.server_sock.sendto(ans.encode(ENCODING),client_add)

if __name__=="__main__":
    DNSServer().start()