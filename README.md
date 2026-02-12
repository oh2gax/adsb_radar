# ADS-B Radar v9.0.0_Beta

A lightweight web-based ADS-B radar display written in Python (Flask)
and JavaScript.

This project provides a real-time radar-style visualization of aircraft
positions using ADS-B / MLAT data.\
It supports TCP-based JSON feeds and displays aircraft movement,
altitude, speed, squawk, registration, and more --- directly in a
browser.

------------------------------------------------------------------------

## ✈ Overview

ADS-B Radar is designed to:

-   Connect to a TCP JSON data source (e.g., local ADS-B receiver
    backend)
-   Parse aircraft position and metadata
-   Display aircraft on a radar-style screen
-   Show trails, headings, selected altitude, squawk, and aircraft
    information
-   Optionally enrich registration/type using BaseStation.sqb database
-   Run as a lightweight Flask web server on Linux

The radar interface works in modern browsers and requires no additional
frontend dependencies.

------------------------------------------------------------------------

## 🔧 Features

-   TCP-based JSON polling (configurable host & port)
-   Robust error handling (no blank screen on temporary feed failure)
-   Aircraft position tracking with heading vector
-   Altitude (ft), speed (kt), vertical rate (ft/min)
-   Selected altitude (formatted as FL-style values)
-   Squawk display
-   Registration and aircraft type display
-   Optional BaseStation.sqb metadata fallback
-   Adjustable radar zoom range
-   Trail display for aircraft movement
-   Works on Ubuntu / Debian-based systems

------------------------------------------------------------------------

## 🖥 System Requirements

-   Linux (Ubuntu/Debian recommended)
-   Python 3.9+
-   Flask
-   SQLite3 (for BaseStation.sqb lookup, optional)

------------------------------------------------------------------------

## 🚀 Installation (Ubuntu / Debian)

### 1. Clone Repository

``` bash
git clone https://github.com/YOUR_USERNAME/adsb_radar.git
cd adsb_radar
```

### 2. Install Python Dependencies

``` bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

(Optional but recommended)

``` bash
python3 -m venv venv
source venv/bin/activate
pip install flask
```

### 3. Configure TCP Data Source

Edit `config.py` if needed:

``` python
TCP_HOST = "127.0.0.1"
TCP_PORT = 31009
```

Or use environment variables:

``` bash
export ADSB_TCP_HOST=127.0.0.1
export ADSB_TCP_PORT=31009
```

### 4. Start the Radar Server

``` bash
bash run_beta.sh
```

The web interface will be available at:

    http://localhost:5320

------------------------------------------------------------------------

## 📡 TCP Data Format

The radar expects a TCP server that:

1.  Accepts connection
2.  Sends JSON data
3.  Closes connection (EOF)

The JSON must be a **top-level array of aircraft objects**, for example:

``` json
[
  {
    "hex": "AABBCC",
    "fli": "FIN123",
    "lat": 60.317,
    "lon": 24.963,
    "alt": 36000,
    "spd": 450,
    "trk": 180,
    "vrt": 0,
    "typ": "A320",
    "reg": "OH-LXA",
    "squ": "7000",
    "alts": 36000
  }
]
```

------------------------------------------------------------------------

## 🧭 Web Interface (Left Pane Settings)

The left control pane allows adjustment of:

### Zoom (NM)

Sets radar range in nautical miles.\
Aircraft beyond this range are still visible if within the screen area.

### Trails

Enable/disable aircraft movement trails.

### Range Filter

Filter aircraft based on ICAO24 hex codes.

### Stale Timeout

Removes aircraft not updated within configured time.

### Position Loss Timeout

Controls how long aircraft remain visible if position data is lost.

------------------------------------------------------------------------

## 🛰 Radar Screen Display

Each aircraft symbol displays:

-   Heading (rotated according to track)
-   Callsign (if available)
-   Altitude in feet
-   Speed in knots
-   Vertical rate indicator
-   Squawk code
-   Registration
-   Aircraft type
-   Selected altitude (formatted as FL-style, e.g. 040, 360)

### Visual Elements

-   Circular range rings
-   Heading vectors
-   Aircraft trails
-   Center reference marker
-   Smooth movement updates

Aircraft outside the selected zoom ring are still displayed within the
full screen area.

------------------------------------------------------------------------

## 🗂 BaseStation.sqb Enrichment (Optional)

If JSON does not provide `reg` or `typ`, the system can look up metadata
from:

    BaseStation.sqb

This is optional and only fills missing fields.

------------------------------------------------------------------------

## ⚙ Configuration Options (config.py)

``` python
TCP_HOST
TCP_PORT
CENTER_LAT
CENTER_LON
POLL_SECONDS
PORT
MAX_RANGE_NM
NAV_DATA_DIR
```

------------------------------------------------------------------------

## 📊 Architecture

    TCP JSON Feed  →  Flask Backend  →  Internal Cache  →  REST API  →  Browser Radar UI

Backend polls every 5 seconds (configurable).\
Frontend updates dynamically without full page reload.

------------------------------------------------------------------------

## 🛠 Troubleshooting

If aircraft disappear briefly:

-   Check TCP feed availability
-   Ensure JSON is valid
-   Verify firewall allows local TCP connections
-   Confirm POLL_SECONDS matches feed frequency

------------------------------------------------------------------------

## 📜 License

Add your license information here.

------------------------------------------------------------------------

## 🙌 Credits

Developed and customized for advanced ADS-B and MLAT radar visualization
use cases.
