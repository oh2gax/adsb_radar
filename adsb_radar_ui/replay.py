"""replay.py - the replay recorder: every second, every aircraft within REPLAY_RANGE_NM of the radar
centre (EFHK), with the Comm-B values of the TopSky extended label, the EFHK movements (go-arounds,
landings, departures) and the METARs, kept REPLAY_DAYS days, for the replay of the scope.

Storage: one SQLite file per UTC day (data/replay/YYYY-MM-DD.db). One row per aircraft per minute
("block"): its samples of that minute, delta-coded integers (lat / lon 1e-5 deg, altitude 25 ft, ground
speed 1 kt, track 0.1 deg, vertical rate 64 fpm), the label values and the Comm-B values when they change,
zlib-compressed JSON. The current minute stays in memory; at each full minute the minute that ended is
written in one transaction (a restart loses at most the current minute). Keeping the days = deleting the
files of the older days. Writing stops (status error) while the disk has less than REPLAY_MIN_FREE_GB free.

Block format (JSON, then zlib), all lists aligned with "t" (second of the minute, 0-59):
  {"v": 1, "t": [...], "la": [...], "lo": [...], "al": [...], "gs": [...], "tr": [...], "vr": [...],
   "src": [...],                                   # 0 ADS-B, 1 feed
   "id": [[t, callsign, squawk, sel_alt_ft, reg, type], ...],   # at the start and when one changes
   "cb": [[t, {...}], ...]}                        # Comm-B values (as /api/ac, without ages) when they change
  la / lo / al / gs / tr / vr: the first value, then differences to the previous non-null value; null = none.
"""
import json
import math
import os
import shutil
import sqlite3
import threading
import time
import zlib
from datetime import datetime, timezone, timedelta

FLUSH_CHECK_SEC = 2.0


