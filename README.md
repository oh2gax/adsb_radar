# ADS-B Radar

A lightweight web radar display for ADS-B / MLAT traffic, written in Python (Flask) and
plain JavaScript (canvas). © Otso Laakso / OH2GAX.

Live: https://radar.oh2gax.org

```
MODE-S Wind TCP feed (127.0.0.1:31009) → Flask backend (app_beta.py) → /api/* → browser radar (radar.js)
```

## Version numbering

The version is the date of the latest git commit (Helsinki time) as `v.DDMMYYYY`, e.g.
`v.03112026`. All changes committed on the same day share one version; a commit on a new
day is a new version. It is worked out automatically when the app starts and shown in the
top-left logo; nothing has to be edited by hand.

## Features

- Polls a TCP JSON feed (connect, read one JSON list, close) every 3 s
- Targets with callsign, squawk (7500/7600/7700 in red), altitude/FL with trend and
  selected altitude, ground speed, registration and type, speed vector and trail
- Registration / type from BaseStation.sqb, completed from aircraft_ref.db (tar1090-db)
  when the feed has none — the files MODE-S Wind keeps up to date every morning
- Auto QNH from the latest METAR (default EFHK) for altitudes below 5000 ft
- Label style **Classic** (the original labels) or **TopSky (ATC)**: three-line labels
  (callsign / level, trend and selected level / speed in tens of kt and type) with leader
  lines and automatic anti-overlap, as in MODE-S Wind's ATC display; the aircraft under the
  mouse or a clicked one shows the six-line extended label with IAS, TAS, Mach, magnetic
  heading, drift, roll, wind, temperature and NACp from MODE-S Wind's Beast feed
- Airports, navaids, waypoints and line overlays (coast, FIR, ATS routes, ILS, …)
- Four themes, label overlap avoidance, ICAO24 hex range filter, traffic list with links
- "FEED LOST" warning when the feed stops; targets are cleared after 30 s
- All viewer settings are kept in the browser (localStorage); "Reset UI" clears them

## Running on the AWS server

The app runs as the systemd service `adsb-radar` on 127.0.0.1:5300 behind nginx
(`radar.oh2gax.org`), from `/home/ubuntu/adsb_radar`. See `deploy/adsb-radar.service`.

### Updating from GitHub — `update.sh`

Nothing updates automatically. After pushing to GitHub, log in to the server and run:

```bash
cd ~/adsb_radar
bash update.sh            # shows the new commits and asks: Update? [y/N]
bash update.sh --check    # only show what is new, change nothing
bash update.sh --status   # running version and service state
bash update.sh --yes      # update without asking
bash update.sh --force    # reinstall packages + restart even if nothing is new
```

An update: `git fetch` → reset to `origin/main` → `pip install` if requirements.txt changed
→ Python syntax check → restart service → health check. If the new version does not start,
it rolls back to the previous commit by itself. Hand edits made on the server are saved to
`.update_state/*.patch` before being replaced — make changes in the repository instead.

### Development workflow

1. Edit and test locally (`bash adsb_radar_ui/run_beta.sh`, or `python app_beta.py`)
2. Commit and push to `main`
3. On the server: `cd ~/adsb_radar && bash update.sh`, answer `y`; the logo shows the new version

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `ADSB_TCP_HOST` / `ADSB_TCP_PORT` | 127.0.0.1 / 31009 | JSON feed |
| `HOST` / `PORT` | 127.0.0.1 / 5300 | web server address |
| `POLL_SECONDS` | 3 | feed poll interval |
| `CENTER_LAT` / `CENTER_LON` | 60.3172 / 24.9633 | default radar center (EFHK) |
| `REG_DB_PATH` | `~/mode_s_wind/data/BaseStation.sqb` | registration database (read-only) |
| `REF_DB_PATH` | `~/mode_s_wind/data/aircraft_ref.db` | tar1090-db reference data; empty = off |
| `METAR_STATION` | EFHK | Auto QNH station |
| `METAR_URL` | NOAA tgftp `{icao}.TXT` | METAR source (same as MODE-S Wind) |
| `BEAST_HOST` / `BEAST_PORT` | 127.0.0.1 / 31005 | MODE-S Wind's Beast feed for the extended label; `0` = off |
| `MAG_DECLINATION` | 10.5 | used for the wind only if `pygeomag` (WMM2025) is missing |
| `FEED_STALE_SECONDS` | 30 | feed silence before targets are cleared |
| `MAX_RANGE_NM` | 0 | drop targets beyond this range (0 = off) |
| `DEBUG_API` | 0 | `1` enables `/api/debug/reg?hex=…` and `/api/debug/schema` |

Databases are opened read-only and never created; a changed or replaced file is noticed
within 30 s. If `~/mode_s_wind/data` does not exist, `adsb_radar_ui/data/BaseStation.sqb` is used.

## TopSky extended label and the Beast feed

`ehs.py` reads MODE-S Wind's local Beast feed (switch on *Beast feed* on MODE-S Wind's
Maintenance page; it listens on 127.0.0.1:31005 unless its config says otherwise) and
decodes, with pyModeS like MODE-S Wind, only the replies of the aircraft on the radar:
Comm-B BDS 5,0 / 6,0 / 4,0 and ADS-B types 29 / 31. The wind comes from a BDS 5,0 + 6,0
pair (wings level), the temperature from TAS and Mach, both averaged over a minute —
the same method as MODE-S Wind. Nothing is stored. Without the Beast feed the radar works
as before and the extended label shows `---` for the Comm-B values.

## Feed format

A TCP server that sends one JSON array of aircraft per connection and closes it:

```json
[{"hex": "461E1A", "fli": "FIN7LH", "lat": 60.317, "lon": 24.963, "alt": 36000,
  "spd": 450, "trk": 180, "vrt": 0, "squ": "2034", "alts": 36000, "typ": "A321", "reg": "OH-LZA"}]
```

`alts` is the selected (MCP) altitude in feet. `reg` and `typ` are optional.

## API

| Endpoint | Returns |
|---|---|
| `/api/aircraft` | targets, `feed_age`, `error`, `feed_lost`, `version` |
| `/api/navaids?clat=&clon=&nmr=` | airports / navaids / waypoints within `nmr` NM |
| `/api/overlays_meta`, `/api/overlays_fetch` | line overlays (GeoJSON in `data/overlays`) |
| `/api/qnh` | latest METAR and QNH |
| `/api/ac/<hex>` | Comm-B / EHS values of one aircraft (TopSky extended label) |
| `/api/ehs_status` | Beast feed reader: connected, messages, aircraft with Comm-B |

## Folders

- `adsb_radar_ui/` – the application (Flask app, static files, data)
- `deploy/` – reference systemd unit
- `tmp_files/` – local scratch folder, not in git
