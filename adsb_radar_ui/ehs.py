"""
ehs.py - Enhanced Mode-S values for the TopSky extended label, from a Beast feed.

Reads the Beast stream that MODE-S Wind offers to programs on the same machine
(127.0.0.1:31005 by default; MODE-S Wind's Maintenance page switches it on) and
keeps, per aircraft, the latest values of the replies the radar needs:

  - Comm-B DF20/21: BDS 5,0 (roll, true track, ground speed, TAS, track rate),
    BDS 6,0 (magnetic heading, IAS, Mach), BDS 4,0 (selected altitude);
  - ADS-B DF17: type 29 (autopilot / approach mode, selected altitude, NACp)
    and type 31 (NACp).

Only replies of aircraft that are on the radar (the JSON feed) are decoded; the
rest of the stream is skipped after a 2 us address check, so this costs little
CPU next to MODE-S Wind's own decoder. BDS 5,0 / 6,0 are told apart with the
aircraft's known speed, track and altitude from the JSON feed (pyModeS "known"),
and a DF20 whose altitude differs from the feed by more than 1000 ft is ignored
(a reply of another aircraft whose CRC happened to give this address).

From a BDS 5,0 + 6,0 pair no more than 10 s apart, wings level (roll <= 5 deg,
track rate <= 1 deg/s), the wind is computed as in MODE-S Wind
(collector/wind_calc.py): ground vector minus air vector, heading magnetic +
declination (WMM2025 via pygeomag, else MAG_DECLINATION). The static air
temperature comes from TAS and Mach (collector/atmos.py). The label shows the
average of the last minute.

From 2026-11-04 the same stream also gives the aircraft positions: every ADS-B airborne /
surface position (DF17/18 types 5-8, 9-18, 20-22) is decoded on its own against a nearby
reference - the aircraft's last decoded position, else its position in the JSON feed, else the
radar centre - so positions are available at once (no waiting for an even/odd pair) and the
reference is always well within the 180 NM (surface 45 NM) the method needs. A position that
implies more than 900 kt from the last one, or lies more than 20 NM from the aircraft's JSON-feed
position, is rejected. Ground speed, track and vertical rate come from the velocity messages
(type 19). The radar shows these instead of the 2-second JSON-feed positions when they are
fresh, and every position goes to the track recorder (tracks.py) for the history line.

Nothing is stored on disk here. If the feed is not available the radar works as before
(JSON-feed positions); the extended label then shows only the values of the JSON feed.
"""

import logging
import math
import socket
import threading
import time
from collections import deque

log = logging.getLogger("ehs")

MAX_AGE_SEC = 20.0          # a register older than this is not shown
AP_MAX_AGE_SEC = 120.0      # autopilot / approach flags, selected altitude
NACP_MAX_AGE_SEC = 30.0
PAIR_MAX_SEC = 10.0         # BDS 5,0 and 6,0 at most this far apart for a wind
WIND_AVG_SEC = 60.0
MAX_ROLL_DEG = 5.0
MAX_TRACK_RATE = 1.0
MAX_WIND_KT = 150.0
DF20_ALT_TOL_FT = 1000.0
FORGET_SEC = 300.0
RECONNECT_SEC = 10.0

_BEAST_LEN = {0x31: 2, 0x32: 7, 0x33: 14}   # Beast frame type -> payload bytes
_cpr = None                                  # pyModeS.position._cpr (set when pyModeS loads)


