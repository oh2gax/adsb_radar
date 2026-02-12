#!/usr/bin/env python3
"""
ADSB JSON Stream Client (Pi side)
---------------------------------
- Periodically fetches aircraftlist.json from local receiver
- Sends it securely to AWS using SSH (Paramiko) via a direct-tcpip channel
- AWS server then exposes latest JSON via TCP port 31009

Requires:
    pip3 install paramiko
"""

import argparse
import json
import logging
import os
import signal
import struct
import sys
import time
import traceback
import urllib.request
from dataclasses import dataclass
from typing import Optional

try:
    import paramiko
except ImportError:
    print("This script requires the 'paramiko' package. Install via: pip install paramiko", file=sys.stderr)
    sys.exit(1)

# Keep Paramiko logs quiet
logging.getLogger("paramiko").setLevel(logging.WARNING)

STOP = False


def _handle_stop(signum, frame):
    global STOP
    STOP = True


signal.signal(signal.SIGINT, _handle_stop)
signal.signal(signal.SIGTERM, _handle_stop)


@dataclass
class Config:
    source_url: str
    host: str
    username: str
    key_file: str
    ingest_host: str
    ingest_port: int
    interval: float
    connect_timeout: float
    read_timeout: float
    strict_host_key_checking: bool
    known_hosts_file: Optional[str]


def parse_args() -> Config:
    p = argparse.ArgumentParser(description="ADS-B JSON stream client (Pi -> AWS via SSH)")
    p.add_argument("--source-url", default="http://192.168.0.119/aircraftlist.json",
                   help="Local receiver JSON URL (default: http://192.168.0.119/aircraftlist.json)")
    p.add_argument("--host", default="blog.oh2gax.org", help="SSH host (default: blog.oh2gax.org)")
    p.add_argument("--username", default="bitnami", help="SSH username (default: bitnami)")
    p.add_argument("--key-file", required=True, help="Path to SSH private key (PEM)")
    p.add_argument("--ingest-host", default="127.0.0.1",
                   help="Remote ingest host (on AWS, default: 127.0.0.1)")
    p.add_argument("--ingest-port", type=int, default=4001,
                   help="Remote ingest port (on AWS, default: 4001)")
    p.add_argument("--interval", type=float, default=5.0,
                   help="Seconds between updates (default: 5)")
    p.add_argument("--connect-timeout", type=float, default=10.0,
                   help="SSH connect timeout (default: 10)")
    p.add_argument("--read-timeout", type=float, default=10.0,
                   help="HTTP read timeout for source URL (default: 10)")
    p.add_argument("--strict-host-key-checking", action="store_true",
                   help="Use strict host key checking with known_hosts")
    p.add_argument("--known-hosts-file", default=None,
                   help="Path to known_hosts (used if --strict-host-key-checking)")
    a = p.parse_args()
    return Config(
        source_url=a.source_url,
        host=a.host,
        username=a.username,
        key_file=a.key_file,
        ingest_host=a.ingest_host,
        ingest_port=a.ingest_port,
        interval=max(0.1, a.interval),
        connect_timeout=a.connect_timeout,
        read_timeout=a.read_timeout,
        strict_host_key_checking=a.strict_host_key_checking,
        known_hosts_file=a.known_hosts_file,
    )


def fetch_json(url: str, timeout: float) -> bytes:
    """Fetch JSON from URL and return compact UTF-8 bytes."""
    req = urllib.request.Request(url, headers={"User-Agent": "ADSB-JSON-Client/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    try:
        parsed = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Downloaded content is not valid JSON: {e}") from e
    compact = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    return compact.encode("utf-8")


# Persistent SSH transport
_SSH_CLIENT: Optional["paramiko.SSHClient"] = None
_TRANSPORT: Optional["paramiko.Transport"] = None


def close_ssh():
    global _SSH_CLIENT, _TRANSPORT
    if _TRANSPORT is not None:
        try:
            _TRANSPORT.close()
        except Exception:
            pass
    if _SSH_CLIENT is not None:
        try:
            _SSH_CLIENT.close()
        except Exception:
            pass
    _SSH_CLIENT = None
    _TRANSPORT = None


def get_ssh_transport(cfg: Config) -> "paramiko.Transport":
    """Get or create a persistent SSH transport."""
    global _SSH_CLIENT, _TRANSPORT

    if _TRANSPORT is not None and _TRANSPORT.is_active():
        return _TRANSPORT

    close_ssh()

    key_path = os.path.expanduser(cfg.key_file)
    if not os.path.exists(key_path):
        raise FileNotFoundError(f"SSH key not found: {key_path}")

    client = paramiko.SSHClient()
    if cfg.strict_host_key_checking:
        if cfg.known_hosts_file:
            client.load_host_keys(cfg.known_hosts_file)
        else:
            client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    client.connect(
        hostname=cfg.host,
        username=cfg.username,
        key_filename=key_path,
        timeout=cfg.connect_timeout,
        look_for_keys=False,
        allow_agent=True,
    )

    transport = client.get_transport()
    if transport is None:
        client.close()
        raise RuntimeError("Failed to get SSH transport")

    transport.set_keepalive(30)

    _SSH_CLIENT = client
    _TRANSPORT = transport
    return transport


def send_update_via_ssh(cfg: Config, data: bytes):
    """Send JSON update to AWS via SSH direct-tcpip channel."""
    transport = get_ssh_transport(cfg)

    # dest_addr = (remote_host, remote_port), src_addr is arbitrary
    chan = transport.open_channel(
        kind="direct-tcpip",
        dest_addr=(cfg.ingest_host, cfg.ingest_port),
        src_addr=("", 0),
    )
    try:
        # length prefix
        header = struct.pack("!I", len(data))
        chan.sendall(header + data)
    finally:
        chan.close()


def main():
    cfg = parse_args()
    print(f"[START] Source: {cfg.source_url}")
    print(f"[START] SSH: {cfg.username}@{cfg.host} -> {cfg.ingest_host}:{cfg.ingest_port}")
    print(f"[INFO] Interval: {cfg.interval}s (Ctrl+C to stop)")

    backoff = 1.0
    try:
        while not STOP:
            start = time.time()
            try:
                # 1) Fetch data from local receiver
                payload = fetch_json(cfg.source_url, timeout=cfg.read_timeout)

                # 2) Send to AWS via SSH channel
                send_update_via_ssh(cfg, payload)

                print(f"[OK] Sent {len(payload)} bytes")
                backoff = 1.0  # reset on success

            except Exception as e:
                print(f"[ERR] {e.__class__.__name__}: {e}", file=sys.stderr)
                traceback.print_exc(limit=1)
                close_ssh()
                time.sleep(min(60.0, backoff))
                backoff = min(60.0, backoff * 2)

            elapsed = time.time() - start
            if STOP:
                break
            sleep_for = max(0.0, cfg.interval - elapsed)
            time.sleep(sleep_for)
    finally:
        close_ssh()
        print("[STOP] Client exited.")


if __name__ == "__main__":
    main()
