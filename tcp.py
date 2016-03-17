import socket
import threading
import netifaces

PORT = 1235
LOCALHOST = '127.0.0.1'
waiting = False


def server_tcp():
    TCP_IP = LOCALHOST
    BUFFER_SIZE = 20  # Normally 1024, but we want fast response

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', PORT))
    s.listen()
    print('[server_tcp] Listen')
    conn, addr = s.accept()
    print('[server_tcp] Connection address:', addr)
    while 1:
        data = conn.recv(BUFFER_SIZE)
        if not data:
            break
        print("[server_tcp] received data:", data)
        conn.send(data)  # echo
    conn.close()

#
# def client_tsp():
#     TCP_IP = '192.168.1.100'
#     BUFFER_SIZE = 1024
#     MESSAGE = "Hello, World!"
#
#     s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#     s.connect((TCP_IP, PORT))
#     s.send(bytes(MESSAGE, encoding='utf-8'))
#     data = s.recv(BUFFER_SIZE)
#     s.close()
#
#     print("[client_tsp]received data:", data)

ser_tcp = threading.Thread(target=server_tcp)
# cl_tcp = threading.Thread(target=client_tsp)
ser_tcp.start()
# a = input()
# cl_tcp.start()


