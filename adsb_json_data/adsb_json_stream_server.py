#!/usr/bin/env python3
"""
ADSB JSON Stream Server (AWS side)
----------------------------------
- Listens on localhost:4001 for JSON updates from the Pi (via SSH direct-tcpip).
- Stores the latest JSON blob in memory.
- Exposes the latest JSON via plain TCP on port 31009 for your ADS-B radar.

Protocol Pi -> AWS (port 4001):
- 4-byte big-endian unsigned length N
- N bytes of UTF-8 JSON

Protocol radar -> AWS (port 31009):
- Client connects (TCP)
- Server sends latest JSON bytes + newline
- Server closes connection
"""

import argparse
import json
import socket
import struct
import threading
import time
from typing import Optional

latest_json = b"{}"
latest_ts: float = 0.0
latest_lock = threading.Lock()


def recv_all(sock: socket.socket, length: int) -> Optional[bytes]:
    """Receive exactly `length` bytes from the socket, or None on EOF/error."""
    data = bytearray()
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


def handle_ingest_client(conn: socket.socket, addr):
    """Handle a single update connection from the Pi on ingest port."""
    global latest_json, latest_ts
    try:
        header = recv_all(conn, 4)
        if not header:
            return
        (length,) = struct.unpack("!I", header)
        if length <= 0 or length > 50_000_000:
            # sanity check
            return
        payload = recv_all(conn, length)
        if payload is None:
            return

        # Optional: validate JSON
        try:
            json.loads(payload.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            # ignore invalid data
            return

        with latest_lock:
            latest_json = payload
            latest_ts = time.time()
        # You can print debug if you want:
        # print(f"[INGEST] Received {length} bytes at {time.ctime(latest_ts)}")
    finally:
        conn.close()


def ingest_server(host: str, port: int):
    """TCP server that accepts JSON updates from Pi (on localhost only)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(5)
    print(f"[INGEST] Listening on {host}:{port}")

    while True:
        conn, addr = srv.accept()
        t = threading.Thread(target=handle_ingest_client, args=(conn, addr), daemon=True)
        t.start()


def handle_radar_client(conn: socket.socket, addr):
    """Serve latest JSON to radar clients on port 31009."""
    try:
        with latest_lock:
            data = latest_json
            ts = latest_ts

        if ts == 0.0:
            # No data yet
            payload = b"{}\n"
        else:
            payload = data + b"\n"

        conn.sendall(payload)
    finally:
        conn.close()


def radar_server(host: str, port: int):
    """TCP server for ADS-B radar to fetch latest JSON."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(5)
    print(f"[RADAR] Listening on {host}:{port}")

    while True:
        conn, addr = srv.accept()
        # You can debug-log if needed:
        # print(f"[RADAR] Connection from {addr}")
        t = threading.Thread(target=handle_radar_client, args=(conn, addr), daemon=True)
        t.start()


def main():
    parser = argparse.ArgumentParser(description="ADS-B JSON stream server (ingest + radar).")
    parser.add_argument("--ingest-host", default="127.0.0.1", help="Host for ingest server (default: 127.0.0.1)")
    parser.add_argument("--ingest-port", type=int, default=4001, help="Port for ingest server (default: 4001)")
    parser.add_argument("--radar-host", default="0.0.0.0", help="Host for radar server (default: 0.0.0.0)")
    parser.add_argument("--radar-port", type=int, default=31009, help="Port for radar server (default: 31009)")
    args = parser.parse_args()

    t_ingest = threading.Thread(target=ingest_server, args=(args.ingest_host, args.ingest_port), daemon=True)
    t_radar = threading.Thread(target=radar_server, args=(args.radar_host, args.radar_port), daemon=True)

    t_ingest.start()
    t_radar.start()

    print("[MAIN] ADS-B JSON stream server running (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[MAIN] Stopping server.")


if __name__ == "__main__":
    main()
