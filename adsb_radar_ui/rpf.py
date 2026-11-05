"""rpf.py - the list behind the RPF switch: military aircraft in the ICAO24 block 100000-1FFFFF.

Two public sources, as in modes_logger:
  - plane-alert-db (github.com/sdr-enthusiasts/plane-alert-db): plane-alert-db.csv, rows with #CMPG = Mil,
    Gov or Pol (military, government, police);
  - tar1090-db (github.com/wiedehopf/tar1090-db, the Mictronics database): aircraft.csv.gz, rows whose
    flags start with 1 (military), except the "Miscode" rows (other countries' aircraft sending a code
    from this block by mistake).
Both are checked once a day with a conditional GET (ETag), so a day without changes costs two small
"304 Not Modified" answers. The result is data/rpf/rpf.json (not in git): {updated, n, hex: [...],
cat: {hex: "M" | "G"}} - M military, G government or police (plane-alert-db decides where it has the
aircraft; tar1090-db's are M).
A download that fails or gives too few aircraft keeps the previous list.

Run by hand: python3 rpf.py [--force|--status]
"""
import csv, gzip, io, json, os, sys, time, urllib.error, urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get("RPF_DIR", os.path.join(BASE_DIR, "data", "rpf"))
OUT = os.path.join(OUT_DIR, "rpf.json")
SOURCES = {
    "pad": "https://raw.githubusercontent.com/sdr-enthusiasts/plane-alert-db/main/plane-alert-db.csv",
    "t1db": "https://github.com/wiedehopf/tar1090-db/raw/refs/heads/csv/aircraft.csv.gz",
}
LO, HI = 0x100000, 0x1FFFFF
FORMAT = 3                       # 2: plane-alert-db Gov and Pol too; 3: M / G (an older list is rebuilt once)
CMPG = ("mil", "gov", "pol")
MIN_N = 100                      # fewer than this: treated as a broken download
TIMEOUT = 120
UA = "adsb_radar (+https://radar.oh2gax.org)"


def _in_block(h):
    try:
        return LO <= int(h, 16) <= HI and len(h) == 6
    except (TypeError, ValueError):
        return False


def parse_pad(text):
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        h = (r.get("$ICAO") or "").strip().upper().zfill(6)
        c = (r.get("#CMPG") or "").strip().lower()
        if _in_block(h) and c in CMPG:
            out[h] = "M" if c == "mil" else "G"
    return out


def parse_t1db(raw_gz):
    out = {}
    with gzip.open(io.BytesIO(raw_gz), "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            p = line.rstrip("\n").split(";")
            if len(p) < 4 or p[3][:1] != "1":
                continue
            h = p[0].strip().upper()
            if _in_block(h) and not (len(p) > 6 and p[6].startswith("Miscode")):
                out[h] = "M"
    return out


def _load():
    try:
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _fetch(url, etag):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **({"If-None-Match": etag} if etag else {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read(), r.headers.get("ETag")
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None, etag
        raise


def update(force=False, log=None):
    """Check the sources; returns (changed, message). Raises on failure (the old list stays)."""
    old = _load() or {}
    if old and old.get("format") != FORMAT:
        force = True
    etags = {} if force else dict(old.get("etags") or {})
    sets = {k: dict(v) for k, v in (old.get("parts") or {}).items()} if not force else {}
    got, errors = False, []
    for key, url in SOURCES.items():
        try:
            body, tag = _fetch(url, etags.get(key) if key in sets else None)
        except Exception as e:                          # this source: keep what it gave last time
            errors.append(f"{key}: {e}")
            continue
        if body is None:
            continue                                   # 304: as before
        sets[key] = parse_pad(body.decode("utf-8", "replace")) if key == "pad" else parse_t1db(body)
        etags[key] = tag
        got = True
        if log:
            log(f"[rpf] {key}: {len(sets[key])}")
    if errors and not got and not sets:
        raise RuntimeError("; ".join(errors))
    if not got and old.get("hex"):
        return False, f"no change ({old.get('n', 0)})" + (" · " + "; ".join(errors) if errors else "")
    cat = {}
    for key in ("t1db", "pad"):                          # plane-alert-db last: its classification wins
        cat.update(sets.get(key) or {})
    allhex = sorted(cat)
    if len(allhex) < MIN_N:
        raise RuntimeError(f"only {len(allhex)} aircraft - the previous list is kept")
    changed = cat != old.get("cat")
    data = {"format": FORMAT, "updated": int(time.time()), "n": len(allhex), "hex": allhex,
            "cat": {h: cat[h] for h in allhex}, "etags": etags, "parts": sets}
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = OUT + ".new"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, OUT)
    return changed, f"{len(allhex)} aircraft" + (" (changed)" if changed else "") + (" · " + "; ".join(errors) if errors else "")


def current():
    """{updated, n, hex} of the installed list, or None."""
    d = _load()
    return {"updated": d.get("updated"), "n": d.get("n", 0), "hex": d.get("hex", []), "cat": d.get("cat", {})} if d else None


if __name__ == "__main__":
    if "--status" in sys.argv:
        c = current()
        print("none" if not c else f"{c['n']} aircraft, updated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(c['updated']))}")
    else:
        print(update(force="--force" in sys.argv, log=print)[1])
