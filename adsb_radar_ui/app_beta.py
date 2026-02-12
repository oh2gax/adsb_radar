
import os, time, threading, csv, sys, json, socket
from flask import Flask, jsonify, render_template, request
from overlays import register_overlays
import requests
import sqlite3
import threading
import config

app = Flask(__name__, static_url_path="/static")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_VERSION = "RADAR v9.0.0_Beta"

_cache = {"ts": 0, "data": None, "err": None}

def _nm_distance(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, atan2, sqrt
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    c = 2 * atan2(sqrt(1-a), sqrt(a))
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

# --- Registration lookup (smart schema + env overrides + logging) ---
REG_DB_PATH = os.environ.get("REG_DB_PATH", os.path.join(BASE_DIR, "data", "BaseStation.sqb"))
REG_TABLE   = os.environ.get("REG_TABLE")      # optional override
REG_ICAO_COL= os.environ.get("REG_ICAO_COL")   # optional override
REG_REG_COL = os.environ.get("REG_REG_COL")    # optional override

_reg_conn = None
_reg_lock = threading.Lock()
_reg_cache = {}
_schema = {"table": None, "icao_col": None, "reg_col": None, "source": None}

def _reg_connect():
    global _reg_conn
    if _reg_conn is None:
        try:
            _reg_conn = sqlite3.connect(f"file:{REG_DB_PATH}?mode=ro", uri=True, check_same_thread=False)
        except Exception:
            _reg_conn = sqlite3.connect(REG_DB_PATH, check_same_thread=False)
    return _reg_conn

def _detect_schema():
    if _schema["table"] and _schema["icao_col"] and _schema["reg_col"]:
        return _schema["table"], _schema["icao_col"], _schema["reg_col"]
    if REG_TABLE and REG_ICAO_COL and REG_REG_COL:
        _schema.update({"table": REG_TABLE, "icao_col": REG_ICAO_COL, "reg_col": REG_REG_COL, "source": "env"})
        print(f"[regdb] Using env schema REG_TABLE={REG_TABLE}, REG_ICAO_COL={REG_ICAO_COL}, REG_REG_COL={REG_REG_COL}")
        return REG_TABLE, REG_ICAO_COL, REG_REG_COL
    cand_icao = ["ModeS","ModeSCode","Icao24","ICAO24","Icao","ICAO","Hex","HEX","Address","ADDR"]
    cand_reg  = ["Registration","REGISTRATION","Reg","REG","Tail","TailNo","TailNumber","TailNum","RegistrationMark","RegMark"]
    try:
        conn = _reg_connect()
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"[regdb] sqlite tables: {tables}")
        tables_sorted = sorted(tables, key=lambda n: (0 if n.lower()=="aircraft" else 1, n.lower()))
        for t in tables_sorted:
            try:
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info('{t}')").fetchall()]
                print(f"[regdb] table {t} columns: {cols}")
                icao = None; reg = None
                for c in cols:
                    if c in cand_icao and not icao: icao = c
                    if c in cand_reg  and not reg:  reg = c
                if not icao:
                    for c in cols:
                        lc = c.lower()
                        if lc in [x.lower() for x in cand_icao] or lc in ("modes","icao","hex","address"):
                            icao = c; break
                if not reg:
                    for c in cols:
                        lc = c.lower()
                        if lc in [x.lower() for x in cand_reg] or "reg" in lc or "tail" in lc:
                            reg = c; break
                if icao and reg:
                    _schema.update({"table": t, "icao_col": icao, "reg_col": reg, "source": "auto"})
                    print(f"[regdb] detected schema: table={t}, icao_col={icao}, reg_col={reg}")
                    return t, icao, reg
            except Exception as e:
                print(f"[regdb] inspect table {t} failed: {e}")
                continue
        print("[regdb] schema detection failed")
    except Exception as e:
        print(f"[regdb] schema detection error: {e}")
    return None, None, None

def lookup_registration(icao24: str):
    if not icao24:
        return None
    key = icao24.strip().upper()
    if len(key) != 6:
        return None
    if key in _reg_cache:
        return _reg_cache[key]
    reg = None
    try:
        with _reg_lock:
            conn = _reg_connect()
            t, icao_col, reg_col = _detect_schema()
            if not t or not icao_col or not reg_col:
                raise Exception("registration table/columns not found")
            sql = f"SELECT {reg_col} FROM {t} WHERE UPPER({icao_col}) = ? LIMIT 1"
            cur = conn.execute(sql, (key,))
            row = cur.fetchone()
            reg = (row[0].strip() if row and row[0] else None)
    except Exception as e:
        print(f"[regdb] lookup failed for {key}: {e}")
        reg = None
    _reg_cache[key] = reg
    return reg

