"""airact.py - which airspace areas are active: the firing / activation NOTAMs and the daily Airspace Use Plan.

Sources (AIS Finland, open):
  - NAV WRNG bulletin of the Helsinki FIR  https://www.ais.fi/bulletins/wrng.htm  (the NOTAMs that activate
    restricted and danger areas, temporary danger areas; updated a few times a day). An activation is a NOTAM
    with an area designator (EFR92A, EFD190E, EFTSA..) and ACT; its FROM / TO and SCHEDULE give the windows.
    A temporary area with PSN ... RADIUS ... gets its own circle.
  - AUP / UUP  https://www.ais.fi/aup/index.html  (PDF, valid 0600-0600 UTC; a UUP replaces the AUP of the
    same day): the "AMC Manageable Areas" (TSA / TRA and some R / D areas) with levels and times. The flight
    plan buffer zones (name + Z, R, S, T) are left out.

The result of every check that differs from the one before is kept (data/airact/airact.db, not in git,
AIRACT_KEEP_DAYS = 31), so a replay shows the areas that were active then: active_at(t).

Run by hand: python3 airact.py [--status]
"""
import hashlib, io, json, math, os, re, sqlite3, sys, threading, time, urllib.request
from calendar import timegm
from datetime import datetime, timedelta, timezone
from html import unescape

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIR = os.environ.get("AIRACT_DIR", os.path.join(BASE_DIR, "data", "airact"))
DB = os.path.join(DIR, "airact.db")
WRNG_URL = "https://www.ais.fi/bulletins/wrng.htm"
AUP_INDEX = "https://www.ais.fi/aup/index.html"
AUP_BASE = "https://www.ais.fi"
KEEP_DAYS = float(os.environ.get("AIRACT_KEEP_DAYS", "31"))
TIMEOUT = 60
UA = "adsb_radar (+https://radar.oh2gax.org)"
MON = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}
WDAY = {d: i for i, d in enumerate("MON TUE WED THU FRI SAT SUN".split())}
AREA_RE = re.compile(r"\b(EF[PRD]\d{2,4}[A-Z]{0,2}|EFTSA[A-Z0-9]+|EFTRA[A-Z0-9]+|EUCBA\d+[A-Z]?)\b")
_lock = threading.Lock()


def _get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        b = r.read()
    return b if binary else b.decode("latin-1" if "bulletins" in url else "utf-8", "replace")


def _text(html):
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", unescape(t).replace("\xa0", " ")).strip()


def _t(s):
    """'03NOV26 0700' -> epoch (UTC); PERM -> far ahead."""
    s = s.strip()
    if s.startswith("PERM"):
        return 4102444800                                         # 2100-01-01
    m = re.match(r"(\d{2})([A-Z]{3})(\d{2}) ?(\d{2})(\d{2})", s)
    if not m or m.group(2) not in MON:
        return None
    return timegm((2000 + int(m.group(3)), MON[m.group(2)], int(m.group(1)), int(m.group(4)), int(m.group(5)), 0))


def short_alt(s):
    """'5000FT AMSL' -> '5000', 'FL310' -> 'FL310', 'SFC' -> 'SFC', '150M AGL' -> '150M AGL'."""
    s = (s or "").upper().strip()
    m = re.match(r"FL ?(\d+)", s)
    if m:
        return "FL" + m.group(1).zfill(3)
    m = re.match(r"(\d+) ?FT (?:A?MSL)", s)
    if m:
        return m.group(1)
    m = re.match(r"(\d+) ?FT AGL", s)
    if m:
        return m.group(1) + " AGL"
    return s.replace("GND", "SFC")


def alt_ft(s):
    """'FL310' -> 31000, '5000' -> 5000, 'SFC' -> 0, '150M AGL' -> 492 (for comparing upper limits)."""
    s = (s or "").upper()
    m = re.match(r"FL(\d+)", s)
    if m:
        return int(m.group(1)) * 100
    m = re.match(r"(\d+)(M)?", s)
    if m:
        return int(int(m.group(1)) * (3.281 if m.group(2) else 1))
    return 99999 if "UNL" in s else 0


