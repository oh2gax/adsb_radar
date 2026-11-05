"""movements.py - the radar's own EFHK movement detection: go-arounds (live, for the GA alarm in
the labels), landings and departures (for the EFHK traffic window, where they fill the rows that
MODE-S Wind's database does not have).

Runs on every update of the aircraft list (once a second, with the ADS-B positions decoded from the
Beast feed). Altitudes are pressure altitudes from the transponders; they are corrected to MSL with
the QNH of the latest EFHK METAR (set_qnh).

Go-around: the method of MODE-S Wind (collector/windshear.py), with its thresholds, in seconds
instead of its 2-3 s sweeps:
  corridor  - within 2.5 NM of a runway's extended centreline, 0-25 NM before its threshold, track
              within 60 deg of the runway heading, not more than 1000 ft below the 3 deg glide path;
              an aircraft climbing faster than 500 fpm that was not on an approach is not in one
              (a climb-out turning through another runway's final);
  approach  - descending (<= -200 fpm) in the corridor for 10 s;
  go-around - on an approach, climbing >= 600 fpm below 2200 ft MSL for 4 s and 50 ft;
              or, after crossing the threshold, 200 ft above the height there (a low go-around or
              a touch-and-go).
Landing: the threshold crossed below 1000 ft and no climb for 60 s, or ground speed under 80 kt after it; or the
aircraft is lost on short final (within 4 NM, below 1500 ft) on an approach.
Departure: within 6 NM of EFHK below 1500 ft MSL, climbing >= 300 fpm at >= 90 kt, not on an
approach and not after a go-around (the start rule of MODE-S Wind's collector/departures.py); the
runway from the direction and the extended centreline, the time from the last point on the ground.
"""
import math
import threading
import time
from collections import deque

# EFHK runways: name, approach heading, threshold lat / lon, threshold elevation ft (AIP, as MODE-S Wind)
RUNWAYS = [
    ("04L", 47, 60.3129, 24.9039, 179), ("04R", 47, 60.3113, 24.9364, 179),
    ("22L", 227, 60.3307, 24.9791, 179), ("22R", 227, 60.3311, 24.9439, 179),
    ("15", 152, 60.3303, 24.9645, 179), ("33", 323, 60.3071, 24.9883, 148),
]
AIRPORT = (60.3172, 24.9633)
ELEV_FT = 179

QNH_FT_PER_HPA = 27.0
GS_FT_PER_NM = 318.5            # 3 deg glide path
MAX_DIST_NM = 30.0              # only aircraft within 30 NM and below 5000 ft MSL are followed
MAX_ALT_FT = 5000.0
CORR_HALF_WIDTH_NM = 2.5
CORR_MAX_NM = 25.0
CORR_MAX_TRACK_DEV = 60.0
CORR_GS_FLOOR_FT = 1000.0
CORR_CLIMB_FPM = 500.0
APP_DESCENT_SEC = 10.0          # MODE-S Wind: 5 sweeps
GA_CLIMB_FPM = 600.0
GA_CLIMB_SEC = 4.0              # MODE-S Wind: 3 sweeps
GA_MIN_GAIN_FT = 50.0
GA_MAX_ALT_FT = 2200.0
GA_COUNT_EXPIRY_SEC = 7200.0
GA_ALARM_SEC = 1800.0           # the GA mark is kept at most 30 min (and until the landing)
LAND_THR_PASS_NM = 0.2
LAND_THR_MAX_FT = 1000.0        # ... and crossed below 1000 ft above the threshold
LAND_CONFIRM_SEC = 60.0
LAND_CANCEL_CLIMB_FT = 200.0
LAND_SLOW_KT = 80.0
LOST_SEC = 30.0                 # not heard for 30 s: lost (landed on short final, or gone)
LOST_FINAL_NM = 4.0
LOST_FINAL_FT = 1500.0
DEP_START_NM = 6.0
DEP_START_MAX_FT = 1500.0
DEP_MIN_VR = 300.0
DEP_MIN_GS = 90.0
DEP_REPEAT_SEC = 1800.0         # one departure per aircraft in 30 min
DEP_AFTER_GA_SEC = 600.0
RING_SEC = 180.0


def _hdg_diff(a, b):
    return abs(((a - b) + 540.0) % 360.0 - 180.0)


