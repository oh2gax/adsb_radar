# ADS-B JSON Secure Stream (Client / Server)

## Overview

This project provides a secure, real-time streaming solution for transferring ADS-B JSON data
between two Linux systems without using intermediate files.

It consists of:

- Client (Raspberry Pi / Edge Device)
  - Fetches aircraftlist.json from a local ADS-B receiver
  - Sends JSON securely over SSH to a remote server
- Server (AWS / Remote Host)
  - Receives JSON updates via SSH tunnel
  - Stores the latest JSON snapshot in memory
  - Exposes the latest data via plain TCP (port 31009)

This approach avoids file read/write race conditions and ensures secure transmission
using SSH encryption.

---

## Features

- Secure transfer using SSH (Paramiko)
- Persistent SSH connection with automatic reconnect
- In-memory storage (no disk race conditions)
- Simple TCP interface for radar systems
- Exponential backoff on errors
- Systemd compatible
- Works on Ubuntu / Debian-based distributions

---

## Requirements

Client:
- Python 3.8+
- paramiko

Server:
- Python 3.8+

---

## Installation (Ubuntu / Debian)

Install Python:

    sudo apt update
    sudo apt install -y python3 python3-pip

Install Paramiko (client only):

    pip3 install paramiko

---

## Running the Server (AWS)

    python3 adsb_json_stream_server.py       --ingest-host 127.0.0.1       --ingest-port 4001       --radar-host 0.0.0.0       --radar-port 31009

Test:

    nc localhost 31009

---

## Running the Client (Raspberry Pi)

    python3 adsb_json_stream_client.py       --source-url http://192.168.0.119/aircraftlist.json       --host blog.oh2gax.org       --username bitnami       --key-file /home/pi/.ssh/id_rsa       --ingest-host 127.0.0.1       --ingest-port 4001       --interval 5

---

## Security Notes

- SSH provides encrypted transport
- Ingest port (4001) listens only on localhost
- Radar port (31009) can be firewalled if needed

---

Generated on: 2026-02-12 12:33:22 UTC