_meta_cache = {}

def _detect_type_col_for_table(table_name: str):
    """
    Best-effort detection of the ICAO type column in the given table.
    Prefers 'IcaoTypeCode', then similar variants.
    """
    try:
        conn = _reg_connect()
        cur = conn.execute(f"PRAGMA table_info('{table_name}')")
        cols = [r[1] for r in cur.fetchall()]
        preferred = ["IcaoTypeCode", "ICAOTypeCode", "icaoTypeCode", "IcaoType", "ICAOType", "TypeCode", "AircraftType", "ACType", "Type"]
        lower = {c.lower(): c for c in cols}
        for name in preferred:
            if name.lower() in lower:
                return lower[name.lower()]
        return None
    except Exception as e:
        print(f"[regdb] type-col detect failed: {e}")
        return None

def lookup_meta(icao24: str):
    """
    Return (registration, type) for a hex code, using BaseStation.sqb.
    Caches results in-memory.
    """
    if not icao24:
        return None, None
    key = icao24.strip().upper()
    if len(key) != 6:
        return None, None
    if key in _meta_cache:
        return _meta_cache[key]

    reg = None
    typ = None
    try:
        with _reg_lock:
            conn = _reg_connect()
            t, icao_col, reg_col = _detect_schema()
            if not t or not icao_col:
                raise Exception("registration table/columns not found")
            type_col = _detect_type_col_for_table(t)
            if reg_col and type_col:
                sql = f"SELECT {reg_col}, {type_col} FROM {t} WHERE UPPER({icao_col}) = ? LIMIT 1"
                row = conn.execute(sql, (key,)).fetchone()
                if row:
                    reg = (row[0].strip() if row[0] else None)
                    typ = (row[1].strip() if row[1] else None)
            elif reg_col:
                sql = f"SELECT {reg_col} FROM {t} WHERE UPPER({icao_col}) = ? LIMIT 1"
                row = conn.execute(sql, (key,)).fetchone()
                if row:
                    reg = (row[0].strip() if row[0] else None)
            else:
                type_col = _detect_type_col_for_table(t)
                if type_col:
                    sql = f"SELECT {type_col} FROM {t} WHERE UPPER({icao_col}) = ? LIMIT 1"
                    row = conn.execute(sql, (key,)).fetchone()
                    if row:
                        typ = (row[0].strip() if row[0] else None)
    except Exception as e:
        print(f"[regdb] meta lookup failed for {key}: {e}")

    _meta_cache[key] = (reg, typ)
    return reg, typ

@app.route("/api/debug/type")
def api_debug_type():
    hexcode = (request.args.get('hex') or request.args.get('icao24') or "").strip().upper()
    exists = os.path.exists(REG_DB_PATH)
    t, icao_col, reg_col = _detect_schema()
    type_col = _detect_type_col_for_table(t) if t else None
    reg, typ = (None, None)
    err = None
    try:
        reg, typ = lookup_meta(hexcode)
    except Exception as e:
        err = str(e)
    return jsonify({
        "ok": True,
        "hex": hexcode,
        "db_path": REG_DB_PATH,
        "exists": exists,
        "table": t,
        "icao_col": icao_col,
        "reg_col": reg_col,
        "type_col": type_col,
        "registration": reg,
        "type": typ,
        "error": err
    }), 200


@app.route("/api/debug/schema")
def api_debug_schema():
    try:
        conn = _reg_connect()
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        info = {}
        for t in tables:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info('{t}')").fetchall()]
            info[t] = cols
        t, icao_col, reg_col = _detect_schema()
        return jsonify({"db_path": REG_DB_PATH, "tables": info, "detected": {"table": t, "icao_col": icao_col, "reg_col": reg_col, "source": _schema.get("source")}})
    except Exception as e:
        return jsonify({"db_path": REG_DB_PATH, "error": str(e)}), 500

