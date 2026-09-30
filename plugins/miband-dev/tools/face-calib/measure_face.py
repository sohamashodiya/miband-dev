#!/usr/bin/env python3
"""Face calibration kit: measure photos of the calibration faces and write the `face` section.

    python3 measure_face.py run PHOTO [PHOTO ...] --device <id> [--page N] [--dry-run]   (a device with layouts/<id>.json)
    python3 measure_face.py set PATH VALUE --source TEXT --device ...     # an observation (face.* path)
    python3 measure_face.py show --device ...                             # every face fact and its status
    python3 measure_face.py seed --device ...                             # add the kit's facts as unknown
    python3 measure_face.py selftest [--device X] [--spec S.json]          # synthetic end-to-end check (default:
                                          band11, band10pro and the synthetic circle / rect in tools/vela-calib/test/specs)

Where it writes (all in your workspace, never next to this script; see ../vela-calib/workspace.py):
  <workspace>/devices/<model>/profile.json, the "face" key only (nothing else in the file is touched; the
  quick-app kit, tools/vela-calib, owns the rest and keeps "face" when it rewrites the file)
  evidence: <workspace>/devices/<model>/evidence-face/<photo>.json (one per photo; the profile is rebuilt from
               all of them, newest photo per page wins; kept apart from the quick-app evidence/)

Reading a photo reuses the quick-app kit (tools/vela-calib/measure.py, imported read-only): the
yellow scale bar and yellow 100 px ticks give a rough similarity, every ruler tick's inner end then
feeds a homography (band px -> photo px), camera bloom is estimated from the tick thickness, and the
screen is rectified to 8 px per band px. The page barcode says which face (and normal / always-on
view) the photo shows. Each sample of that page (layouts/<model>.json, written by gen.py) is then
measured: swatches, digit and frame cells (their value is in 4 bit squares), placement targets,
image-format tiles, Lua status squares, the capsule ends / corners / round edge, the edge combs and
the top strip. Faces for any device other than the Band 10 / 11 (212 x 520, band10-toolkit's own
target) are experimental until a photo of F1 on that device measures (see README.md).
"""
import argparse
import datetime
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True  # never write a __pycache__ into tools/vela-calib
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..', 'vela-calib')))
import measure as vm  # noqa: E402  (read-only reuse: Fit, Rect, read_barcode, corner/comb/swatch/ramp)
import workspace as ws  # noqa: E402  (where profiles and evidence are read and written)

S = vm.S
WS = None  # --workspace (None: $MIBAND_WORKSPACE or the nearest folder with devices/)
SCHEMA = 'vela-device-profile/2'


# ---------------------------------------------------------------------------------------------
# small helpers on the rectified image
# ---------------------------------------------------------------------------------------------
def cname(rgb):
    """Colour name robust to the phone camera's rendering (Pixel 10, 2026-09-29): the band's green
    #3CFF3C photographs as about (25, 214, 140) and neutral greys come out bluish."""
    r, g, b = [float(v) for v in rgb]
    mx = max(r, g, b)
    if mx < 40:
        return 'black'
    if min(r, g, b) > 0.55 * mx:
        return 'white' if mx > 120 else 'grey'
    if b >= r and b >= g:
        return 'cyan' if g > 0.75 * b else 'pink' if r > 0.6 * b else 'blue'
    if r >= g:
        return 'pink' if b > 0.45 * r else 'yellow' if g > 0.6 * r else 'red'
    return 'yellow' if r > 0.6 * g else 'cyan' if b > 0.8 * g else 'green'


def mean_rgb(R, x0, y0, x1, y1):
    rgb, _ = R.mean(x0, y0, x1, y1)
    return [float(v) for v in rgb]


def luma(rgb):
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def read_code(R, x, y, at, glyph_box, L):
    """Value of a cell's 4 bit squares at band (x, y). glyph_box: (x0,y0,x1,y1) relative, for the
    reference level (the white glyph is always there)."""
    sq, gap = L['cells']['bit_sq'], L['cells']['bit_gap']
    p = sq + gap
    bx, by = at
    vals = []
    for (dx, dy) in ((0, 0), (p, 0), (0, p), (p, p)):
        cx, cy = x + bx + dx + sq / 2, y + by + dy + sq / 2
        vals.append(luma(mean_rgb(R, cx - 1, cy - 1, cx + 1, cy + 1)))
    g0, g1, g2, g3 = glyph_box
    sub, _, _ = R.crop('luma', x + g0, y + g1, x + g2, y + g3)
    ref = float(np.percentile(sub, 98)) if sub.size else 0.0
    ref = max(ref, max(vals))
    if ref < 50:
        return None, vals
    code = 0
    for v in vals:
        code = code * 2 + (1 if v > 0.4 * ref else 0)
    return code, [round(v, 1) for v in vals]


def pink_span(R, x0, x1, y0, y1):
    """Outer left/right edges (band px) of the pink cell outlines in [x0,x1] x [y0,y1]."""
    lines = R.lines_in('pink', 'v', x0, y0 + 2, x1, y1 - 2, x0, x1, min_frac=0.35, pct=50)
    if not lines:
        return None
    return min(lines) - 0.5, max(lines) + 0.5, lines


def lines_hv(R, ch, x0, y0, x1, y1):
    v = R.lines_in(ch, 'v', x0, y0 + 3, x1, y1 - 3, x0, x1, min_frac=0.35, pct=50)
    h = R.lines_in(ch, 'h', x0 + 3, y0, x1 - 3, y1, y0, y1, min_frac=0.35, pct=50)
    return v, h


# ---------------------------------------------------------------------------------------------
# per-sample measurements
# ---------------------------------------------------------------------------------------------
def m_number(R, s, L):
    cw = L['cells']['digit']['w']
    y = s['y']
    x0, x1 = s['region']
    sp = s['spacing']
    span = pink_span(R, max(0, x0), min(L['screen']['w'], x1), y, y + L['cells']['digit']['h'])
    if not span:
        return {'error': 'no digit cells found'}
    left, right, _ = span
    w = right - left
    n = max(1, int(round((w + sp) / (cw + sp))))
    vals = []
    for i in range(n):
        c, raw = read_code(R, left + i * (cw + sp), y, L['cells']['digit']['bits_at'], (2, 3, cw - 2, 17), L)
        vals.append(c)
    digits = ''.join('-' if v == L['cells']['minus_code'] else ('?' if v is None or v > 9 else str(v)) for v in vals)
    out = {'left': round(left, 2), 'right': round(right, 2), 'width': round(w, 2), 'cells': n, 'digits': digits,
           'value': int(digits) if digits.isdigit() else None}
    x, cnt = s['x'], s['count']
    width = n * cw + (n - 1) * sp
    slot = cnt * cw + (cnt - 1) * sp
    hyp = {'anchor_left': x, 'anchor_centre': x - width / 2, 'anchor_right': x - width,
           'box_centre': x + (slot - width) / 2, 'box_right': x + slot - width}
    ds = {k: round(abs(left - v), 2) for k, v in hyp.items()}
    best = min(ds, key=ds.get)
    ties = sorted(k for k, d in ds.items() if d - ds[best] < 1.0)
    out.update({'verdict': '|'.join(ties), 'distances': ds})
    if s.get('unit'):
        g = R.lines_in('green', 'v', right - 2, y + 2, min(L['screen']['w'], right + 40), y + 30, right - 2, min(L['screen']['w'], right + 40), min_frac=0.35)
        if g:
            out['unit_left'] = round(min(g) - 0.5, 2)
            out['unit_gap'] = round(min(g) - 0.5 - right, 2)
    return out


def m_imagelist(R, s, L):
    fw, fh = L['cells']['frame']['w'], L['cells']['frame']['h']
    span = pink_span(R, max(0, s['x'] - 8), min(L['screen']['w'], s['x'] + fw + 8), s['y'], s['y'] + fh)
    if not span or span[1] - span[0] < fw * 0.6:
        return {'shown': None, 'note': 'no frame drawn'}
    left = span[0]
    c, raw = read_code(R, left, s['y'], L['cells']['frame']['bits_at'], (3, 8, 40, 24), L)
    if c is None or c >= len(s['values']):
        return {'shown': None, 'code': c, 'error': 'frame drawn but its index is unreadable'}
    return {'shown': c, 'value': s['values'][c], 'label': s['labels'][c], 'left': round(left, 2), 'dx': round(left - s['x'], 2)}


def m_digits(R, s, L):
    cw = L['cells']['digit']['w']
    vals = []
    for i in range(s['n']):
        c, _ = read_code(R, s['x'] + i * cw, s['y'], L['cells']['digit']['bits_at'], (2, 3, cw - 2, 17), L)
        vals.append(c)
    if any(v is None for v in vals):
        return {'value': None, 'codes': vals, 'note': 'not drawn (or not readable)'}
    if any(v > 9 for v in vals):
        return {'value': None, 'codes': vals, 'error': 'unreadable digit'}
    return {'value': int(''.join(map(str, vals)))}


