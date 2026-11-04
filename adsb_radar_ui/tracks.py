"""
tracks.py - flight tracks for the history line (own database data/tracks.db).

Positions come from two places:
  - ADS-B positions decoded from MODE-S Wind's Beast feed (ehs.py), about two per second;
  - the JSON feed every second, for aircraft without a fresh ADS-B position (MLAT, fallback).

Not every position is stored: while an aircraft turns, climbs or descends every position
is kept (go-arounds and approaches at full resolution); in straight, level flight one point
every KEEP_STRAIGHT_SEC is enough, because the line would look the same.

Points are written to SQLite in batches every few seconds (a separate thread), kept
RETENTION_HOURS and purged every hour. A flight is the aircraft's points with no gap
longer than FLIGHT_GAP_SEC, so a go-around and the next approach are the same flight.
The database survives restarts and updates; it is created if missing (unlike the
read-only MODE-S Wind databases) and is not part of the git repository.
"""

import math
import os
import sqlite3
import threading
import time

KEEP_STRAIGHT_SEC = 5.0      # in straight, level flight at least one point this often
MIN_STEP_SEC = 0.4           # never two points closer in time than this
TURN_DEG = 1.5               # direction change that keeps a point
CLIMB_FT = 50                # altitude change that keeps a point
MIN_MOVE_M = 25.0            # a direction change counts only after this much movement
FLIGHT_GAP_SEC = 20 * 60
RETENTION_HOURS = 24
FLUSH_SEC = 3.0
MAX_POINTS_RETURNED = 50000

SRC_ADSB, SRC_FEED = 0, 1


def _dist_m(la1, lo1, la2, lo2):
    dy = (la2 - la1) * 111195.0
    dx = (lo2 - lo1) * 111195.0 * math.cos(math.radians((la1 + la2) / 2))
    return math.hypot(dx, dy)


def _bearing(la1, lo1, la2, lo2):
    dy = la2 - la1
    dx = (lo2 - lo1) * math.cos(math.radians((la1 + la2) / 2))
    return math.degrees(math.atan2(dx, dy)) % 360.0


def _angle_diff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


