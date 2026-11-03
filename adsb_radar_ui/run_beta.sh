#!/usr/bin/env bash
# Run adsb_radar by hand (for testing). On the server it runs as the adsb-radar systemd service.
set -e
cd "$(dirname "$0")"
[ -d venv ] || python3 -m venv venv
venv/bin/pip install -q -r requirements.txt
exec venv/bin/python app_beta.py
