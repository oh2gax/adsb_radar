from flask import jsonify, request, Response
import os, gzip, json as _json
from math import radians, cos

def register_overlays(app, CENTER_LAT, CENTER_LON, OVERLAY_DIR, exclude_names=None, extra_dirs=None, seg_filter=None, version=None):
    """extra_dirs: a function returning more folders of .geojson layers (the AIP data, navdata.py);
    seg_filter(name, line) -> False drops a line (old lines replaced by the AIP data); version() -> a text
    that changes with the data (the layer URLs carry it). Returns reload(), to call when the data change."""
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
        dirs = [OVERLAY_DIR] + list((extra_dirs() if extra_dirs else None) or [])
        files = [(d, fn) for d in dirs if os.path.isdir(d) for fn in sorted(os.listdir(d))]
        for d, fn in files:
            if not fn.lower().endswith('.geojson'):
                continue
            base_noext = os.path.splitext(fn)[0]
            if base_noext in exclude_names:
                continue
            path = os.path.join(d, fn)
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    gj = _json.load(fh)
                segs = []
                if (gj.get('type') or '').lower() == 'featurecollection':
                    for feat in (gj.get('features') or []):
                        _ov_handle_geom_into(feat.get('geometry') or {}, segs)
                else:
                    _ov_handle_geom_into(gj, segs)
                if seg_filter:
                    segs = [sg for sg in segs if seg_filter(base_noext, sg)]
                # bounding box per line: (min_lat, max_lat, min_lon, max_lon)
                boxes = [(min(p[0] for p in sg), max(p[0] for p in sg), min(p[1] for p in sg), max(p[1] for p in sg)) for sg in segs]
                _overlays_cache[base_noext] = {'segments': segs, 'bbox': boxes, 'count': len(segs)}
            except Exception as e:
                print('Overlay load fail', fn, e)

    @app.route('/api/overlays_meta')
    def overlays_meta():
        try:
            if not _overlays_cache:
                _load_overlays()
            return jsonify({'ok': True, 'layers': {k: v['count'] for k, v in _overlays_cache.items()},
                            'ver': (version() if version else '')})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    _layer_bytes = {}   # (name, dec) -> (json bytes, gzip bytes)

    @app.route('/api/overlay/<name>')
    def overlay_layer(name):
        """One whole line layer, for the browser to keep: {"segments": [[lat, lon, lat, lon, ...], ...]}.
        Coordinates rounded to 5 decimals (about 1 m); every dec-th point (dec=1..4), first and last always
        kept. Sent gzip-compressed and cacheable: the page asks with ?v=<version>, so a new version of
        the radar gets fresh data."""
        try:
            if not _overlays_cache:
                _load_overlays()
            if name not in _overlays_cache:
                return jsonify({'ok': False, 'error': 'no such layer'}), 404
            try:
                dec = max(1, min(4, int(request.args.get('dec') or 1)))
            except ValueError:
                dec = 1
            key = (name, dec)
            if key not in _layer_bytes:
                segs = []
                for seg in _overlays_cache[name]['segments']:
                    s2 = seg[::dec] if dec > 1 else list(seg)
                    if s2[-1] != seg[-1]:
                        s2.append(seg[-1])
                    flat = []
                    for lat, lon in s2:
                        flat.append(round(lat, 5)); flat.append(round(lon, 5))
                    segs.append(flat)
                raw = _json.dumps({'ok': True, 'name': name, 'segments': segs}, separators=(',', ':')).encode()
                _layer_bytes[key] = (raw, gzip.compress(raw, 6))
            raw, gz = _layer_bytes[key]
            use_gz = 'gzip' in (request.headers.get('Accept-Encoding') or '')
            resp = Response(gz if use_gz else raw, mimetype='application/json')
            if use_gz:
                resp.headers['Content-Encoding'] = 'gzip'
            resp.headers['Vary'] = 'Accept-Encoding'
            resp.headers['Cache-Control'] = 'public, max-age=86400'
            return resp
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
            # Keep every line whose bounding box touches the area around the view
            # (2x range covers wide screens, where targets are drawn beyond the range ring).
            dlat = rng * 2 / 60.0
            dlon = rng * 2 / (60.0 * max(0.01, cos(radians(clat))))
            v_lat1, v_lat2, v_lon1, v_lon2 = clat - dlat, clat + dlat, clon - dlon, clon + dlon
            out = {}
            for nm in names:
                layer = _overlays_cache[nm]
                segs_out = []
                for seg, (la1, la2, lo1, lo2) in zip(layer['segments'], layer['bbox']):
                    if la2 < v_lat1 or la1 > v_lat2 or lo2 < v_lon1 or lo1 > v_lon2:
                        continue
                    s2 = seg[::dec] if dec > 1 else list(seg)
                    if s2 and (s2[-1] != seg[-1]):
                        s2.append(seg[-1])
                    segs_out.append([[lat, lon] for (lat, lon) in s2])
                out[nm] = segs_out
            return jsonify({'ok': True, 'layers': out})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    def reload():
        """Read the layers again (new AIP data); the browser gets them under a new ?v=."""
        _load_overlays()
        _layer_bytes.clear()

    return reload