def m_status(R, s, L):
    b = s['box']
    rgb = mean_rgb(R, b['x'] + 1.5, b['y'] + 1.5, b['x'] + b['w'] - 1.5, b['y'] + b['h'] - 1.5)
    r_, g_, b_ = rgb
    if max(rgb) < 40:
        st = 'not_drawn'
    elif g_ >= r_ and g_ >= b_:
        st = 'ok'            # green (the camera may shift it towards cyan)
    elif r_ >= g_ and b_ > 0.35 * r_:
        st = 'error'         # pink
    else:
        st = 'unclear:' + cname(rgb)
    return {'status': st, 'rgb': [round(v) for v in rgb]}


def m_presence(R, s, L):
    b = s['box']
    if s.get('colour'):
        rgb = mean_rgb(R, b['x'] + 3, b['y'] + 3, b['x'] + b['w'] - 3, b['y'] + b['h'] - 3)
        return {'present': cname(rgb) == s['colour'], 'colour': cname(rgb), 'rgb': [round(v) for v in rgb]}
    sub, _, _ = R.crop('luma', b['x'], b['y'], b['x'] + b['w'], b['y'] + b['h'])
    pk = float(np.percentile(sub, 99.5)) if sub.size else 0.0
    return {'present': pk > 80, 'peak_luma': round(pk, 1)}


def m_tile(R, s, L):
    b = s['box']
    x, y, t = b['x'], b['y'], b['w']
    if s.get('zoom_test'):
        sub, oy, ox = R.crop('any', x - 20, y - 20, x + t + 20, y + t + 20)
        m = sub > max(60.0, 0.5 * float(np.percentile(sub, 99.5)))
        if not m.any():
            return {'verdict': 'missing'}
        ys, xs = np.nonzero(m)
        w, h = (xs.max() - xs.min() + 1) / S, (ys.max() - ys.min() + 1) / S
        return {'verdict': 'scaled' if w > 1.5 * t else 'not_scaled', 'drawn_w': round(w, 1), 'drawn_h': round(h, 1)}
    q = {'tl': (x + 3, y + 3), 'tr': (x + t - 9, y + 3), 'bl': (x + 3, y + t - 9), 'br': (x + t - 9, y + t - 9)}
    got = {k: cname(mean_rgb(R, a, c, a + 6, c + 6)) for k, (a, c) in q.items()}
    lum = {k: round(luma(mean_rgb(R, a, c, a + 6, c + 6)), 1) for k, (a, c) in q.items()}
    crgb = mean_rgb(R, x + 14, y + 14, x + 18, y + 18)
    # the 8 px hole picks up blur from the quadrants around it: black = well below the white quadrant
    centre = 'black' if luma(crgb) < 0.3 * max(lum['tl'], 1) and cname(crgb) != 'cyan' else cname(crgb)
    exp = s['expect']
    if all(v == 'black' for v in got.values()) and centre == 'black':
        verdict = 'missing'
    elif exp == 'grey':
        order = lum['tl'] > lum['bl'] > lum['tr'] >= lum['br']
        # the camera tints the band's greys bluish (and clips its white), so "neutral" = no quadrant
        # reads as one of the tile's real colours, and the luma order and spread are a grey's
        neutral = not any(v in ('red', 'green', 'pink', 'yellow') for v in got.values()) and lum['tl'] > 2.5 * max(lum['br'], 1)
        verdict = 'correct' if order and neutral else 'garbled'
    elif got == {'tl': 'white', 'tr': 'red', 'bl': 'green', 'br': 'blue'}:
        verdict = 'correct'
    elif got == {'tl': 'white', 'tr': 'blue', 'bl': 'green', 'br': 'red'}:
        verdict = 'rb_swapped'
    else:
        verdict = 'garbled'
    alpha = {'black': 'honoured', 'cyan': 'ignored'}.get(centre, 'other:' + centre)
    if exp == 'rgb':
        alpha = 'n/a (no alpha)' if centre == 'cyan' else 'other:' + centre
    return {'verdict': verdict, 'quadrants': got, 'lumas': lum, 'centre': centre, 'alpha': alpha}


def m_blend(R, s, L):
    b = s['box']
    got = np.array(mean_rgb(R, b['x'] + 8, b['y'] + 8, b['x'] + b['w'] - 8, b['y'] + b['h'] - 8))
    wr = s['white_ref']
    white = np.array(mean_rgb(R, wr['x'] + 2, wr['y'] + 2, wr['x'] + wr['w'] - 2, wr['y'] + wr['h'] - 2))
    norm = got / np.maximum(white, 1) * 255
    a = s['alpha'] / 255
    over, top = np.array(s['over'], float), np.array(s['top'], float)
    hyp = {'blend': a * top + (1 - a) * over, 'opaque': top, 'missing': over, 'over_black': a * top}
    ds = {k: round(float(np.linalg.norm(norm - v)), 1) for k, v in hyp.items()}
    best = min(ds, key=ds.get)
    return {'verdict': best, 'distances': ds, 'normalised_rgb': [round(float(v)) for v in norm]}


def m_target(R, s, L):
    b = s['box']
    v, h = lines_hv(R, 'pink', b['x'] - 6, b['y'] - 6, b['x'] + b['w'] + 6, b['y'] + b['h'] + 6)
    if len(v) < 2 or len(h) < 2:
        return {'error': 'target not found'}
    left, top = min(v) - 0.5, min(h) - 0.5
    return {'left': round(left, 2), 'top': round(top, 2), 'w': round(max(v) - min(v) + 1, 2), 'h': round(max(h) - min(h) + 1, 2),
            'dx': round(left - b['x'], 2), 'dy': round(top - b['y'], 2)}


def m_capsule_end(R, s, L, bloom=0.0):
    W = L['screen']['w']
    y0, y1 = s['rows']
    pts = []
    lum = R.sc['luma']
    level = float(np.median(lum[int((y0 + y1) / 2 * S), int((W / 2 - 10) * S):int((W / 2 + 10) * S)]))
    if level < 60:
        return {'error': 'end fill not visible'}
    h = level / 2
    for i in range(int(y0 * S), int(y1 * S), S // 2):
        row = lum[i]
        on = np.nonzero(row > h)[0]
        if not len(on):
            continue
        a, b = on[0], on[-1]
        fa = (row[a] - h) / (row[a] - row[a - 1]) if a > 0 and row[a] > row[a - 1] else 0.0
        fb = (row[b] - h) / (row[b] - row[b + 1]) if b + 1 < len(row) and row[b] > row[b + 1] else 1.0
        yy = (i + 0.5) / S
        pts.append(((a - min(max(fa, 0), 1) + 0.5) / S, yy))
        pts.append(((b + min(max(fb, 0), 1) + 0.5) / S, yy))
    P = np.array(pts, float)
    if len(P) < 20:
        return {'error': 'too few edge points'}
    A = np.c_[2 * P[:, 0], 2 * P[:, 1], np.ones(len(P))]
    cx, cy, c = np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)[0]
    r = math.sqrt(max(c + cx * cx + cy * cy, 0))
    res = np.hypot(P[:, 0] - cx, P[:, 1] - cy) - r
    r_true = r - bloom
    out = {'cx': round(cx, 2), 'cy': round(cy, 2), 'r': round(r_true, 2), 'r_raw': round(r, 2), 'points': len(P),
           'fit_rms_px': round(float(np.sqrt((res ** 2).mean())), 3), 'expect': s['expect']}
    if s['end'] == 'top':
        out['hidden_top_px'] = round(cy - r_true, 2)
    else:
        out['hidden_bottom_px'] = round(L['screen']['h'] - (cy + r_true), 2)
    out['hidden_left_px'] = round(cx - r_true, 2)
    out['hidden_right_px'] = round(W - (cx + r_true), 2)
    return out


def m_comb(R, s, L):
    r = vm.measure_comb(R, s)
    k = s['xs'].index(s['centre_x']) if s.get('centre_x') in s['xs'] else None
    if k is not None:
        r['centre_hidden_px'] = r['per_line'][k]
    return r


def m_overlay(R, s, L):
    x0, y0, x1, y1 = s['region']
    sub, oy, ox = R.crop('any', x0, y0, x1, y1)   # max channel: a red dot has little luma
    bg = float(np.percentile(sub, 50))
    m = sub > bg + 45
    from scipy import ndimage as ndi
    m = ndi.binary_opening(m, structure=np.ones((3, 3)))
    # only pixels 4 px inside the visible screen: the bezel and the glass edge catch light
    yy, xx = np.mgrid[0:sub.shape[0], 0:sub.shape[1]]
    m &= inside_screen(L, ox + (xx + 0.5) / S, oy + (yy + 0.5) / S, 4)
    lab, k = ndi.label(m)
    boxes, rejected = [], 0
    for i, sl in enumerate(ndi.find_objects(lab)):
        area = int((lab[sl] == i + 1).sum())
        if area < 12 * S * S:   # glints on the glass are a few px; the Band 11's red dot is ~300 px^2
            continue
        w, h = (sl[1].stop - sl[1].start) / S, (sl[0].stop - sl[0].start) / S
        # a status dot / icon is compact; specular glare on the glass is a long thin arc
        if max(w, h) > 24 or min(w, h) < 0.5 * max(w, h) or area / (w * h * S * S) < 0.4:
            rejected += 1
            continue
        boxes.append([ox + sl[1].start / S, oy + sl[0].start / S, ox + sl[1].stop / S, oy + sl[0].stop / S, area / (S * S)])
    if not boxes:
        return {'found': False, 'rejected_glare_blobs': rejected}
    bb = max(boxes, key=lambda b: b[4])[:4]   # the main thing drawn (a status dot); others listed
    rgb = mean_rgb(R, bb[0], bb[1], bb[2], bb[3])
    return {'found': True, 'bbox': [round(v, 1) for v in bb], 'blobs': [[round(v, 1) for v in b] for b in boxes], 'colour': cname(rgb),
            'centre': [round((bb[0] + bb[2]) / 2, 1), round((bb[1] + bb[3]) / 2, 1)], 'size': [round(bb[2] - bb[0], 1), round(bb[3] - bb[1], 1)]}


