import os

# TCP source for JSON aircraft data (MODE-S Wind local feed)
TCP_HOST = os.environ.get("ADSB_TCP_HOST", "127.0.0.1")
TCP_PORT = int(os.environ.get("ADSB_TCP_PORT", "31009"))

CENTER_LAT = float(os.environ.get("CENTER_LAT", "60.3172"))
CENTER_LON = float(os.environ.get("CENTER_LON", "24.9633"))
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "1"))   # the browser asks every second too

# Web server. 127.0.0.1 = reachable only through nginx on the same machine.
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "5300"))

MAX_RANGE_NM = float(os.environ.get("MAX_RANGE_NM", "0"))  # 0 = unlimited
NAV_DATA_DIR = os.environ.get("NAV_DATA_DIR", "")

# Registration / type databases (read-only). Default: the files mode_s_wind keeps up to date
# in ~/mode_s_wind/data (on AWS /home/ubuntu/mode_s_wind/data). Override with REG_DB_PATH /
# REF_DB_PATH; set REF_DB_PATH to an empty value to use BaseStation.sqb only.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_MSW_DATA = os.path.join(os.path.expanduser("~"), "mode_s_wind", "data")
_USE_MSW = os.path.isdir(_MSW_DATA)
REG_DB_PATH = os.environ.get("REG_DB_PATH") or (
    os.path.join(_MSW_DATA, "BaseStation.sqb") if _USE_MSW else os.path.join(_BASE_DIR, "data", "BaseStation.sqb"))
REF_DB_PATH = os.environ.get("REF_DB_PATH", os.path.join(_MSW_DATA, "aircraft_ref.db") if _USE_MSW else "")
# MODE-S Wind's main database: EFHK landings and departures for the EFHK traffic window (read-only)
MSW_DB_PATH = os.environ.get("MSW_DB_PATH", os.path.join(_MSW_DATA, "modes_meteo.db") if _USE_MSW else "")

# After this many seconds without a good feed read, targets are cleared and "feed lost" is shown
FEED_STALE_SECONDS = float(os.environ.get("FEED_STALE_SECONDS", "30"))

# Auto QNH: METAR station and source (same NOAA source as MODE-S Wind); {icao} is replaced
METAR_STATION = os.environ.get("METAR_STATION", "EFHK").strip().upper()
METAR_URL = os.environ.get("METAR_URL", "https://tgftp.nws.noaa.gov/data/observations/metar/stations/{icao}.TXT")

# Beast feed for the TopSky extended label (Comm-B: IAS, Mach, heading, roll, wind, temperature,
# NACp). MODE-S Wind serves it on 127.0.0.1:31005 when "Beast feed" is on in its Maintenance page.
# BEAST_PORT=0 turns the reader off.
BEAST_HOST = os.environ.get("BEAST_HOST", "127.0.0.1")
BEAST_PORT = int(os.environ.get("BEAST_PORT", "31005"))
# Flight tracks for the history line: adsb_radar's own database (created if missing, not in git)
TRACKS_DB_PATH = os.environ.get("TRACKS_DB_PATH", os.path.join(_BASE_DIR, "data", "tracks.db"))
TRACKS_HOURS = float(os.environ.get("TRACKS_HOURS", "24"))
# Replay recorder (replay.py): every second, every aircraft within REPLAY_RANGE_NM of the centre
REPLAY_DIR = os.environ.get("REPLAY_DIR", os.path.join(_BASE_DIR, "data", "replay"))
REPLAY_DAYS = int(os.environ.get("REPLAY_DAYS", "30"))
REPLAY_RANGE_NM = float(os.environ.get("REPLAY_RANGE_NM", "150"))
REPLAY_MIN_FREE_GB = float(os.environ.get("REPLAY_MIN_FREE_GB", "5"))   # pause recording below this
# AIP Finland (navdata.py): navaids, IFR points, routes and airspaces; checked once a day, installed
# into data/navdata when a new AIRAC amendment takes effect
NAVDATA_AUTO = os.environ.get("NAVDATA_AUTO", "1") not in ("0", "false", "no")
NAVDATA_CHECK_HOURS = float(os.environ.get("NAVDATA_CHECK_HOURS", "24"))
NAVDATA_RETRY_MIN = float(os.environ.get("NAVDATA_RETRY_MIN", "60"))      # after a failed check: try again sooner

# Used for the wind when the pygeomag model is not installed (deg east, EFHK area)
MAG_DECLINATION = float(os.environ.get("MAG_DECLINATION", "10.5"))

# /api/debug/* pages are disabled unless DEBUG_API=1
DEBUG_API = os.environ.get("DEBUG_API", "0") == "1"