# ---------------------------------------------------------------- the schedule of a NOTAM
def _times(seg):
    """'0600-1500 1700-1800' -> [(360, 900), (1020, 1080)] minutes; H24 -> whole day."""
    if re.search(r"\bH24\b", seg):
        return [(0, 1440)]
    return [(int(a[:2]) * 60 + int(a[2:]), int(b[:2]) * 60 + int(b[2:])) for a, b in re.findall(r"\b(\d{4})-(\d{4})\b", seg)]


def _day_rule(spec, t_from):
    """The day part of a schedule segment -> a test day(date) -> bool; None = not understood."""
    spec = re.sub(r"\s*-\s*", "-", spec.strip())
    if not spec or spec in ("DAILY", "DLY"):
        return lambda d: True
    # weekdays: MON-FRI, MON TUE THU, SAT-SUN
    if re.fullmatch(r"(?:(?:MON|TUE|WED|THU|FRI|SAT|SUN)(?:-(?:MON|TUE|WED|THU|FRI|SAT|SUN))?\s*)+", spec):
        days = set()
        for a, b in re.findall(r"(MON|TUE|WED|THU|FRI|SAT|SUN)(?:-(MON|TUE|WED|THU|FRI|SAT|SUN))?", spec):
            i, j = WDAY[a], WDAY[b or a]
            k = i
            while True:
                days.add(k)
                if k == j:
                    break
                k = (k + 1) % 7
        return lambda d: d.weekday() in days
    # dates: 04, 05-06, OCT 29, OCT 30-NOV 11, 29 30 31
    y0 = datetime.fromtimestamp(t_from, timezone.utc).year
    ranges, mon = [], None
    for tok in re.findall(r"[A-Z]{3}\s*\d{1,2}(?:-(?:[A-Z]{3}\s*)?\d{1,2})?|\d{1,2}(?:-(?:[A-Z]{3}\s*)?\d{1,2})?", spec):
        m = re.fullmatch(r"(?:([A-Z]{3})\s*)?(\d{1,2})(?:-(?:([A-Z]{3})\s*)?(\d{1,2}))?", tok.strip())
        if not m or (m.group(1) and m.group(1) not in MON) or (m.group(3) and m.group(3) not in MON):
            return None
        mon = MON[m.group(1)] if m.group(1) else mon
        a = (mon, int(m.group(2)))
        mon2 = MON[m.group(3)] if m.group(3) else mon
        b = (mon2, int(m.group(4))) if m.group(4) else a
        ranges.append((a, b))
        mon = mon2
    if not ranges or re.sub(r"[A-Z]{3}|\d|-|\s", "", spec):
        return None

    def test(d):
        for (ma, da), (mb, db) in ranges:
            if ma is None:                                   # bare day numbers: any month
                if da <= d.day <= db if da <= db else (d.day >= da or d.day <= db):
                    return True
            else:
                lo, hi = (ma, da), (mb or ma, db)
                cur = (d.month, d.day)
                if (lo <= cur <= hi) if lo <= hi else (cur >= lo or cur <= hi):
                    return True
        return False
    return test


