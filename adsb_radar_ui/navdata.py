"""navdata.py - Finnish navaids, IFR points, ATS routes and airspaces from the eAIP of AIS Finland
(Fintraffic ANS, https://www.ais.fi/eaip/), updated automatically when a new AIRAC amendment takes
effect (from 2026-11-05).

Source pages (HTML of the eAIP package in force, plus one PDF list per IFR aerodrome):
  ENR 4.4   five-letter IFR points (en-route)            -> points.csv   (type "en-route")
  AD 2.15   WAYPOINTS AND FIXES PDF of each aerodrome    -> points.csv   (type "terminal")
  ENR 4.1   en-route navaids, AD 2.19 aerodrome navaids  -> navaids.csv  (VOR / DME / NDB / L; no ILS parts)
  ENR 3.2   the RNAV routes, one page each               -> overlays/fi_routes.geojson
  ENR 2.1   FIR, ACC sectors, CTA, FIZ upper, TMA        -> overlays/fi_fir / fi_sectors / fi_tma
  AD 2.17   the CTR of each aerodrome                    -> overlays/fi_tma
  ENR 5.1   prohibited, restricted and danger areas      -> overlays/fi_restricted
Terms (AIP Finland GEN 0.1): "Aeronautical data is available for further refining and research without a
separate fee or agreement." Not for navigation.

The output goes to data/navdata/ (git-ignored): AIRAC.json (package, effective date, counts, time),
points.csv, navaids.csv and overlays/*.geojson. A new package is written to a temporary folder,
checked (counts, routes resolved, closed areas) and only then put in place; on any failure the
previous data stay.

    python3 navdata.py            # update if a newer package is in force
    python3 navdata.py --force    # download and rebuild now
    python3 navdata.py --status   # show what is installed
"""
import csv, io, json, os, re, shutil, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser

BASE = "https://www.ais.fi/eaip/"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get("NAVDATA_DIR", os.path.join(HERE, "data", "navdata"))
BORDER_FILE = os.path.join(HERE, "data", "fi_borders.geojson")   # Finland's land borders (Natural Earth, public domain)
UA = "adsb_radar navdata (radar.oh2gax.org)"
COORD = r"(\d{2})(\d{2})(\d{2}(?:\.\d+)?)\s*([NS])\s*(\d{3})(\d{2})(\d{2}(?:\.\d+)?)\s*([EW])"