def inside_screen(L, x, y, inset=0.0):
    """Boolean array: band points (x, y) at least `inset` px inside the nominal screen shape."""
    W, H, r = L['screen']['w'], L['screen']['h'], L['screen']['r']
    if L['screen']['shape'] in ('capsule', 'circle'):
        r = W / 2
    cx = np.clip(x, r, W - r)
    cy = np.clip(y, r, H - r)
    return np.hypot(x - cx, y - cy) <= r - inset


def ruler_edges(R, L, bloom):
    """Visible screen edge from the outer ends of the ruler ticks on the straight part of the screen."""
    W = L['screen']['w']
    rx0, rx1, ry0 = vm.ruler_geom(L)
    if not L['screen'].get('straight_rows') or rx0 > 0 or rx1 < W:
        # a circle: the rulers are drawn inside the screen, so their ends are not its edges (F1's round fit is)
        return {'left': None, 'right': None, 'rows': 0}
    a, b = L['screen']['straight_rows']
    lum = R.sc['luma']
    left, right = [], []
    for i, t in enumerate(L['frame']['ticks']):
        y = ry0 + i * L['frame']['tick_every']
        if not a <= y <= b:
            continue
        ln = L['frame']['tick_len'][t]
        row = lum[y * S:(y + 1) * S].max(axis=0)
        seg = row[: int((ln + 2) * S)]
        if seg.max() > 60:
            on = np.nonzero(seg > seg.max() / 2)[0]
            left.append(on[0] / S)
        seg = row[int((W - ln - 2) * S):]
        if seg.max() > 60:
            on = np.nonzero(seg > seg.max() / 2)[0]
            right.append(W - (W - ln - 2 + (on[-1] + 1) / S))
    fix = lambda v: 0.0 if v < 0.25 else v + bloom
    return {'left': round(fix(float(np.median(left))), 2) if left else None,
            'right': round(fix(float(np.median(right))), 2) if right else None, 'rows': len(left)}


MEASURE = {'number': m_number, 'imagelist': m_imagelist, 'digits': m_digits, 'status': m_status, 'presence': m_presence,
           'tile': m_tile, 'blend': m_blend, 'target': m_target, 'comb': m_comb, 'overlay': m_overlay,
           'corner': lambda R, s, L: vm.measure_corner(R, s), 'swatch': lambda R, s, L: vm.measure_swatch(R, s),
           'round': lambda R, s, L: vm.measure_round(R, s),
           'ramp': lambda R, s, L: vm.measure_ramp(R, s)}


def isolate_screen(img, aspect=2.45):
    """Blank everything outside the band's screen: the photo's background can outscore the rulers on
    "yellow" (a tan table, an orange frame in daylight, Band 11 round 2, 2026-09-29), and vm.Fit's
    thresholds are percentiles of the whole photo. The screen is the largest dark region (black panel +
    bezel) with the content holes filled; the mask is its convex hull. Returns
    (image, found)."""
    expect = aspect
    small = cv2.resize(img, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    lum = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY), (0, 0), 2)
    dark = (lum < 55).astype(np.uint8)
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(dark, 8)
    best, score = None, 0.0
    H, W = lum.shape
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a < 0.01 * H * W or x == 0 or y == 0 or x + w >= W or y + h >= H:
            continue                                  # tiny, or touching the photo edge (background)
        comp = (lab[y:y + h, x:x + w] == i).astype(np.uint8)
        cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        hull = cv2.convexHull(max(cnts, key=cv2.contourArea))
        solidity = a / max(cv2.contourArea(hull), 1)
        (_, _), (rw, rh), _ = cv2.minAreaRect(hull)
        aspect = max(rw, rh) / max(1, min(rw, rh))
        # the band's dark region (screen + bezel) roughly has the screen's aspect: a tall band 1.2-3.5,
        # a round or square watch 1.0-1.5
        lo, hi = (1.2, 3.5) if expect > 1.3 else (1.0, 1.5)
        sc = cv2.contourArea(hull) * (1.0 if lo < aspect < hi else 0.2) * (0.5 + min(solidity, 1))
        if sc > score:
            best, score = (x, y, hull), sc
    if best is None:
        return img, False
    x, y, hull = best
    hull = (hull + np.array([x, y])).astype(np.float32)
    c = hull.reshape(-1, 2).mean(0)
    hull = ((hull - c) * 1.0 + c) * 4   # no growth: the dark region already includes the bezel, and any white
                                         # case let in lifts vm.Fit's brightness percentile above dim AOD ticks
    mask = np.zeros(img.shape[:2], np.uint8)
    cv2.fillPoly(mask, [hull.astype(np.int32)], 1)
    return img * mask[..., None], True


ROTATIONS = {None: None, 'cw90': cv2.ROTATE_90_CLOCKWISE, 'ccw90': cv2.ROTATE_90_COUNTERCLOCKWISE, '180': cv2.ROTATE_180}


def exif_exposure(path):
    try:
        ex = Image.open(path).getexif().get_ifd(0x8769)
        return {'t': float(ex.get(33434)) if ex.get(33434) else None, 'iso': ex.get(34855), 'f': float(ex.get(33437)) if ex.get(33437) else None}
    except Exception:
        return {}


def exif_time(path):
    try:
        ex = Image.open(path).getexif()
        v = ex.get_ifd(0x8769).get(36867) or ex.get(306)
        return datetime.datetime.strptime(v, '%Y:%m:%d %H:%M:%S').isoformat() if v else None
    except Exception:
        return None


