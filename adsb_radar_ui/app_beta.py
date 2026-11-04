
import os, re, time, threading, csv, sys, json, socket, subprocess, sqlite3, urllib.request
from datetime import datetime
from math import radians, cos
from urllib.request import pathname2url
from flask import Flask, jsonify, render_template, request, abort
from overlays import register_overlays
import config
import ehs

app = Flask(__name__, static_url_path="/static")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _compute_version():
    """Version = date of the latest git commit in Helsinki time, e.g. v.03112026.
    Returns (version, asset_tag); asset_tag (commit hash) busts browser caches after updates."""
    def git(*args):
        try:
            r = subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True, timeout=5)
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""
    ts, short = git("log", "-1", "--format=%ct"), git("log", "-1", "--format=%h")
    if ts.isdigit():
        try:
            from zoneinfo import ZoneInfo
            dt = datetime.fromtimestamp(int(ts), ZoneInfo("Europe/Helsinki"))
        except Exception:
            dt = datetime.fromtimestamp(int(ts))
        return "v." + dt.strftime("%d%m%Y"), short or ts
    return "v.dev", str(int(time.time()))


APP_VERSION, ASSET_TAG = _compute_version()
print(f"[app] adsb_radar {APP_VERSION} ({ASSET_TAG})", flush=True)

# data = last good result, ok_ts = time of last successful feed read, err = last error
_cache = {"ts": 0, "ok_ts": 0, "data": None, "err": None}

