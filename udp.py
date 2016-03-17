from collections import namedtuple
import struct
import threading
import time
import socket
import netifaces
import binascii
from tcp import tcp_handling

PORT = 1234
stop_threads = False
stop_tbk_threads = False
table_lock = threading.Lock()
table = {}
cnt = 0

Info = namedtuple("Info", ["host_name", "timestamp", "ip", "cnt"])


def restructure():
    global cl_udp, ser_udp, tbk
    cl_udp.start()
    stop_tbk_threads = True



def server_udp():
    global table_lock, table
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = ('', PORT)
    print('[server_udp] starting up on ' + str(PORT) + ' port')
    sock.bind(server_address)
    sock.settimeout(2)
    wait_restructure = False
    while not stop_threads:
        print('[server_udp] waiting to receive message')
        try:
            data, address = sock.recvfrom(4096)
        except socket.timeout:
            print('[server_udp] no messages received in 2 seconds')
            print('[server_udp] ring determined')
            tcp_handling(table)

        else:
            if data:
                if len(data) == 1:
                    restructure()
                else:
                    print(
                        '[server_udp] received {} bytes from {}'.format(
                            str(len(data)),
                            address))
                    MAC_ADDR, _, HOST_NAME, TIMESTAMP, CNT = \
                        unpuck_message(data)
                    info = Info(HOST_NAME, TIMESTAMP, address[0], CNT)
                    table_lock.acquire()
                    table[MAC_ADDR] = info
                    table_lock.release()
                    print(table)
                    print("DATA: ", unpuck_message(data))
    sock.close()
    print('[server_udp] closing socket')


def pack_message():
    global cnt
    HOST_NAME = bytes(socket.gethostname(), encoding='utf-8')
    LEN_HOST_NAME = struct.pack('!B', len(HOST_NAME))
    addrs = netifaces.ifaddresses('wlan0')
    MAC_ADDR = addrs[netifaces.AF_LINK][0]['addr']
    MAC_ADDR = binascii.unhexlify(MAC_ADDR.replace(':', ''))
    TIMESTAMP = struct.pack('!Q', int(time.time()))
    CNT = cnt
    LEN_CNT = len(str(CNT))
    LEN_CNT_B = struct.pack('!B', LEN_CNT)
    CNT_B = bytes(str(CNT), encoding='utf-8')
    # print("MAC_ADDR = {}".format(MAC_ADDR))
    # print("LEN_HOST_NAME = {}".format(LEN_HOST_NAME))
    # print("HOST_NAME = {}".format(HOST_NAME))
    # print("TIMESTAMP = {}".format(TIMESTAMP))
    # print("CNT = {}".format(CNT))
    msg = b"".join(
        [MAC_ADDR, LEN_HOST_NAME, HOST_NAME, TIMESTAMP, LEN_CNT_B, CNT_B])
    return msg


def unpuck_message(msg):
    if len(msg) == 1:
        return None, None, None, None, None
    addr = bytes.decode(binascii.hexlify(msg[:6]))
    t = iter(addr)
    MAC_ADDR = ':'.join(a + b for a, b in zip(t, t))
    (LEN_HOST_NAME, *_) = struct.unpack("!B", msg[6:7])
    HOST_NAME = bytes.decode(msg[7:7 + LEN_HOST_NAME])
    (TIMESTAMP, *_) = struct.unpack("!Q", msg[
                                          7 + LEN_HOST_NAME:7 + LEN_HOST_NAME + 8])
    (LEN_CNT, *_) = struct.unpack("!B", msg[
                                        7 + LEN_HOST_NAME + 8:7 + LEN_HOST_NAME + 8 + 1])
    CNT = bytes.decode(
        msg[7 + LEN_HOST_NAME + 8 + 1:7 + LEN_HOST_NAME + 8 + 1 + LEN_CNT])
    CNT = int(CNT)
    # print("MAC_ADDR = {}".format(MAC_ADDR))
    # print("LEN_HOST_NAME = {}".format(LEN_HOST_NAME))
    # print("HOST_NAME = {}".format(HOST_NAME))
    # print("TIMESTAMP = {}".format(TIMESTAMP))
    # CNT = 0
    return MAC_ADDR, LEN_HOST_NAME, HOST_NAME, TIMESTAMP, CNT


def client_udp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    server_address = ('<broadcast>', PORT)
    try:
        message = pack_message()
        print('[client_udp] sending ' + str(message))
        sock.sendto(message, server_address)
        time.sleep(5)
    finally:
        print('[client_udp] closing socket')
        sock.close()


def table_keaper():
    global stop_tbk_threads
    while not stop_threads:
        if stop_tbk_threads:
            table.clear()
            stop_tbk_threads = False
            continue
        time.sleep(5)
        table_lock.acquire()
        for k, v in table:
            if v.timestamp < time.time() - 25:
                del table[k]
        table_lock.release()


# msg = pack_message()
# unpuck_message(msg)

ser_udp = threading.Thread(target=server_udp)
cl_udp = threading.Thread(target=client_udp)
tbk = threading.Thread(target=table_keaper)

ser_udp.start()
cl_udp.start()

while not stop_threads:
    if 'q' in input():
        stop_threads = True