def measure_photo(path, L, page_id=None, annotate_dir=None):
    img0 = vm.load_photo(path)
    bars = []
    for p in L['pages']:
        if p['bar'] not in bars:
            bars.append(p['bar'])
    if page_id is not None:
        bars = [next(p for p in L['pages'] if p['id'] == page_id)['bar']]
    # vm.Fit takes the scale bar's direction from PCA and forces it to point right in the photo
    # (u[0] > 0), so it assumes a roughly upright band. With the band lying sideways the bar is
    # vertical, u[0] ~ 0, and the sign (so the whole similarity) flips with the slightest tilt: the
    # fit then locks onto the wrong ticks (Band 11 photos 2026-09-29, F2-F5). So try the photo in
    # all four orientations and keep the best fit; the page barcode must read in the chosen one.
    best, errors = None, []
    candidates = [img0]
    iso, found = isolate_screen(img0, max(L['screen']['w'], L['screen']['h']) / min(L['screen']['w'], L['screen']['h']))
    if found:
        candidates.append(iso)
    for rot, base in [(r, b) for b in candidates for r in ROTATIONS]:
        img0_ = base
        img = img0_ if rot is None else np.ascontiguousarray(cv2.rotate(img0_, ROTATIONS[rot]))
        for bar in bars:
            try:
                f = vm.Fit(img, L, bar).run()
            except RuntimeError as e:
                errors.append('%s: %s' % (rot or 'as is', e))
                continue
            f.rotation = (rot or 'none') + (' (screen isolated)' if base is not img0 else '')
            # the mask only guides the fit: rectify the unmasked photo (the mask can clip the top strip)
            f.img = img0 if rot is None else np.ascontiguousarray(cv2.rotate(img0, ROTATIONS[rot]))
            if best is None or (f.ok, f.n_ticks, -max(f.rms)) > (best.ok, best.n_ticks, -max(best.rms)):
                best = f
    if best is None:
        return {'photo': os.path.basename(path), 'error': '; '.join(errors)}
    f = best
    R = vm.Rect(f.rectify())
    R.bloom = f.bloom  # measure_round takes the bloom out of the round edge
    pid = page_id
    if pid is None:
        for p in L['pages']:
            if p['bar'] != f.bar_spec:
                continue
            got = vm.read_barcode(R, p['code'])
            if got is not None:
                pid = got
                break
    fit = vm._fit_info(f)
    fit['rotation'] = f.rotation
    if pid is None:
        return {'photo': os.path.basename(path), 'error': 'page barcode not readable; pass --page N', 'fit': fit}
    page = next((p for p in L['pages'] if p['id'] == pid), None)
    if page is None:
        return {'photo': os.path.basename(path), 'error': 'page %d not in the layout' % pid, 'fit': fit}
    out = {'exposure': exif_exposure(path), 'photo': os.path.basename(path), 'page': pid, 'page_key': page['key'], 'face': page['face'], 'theme': page['theme'],
           'taken_at': exif_time(path), 'fit': fit, 'ruler_edges': ruler_edges(R, L, f.bloom), 'samples': []}
    samples_ = list(page['samples'])
    if page['theme'] == 'normal' and page['id'] != 1 and not any(s['type'] == 'overlay' for s in samples_):
        samples_.append({'id': page['key'] + '.top', 'type': 'overlay', 'region': [24, 0, L['screen']['w'] - 24, 42]})
    for s in samples_:
        if s['type'] == 'ruler_edges':
            continue
        try:
            if s['type'] == 'capsule_end':
                r = m_capsule_end(R, s, L, f.bloom)
            else:
                r = MEASURE[s['type']](R, s, L)
        except Exception as e:
            r = {'error': '%s: %s' % (type(e).__name__, e)}
        out['samples'].append({'id': s['id'], 'type': s['type'], 'spec': s, 'result': r})
    if annotate_dir:
        os.makedirs(annotate_dir, exist_ok=True)
        small = cv2.resize(R.img, (R.img.shape[1] // 2, R.img.shape[0] // 2), interpolation=cv2.INTER_AREA)
        Image.fromarray(small).save(os.path.join(annotate_dir, os.path.splitext(os.path.basename(path))[0] + '.rect.png'))
    return json.loads(json.dumps(out, default=vm._plain))


# ---------------------------------------------------------------------------------------------
# results -> face facts
# ---------------------------------------------------------------------------------------------
def apply_face(face, results, L):
    """Merge page results (newest per page) into the face section dict. Returns the paths written."""
    written = []
    ok = [r for r in results if 'samples' in r and r['fit']['ok']]

    def src(pred):
        ps = sorted({r['photo'] for r in ok if pred(r)})
        return 'face-calib photos ' + ', '.join(ps)

    def put(path, value, pages, extra=None, status='measured'):
        parent, key = vm.get_path(face, path, create=True)
        old = parent.get(key)
        if isinstance(old, dict) and old.get('status') == 'measured' and not str(old.get('source', '')).startswith('face-calib photos'):
            # an observation recorded with `set` (watched on the band): keep it, attach what the photo says
            old['photo_check'] = {'value': value, 'source': src(lambda r: r['page'] in pages), **(extra or {})}
            return
        vm.set_fact(face, path, value, src(lambda r: r['page'] in pages), status=status, extra=extra)
        written.append(path if isinstance(path, str) else '.'.join(path))

    def samples(page_ids, typ=None):
        return [(r, s) for r in ok if r['page'] in page_ids for s in r['samples'] if (typ is None or s['type'] == typ) and 'error' not in s['result']]

    def one(page_id, pred):
        for r, s in samples([page_id]):
            if pred(s):
                return s['result']
        return None

    byid = {r['page']: r for r in ok}
    normal_pages = [p['id'] for p in L['pages'] if p['theme'] == 'normal']
    # ---- screen
    re_ = [r['ruler_edges'] for r in ok if r['page'] in normal_pages]
    for side in ('left', 'right'):
        v = [e[side] for e in re_ if e.get(side) is not None]
        if v:
            put('screen.hidden_px.' + side, round(float(np.median(v)), 2), normal_pages,
                {'note': 'outer ends of the ruler ticks on the straight part of the screen, bloom-corrected, +-1 px'})
    for r, s in samples([1], 'comb'):
        v = s['result'].get('centre_hidden_px')
        if v is not None:
            put('screen.hidden_px.' + s['spec']['edge'], round(v, 2), [1], {'per_line': s['result']['per_line'], 'note': 'comb line at the screen centre'})
    ends = {s['spec']['end']: s['result'] for r, s in samples([1], 'capsule_end')}
    if ends:
        put('screen.corner_radius_px', {k: v['r'] for k, v in ends.items()}, [1], {'note': 'capsule: radius of each semicircular end (circle fit to the lit fill)'})
        put('screen.capsule_ends', ends, [1])
    rnd = [s['result'] for r, s in samples([1], 'round')]
    if rnd:
        rad = round(float(np.median([v['radius_px'] for v in rnd])), 2)
        put('screen.corner_radius_px', {k: rad for k in ('tl', 'tr', 'bl', 'br')}, [1], {'note': 'circle: one radius (circle fit to the lit fills), given per corner'})
        put('screen.round_edge', rnd[-1], [1])
        for side in ('left', 'right', 'top', 'bottom'):
            put('screen.hidden_px.' + side, round(float(np.median([v['hidden_%s_px' % side] for v in rnd])), 2), [1],
                {'note': 'from the circle fit on F1 (centre -+ radius against the canvas edges)'})
    cs = {s['spec']['corner']: s['result'] for r, s in samples([1], 'corner')}
    if cs:
        put('screen.corner_radius_px', {k: v.get('radius_px') for k, v in cs.items()}, [1])
        put('screen.corner_detail', cs, [1])
    ov = [(r['page'], s['result']) for r, s in samples(normal_pages, 'overlay')]
    if ov:
        found = [(p, o) for p, o in ov if o.get('found')]
        put('screen.status_overlay', {'pages_checked': sorted(p for p, _ in ov), 'found_on': {str(p): o for p, o in found}}, [p for p, _ in ov],
            {'note': 'lit pixels in the top strip, which every page leaves black; confirm by eye (glare can trip it)'})
        if found:
            put('screen.status_clear_top_px', int(math.ceil(max(o['bbox'][3] for _, o in found))), [p for p, _ in found],
                {'note': 'bottom of what the system drew in the top strip'})
    # ---- colour
    sw = samples([2], 'swatch')
    if sw:
        # Each grey ramp is judged against its own #000 swatch; colour ramps and surfaces against the
        # median black of the three grey ramps. Threshold max(6, 2 sd): 4 sd let glare on one black
        # swatch hide a clearly lit #10 (Band 11 photo 2026-09-29, background ramp black 21.5 sd 5.7).
        zero = {s['spec']['group']: s['result'] for r, s in sw if s['spec']['value'] == 0 and s['spec']['group'].startswith('grey')}
        gbase = float(np.median([z['luma'] for z in zero.values()])) if zero else 0.0
        gsd = float(np.median([z['sd'] for z in zero.values()])) if zero else 1.0
        floors = {}
        for group in ('grey', 'grey_rgba32', 'grey_lua', 'red', 'green', 'blue', 'surface'):
            g = sorted([s for r, s in sw if s['spec']['group'] == group], key=lambda s: s['spec']['value'])
            if not g:
                continue
            base, sd = (zero[group]['luma'], zero[group]['sd']) if group in zero else (gbase, gsd)
            thr = max(6.0, 2 * sd)
            vis = [s['spec']['value'] for s in g if s['result']['luma'] - base > thr]
            floor = min(vis) if vis else None
            floors[group] = floor
            put('colour.floor.' + ('grey_background' if group == 'grey' else group), floor, [2],
                {'lumas': {s['spec']['hex']: s['result']['luma'] for s in g}, 'black_luma': round(base, 1),
                 'threshold': round(thr, 1), 'note': 'lowest channel value the camera saw above black; confirm by eye'})
        gf = [floors[k] for k in ('grey', 'grey_rgba32', 'grey_lua') if floors.get(k) is not None]
        if gf:
            put('colour.floor.grey', min(gf), [2], {'per_ramp': {k: floors.get(k) for k in ('grey', 'grey_rgba32', 'grey_lua')},
                                                   'note': 'lowest of the three grey ramps (background image, BGRA32 image, Lua fills); same panel, so glare on one ramp does not count; confirm by eye'})
    # ---- images
    for r, s in samples([3]):
        sp, res = s['spec'], s['result']
        if s['type'] == 'tile' and sp['layer'] == 'widget':
            put('image.encoding.' + sp['variant'], res['verdict'], [3], {'alpha': res.get('alpha'), 'detail': res})
        elif s['type'] == 'blend':
            put('image.alpha_over_element', res['verdict'], [3], {'detail': res})
        elif s['type'] == 'ramp':
            put('image.alpha_over_black', 'matches_opaque_grey' if res['rms_diff'] < 12 else 'differs', [3], {'detail': res})
    fmt = {s['spec']['variant']: {'verdict': s['result']['verdict'], 'alpha': s['result'].get('alpha')}
           for r, s in samples([3], 'tile') if s['spec']['layer'] == 'lua' and not s['spec'].get('zoom_test')}
    if fmt:
        works = sorted(k for k, v in fmt.items() if v['verdict'] == 'correct')
        put('lua.image_format', works, [3], {'per_format': fmt, 'note': 'formats the Lua layer drew correctly (tile quadrants and alpha hole checked)'})
    zm = {s['spec']['variant'].split('_')[2]: s['result']['verdict'] for r, s in samples([3], 'tile') if s['spec'].get('zoom_test')}
    if zm:
        put('lua.image_zoom', zm, [3], {'note': 'Image:set{zoom=512} / set{scale=512} on a 32 px PNG: scaled means it drew ~64 px'})
    # ---- Lua API status squares, placement, values
    lua_pages = [2, 3, 6, 9]
    st = {}
    for r, s in samples(lua_pages, 'status'):
        st.setdefault(s['spec']['test'], s['result']['status'])
    if st:
        put('lua.api_status', st, lua_pages, {'note': 'ok = the pcall returned; error = it raised; not_drawn = the script never got there (or did not run)'})
        if 'alive' in st:
            put('lua.runs', st['alive'] == 'ok', lua_pages)
    tg = samples([6], 'target')
    for layer, path in (('lua', 'lua.placement_offset_px'), ('widget', 'widgets.placement_offset_px')):
        d = [s['result'] for r, s in tg if s['spec']['layer'] == layer]
        if d:
            put(path, {'dx': round(float(np.mean([v['dx'] for v in d])), 2), 'dy': round(float(np.mean([v['dy'] for v in d])), 2)}, [6],
                {'note': 'drawn position minus the requested x, y (band px, +-0.5)'})
    dg = {s['spec']['what']: s['result'].get('value') for r, s in samples([6], 'digits')}
    if dg.get('hor_res') is not None or dg.get('ver_res') is not None:
        put('lua.canvas_px', {'w': dg.get('hor_res'), 'h': dg.get('ver_res')}, [6], {'note': 'lvgl.HOR_RES() / VER_RES() as the Lua layer reports them'})
    wn = {s['spec']['source']: s['result'].get('value') for r, s in samples([6], 'number')}
    if dg.get('minute') is not None and dg.get('raw_minute_low') is not None and dg['minute'] % 10:
        put('lua.dataman_scale', round(dg['raw_minute_low'] / (dg['minute'] % 10), 3), [6], {'raw_minute_low': dg['raw_minute_low'], 'minute': dg['minute']})
    if dg.get('hour') is not None and wn.get('hour') is not None:
        put('lua.time_matches_widget', dg.get('hour') == wn.get('hour') and dg.get('minute') == wn.get('minute'), [6],
            {'lua': [dg.get('hour'), dg.get('minute')], 'widget': [wn.get('hour'), wn.get('minute')]})
    lab = one(6, lambda s: s['type'] == 'presence' and s['spec']['what'] == 'lua_label')
    if lab is not None:
        put('lua.label_draws', lab['present'], [6], {'detail': lab})
    fills = {s['spec']['hex']: s['result']['luma'] for r, s in samples([6], 'swatch')}
    if fills:
        put('lua.object_fill_lumas', fills, [6])
    if 10 in byid:
        lsq = one(10, lambda s: s['type'] == 'presence' and s['spec']['what'] == 'lua_square')
        wsq = one(10, lambda s: s['type'] == 'presence' and s['spec']['what'] == 'widget_square')
        if lsq is not None and wsq is not None and wsq['present']:
            put('lua.runs_on_aod', bool(lsq['present']), [10], {'widget_square': wsq, 'lua_square': lsq})
    # ---- number widgets
    nums = [(r, s) for r, s in samples([4], 'number')]
    rows = {s['spec']['row']: s for r, s in nums if s['spec']['source'] in ('steps', 'battery')}
    align = {}
    for k, name in ((0, 'left'), (1, 'center'), (2, 'right'), (3, 'battery_center')):
        if k in rows:
            res = rows[k]['result']
            align[name] = {'verdict': res['verdict'], 'cells': res['cells'], 'count': rows[k]['spec']['count'], 'value': res['value'], 'distances': res['distances']}
    if align:
        put('widgets.number.align', align, [4], {'note': 'anchor_* = x is the left/centre/right of the digits drawn; box_* = the digits are aligned inside a slot of `count` cells starting at x. Only told apart when fewer digits than `count` are drawn.'})
        c = align.get('center') or align.get('battery_center')
        if c and c['cells'] < c['count'] and '|' not in c['verdict']:
            put('widgets.number_anchor_fixed', c['verdict'] != 'anchor_centre', [4], {'centre_verdict': c['verdict']})
    if 0 in rows and rows[0]['result']['cells']:
        n0 = rows[0]['result']['cells']
        sp = {}
        for k in (5, 6):
            if k in rows and n0 > 1:
                w = rows[k]['result']['width']
                sp[str(rows[k]['spec']['spacing'])] = round((w - n0 * 16) / (n0 - 1), 2)
        if sp:
            put('widgets.number.spacing_px', sp, [4], {'note': 'requested spacing -> measured gap between cells; a huge gap for -3 means the byte is read unsigned'})
        v = rows[0]['result']['value']
        if v is not None:
            put('widgets.number.pads_to_count', n0 == rows[0]['spec']['count'] and len(str(v)) < n0, [4], {'steps': v, 'cells': n0})
    lz = {s['spec']['source']: s['result'] for r, s in nums if s['spec']['row'] == 4}
    if lz:
        put('widgets.number.leading_zero', {k: {'lz': [s for r, s in nums if s['spec']['row'] == 4 and s['spec']['source'] == k][0]['spec']['lz'],
                                                 'digits': v.get('digits')} for k, v in lz.items()}, [4])
    if 3 in rows and 'unit_gap' in rows[3]['result']:
        put('widgets.number.unit_gap_px', rows[3]['result']['unit_gap'], [4], {'note': 'gap between the last digit and the unit image'})
    # ---- image lists
    lv = {s['spec']['list']: s['result'] for r, s in samples([5], 'imagelist')}
    nv = {s['spec']['source']: s['result'].get('value') for r, s in samples([5], 'number')}
    bat = nv.get('battery')
    if lv and bat is not None:
        st_ = lv.get('batt-steps', {})
        vals = [0, 20, 40, 60, 80, 100]
        if st_.get('shown') is not None:
            v = st_['value']
            fl = max(x for x in vals if x <= bat)
            ce = min(x for x in vals if x >= bat)
            ne = min(vals, key=lambda x: (abs(x - bat), x))
            names = [n for n, e in (('floor', fl), ('ceil', ce), ('nearest', ne)) if e == v]
            put('widgets.image_list.fallback', '|'.join(names) or 'other', [5], {'battery': bat, 'frame_value': v,
                                                                               'note': 'several names = this battery value cannot tell them apart; retake at another charge'})
        elif 'batt-steps' in lv:
            put('widgets.image_list.fallback', 'exact_only' if bat not in vals else 'none_drawn', [5], {'battery': bat})
        if 'batt-below' in lv:
            put('widgets.image_list.below_first', 'nothing' if lv['batt-below'].get('shown') is None else 'frame %s' % lv['batt-below'].get('value'), [5], {'battery': bat})
        if 'batt-above' in lv:
            put('widgets.image_list.above_last', 'nothing' if lv['batt-above'].get('shown') is None else 'frame %s' % lv['batt-above'].get('value'), [5], {'battery': bat})
    if lv.get('steps-steps', {}).get('shown') is not None:
        put('widgets.image_list.u16_values', lv['steps-steps']['value'], [5], {'note': 'frame shown for steps with frames at 0/1000/5000/10000 (values above 255 work if not always 0)'})
    if lv:
        put('widgets.image_list_frames_same_size', True, [5], {'status_note': 'format rule: an image-list block has one width/height for all frames (parser/imageCodec.ts)'})
    # ---- data sources (checked against the photo's EXIF time)
    r5 = byid.get(5)
    if r5 and r5.get('taken_at'):
        t = datetime.datetime.fromisoformat(r5['taken_at'])
        wd = lv.get('weekday', {}).get('value')
        if wd is not None:
            put('data_sources.weekday_sunday_zero', wd == (t.weekday() + 1) % 7, [5], {'shown': wd, 'photo_weekday': t.strftime('%A')})
        mo = lv.get('month', {}).get('value')
        if mo is not None:
            put('data_sources.month_one_based', mo == t.month, [5], {'shown': mo, 'photo_month': t.month})
        h = nv.get('hour')
        if h is not None:
            put('data_sources.hour_observed', {'widget': h, 'photo_hour': t.hour, 'looks_12h': h != t.hour and h == (t.hour % 12 or 12)}, [5],
                {'note': 'record the band\'s 12/24-hour setting with `set data_sources.hour_follows_12_24_setting`'})
    # ---- always-on
    if 8 in byid:
        put('aod.shows', 'face_aod', [8], {'note': 'the photo of the dimmed band shows the face\'s own AOD view (barcode p8)'})
        g8 = sorted([s for r, s in samples([8], 'swatch') if s['spec']['group'] == 'aod_grey'], key=lambda s: s['spec']['value'])
        if g8:
            base = g8[0]['result']['luma']
            thr = max(4.0, 4 * g8[0]['result']['sd'])
            vis = [s['spec']['value'] for s in g8 if s['result']['luma'] - base > thr]
            put('aod.colour_floor_grey', min(vis) if vis else None, [8], {'lumas': {s['spec']['hex']: s['result']['luma'] for s in g8}})
        n8 = {s['spec']['source']: s['result'].get('value') for r, s in samples([8], 'number')}
        put('aod.number_widgets', n8, [8], {'note': 'values the AOD number widgets drew'})
        if 7 in byid:
            l7 = {s['spec']['hex']: s['result']['luma'] for r, s in samples([7], 'swatch') if s['spec']['group'] == 'aod_level'}
            l8 = {s['spec']['hex']: s['result']['luma'] for r, s in samples([8], 'swatch') if s['spec']['group'] == 'aod_level'}
            rat = {k: round(l8[k] / l7[k], 3) for k in l7 if k in l8 and l7[k] > 20 and k != '#ffffff'}
            e7, e8 = byid[7].get('exposure') or {}, byid[8].get('exposure') or {}
            ev = lambda e: (e.get('t') or 0) * (e.get('iso') or 0) / max(e.get('f') or 1, 1e-3) ** 2
            no_exif = ev(e7) == 0 and ev(e8) == 0      # synthetic / stripped photos: can't check, assume locked
            same = no_exif or (ev(e7) > 0 and abs(ev(e8) / ev(e7) - 1) < 0.05)
            shape = {p: {k: round(v / max(l['#ffffff'], 1), 3) for k, v in l.items()} for p, l in (('normal', l7), ('aod', l8)) if '#ffffff' in l}
            if rat and same:
                put('aod.dim_ratio', round(float(np.mean(list(rat.values()))), 3), [7, 8],
                    {'per_level': rat, 'exposure': [e7, e8], 'level_shape': shape, 'note': 'AOD luma / normal luma of the same swatch (exposure equal in EXIF)'})
            elif rat:
                put('aod.dim_ratio', None, [7, 8], {'raw_ratio_unusable': rat, 'exposure': [e7, e8], 'level_shape': shape,
                    'note': 'exposure differs between the two photos (EXIF time x ISO / f^2), so the ratio is not the dimming. '
                            'level_shape (each swatch / #ffffff within one photo) is still valid. Retake F7 with exposure locked.'}, status='unknown')
    return written


# ---------------------------------------------------------------------------------------------
# profile files
# ---------------------------------------------------------------------------------------------
FACE_FACTS = [
    'screen.hidden_px.left', 'screen.hidden_px.right', 'screen.hidden_px.top', 'screen.hidden_px.bottom',
    'screen.corner_radius_px', 'screen.status_overlay', 'screen.status_clear_top_px',
    'colour.floor.grey', 'colour.floor.grey_background', 'colour.floor.grey_rgba32', 'colour.floor.grey_lua', 'colour.floor.red', 'colour.floor.green',
    'colour.floor.blue', 'colour.floor.surface',
    'image.encoding.png_indexed', 'image.encoding.png_rgba32', 'image.alpha_over_black', 'image.alpha_over_element',
    'lua.runs', 'lua.image_format', 'lua.image_zoom', 'lua.api_status', 'lua.placement_offset_px', 'lua.canvas_px',
    'lua.dataman_scale', 'lua.time_matches_widget', 'lua.label_draws', 'lua.timer_runs', 'lua.runs_on_aod',
    'widgets.placement_offset_px', 'widgets.number.align', 'widgets.number_anchor_fixed', 'widgets.number.spacing_px',
    'widgets.number.pads_to_count', 'widgets.number.leading_zero', 'widgets.number.unit_gap_px', 'widgets.number.second_updates',
    'widgets.image_list.fallback', 'widgets.image_list.below_first', 'widgets.image_list.above_last', 'widgets.image_list.u16_values',
    'widgets.image_list_frames_same_size',
    'data_sources.weekday_sunday_zero', 'data_sources.month_one_based', 'data_sources.hour_observed',
    'data_sources.hour_follows_12_24_setting', 'data_sources.temperatureF_D031',
    'aod.shows', 'aod.dim_ratio', 'aod.colour_floor_grey', 'aod.number_widgets', 'aod.second_updates',
]


def profile_path(device, write=False):
    # Only the "face" key is ever written. Reading: the workspace profile, else the shipped default.
    # Writing: the workspace profile, first seeded from the shipped default when there is one.
    return ws.write_profile_path(device, WS) if write else ws.read_profile_path(device, WS)


def load_face(device, write=False):
    p = profile_path(device, write)
    if os.path.exists(p):
        with open(p) as f:
            doc = json.load(f)
    else:
        doc = {'schema': SCHEMA + ' (face section only)', 'device': device, 'face': {}}
    doc.setdefault('face', {})
    return doc


def save_doc(device, doc):
    p = profile_path(device, write=True)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if 'quickapp' not in doc:          # a face-only file; a full profile's other keys stay untouched
        doc['updated'] = datetime.date.today().isoformat()
    vm.save_json(p, doc)
    return p


def seed(face, source):
    n = 0
    for path in FACE_FACTS:
        parent, key = vm.get_path(face, path, create=True)
        if key not in parent:
            parent[key] = {'value': None, 'status': 'unknown', 'source': source, 'date': datetime.date.today().isoformat()}
            n += 1
    return n


# ---------------------------------------------------------------------------------------------
# synthetic self-test: render every page the way the face engine would, photograph it, measure it
# ---------------------------------------------------------------------------------------------
TRUTHS = [
    {'name': 'A', 'values': {'steps': 1234, 'battery': 57, 'hour': 9, 'minute': 5, 'second': 42, 'day': 28, 'weekday': 0, 'month': 9},
     'align': {'left': 'anchor_left', 'center': 'box_centre', 'right': 'box_right'}, 'fallback': 'floor',
     'floor': 0x30, 'dim': 0.5, 'dot': (None, 16, 5),
     'lua': {'png_rgba': 'correct', 'png8': 'correct', 'png_grey': 'correct', 'png_rgb': 'correct', 'v8_tca32': 'garbled',
             'v8_tca16': 'missing', 'v9_argb8888': 'correct', 'v9_rgb565': 'rb_swapped'},
     'zoom': {'zoom': 'scaled', 'scale': 'error'}, 'lua_on_aod': False, 'label': True},
    {'name': 'B', 'values': {'steps': 873, 'battery': 88, 'hour': 14, 'minute': 37, 'second': 3, 'day': 4, 'weekday': 3, 'month': 12},
     'align': {'left': 'anchor_left', 'center': 'anchor_centre', 'right': 'anchor_right'}, 'fallback': 'nearest',
     'floor': 0x40, 'dim': 0.35, 'dot': None,
     'lua': {'png_rgba': 'correct', 'png8': 'missing', 'png_grey': 'correct', 'png_rgb': 'correct', 'v8_tca32': 'correct',
             'v8_tca16': 'garbled', 'v9_argb8888': 'garbled', 'v9_rgb565': 'garbled'},
     'zoom': {'zoom': 'not_scaled', 'scale': 'scaled'}, 'lua_on_aod': True, 'label': False},
]


def _paste(canvas, rgba, x, y):
    h, w = rgba.shape[:2]
    H, W = canvas.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x0 >= x1 or y0 >= y1:
        return
    src = rgba[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
    a = src[..., 3:4] / 255
    canvas[y0:y1, x0:x1] = canvas[y0:y1, x0:x1] * (1 - a) + src[..., :3] * a


def _png(path):
    return np.asarray(Image.open(path).convert('RGBA'))


def render_page(L, face, page, truth, base=HERE):
    W, H = L['screen']['w'], L['screen']['h']
    d = os.path.join(base, face['project'])
    lay = json.load(open(os.path.join(d, 'layout.json')))
    theme = page['theme']
    cv = np.zeros((H, W, 3), np.float32)
    vals = truth['values']
    cw = L['cells']['digit']['w']
    for w in sorted(lay[theme]['widgets'], key=lambda w: w['z']):
        if w['type'] == 'image':
            _paste(cv, _png(os.path.join(d, w['asset'])), w['x'], w['y'])
        elif w['type'] == 'number':
            ds = lay['assets']['digitSets'][w['digitSet']]
            v = vals[w['source']]
            s = str(v).zfill(w['digits']) if w['leadingZero'] else str(v)
            n, sp = len(s), w['spacing']
            width = n * cw + (n - 1) * sp
            slot = w['digits'] * cw + (w['digits'] - 1) * sp
            rule = {'left': 'anchor_left'}.get(w['align']) or truth['align'][w['align']]
            left = {'anchor_left': w['x'], 'anchor_centre': w['x'] - width / 2, 'anchor_right': w['x'] - width,
                    'box_centre': w['x'] + (slot - width) / 2, 'box_right': w['x'] + slot - width}[rule]
            left = int(round(left))
            for i, ch in enumerate(s):
                _paste(cv, _png(os.path.join(d, ds['digits'][int(ch)])), left + i * (cw + sp), w['y'])
            if w.get('unitAsset'):
                _paste(cv, _png(os.path.join(d, w['unitAsset'])), left + width, w['y'])
        elif w['type'] == 'image-list':
            v = vals[w['source']]
            items = sorted(w['items'], key=lambda i: i['value'])
            iv = [i['value'] for i in items]
            if truth['fallback'] == 'floor':
                cand = [i for i in items if i['value'] <= v]
                it = cand[-1] if cand else None
            else:
                it = min(items, key=lambda i: (abs(i['value'] - v), i['value'])) if min(iv) <= v else None
            if it:
                _paste(cv, _png(os.path.join(d, it['asset'])), w['x'], w['y'])
    if face['lua_ops'] and (theme == 'normal' or (face['aod_script'] and truth['lua_on_aod'])):
        sd = os.path.join(d, 'script')
        ok, err = _png(os.path.join(sd, 'st_ok.png')), _png(os.path.join(sd, 'st_err.png'))
        rng = np.random.default_rng(7)
        for op in face['lua_ops']:
            sx, sy = op.get('status', (0, 0))
            k = op['kind']
            if k == 'alive':
                _paste(cv, ok, op['x'], op['y'])
                continue
            good = True
            if k == 'image':
                fname = op['file']
                if op.get('zoom'):
                    how = truth['zoom'][op['zoom']]
                    t = _png(os.path.join(sd, fname))
                    if how == 'scaled':
                        t2 = np.repeat(np.repeat(t, 2, 0), 2, 1)
                        _paste(cv, t2, op['x'] - 16, op['y'] - 16)
                    else:
                        _paste(cv, t, op['x'], op['y'])
                    good = how != 'error'
                else:
                    how = truth['lua'].get(op['format'], 'correct')
                    tpng = fname if fname.endswith('.png') else ('t_png_rgba.png' if 'rgb565' not in fname else 't_png_rgb.png')
                    t = _png(os.path.join(sd, tpng)).copy()
                    if how == 'garbled':
                        t = rng.integers(0, 256, t.shape).astype(np.uint8)
                        t[..., 3] = 255
                    elif how == 'rb_swapped':
                        t[..., [0, 2]] = t[..., [2, 0]]
                    if how != 'missing':
                        _paste(cv, t, op['x'], op['y'])
            elif k == 'fills':
                for f in op['fills']:
                    c = [int(f['hex'][i:i + 2], 16) for i in (1, 3, 5)]
                    cv[f['y']:f['y'] + f['h'], f['x']:f['x'] + f['w']] = c
            elif k == 'label':
                good = truth['label']
                if good:
                    im = Image.fromarray(cv.astype(np.uint8))
                    ImageDraw.Draw(im).text((op['x'], op['y']), op['text'], font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 16), fill=(255, 255, 255))
                    cv = np.asarray(im).astype(np.float32)
            elif k == 'timer':
                _paste(cv, ok, op['x'], op['y'])
            elif k == 'digits':
                v = {'hor_res': W, 'ver_res': H, 'hour': vals['hour'], 'minute': vals['minute'], 'raw_minute_low': (vals['minute'] % 10) * 256}[op['what']]
                s = str(v).zfill(op['n'])
                for i, ch in enumerate(s):
                    _paste(cv, _png(os.path.join(sd, 'dg%s.png' % ch)), op['x'] + i * cw, op['y'])
            _paste(cv, ok if good else err, sx, sy)
    # device: dark values crush to black, AOD dims, the status dot, the panel's shape
    cv = np.where(cv < truth['floor'] - 0.5, 0, cv)
    if theme == 'aod':
        cv *= truth['dim']
    if truth['dot'] and theme == 'normal':
        _, y, r = truth['dot']
        yy, xx = np.mgrid[0:H, 0:W]
        cv[(xx - W / 2 + 0.5) ** 2 + (yy - y + 0.5) ** 2 <= r * r] = 230
    mask = Image.new('L', (W * 4, H * 4), 0)
    rr = L['screen']['r'] if L['screen']['shape'] == 'rrect' else W / 2   # capsule ends / circle: W / 2
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W * 4 - 1, H * 4 - 1), radius=rr * 4, fill=255)
    return cv, np.asarray(mask).astype(np.float32) / 255


