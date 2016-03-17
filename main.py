from collections import namedtuple
import socket
import struct
import threading
import netifaces
import binascii
import time
from queue import Queue

__author__ = 'rita'
PORT_UDP = 1234
PORT_TCP = 1235
LOCALHOST = '127.0.0.1'
cnt = 0

table_lock = threading.Lock()
table = {}
MAC_ADDR = netifaces.ifaddresses('wlp7s0')[netifaces.AF_LINK][0]['addr']
message_box = Queue()
recycling = threading.Event()

with open('pi.txt', 'r') as f:
    pi_string = f.readline()

Info = namedtuple("Info", ["host_name", "timestamp", "ip", "cnt"])


class ServerUdp:
    def __init__(self):
        self.stop_thread = threading.Event()
        self.thread = None

    def run(self):
        global table
        recycling.set()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_address = ('', PORT_UDP)
        print('[server_udp] starting up on ' + str(PORT_UDP) + ' port')
        sock.bind(server_address)
        sock.settimeout(2)
        while not self.stop_thread.is_set():
            print('[server_udp] waiting to receive message')
            try:
                data, address = sock.recvfrom(4096)
            except socket.timeout:
                print('[server_udp] no messages received in 2 seconds')
                if recycling.is_set():
                    print('[server_udp] cycle constructed. Starting communication')
                    recycling.clear()
            else:
                if is_recycle_msg(data):
                    print('[server_udp] Received recycle init message from {}'.format(address[0]))
                    recycling.set()
                    table.clear()
                    cl_udp.send_info()
                elif len(data) != 0:
                    if not recycling.is_set():
                        recycling.set()
                        print('[server_udp] INIT RECYCLE: udp message from unknown host')
                        cl_udp.send_recycle()
                    print('[server_udp] received {} bytes from {}'.format(str(len(data)), address))
                    add_to_table(data, address)

        sock.close()
        print('[server_udp] closing socket')

    def start(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.start()


class ClientUdp:
    def __init__(self):
        pass

    def run(self, message):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        server_address = ('<broadcast>', PORT_UDP)
        try:
            print('[client_udp] sending ' + str(message))
            sock.sendto(message, server_address)
        finally:
            print('[client_udp] closing socket')
            sock.close()

    def send_recycle(self):
        threading.Thread(target=self.run, args=(get_recycle_msg(),)).start()

    def send_info(self):
        threading.Thread(target=self.run, args=(get_info_msg(),)).start()


class ServerTcp:
    def __init__(self):
        self.stop_thread = threading.Event()
        self.restart_thread = threading.Event()
        self.thread = None

    def run(self):
        print('[server_tcp] Starting')
        global cnt
        BUFFER_SIZE = 1024

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('', PORT_TCP))
        s.listen(1)
        print('[server_tcp] listening on the port {}'.format(PORT_TCP))
        s.settimeout(3)

        while not self.stop_thread.is_set():
            self.restart_thread.clear()
            while recycling.is_set() and not self.stop_thread.is_set():
                time.sleep(.5)
            time.sleep(3)
            if self.stop_thread.is_set():
                break
            if self.restart_thread.is_set() or recycling.is_set():
                continue
            prev = get_prev()
            cl_tcp.start()
            conn = None
            # Maybe it's too complicated, but it must work
            while conn is None and not self.restart_thread.is_set() and not self.stop_thread.is_set() and not recycling.is_set():
                try:
                    conn, addr = s.accept()
                except socket.timeout:
                    pass
            if self.restart_thread.is_set() or recycling.is_set():
                if conn is not None:
                    conn.close()
                continue
            if self.stop_thread.is_set():
                if conn is not None:
                    conn.close()
                break

            print('[server_tcp] accepting connection from {}'.format(addr))
            if addr[0] != table[prev].ip:
                print('[server_tcp] Received connection from wrong address {}. {} expected. Recycling'.format(addr[0], table[prev].ip))
                conn.close()
                cl_udp.send_recycle()
                recycling.set()
                continue

            conn.settimeout(30)
            while not self.restart_thread.is_set() and not self.stop_thread.is_set() and not recycling.is_set():
                try:
                    data = conn.recv(BUFFER_SIZE)
                except socket.timeout:
                    if len(table) > 1:
                        conn.close()
                        cl_udp.send_recycle()
                        break
                    else:
                        print('[server_tcp] no data received in 30 seconds')
                        continue
                if len(data) == 0:
                    print('[server_tcp] connection lost')
                    cl_udp.send_recycle()
                    break
                unpacked_data = unpack_data_tcp(data)
                cnt = len(unpacked_data)
                print("[server_tcp] received data of len {}: {}".format(cnt, data))
                message_box.put(unpacked_data)
            conn.close()
        s.close()

    def start(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.start()



class ClientTcp:
    def __init__(self):
        self.stop_thread = threading.Event()
        self.thread = None

    def run(self, stop_event):
        print('[client_tcp] starting')
        next = get_next()
        # print('Next:', next, table[next])

        TCP_IP = table[next].ip

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        try:
            print('[client_tcp] conecting to {}:{}'.format(TCP_IP, PORT_TCP))
            s.connect((TCP_IP, PORT_TCP))
        except socket.timeout:
            cl_udp.send_recycle()
            return

        mac, cnt = get_min()
        if len(table) > 1 and mac == MAC_ADDR:
            print('[client_tcp] I must send initial message')
            message_box.put(pi_string[:cnt+1])
        else:
            print('[client_tcp] Someone knows more then me')

        while not stop_event.is_set() and not recycling.is_set():
            time.sleep(2)
            if not message_box.empty():
                msg = message_box.get()
                if len(msg) < len(pi_string):
                    msg += pi_string[len(msg)]
                print("[client_tcp] send dataof len {}: {}".format(len(msg), msg))
                s.send(pack_data_tcp(msg))
        s.close()

    def start(self):
        time.sleep(2)
        self.stop_thread = threading.Event()
        self.thread = threading.Thread(target=self.run, args=(self.stop_thread,))
        self.thread.start()



def pack_data_tcp(msg):
    str_len_msg = str(len(msg)).rjust(4, '0')
    return bytes(str_len_msg + msg, encoding='utf-8')


def get_recycle_msg():
    return bytes("1", encoding='utf-8')


def is_recycle_msg(data):
    return len(data) == 1


def get_info_msg():
    global cnt
    MAC = binascii.unhexlify(MAC_ADDR.replace(':', ''))
    HOST_NAME = bytes(socket.gethostname(), encoding='utf-8')
    LEN_HOST_NAME = struct.pack('!B', len(HOST_NAME))
    TIMESTAMP = struct.pack('!Q', int(time.time()))
    CNT = cnt
    LEN_CNT_B = struct.pack('!B', len(str(CNT)))
    CNT_B = bytes(str(CNT), encoding='utf-8')
    # print("MAC_ADDR = {}".format(MAC_ADDR))
    # print("LEN_HOST_NAME = {}".format(LEN_HOST_NAME))
    # print("HOST_NAME = {}".format(HOST_NAME))
    # print("TIMESTAMP = {}".format(TIMESTAMP))
    # print("CNT = {}".format(CNT))
    msg = b"".join(
        [MAC, LEN_HOST_NAME, HOST_NAME, TIMESTAMP, LEN_CNT_B, CNT_B])
    return msg


def add_to_table(data, address):
    global table_lock, table
    MAC, _, HOST_NAME, TIMESTAMP, CNT = unpack_message(data)
    info = Info(HOST_NAME, TIMESTAMP, address[0], CNT)
    table_lock.acquire()
    table[MAC] = info
    table_lock.release()
    print('Table: {}'.format(table))
    print("DATA: ", unpack_message(data))


def unpack_message(msg):
    addr = bytes.decode(binascii.hexlify(msg[:6]))
    t = iter(addr)
    MAC = ':'.join(a + b for a, b in zip(t, t))
    (LEN_HOST_NAME, *_) = struct.unpack("!B", msg[6:7])
    HOST_NAME = bytes.decode(msg[7:7 + LEN_HOST_NAME])
    (TIMESTAMP, *_) = struct.unpack(
        "!Q", msg[7 + LEN_HOST_NAME:7 + LEN_HOST_NAME + 8])
    (LEN_CNT, *_) = struct.unpack(
        "!B", msg[7 + LEN_HOST_NAME + 8:7 + LEN_HOST_NAME + 8 + 1])
    CNT = bytes.decode(
        msg[7 + LEN_HOST_NAME + 8 + 1:7 + LEN_HOST_NAME + 8 + 1 + LEN_CNT])
    CNT = int(CNT)
    # print("MAC_ADDR = {}".format(MAC_ADDR))
    # print("LEN_HOST_NAME = {}".format(LEN_HOST_NAME))
    # print("HOST_NAME = {}".format(HOST_NAME))
    # print("TIMESTAMP = {}".format(TIMESTAMP))
    # CNT = 0
    return MAC, LEN_HOST_NAME, HOST_NAME, TIMESTAMP, CNT


ser_udp = ServerUdp()
cl_udp = ClientUdp()
ser_tcp = ServerTcp()
cl_tcp = ClientTcp()


def get_prev():
    prevs = [mac for mac in table if mac < MAC_ADDR]
    if len(prevs) == 0:
        return max(table)
    return max(prevs)


def get_next():
    nexts = [mac for mac in table if mac > MAC_ADDR]
    if len(nexts) == 0:
        return min(table)
    return min(nexts)


def get_min():
    max_cnt = -1
    max_mac = None
    for mac, row in table.items():
        if row.cnt > max_cnt or row.cnt == max_cnt and mac < max_mac:
            max_cnt = row.cnt
            max_mac = mac
    return max_mac, max_cnt


def unpack_data_tcp(data):
    str_len_msg = bytes.decode(data[0:4])
    len_msg = int(str_len_msg)
    msg = bytes.decode(data[4:4+len_msg])
    return msg

cl_udp.send_recycle()
ser_udp.start()
ser_tcp.start()
time.sleep(0.5)
cl_udp.send_info()
while True:
    # print('Table: {}'.format(table))
    s = input()
    if s == 'x':
        cl_tcp.stop_thread.set()
        ser_tcp.stop_thread.set()
        ser_udp.stop_thread.set()
        break