class TrackStore:
    def __init__(self, path, retention_hours=RETENTION_HOURS):
        self.path = path
        self.retention = retention_hours * 3600
        self.lock = threading.Lock()      # state + pending (fast, taken for every position)
        self.dblock = threading.Lock()    # the SQLite connection (writer thread and queries)
        self.state = {}          # HEX -> last kept point and direction
        self.pending = []        # points waiting to be written
        self.conn = None
        self.error = None
        self.n_in = 0
        self.n_kept = 0
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            c = sqlite3.connect(path, check_same_thread=False, timeout=10)
            c.execute("PRAGMA journal_mode = WAL")
            c.execute("PRAGMA synchronous = NORMAL")
            c.execute("CREATE TABLE IF NOT EXISTS points (icao TEXT NOT NULL, t REAL NOT NULL, lat REAL NOT NULL, "
                      "lon REAL NOT NULL, alt INTEGER, src INTEGER)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_points_icao_t ON points(icao, t)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_points_t ON points(t)")
            # EFHK movements found by movements.py (arr / dep / ga), for the EFHK traffic window
            c.execute("CREATE TABLE IF NOT EXISTS movements (t REAL NOT NULL, kind TEXT NOT NULL, icao TEXT NOT NULL, "
                      "callsign TEXT, rwy TEXT, ga INTEGER, low INTEGER)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_movements_t ON movements(t)")
            c.commit()
            self.conn = c
            print(f"[tracks] recording to {path} (kept {retention_hours} h)", flush=True)
        except Exception as e:
            self.error = str(e)
            print(f"[tracks] cannot open {path}: {e} - history lines from memory only", flush=True)

    def start(self):
        threading.Thread(target=self._writer, name="tracks", daemon=True).start()

    # ---- recording ----
    def add(self, icao, t, lat, lon, alt=None, src=SRC_ADSB):
        """One position. Keeps it if the aircraft turned, climbed / descended, or if
        KEEP_STRAIGHT_SEC passed since the last kept point."""
        if lat is None or lon is None or not icao:
            return
        self.n_in += 1
        with self.lock:
            s = self.state.get(icao)
            if s is not None:
                dt = t - s["t"]
                if dt < MIN_STEP_SEC:
                    return
                if dt < FLIGHT_GAP_SEC:
                    moved = _dist_m(s["lat"], s["lon"], lat, lon)
                    same_alt = alt is None or s["alt"] is None or abs(alt - s["alt"]) < CLIMB_FT
                    if moved < 10.0 and same_alt and dt < 60.0:
                        return                          # standing still: one point a minute is enough
                    keep = dt >= KEEP_STRAIGHT_SEC
                    if not keep and alt is not None and s["alt"] is not None and abs(alt - s["alt"]) >= CLIMB_FT:
                        keep = True
                    if not keep:
                        d = _dist_m(s["lat"], s["lon"], lat, lon)
                        if d >= MIN_MOVE_M and s["dir"] is not None and \
                                _angle_diff(_bearing(s["lat"], s["lon"], lat, lon), s["dir"]) >= TURN_DEG:
                            keep = True
                    if not keep:
                        return
                    d = _dist_m(s["lat"], s["lon"], lat, lon)
                    direction = _bearing(s["lat"], s["lon"], lat, lon) if d >= MIN_MOVE_M else s["dir"]
                else:
                    direction = None
            else:
                direction = None
            self.state[icao] = {"t": t, "lat": lat, "lon": lon, "alt": alt, "dir": direction}
            self.pending.append((icao, t, round(lat, 6), round(lon, 6), int(alt) if alt is not None else None, src))
            self.n_kept += 1

    # ---- EFHK movements (movements.py) ----
    def add_event(self, ev):
        """Store one movement at once (they are few: a few hundred a day)."""
        row = (ev["t"], ev["kind"], ev["icao"], ev.get("callsign"), ev.get("rwy"), ev.get("ga") or 0,
               1 if ev.get("low") else 0)
        with self.lock:
            self._events_mem = (getattr(self, "_events_mem", []) + [row])[-5000:]
        if self.conn is None:
            return
        with self.dblock:
            self.conn.execute("INSERT INTO movements VALUES (?,?,?,?,?,?,?)", row)
            self.conn.commit()

    def events(self, since, kinds=("arr", "dep", "ga")):
        """Movements since `since`, newest first: dicts t, kind, icao, callsign, rwy, ga, low."""
        if self.conn is not None:
            with self.dblock:
                rows = self.conn.execute("SELECT t, kind, icao, callsign, rwy, ga, low FROM movements "
                                         "WHERE t >= ? ORDER BY t DESC", (since,)).fetchall()
        else:
            with self.lock:
                rows = sorted((r for r in getattr(self, "_events_mem", []) if r[0] >= since), reverse=True)
        keys = ("t", "kind", "icao", "callsign", "rwy", "ga", "low")
        return [dict(zip(keys, r)) for r in rows if r[1] in kinds]

    def last_time(self, icao):
        s = self.state.get(icao)
        return s["t"] if s else None

    # ---- writing / purging ----
    def _writer(self):
        next_purge = time.time() + 60
        while True:
            time.sleep(FLUSH_SEC)
            with self.lock:
                batch, self.pending = self.pending, []
                # forget the state of aircraft not heard for a long time
                cut = time.time() - FLIGHT_GAP_SEC
                for k in [k for k, v in self.state.items() if v["t"] < cut]:
                    del self.state[k]
            if self.conn is None:
                with self.lock:                       # no database: keep the last hour in memory
                    self._mem = (getattr(self, "_mem", []) + batch)[-500000:]
                continue
            try:
                with self.dblock:
                    if batch:
                        self.conn.executemany("INSERT INTO points VALUES (?,?,?,?,?,?)", batch)
                        self.conn.commit()
                    if time.time() >= next_purge:
                        next_purge = time.time() + 3600
                        n = self.conn.execute("DELETE FROM points WHERE t < ?", (time.time() - self.retention,)).rowcount
                        self.conn.execute("DELETE FROM movements WHERE t < ?", (time.time() - self.retention,))
                        self.conn.commit()
                        if n:
                            print(f"[tracks] purged {n} points older than {self.retention // 3600} h", flush=True)
                self.error = None
            except Exception as e:
                if str(e) != self.error:
                    print(f"[tracks] write failed: {e}", flush=True)
                self.error = str(e)
                with self.lock:                       # try again with the next batch
                    self.pending = batch + self.pending

    # ---- reading ----
    def flight(self, icao, at=None, since=None):
        """Points [[t, lat, lon, alt, src], ...] of the flight of `icao` that contains time `at`
        (default: the latest flight). since: only points after that time (live updates)."""
        icao = (icao or "").upper()
        now = time.time()
        lo = now - self.retention
        rows = []
        if self.conn is not None:
            with self.dblock:   # the connection is shared with the writer thread
                rows = self.conn.execute("SELECT t, lat, lon, alt, src FROM points WHERE icao = ? AND t >= ? ORDER BY t",
                                         (icao, lo)).fetchall()
        with self.lock:
            extra = [(p[1], p[2], p[3], p[4], p[5]) for p in self.pending if p[0] == icao]
            extra += [(p[1], p[2], p[3], p[4], p[5]) for p in getattr(self, "_mem", []) if p[0] == icao]
        if extra:
            rows = sorted(set(rows) | set(extra))
        if not rows:
            return {"icao": icao, "points": [], "start": None, "end": None, "live": False}
        # split into flights at gaps longer than FLIGHT_GAP_SEC; pick the one containing `at`
        flights, cur = [], [rows[0]]
        for r in rows[1:]:
            if r[0] - cur[-1][0] > FLIGHT_GAP_SEC:
                flights.append(cur)
                cur = []
            cur.append(r)
        flights.append(cur)
        pick = flights[-1]
        if at is not None:
            # the flight within 10 min of `at`; none: that flight was not recorded (do not show another one)
            near = [f for f in flights if f[0][0] - 600 <= at <= f[-1][0] + 600]
            if not near:
                return {"icao": icao, "points": [], "start": None, "end": None, "live": False}
            pick = min(near, key=lambda f: 0 if f[0][0] <= at <= f[-1][0] else min(abs(f[0][0] - at), abs(f[-1][0] - at)))
        pts = pick if since is None else [r for r in pick if r[0] > since]
        if len(pts) > MAX_POINTS_RETURNED:
            step = math.ceil(len(pts) / MAX_POINTS_RETURNED)
            pts = pts[::step] + [pts[-1]]
        return {"icao": icao, "start": pick[0][0], "end": pick[-1][0],
                "live": now - pick[-1][0] < 60,
                "points": [[round(r[0], 1), r[1], r[2], r[3], r[4]] for r in pts]}

    def status(self):
        n = None
        if self.conn is not None:
            try:
                with self.dblock:
                    n = self.conn.execute("SELECT COUNT(*) FROM points").fetchone()[0]
            except Exception:
                n = None
        size = None
        try:
            size = os.path.getsize(self.path) + (os.path.getsize(self.path + "-wal") if os.path.exists(self.path + "-wal") else 0)
        except OSError:
            pass
        return {"path": self.path, "points_stored": n, "bytes": size, "positions_in": self.n_in,
                "points_kept": self.n_kept, "aircraft": len(self.state), "error": self.error}