def windows(t_from, t_to, sched):
    """Activation windows [(t0, t1)] in [t_from, t_to]; without a schedule (or one not understood) the
    whole span. Returns (windows, understood)."""
    if t_from is None or t_to is None or t_to <= t_from:
        return [], True
    if not sched:
        return [(t_from, t_to)], True
    s = sched.upper().strip().rstrip(".")
    exc = None
    m = re.search(r"\bEXC\b(.*)$", s)
    if m:
        exc = _day_rule(m.group(1).strip(), t_from)
        s = s[:m.start()].strip()
    rules = []
    for seg in [x.strip() for x in s.split(",") if x.strip()]:
        tm = _times(seg)
        if not tm:
            return [(t_from, t_to)], False
        spec = re.sub(r"\b\d{4}-\d{4}\b|\bH24\b", " ", seg).strip()
        rule = _day_rule(spec, t_from)
        if rule is None:
            return [(t_from, t_to)], False
        if rules and not spec and rules[-1][0] is not None:   # "MON-FRI 0600-0800 1000-1200" split by commas
            rule = rules[-1][0]
        rules.append((rule, tm))
    out = []
    d = datetime.fromtimestamp(t_from, timezone.utc).date() - timedelta(days=1)
    end = datetime.fromtimestamp(t_to, timezone.utc).date()
    while d <= end:
        if not (exc and exc(d)):
            base = timegm((d.year, d.month, d.day, 0, 0, 0))
            for rule, tm in rules:
                if rule(d):
                    for a, b in tm:
                        t0, t1 = base + a * 60, base + (b if b > a else b + 1440) * 60
                        t0, t1 = max(t0, t_from), min(t1, t_to)
                        if t1 > t0:
                            out.append((t0, t1))
        d += timedelta(days=1)
    return sorted(set(out)), True


# ---------------------------------------------------------------- sources
def parse_wrng(html):
    """The activations of the NAV WRNG bulletin: [{ids, lo, up, t0, t1, ref, sched, ok, text, circle}]."""
    i = html.find("NAV WARNINGS")
    body = html[i:] if i >= 0 else html
    out = []
    for blk in re.split(r"<table\b", body)[1:]:
        t = _text("<table " + blk)
        t = re.sub(r"^\+\s*", "", t)
        if "FROM:" not in t:
            continue
        head = t.split("LOWER:")[0] if "LOWER:" in t else t.split("FROM:")[0]
        ids = list(dict.fromkeys(AREA_RE.findall(head)))
        if not ids or not re.search(r"\bACT\b", head) or re.search(r"\bTRIGGER NOTAM\b|WILL BE ISSUED TO ACTIVATE", head):
            continue
        lo = re.search(r"LOWER:\s*(.+?)\s+UPPER:", t)
        up = re.search(r"UPPER:\s*(.+?)\s+FROM:", t)
        fr = re.search(r"FROM:\s*(\d{2}[A-Z]{3}\d{2} \d{4})", t)
        to = re.search(r"\bTO:\s*(\d{2}[A-Z]{3}\d{2} \d{4}|PERM)", t)
        ref = re.search(r"\(([A-Z]\d{4}/\d{2})\)", t)
        sc = re.search(r"SCHEDULE:\s*(.+)$", t)
        t0, t1 = _t(fr.group(1)) if fr else None, _t(to.group(1)) if to else None
        win, ok = windows(t0, t1, sc.group(1).strip() if sc else "")
        circle = None
        pm = re.search(r"PSN\s*(\d{6})N\s*(\d{7})E[ ,]*RADIUS\s*(\d+(?:\.\d+)?)\s*(KM|NM|M)\b", head)
        if pm:
            la = int(pm.group(1)[:2]) + int(pm.group(1)[2:4]) / 60 + int(pm.group(1)[4:]) / 3600
            lo_ = int(pm.group(2)[:3]) + int(pm.group(2)[3:5]) / 60 + int(pm.group(2)[5:]) / 3600
            r = float(pm.group(3)) * {"KM": 1 / 1.852, "NM": 1.0, "M": 1 / 1852}[pm.group(4)]
            circle = [round(la, 5), round(lo_, 5), round(r, 3)]
        out.append({"ids": ids, "lo": short_alt(lo.group(1)) if lo else "", "up": short_alt(up.group(1)) if up else "",
                    "win": win, "ok": ok, "ref": ref.group(1) if ref else "", "sched": sc.group(1).strip()[:120] if sc else "",
                    "text": head[:160], "circle": circle})
    return out


