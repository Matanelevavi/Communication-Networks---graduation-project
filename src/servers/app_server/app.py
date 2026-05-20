import socket
import threading
import json
import sys
import logging
import random
from src.config import *
from src.servers.app_server.logic import WeatherLogic
from src.servers.app_server.agent import FileAgent
from src.servers.app_server.rudp import RUDP

logging.basicConfig(level=logging.INFO, format='%(asctime)s -SERVER- %(message)s', datefmt='%H:%M:%S', stream=sys.stdout)

class AppServer:
    #setup the logic, agent, and two sockets (TCP and UDP).
    def __init__(self):
        self.logic = WeatherLogic()
        self.agent = FileAgent()
        self.active_transfers = set()

        # Setup Standard TCP
        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_sock.bind(APP_ADD)
        self.tcp_sock.listen(5)

        # Setup Reliable UDP (RUDP)
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.bind(APP_ADD)

    #route the client's request to the right logic: get weather, list files, or download a file
    def pros_request(self, payld):
        action = payld.get("action", "FORECAST")

        if action == "FORECAST":
            city = payld.get("city")
            safe_city = city.replace(" ", "_")
            cached_result = self.agent.get_cached_forecast(safe_city)
            if cached_result:
                return cached_result
            profiles = payld.get("profiles")

            weather_data = self.logic.fetch_weather(city)
            if weather_data and weather_data.get("error"):
                return weather_data["error"]

            advice = self.logic.get_ai_recommendation(weather_data, profiles)
            self.agent.save_text_file(f"{safe_city}_forecast.txt", advice)

            csv_bytes = self.logic.download_weather_csv_report(city, weather_data["lat"], weather_data["lon"])
            if csv_bytes:
                self.agent.save_binary_file(f"{safe_city}_full_report.csv", csv_bytes)
            return advice

        elif action == "FTP_LIST":
            return self.agent.get_ftp_file_list()

        elif action == "FTP_GET":
            filename= payld.get("filename", "")
            return self.agent.get_ftp_file_content(filename)

        return "Error: Unknown action requested."

    #handle a standard TCP connection, read the JSON request, send the response and close
    def handle_tcp_client(self, client_sock, addr):
        try:
            data = client_sock.recv(4096).decode(ENCODING)
            if data:
                payload = json.loads(data)
                response = self.pros_request(payload)

                if isinstance(response, str):
                    client_sock.sendall(response.encode(ENCODING))
                else:
                    client_sock.sendall(response)

        except Exception as e:
            logging.error(f"TCP client error: {e}")
        finally:
            client_sock.close()

    #keep listening for new TCP clients and create a new thread for each one
    def run_tcp(self):
        logging.info(f"TCP listening on {APP_ADD}")
        while True:
            try:
                client_sock, addr = self.tcp_sock.accept()
                logging.info(f"TCP connection from {addr}")
                threading.Thread(target=self.handle_tcp_client, args=(client_sock, addr), daemon=True).start()
            except Exception as e:
                logging.error(f"TCP loop error: {e}")

    #create a new temporary socket just to send the RUDP response back to the client
    def handle_udp_request(self, payload, addr):
        try:
            respo = self.pros_request(payload)

            # Use an ephemeral socket for the transfer to avoid ACK collisions on the main port
            transfer_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            transfer_rudp = RUDP(transfer_sock)
            transfer_rudp.reliable_send(respo, addr)
            transfer_sock.close()

        except Exception as e:
            logging.error(f"Transfer thread error: {e}")
        finally:
            self.active_transfers.discard(addr)

    #listen for UDP messages, Manage connections (FIN) and start threads for new valid requests
    def run_udp(self):
        logging.info(f"RUDP listening on {APP_ADD}")
        try:
            while True:
                try:
                    self.udp_sock.settimeout(None)
                    data,addr = self.udp_sock.recvfrom(8192)
                    msg =data.decode(ENCODING)

                    # Client gracefully disconnecting
                    if msg.startswith("FIN"):
                        logging.info(f"Client {addr} started dissolution (FIN).")
                        self.udp_sock.sendto(b"FIN-ACK",addr)
                        continue

                    if msg.startswith("SEQ:1"):
                        if SIMULATE_LOSS and random.random()< LOSS_RATE:
                            logging.warning(f"Simulated packet drop from {addr}")
                            continue

                        self.udp_sock.sendto(b"ACK:1", addr)

                        if addr in self.active_transfers:
                            continue

                        self.active_transfers.add(addr)

                        payld_str = msg.split("|")[1]
                        payld = json.loads(payld_str)

                        threading.Thread(target=self.handle_udp_request, args=(payld, addr), daemon=True).start()

                except ConnectionResetError:
                    #ignore Windows ICMP Port Unreachable errors
                    pass
                except Exception as e:
                    logging.error(f"UDP loop error: {e}")
        except KeyboardInterrupt:
            logging.info("Shutting down App Server gracefully...")
        finally:
            self.tcp_sock.close()
            self.udp_sock.close()

    #start the server by running TCP in the background and keeping UDP on the main thread
    def start(self):
        logging.info("Starting Multi-Threaded App Server (WeatherWear)")
        threading.Thread(target=self.run_tcp, daemon=True).start()
        self.run_udp()

if __name__ == "__main__":
    AppServer().start()