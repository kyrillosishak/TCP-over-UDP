#!/usr/bin/env python3

import socket
from threading import Thread, Event, Lock
from packet import Packet
from itertools import chain, islice
from random import randint

HOST = '127.0.0.1'

MAX_DATA_SIZE = 32768    # max size of the data to be sent in a packet
MAX_PACKET_SIZE = 33000  # max size of a packet
MAX_SINGLE_SEND = 5      # max # of packets to be sent in a single window


# class TCPSendThread(Thread):
#     """
#     Thread for emulating TCP send of single file by doing these things:
#     1. Bind to specific address, each file will bind to different port
#     2. Send all packet
#     3. Check after timeout if any packet is not acknowledged
#     4. Retry sending unacknowledged packet
#     """
#
#     def __init__(self, src, dest, timeout, packets, event):
#         Thread.__init__(self)
#         self.stopped = event
#         self.src = src
#         self.dest = dest
#         self.timeout = timeout
#         self.unacknowledged_packets = packets
#         self.pid = self.unacknowledged_packets[0].id
#
#     def run(self):
#         with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
#             sock.bind(self.src)
#
#             ack_thread = TCPAckThread(
#                 self.pid, self.unacknowledged_packets, sock)
#             ack_thread.start()
#
#             for unacknowledged_packet in self.unacknowledged_packets[:MAX_SINGLE_SEND]:
#                 sock.sendto(unacknowledged_packet.to_bytes(), self.dest)
#                 print(f'{self.dest} <- {unacknowledged_packet}')
#
#             while not self.stopped.wait(self.timeout):
#                 if len(self.unacknowledged_packets) == 0:
#                     self.stopped.set()
#                 for unacknowledged_packet in self.unacknowledged_packets[:MAX_SINGLE_SEND]:
#                     sock.sendto(
#                         unacknowledged_packet.to_bytes(), self.dest)
#                     print(f'{self.dest} <- {unacknowledged_packet}')
#
#             ack_thread.join()
#
#         print(f'[i] All package for id {self.pid} sent!')

# This class is responsible for sending a single file with stop and wait approach
class TCPSendThread(Thread):
    """
    Thread for emulating TCP send of single file by doing these things:
    1. Bind to specific address, each file will bind to different port
    2. Send all packet using Stop-and-Wait protocol
    3. Check after timeout if any packet is not acknowledged
    4. Retry sending unacknowledged packet
    """

    def __init__(self, src, dest, timeout, packets, event):
        Thread.__init__(self)
        self.stopped = event
        self.src = src
        self.dest = dest
        self.timeout = timeout
        self.unacknowledged_packets = packets
        self.pid = self.unacknowledged_packets[0].id
        self.lock = Lock()

    def run(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(self.src)

            ack_thread = TCPAckThread(
                self.pid, self.unacknowledged_packets, sock)
            ack_thread.start()

            while len(self.unacknowledged_packets) > 0:
                # Send the first unacknowledged packet and wait for acknowledgement
                with self.lock:
                    packet = self.unacknowledged_packets[0]
                    sock.sendto(packet.to_bytes(), self.dest)
                    print(f'{self.dest} <- {packet}')

                # Wait for acknowledgement or timeout
                if self.stopped.wait(self.timeout):
                    continue  # packet was acknowledged, move on to the next one

                # Timeout occurred, retransmit the unacknowledged packet
                with self.lock:
                    sock.sendto(packet.to_bytes(), self.dest)
                    print(f'{self.dest} (Retransmission) <- {packet}')

            ack_thread.join()

        print(f'[i] All packets for id {self.pid} sent and acknowledged!')


class TCPAckThread(Thread):
    """
    Thread for handling acknowledgement by removing packets
    from unacknowledged_packets list and stop on FIN-ACK
    """

    def __init__(self, pid, unacknowledged_packets, sock):
        Thread.__init__(self)
        self.stopped = Event()
        self.unacknowledged_packets = unacknowledged_packets
        self.sock = sock
        self.pid = pid

    def run(self):
        while not self.stopped.is_set():
            data, addr = self.sock.recvfrom(MAX_PACKET_SIZE)
            ack_packet = Packet.from_bytes(data)
            print(f'{addr} -> {ack_packet}')

            if ack_packet in self.unacknowledged_packets:
                self.unacknowledged_packets.remove(ack_packet)

            if ack_packet.get_type() == 'FIN-ACK':
                self.stopped.set()

        print(f'[i] All package for id {self.pid} acknowledged!')


class TCPSend:
    """
    Emulate TCP sending by splitting files into packets
    and spawning a send thread for each file
    """

    def __init__(self, dest, timeout, files):
        all_packets = []

        for file_to_split in files:
            all_packets.append(list(self.file_to_packets(file_to_split)))

        stop_flags = []
        send_threads = []
        base_port = randint(1025, 65534)

        for idx, single_file_packets in enumerate(all_packets):
            stop_flag = Event()
            stop_flags.append(stop_flag)

            src = (HOST, base_port + idx)

            send_thread = TCPSendThread(
                src, dest, timeout, single_file_packets, stop_flag)
            send_threads.append(send_thread)
            send_thread.start()

        for idx, thread in enumerate(send_threads):
            thread.join()

    @staticmethod
    def file_to_packets(filename):
        try:
            with open(filename, 'rb') as file_to_split:
                pid = Packet.pick_id()
                seq = 0
                chunk = file_to_split.read(MAX_DATA_SIZE)

                while chunk:
                    next_chunk = file_to_split.read(MAX_DATA_SIZE)
                    if next_chunk:
                        yield Packet('DATA', pid, seq, len(chunk), chunk)
                        chunk = next_chunk
                    else:
                        yield Packet('FIN', pid, seq, len(chunk), chunk)
                        chunk = False
                    seq += 1
        except OSError as err:
            print(f'File {filename} doesn\'t exist')


if __name__ == '__main__':
    dest_ip = input('Enter destination (IP): ')
    dest_port = input('Enter destination (Port): ')
    dest = (dest_ip.strip(), int(dest_port.strip()))

    timeout = float(input('Timeout (s): '))

    files = input('Files to send (Separated by comma): ')
    files = [f.strip() for f in files.split(',')]

    TCPSend(dest, timeout, files)