# ---- magnetic declination (WMM2025 via pygeomag, cached on a 0.5 deg grid) ----
class _Declination:
    GRID = 0.5

    def __init__(self, fixed):
        self.fixed = fixed
        self.model = None
        self.cache = {}
        self.year = None
        try:
            from pygeomag import GeoMag
            self.model = GeoMag(coefficients_file="wmm/WMM_2025.COF")
        except Exception as e:  # pygeomag missing -> fixed value
            print(f"[ehs] pygeomag not available ({e}); declination fixed {fixed} deg", flush=True)

    def _corner(self, i, j):
        k = (i, j)
        if k not in self.cache:
            t = time.gmtime()
            yr = t.tm_year + (t.tm_yday - 1) / 365.25
            self.cache[k] = self.model.calculate(glat=i * self.GRID, glon=j * self.GRID, alt=0.0, time=yr,
                                                 allow_date_outside_lifespan=True).d
        return self.cache[k]

    def at(self, lat, lon):
        if self.model is None or lat is None or lon is None:
            return self.fixed
        try:
            day = int(time.time() // 86400)
            if day != self.year:          # follow the slow drift: rebuild once a day
                self.cache.clear()
                self.year = day
            fi, fj = lat / self.GRID, lon / self.GRID
            i, j = math.floor(fi), math.floor(fj)
            u, v = fi - i, fj - j
            d00, d01 = self._corner(i, j), self._corner(i, j + 1)
            d10, d11 = self._corner(i + 1, j), self._corner(i + 1, j + 1)
            return (d00 * (1 - u) * (1 - v) + d01 * (1 - u) * v + d10 * u * (1 - v) + d11 * u * v)
        except Exception:
            return self.fixed


def _nm(la1, lo1, la2, lo2):
    dy = (la2 - la1) * 60.0
    dx = (lo2 - lo1) * 60.0 * math.cos(math.radians((la1 + la2) / 2))
    return math.hypot(dx, dy)


def _isa_temp_c(alt_ft):
    m = alt_ft * 0.3048
    return (288.15 - 0.0065 * m if m <= 11000 else 216.65) - 273.15


def _sat_c(tas, mach, alt_ft):
    """Static air temperature from TAS (kt) and Mach, as MODE-S Wind (atmos.tm_temp_c)."""
    if tas is None or mach is None or mach < 0.20 or tas < 60:
        return None
    t = 288.15 * (tas / (661.47 * mach)) ** 2 - 273.15
    if not -85.0 <= t <= 50.0:
        return None
    if alt_ft is not None and abs(t - _isa_temp_c(alt_ft)) > 40.0:
        return None
    return t


def _mach_to_tas(mach, alt_ft):
    """TAS (kt) from Mach at the ISA temperature of the pressure altitude."""
    t = _isa_temp_c(alt_ft) + 273.15
    return mach * 38.967854 * math.sqrt(t)


def _wind(trk, gs, hdg_true, tas):
    """(speed kt, direction FROM deg) = ground vector - air vector."""
    wn = gs * math.cos(math.radians(trk)) - tas * math.cos(math.radians(hdg_true))
    we = gs * math.sin(math.radians(trk)) - tas * math.sin(math.radians(hdg_true))
    return math.hypot(wn, we), (math.degrees(math.atan2(we, wn)) + 180.0) % 360.0


class EhsReceiver:
    def __init__(self, host, port, mag_declination=10.5, center=(60.3172, 24.9633)):
        self.host, self.port = host, int(port)
        self.center = center
        self.pos = {}           # HEX -> (t, lat, lon, alt or None, surface)
        self.vel = {}           # HEX -> (t, gs, track, vertical rate)
        self.on_position = None # callback(icao, t, lat, lon, alt) - the track recorder
        self.n_pos = 0
        self.n_pos_rejected = 0
        self.decl = _Declination(mag_declination)
        self.lock = threading.Lock()
        self.feed = {}          # HEX -> {"gs","trk","alt","lat","lon"} from the JSON feed
        self.ac = {}            # HEX -> state
        self.connected = False
        self.error = None
        self.n_msgs = 0
        self.n_used = 0
        self.last_msg = 0.0
        self.started = None
        self.pms = None
        try:
            import pyModeS
            from pyModeS import util
            self.pms, self.util = pyModeS, util
        except Exception as e:
            self.error = f"pyModeS not installed: {e}"
            print(f"[ehs] {self.error} - extended label without Comm-B values", flush=True)
        if self.pms is not None:
            try:                    # ADS-B positions only; the Comm-B values work without it
                global _cpr
                from pyModeS.position import _cpr as cpr_mod
                _cpr = cpr_mod
            except Exception as e:
                print(f"[ehs] this pyModeS has no pyModeS.position._cpr ({e}) - no 1-second ADS-B positions", flush=True)

    # ---- called by the app ----
    def start(self):
        if self.pms is None or not self.port:
            return
        self.started = time.time()
        threading.Thread(target=self._run, name="ehs", daemon=True).start()

    def set_feed(self, aircraft):
        """The current JSON feed list (called after every poll)."""
        feed = {}
        for o in aircraft:
            hx = str(o.get("hex") or "").upper()
            if len(hx) != 6:
                continue
            def num(*keys):
                for k in keys:
                    v = o.get(k)
                    if v is not None:
                        try:
                            return float(v)
                        except (TypeError, ValueError):
                            pass
                return None
            feed[hx] = {"gs": num("gs", "spd"), "trk": num("track", "trk"), "alt": num("alt_baro", "alt"),
                        "lat": num("lat"), "lon": num("lon")}
        self.feed = feed

    def fresh(self, icao, max_age=3.0):
        """(position, velocity) heard within max_age seconds, each None if not."""
        now = time.time()
        p, v = self.pos.get(icao), self.vel.get(icao)
        return (p if p and now - p[0] <= max_age else None,
                v if v and now - v[0] <= max_age + 2 else None)

    def get(self, icao):
        """Values for the extended label of one aircraft (same keys as MODE-S Wind's /api/live/ac)."""
        icao = (icao or "").upper()[:6]
        now = time.time()
        f = self.feed.get(icao) or {}
        out = {"icao": icao, "ehs": self.connected, "b50": None, "b60": None, "sel": None, "ap": None,
               "app": None, "nacp": None, "wdir": None, "wspd": None, "temp": None,
               "decl": round(self.decl.at(f.get("lat"), f.get("lon")), 1)}
        with self.lock:
            s = self.ac.get(icao)
            if not s:
                return out
            r = lambda v, n=0: (round(v, n) if n else round(v)) if isinstance(v, (int, float)) else None
            if s.get("b50") and now - s["b50"][0] <= MAX_AGE_SEC:
                t, d = s["b50"]
                out["b50"] = {"age": round(now - t, 1), "roll": r(d.get("roll"), 1), "trk": r(d.get("true_track"), 1),
                              "gs": r(d.get("groundspeed")), "tas": r(d.get("true_airspeed")),
                              "rate": r(d.get("track_rate"), 2)}
            if s.get("b60") and now - s["b60"][0] <= MAX_AGE_SEC:
                t, d = s["b60"]
                out["b60"] = {"age": round(now - t, 1), "ias": r(d.get("indicated_airspeed")),
                              "mhdg": r(d.get("magnetic_heading"), 1), "mach": r(d.get("mach"), 3)}
            if s.get("sel") and now - s["sel"][0] <= AP_MAX_AGE_SEC:
                out["sel"] = s["sel"][1]
            if s.get("ap") and now - s["ap"][0] <= AP_MAX_AGE_SEC:
                out["ap"], out["app"] = s["ap"][1], s["ap"][2]
            if s.get("nacp") and now - s["nacp"][0] <= NACP_MAX_AGE_SEC:
                out["nacp"] = s["nacp"][1]
            winds = [w for w in s.get("winds", ()) if now - w[0] <= WIND_AVG_SEC]
            if winds:
                n = sum(w[1] * math.cos(math.radians(w[2])) for w in winds) / len(winds)
                e = sum(w[1] * math.sin(math.radians(w[2])) for w in winds) / len(winds)
                out["wspd"] = round(math.hypot(n, e))
                out["wdir"] = round(math.degrees(math.atan2(e, n)) % 360)
            temps = [t[1] for t in s.get("temps", ()) if now - t[0] <= WIND_AVG_SEC]
            if temps:
                out["temp"] = round(sum(temps) / len(temps), 1)
        return out

    def status(self):
        with self.lock:
            n_ehs = sum(1 for s in self.ac.values() if s.get("b50") or s.get("b60"))
        now = time.time()
        return {"enabled": self.pms is not None and bool(self.port), "connected": self.connected,
                "host": self.host, "port": self.port, "messages": self.n_msgs, "used": self.n_used,
                "positions": self.n_pos, "positions_rejected": self.n_pos_rejected,
                "aircraft_with_adsb_position": sum(1 for p in list(self.pos.values()) if now - p[0] <= 10),
                "aircraft_with_commb": n_ehs, "last_message_age": round(time.time() - self.last_msg, 1) if self.last_msg else None,
                "error": self.error}

    # ---- the reader thread ----
    def _run(self):
        last_err = None
        next_cleanup = time.time() + 60
        while True:
            try:
                with socket.create_connection((self.host, self.port), timeout=10) as sock:
                    sock.settimeout(60)
                    self.connected, self.error = True, None
                    print(f"[ehs] connected to Beast feed {self.host}:{self.port}", flush=True)
                    last_err = None
                    buf = b""
                    while True:
                        chunk = sock.recv(65536)
                        if not chunk:
                            raise ConnectionError("feed closed the connection")
                        buf = self._parse(buf + chunk)
                        if time.time() >= next_cleanup:
                            self._cleanup()
                            next_cleanup = time.time() + 60
            except Exception as e:
                self.connected = False
                self.error = str(e)
                if str(e) != last_err:
                    print(f"[ehs] Beast feed {self.host}:{self.port} not available: {e} (retrying every {RECONNECT_SEC:.0f} s)", flush=True)
                    last_err = str(e)
            time.sleep(RECONNECT_SEC)

    def _parse(self, buf):
        """Decode all complete Beast frames in buf; return the unparsed rest.
        Frame: 0x1a, type ('1' Mode A/C, '2' short, '3' long), 6-byte time stamp,
        signal byte, payload; every 0x1a inside the frame is doubled."""
        i, n = 0, len(buf)
        while True:
            i = buf.find(b"\x1a", i)
            if i < 0:
                return b""
            if i + 1 >= n:
                return buf[i:]
            plen = _BEAST_LEN.get(buf[i + 1])
            if plen is None:             # not a frame start (e.g. the 2nd byte of an escaped 0x1a)
                i += 1
                continue
            need, out, j = 7 + plen, bytearray(), i + 2
            while len(out) < need:
                if j >= n:
                    return buf[i:]       # incomplete: wait for more bytes
                c = buf[j]
                if c == 0x1a:
                    if j + 1 >= n:
                        return buf[i:]
                    if buf[j + 1] != 0x1a:
                        break            # a new frame starts: this one was cut short
                    j += 1
                out.append(c)
                j += 1
            if len(out) < need:
                i = j
                continue
            i = j
            if plen >= 7:
                self.last_msg = time.time()
                self.n_msgs += 1
                try:
                    self._handle(out[7:].hex().upper())
                except Exception as e:
                    log.debug("decode error: %s", e)

    def _handle(self, msg):
        df = int(msg[:2], 16) >> 3
        if df in (20, 21):
            icao = self.util.icao(msg)
            f = self.feed.get(icao)
            if f is None:
                return                       # not on the radar (or a garbled reply)
            known = {k2: f[k1] for k1, k2 in (("gs", "groundspeed"), ("trk", "track"), ("alt", "altitude"))
                     if f.get(k1) is not None}
            with self.lock:
                s = self.ac.get(icao)
                if s:
                    known.update(s.get("known", {}))
            r = self.pms.decode(msg, known=known or None)
            if df == 20 and r.get("altitude") is not None and f.get("alt") is not None \
                    and abs(r["altitude"] - f["alt"]) > DF20_ALT_TOL_FT:
                return
            bds = r.get("bds")
            if bds not in ("5,0", "6,0", "4,0"):
                return
            self.n_used += 1
            now = time.time()
            with self.lock:
                s = self.ac.setdefault(icao, {"winds": deque(maxlen=20), "temps": deque(maxlen=20), "known": {}})
                s["seen"] = now
                if bds == "5,0":
                    s["b50"] = (now, r)
                    for k_dec, k_known in (("true_airspeed", "tas"), ("true_track", "track"), ("groundspeed", "groundspeed")):
                        if r.get(k_dec) is not None:
                            s["known"][k_known] = r[k_dec]
                elif bds == "6,0":
                    s["b60"] = (now, r)
                    for k_dec, k_known in (("magnetic_heading", "heading"), ("indicated_airspeed", "ias"), ("mach", "mach")):
                        if r.get(k_dec) is not None:
                            s["known"][k_known] = r[k_dec]
                else:
                    sel = r.get("selected_altitude_mcp") or r.get("selected_altitude_fms")
                    if sel:
                        s["sel"] = (now, sel)
                if bds in ("5,0", "6,0"):
                    self._pair(icao, s, f, now)
        elif df in (17, 18):
            tc = self.util.typecode(msg)
            if tc is None:
                return
            if 5 <= tc <= 18 or 20 <= tc <= 22:
                self._position(msg, tc)
                return
            if tc == 19:
                r = self.pms.decode(msg)
                if r.get("crc_valid") is False or not r.get("icao") or r.get("groundspeed") is None:
                    return
                self.vel[r["icao"]] = (time.time(), r.get("groundspeed"), r.get("track"), r.get("vertical_rate"))
                return
            if tc not in (29, 31) or df != 17:
                return
            icao = msg[2:8]
            if icao not in self.feed:
                return
            r = self.pms.decode(msg)
            if r.get("crc_valid") is False:
                return
            self.n_used += 1
            now = time.time()
            with self.lock:
                s = self.ac.setdefault(icao, {"winds": deque(maxlen=20), "temps": deque(maxlen=20), "known": {}})
                s["seen"] = now
                if r.get("nac_p") is not None:
                    s["nacp"] = (now, r["nac_p"])
                if tc == 29:
                    if r.get("autopilot") is not None:
                        s["ap"] = (now, bool(r.get("autopilot")), bool(r.get("approach_mode")))
                    if r.get("selected_altitude"):
                        s["sel"] = (now, r["selected_altitude"])

    def _position(self, msg, tc):
        """One ADS-B position, decoded against a nearby reference (see the module notes)."""
        r = self.pms.decode(msg)
        if r.get("crc_valid") is False:
            return
        icao, fmt, clat, clon = r.get("icao"), r.get("cpr_format"), r.get("cpr_lat"), r.get("cpr_lon")
        if not icao or fmt is None or clat is None or clon is None:
            return
        now = time.time()
        surface = tc <= 8
        prev = self.pos.get(icao)
        f = self.feed.get(icao)
        if prev and now - prev[0] < 60:
            ref, ref_kind = (prev[1], prev[2]), "own"
        elif f and f.get("lat") is not None and f.get("lon") is not None:
            ref, ref_kind = (f["lat"], f["lon"]), "feed"
        else:
            ref, ref_kind = self.center, "centre"
        try:
            fn = _cpr.surface_position_with_ref if surface else _cpr.airborne_position_with_ref
            lat, lon = fn(fmt, clat, clon, ref[0], ref[1])
        except Exception:
            return
        d_ref = _nm(ref[0], ref[1], lat, lon)
        if ref_kind == "centre" and d_ref > (40 if surface else 170):
            self.n_pos_rejected += 1
            return
        if f and f.get("lat") is not None and _nm(f["lat"], f["lon"], lat, lon) > 20:
            self.n_pos_rejected += 1      # far from where the JSON feed has it: not this aircraft
            return
        if prev and now - prev[0] < 30:
            dt = max(0.5, now - prev[0])
            if _nm(prev[1], prev[2], lat, lon) / dt * 3600 > 900:
                self.n_pos_rejected += 1
                return
        alt = r.get("altitude") if 9 <= tc <= 18 else None
        self.pos[icao] = (now, lat, lon, alt, surface)
        self.n_pos += 1
        cb = self.on_position
        if cb is not None:
            try:
                cb(icao, now, lat, lon, alt if alt is not None else (f.get("alt") if f else None))
            except Exception as e:
                log.debug("track recorder: %s", e)

    def _pair(self, icao, s, f, now):
        """Wind and temperature from the latest BDS 5,0 + 6,0 (lock held)."""
        if not (s.get("b50") and s.get("b60")):
            return
        t50, b50 = s["b50"]
        t60, b60 = s["b60"]
        if abs(t50 - t60) > PAIR_MAX_SEC:
            return
        alt = f.get("alt")
        tas, mach = b50.get("true_airspeed"), b60.get("mach")
        sat = _sat_c(tas, mach, alt)
        if sat is not None:
            s["temps"].append((now, sat))
        trk, gs, mh = b50.get("true_track"), b50.get("groundspeed"), b60.get("magnetic_heading")
        roll, rate = b50.get("roll"), b50.get("track_rate")
        if trk is None or gs is None or mh is None:
            return
        if (roll is not None and abs(roll) > MAX_ROLL_DEG) or (rate is not None and abs(rate) > MAX_TRACK_RATE):
            return
        if tas is None and mach is not None and alt is not None:
            tas = _mach_to_tas(mach, alt)
        if tas is None or tas < 50:
            return
        hdg = (mh + self.decl.at(f.get("lat"), f.get("lon"))) % 360.0
        spd, wdir = _wind(trk, gs, hdg, tas)
        if spd <= MAX_WIND_KT:
            s["winds"].append((now, spd, wdir))

    def _cleanup(self):
        cut = time.time() - FORGET_SEC
        with self.lock:
            for k in [k for k, s in self.ac.items() if s.get("seen", 0) < cut]:
                del self.ac[k]
        for d in (self.pos, self.vel):
            for k in [k for k, v in list(d.items()) if v[0] < cut]:
                d.pop(k, None)
