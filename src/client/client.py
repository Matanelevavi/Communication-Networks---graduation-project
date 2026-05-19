import socket
import logging
import json
import sys
import time
import zlib
from src.config import *
from src.client.gui import get_user_data_gui, show_result_gui, show_ftp_list_gui

logging.basicConfig(level=logging.INFO, format='%(asctime)s -CLIENT- %(message)s', datefmt='%H:%M:%S', stream=sys.stdout)

class NetworkClient:
    def __init__(self):
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client_socket.bind((HOST,0))
        self.client_socket.settimeout(TIMEOUT)
        self.my_ip = None
        self.app_server_ip = None
        self.dns_cache = {}
        self.DNS_TTL = 60

    def get_ip_via_dhcp(self):
        logging.info("Starting DHCP DORA")
        try:
            self.client_socket.sendto(DISCOVER_MSG.encode(ENCODING), DHCP_ADD)
            self.client_socket.sendto(DISCOVER_MSG.encode(ENCODING), DHCP_BACKUP_ADD)

            while True:
                try:
                    data, server_addr = self.client_socket.recvfrom(BUFF_SIZE)
                    offer = data.decode(ENCODING)

                    if offer.startswith(OFFER_MSG):
                        offered_ip = offer.split(":")[1]
                        logging.info(f"Got OFFER: {offered_ip} from {server_addr[1]}")

                        req_msg = f"{REQUEST_MSG}:{offered_ip}"
                        self.client_socket.sendto(req_msg.encode(ENCODING), server_addr)

                        while True:
                            try:
                                ack_data, _ = self.client_socket.recvfrom(BUFF_SIZE)
                                ack = ack_data.decode(ENCODING)

                                if ack.startswith(ACK_MSG):
                                    self.my_ip = ack.split(":")[1]
                                    logging.info(f"DHCP successful. My IP: {self.my_ip}")
                                    return True
                                elif ack.startswith(OFFER_MSG):
                                    continue # ignore late offers
                            except ConnectionResetError:
                                continue

                except ConnectionResetError:
                    continue

        except socket.timeout:
            logging.error("DHCP Timeout")
            return False

    def resolve_dns(self, target_domain):
        # check cache first with TTL
        if target_domain in self.dns_cache:
            cached_ip, timestamp = self.dns_cache[target_domain]
            if time.time()-timestamp<self.DNS_TTL:
                logging.info(f"DNS resolved from cache: {cached_ip} (TTL valid)")
                return cached_ip
            else:
                logging.info(f"DNS cache for {target_domain} expired. Fetching fresh IP.")
                return self.dns_cache[target_domain]

        logging.info(f"Resolving {target_domain} via network")
        try:
            self.client_socket.sendto(target_domain.encode(ENCODING), DNS_ADD)
            data, _ = self.client_socket.recvfrom(BUFF_SIZE)
            res = data.decode(ENCODING)

            if res.startswith("RESOLVED:"):
                self.app_server_ip = res.split(":")[1]
                self.dns_cache[target_domain] = (self.app_server_ip, time.time())
                logging.info(f"DNS result: {self.app_server_ip}")
                return self.app_server_ip

            logging.error(f"DNS failed: {res}")
            return None
        except socket.timeout:
            logging.error("DNS timeout.")
            return None

    def tcp_send_and_receive(self, payload_str):
        logging.info("[TCP] Connecting")
        tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            tcp_sock.connect((self.app_server_ip, APP_PORT))
            tcp_sock.sendall(payload_str.encode(ENCODING))
            tcp_sock.settimeout(20.0)

            response = tcp_sock.recv(8192)
            try:
                return response.decode(ENCODING)
            except UnicodeDecodeError:
                return response # return raw bytes for files

        except Exception as e:
            logging.error(f"[TCP] Error: {e}")
            return None
        finally:
            tcp_sock.close()

    def reliable_send_and_receive(self, payload_str):
        addr = (self.app_server_ip, APP_PORT)
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.settimeout(RUDP_TIMEOUT)

        packet = f"SEQ:1|{payload_str}"
        ack_ok = False

        #send request with retries
        for attempt in range(MAX_RETRIES):
            logging.info(f"[RUDP] Sending request ({attempt+1}/{MAX_RETRIES})")
            udp_sock.sendto(packet.encode(ENCODING), addr)
            try:
                ack_data, _ = udp_sock.recvfrom(BUFF_SIZE)
                if ack_data.decode(ENCODING) == "ACK:1":
                    ack_ok = True
                    break
            except socket.timeout:
                pass

        if not ack_ok:
            logging.error("[RUDP] Server unreachable.")
            udp_sock.close()
            return None

        logging.info("[RUDP] Waiting for chunks")
        udp_sock.settimeout(20.0)
        chunks = {}
        total = None

        #receive sliding window chunks
        while True:
            try:
                data, server_info = udp_sock.recvfrom(8500)
                parts = data.split(b'|', 3)
                if len(parts) == 4:
                    seq = int(parts[0].split(b':')[1])
                    total = int(parts[1].split(b':')[1])
                    expected_chk = int(parts[2].split(b':')[1])
                    payload = parts[3]

                    actual_chk = zlib.crc32(payload) & 0xffffffff
                    if actual_chk != expected_chk:
                        logging.warning(f"[RUDP] Corrupted chunk {seq} dropped. CRC mismatch!")
                        continue #

                    if seq not in chunks:
                        chunks[seq] = payload
                        logging.info(f"[RUDP] Chunk {seq}/{total} received.")

                    udp_sock.sendto(f"ACK:{seq}".encode('utf-8'), server_info)

                    if len(chunks) == total:
                        # blast final acks to be safe
                        for _ in range(3):
                            udp_sock.sendto(f"ACK:{seq}".encode('utf-8'), server_info)
                            time.sleep(0.1)

                        udp_sock.close()
                        full_data = b"".join(chunks[i] for i in range(1, total + 1))

                        try:
                            return full_data.decode('utf-8')
                        except UnicodeDecodeError:
                            return full_data

            except socket.timeout:
                logging.error("[RUDP] Timeout receiving chunks")
                udp_sock.close()
                return None

    def close(self):
        try:
            if self.app_server_ip:
                logging.info("[TEARDOWN] Sending FIN to server")
                self.client_socket.sendto(b"FIN", (self.app_server_ip, APP_PORT))
                self.client_socket.settimeout(2.0)
                try:
                    ack_data, _ = self.client_socket.recvfrom(1024)
                    if ack_data.decode(ENCODING) == "FIN-ACK":
                        logging.info("[TEARDOWN] Received FIN-ACK, Connection closed elegantly")
                except socket.timeout:
                    logging.warning("[TEARDOWN] Timeout waiting for FIN-ACK, Forcing close")
            self.client_socket.close()
        except Exception:
            pass

if __name__ == "__main__":
    client = NetworkClient()

    # setup network
    if not client.get_ip_via_dhcp():
        sys.exit(1)

    if not client.resolve_dns(MY_DOMAIN):
        sys.exit(1)

    logging.info("Starting GUI")

    # main app loop
    while True:
        action, city, profiles, protocol = get_user_data_gui()

        if not action:
            client.close()
            break

        req_data = {"action": action}
        if action == "FORECAST":
            req_data["city"] = city
            req_data["profiles"] = profiles

        payload = json.dumps(req_data)
        res = None

        if protocol == "TCP":
            res = client.tcp_send_and_receive(payload)
        else:
            res = client.reliable_send_and_receive(payload)

        # handle UI routing based on response
        if res:
            if action == "FTP_LIST":
                file_choice = show_ftp_list_gui(res)
                if file_choice:
                    file_req = json.dumps({"action": "FTP_GET", "filename": file_choice})

                    if protocol == "TCP":
                        file_data = client.tcp_send_and_receive(file_req)
                    else:
                        file_data = client.reliable_send_and_receive(file_req)

                    if file_data:
                        show_result_gui("FTP_GET", file_choice, file_data)
            else:
                show_result_gui(action, city, res)