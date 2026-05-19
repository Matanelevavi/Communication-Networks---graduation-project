import random
import socket
import logging
import zlib
import time


class RUDP:
    def __init__(self, sock):
        self.sock = sock
        # Dynamic window for congestion control
        self.cwnd = 1.0
        self.max_cwnd = 20.0
        self.chunk_size = 800

    def reliable_send(self, data, addr):
        if isinstance(data, str):
            data = data.encode('utf-8')

        # Efficient integer division ceiling
        total_chunks = (len(data) + self.chunk_size - 1) // self.chunk_size
        if total_chunks == 0:
            total_chunks = 1

        # Pythonic chunk generation
        chunks = {
            i + 1: data[i * self.chunk_size : (i + 1) * self.chunk_size]
            for i in range(total_chunks)
        }

        unacked = set(chunks.keys())
        window_start = 1
        max_retries = 3
        retry_count = 0

        dup_ack_count = 0
        last_ack = -1

        logging.info(f"Transferring {total_chunks} chunks to {addr}")

        while unacked and retry_count < max_retries:
            window_end = min(window_start + int(self.cwnd), total_chunks + 1)

            for seq in range(window_start, window_end):
                if seq in unacked:
                    chk = zlib.crc32(chunks[seq]) & 0xffffffff
                    header = f"SEQ:{seq}|TOTAL:{total_chunks}|CHK:{chk}|".encode('utf-8')

                    try:
                        if random.random()<0.2:
                            logging.info(f"Packet loss simulation {seq}")
                            continue
                        if seq==2 and retry_count==0:
                            logging.info(f"Delaying packet {seq} for 2 seconds")
                            time.sleep(2)
                        self.sock.sendto(header+chunks[seq], addr)
                    except Exception:
                        pass

            self.sock.settimeout(1.0)
            try:
                ack_data, _ = self.sock.recvfrom(1024)
                ack_msg = ack_data.decode('utf-8')

                if ack_msg.startswith("ACK:"):
                    ack_seq = int(ack_msg.split(":")[1])

                    if ack_seq in unacked:
                        unacked.remove(ack_seq)
                        retry_count = 0
                        dup_ack_count = 0
                        last_ack = ack_seq

                        # Additive increase
                        self.cwnd = min(self.cwnd + 1.0, self.max_cwnd)

                        # Slide the window forward
                        while window_start not in unacked and window_start <= total_chunks:
                            window_start += 1

                    elif ack_seq == last_ack:
                        dup_ack_count += 1

                        # Fast retransmit on 3 dup ACKs
                        if dup_ack_count == 3:
                            logging.warning(f"Fast Retransmit triggered for packet {window_start}")

                            # Multiplicative decrease
                            self.cwnd = max(self.cwnd / 2.0, 1.0)

                            if window_start in unacked:
                                chk = zlib.crc32(chunks[window_start]) & 0xffffffff
                                header = f"SEQ:{window_start}|TOTAL:{total_chunks}|CHK:{chk}|".encode('utf-8')
                                self.sock.sendto(header + chunks[window_start], addr)

                            dup_ack_count = 0

            except socket.timeout:
                # Multiplicative decrease on drop
                self.cwnd = max(self.cwnd / 2.0, 1.0)
                retry_count += 1
            except ConnectionResetError:
                logging.warning(f"Client {addr} disconnected abruptly.")
                break
            except Exception:
                break

        self.sock.settimeout(None)

        if not unacked:
            logging.info(f"Transfer to {addr} complete.")
        else:
            logging.warning(f"Transfer to {addr} aborted. Max retries reached.")