def photograph(cv, mask, rng, K=4, backdrop=False):
    band = np.repeat(np.repeat(cv, K, 0), K, 1) * mask[..., None]
    H, W = cv.shape[:2]
    scale = 3.2 / K
    cx, cy = 1500, 2000
    src = np.float32([[0, 0], [W * K, 0], [W * K, H * K], [0, H * K]])
    half = np.array([W * K * scale / 2, H * K * scale / 2])
    dst = np.float32([[cx - half[0] - 12, cy - half[1] + 9], [cx + half[0] + 10, cy - half[1] - 6],
                      [cx + half[0] + 22, cy + half[1] + 14], [cx - half[0] - 20, cy + half[1] - 3]])
    M = cv2.getPerspectiveTransform(src, dst)
    photo = cv2.warpPerspective(band, M, (3000, 4000), flags=cv2.INTER_AREA)
    if backdrop:
        # daylight on a tan table with an orange frame, a white strap and a bezel around the screen:
        # the scene that outscored the rulers on "yellow" (Band 11 round 2, 2026-09-29)
        shell = cv2.warpPerspective(np.ones((H * K, W * K), np.float32), M, (3000, 4000), flags=cv2.INTER_AREA)
        grown = cv2.dilate(shell, np.ones((121, 121), np.uint8))
        bezel = cv2.dilate(shell, np.ones((41, 41), np.uint8))
        bg = np.empty_like(photo)
        bg[:] = (215, 165, 110)
        bg[:, :400] = (250, 140, 25)
        bg[1400:2600, 1300:1700] = (235, 235, 230)          # strap above/below the case
        bg = bg * (1 - grown[..., None]) + np.array([235, 235, 230], np.float32) * (grown - bezel)[..., None]
        photo = photo + bg * (1 - bezel[..., None])
    photo = cv2.GaussianBlur(photo, (0, 0), 1.3)
    return np.clip(photo * 1.1 + rng.normal(0, 3, photo.shape) + 6, 0, 255).astype(np.uint8)