def _nm_distance(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, atan2, sqrt
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    km = 6371.0 * c
    return km * 0.539957

def _within_range(obj):
    if not config.MAX_RANGE_NM or not isinstance(obj, dict):
        return True
    try:
        lat = obj.get("lat") or obj.get("latitude")
        lon = obj.get("lon") or obj.get("longitude")
        if lat is None or lon is None:
            return True
        return _nm_distance(config.CENTER_LAT, config.CENTER_LON, float(lat), float(lon)) <= config.MAX_RANGE_NM
    except Exception:
        return True

# --- Registration / type lookup ---
# 1. BaseStation.sqb (table Aircraft) - on AWS the copy that mode_s_wind completes every morning
# 2. aircraft_ref.db (table ac, ~620 000 aircraft from tar1090-db, also from mode_s_wind)
#    fills whatever BaseStation.sqb does not have.
# Both are opened read-only and never created. Results are cached with an expiry, and the cache
# is cleared when either file changes, so daily updates show up without restarting this service.
REG_DB_PATH  = config.REG_DB_PATH
REF_DB_PATH  = config.REF_DB_PATH
REG_TABLE    = os.environ.get("REG_TABLE")      # optional override
REG_ICAO_COL = os.environ.get("REG_ICAO_COL")   # optional override
REG_REG_COL  = os.environ.get("REG_REG_COL")    # optional override
REG_TYPE_COL = os.environ.get("REG_TYPE_COL")   # optional override
REG_HIT_TTL  = 6 * 3600    # seconds a found registration/type is cached
REG_MISS_TTL = 10 * 60     # seconds a "not found" result is cached
REG_CACHE_MAX = 20000

_reg_lock = threading.Lock()
_meta_cache = {}   # HEX -> (expires_ts, reg, type)
_schema = {"table": None, "icao_col": None, "reg_col": None, "type_col": None, "source": None}
_reg_state = {"next_detect": 0.0, "next_check": 0.0, "last_msg": {}}


def _reg_log(msg, key="regdb"):
    """Print a message only when it differs from the previous one with the same key (no log spam)."""
    if _reg_state["last_msg"].get(key) != msg:
        _reg_state["last_msg"][key] = msg
        print(msg, flush=True)


def _reg_reset_schema():
    _schema.update({"table": None, "icao_col": None, "reg_col": None, "type_col": None, "source": None})
    _reg_state["next_detect"] = 0.0


class _ReadOnlyDb:
    """A SQLite file opened read-only. The file is checked at most every 30 s: a missing file is
    never created, a replaced file is reopened, and a changed file sets `changed` (cache reset)."""

    def __init__(self, name, path):
        self.name, self.path = name, path
        self.conn, self.ident, self.mtime = None, None, None
        self.next_stat = 0.0
        self.changed = False

    def get(self):
        if not self.path:
            return None
        now = time.time()
        if now < self.next_stat:
            return self.conn
        self.next_stat = now + 30
        try:
            st = os.stat(self.path)
        except OSError:
            if self.conn is not None:
                self._close()
                self.changed = True
            _reg_log(f"[regdb] {self.name} not found: {self.path}", self.name)
            return None
        ident = (st.st_dev, st.st_ino)
        if self.conn is not None and ident == self.ident:
            if st.st_mtime != self.mtime:
                self.mtime = st.st_mtime
                self.changed = True
            return self.conn
        self._close()
        try:
            uri = "file:" + pathname2url(os.path.abspath(self.path)) + "?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=2.0)
            self.ident, self.mtime, self.changed = ident, st.st_mtime, True
            _reg_log(f"[regdb] {self.name} opened read-only: {self.path}", self.name)
        except Exception as e:
            self.conn = None
            _reg_log(f"[regdb] {self.name} cannot be opened ({self.path}): {e}", self.name)
        return self.conn

    def _close(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
        self.conn, self.ident, self.mtime = None, None, None


_bs_db = _ReadOnlyDb("BaseStation.sqb", REG_DB_PATH)
_ref_db = _ReadOnlyDb("aircraft_ref.db", REF_DB_PATH)


def _reg_connect():
    """Open/check both databases; clear the cache if either changed. Returns the BaseStation connection."""
    conn = _bs_db.get()
    _ref_db.get()
    if _bs_db.changed:
        _reg_reset_schema()
    if _bs_db.changed or _ref_db.changed:
        _meta_cache.clear()
        _bs_db.changed = _ref_db.changed = False
    return conn


def _ref_lookup(key):
    """(reg, type) from aircraft_ref.db table ac, or (None, None)."""
    conn = _ref_db.conn
    if conn is None:
        return None, None
    try:
        row = conn.execute("SELECT reg, type FROM ac WHERE icao = ?", (key,)).fetchone()
    except sqlite3.Error as e:
        _reg_log(f"[regdb] aircraft_ref.db lookup failed: {e}", "ref_err")
        return None, None
    if not row:
        return None, None
    return (str(row[0]).strip().upper() or None) if row[0] else None, \
           (str(row[1]).strip().upper() or None) if row[1] else None


def _detect_schema(conn):
    """Find table + ICAO, registration and type columns. Retries at most once a minute."""
    if _schema["table"] and _schema["icao_col"]:
        return _schema["table"], _schema["icao_col"], _schema["reg_col"], _schema["type_col"]
    if conn is None or time.time() < _reg_state["next_detect"]:
        return None, None, None, None
    if REG_TABLE and REG_ICAO_COL and (REG_REG_COL or REG_TYPE_COL):
        _schema.update({"table": REG_TABLE, "icao_col": REG_ICAO_COL, "reg_col": REG_REG_COL,
                        "type_col": REG_TYPE_COL, "source": "env"})
        _reg_log(f"[regdb] using env schema {REG_TABLE}({REG_ICAO_COL}, {REG_REG_COL}, {REG_TYPE_COL})")
        return REG_TABLE, REG_ICAO_COL, REG_REG_COL, REG_TYPE_COL
    cand_icao = ["ModeS", "ModeSCode", "Icao24", "ICAO24", "Icao", "ICAO", "Hex", "HEX", "Address", "ADDR"]
    cand_reg = ["Registration", "REGISTRATION", "Reg", "REG", "Tail", "TailNo", "TailNumber", "TailNum",
                "RegistrationMark", "RegMark"]
    cand_type = ["IcaoTypeCode", "ICAOTypeCode", "IcaoType", "ICAOType", "TypeCode", "AircraftType", "ACType", "Type"]
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        tables.sort(key=lambda n: (0 if n.lower() == "aircraft" else 1, n.lower()))
        for t in tables:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info(\"{t}\")").fetchall()]
            lower = {c.lower(): c for c in cols}
            icao = next((lower[c.lower()] for c in cand_icao if c.lower() in lower), None)
            reg = next((lower[c.lower()] for c in cand_reg if c.lower() in lower), None)
            if not reg:
                reg = next((c for c in cols if "reg" in c.lower() or "tail" in c.lower()), None)
            typ = next((lower[c.lower()] for c in cand_type if c.lower() in lower), None)
            if icao and (reg or typ):
                _schema.update({"table": t, "icao_col": icao, "reg_col": reg, "type_col": typ, "source": "auto"})
                _reg_log(f"[regdb] detected schema: table={t}, icao={icao}, reg={reg}, type={typ}")
                return t, icao, reg, typ
        _reg_log(f"[regdb] no registration table found (tables: {tables})")
    except Exception as e:
        _reg_log(f"[regdb] schema detection error: {e}")
    _reg_state["next_detect"] = time.time() + 60
    return None, None, None, None


def _meta_cache_put(key, reg, typ, ttl):
    if len(_meta_cache) > REG_CACHE_MAX:
        now = time.time()
        for k in [k for k, v in _meta_cache.items() if v[0] <= now]:
            del _meta_cache[k]
        if len(_meta_cache) > REG_CACHE_MAX:
            _meta_cache.clear()
    _meta_cache[key] = (time.time() + ttl, reg, typ)


def lookup_meta(icao24):
    """Return (registration, type) for a hex code using BaseStation.sqb (cached)."""
    if not icao24:
        return None, None
    key = str(icao24).strip().upper()
    if len(key) != 6:
        return None, None
    now = time.time()
    if now >= _reg_state["next_check"]:
        # look at the database files every 30 s even when everything comes from the cache,
        # so a daily update (file changed) clears the cache
        _reg_state["next_check"] = now + 30
        with _reg_lock:
            _reg_connect()
    hit = _meta_cache.get(key)
    if hit and hit[0] > now:
        return hit[1], hit[2]
    reg = typ = None
    ttl = REG_MISS_TTL
    try:
        with _reg_lock:
            conn = _reg_connect()
            t, icao_col, reg_col, type_col = _detect_schema(conn)
            if conn is not None and t:
                sel = ", ".join([f'"{reg_col}"' if reg_col else "NULL", f'"{type_col}"' if type_col else "NULL"])
                sql = f'SELECT {sel} FROM "{t}" WHERE "{icao_col}" = ? LIMIT 1'
                row = conn.execute(sql, (key,)).fetchone() or conn.execute(sql, (key.lower(),)).fetchone()
                if row:
                    reg = (str(row[0]).strip() or None) if row[0] else None
                    typ = (str(row[1]).strip() or None) if row[1] else None
            if reg is None or typ is None:
                r_reg, r_typ = _ref_lookup(key)
                reg = reg or r_reg
                typ = typ or r_typ
            if conn is None and _ref_db.conn is None:
                ttl = 60   # neither database available right now: try again soon
            elif reg or typ:
                ttl = REG_HIT_TTL
    except Exception as e:
        _reg_log(f"[regdb] lookup failed: {e}", "lookup_err")
        ttl = 60
    _meta_cache_put(key, reg, typ, ttl)
    return reg, typ


def lookup_registration(icao24):
    return lookup_meta(icao24)[0]


def _enrich(objs):
    """Fill missing reg/type from BaseStation.sqb (feed values always win)."""
    try:
        for obj in objs:
            hexcode = str(obj.get("hex") or obj.get("icao24") or "").strip().upper()
            if hexcode and len(hexcode) == 6:
                reg, typ = lookup_meta(hexcode)
                if reg and not obj.get("reg"):
                    obj["reg"] = reg
                if typ and not obj.get("type"):
                    obj["type"] = typ
    except Exception as e:
        print(f"[enrich] failed: {e}", flush=True)
    return objs


# Debug pages are off unless DEBUG_API=1 is set in the environment.
@app.before_request
def _guard_debug_api():
    if request.path.startswith("/api/debug/") and not config.DEBUG_API:
        abort(404)


@app.route("/api/debug/reg")
@app.route("/api/debug/type")
def api_debug_reg():
    hexcode = (request.args.get('hex') or request.args.get('icao24') or "").strip().upper()
    with _reg_lock:
        conn = _reg_connect()
        t, icao_col, reg_col, type_col = _detect_schema(conn)
    reg, typ = lookup_meta(hexcode) if hexcode else (None, None)
    return jsonify({
        "version": APP_VERSION, "hex": hexcode, "reg": reg, "type": typ,
        "db_path": REG_DB_PATH, "db_exists": os.path.exists(REG_DB_PATH), "db_open": conn is not None,
        "ref_db_path": REF_DB_PATH, "ref_db_open": _ref_db.conn is not None,
        "table": t, "icao_col": icao_col, "reg_col": reg_col, "type_col": type_col,
        "schema_source": _schema.get("source"), "cache_entries": len(_meta_cache),
    })


@app.route("/api/debug/schema")
def api_debug_schema():
    try:
        with _reg_lock:
            conn = _reg_connect()
            if conn is None:
                return jsonify({"db_path": REG_DB_PATH, "error": "database not available"}), 500
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            info = {t: [r[1] for r in conn.execute(f"PRAGMA table_info(\"{t}\")").fetchall()] for t in tables}
            t, icao_col, reg_col, type_col = _detect_schema(conn)
        return jsonify({"db_path": REG_DB_PATH, "tables": info,
                        "detected": {"table": t, "icao_col": icao_col, "reg_col": reg_col, "type_col": type_col,
                                     "source": _schema.get("source")}})
    except Exception as e:
        return jsonify({"db_path": REG_DB_PATH, "error": str(e)}), 500
# --- /Registration lookup ---

def _parse_colon_feed(text):
    # 0 ICAO24 | 2 Callsign | 7 Squawk | 8 Lat | 9 Lon | 12 FL | 13 ALT (Axxx) | 19 VR | 22 HDG | 27 SPEED
    out = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw or raw.startswith('#'):
            continue
        parts = raw.split(':')
        try:
            hexcode = parts[0].strip().upper() if len(parts) > 0 else ''
            callsign = parts[2].strip() if len(parts) > 2 else ''
            squawk = parts[7].strip() if len(parts) > 7 else ''
            lat_s = parts[8].strip() if len(parts) > 8 else ''
            lon_s = parts[9].strip() if len(parts) > 9 else ''
            fl_s  = parts[12].strip() if len(parts) > 12 else ''
            alt_s = parts[13].strip() if len(parts) > 13 else ''
            vr_s  = parts[19].strip() if len(parts) > 19 else ''
            hdg_s = parts[22].strip() if len(parts) > 22 else ''
            spd_s = parts[27].strip() if len(parts) > 27 else ''
            mcp_s = parts[32].strip() if len(parts) > 32 else ''
            lat = float(lat_s) if lat_s else None
            lon = float(lon_s) if lon_s else None
            alt_ft = None
            if alt_s:
                if alt_s.startswith('A') and alt_s[1:].isdigit():
                    alt_ft = int(alt_s[1:]) * 100
                else:
                    try: alt_ft = float(alt_s)
                    except: alt_ft = None
            if alt_ft is None and fl_s:
                try:
                    fl_val = float(fl_s)
                    alt_ft = (round(fl_val/10.0)*100.0) if fl_val >= 1000 else (fl_val*100.0)
                except Exception:
                    pass
            hdg = float(hdg_s) if hdg_s else None
            gs = float(spd_s) if spd_s else None
            vr = float(vr_s) if vr_s else None
            # MCP selected altitude (column 32) — feet or hundreds
            sel_ft = None
            sel_hundreds = None
            try:
                if mcp_s:
                    _val = float(mcp_s)
                    if _val >= 0:
                        if _val >= 1000:
                            sel_ft = _val
                            sel_hundreds = int(round(_val/100.0))
                        else:
                            sel_hundreds = int(round(_val))
                            sel_ft = sel_hundreds * 100.0
            except Exception:
                sel_ft = None
                sel_hundreds = None
            obj = {"hex": hexcode, "flight": callsign, "squawk": squawk, "lat": lat, "lon": lon, "reg": lookup_registration(hexcode),
                   "alt_baro": alt_ft, "track": hdg, "gs": gs, "baro_rate": vr, "sel_alt_ft": sel_ft, "sel_alt_hundreds": sel_hundreds}
            out.append(obj)
        except Exception:
            continue
    return out

def fetch_data():
    while True:
        try:
            new_data = None
            new_err = None

            raw = b""
            try:
                # Connect to TCP provider (JSON per connection)
                with socket.create_connection((config.TCP_HOST, config.TCP_PORT), timeout=6.0) as s:
                    # Read until EOF
                    chunks = []
                    while True:
                        chunk = s.recv(65536)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    raw = b"".join(chunks)
            except Exception as e:
                new_err = f"TCP read failed: {e}"
            if not raw and new_err is None:
                new_err = "Feed returned no data"

            if raw and new_err is None:
                try:
                    text = raw.decode("utf-8", errors="replace")
                except Exception as e:
                    text = ""
                    new_err = f"Decode failed: {e}"

                if text:
                    try:
                        data = json.loads(text)
                        is_json = True
                    except Exception as e:
                        data = text
                        is_json = False
                        new_err = f"Invalid JSON: {e}"

                    # Primary: new JSON feed as a top-level list of aircraft objects
                    if is_json and isinstance(data, list):
                        mapped = []
                        for obj in data:
                            if not isinstance(obj, dict):
                                continue
                            o = dict(obj)

                            # Normalize hex to upper-case
                            hexcode = str(o.get("hex") or o.get("icao24") or "").strip().upper()
                            if hexcode:
                                o["hex"] = hexcode

                            # Callsign (JSON: fli -> flight)
                            if "fli" in o and not (o.get("flight") or o.get("callsign") or o.get("ident")):
                                try:
                                    o["flight"] = str(o.get("fli")).strip()
                                except Exception:
                                    pass

                            # Altitude (JSON: alt in feet)
                            if "alt" in o and o.get("alt") is not None and not any(
                                k in o for k in ("alt_baro", "baro_altitude", "altitude", "alt_geom")
                            ):
                                try:
                                    alt_val = float(o.get("alt"))
                                except Exception:
                                    alt_val = o.get("alt")
                                o["alt_baro"] = alt_val
                                o["altitude"] = alt_val

                            # Ground speed (JSON: spd in kt)
                            if "spd" in o and o.get("spd") is not None and not any(
                                k in o for k in ("gs", "speed", "ground_speed")
                            ):
                                try:
                                    spd_val = float(o.get("spd"))
                                except Exception:
                                    spd_val = o.get("spd")
                                o["gs"] = spd_val
                                o["speed"] = spd_val

                            # Track / heading (JSON: trk in degrees)
                            if "trk" in o and o.get("trk") is not None and not any(
                                k in o for k in ("track", "heading", "true_heading")
                            ):
                                o["track"] = o.get("trk")

                            # Vertical rate (JSON: vrt in ft/min)
                            if "vrt" in o and o.get("vrt") is not None and not any(
                                k in o for k in ("baro_rate", "vert_rate", "vertical_rate")
                            ):
                                o["baro_rate"] = o.get("vrt")

                            # Squawk (JSON: squ)
                            if "squ" in o and o.get("squ") is not None and not any(
                                k in o for k in ("squawk", "sqk", "mode_a", "squawk_code")
                            ):
                                o["squawk"] = str(o.get("squ"))

                            # Type code (JSON: typ)
                            if "typ" in o and o.get("typ") and "type" not in o:
                                o["type"] = o.get("typ")

                            # Registration (JSON: reg)
                            if "reg" in o and o.get("reg"):
                                o["reg"] = o.get("reg")

                            # Selected altitude (JSON: alts in feet) -> sel_alt_ft + sel_alt_hundreds
                            if "alts" in o and o.get("alts") is not None:
                                try:
                                    v = float(o.get("alts"))
                                except Exception:
                                    v = None
                                if v is not None and v >= 0:
                                    o["sel_alt_ft"] = v
                                    sel_h = None
                                    if v >= 1000:
                                        sel_h = int(round(v / 100.0))
                                    elif v <= 600:
                                        sel_h = int(round(v))
                                    if sel_h is not None:
                                        o["sel_alt_hundreds"] = sel_h

                            mapped.append(o)

                        filtered = [x for x in mapped if _within_range(x)]

                        _enrich(filtered)

                        new_data = {"now": time.time(), "aircraft": filtered}
                        new_err = None

                    # Legacy or fallback formats (dict or string) — reuse old logic where useful
                    elif is_json and isinstance(data, dict):
                        ac = data.get("aircraft", data.get("planes", data.get("ac", [])))
                        if isinstance(ac, list):
                            filtered = [x for x in ac if _within_range(x)]
                            _enrich(filtered)
                            new_data = {"now": data.get("now", time.time()), "aircraft": filtered}
                            new_err = None
                        else:
                            new_err = "No aircraft list in JSON"
                    else:
                        # Treat as colon feed using legacy parser
                        ac = _parse_colon_feed(data if isinstance(data, str) else "")
                        filtered = [x for x in ac if _within_range(x)]
                        _enrich(filtered)
                        new_data = {"now": time.time(), "aircraft": filtered}
                        new_err = None

            # Only update cache if we actually got new_data.
            # On transient errors we keep previous targets and just update error info.
            if new_data is not None:
                _ehs.set_feed(new_data.get("aircraft") or [])
                _cache["data"] = new_data
                _cache["err"] = new_err
                _cache["ok_ts"] = time.time()
            else:
                if new_err:
                    _cache["err"] = new_err

        except Exception as e:
            _cache["err"] = str(e)

        if _cache["err"] and _cache["err"] != _cache.get("_logged_err"):
            print(f"[feed] {_cache['err']}", flush=True)
        if not _cache["err"] and _cache.get("_logged_err"):
            print("[feed] recovered", flush=True)
        _cache["_logged_err"] = _cache["err"]
        _cache["ts"] = time.time()
        time.sleep(max(1, config.POLL_SECONDS))

# Comm-B / EHS values for the TopSky extended label (ehs.py)
_ehs = ehs.EhsReceiver(config.BEAST_HOST, config.BEAST_PORT, config.MAG_DECLINATION)
_ehs.start()

threading.Thread(target=fetch_data, daemon=True).start()

# --- OurAirports loader: headered or headerless ---
_navaids_cache = {"airports": [], "navaids": [], "fixes": []}
_navaids_counts = {"airports": 0, "navaids": 0, "fixes": 0}
_navaids_sources = {"airports": None, "navaids": None, "fixes": None}

def _read_rows_any(path):
    rows = []
    try:
        with open(path, newline='', encoding="utf-8-sig") as f:
            r = csv.reader(f)
            for row in r:
                rows.append(row)
    except Exception as e:
        print(f"[navaids] csv.reader failed for {path}: {e}", file=sys.stderr)
    return rows

def _index_from_header(header):
    idx = {"lat": None, "lon": None, "ident": None, "name": None, "type": None}
    if not header: return idx
    lower = [c.strip().lower() for c in header]
    for i, col in enumerate(lower):
        if "latitude" in col or col == "lat" or col == "y": idx["lat"] = i
        if "longitude" in col or col == "lon" or col == "x": idx["lon"] = i
        if col in ("ident","identifier","fix_ident","code"): idx["ident"] = i
        if col == "name": idx["name"] = i
        if col == "type" or col == "category": idx["type"] = i
    return idx

def _fallback_indices_for(fname):
    fn = (fname or "").lower()
    if "airport" in fn:
        return {"ident":1, "type":2, "name":3, "lat":4, "lon":5}
    if "navaid" in fn:
        return {"ident":2, "type":4, "name":3, "lat":6, "lon":7}
    return {"ident":1, "type":None, "name":2, "lat":-2, "lon":-1}

def _safe_float(s):
    try:
        return float(str(s).strip().strip('"'))
    except Exception:
        return None

def _guess_lat_lon(row):
    lat = lon = None
    for v in row:
        f = _safe_float(v)
        if f is None: continue
        if -90 <= f <= 90 and lat is None:
            lat = f; continue
        if -180 <= f <= 180 and lon is None:
            lon = f; continue
    return lat, lon

def _load_csv_norm(path, fname_hint=None):
    out = []
    rows = _read_rows_any(path)
    if not rows: return out
    header_candidate = rows[0]
    has_header = any(isinstance(c, str) and c and any(k in c.lower() for k in ("lat","lon","name","ident","type","longitude","latitude")) for c in header_candidate)
    start = 1 if has_header else 0
    idx = _index_from_header(header_candidate) if has_header else _fallback_indices_for(fname_hint or path)
    for row in rows[start:]:
        if not row or len(row) < 2: continue
        def get_idx(i):
            if i is None: return ""
            if i == -1: return row[-1] if len(row)>=1 else ""
            if i == -2: return row[-2] if len(row)>=2 else ""
            return row[i] if i < len(row) else ""
        lat = _safe_float(get_idx(idx.get("lat")))
        lon = _safe_float(get_idx(idx.get("lon")))
        if lat is None or lon is None:
            lat2, lon2 = _guess_lat_lon(row)
            lat = lat if lat is not None else lat2
            lon = lon if lon is not None else lon2
        if lat is None or lon is None: continue
        ident = str(get_idx(idx.get("ident")) or "").strip().strip('"')
        name  = str(get_idx(idx.get("name")) or ident).strip().strip('"')
        typ   = str(get_idx(idx.get("type")) or "").strip().strip('"').lower()
        out.append({"ident": ident, "name": name or ident, "type": typ, "lat": lat, "lon": lon})
    return out

def _resolve_data_file(fname):
    candidates = []
    here = os.path.dirname(__file__)
    env = (config.NAV_DATA_DIR or "").strip() or None
    for base in [here, os.getcwd()] + ([env] if env else []):
        if not base: continue
        p1 = os.path.join(base, "data", fname)
        p2 = os.path.join(base, fname)
        candidates.extend([p1, p2])
    for p in candidates:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    return None

def _load_navaids():
    files = {
        "airports": _resolve_data_file("airports.csv"),
        "navaids":  _resolve_data_file("navaids.csv"),
        "fixes":    _resolve_data_file("waypoints.csv"),
    }
    for key, path in files.items():
        rows = _load_csv_norm(path, fname_hint=os.path.basename(path) if path else None) if path else []
        _navaids_cache[key] = rows
        _navaids_counts[key] = len(rows)
        _navaids_sources[key] = path
        print(f"[navaids] {key}: {len(rows)} from {path or 'N/A'}", file=sys.stderr)

_load_navaids()

@app.route("/api/navaids")
def api_navaids():
    """Airports / navaids / waypoints within nmr NM of clat,clon (default: radar center).
    raw=1 returns everything (large: the airport file covers the whole world)."""
    if request.args.get('raw') == '1':
        return jsonify({k: _navaids_cache.get(k, []) for k in ["airports", "navaids", "fixes"]})
    try:
        nmr = max(1.0, min(2000.0, float(request.args.get('nmr', '100'))))
    except Exception:
        nmr = 100.0
    try:
        clat = float(request.args.get('clat')) if request.args.get('clat') is not None else config.CENTER_LAT
        clon = float(request.args.get('clon')) if request.args.get('clon') is not None else config.CENTER_LON
    except Exception:
        clat, clon = config.CENTER_LAT, config.CENTER_LON
    # Cheap bounding-box test first, exact distance only for the few rows inside it
    dlat = nmr / 60.0
    dlon = nmr / (60.0 * max(0.01, cos(radians(clat))))
    def within(r):
        lat, lon = r.get('lat'), r.get('lon')
        if lat is None or lon is None or abs(lat - clat) > dlat:
            return False
        if dlon < 180 and abs(((lon - clon + 540.0) % 360.0) - 180.0) > dlon:
            return False
        return _nm_distance(clat, clon, lat, lon) <= nmr
    return jsonify({k: [r for r in _navaids_cache.get(k, []) if within(r)] for k in ["airports", "navaids", "fixes"]})

@app.route("/api/navaids_meta")
def api_navaids_meta():
    return jsonify({"counts": _navaids_counts, "sources": _navaids_sources})

@app.route("/")
def index():
    return render_template("index.html",
                           center_lat=config.CENTER_LAT,
                           center_lon=config.CENTER_LON,
                           version=APP_VERSION,
                           asset_tag=ASSET_TAG)

@app.route("/api/aircraft")
def api_aircraft():
    now = time.time()
    feed_age = (now - _cache["ok_ts"]) if _cache["ok_ts"] else None
    out = dict(_cache["data"]) if _cache["data"] is not None else {"now": now, "aircraft": []}
    out["feed_age"] = round(feed_age, 1) if feed_age is not None else None
    out["version"] = APP_VERSION
    if _cache["err"]:
        out["error"] = _cache["err"]
    # Short outages keep the last picture; after FEED_STALE_SECONDS the old targets are dropped
    # so a dead feed is visible instead of showing frozen aircraft.
    if feed_age is None or feed_age > config.FEED_STALE_SECONDS:
        out["aircraft"] = []
        out["feed_lost"] = True
    return jsonify(out), 200


# --- METAR / TAF (same NOAA tgftp source and parsing as MODE-S Wind) ---
# One cache per airport, shared by all viewers: fetched only when someone asks (Auto QNH,
# the METAR & TAF window), at most every 10 minutes (2 minutes after a failure). On a
# failure the last good report is kept and the error is passed on.
WX_REFRESH_SEC = 600
WX_RETRY_SEC = 120
WX_MAX_STATIONS = 50
TAF_URL = os.environ.get("TAF_URL", "https://tgftp.nws.noaa.gov/data/forecasts/taf/stations/{icao}.TXT")
_wx = {}                       # ICAO -> entry
_wx_lock = threading.Lock()    # protects _wx; each entry has its own lock for the fetch


def _parse_qnh(metar_text):
    """QNH in hPa from a METAR: Q-group (Q1013) or A-group in inHg (A2992). None if missing."""
    m = re.search(r"\bQ(\d{3,4})\b", metar_text)
    if m:
        v = float(m.group(1))
    else:
        m = re.search(r"\bA(\d{4})\b", metar_text)
        if not m:
            return None
        v = round(float(m.group(1)) / 100.0 * 33.8639, 1)
    return v if 900 <= v <= 1100 else None


def _fetch_text(url):
    """A NOAA station file: line 1 is the date/time, the rest the report."""
    req = urllib.request.Request(url, headers={"User-Agent": f"adsb_radar/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read().decode("utf-8", errors="replace").strip()
    lines = raw.splitlines()
    return "\n".join(l.rstrip() for l in lines[1:]).strip() if len(lines) > 1 else raw


def _wx_fetch(e):
    icao, now, errs = e["icao"], time.time(), []
    for kind, url in (("metar", config.METAR_URL), ("taf", TAF_URL)):
        try:
            text = _fetch_text(url.format(icao=icao))
            if not text:
                raise ValueError("empty report")
            e[kind], e[kind + "_ok_ts"], e[kind + "_err"] = text, now, None
        except Exception as ex:
            msg = "not available" if "404" in str(ex) else str(ex)
            e[kind + "_err"] = msg
            errs.append(f"{kind.upper()} {msg}")
    # a network error: try again in 2 min; "not available" (no such report, e.g. no TAF): 10 min
    hard = any(e[k + "_err"] and e[k + "_err"] != "not available" for k in ("metar", "taf"))
    e["next_fetch"] = now + (WX_RETRY_SEC if hard else WX_REFRESH_SEC)
    msg = "; ".join(errs) or None
    if msg != e.get("_logged"):
        print(f"[wx] {icao}: {msg or 'OK again'}", flush=True)
    e["_logged"] = msg


def wx_get(icao):
    """METAR / TAF entry of one airport (fetched if older than the refresh time)."""
    icao = (icao or "").strip().upper()
    with _wx_lock:
        e = _wx.get(icao)
        if e is None:
            if len(_wx) >= WX_MAX_STATIONS:          # forget the least recently used
                del _wx[min(_wx, key=lambda k: _wx[k]["used"])]
            e = _wx[icao] = {"icao": icao, "metar": None, "taf": None, "metar_ok_ts": 0.0, "taf_ok_ts": 0.0,
                             "metar_err": None, "taf_err": None, "next_fetch": 0.0, "lock": threading.Lock()}
        e["used"] = time.time()
    with e["lock"]:
        if time.time() >= e["next_fetch"]:
            _wx_fetch(e)
        return dict(e)


def _obs_time(text):
    t = re.search(r"\b(\d{6})Z\b", text or "")
    return (t.group(1) + "Z") if t else None


@app.route("/api/qnh")
def api_qnh():
    e = wx_get(config.METAR_STATION)
    qnh = _parse_qnh(e["metar"]) if e["metar"] else None
    age = (time.time() - e["metar_ok_ts"]) if e["metar_ok_ts"] else None
    err = e["metar_err"] or (None if qnh is not None or not e["metar"] else "no QNH in METAR")
    return jsonify({"station": e["icao"], "qnh": qnh, "obs_time": _obs_time(e["metar"]),
                    "metar": e["metar"], "age_sec": round(age) if age is not None else None, "error": err})


@app.route("/api/wx")
def api_wx():
    """METAR and TAF of one airport for the METAR & TAF window (?icao=EFHK)."""
    icao = (request.args.get("icao") or config.METAR_STATION).strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]{3}", icao):
        return jsonify({"icao": icao, "error": "ICAO code must be 4 letters/digits, e.g. EFHK"}), 400
    e = wx_get(icao)
    now = time.time()
    age = lambda ts: round(now - ts) if ts else None
    return jsonify({"icao": icao, "metar": e["metar"], "taf": e["taf"],
                    "metar_time": _obs_time(e["metar"]), "taf_time": _obs_time(e["taf"]),
                    "metar_age": age(e["metar_ok_ts"]), "taf_age": age(e["taf_ok_ts"]),
                    "metar_error": e["metar_err"], "taf_error": e["taf_err"]})


# --- What's new (doc/whats_new.md) ---
# "## v.DDMMYYYY — title" starts a version; the lines under it (bullets / paragraphs) are
# sent as they are and rendered in the browser. Read again only when the file changes.
WHATS_NEW_PATH = os.path.join(os.path.dirname(BASE_DIR), "doc", "whats_new.md")
_whats_new = {"mtime": None, "entries": []}


def _whats_new_entries():
    try:
        mt = os.path.getmtime(WHATS_NEW_PATH)
    except OSError:
        return []
    if mt != _whats_new["mtime"]:
        out, cur = [], None
        try:
            with open(WHATS_NEW_PATH, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            lines = []
        for line in lines:
            m = re.match(r"^##\s+(v\.\d{8})\s*(?:[\u2014-]\s*(.*))?$", line.strip())
            if m:
                cur = {"version": m.group(1), "title": (m.group(2) or "").strip(), "lines": []}
                out.append(cur)
            elif cur is not None:
                cur["lines"].append(line.rstrip())
        for e in out:
            while e["lines"] and not e["lines"][-1].strip():
                e["lines"].pop()
            while e["lines"] and not e["lines"][0].strip():
                e["lines"].pop(0)
            d = e["version"][2:]
            e["date"] = f"{d[4:]}-{d[2:4]}-{d[:2]}"
        out.sort(key=lambda e: e["date"], reverse=True)       # newest first, whatever the file order
        _whats_new.update({"mtime": mt, "entries": out})
    return _whats_new["entries"]


@app.route("/api/whatsnew")
def api_whatsnew():
    return jsonify({"version": APP_VERSION, "entries": _whats_new_entries()[:10]})


@app.route("/api/ac/<icao>")
def api_ac(icao):
    """Comm-B / EHS values of one aircraft for the TopSky extended label (polled every 2 s
    while the mouse is on it or it is selected)."""
    return jsonify(_ehs.get(icao))


@app.route("/api/ehs_status")
def api_ehs_status():
    return jsonify(_ehs.status())


# Register overlays endpoints
register_overlays(app, config.CENTER_LAT, config.CENTER_LON, os.path.join(BASE_DIR, 'data', 'overlays'), exclude_names={'efhk_coast_demo','efhk_ils_demo','Navaids','efhk_nav'})
if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=False)
