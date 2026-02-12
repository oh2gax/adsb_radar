import os

# TCP source for JSON aircraft data
TCP_HOST = os.environ.get("ADSB_TCP_HOST", "127.0.0.1")
TCP_PORT = int(os.environ.get("ADSB_TCP_PORT", "31009"))

# Legacy URL (not used by TCP mode, kept for backwards compatibility)
DATA_URL = os.environ.get("ADSB_DATA_URL", "http://blog.oh2gax.org:31007/")

CENTER_LAT = float(os.environ.get("CENTER_LAT", "60.3172"))
CENTER_LON = float(os.environ.get("CENTER_LON", "24.9633"))
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "3"))
PORT = int(os.environ.get("PORT", "5300"))  # Beta default port for TCP JSON version
MAX_RANGE_NM = float(os.environ.get("MAX_RANGE_NM", "0"))  # 0 = unlimited
NAV_DATA_DIR = os.environ.get("NAV_DATA_DIR", "")