SPECS = os.path.normpath(os.path.join(HERE, '..', 'vela-calib', 'test', 'specs'))


def selftest_layouts(models=None, specs=()):
    """(name, layout, base dir) to test: layouts/<model>.json here, and each spec generated with
    gen.py into a temp dir. Nothing given: band11, band10pro and the synthetic specs (a 466 px circle,
    a 390 x 450 rounded rectangle) in tools/vela-calib/test/specs/."""
    import subprocess
    import tempfile
    if not models and not specs:
        models = ['band11', 'band10pro']
        specs = sorted(os.path.join(SPECS, f) for f in os.listdir(SPECS) if f.endswith('.json')) if os.path.isdir(SPECS) else []
    out = [(m, json.load(open(os.path.join(HERE, 'layouts', m + '.json'))), HERE) for m in (models or [])]
    for sp in specs:
        d = tempfile.mkdtemp()
        subprocess.run([sys.executable, os.path.join(HERE, 'gen.py'), '--spec', sp, '--out', d], check=True, stdout=subprocess.DEVNULL)
        sid = json.load(open(sp))['id']
        out.append((sid, json.load(open(os.path.join(d, 'layouts', sid + '.json'))), d))
    return out


def selftest(models=None, specs=()):
    import tempfile
    tmp = tempfile.mkdtemp()
    ok_all = True
    for model, L, base in selftest_layouts(models, specs):
        W, H = L['screen']['w'], L['screen']['h']
        faces = {f['n']: f for f in L['faces']}
        for truth in TRUTHS:
            rng = np.random.default_rng(3)
            results = []
            fails = []
            for page in L['pages']:
                cv, mask = render_page(L, faces[page['face']], page, truth, base)
                p = os.path.join(tmp, '%s_%s_p%d.png' % (model, truth['name'], page['id']))
                ph = photograph(cv, mask, rng, backdrop=truth['name'] == 'B')
                turn = page['id'] % 3  # upright, band lying with its top to the left, top to the right
                if turn:
                    ph = cv2.rotate(ph, cv2.ROTATE_90_COUNTERCLOCKWISE if turn == 1 else cv2.ROTATE_90_CLOCKWISE)
                Image.fromarray(ph).save(p)
                r = measure_photo(p, L)
                r['measured_at'] = datetime.datetime.now().isoformat()
                results.append(r)
                if 'error' in r:
                    fails.append('p%d: %s' % (page['id'], r['error']))
                    continue
                if r['page'] != page['id'] or not r['fit']['ok']:
                    fails.append('p%d: read as page %s, fit ok %s' % (page['id'], r['page'], r['fit']['ok']))
                for s in r['samples']:
                    if 'error' in s['result']:
                        fails.append('p%d %s: %s' % (page['id'], s['id'], s['result']['error']))
            face = {}
            apply_face(face, results, L)
            g = lambda path: (vm.get_path(face, path)[0] or {}).get(vm.get_path(face, path)[1], {}).get('value') if vm.get_path(face, path)[0] is not None else None

            def check(name, cond, got):
                if not cond:
                    fails.append('%s: got %s' % (name, json.dumps(got, default=str)[:200]))

            for side in ('left', 'right', 'top', 'bottom'):
                v = g('screen.hidden_px.' + side)
                check('hidden ' + side, v is not None and abs(v) < 1.0, v)
            cr = g('screen.corner_radius_px') or {}
            want_r = W / 2 if L['screen']['shape'] in ('capsule', 'circle') else L['screen']['r']
            check('corner radius', cr and all(v is not None and abs(v - want_r) < 3 for v in cr.values()), cr)
            ov = g('screen.status_clear_top_px')
            if truth['dot']:
                check('status dot', ov is not None and abs(ov - (truth['dot'][1] + truth['dot'][2])) <= 2, ov)
            else:
                check('no status dot', ov is None, ov)
            for grp in ('grey', 'grey_background', 'grey_rgba32', 'grey_lua'):
                check('floor ' + grp, g('colour.floor.' + grp) == truth['floor'], g('colour.floor.' + grp))
            check('encoding', g('image.encoding.png_indexed') == 'correct' and g('image.encoding.png_rgba32') == 'correct', [g('image.encoding.png_indexed'), g('image.encoding.png_rgba32')])
            check('alpha over element', g('image.alpha_over_element') == 'blend', g('image.alpha_over_element'))
            check('alpha over black', g('image.alpha_over_black') == 'matches_opaque_grey', g('image.alpha_over_black'))
            pf = (vm.get_path(face, 'lua.image_format')[0] or {}).get('image_format', {}).get('per_format', {})
            check('lua formats', {k: v['verdict'] for k, v in pf.items()} == truth['lua'], pf)
            want_z = {k: ('not_scaled' if v == 'error' else v) for k, v in truth['zoom'].items()}
            check('lua zoom', g('lua.image_zoom') == want_z, g('lua.image_zoom'))
            api = g('lua.api_status') or {}
            check('lua api', api.get('image_scale' if truth['zoom']['scale'] == 'error' else 'image_zoom') in (('error',) if truth['zoom']['scale'] == 'error' else ('ok',))
                  and api.get('label') == ('ok' if truth['label'] else 'error') and api.get('alive') == 'ok', api)
            check('lua label', g('lua.label_draws') == truth['label'], g('lua.label_draws'))
            for path in ('lua.placement_offset_px', 'widgets.placement_offset_px'):
                v = g(path)
                check(path, v and abs(v['dx']) < 0.7 and abs(v['dy']) < 0.7, v)
            check('canvas', g('lua.canvas_px') == {'w': W, 'h': H}, g('lua.canvas_px'))
            check('dataman scale', g('lua.dataman_scale') == 256, g('lua.dataman_scale'))
            check('lua time', g('lua.time_matches_widget') is True, g('lua.time_matches_widget'))
            check('lua on aod', g('lua.runs_on_aod') == truth['lua_on_aod'], g('lua.runs_on_aod'))
            al = g('widgets.number.align') or {}
            check('align', all(al.get(k, {}).get('verdict') == v for k, v in truth['align'].items()), {k: v.get('verdict') for k, v in al.items()})
            check('anchor fixed', g('widgets.number_anchor_fixed') == (truth['align']['center'] != 'anchor_centre'), g('widgets.number_anchor_fixed'))
            sp = g('widgets.number.spacing_px') or {}
            check('spacing', abs(sp.get('6', 99) - 6) < 0.7 and abs(sp.get('-3', 99) + 3) < 0.7, sp)
            check('steps value', (al.get('left') or {}).get('value') == truth['values']['steps'], al.get('left'))
            fb = g('widgets.image_list.fallback') or ''
            check('fallback', truth['fallback'] in fb.split('|'), fb)
            check('below first', g('widgets.image_list.below_first') == 'nothing', g('widgets.image_list.below_first'))
            check('above last', g('widgets.image_list.above_last') == 'frame 1', g('widgets.image_list.above_last'))
            check('aod shows', g('aod.shows') == 'face_aod', g('aod.shows'))
            dr = g('aod.dim_ratio')
            check('dim ratio', dr is not None and abs(dr - truth['dim']) < 0.08, dr)
            check('aod numbers', (g('aod.number_widgets') or {}).get('minute') == truth['values']['minute'], g('aod.number_widgets'))
            print('%-9s truth %s: %d pages, %d facts, %s' % (model, truth['name'], len(results), sum(1 for _ in _walk(face)),
                                                            'PASS' if not fails else 'FAIL'))
            for f in fails:
                print('   FAIL', f)
            ok_all = ok_all and not fails
    print('selftest', 'PASS' if ok_all else 'FAIL')
    return 0 if ok_all else 1