def _day(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")


def _q(v, scale):
    """Quantize: value / scale rounded to an int, or None."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return int(round(f / scale))


def _delta(values):
    out, prev = [], None
    for v in values:
        if v is None:
            out.append(None)
        elif prev is None:
            out.append(v); prev = v
        else:
            out.append(v - prev); prev = v
    return out


def _undelta(values):
    out, prev = [], None
    for d in values:
        if d is None:
            out.append(None)
        elif prev is None:
            prev = d; out.append(d)
        else:
            prev += d; out.append(prev)
    return out


# fields: name in the block, key in the aircraft object, quantum
FIELDS = (("la", "lat", 1e-5), ("lo", "lon", 1e-5), ("al", "alt_baro", 25), ("gs", "gs", 1),
          ("tr", "track", 0.1), ("vr", "baro_rate", 64))


def encode_block(samples, ids, cbs):
    """samples: [(sec, lat, lon, alt, gs, trk, vr, src)]."""
    b = {"v": 1, "t": [s[0] for s in samples]}
    for i, (name, _k, q) in enumerate(FIELDS):
        b[name] = _delta([_q(s[1 + i], q) for s in samples])
    b["src"] = [s[7] for s in samples]
    if ids:
        b["id"] = ids
    if cbs:
        b["cb"] = cbs
    return zlib.compress(json.dumps(b, separators=(",", ":")).encode(), 6)


def decode_block(blob):
    b = json.loads(zlib.decompress(blob))
    cols = {}
    for name, _k, q in FIELDS:
        vals = _undelta(b.get(name, []))
        nd = 5 if name in ("la", "lo") else (1 if name == "tr" else 0)
        cols[name] = [None if v is None else (round(v * q, nd) if nd else int(round(v * q))) for v in vals]
    rows = [[t, cols["la"][i], cols["lo"][i], cols["al"][i], cols["gs"][i], cols["tr"][i], cols["vr"][i],
             b["src"][i] if i < len(b.get("src", [])) else None] for i, t in enumerate(b["t"])]
    return {"s": rows, "id": b.get("id", []), "cb": b.get("cb", [])}


class ReplayRecorder:
    def __init__(self, directory, days=30, range_nm=150.0, center=(60.3172, 24.9633), min_free_gb=5.0):
        self.dir = directory
        self.days = max(1, int(days))
        self.range_nm = float(range_nm)
        self.center = center
        self.min_free = float(min_free_gb) * 1e9
        self.lock = threading.Lock()
        self.minute = None          # the minute being collected (epoch of its start)
        self.buf = {}               # icao -> {"s": [...], "id": [...], "cb": [...]}
        self.last_id = {}           # icao -> last label tuple stored (kept over minutes: changes only)
        self.last_cb = {}           # icao -> last Comm-B JSON stored
        self.pending = []           # (minute, {icao: buf}, events, metars) ready to write
        self.events, self.metars = [], []
        self.conns = {}             # day -> sqlite connection
        self.error = None
        self.disk_full = False
        self.n_samples = 0
        self.n_blocks = 0
        self.n_written = 0
        self.bytes_written = 0
        self.last_write = None
        self.last_metar = None
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as e:
            self.error = f"cannot create {directory}: {e}"
            print(f"[replay] {self.error}", flush=True)

    # ---- recording (called by the app every second) ----
    def add(self, objs, now=None, commb=None):
        """objs: the merged aircraft list of this second. commb(icao) -> dict or None (ehs.get)."""
        now = now or time.time()
        minute = int(now // 60) * 60
        sec = int(now - minute)
        clat, clon = self.center
        kx = math.cos(math.radians(clat))
        with self.lock:
            if self.minute is None:
                self.minute = minute
            if minute != self.minute:              # a new minute: hand the finished one to the writer
                self.pending.append((self.minute, self.buf, self.events, self.metars))
                self.buf, self.events, self.metars = {}, [], []
                self.minute = minute
            for o in objs:
                icao = str(o.get("hex") or "").upper()
                lat, lon = o.get("lat"), o.get("lon")
                if len(icao) != 6 or lat is None or lon is None:
                    continue
                try:
                    lat, lon = float(lat), float(lon)
                except (TypeError, ValueError):
                    continue
                b = self.buf.get(icao)
                if b is None:
                    if math.hypot((lat - clat) * 60, (lon - clon) * 60 * kx) > self.range_nm:
                        continue                   # outside: not recorded (once inside, the whole minute)
                    b = self.buf[icao] = {"s": [], "id": [], "cb": []}
                    self.last_id.pop(icao, None)   # a new block repeats the label and the Comm-B values
                    self.last_cb.pop(icao, None)
                if b["s"] and b["s"][-1][0] == sec:
                    continue                       # the same second twice
                b["s"].append((sec, lat, lon, o.get("alt_baro"), o.get("gs"), o.get("track"), o.get("baro_rate"),
                               0 if o.get("pos_src") == "adsb" else 1))
                ident = [(o.get("flight") or "").strip() or None, o.get("squawk"), o.get("sel_alt_ft"),
                         o.get("reg"), o.get("type") or o.get("typ")]
                if self.last_id.get(icao) != ident:
                    b["id"].append([sec] + ident)
                    self.last_id[icao] = ident
                if commb:
                    cb = commb(icao)
                    if cb:
                        key = json.dumps(cb, sort_keys=True, separators=(",", ":"))
                        if self.last_cb.get(icao) != key:
                            b["cb"].append([sec, cb])
                            self.last_cb[icao] = key
                self.n_samples += 1

    def add_event(self, ev):
        with self.lock:
            self.events.append(ev)

    def add_metar(self, station, text, t=None):
        if not text or text == self.last_metar:
            return
        self.last_metar = text
        with self.lock:
            self.metars.append((t or time.time(), station, text))

    # ---- writing ----
    def start(self):
        threading.Thread(target=self._writer, name="replay", daemon=True).start()

    def _conn(self, day):
        c = self.conns.get(day)
        if c is None:
            c = sqlite3.connect(os.path.join(self.dir, day + ".db"), check_same_thread=False, timeout=10)
            c.execute("PRAGMA journal_mode = WAL")
            c.execute("PRAGMA synchronous = NORMAL")
            c.execute("CREATE TABLE IF NOT EXISTS blocks (minute INTEGER NOT NULL, icao TEXT NOT NULL, data BLOB NOT NULL, "
                      "PRIMARY KEY (minute, icao)) WITHOUT ROWID")
            c.execute("CREATE TABLE IF NOT EXISTS minutes (minute INTEGER PRIMARY KEY, aircraft INTEGER, samples INTEGER)")
            c.execute("CREATE TABLE IF NOT EXISTS events (t REAL NOT NULL, kind TEXT, icao TEXT, callsign TEXT, rwy TEXT, "
                      "ga INTEGER, low INTEGER)")
            c.execute("CREATE TABLE IF NOT EXISTS metar (t REAL NOT NULL, station TEXT, text TEXT)")
            c.commit()
            for d in [k for k in self.conns if k < day]:          # yesterday's file is finished
                try:
                    self.conns.pop(d).close()
                except Exception:
                    pass
            self.conns[day] = c
        return c

    def _write(self, minute, buf, events, metars):
        try:
            free = shutil.disk_usage(self.dir).free
        except OSError:
            free = None
        if free is not None and free < self.min_free:
            if not self.disk_full:
                print(f"[replay] only {free / 1e9:.1f} GB free - recording paused", flush=True)
            self.disk_full = True
            self.error = f"recording paused: only {free / 1e9:.1f} GB free (limit {self.min_free / 1e9:.0f} GB)"
            return
        if self.disk_full:
            print("[replay] disk space OK again - recording", flush=True)
        self.disk_full = False
        c = self._conn(_day(minute))
        rows, nbytes, nsamp = [], 0, 0
        for icao, b in buf.items():
            if not b["s"]:
                continue
            blob = encode_block(b["s"], b["id"], b["cb"])
            rows.append((minute, icao, blob))
            nbytes += len(blob); nsamp += len(b["s"])
        c.executemany("INSERT OR REPLACE INTO blocks VALUES (?,?,?)", rows)
        c.execute("INSERT OR REPLACE INTO minutes VALUES (?,?,?)", (minute, len(rows), nsamp))
        if events:
            c.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?)",
                          [(e["t"], e["kind"], e["icao"], e.get("callsign"), e.get("rwy"), e.get("ga") or 0,
                            1 if e.get("low") else 0) for e in events])
        if metars:
            c.executemany("INSERT INTO metar VALUES (?,?,?)", metars)
        c.commit()
        self.n_blocks += len(rows)
        self.n_written += nsamp
        self.bytes_written += nbytes
        self.last_write = time.time()
        self.error = None

    def _purge(self):
        """Delete the day files older than `days` days."""
        keep_from = _day(time.time() - (self.days - 1) * 86400)
        for fn in os.listdir(self.dir):
            if fn.endswith(".db") and len(fn) == 13 and fn[:10] < keep_from:
                day = fn[:10]
                c = self.conns.pop(day, None)
                if c:
                    c.close()
                for ext in ("", "-wal", "-shm"):
                    try:
                        os.remove(os.path.join(self.dir, fn + ext))
                    except FileNotFoundError:
                        pass
                print(f"[replay] removed {fn} (older than {self.days} days)", flush=True)

    def _writer(self):
        next_purge = 0
        while True:
            time.sleep(FLUSH_CHECK_SEC)
            with self.lock:
                if not self.pending and self.minute is not None and time.time() - self.minute >= 65:
                    # no data for over a minute (feed lost): close the minute that was collected
                    self.pending.append((self.minute, self.buf, self.events, self.metars))
                    self.buf, self.events, self.metars, self.minute = {}, [], [], None
                work, self.pending = self.pending, []
            for item in work:
                try:
                    self._write(*item)
                except Exception as e:
                    if str(e) != self.error:
                        print(f"[replay] write failed: {e}", flush=True)
                    self.error = f"write failed: {e}"
            if time.time() >= next_purge:
                next_purge = time.time() + 3600
                try:
                    self._purge()
                except Exception as e:
                    print(f"[replay] purge failed: {e}", flush=True)

    # ---- reading ----
    def _ro(self, day):
        p = os.path.join(self.dir, day + ".db")
        if not os.path.exists(p):
            return None
        return sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=10)

    def days_info(self):
        """[{day, minutes, first, last, bytes}] of the files on disk, oldest first."""
        out = []
        try:
            files = sorted(f for f in os.listdir(self.dir) if f.endswith(".db") and len(f) == 13)
        except OSError:
            return out
        for fn in files:
            day = fn[:10]
            info = {"day": day, "minutes": 0, "first": None, "last": None,
                    "bytes": sum(os.path.getsize(os.path.join(self.dir, fn + e))
                                 for e in ("", "-wal") if os.path.exists(os.path.join(self.dir, fn + e)))}
            try:
                c = self._ro(day)
                if c:
                    n, a, b = c.execute("SELECT COUNT(*), MIN(minute), MAX(minute) FROM minutes").fetchone()
                    c.close()
                    info.update(minutes=n, first=a, last=(b + 59) if b is not None else None)
            except sqlite3.Error:
                pass
            out.append(info)
        return out

    def chunk(self, t0, minutes=1, step=1):
        """All aircraft from t0 for `minutes` minutes, every `step` seconds:
        {t0, step, ac: {icao: {s: [[t, lat, lon, alt, gs, trk, vr, src], ...], id: [[t, cs, sq, sel, reg, type]],
        cb: [[t, {...}]]}}, events: [...], metar: [...]} - t as epoch seconds."""
        m0 = int(t0 // 60) * 60
        minutes = max(1, min(10, int(minutes)))
        step = max(1, int(step))
        ac, events, metars = {}, [], []
        by_day = {}
        for k in range(minutes):
            m = m0 + k * 60
            by_day.setdefault(_day(m), []).append(m)
        for day, ms in by_day.items():
            c = self._ro(day)
            if c is None:
                continue
            try:
                rows = c.execute("SELECT minute, icao, data FROM blocks WHERE minute >= ? AND minute <= ? ORDER BY minute",
                                 (ms[0], ms[-1])).fetchall()
                events += [dict(zip(("t", "kind", "icao", "callsign", "rwy", "ga", "low"), r)) for r in
                           c.execute("SELECT * FROM events WHERE t >= ? AND t < ? ORDER BY t", (ms[0], ms[-1] + 60))]
                metars += [{"t": r[0], "station": r[1], "text": r[2]} for r in
                           c.execute("SELECT * FROM metar WHERE t < ? ORDER BY t DESC LIMIT 1", (ms[-1] + 60,))]
            finally:
                c.close()
            for minute, icao, blob in rows:
                d = decode_block(blob)
                a = ac.setdefault(icao, {"s": [], "id": [], "cb": []})
                a["s"] += [[minute + r[0]] + r[1:] for r in d["s"] if r[0] % step == 0 or step == 1]
                a["id"] += [[minute + r[0]] + r[1:] for r in d["id"]]
                a["cb"] += [[minute + r[0], r[1]] for r in d["cb"]]
        if not metars:
            m = self.metar_at(m0 + minutes * 60)
            metars = [m] if m else []
        return {"t0": m0, "minutes": minutes, "step": step, "ac": ac, "events": events, "metar": metars[:1]}

    def _days_between(self, t0, t1):
        d, out = int(t0 // 86400) * 86400, []
        while d <= t1:
            out.append(_day(d)); d += 86400
        return out

    def track(self, icao, t, before=3 * 3600, after=3600, gap=20 * 60, max_points=4000):
        """The flight of `icao` around time t from the recording: [[t, lat, lon, alt, src]], from at most
        `before` s earlier (split at gaps longer than `gap`: the part that contains t, or the last one
        before it) to `after` s later (the replay draws the line up to its time)."""
        icao = (icao or "").upper()
        m0, m1 = int((t - before) // 60) * 60, int((t + after) // 60) * 60
        pts = []
        for day in self._days_between(m0, m1):
            c = self._ro(day)
            if c is None:
                continue
            try:
                rows = c.execute("SELECT minute, data FROM blocks WHERE minute >= ? AND minute <= ? AND icao = ? ORDER BY minute",
                                 (m0, m1, icao)).fetchall()
            finally:
                c.close()
            for minute, blob in rows:
                for r in decode_block(blob)["s"]:
                    if r[1] is not None and r[2] is not None:
                        pts.append([minute + r[0], r[1], r[2], r[3], r[7]])
        if not pts:
            return {"icao": icao, "points": [], "live": True}
        # the part of the flight around t
        segs, cur = [], [pts[0]]
        for p in pts[1:]:
            if p[0] - cur[-1][0] > gap:
                segs.append(cur); cur = []
            cur.append(p)
        segs.append(cur)
        pick = None
        for sg in segs:
            if sg[0][0] <= t + 5:
                pick = sg
        pick = pick or segs[0]
        if len(pick) > max_points:
            step = -(-len(pick) // max_points)
            pick = pick[::step] + [pick[-1]]
        return {"icao": icao, "points": pick, "live": True, "until": m1 + 59}

    def events_between(self, t0, t1):
        """The go-arounds, landings and departures recorded between t0 and t1."""
        out = []
        for day in self._days_between(t0, t1):
            c = self._ro(day)
            if c is None:
                continue
            try:
                out += [dict(zip(("t", "kind", "icao", "callsign", "rwy", "ga", "low"), r)) for r in
                        c.execute("SELECT * FROM events WHERE t >= ? AND t <= ? ORDER BY t", (t0, t1))]
            finally:
                c.close()
        return out

    def metar_at(self, t):
        """The latest METAR recorded at or before t (looks back over the day files of the last 2 days)."""
        for day in reversed(self._days_between(t - 2 * 86400, t)):
            c = self._ro(day)
            if c is None:
                continue
            try:
                r = c.execute("SELECT t, station, text FROM metar WHERE t <= ? ORDER BY t DESC LIMIT 1", (t,)).fetchone()
            finally:
                c.close()
            if r:
                return {"t": r[0], "station": r[1], "text": r[2]}
        return None

    def status(self):
        days = self.days_info()
        total = sum(d["bytes"] for d in days)
        per = (self.bytes_written / self.n_written) if self.n_written else None
        return {"dir": self.dir, "days_kept": self.days, "range_nm": self.range_nm, "days": len(days),
                "bytes_total": total, "first": days[0]["first"] if days else None,
                "last": days[-1]["last"] if days else None, "samples": self.n_samples, "blocks": self.n_blocks,
                "bytes_per_sample": round(per, 2) if per else None,
                "last_write_age": round(time.time() - self.last_write, 1) if self.last_write else None,
                "aircraft_this_minute": len(self.buf), "error": self.error}