def aup_files(index_html):
    """The AUP / UUP files of the index, one per validity day (a UUP wins over the AUP, the newest UUP last):
    [(href, kind, valid_from_epoch)]."""
    rows = re.findall(r'<a href="([^"]+\.pdf)"[^>]*>\s*([AU]UP)\s*</a>\s*</td>\s*<td>\s*(\d{2})\.(\d{2})\.(\d{4}) (\d{2})(\d{2})', index_html)
    best = {}
    for href, kind, dd, mm, yy, hh, mi in rows:
        v = timegm((int(yy), int(mm), int(dd), int(hh), int(mi), 0))
        key = (kind == "UUP", href)
        if v not in best or key > best[v][0]:
            best[v] = (key, href, kind)
    return [(b[1], b[2], v) for v, b in sorted(best.items())]


def parse_aup_pdf(data, valid_from):
    """The AMC Manageable Areas of an AUP / UUP PDF: [{ids: [area], lo, up, win, ref}]."""
    import pypdf
    t = "\n".join(p.extract_text(extraction_mode="layout") for p in pypdf.PdfReader(io.BytesIO(data)).pages)
    m = re.search(r"VALIDITY:\s*(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})", t)
    if m:
        valid_from = timegm((int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)), 0))
    kind = "UUP" if re.search(r"\bUUP\b", t[:400]) else "AUP"
    ama = t.split("AMC Manageable Areas", 1)[1] if "AMC Manageable Areas" in t else ""
    out = []
    d0 = valid_from - (valid_from % 86400)                        # the day of the validity start
    for area, mnm, mx, wef, til in re.findall(r"^\s*\d+\s+(E[FU]\w+)\s+(\d+)\s+(\d+)\s+(\d\d:\d\d)\s+(\d\d:\d\d)", ama, re.M):
        if re.match(r"E[FU](?:TSA|TRA|CBA|TI)", area) and re.search(r"\d[ZRST]$", area):
            continue                                               # a flight plan buffer zone (EFTSAV21Z)
        def at(hm):
            h, mi = int(hm[:2]), int(hm[3:])
            x = d0 + h * 3600 + mi * 60
            return x + 86400 if x < valid_from else x            # 00:00-06:00 belong to the next day
        a, b = at(wef), at(til)
        if b <= a:
            b += 86400
        out.append({"ids": [area], "lo": "FL" + mnm.zfill(3), "up": "FL" + mx.zfill(3), "win": [(a, b)], "ok": True,
                    "ref": kind, "sched": "", "text": "", "circle": None})
    return out, kind, valid_from


