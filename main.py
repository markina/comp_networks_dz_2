from collections import namedtuple
import struct
import threading
import time
import socket
import netifaces
import binascii

PORT = 1234
stop_threads = False
table_lock = threading.Lock()
table = {}

Info = namedtuple("Info", ["host_name", "timestamp", "ip"])


def server():
    global table_lock, table
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = ('', PORT)
    print('[server] starting up on ' + str(PORT) + ' port')
    sock.bind(server_address)
    sock.settimeout(15)
    while not stop_threads:
        print('[server] waiting to receive message')
        try:
            data, address = sock.recvfrom(4096)
        except socket.timeout:
            print('[server] no messages received in 15 seconds')
        else:
            if data:
                print(
                    '[server] received {} bytes from {}'.format(str(len(data)),
                                                                address))
                MAC_ADDR, _, HOST_NAME, TIMESTAMP = unpuck_message(data)
                info = Info(HOST_NAME, TIMESTAMP, address[0])
                table_lock.acquire()
                table[MAC_ADDR] = info
                table_lock.release()
                print(table)
                print("DATA: ", unpuck_message(data))
    sock.close()
    print('[server] closing socket')


def pack_message():
    HOST_NAME = bytes(socket.gethostname(), encoding='utf-8')
    LEN_HOST_NAME = struct.pack('!B', len(HOST_NAME))
    addrs = netifaces.ifaddresses('wlan0')
    MAC_ADDR = addrs[netifaces.AF_LINK][0]['addr']
    MAC_ADDR = binascii.unhexlify(MAC_ADDR.replace(':', ''))
    TIMESTAMP = int(time.time())
    TIMESTAMP = struct.pack('!Q', int(time.time()))

    print("MAC_ADDR = {}".format(MAC_ADDR))
    print("LEN_HOST_NAME = {}".format(LEN_HOST_NAME))
    print("HOST_NAME = {}".format(HOST_NAME))
    print("TIMESTAMP = {}".format(TIMESTAMP))
    msg = b"".join([MAC_ADDR, LEN_HOST_NAME, HOST_NAME, TIMESTAMP])
    return msg


def unpuck_message(msg):
    addr = bytes.decode(binascii.hexlify(msg[:6]))
    t = iter(addr)
    MAC_ADDR = ':'.join(a+b for a, b in zip(t, t))
    (LEN_HOST_NAME, *_) = struct.unpack("!B", msg[6:7])
    HOST_NAME = bytes.decode(msg[7:7+LEN_HOST_NAME])
    (TIMESTAMP, *_) = struct.unpack("!Q", msg[7+LEN_HOST_NAME:7+LEN_HOST_NAME+8])
    # print("MAC_ADDR = {}".format(MAC_ADDR))
    # print("LEN_HOST_NAME = {}".format(LEN_HOST_NAME))
    # print("HOST_NAME = {}".format(HOST_NAME))
    # print("TIMESTAMP = {}".format(TIMESTAMP))
    return MAC_ADDR, LEN_HOST_NAME, HOST_NAME, TIMESTAMP
    # msg = "\n".join([MAC_ADDR, str(LEN_HOST_NAME), HOST_NAME, str(TIMESTAMP)])
    # return msg


def client():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    server_address = ('<broadcast>', PORT)

    try:
        while not stop_threads:
            message = pack_message()
            print('[client] sending ' + str(message))
            sock.sendto(message, server_address)
            time.sleep(5)
    finally:
        print('[client] closing socket')
        sock.close()


def table_ceaper():
    while not stop_threads:
        time.sleep(5)
        table_lock.acquire()
        for k, v in table:
            if v.timestamp < time.time() - 25:
                del table[k]
        table_lock.release()

msg = pack_message()
unpuck_message(msg)

ser = threading.Thread(target=server)
cl = threading.Thread(target=client)
tbc = threading.Thread(target=table_ceaper)
ser.start()
cl.start()

while not stop_threads:
    if 'q' in input():
        stop_threads = True
