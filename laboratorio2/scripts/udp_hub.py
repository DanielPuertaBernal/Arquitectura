#!/usr/bin/env python3
"""Virtual Ethernet hub for the lab cluster's internal network (192.168.100.0/24).

Every VM's second NIC is a QEMU UDP socket that sends its frames to
127.0.0.1:5600 and listens on 127.0.0.1:56NN (kali=5610, workerN=561N).
This hub receives each frame and forwards it to every other node.

Usage: python3 udp_hub.py   (leave it running while the cluster is up)
"""
import socket

HUB = ("127.0.0.1", 5600)
NODES = [("127.0.0.1", port) for port in range(5610, 5615)]

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
sock.bind(HUB)
print(f"hub listening on {HUB[0]}:{HUB[1]}, nodes {[p for _, p in NODES]}", flush=True)

while True:
    frame, src = sock.recvfrom(65535)
    for node in NODES:
        if node != src:
            sock.sendto(frame, node)