# ---------------------------------------------------------------- store
def _db():
    os.makedirs(DIR, exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.execute("CREATE TABLE IF NOT EXISTS snap (t INTEGER, src TEXT, hash TEXT, data TEXT)")
    c.execute("CREATE INDEX IF NOT EXISTS snap_src_t ON snap (src, t)")
    return c


def _store(src, items, now):
    data = json.dumps(items, separators=(",", ":"), sort_keys=True)
    h = hashlib.sha1(data.encode()).hexdigest()
    with _lock:
        c = _db()
        try:
            row = c.execute("SELECT hash FROM snap WHERE src=? ORDER BY t DESC LIMIT 1", (src,)).fetchone()
            if not row or row[0] != h:
                c.execute("INSERT INTO snap VALUES (?,?,?,?)", (int(now), src, h, data))
            c.execute("DELETE FROM snap WHERE t < ?", (int(now - KEEP_DAYS * 86400),))
            c.commit()
            return not row or row[0] != h
        finally:
            c.close()


def update(log=None):
    """Read both sources; returns a short message. A source that fails keeps its last result."""
    now = time.time()
    msgs, errs = [], []
    try:
        items = parse_wrng(_get(WRNG_URL))
        ch = _store("notam", items, now)
        msgs.append(f"NOTAM {len(items)}" + (" (changed)" if ch else ""))
    except Exception as e:
        errs.append(f"NOTAM: {e}")
    try:
        files = aup_files(_get(AUP_INDEX))
        items, names = [], []
        for href, kind, v in files:
            if v + 86400 < now - 3600:                             # a day already over
                continue
            its, k, _ = parse_aup_pdf(_get(AUP_BASE + href if href.startswith("/") else AUP_BASE + "/aup/" + href, binary=True), v)
            items.extend(its)
            names.append(f"{k} {datetime.fromtimestamp(v, timezone.utc):%d.%m.}")
        if files:
            ch = _store("aup", items, now)
            msgs.append(f"{', '.join(names)}: {len(items)} areas" + (" (changed)" if ch else ""))
    except Exception as e:
        errs.append(f"AUP: {e}")
    msg = " · ".join(msgs + errs)
    if log:
        log(f"[airact] {msg}")
    if not msgs:
        raise RuntimeError(msg)
    return msg


def _snaps(c, src, t, after_s):
    """The snapshot of src in force at t (the newest at or before t) and the first after it within
    after_s (a NOTAM published just after the moment)."""
    out = []
    r = c.execute("SELECT t, data FROM snap WHERE src=? AND t<=? ORDER BY t DESC LIMIT 1", (src, int(t))).fetchone()
    if r:
        out.append(r)
    if after_s:
        r2 = c.execute("SELECT t, data FROM snap WHERE src=? AND t>? AND t<=? ORDER BY t LIMIT 1", (src, int(t), int(t + after_s))).fetchone()
        if r2:
            out.append(r2)
    if not out:                                                  # before the first snapshot of the day: the first one
        r3 = c.execute("SELECT t, data FROM snap WHERE src=? AND t>? AND t<=? ORDER BY t LIMIT 1", (src, int(t), int(t + 6 * 3600))).fetchone()
        if r3:
            out.append(r3)
    return out


def active_at(t=None):
    """The areas active at t (epoch, default now): {t, areas: [{id, src, lo, up, until, ref, sched, ok}],
    circles: [{id, lat, lon, r_nm, ...}], checked: {notam, aup}}."""
    t = time.time() if t is None else float(t)
    res = {"t": int(t), "areas": [], "circles": [], "checked": {}}
    if not os.path.exists(DB):
        return res
    with _lock:
        c = _db()
        try:
            snaps = {"notam": _snaps(c, "notam", t, 3600), "aup": _snaps(c, "aup", t, 0)}
            for src in ("notam", "aup"):
                r = c.execute("SELECT MAX(t) FROM snap WHERE src=?", (src,)).fetchone()
                res["checked"][src] = r[0] if r else None
        finally:
            c.close()
    seen = {}
    for src, rows in snaps.items():
        for _, data in rows:
            for it in json.loads(data):
                for a, b in it["win"]:
                    if a <= t < b:
                        for i in it["ids"]:
                            cur = seen.get(i)
                            if cur is None or (alt_ft(it["up"]), b) > (alt_ft(cur["up"]), cur["until"]):
                                seen[i] = {"id": i, "src": src, "lo": it["lo"], "up": it["up"], "until": b,
                                           "ref": it["ref"], "sched": it["sched"], "ok": it["ok"]}
                        if it.get("circle"):
                            la, lo, r = it["circle"]
                            res["circles"].append({"id": it["ids"][0], "lat": la, "lon": lo, "r_nm": r, "lo": it["lo"],
                                                   "up": it["up"], "until": b, "ref": it["ref"]})
                        break
    res["areas"] = sorted(seen.values(), key=lambda x: x["id"])
    uniq = {}
    for cc in res["circles"]:
        uniq[cc["id"]] = cc
    res["circles"] = list(uniq.values())
    return res


if __name__ == "__main__":
    if "--status" in sys.argv:
        a = active_at()
        print(json.dumps({"checked": a["checked"], "active": [x["id"] for x in a["areas"]], "circles": len(a["circles"])}, indent=1))
    else:
        print(update(log=None))