def _walk(d, pre=''):
    for k, v in d.items():
        p = pre + '.' + k if pre else k
        if isinstance(v, dict) and 'status' in v and 'value' in v:
            yield p, v
        elif isinstance(v, dict):
            yield from _walk(v, p)


# ---------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('photos', nargs='+')
    r.add_argument('--device', required=True, help='device id (layouts/<id>.json)')
    r.add_argument('--page', type=int, default=None)
    r.add_argument('--out', default=None, help='annotated images (default <workspace>/devices/<model>/results-face)')
    r.add_argument('--dry-run', action='store_true')
    s_ = sub.add_parser('set')
    s_.add_argument('path')
    s_.add_argument('value')
    s_.add_argument('--source', required=True)
    s_.add_argument('--status', default='measured', choices=['measured', 'assumed', 'unknown'])
    s_.add_argument('--device', required=True)
    sh = sub.add_parser('show')
    sh.add_argument('--device', required=True)
    se = sub.add_parser('seed')
    se.add_argument('--device', required=True)
    st = sub.add_parser('selftest')
    st.add_argument('--device', action='append', default=None, help='layouts/<id>.json to test (repeatable)')
    st.add_argument('--spec', action='append', default=[], help='a device spec to generate faces for and test (repeatable)')
    for sp in (r, s_, sh, se):
        sp.add_argument('--workspace', default=None, help='workspace root (default: $MIBAND_WORKSPACE, else the nearest folder with devices/)')
    a = ap.parse_args(argv)
    global WS
    WS = getattr(a, 'workspace', None)

    if a.cmd == 'selftest':
        return selftest(a.device, a.spec)
    if a.cmd == 'show':
        for p, v in _walk(load_face(a.device)['face'], 'face'):
            val = json.dumps(v['value'])
            print('%-9s %-44s %s' % (v['status'], p, val if len(val) < 70 else val[:67] + '...'))
        return 0
    if a.cmd == 'seed':
        doc = load_face(a.device, write=True)
        n = seed(doc['face'], 'not measured yet: tools/face-calib (build the calibration faces, photograph them, measure_face.py run)')
        print('seeded %d facts -> %s' % (n, save_doc(a.device, doc)))
        return 0
    if a.cmd == 'set':
        doc = load_face(a.device, write=True)
        try:
            v = json.loads(a.value)
        except ValueError:
            v = a.value
        path = a.path[len('face.'):] if a.path.startswith('face.') else a.path
        vm.set_fact(doc['face'], path, v, a.source, status=a.status)
        save_doc(a.device, doc)
        print('set face.%s = %s (%s)' % (path, json.dumps(v), a.status))
        return 0
    L = json.load(open(os.path.join(HERE, 'layouts', a.device + '.json')))
    evidence = os.path.join(ws.devices_dir(WS), a.device, 'evidence-face')
    if a.out is None:
        a.out = os.path.join(ws.devices_dir(WS), a.device, 'results-face')
    for ph in a.photos:
        res = measure_photo(ph, L, page_id=a.page, annotate_dir=a.out)
        res['layout'] = 'face-calib/%s b%d' % (a.device, L['kit_build'])
        res['measured_at'] = datetime.datetime.now().isoformat(timespec='seconds')
        if 'error' in res:
            print('%s: ERROR %s' % (res['photo'], res['error']))
            continue
        fi = res['fit']
        print('%s: page %d (%s, F%d %s), rulers rms %.2f/%.2f, %d ticks, %.2f photo px/band px%s' % (
            res['photo'], res['page'], res['page_key'], res['face'], res['theme'], fi['rms_band_px'][0], fi['rms_band_px'][1],
            fi['ticks'], min(fi['photo_px_per_band_px']), '' if fi['ok'] else '  NOT USED: ' + '; '.join(fi['notes'])))
        print('   edges %s' % json.dumps(res['ruler_edges']))
        for s in res['samples']:
            rr = s['result']
            brief = {k: rr[k] for k in rr if k in ('verdict', 'value', 'digits', 'status', 'present', 'shown', 'luma', 'r', 'found', 'bbox', 'dx', 'dy', 'error', 'centre_hidden_px', 'radius_px')}
            print('   %-14s %-10s %s' % (s['id'], s['type'], json.dumps(brief)))
        if not a.dry_run:
            os.makedirs(evidence, exist_ok=True)
            vm.save_json(os.path.join(evidence, os.path.splitext(res['photo'])[0] + '.json'), res)
    if a.dry_run:
        return 0
    newest = {}
    for fn in sorted(os.listdir(evidence)) if os.path.isdir(evidence) else []:
        if fn.endswith('.json'):
            r = vm.load_json(os.path.join(evidence, fn))
            if 'samples' not in r:
                continue
            k = r.get('page_key')
            if k not in newest or r.get('measured_at', '') > newest[k].get('measured_at', ''):
                newest[k] = r
    doc = load_face(a.device, write=True)
    seed(doc['face'], 'not measured yet: tools/face-calib')
    written = apply_face(doc['face'], list(newest.values()), L)
    print('%s: %d face facts written' % (save_doc(a.device, doc), len(written)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