def _ne(lat, lon, lat0, lon0):
    """North / east offset in NM (flat earth, fine within 30 NM)."""
    return (lat - lat0) * 60.0, (lon - lon0) * 60.0 * math.cos(math.radians(lat0))


def _dist_nm(lat, lon, lat0, lon0):
    n, e = _ne(lat, lon, lat0, lon0)
    return math.hypot(n, e)


def _along_cross(lat, lon, rwy):
    """Along-track distance before the threshold (positive on final) and cross-track distance."""
    _, hdg, tlat, tlon, _ = rwy
    n, e = _ne(lat, lon, tlat, tlon)
    h = math.radians(hdg)
    along = -(n * math.cos(h) + e * math.sin(h))     # the approach comes from the opposite direction
    cross = -n * math.sin(h) + e * math.cos(h)
    return along, cross


def dep_runway(lat, lon, track):
    """Runway of a climb-out: the runway of that direction (within 25 deg) whose extended
    centreline is nearest (<= 1 NM). As MODE-S Wind / app_beta._dep_runway."""
    if lat is None or lon is None or track is None:
        return None
    best = None
    for rwy in RUNWAYS:
        if _hdg_diff(track, rwy[1]) > 25.0:
            continue
        _, xt = _along_cross(lat, lon, rwy)
        if abs(xt) <= 1.0 and (best is None or abs(xt) < best[0]):
            best = (abs(xt), rwy[0])
    return best[1] if best else None


