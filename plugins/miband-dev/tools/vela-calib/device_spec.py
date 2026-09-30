"""Device specs (devices/<id>/device.json, schema vela-device-spec/1): the Python twin of
device-spec.mjs. Same rules; keep the two in step.

    import device_spec as ds
    spec = ds.load('band11')                      # or a path to a spec .json
    ds.list_ids()                                 # every devices/<id>/device.json
    g = ds.geometry(spec)                         # {'w', 'h', 'shape': rect|capsule|circle, 'corner_r' | 'end_r' | 'radius'}
    ds.inside(g, x, y, m)                         # (x, y) at least m px inside the visible outline
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workspace as ws  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
# Specs: the workspace's devices/<id>/device.json when it exists, else the known-device spec shipped
# with the miband-dev plugin (data/profiles/<id>/device.json), as for profiles (workspace.py).
SCHEMA = 'vela-device-spec/1'
SHAPES = ('rect', 'rounded_rect', 'capsule', 'circle')


def spec_path(id_or_path):
    if str(id_or_path).endswith('.json'):
        return os.path.abspath(id_or_path)
    mine = os.path.join(ws.devices_dir(), id_or_path, 'device.json')
    if os.path.isfile(mine):
        return mine
    shipped = os.path.join(ws.DEFAULTS_DIR, id_or_path, 'device.json')
    return shipped if os.path.isfile(shipped) else mine


def list_ids():
    ids = set()
    for d in (ws.devices_dir(), ws.DEFAULTS_DIR):
        if os.path.isdir(d):
            ids.update(x for x in os.listdir(d) if os.path.isfile(os.path.join(d, x, 'device.json')))
    return sorted(ids)


def default_corner_radius(w, h):
    return round(0.2 * min(w, h))


def validate(s, where='spec'):
    def bad(m):
        raise ValueError('%s: %s' % (where, m))
    if s.get('schema') != SCHEMA:
        bad('schema must be ' + SCHEMA)
    sc = s.get('screen') or bad('screen missing')
    for k in ('w', 'h'):
        if not isinstance(sc.get(k), int) or not 100 <= sc[k] <= 2000:
            bad('screen.%s must be an integer 100-2000' % k)
    if sc.get('shape') not in SHAPES:
        bad('screen.shape must be one of ' + ', '.join(SHAPES))
    if sc['shape'] == 'capsule' and not sc['h'] > sc['w']:
        bad('a capsule is taller than it is wide')
    if sc['shape'] == 'circle' and sc['w'] != sc['h']:
        bad('a circle has w == h')
    f = s.get('face')
    if f:
        if f.get('id_digit') is not None and (not isinstance(f['id_digit'], int) or not 1 <= f['id_digit'] <= 9):
            bad('face.id_digit must be 1-9 or null (assigned by new-device.mjs)')
        if f.get('builder') not in ('band10-toolkit', 'pack.mts'):
            bad("face.builder must be 'band10-toolkit' or 'pack.mts'")
    return s


def load(id_or_path):
    p = spec_path(id_or_path)
    if not os.path.isfile(p):
        raise FileNotFoundError('no device spec %s (create one: node tools/vela-calib/new-device.mjs <id> --w W --h H --shape S)' % p)
    with open(p) as f:
        return validate(json.load(f), p)


def geometry(s):
    sc = s['screen']
    w, h, shape = sc['w'], sc['h'], sc['shape']
    if shape == 'capsule':
        return {'w': w, 'h': h, 'shape': 'capsule', 'end_r': w / 2}
    if shape == 'circle':
        return {'w': w, 'h': h, 'shape': 'circle', 'radius': w / 2}
    r = sc.get('corner_radius')
    if r is None:
        r = 0 if shape == 'rect' else default_corner_radius(w, h)
    return {'w': w, 'h': h, 'shape': 'rect', 'corner_r': r}


def inside(g, x, y, m=0.0):
    W, H = g['w'], g['h']
    if g['shape'] == 'capsule':
        r = g['end_r']
        dy = r - y if y < r else y - (H - r) if y > H - r else 0
        return math.hypot(x - W / 2, dy) <= r - m + 1e-9
    if g['shape'] == 'circle':
        return math.hypot(x - W / 2, y - H / 2) <= g['radius'] - m + 1e-9
    r = g['corner_r']
    if x < m or y < m or x > W - m or y > H - m:
        return False
    if r <= m:
        return True
    cx = min(max(x, r), W - r)
    cy = min(max(y, r), H - r)
    return math.hypot(x - cx, y - cy) <= r - m + 1e-9


def rect_inside(g, x, y, w, h, m=0.0):
    return all(inside(g, a, b, m) for a, b in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)))