# ---------------------------------------------------------------- download
def _get(url, binary=False, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            return data if binary else data.decode("utf-8", "replace")
        except Exception as e:              # noqa: BLE001 - network errors of any kind: retry
            last = e
            time.sleep(2 + 3 * i)
    raise RuntimeError(f"download failed: {url}: {last}")


def _q(path):
    return urllib.parse.quote(path, safe="/")


def packages():
    """[(folder, effective date 'YYYY-MM-DD')] of the eAIP packages listed at /eaip/, newest first."""
    html = _get(BASE)
    out = []
    for m in re.finditer(r'href="([^"]*?_(\d{4})_(\d{2})_(\d{2}))[\\/]index\.html"', html):
        out.append((m.group(1), f"{m.group(2)}-{m.group(3)}-{m.group(4)}"))
    return sorted(set(out), key=lambda p: p[1], reverse=True)


def package_in_force(today=None):
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for folder, eff in packages():
        if eff <= today:
            return folder, eff
    raise RuntimeError("no eAIP package in force found")


# ---------------------------------------------------------------- text helpers
def _text(html):
    t = re.sub(r"(?is)<(script|style|del)\b.*?</\1>", " ", html)
    t = re.sub(r"(?i)<br[^>]*>|</(p|div|td|th|tr|li|h\d)>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = unescape(t).replace("\xa0", " ")
    t = re.sub(r"[ \t\r]+", " ", t)
    return "\n".join(l.strip() for l in t.split("\n") if l.strip())


def dms(s):
    m = re.search(COORD, s)
    if not m:
        return None
    la = int(m[1]) + int(m[2]) / 60 + float(m[3]) / 3600
    lo = int(m[5]) + int(m[6]) / 60 + float(m[7]) / 3600
    return (round(la if m[4] == "N" else -la, 6), round(lo if m[8] == "E" else -lo, 6))


# ---------------------------------------------------------------- parsers
class _T(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.stack, self.row, self.cell = [], [], None, None
        self.skip = 0

    def handle_starttag(self, tag, a):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "table":
            self.stack.append([])
        elif tag == "tr" and self.stack:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag == "br" and self.cell is not None:
            self.cell.append("\n")
        # changed / deleted text: the eAIP marks deletions with <del> (skip) - see handle_data
        if tag in ("del", "strike"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "del", "strike"):
            self.skip = max(0, self.skip - 1)
        elif tag in ("td", "th") and self.cell is not None and self.row is not None:
            txt = "".join(self.cell)
            txt = re.sub(r"[ \t\r\xa0]+", " ", txt)
            txt = "\n".join(l.strip() for l in txt.split("\n"))
            self.row.append(re.sub(r"\n+", "\n", txt).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None and self.stack:
            self.stack[-1].append(self.row)
            self.row = None
        elif tag == "table" and self.stack:
            self.tables.append(self.stack.pop())

    def handle_data(self, d):
        if self.skip:
            return
        if self.cell is not None:
            self.cell.append(d)


def _tables(html_text):
    p = _T()
    p.feed(html_text)
    return p.tables



def parse_enr44(html):
    """ENR 4.4: [{ident, lat, lon, fra, routes}] - rows 'ABOXU 633457N 0252329E Y77, Y86 FRA (I) ...'."""
    out, seen = [], set()
    for t in _tables(html):
        for cells in t:
            if len(cells) < 2 or not cells[0] or not re.fullmatch(r"[A-Z]{5}", cells[0].split("\n")[0]):
                continue
            ident, c = cells[0].split("\n")[0], dms(cells[1].replace("\n", " "))
            if not c or ident in seen:
                continue
            seen.add(ident)
            out.append({"ident": ident, "lat": c[0], "lon": c[1],
                        "routes": " ".join(cells[2].split()) if len(cells) > 2 else "",
                        "fra": " ".join(cells[3].split()) if len(cells) > 3 else ""})
    return out


_AID = re.compile(r"\b(DVOR/DME|VOR/DME|DVOR|VOR|DME|TACAN|VORTAC|NDB|L)\b")


def parse_enr41(html):
    """ENR 4.1: [{ident, name, type, freq, lat, lon}] - the station name and type in column 1."""
    out = []
    for t in _tables(html):
        for cells in t:
            if len(cells) < 5 or not cells[1]:
                continue
            ident, c = cells[1].split("\n")[0].strip(), dms(cells[4].replace("\n", " "))
            if not c or not re.fullmatch(r"[A-Z]{1,3}", ident):
                continue
            lines = cells[0].split("\n")
            m = _AID.search(cells[0])
            out.append({"ident": ident, "name": lines[0].title(), "type": m.group(1) if m else "",
                        "freq": cells[2].split("\n")[0], "lat": c[0], "lon": c[1], "aerodrome": ""})
    return out


def parse_ad219(html, icao):
    """AD 2.19 of an aerodrome: its navaids (VOR / DME / NDB / locators); the ILS parts (LOC, GP and their
    DME) are left out - they sit on the runways. Read from the page text: each aid ends with its position."""
    t = _text(html)
    i = t.find("RADIO NAVIGATION AND LANDING AIDS")
    j = t.find("AD 2.20", i + 1) if i >= 0 else -1
    if i < 0:
        return []
    lines = t[i:j if j > 0 else None].split("\n")
    out, block = [], []
    k = 0
    while k < len(lines) - 1:
        la, lo = lines[k], lines[k + 1]
        if re.fullmatch(r"\d{6}(?:\.\d+)?[NS]", la) and re.fullmatch(r"\d{7}(?:\.\d+)?[EW]", lo):
            c = dms(la + lo)
            blk = [b for b in block if b not in ("NIL",)]
            fq = next((n for n, b in enumerate(blk) if re.search(r"(MHZ|KHZ)$", b)), None)
            if fq is not None and fq >= 1:
                ident = blk[fq - 1]
                head = " ".join(blk[:fq - 1])
                ils = re.search(r"\b(LOC|GP|ILS|MLS)\b", head) or re.search(r"\b(LOC|GP)\b|\bDME \d{2}[LRC]?\b", head)
                m = _AID.search(head)
                name = next((b for b in blk[:fq - 1] if re.fullmatch(r"[A-ZÄÖÅ][A-ZÄÖÅ .\-]+", b) and not _AID.fullmatch(b)), "")
                if c and not ils and m and re.fullmatch(r"[A-Z]{1,3}", ident):
                    out.append({"ident": ident, "name": name.title(), "type": m.group(1), "freq": blk[fq],
                                "lat": c[0], "lon": c[1], "aerodrome": icao})
            block = []
            k += 2
            continue
        block.append(la)
        # a new aid starts after the remarks of the previous one: keep only the recent lines
        if len(block) > 14:
            block = block[-14:]
        k += 1
    return out


def parse_wpt_pdf(data, icao):
    """The aerodrome's WAYPOINTS AND FIXES list (PDF): [{ident, lat, lon}] (pypdf, layout mode)."""
    try:
        import pypdf
    except ImportError:
        raise RuntimeError("pypdf is not installed (pip install pypdf)")
    r = pypdf.PdfReader(io.BytesIO(data))
    t = "\n".join(p.extract_text(extraction_mode="layout") for p in r.pages)
    out, seen = [], set()
    for m in re.finditer(r"^\s*([A-Z][A-Z0-9]{4})\b[^\n]*?(\d{6}(?:\.\d+)?[NS])\s*(\d{7}(?:\.\d+)?[EW])", t, re.M):
        if m.group(1) in seen:
            continue
        c = dms(m.group(2) + m.group(3))
        if c:
            seen.add(m.group(1))
            out.append({"ident": m.group(1), "lat": c[0], "lon": c[1], "aerodrome": icao})
    return out


def parse_route(html, name):
    """ENR 3.2 page of one route: the points in order [(ident, lat, lon)] (a point name, then its
    coordinates on the next lines)."""
    t = _text(html)
    pts = []
    for m in re.finditer(r"\b([A-Z]{2,5})\b[^\n]*\n(?:[^\n]*\n){0,1}?\s*(\d{6}(?:\.\d+)?[NS])\s*\n?\s*(\d{7}(?:\.\d+)?[EW])", t):
        c = dms(m.group(2) + m.group(3))
        if c and m.group(1) not in ("FL", "NM", "PERM", "CDR", "RTE", "MAG", "UNL", "GND", "SFC", "END"):
            if not pts or pts[-1][0] != m.group(1):
                pts.append((m.group(1), c[0], c[1]))
    return pts


def parse_areas(html):
    """ENR 2.1 / ENR 5.1 / AD 2.17: [{name, desig, text (lateral limits), upper, lower}] for every
    'Area bounded by lines joining points ... to point of origin.'"""
    t = _text(html)
    out = []
    for m in re.finditer(r"Area bounded by lines joining points\s*\n?(.*?to point of origin\.?)", t, re.S):
        before = t[:m.start()].split("\n")[-4:]
        after = t[m.end():].split("\n")
        after = [a for a in after if a.strip()][:3]
        name, desig = "", ""
        for b in reversed(before):
            b = b.strip()
            if re.fullmatch(r"\(.+\)", b) and not desig:
                desig = b.strip("()")
            elif b and not name and not re.fullmatch(r"\d+", b) and len(b) < 80:
                name = b
                break
        up = lo = ""
        if after:
            if "/" in after[0] and len(after[0]) < 40:
                up, lo = [x.strip() for x in after[0].split("/", 1)]
            elif len(after) > 1:
                up, lo = after[0], after[1]
        out.append({"name": name, "desig": desig, "text": " ".join(m.group(1).split()), "upper": up, "lower": lo})
    return out


# ---------------------------------------------------------------- geometry
_borders = None


def _border_lines():
    """Finland's land borders as continuous lines [(lat, lon)] (the parts of each border joined)."""
    global _borders
    if _borders is None:
        _borders = []
        try:
            gj = json.load(open(BORDER_FILE, encoding="utf-8"))
        except (OSError, ValueError):
            return _borders
        for f in gj.get("features", []):
            g = f.get("geometry") or {}
            parts = [g.get("coordinates")] if g.get("type") == "LineString" else list(g.get("coordinates") or [])
            parts = [[(float(y), float(x)) for x, y in p] for p in parts if p and len(p) >= 2]
            while parts:                                   # chain the parts end to end
                line = parts.pop(0)
                grown = True
                while grown:
                    grown = False
                    for i, q in enumerate(parts):
                        for cand in (q, q[::-1]):
                            if _d2(line[-1], cand[0]) < 1e-6:
                                line = line + cand[1:]; parts.pop(i); grown = True; break
                            if _d2(line[0], cand[-1]) < 1e-6:
                                line = cand[:-1] + line; parts.pop(i); grown = True; break
                        if grown:
                            break
                _borders.append(line)
    return _borders


def _d2(a, b):
    from math import cos, radians
    k = cos(radians((a[0] + b[0]) / 2))
    return (a[0] - b[0]) ** 2 + ((a[1] - b[1]) * k) ** 2


def _along_border(a, b):
    """The state border between points a and b ([(lat, lon)], without a and b): from the vertex of a border
    line nearest to a to the one nearest to b. A point may lie off the land border (out at sea, where the
    border continues as the sea boundary) - up to 30 NM. [] (a straight line) when no line fits."""
    best = None
    for line in _border_lines():
        ia = min(range(len(line)), key=lambda i: _d2(line[i], a))
        ib = min(range(len(line)), key=lambda i: _d2(line[i], b))
        da, db = _d2(line[ia], a), _d2(line[ib], b)
        if da < 0.5 ** 2 and db < 0.5 ** 2 and ia != ib:         # both within ~30 NM of this line
            if best is None or da + db < best[0]:
                best = (da + db, line, ia, ib)
    if not best:
        return []
    _, line, ia, ib = best
    seg = line[ia:ib + 1] if ia < ib else line[ib:ia + 1][::-1]
    if seg and _d2(seg[0], a) < 1e-8:
        seg = seg[1:]
    if seg and _d2(seg[-1], b) < 1e-8:
        seg = seg[:-1]
    return seg


def area_ring(text):
    """Lateral limits text -> closed ring [(lat, lon)]; follows 'then along <state> border up to <point>'."""
    parts = re.split(r"(\d{6}(?:\.\d+)?[NS]\s*\d{7}(?:\.\d+)?[EW])", text)
    ring, along = [], False
    for p in parts:
        c = dms(p) if re.fullmatch(r"\d{6}(?:\.\d+)?[NS]\s*\d{7}(?:\.\d+)?[EW]", p.strip()) else None
        if c:
            if along and ring:
                ring.extend(_along_border(ring[-1], c))
            ring.append(c)
            along = False
        elif re.search(r"(?i)along\b.*border", p):
            along = True
    if re.search(r"(?i)along\b[^.]*border[^.]*to point of origin", text) and ring:
        ring.extend(_along_border(ring[-1], ring[0]))
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def _feature(name, coords, props, poly=True):
    pts = [[lon, lat] for lat, lon in coords]
    geom = {"type": "Polygon", "coordinates": [pts]} if poly else {"type": "LineString", "coordinates": pts}
    return {"type": "Feature", "properties": dict(props, name=name), "geometry": geom}


def _point_in(ring, lat, lon):
    inside = False
    for (y1, x1), (y2, x2) in zip(ring, ring[1:]):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-12) + x1:
            inside = not inside
    return inside


# ---------------------------------------------------------------- build
def build(folder, eff, log=print):
    root = BASE + _q(folder) + "/"
    eaip = root + "eAIP/"
    log(f"[navdata] package {folder} (effective {eff})")
    cover = _text(_get(root + _q("EF-Cover Page-en-GB.html")))
    m = re.search(r"AIRAC AMDT[^\n(]*\((\d{3}/\d{4})\)", cover)
    amdt = m.group(1) if m else ""
    menu = _get(eaip + "menu.html")
    page = lambda name: _get(eaip + _q(f"EF-{name}-en-GB.html"))

    pts = [dict(p, type="en-route", aerodrome="") for p in parse_enr44(page("ENR 4.4"))]
    navs = parse_enr41(page("ENR 4.1"))
    feats = {"fi_fir": [], "fi_sectors": [], "fi_tma": [], "fi_restricted": [], "fi_routes": []}

    for a in parse_areas(page("ENR 2.1")):
        ring = area_ring(a["text"])
        n = (a["name"] + " " + a["desig"]).upper()
        kind = "fi_fir" if "FIR" in n else "fi_sectors" if "SECT" in n else "fi_tma"
        feats[kind].append(_feature(a["name"], ring, {"desig": a["desig"], "upper": a["upper"], "lower": a["lower"]}))
    for a in parse_areas(page("ENR 5.1")):
        ring = area_ring(a["text"])
        feats["fi_restricted"].append(_feature(a["name"], ring, {"upper": a["upper"], "lower": a["lower"],
                                                                 "kind": (re.match(r"EF([PRD])", a["name"]) or [None, ""])[1]}))

    ads = sorted(set(re.findall(r"EF-AD 2 (EF[A-Z]{2}) - ([^\"'#]*?) 1-en-GB\.html", menu)))
    try:
        import pypdf  # noqa: F401 - the aerodromes' waypoint lists are PDF
        have_pdf = True
    except ImportError:
        have_pdf = False
        log("[navdata] pypdf missing (pip install pypdf): no terminal waypoints this time")
    for icao, adname in ads:
        try:
            h = _get(eaip + _q(f"EF-AD 2 {icao} - {adname} 1-en-GB.html"))
        except RuntimeError as e:
            log(f"[navdata] {icao}: {e}")
            continue
        navs.extend(parse_ad219(h, icao))
        for a in parse_areas(h):
            if "CTR" in a["name"].upper():
                feats["fi_tma"].append(_feature(a["name"], area_ring(a["text"]), {"upper": a["upper"], "lower": a["lower"]}))
        if not have_pdf:
            continue
        try:
            pdf = _get(root + f"documents/Root_WePub/ANSFI/Charts/AD/{icao}/EF_AD_2_{icao}_WPT_LIST.pdf", binary=True, tries=1)
        except RuntimeError:
            continue                                          # a VFR aerodrome: no IFR points
        if pdf[:4] == b"%PDF":
            pts.extend(dict(p, type="terminal", fra="", routes="") for p in parse_wpt_pdf(pdf, icao))

    by_id = {}
    for p in pts:                                             # en-route first; a terminal duplicate is dropped
        by_id.setdefault(p["ident"], p)
    pts = list(by_id.values())
    seen, nav2 = set(), []
    for n in navs:                                            # ENR 4.1 and AD 2.19 list some aids twice
        key = (n["ident"], round(n["lat"], 2), round(n["lon"], 2))
        if key not in seen:
            seen.add(key)
            nav2.append(n)
    navs = nav2

    known = {p["ident"]: (p["lat"], p["lon"]) for p in pts}
    known.update({n["ident"]: (n["lat"], n["lon"]) for n in navs})
    rnames = sorted(set(re.findall(r"EF-ENR 3\.2 ([A-Z]\d+)-en-GB\.html", menu)))
    for rn in rnames:
        rp = parse_route(page(f"ENR 3.2 {rn}"), rn)
        if len(rp) >= 2:
            feats["fi_routes"].append(_feature(rn, [(la, lo) for _, la, lo in rp], {"points": " ".join(p[0] for p in rp)}, poly=False))
    counts = {"points_en_route": sum(p["type"] == "en-route" for p in pts),
              "points_terminal": sum(p["type"] == "terminal" for p in pts), "navaids": len(navs),
              "routes": len(feats["fi_routes"]), "fir": len(feats["fi_fir"]), "sectors": len(feats["fi_sectors"]),
              "tma_cta_ctr": len(feats["fi_tma"]), "restricted": len(feats["fi_restricted"]), "aerodromes": len(ads)}
    return {"package": folder, "effective": eff, "amdt": amdt, "counts": counts, "pdf": have_pdf}, pts, navs, feats


def check(meta, pts, navs, feats):
    """Sanity limits: a broken page or a changed layout must not replace good data with junk."""
    c, errs = meta["counts"], []
    if not 150 <= c["points_en_route"] <= 1500: errs.append(f"en-route points {c['points_en_route']}")
    if meta.get("pdf") and c["points_terminal"] < 50: errs.append(f"terminal points {c['points_terminal']}")
    if not 10 <= c["navaids"] <= 300: errs.append(f"navaids {c['navaids']}")
    if c["routes"] < 5: errs.append(f"routes {c['routes']}")
    if c["fir"] < 1: errs.append("no FIR")
    if c["tma_cta_ctr"] < 10: errs.append(f"TMA/CTA/CTR {c['tma_cta_ctr']}")
    if c["restricted"] < 10: errs.append(f"restricted areas {c['restricted']}")
    for p in pts + navs:
        if not (59 <= p["lat"] <= 71 and 18 <= p["lon"] <= 33):
            errs.append(f"{p['ident']} outside Finland ({p['lat']}, {p['lon']})")
            break
    for k, fs in feats.items():
        for f in fs:
            if len(f["geometry"]["coordinates"][0 if f["geometry"]["type"] == "Polygon" else slice(None)]) < 2:
                errs.append(f"{k}: {f['properties']['name']} has no shape")
                break
    return errs


def write(meta, pts, navs, feats, out_dir=OUT_DIR):
    tmp = out_dir + ".new"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(tmp, "overlays"))
    with open(os.path.join(tmp, "points.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ident", "type", "name", "latitude_deg", "longitude_deg", "aerodrome", "routes", "fra"])
        for p in sorted(pts, key=lambda p: p["ident"]):
            w.writerow([p["ident"], p["type"], p["ident"], p["lat"], p["lon"], p.get("aerodrome", ""), p.get("routes", ""), p.get("fra", "")])
    with open(os.path.join(tmp, "navaids.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ident", "name", "type", "frequency", "latitude_deg", "longitude_deg", "aerodrome"])
        for n in sorted(navs, key=lambda n: n["ident"]):
            w.writerow([n["ident"], n["name"], n["type"], n["freq"], n["lat"], n["lon"], n.get("aerodrome", "")])
    for k, fs in feats.items():
        with open(os.path.join(tmp, "overlays", k + ".geojson"), "w", encoding="utf-8") as fh:
            json.dump({"type": "FeatureCollection", "features": fs}, fh, separators=(",", ":"))
    meta = dict(meta, fetched=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                source="AIP Finland, Fintraffic ANS (www.ais.fi) - not for navigation")
    with open(os.path.join(tmp, "AIRAC.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    old = out_dir + ".old"
    shutil.rmtree(old, ignore_errors=True)
    if os.path.isdir(out_dir):
        os.rename(out_dir, old)
    os.rename(tmp, out_dir)
    shutil.rmtree(old, ignore_errors=True)
    return meta


def installed(out_dir=OUT_DIR):
    try:
        with open(os.path.join(out_dir, "AIRAC.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def update(force=False, log=print, out_dir=OUT_DIR):
    """Download and install the package in force when it differs from the installed one.
    Returns (changed, meta or None, message)."""
    folder, eff = package_in_force()
    cur = installed(out_dir)
    if cur and cur.get("package") == folder and not force:
        return False, cur, f"up to date: {folder}"
    meta, pts, navs, feats = build(folder, eff, log=log)
    errs = check(meta, pts, navs, feats)
    if errs:
        raise RuntimeError("new data rejected: " + "; ".join(errs[:5]))
    meta = write(meta, pts, navs, feats, out_dir)
    return True, meta, f"installed {folder}: {meta['counts']}"


def fir_ring(out_dir=OUT_DIR):
    """The EFIN FIR boundary [(lat, lon)] of the installed data (None without data)."""
    try:
        gj = json.load(open(os.path.join(out_dir, "overlays", "fi_fir.geojson"), encoding="utf-8"))
        return [(y, x) for x, y in gj["features"][0]["geometry"]["coordinates"][0]]
    except (OSError, ValueError, KeyError, IndexError):
        return None


def inside_fir(ring, lat, lon):
    return bool(ring) and _point_in(ring, lat, lon)


if __name__ == "__main__":
    if "--status" in sys.argv:
        print(json.dumps(installed(), indent=1))
        sys.exit(0)
    ok, meta, msg = update(force="--force" in sys.argv)
    print("[navdata]", msg)