class MovementDetector:
    def __init__(self, on_event=None):
        self.on_event = on_event          # fn(event dict): t, kind (arr/dep/ga), icao, callsign, rwy, ga, low
        self.qnh = None
        self.state = {}
        self.alarm = {}                   # icao -> {"t", "n", "rwy"}: aircraft with a GA mark
        self.lock = threading.Lock()
        self.n_events = {"arr": 0, "dep": 0, "ga": 0}
        self.recent = deque(maxlen=20)

    def set_qnh(self, qnh):
        if qnh is not None and 900 < qnh < 1100:
            self.qnh = float(qnh)

    def _corr(self):
        """Pressure altitude minus MSL altitude, ft (0 until the QNH is known)."""
        return (1013.25 - self.qnh) * QNH_FT_PER_HPA if self.qnh else 0.0

    # ---- events ----
    def _event(self, kind, icao, st, t, rwy, **extra):
        ev = {"t": round(t, 1), "kind": kind, "icao": icao, "callsign": st.get("cs") or None, "rwy": rwy}
        ev.update(extra)
        self.n_events[kind] += 1
        self.recent.append(ev)
        if self.on_event:
            try:
                self.on_event(ev)
            except Exception as e:
                print(f"[movements] storing an event failed: {e}", flush=True)

    def _go_around(self, icao, st, now, rwy, low=False):
        n = st["ga_n"] + 1 if now - st.get("ga_t", 0) < GA_COUNT_EXPIRY_SEC else 1
        st["ga_n"], st["ga_t"] = n, now
        self.alarm[icao] = {"t": now, "n": n, "rwy": rwy}
        self._event("ga", icao, st, now, rwy, ga=n, low=low)
        st.update(phase="GO_AROUND", climb_s=0.0, climb_alt=None, desc_s=0.0)
        st["land_rwy"] = st["land_t"] = st["land_h"] = None

    def _landed(self, icao, st, t, rwy):
        ga = st["ga_n"] if t - st.get("ga_t", 0) < GA_COUNT_EXPIRY_SEC else 0
        self._event("arr", icao, st, t, rwy, ga=ga)
        st.update(phase="NONE", desc_s=0.0, climb_s=0.0, climb_alt=None, ga_n=0, ga_t=0, arr_t=t, left=False)
        st["land_rwy"] = st["land_t"] = st["land_h"] = st["app_rwy"] = None
        self.alarm.pop(icao, None)

    # ---- the corridor (as MODE-S Wind's _best_runway + gates) ----
    def _corridor(self, lat, lon, h, trk, vr, st):
        best = None
        for rwy in RUNWAYS:
            along, xt = _along_cross(lat, lon, rwy)
            if abs(xt) > CORR_HALF_WIDTH_NM or along < 0 or along > CORR_MAX_NM:
                continue
            if trk is not None and _hdg_diff(trk, rwy[1]) > CORR_MAX_TRACK_DEV:
                continue
            if best is None or abs(xt) < abs(best[2]):
                best = (rwy, along, xt)
        if best is None:
            return None
        rwy, along, _ = best
        if h < rwy[4] + _dist_nm(lat, lon, rwy[2], rwy[3]) * GS_FT_PER_NM - CORR_GS_FLOOR_FT:
            return None                       # far below the glide path: traffic for another runway
        if vr > CORR_CLIMB_FPM and st["phase"] == "NONE" and st["land_rwy"] is None:
            return None                       # a climb-out crossing a final
        return rwy, along

    # ---- one update of the whole aircraft list ----
    def update(self, objs, now=None):
        now = now or time.time()
        corr = self._corr()
        seen = set()
        with self.lock:
            for o in objs:
                try:
                    self._one(o, now, corr, seen)
                except (TypeError, ValueError):
                    continue
            # aircraft no longer heard
            for icao in [k for k, st in self.state.items() if k not in seen and now - st["seen"] > LOST_SEC]:
                st = self.state.pop(icao)
                if st["land_rwy"] is not None:
                    self._landed(icao, st, st["land_t"], st["land_rwy"])
                elif (st["phase"] == "APPROACHING" and st.get("app_along") is not None
                      and st["app_along"] <= LOST_FINAL_NM and st["h"] <= ELEV_FT + LOST_FINAL_FT):
                    self._landed(icao, st, st["seen"], st["app_rwy"])
            for icao in [k for k, a in self.alarm.items() if now - a["t"] > GA_ALARM_SEC or
                         (k not in self.state)]:
                self.alarm.pop(icao, None)

    def _one(self, o, now, corr, seen):
        icao = str(o.get("hex") or "").upper()
        lat, lon, alt = o.get("lat"), o.get("lon"), o.get("alt_baro")
        if len(icao) != 6 or lat is None or lon is None or alt is None:
            return
        lat, lon, alt = float(lat), float(lon), float(alt)
        if _dist_nm(lat, lon, *AIRPORT) > MAX_DIST_NM or alt - corr > MAX_ALT_FT:
            if icao in self.state:
                self.state.pop(icao)
                self.alarm.pop(icao, None)
            return
        seen.add(icao)
        h = alt - corr                                   # ft MSL
        gs = float(o["gs"]) if o.get("gs") is not None else None
        trk = float(o["track"]) if o.get("track") is not None else None
        st = self.state.get(icao)
        if st is None:
            st = self.state[icao] = {"phase": "NONE", "desc_s": 0.0, "climb_s": 0.0, "climb_alt": None,
                                     "left": False, "land_rwy": None, "land_t": None, "land_h": None,
                                     "app_rwy": None, "app_along": None, "ga_n": 0, "ga_t": 0,
                                     "dep_t": 0, "arr_t": 0, "ring": deque(), "seen": now, "h": h, "cs": None}
        cs = (o.get("flight") or "").strip()
        if cs:
            st["cs"] = cs
        if st["ring"] and now - st["ring"][-1][0] < 0.5:  # the same second again
            return
        dt = min(5.0, now - st["seen"]) if st["ring"] else 0.0
        vr = o.get("baro_rate")
        if vr is None and st["ring"]:                   # no vertical rate: from the heights of the last ~10 s
            old = next((p for p in st["ring"] if now - p[0] <= 12), None)
            vr = (h - old[3]) / (now - old[0]) * 60 if old and now - old[0] >= 4 else 0.0
        vr = float(vr or 0.0)
        st["seen"], st["h"] = now, h
        st["ring"].append((now, lat, lon, h, gs, trk))
        while st["ring"] and now - st["ring"][0][0] > RING_SEC:
            st["ring"].popleft()

        m = self._corridor(lat, lon, h, trk, vr, st)
        rwy = m[0][0] if m else None
        # threshold crossed: the runway match ends (or flips to the parallel runway) at / past the threshold
        if st["land_rwy"] is None and st["phase"] == "APPROACHING" and st["app_rwy"] and rwy != st["app_rwy"]:
            r = next(x for x in RUNWAYS if x[0] == st["app_rwy"])
            # a landing crosses the threshold low (~50 ft): an aircraft passing over the runway higher up
            # (descending through 2000 ft, say) has not landed
            if _along_cross(lat, lon, r)[0] <= LAND_THR_PASS_NM and h <= r[4] + LAND_THR_MAX_FT:
                st["land_rwy"], st["land_t"], st["land_h"] = st["app_rwy"], now, h

        if m:
            if st["phase"] == "GO_AROUND" and st["left"]:      # back on an approach after a go-around
                st.update(phase="NONE", left=False, desc_s=0.0, climb_s=0.0, climb_alt=None)
            if st["phase"] == "NONE":
                st["desc_s"] = st["desc_s"] + dt if vr <= -200 else max(0.0, st["desc_s"] - dt)
                if st["desc_s"] >= APP_DESCENT_SEC:
                    st["phase"] = "APPROACHING"
            elif st["phase"] == "APPROACHING":
                if vr >= GA_CLIMB_FPM and h <= GA_MAX_ALT_FT:
                    if st["climb_s"] == 0:
                        st["climb_alt"] = h
                    st["climb_s"] += max(dt, 0.5)
                    if st["climb_s"] >= GA_CLIMB_SEC and h - st["climb_alt"] >= GA_MIN_GAIN_FT:
                        self._go_around(icao, st, now, st["land_rwy"] or rwy)
                else:
                    st["climb_s"], st["climb_alt"] = 0.0, None
            if st["phase"] == "APPROACHING":
                st["app_rwy"], st["app_along"] = rwy, m[1]
        else:
            if st["phase"] == "APPROACHING":
                st.update(phase="NONE", desc_s=0.0, climb_s=0.0, climb_alt=None)
            elif st["phase"] == "GO_AROUND":
                st["left"] = True

        # after the threshold: landed, or a low go-around / touch-and-go
        if st["land_rwy"] is not None:
            if h > st["land_h"] + LAND_CANCEL_CLIMB_FT:
                self._go_around(icao, st, now, st["land_rwy"], low=True)
                st["left"] = not m
            elif (gs is not None and gs < LAND_SLOW_KT) or now - st["land_t"] >= LAND_CONFIRM_SEC:
                self._landed(icao, st, st["land_t"], st["land_rwy"])
            elif m and st["phase"] == "APPROACHING" and m[1] > 3.0:
                st["land_rwy"] = st["land_t"] = st["land_h"] = None    # a new approach far out

        # departure
        if (st["phase"] == "NONE" and st["land_rwy"] is None and vr >= DEP_MIN_VR
                and gs is not None and gs >= DEP_MIN_GS and h <= DEP_START_MAX_FT
                and now - st["dep_t"] > DEP_REPEAT_SEC and now - st.get("ga_t", 0) > DEP_AFTER_GA_SEC
                and _dist_nm(lat, lon, *AIRPORT) <= DEP_START_NM):
            st["dep_t"] = now
            t_off, r = self._takeoff(st, now, h, vr)
            self._event("dep", icao, st, t_off, r)

    def _takeoff(self, st, now, h, vr):
        """Takeoff time and runway: the last point near the ground with take-off speed, else an
        estimate from the height and the climb rate; the runway from the first airborne points."""
        ring = list(st["ring"])
        low = [p for p in ring if p[3] <= ELEV_FT + 150 and (p[4] or 0) >= 60]
        if low:
            t_off = low[-1][0]
        else:
            t_off = now - min(180.0, max(0.0, h - ELEV_FT) / max(vr, 500.0) * 60.0)
        rwy = None
        for p in ring:                                # the first points after the takeoff first
            if p[0] >= t_off - 5 and p[5] is not None:
                rwy = dep_runway(p[1], p[2], p[5])
                if rwy:
                    break
        return t_off, rwy

    # ---- for the app ----
    def ga_info(self, icao):
        a = self.alarm.get(icao)
        if not a:
            return None
        return {"age": round(time.time() - a["t"], 1), "n": a["n"], "rwy": a["rwy"]}

    def status(self):
        with self.lock:
            return {"qnh": self.qnh, "followed": len(self.state), "ga_marks": len(self.alarm),
                    "events": dict(self.n_events), "recent": list(self.recent)[-10:]}
