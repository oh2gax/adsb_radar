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

- Polls a TCP JSON feed (connect, read one JSON list, close) every second
- Targets with callsign, squawk (7500/7600/7700 in red), altitude/FL with trend and
  selected altitude, ground speed, registration and type, speed vector and trail
- Registration / type from BaseStation.sqb, completed from aircraft_ref.db (tar1090-db)
  when the feed has none — the files MODE-S Wind keeps up to date every morning
- **What's new** link under the logo: the notes of the ten newest versions in a window over
  the scope (`doc/whats_new.md`)
- **Own position**: a small triangle at a position entered in decimal degrees
- **METAR & TAF** window for any airport (EFHK by default): movable, resizable, remembered
- **EFHK traffic** window: landings and departures (ARR / DEP / BOTH, 1 h – 1 d) with runway and
  go-arounds, read from MODE-S Wind's database and completed with the radar's own detection;
  click a row to draw that flight's track
- **Go-around alarm**: a red GA after the callsign (flashing 60 s, then steady until the landing),
  from the radar's own EFHK go-around / landing / departure detection (`movements.py`)
- **History line** of the selected aircraft: its whole current flight from the radar's own
  track recorder (`tracks.db`, 24 h), high resolution in turns and go-arounds
- Move the map by dragging it, zoom with the mouse wheel (2–400 NM); ⌂ returns to the default centre
- Aircraft updated every second (ADS-B positions decoded from the Beast feed every second); map lines loaded once and drawn from a cached background layer
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
2. Add a short user-oriented note to `doc/whats_new.md` under `## v.DDMMYYYY — title`
   (one section per day; newest first) — it appears in the What's new window
3. Commit and push to `main`
4. On the server: `cd ~/adsb_radar && bash update.sh`, answer `y`; the logo shows the new version

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `ADSB_TCP_HOST` / `ADSB_TCP_PORT` | 127.0.0.1 / 31009 | JSON feed |
| `HOST` / `PORT` | 127.0.0.1 / 5300 | web server address |
| `POLL_SECONDS` | 1 | feed poll interval (the browser asks every second too) |
| `CENTER_LAT` / `CENTER_LON` | 60.3172 / 24.9633 | default radar center (EFHK) |
| `REG_DB_PATH` | `~/mode_s_wind/data/BaseStation.sqb` | registration database (read-only) |
| `REF_DB_PATH` | `~/mode_s_wind/data/aircraft_ref.db` | tar1090-db reference data; empty = off |
| `MSW_DB_PATH` | `~/mode_s_wind/data/modes_meteo.db` | MODE-S Wind's database for the EFHK traffic window (read-only) |
| `METAR_STATION` | EFHK | Auto QNH station |
| `METAR_URL` | NOAA tgftp `{icao}.TXT` | METAR source (same as MODE-S Wind) |
| `TAF_URL` | NOAA tgftp `forecasts/taf/stations/{icao}.TXT` | TAF source (same as MODE-S Wind) |
| `BEAST_HOST` / `BEAST_PORT` | 127.0.0.1 / 31005 | MODE-S Wind's Beast feed for the extended label; `0` = off |
| `TRACKS_DB_PATH` | `adsb_radar_ui/data/tracks.db` | the radar's own track recorder (created automatically, not in git) |
| `TRACKS_HOURS` | 24 | how long tracks are kept |
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
the same method as MODE-S Wind. Without the Beast feed the radar works as before and the
extended label shows `---` for the Comm-B values.

It also decodes the ADS-B airborne / surface positions (types 5–18, 20–22) and velocities
(type 19) of those aircraft, locally against a known reference position, and checks each
one against the JSON feed (within 20 NM) and the previous position (under 900 kt). A fresh
ADS-B position (under 3 s old) replaces the JSON feed's position in `/api/aircraft`
(`pos_src: "adsb"`), so ADS-B aircraft move every second although the JSON feed is
refreshed every 2 s.

## Track recorder (history line)

`tracks.py` stores the positions of every aircraft in `tracks.db` (SQLite, WAL) for
`TRACKS_HOURS`: the ADS-B positions above, and the JSON feed's positions of aircraft
without ADS-B (MLAT). To keep the file small without losing shape, a point is kept when the
direction changes by 1.5° or more, the altitude by 50 ft or more, or else every 5 s (once a
minute when standing still) — about 85 bytes a point, 6–8 MB per 100 aircraft-hours, so a
busy day around EFHK is some tens of MB. A flight ends after
20 minutes without positions. The file is written every 3 s and cleaned every hour.

## EFHK movements (go-around alarm)

`movements.py` follows every aircraft within 30 NM of EFHK below 5000 ft on each update
(once a second), with altitudes corrected to MSL by the QNH of the latest EFHK METAR. It
uses MODE-S Wind's go-around rules (collector/windshear.py), timed in seconds:

- **approach** — in a runway's ILS corridor (±2.5 NM, 0–25 NM out, track within 60°, not
  more than 1000 ft below the 3° path) and descending for 10 s;
- **go-around** — on an approach, climbing ≥ 600 fpm below 2200 ft for 4 s and 50 ft; or,
  after crossing the threshold, 200 ft above the height there (low go-around, touch-and-go);
- **landing** — the threshold crossed and no climb for 60 s (or under 80 kt), or lost on
  short final (within 4 NM, below 1500 ft);
- **departure** — within 6 NM below 1500 ft, climbing ≥ 300 fpm at ≥ 90 kt, not on an
  approach or after a go-around; runway from the direction and the extended centreline.

A go-around puts `ga: {age, n, rwy}` on the aircraft in `/api/aircraft` (the GA mark) until
the landing, at most 30 min. The events are stored in `tracks.db` (table `movements`, 24 h);
the EFHK traffic window adds the landings and departures that MODE-S Wind has no row for
(same aircraft and kind within 10 minutes, `own: true`). Without MODE-S Wind's database
the window shows the radar's own rows only.

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
| `/api/overlays_meta`, `/api/overlay/<name>?dec=2` | line overlays (GeoJSON in `data/overlays`), one whole layer, gzip, cacheable |
| `/api/qnh` | latest METAR and QNH (Auto QNH, `METAR_STATION`) |
| `/api/efhk_traffic?kind=both&hours=3` | EFHK landings / departures from MODE-S Wind (kind arr/dep/both, hours 1/3/6/12/24) |
| `/api/wx?icao=EFHK` | METAR and TAF of one airport (cached 10 min, shared by all viewers) |
| `/api/whatsnew` | the ten newest versions of `doc/whats_new.md` |
| `/api/ac/<hex>` | Comm-B / EHS values of one aircraft (TopSky extended label) |
| `/api/track/<hex>?t=&since=` | history line: the points `[t, lat, lon, alt, src]` of the flight around time `t` (default the latest), only newer than `since` |
| `/api/ehs_status` | Beast feed reader: connected, messages, ADS-B positions, aircraft with Comm-B; `tracks`: recorder status; `movements`: QNH, GA marks, recent events |

## Folders

- `adsb_radar_ui/` – the application (Flask app, static files, data)
- `deploy/` – reference systemd unit
- `doc/` – `whats_new.md`, the notes of the What's new window
- `tmp_files/` – local scratch folder, not in git