@app.route("/api/debug/reg")
def api_debug_reg():
    hexcode = (request.args.get('hex') or request.args.get('icao24') or "").strip().upper()
    exists = os.path.exists(REG_DB_PATH)
    t, icao_col, reg_col = _detect_schema()
    reg = None
    err = None
    try:
        reg = lookup_registration(hexcode) if hexcode else None
    except Exception as e:
        err = str(e)
    return jsonify({
        "version": APP_VERSION,
        "hex": hexcode,
        "reg": reg,
        "db_path": REG_DB_PATH,
        "db_exists": exists,
        "table": t,
        "icao_col": icao_col,
        "reg_col": reg_col,
        "schema_source": _schema.get("source"),
        "error": err
    })
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

                        # Enrich reg + type from BaseStation.sqb (fallback only)
                        try:
                            for obj in filtered:
                                hexcode = (str(obj.get("hex") or obj.get("icao24") or "")).strip().upper()
                                if hexcode and len(hexcode) == 6:
                                    reg, typ = lookup_meta(hexcode)
                                    if reg and ("reg" not in obj or not obj.get("reg")):
                                        obj["reg"] = reg
                                    if typ and ("type" not in obj or not obj.get("type")):
                                        obj["type"] = typ
                        except Exception as _e:
                            print(f"[enrich] failed: {_e}")

                        new_data = {"now": time.time(), "aircraft": filtered}
                        new_err = None

                    # Legacy or fallback formats (dict or string) — reuse old logic where useful
                    elif is_json and isinstance(data, dict):
                        ac = data.get("aircraft", data.get("planes", data.get("ac", [])))
                        if isinstance(ac, list):
                            filtered = [x for x in ac if _within_range(x)]
                            try:
                                for obj in filtered:
                                    hexcode = (str(obj.get("hex") or obj.get("icao24") or "")).strip().upper()
                                    if hexcode and len(hexcode) == 6:
                                        reg, typ = lookup_meta(hexcode)
                                        if reg and ("reg" not in obj or not obj.get("reg")):
                                            obj["reg"] = reg
                                        if typ and ("type" not in obj or not obj.get("type")):
                                            obj["type"] = typ
                            except Exception as _e:
                                print(f"[enrich] failed: {_e}")
                            new_data = {"now": data.get("now", time.time()), "aircraft": filtered}
                            new_err = None
                        else:
                            new_err = "No aircraft list in JSON"
                    else:
                        # Treat as colon feed using legacy parser
                        ac = _parse_colon_feed(data if isinstance(data, str) else "")
                        filtered = [x for x in ac if _within_range(x)]
                        try:
                            for obj in filtered:
                                hexcode = (str(obj.get("hex") or obj.get("icao24") or "")).strip().upper()
                                if hexcode and len(hexcode) == 6:
                                    reg, typ = lookup_meta(hexcode)
                                    if reg and ("reg" not in obj or not obj.get("reg")):
                                        obj["reg"] = reg
                                    if typ and ("type" not in obj or not obj.get("type")):
                                        obj["type"] = typ
                        except Exception as _e:
                            print(f"[enrich] failed: {_e}")
                        new_data = {"now": time.time(), "aircraft": filtered}
                        new_err = None

            # Only update cache if we actually got new_data.
            # On transient errors we keep previous targets and just update error info.
            if new_data is not None:
                _cache["data"] = new_data
                _cache["err"] = new_err
            else:
                if new_err:
                    _cache["err"] = new_err

        except Exception as e:
            _cache["err"] = str(e)

        _cache["ts"] = time.time()
        time.sleep(max(1, config.POLL_SECONDS))

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
    raw = request.args.get('raw') == '1'
    nmr = float(request.args.get('nmr', '500'))
    try:
        clat = float(request.args.get('clat')) if request.args.get('clat') is not None else config.CENTER_LAT
        clon = float(request.args.get('clon')) if request.args.get('clon') is not None else config.CENTER_LON
    except Exception:
        clat, clon = config.CENTER_LAT, config.CENTER_LON
    def within(lat, lon):
        try:
            lat = float(lat); lon = float(lon)
            return _nm_distance(clat, clon, lat, lon) <= nmr
        except Exception:
            return False
    if raw:
        return jsonify({k: _navaids_cache.get(k, []) for k in ["airports","navaids","fixes"]})
    out = {k: [r for r in _navaids_cache.get(k, []) if within(r.get('lat'), r.get('lon'))] for k in ["airports","navaids","fixes"]}
    return jsonify(out)

@app.route("/api/navaids_meta")
def api_navaids_meta():
    return jsonify({"counts": _navaids_counts, "sources": _navaids_sources})

@app.route("/")
def index():
    return render_template("index.html",
                           center_lat=config.CENTER_LAT,
                           center_lon=config.CENTER_LON,
                           version=APP_VERSION)

@app.route("/api/aircraft")
def api_aircraft():
    if _cache["data"] is None:
        return jsonify({"now": time.time(), "aircraft": [], "error": _cache["err"]}), 200
    out = dict(_cache["data"])
    if _cache["err"]:
        out["error"] = _cache["err"]
    return jsonify(out), 200


# Register overlays endpoints
register_overlays(app, config.CENTER_LAT, config.CENTER_LON, os.path.join(BASE_DIR, 'data', 'overlays'), exclude_names={'efhk_coast_demo','efhk_ils_demo','Navaids','efhk_nav'})
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, debug=False)
