from flask import jsonify, request
import os, json as _json
from math import radians, sin, cos, atan2

def register_overlays(app, CENTER_LAT, CENTER_LON, OVERLAY_DIR, exclude_names=None):
    exclude_names = set(exclude_names or [])
    _overlays_cache = {}

    def _ov_handle_geom_into(geom, acc):
        t = (geom.get('type') or '').lower()
        def add_line(coords):
            line = []
            for p in coords or []:
                try:
                    lon, lat = float(p[0]), float(p[1])
                except Exception:
                    continue
                line.append((lat, lon))
            if len(line) >= 2:
                acc.append(line)
        if t == 'linestring':
            add_line(geom.get('coordinates'))
        elif t == 'multilinestring':
            for part in (geom.get('coordinates') or []):
                add_line(part)
        elif t == 'polygon':
            rings = geom.get('coordinates') or []
            if rings:
                add_line(rings[0])
        elif t == 'multipolygon':
            for poly in (geom.get('coordinates') or []):
                if poly:
                    add_line(poly[0])

    def _load_overlays():
        nonlocal _overlays_cache
        _overlays_cache = {}
        if not os.path.isdir(OVERLAY_DIR):
            return
        for fn in sorted(os.listdir(OVERLAY_DIR)):
            if not fn.lower().endswith('.geojson'):
                continue
            base_noext = os.path.splitext(fn)[0]
            if base_noext in exclude_names:
                continue
            path = os.path.join(OVERLAY_DIR, fn)
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    gj = _json.load(fh)
                segs = []
                if (gj.get('type') or '').lower() == 'featurecollection':
                    for feat in (gj.get('features') or []):
                        _ov_handle_geom_into(feat.get('geometry') or {}, segs)
                else:
                    _ov_handle_geom_into(gj, segs)
                _overlays_cache[base_noext] = {'segments': segs, 'count': len(segs)}
            except Exception as e:
                print('Overlay load fail', fn, e)

    def _nm_distance(a,b,c,d):
        dlat = radians(c - a)
        dlon = radians(d - b)
        x = sin(dlat/2)**2 + cos(radians(a)) * cos(radians(c)) * sin(dlon/2)**2
        return (6371.0 * 2 * atan2(x**0.5, (1-x)**0.5)) * 0.5399568  # km->nm

    @app.route('/api/overlays_meta')
    def overlays_meta():
        try:
            if not _overlays_cache:
                _load_overlays()
            return jsonify({'ok': True, 'layers': {k: v['count'] for k, v in _overlays_cache.items()}})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @app.route('/api/overlays_fetch')
    def overlays_fetch():
        try:
            if not _overlays_cache:
                _load_overlays()
            names = request.args.get('names', '').split(',')
            names = [n for n in names if n in _overlays_cache]
            center = (request.args.get('center') or '').split(',')
            clat, clon = (float(center[0]), float(center[1])) if len(center) == 2 else (CENTER_LAT, CENTER_LON)
            rng = float(request.args.get('range_nm') or 80.0)
            dec = int(request.args.get('decimate') or 2)
            if dec < 1:
                dec = 1
            out = {}
            for nm in names:
                segs_out = []
                for seg in _overlays_cache[nm]['segments']:
                    try:
                        if _nm_distance(clat,clon, seg[0][0],seg[0][1]) > rng*2 and _nm_distance(clat,clon, seg[-1][0],seg[-1][1]) > rng*2:
                            continue
                    except Exception:
                        pass
                    s2 = seg[::dec] if dec > 1 else list(seg)
                    if s2 and (s2[-1] != seg[-1]):
                        s2.append(seg[-1])
                    segs_out.append([[lat, lon] for (lat, lon) in s2])
                out[nm] = segs_out
            return jsonify({'ok': True, 'layers': out})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500