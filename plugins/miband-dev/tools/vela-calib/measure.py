#!/usr/bin/env python3
"""Vela calibration kit: measure photos of the calibration pages and write a device profile.

    python3 measure.py run PHOTO [PHOTO ...] [--device band10pro | --profile devices/band10pro/profile.json]
                                             [--layout layouts/band10pro.json]
                                             [--page N] [--out results] [--dry-run]
    python3 measure.py set PATH VALUE --source TEXT [--device ...]      # record an observation
    python3 measure.py show [--device ...]                              # print every fact and its status
    python3 measure.py selftest                                         # synthetic end-to-end check

Where it reads and writes (workspace.py): the profile, evidence/ and results/ live in your
workspace's devices/<model>/ (--workspace, $MIBAND_WORKSPACE, or the nearest folder above the
current directory with a devices/ folder). A model with no workspace profile reads the default
shipped with the plugin, and its first write starts from a copy of that default. Nothing is
written next to this script.

How a photo is read (all numbers end up in band px):
  1. Find the yellow scale bar (the longest yellow blob) and the yellow 100 px ruler ticks; a rough
     similarity transform from the bar identifies each tick's band y.
  2. Match every 10 px white tick, measure the inner end of each at half brightness, and fit a
     homography (band px -> photo px) to the tick ends and the bar ends, dropping outliers. The
     residual (rms, band px) is reported; above 0.5 px the photo is flagged.
  3. Rectify the screen to S = 8 photo-free pixels per band px, read the page barcode, and measure
     each sample the layout file lists for that page (outline edges, ink edges at half brightness,
     colours, corners...).
  4. Merge the page results into the device profile: every value it writes gets status "measured"
     with the photo name and date; values no photo covers keep their status ("assumed"/"unknown").
"""
import argparse
import datetime
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage as ndi

sys.dont_write_bytecode = True  # the plugin copy is read-only: no __pycache__ next to the kit
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workspace as ws  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
S = 8  # rectified pixels per band px
SQ2M1 = math.sqrt(2) - 1
ARC = 1 - 1 / math.sqrt(2)  # a corner arc of radius r crosses the diagonal r * ARC in from each edge


# ---------------------------------------------------------------------------------------------
# photo -> band coordinates
# ---------------------------------------------------------------------------------------------
def load_photo(path):
    im = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
    return np.asarray(im)


def scores(img):
    """Per-pixel colour scores (float32): luma, whiteness and the outline colours."""
    f = img.astype(np.float32)
    R, G, B = f[..., 0], f[..., 1], f[..., 2]
    return {
        'luma': 0.299 * R + 0.587 * G + 0.114 * B,
        'white': np.minimum(np.minimum(R, G), B),
        # white without saturated colour: a pink/cyan outline's glow scores ~0 (box-model pages)
        # (the band's white photographs bluish, min/max ~0.6; a pink/cyan line is ~0.3 or less)
        'neutral': np.minimum(np.minimum(R, G), B) * np.clip(
            (np.minimum(np.minimum(R, G), B) / np.maximum(np.maximum(np.maximum(R, G), B), 1.0) - 0.4) / 0.25, 0, 1),
        'yellow': np.clip(np.minimum(R, G) - B, 0, None),
        'pink': np.clip(np.minimum(R, B) - G, 0, None),
        'cyan': np.clip(np.minimum(G, B) - R, 0, None),
        'green': np.clip(G - np.maximum(R, B), 0, None),
        'any': np.maximum(np.maximum(R, G), B),
    }


def half_cross(prof, lo_val, hi_val, i0, direction):
    """Sub-pixel index where prof crosses the half level, walking from i0 in direction (+1/-1)."""
    h = (lo_val + hi_val) / 2
    i = i0
    n = len(prof)
    while 0 <= i + direction < n and prof[i + direction] >= h:
        i += direction
    j = i + direction
    if not (0 <= j < n):
        return float(i)
    a, b = prof[i], prof[j]
    t = (a - h) / (a - b) if a != b else 0.5
    return i + direction * t


def sample_line(ch, p0, p1, n):
    xs = np.linspace(p0[0], p1[0], n)
    ys = np.linspace(p0[1], p1[1], n)
    return ndi.map_coordinates(ch, [ys, xs], order=1, mode='nearest'), xs, ys


def blobs(mask, min_area=6):
    n, lab, st, cen = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a >= min_area:
            out.append({'i': i, 'x': x, 'y': y, 'w': w, 'h': h, 'area': a, 'cx': cen[i][0], 'cy': cen[i][1]})
    return out, lab


def end_along(ch, c, u, span, outward, thick=0.0):
    """Half-max end of a bright bar-like blob: walk from centre c along unit vector u (photo px).
    thick > 0 (the bar): average parallel lines across the middle of the bar's thickness and
    median-filter along it, so a screen-door / moire pattern (dark gaps between the panel's
    pixels that a sharp photo resolves) doesn't read as the bar's end."""
    n = int(span * 4) + 8
    p1 = (c[0] + u[0] * span * outward, c[1] + u[1] * span * outward)
    prof, xs, ys = sample_line(ch, c, p1, n)
    if thick > 0:
        v = (-u[1], u[0])
        acc = [prof]
        for k in np.linspace(-0.3 * thick, 0.3 * thick, 5):
            if k == 0:
                continue
            q, _, _ = sample_line(ch, (c[0] + v[0] * k, c[1] + v[1] * k), (p1[0] + v[0] * k, p1[1] + v[1] * k), n)
            acc.append(q)
        prof = ndi.median_filter(np.mean(acc, axis=0), size=9, mode='nearest')
    hi = np.percentile(prof[: max(3, n // 4)], 90)
    lo = np.percentile(prof, 5)
    i0 = 0
    if thick > 0:
        # step over short dark gaps (a line of another colour drawn across the bar, e.g. an
        # overflowing outline): the end is the first gap longer than 6 % of the walk
        above = prof >= (lo + hi) / 2
        gapmax = max(4, int(0.06 * n))
        last, run = 0, 0
        for i in range(n):
            if above[i]:
                last, run = i, 0
            else:
                run += 1
                if run > gapmax:
                    break
        i0 = last
    t = half_cross(prof, lo, hi, i0, +1)
    t = min(max(t, 0), n - 1)
    return (np.interp(t, np.arange(n), xs), np.interp(t, np.arange(n), ys))


class Fit:
    """Homography band -> photo, fitted to the rulers and the bar."""

    def __init__(self, img, layout, bar):
        self.img = img
        self.layout = layout
        self.bar_spec = bar
        fr = layout['frame']
        self.W, self.H = layout['screen']['w'], layout['screen']['h']
        self.every = fr['tick_every']
        self.lens = fr['tick_len']
        self.ticks = fr['ticks']
        self.ok = False
        self.notes = []

    def run(self):
        img = self.img
        sc = scores(img)
        self.sc = sc
        luma, yel = sc['luma'], sc['yellow']
        # bright mask: ticks are the brightest thin things on black
        hi = np.percentile(luma, 99.7)
        bright = luma > max(50.0, 0.35 * hi)
        ymask = (yel > max(40.0, 0.35 * np.percentile(yel, 99.9))) & bright
        yb, _ = blobs(ymask, 20)
        if not yb:
            raise RuntimeError('no yellow found (bar and 100 px ticks)')
        bar = max(yb, key=lambda b: max(b['w'], b['h']) / max(1, min(b['w'], b['h'])) * math.sqrt(b['area']))
        # bar axis by PCA of its pixels
        ys_, xs_ = np.nonzero(_blob_mask(ymask, bar))
        pts = np.stack([xs_, ys_], 1).astype(np.float64)
        c = pts.mean(0)
        u = np.linalg.svd(pts - c, full_matrices=False)[2][0]
        half = max(bar['w'], bar['h'])
        thick = float(len(pts)) / max(1.0, float(np.ptp(pts[:, 0] * u[0] + pts[:, 1] * u[1])))  # blob area / length
        ea = end_along(yel, tuple(c), (-u[0], -u[1]), half, 1, thick)
        eb = end_along(yel, tuple(c), (u[0], u[1]), half, 1, thick)
        bl = self.bar_spec
        blen = bl['len']
        by = bl['y'] + bl['h'] / 2
        L = self.lens[2]

        def match(e0, e1):
            """Similarity from the bar (its left end e0) and the yellow 100 px ticks it predicts.
            A yellow blob counts as a tick only if it is tick-shaped (about L x 1 band px) and close
            to where the similarity puts one: yellow text (the geometry page's device line) and
            other yellow content near the rulers must not become ticks."""
            vx = (np.array(e1) - np.array(e0)) / blen                 # photo px per band px along x
            vy = np.array([-vx[1], vx[0]])                             # band y is 90 deg clockwise (image y down)
            o = np.array(e0) - bl['x'] * vx - by * vy                  # photo position of band (0, 0)
            simA = np.array([[vx[0], vy[0], o[0]], [vx[1], vy[1], o[1]], [0, 0, 1]])
            simI = np.linalg.inv(simA)
            k = float(np.linalg.norm(vx))
            src, dst, kind = [(bl['x'], by), (bl['x'] + blen, by)], [e0, e1], ['bar', 'bar']
            for b in yb:
                if b is bar:
                    continue
                length = math.hypot(b['w'], b['h']) / k
                width = b['area'] / max(1.0, math.hypot(b['w'], b['h'])) / k
                if not (0.5 * L <= length <= 1.6 * L + 4 and width <= 4.0):
                    continue
                bx, byy, _ = simI @ np.array([b['cx'], b['cy'], 1.0])
                for side, xc in (('L', L / 2), ('R', self.W - L / 2)):
                    yy = round((byy - 0.5) / 100) * 100
                    if abs(bx - xc) < 14 and abs(byy - (yy + 0.5)) < 15 and 0 <= yy < self.H:
                        src.append((xc, yy + 0.5))
                        dst.append((b['cx'], b['cy']))
                        kind.append('y' + side)
            return src, dst, kind, k

        # The bar alone doesn't say which way the page runs along it (a band lying sideways puts the
        # bar vertical in the photo): try both ends as the left end, keep the one the ticks agree with.
        cands = [match(ea, eb), match(eb, ea)]
        src, dst, kind, self.scale0 = max(cands, key=lambda m: len(m[0]))
        e0, e1 = dst[0], dst[1]
        if len(src) < 5:
            raise RuntimeError('too few yellow ruler ticks matched (%d); is the whole screen in the photo?' % (len(src) - 2))
        Hm, _ = cv2.findHomography(np.array(src, np.float64), np.array(dst, np.float64), 0)
        # all ticks: locate each one's row next to its inner end (away from any bezel glare at the
        # screen edge), then walk along the row to the inner end at half brightness. Two passes.
        # Bloom: a saturated bright edge reads d px outside its true place at half brightness, so a
        # tick looks 1 + 2d thick and d longer at each end, and the bar 2d longer. d comes from the
        # tick thickness (pass 1) and is applied to the tick ends and the bar ends (pass 2, 3).
        # a sharp close-up resolves the panel's pixel grid (a 1 px tick reads as dotted rows):
        # blur by ~0.4 band px so each tick is one smooth peak (symmetric, so centres don't move)
        ch = cv2.GaussianBlur(sc['luma'], (0, 0), max(0.5, 0.4 * self.scale0))
        self.bloom = 0.0
        for _pass in range(3):
            self._widths = []
            d = self.bloom
            src, dst, kind, outer = [], [], [], []
            for i, t in enumerate(self.ticks):
                ln = self.lens[t]
                y = i * self.every
                for side in ('L', 'R'):
                    sgn = 1 if side == 'L' else -1
                    xm = 0.6 * ln if side == 'L' else self.W - 0.6 * ln
                    pc = self._row_peak(ch, Hm, xm, y + 0.5)
                    if pc is None:
                        continue
                    ux = _proj(Hm, xm + 1, y + 0.5) - _proj(Hm, xm, y + 0.5)
                    ux = ux / np.linalg.norm(ux)
                    reach = 0.4 * ln * self.scale0 + 3 * self.scale0
                    ein = end_along(ch, pc, (ux[0] * sgn, ux[1] * sgn), reach, 1)
                    eout = end_along(ch, pc, (-ux[0] * sgn, -ux[1] * sgn), 0.6 * ln * self.scale0 + 3 * self.scale0, 1)
                    src.append((ln + d if side == 'L' else self.W - ln - d, y + 0.5))
                    dst.append(ein)
                    kind.append('t' + side)
                    outer.append((side, y, eout))
            if len(src) < 8:
                raise RuntimeError('too few ruler ticks found (%d)' % len(src))
            Hm, _ = cv2.findHomography(np.array(src + [(bl['x'] - d, by), (bl['x'] + blen + d, by)], np.float64),
                                       np.array(dst + [e0, e1], np.float64), cv2.RANSAC, max(1.0, 0.8 * self.scale0))
            self.bloom = float(min(3.0, max(0.0, (np.median(self._widths) - 1) / 2)))
        d = self.bloom
        src = np.array(src, np.float64)
        dst = np.array(dst, np.float64)
        # bar ends again + iterative outlier rejection
        src = np.vstack([src, [(bl['x'] - d, by), (bl['x'] + blen + d, by)]])
        dst = np.vstack([dst, [e0, e1]])
        keep = np.ones(len(src), bool)
        for _ in range(4):
            Hm, _ = cv2.findHomography(src[keep], dst[keep], 0)
            Hi = np.linalg.inv(Hm)
            back = cv2.perspectiveTransform(dst[None], Hi)[0] - src
            err = np.hypot(back[:, 0], back[:, 1])
            rms = math.sqrt((err[keep] ** 2).mean())
            nk = err < max(0.6, 3 * rms)
            nk[-2:] = True
            if (nk == keep).all():
                break
            keep = nk
        self.Hm = Hm
        self.Hi = np.linalg.inv(Hm)
        back = cv2.perspectiveTransform(dst[None], self.Hi)[0] - src
        # the fit's points, for diagnosis: (kind, band x, band y, residual x, residual y, kept)
        self.points = [(k, float(a[0]), float(a[1]), float(b[0]), float(b[1]), bool(kk))
                       for k, a, b, kk in zip(kind + ['bar', 'bar'], src, back, keep)]
        self.rms = [float(np.sqrt((back[keep, 0] ** 2).mean())), float(np.sqrt((back[keep, 1] ** 2).mean()))]
        self.n_ticks = int(keep[:-2].sum())
        self.n_dropped = int((~keep).sum())
        # visible edges: where do the outer tick ends land in band px? Only ticks on the straight
        # part of the sides count (a capsule's or a rounded corner's arc hides the outer ends there).
        sy = self.layout['frame'].get('straight_y')
        if sy:
            outer = [o for o in outer if sy[0] <= o[1] <= sy[1]]
        ol = [cv2.perspectiveTransform(np.array([[e]], np.float64), self.Hi)[0][0][0] for s_, y, e in outer if s_ == 'L']
        orr = [cv2.perspectiveTransform(np.array([[e]], np.float64), self.Hi)[0][0][0] for s_, y, e in outer if s_ == 'R']
        self.edge = {
            # half-max tick ends read `bloom` px outside the true end: correct inward
            'left_first_visible_x': float(np.median(ol)) + self.bloom if ol else None,
            'right_last_visible_x': float(np.median(orr)) - self.bloom if orr else None,
            'ticks_seen_left': len(ol), 'ticks_seen_right': len(orr),
            'first_tick_y_left': min([y for s_, y, e in outer if s_ == 'L'], default=None),
            'last_tick_y_left': max([y for s_, y, e in outer if s_ == 'L'], default=None),
        }
        sx = np.linalg.norm(_proj(Hm, self.W / 2 + 50, self.H / 2) - _proj(Hm, self.W / 2 - 50, self.H / 2)) / 100
        sy = np.linalg.norm(_proj(Hm, self.W / 2, self.H / 2 + 50) - _proj(Hm, self.W / 2, self.H / 2 - 50)) / 100
        self.scale = [float(sx), float(sy)]
        self.ok = self.n_ticks >= 12 and max(self.rms) < 0.5
        if not orr or not ol:
            self.notes.append('no %s ruler ticks seen: is the page drawn larger than the screen (manifest designWidth '
                              'smaller than the panel), or is that edge out of the photo?' % ('right' if not orr else 'left'))
        if self.n_ticks < 12:
            self.notes.append('only %d ruler ticks matched' % self.n_ticks)
        if max(self.rms) >= 0.5:
            self.notes.append('ruler fit residual %.2f px (want < 0.5): retake straight on' % max(self.rms))
        if min(sx, sy) < 2.0:
            self.notes.append('low resolution: %.1f photo px per band px (want >= 2.5); move closer' % min(sx, sy))
        return self

    def _row_peak(self, ch, Hm, bx, by):
        """Photo point of a 1 px tick crossing band (bx, ~by): brightness peak along band y, +-4 px."""
        p0 = _proj(Hm, bx, by - 4)
        p1 = _proj(Hm, bx, by + 4)
        n = int(8 * self.scale0 * 3) + 1
        prof, xs, ys = sample_line(ch, p0, p1, n)
        k = int(np.argmax(prof))
        pk, bg = prof[k], np.percentile(prof, 20)
        if pk - bg < 40:
            return None
        h = bg + (pk - bg) / 2
        a = k
        while a > 0 and prof[a - 1] > h:
            a -= 1
        b = k
        while b < n - 1 and prof[b + 1] > h:
            b += 1
        width = (b - a + 1) / (n - 1) * 8  # band px (half-max; a saturated 1 px tick blooms to 3-4)
        if width > 6.0 or a == 0 or b == n - 1:
            return None
        w = prof[a:b + 1] - bg
        c = (w * np.arange(a, b + 1)).sum() / w.sum()
        self._widths.append(width)
        return (float(np.interp(c, np.arange(n), xs)), float(np.interp(c, np.arange(n), ys)))

    def rectify(self):
        T = self.Hm @ np.array([[1.0 / S, 0, 0.5 / S], [0, 1.0 / S, 0.5 / S], [0, 0, 1]])
        return cv2.warpPerspective(self.img, T, (self.W * S, self.H * S), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)


def _proj(Hm, x, y):
    v = Hm @ np.array([x, y, 1.0])
    return v[:2] / v[2]


def _blob_mask(mask, b):
    sub = np.zeros_like(mask, dtype=bool)
    sl = (slice(b['y'], b['y'] + b['h']), slice(b['x'], b['x'] + b['w']))
    lab = cv2.connectedComponents(mask[sl].astype(np.uint8), connectivity=8)[1]
    # the component at the blob's centre region (largest in the box)
    ids, cnt = np.unique(lab[lab > 0], return_counts=True)
    sub[sl] = lab == ids[np.argmax(cnt)]
    return sub


# ---------------------------------------------------------------------------------------------
# rectified image helpers (band coordinates; rect pixel i covers band [i/S, (i+1)/S))
# ---------------------------------------------------------------------------------------------
class Rect:
    def __init__(self, rect, white=None):
        self.img = rect
        self.sc = scores(rect)
        self.Hr, self.Wr = rect.shape[:2]
        self.white = None
        if white is not None:
            self.set_white(white)

    def set_white(self, white):
        """Re-score 'neutral' (white, not pink / cyan / green) against this photo's own white: the
        band's white photographs tinted (Band 10 Pro min/max ~0.6, Band 11 ~0.44, bluish), which a
        fixed ratio can't cover. Chromaticity is taken over ~1 band px (the panel's RGB sub-pixels
        and moire make single pixels' colour swing), then compared with the reference white."""
        ref = np.asarray(white, np.float64)
        ref = ref / max(ref.sum(), 1e-6)
        f = cv2.blur(self.img, (S + 1, S + 1)).astype(np.float32)
        chroma = f / np.maximum(f.sum(2, keepdims=True), 1.0)
        d = np.sqrt(((chroma - ref.astype(np.float32)) ** 2).sum(2))
        w = np.clip(1 - (d - 0.04) / 0.08, 0, 1)
        self.sc['neutral'] = self.sc['luma'] * w
        self.white = [float(v) for v in white]

    def crop(self, ch, x0, y0, x1, y1):
        a = self.sc[ch]
        i0, i1 = max(0, int(round(y0 * S))), min(self.Hr, int(round(y1 * S)))
        j0, j1 = max(0, int(round(x0 * S))), min(self.Wr, int(round(x1 * S)))
        return a[i0:i1, j0:j1], i0 / S, j0 / S

    def line_peak(self, ch, axis, x0, y0, x1, y1, lo, hi, pct=50):
        """Centre (band px) of the strongest 1 px line of colour ch inside [x0,x1]x[y0,y1], searching
        rows (axis='h': a horizontal line, returns y) or columns (axis='v', returns x) in [lo, hi]."""
        if axis == 'h':
            sub, oy, ox = self.crop(ch, x0, lo, x1, hi)
            prof = np.percentile(sub, pct, axis=1) if sub.shape[1] else np.zeros(1)
            off = oy
        else:
            sub, oy, ox = self.crop(ch, lo, y0, hi, y1)
            prof = np.percentile(sub, pct, axis=0) if sub.shape[0] else np.zeros(1)
            off = ox
        if prof.size < 3 or prof.max() < 15:
            return None, 0.0
        k = int(np.argmax(prof))
        pk = prof[k]
        bg = np.percentile(prof, 20)
        h = bg + (pk - bg) / 2
        a = k
        while a > 0 and prof[a - 1] > h:
            a -= 1
        b = k
        while b < len(prof) - 1 and prof[b + 1] > h:
            b += 1
        w = prof[a:b + 1] - bg
        c = (w * np.arange(a, b + 1)).sum() / max(w.sum(), 1e-6)
        return off + (c + 0.5) / S, float(pk)

    def lines_in(self, ch, axis, x0, y0, x1, y1, lo, hi, min_frac=0.5, pct=50):
        """All 1 px lines of colour ch (centres, band px) in [lo, hi]: peaks above min_frac of the max."""
        if axis == 'h':
            sub, oy, ox = self.crop(ch, x0, lo, x1, hi)
            prof = np.percentile(sub, pct, axis=1) if sub.shape[1] else np.zeros(1)
            off = oy
        else:
            sub, oy, ox = self.crop(ch, lo, y0, hi, y1)
            prof = np.percentile(sub, pct, axis=0) if sub.shape[0] else np.zeros(1)
            off = ox
        if prof.size < 3 or prof.max() < 15:
            return []
        thr = np.percentile(prof, 20) + (prof.max() - np.percentile(prof, 20)) * min_frac
        out = []
        i = 0
        while i < len(prof):
            if prof[i] > thr:
                j = i
                while j + 1 < len(prof) and prof[j + 1] > thr:
                    j += 1
                w = prof[i:j + 1]
                out.append(off + ((w * np.arange(i, j + 1)).sum() / w.sum() + 0.5) / S)
                i = j + 1
            else:
                i += 1
        return out

    def ink_extent(self, x0, y0, x1, y1, ch='white'):
        """Ink rows/cols (band px, half-max edges) inside a box; None if empty."""
        sub, oy, ox = self.crop(ch, x0, y0, x1, y1)
        if sub.size == 0:
            return None
        pk = np.percentile(sub, 99.5)
        bg = np.percentile(sub, 5)
        if pk - bg < 40:
            return None
        rows = sub.max(axis=1)
        cols = sub.max(axis=0)
        h = (pk + bg) / 2
        # ink = the half-level mask without specks (a hot pixel or a glint of a neighbour's
        # outline must not become the ink's top); edges then sub-pixel from the max profiles
        clean = ndi.binary_opening(sub > h, structure=np.ones((3, 3)))
        lab, k = ndi.label(clean)
        if k > 1:
            area = ndi.sum(clean, lab, index=np.arange(1, k + 1))
            # drop specks: under 1 band px^2, or under 1 % of the largest part (outline glow)
            clean = np.isin(lab, 1 + np.nonzero(area >= max(S * S, 0.01 * area.max()))[0])
        on_r, on_c = clean.any(axis=1), clean.any(axis=0)

        def ends(p, on):
            idx = np.nonzero(on)[0]
            if not len(idx):
                return None
            a, b = idx[0], idx[-1]
            fa = (p[a] - h) / (p[a] - p[a - 1]) if a > 0 and p[a] > p[a - 1] else 0.0
            fb = (p[b] - h) / (p[b] - p[b + 1]) if b + 1 < len(p) and p[b] > p[b + 1] else 1.0
            ta = a - min(max(fa, 0.0), 1.0)
            tb = b + min(max(fb, 0.0), 1.0)
            return ta, tb

        ry, cx = ends(rows, on_r), ends(cols, on_c)
        if ry is None or cx is None:
            return None
        return {'top': oy + (ry[0] + 0.5) / S, 'bottom': oy + (ry[1] + 0.5) / S,
                'left': ox + (cx[0] + 0.5) / S, 'right': ox + (cx[1] + 0.5) / S,
                'mask': clean, 'origin': (ox, oy), 'level': (float(bg), float(pk))}

    def glyphs(self, ink, n):
        """Split an ink mask into n glyphs left to right (connected components merged by x overlap)."""
        m = ink['mask']
        lab, k = ndi.label(m, structure=np.ones((3, 3)))
        if k == 0:
            return None
        objs = ndi.find_objects(lab)
        comps = []
        for i, sl in enumerate(objs):
            area = int((lab[sl] == i + 1).sum())
            if area < 0.0005 * m.size and area < 40:
                continue
            comps.append([sl[1].start, sl[1].stop, sl[0].start, sl[0].stop])
        comps.sort()
        merged = []
        for c in comps:
            if merged and c[0] < merged[-1][1] - 0.3 * (c[1] - c[0]):
                p = merged[-1]
                merged[-1] = [min(p[0], c[0]), max(p[1], c[1]), min(p[2], c[2]), max(p[3], c[3])]
            else:
                merged.append(c)
        if len(merged) != n:
            return None
        ox, oy = ink['origin']
        return [{'left': ox + x0 / S, 'right': ox + x1 / S, 'top': oy + y0 / S, 'bottom': oy + y1 / S} for x0, x1, y0, y1 in merged]

    def mask_bbox(self, ch, x0, y0, x1, y1, min_level=40):
        sub, oy, ox = self.crop(ch, x0, y0, x1, y1)
        if sub.size == 0:
            return None, None
        # peak and mask from a blur about one band px wide: a sharp close-up resolves the panel's
        # pixel grid (moire), whose bright dots would set the peak far above the fill and leave only
        # a fragment above half (Band 11 photos 2026-09-29: a 64 x 32 pill read as 58 x 8). A
        # symmetric blur keeps half-level edges where they are.
        k = S + 1
        sm = cv2.blur(sub.astype(np.float32), (k, k)) if min(sub.shape) > k else sub.astype(np.float32)
        pk = float(sm.max())
        bg = np.percentile(sub, 10)
        if pk - bg < min_level:
            return None, None
        m = sm > (pk + bg) / 2
        m = ndi.binary_opening(m, structure=np.ones((3, 3)))
        lab, k = ndi.label(m, structure=np.ones((3, 3)))
        if k > 1:  # drop fragments (colour fringes of a neighbouring outline)
            area = ndi.sum(m, lab, index=np.arange(1, k + 1))
            m = np.isin(lab, 1 + np.nonzero(area >= 0.05 * area.max())[0])
        ys, xs = np.nonzero(m)
        if not len(xs):
            return None, None
        return [ox + xs.min() / S, oy + ys.min() / S, (xs.max() + 1 - xs.min()) / S, (ys.max() + 1 - ys.min()) / S], (m, ox, oy)

    def mean(self, x0, y0, x1, y1):
        i0, i1 = int(round(y0 * S)), int(round(y1 * S))
        j0, j1 = int(round(x0 * S)), int(round(x1 * S))
        a = self.img[i0:i1, j0:j1].reshape(-1, 3).astype(np.float64)
        return a.mean(0), float((0.299 * a[:, 0] + 0.587 * a[:, 1] + 0.114 * a[:, 2]).std())


def ruler_white(rect, layout):
    """The photo's white: median RGB of the brightest pixels of the white ruler ticks (straight
    sides only), from a rectified page. None if too few are found."""
    fr = layout['frame']
    W, H = layout['screen']['w'], layout['screen']['h']
    y0, y1 = fr.get('straight_y') or [0, H]
    px = []
    for i, t in enumerate(fr['ticks']):
        y = i * fr['tick_every']
        if t == 2 or not (y0 <= y <= y1):
            continue  # the 100s are yellow
        ln = fr['tick_len'][t]
        for xa, xb in ((1, ln - 1), (W - ln + 1, W - 1)):
            a = rect[y * S + 2:y * S + S - 2, xa * S:xb * S].reshape(-1, 3).astype(np.float64)
            if len(a):
                px.append(a)
    if not px:
        return None
    a = np.concatenate(px)
    lum = 0.299 * a[:, 0] + 0.587 * a[:, 1] + 0.114 * a[:, 2]
    a = a[lum >= np.percentile(lum, 75)]
    if len(a) < 50 or a.max() < 60:
        return None
    return np.median(a, axis=0)


def colour_name(rgb, white=None):
    """Name of a photographed colour. white: this photo's white (ruler_white); the band's white
    photographs tinted (the Band 11's lavender reads min/max 0.44), so it is matched by chromaticity."""
    r, g, b = [float(v) for v in rgb]
    mx = max(r, g, b)
    if mx < 40:
        return 'black'
    if white is not None:
        ref = np.asarray(white, np.float64)
        c = np.array([r, g, b]) / max(r + g + b, 1e-6)
        if float(np.linalg.norm(c - ref / max(ref.sum(), 1e-6))) < 0.08:
            return 'white' if mx > 0.45 * max(ref) else 'grey'
    if min(r, g, b) > 0.55 * mx:  # the camera sees the band's white slightly blue (min/max ~0.6)
        return 'white' if mx > 120 else 'grey'
    if r > 0.6 * mx and b > 0.4 * mx and g < 0.6 * mx:
        return 'pink'
    if g > 0.6 * mx and b > 0.6 * mx and r < 0.6 * mx:
        return 'cyan'
    if b == mx and g > 0.45 * b and r < 0.3 * b:  # cyan as the Band 11 photographs it: (13, 128, 223)
        return 'cyan'
    if r > 0.6 * mx and g > 0.6 * mx and b < 0.5 * mx:
        return 'yellow'
    if g > 0.6 * mx and r < 0.6 * mx and b < 0.6 * mx:
        return 'green'
    return 'other'


# ---------------------------------------------------------------------------------------------
# per-sample measurements
# ---------------------------------------------------------------------------------------------
def outline_box(R, s, colour, w_known=True, h_known=True, px=None, est_w=None):
    """Outer edges of a 1 px outline (band px). Missing sizes are searched for.

    Each edge is looked for with the median of the outline colour along the side first, then
    (if that finds nothing) a high percentile: glyph ink is drawn over the outline where text
    overflows or is clipped at the box edge (a clipped digit covers most of its box's bottom
    edge), and the part of the side the ink doesn't cover is enough. A bottom found by search
    (no explicit height) must be a corner: the left line has to stop there. A natural box that
    is two or more lines tall (the text wrapped) is reported with wrapped=True."""
    b = s['box']
    x, y = b['x'], b['y']
    w = b['w'] if b.get('w') else est_w
    h = b['h'] if b.get('h') else None
    fs = px or 24

    def peak(*a):
        v, st = R.line_peak(*a)
        if v is None:
            v, st = R.line_peak(*a, pct=85)
        return v, st

    def corner_ok(left, yb, strength):
        # the side must stop at a corner; camera bloom below the corner reads up to ~0.4 of the
        # side's strength 2 px down (Band 11 photos 2026-09-29), a side that goes on reads ~1
        sub, _, _ = R.crop(colour, left - 1, yb + 3, left + 1, yb + 6)
        return sub.size == 0 or float(np.percentile(sub.max(axis=1), 50)) < 0.5 * strength

    top, _ = peak(colour, 'h', x + 3, 0, x + min(w, 60) - 3, 0, y - 4, y + 4)
    if top is None:
        return None
    left, lst = peak(colour, 'v', 0, top + 3, 0, top + min(h or 1.2 * fs, 60) - 3, x - 4, x + 4)
    inferred = []
    if left is None and b.get('w') and h:
        # left side hidden (a neighbour's outline blurred into it, or ink over it): the box has an
        # explicit width, so take it from the right side
        r_, lst = peak(colour, 'v', 0, top + 3, 0, top + h - 3, x + w - 5, x + w + 4)
        if r_ is not None:
            left = r_ - (w - 1)
            inferred.append('left')
    if left is None:
        return None
    wrapped = False
    bottom = None
    if h:
        bottom, _ = peak(colour, 'h', left + 3, 0, left + w - 3, 0, top + h - 5, top + h + 4)
        if bottom is None:
            bottom = top + h - 1
            inferred.append('bottom')
    else:
        for pct in (50, 85):
            for lo, hi, wr in ((top + 0.9 * fs, top + 1.8 * fs + 4, False), (top + 1.8 * fs + 4, top + 4.2 * fs, True)):
                for c in R.lines_in(colour, 'h', left + 3, 0, left + w - 3, 0, lo, hi, pct=pct):
                    if corner_ok(left, c, lst):
                        bottom, wrapped = c, wr
                        break
                if bottom is not None:
                    break
            if bottom is not None:
                break
    if bottom is None:
        return None
    if w_known and b.get('w'):
        right, _ = peak(colour, 'v', 0, top + 3, 0, bottom - 3, left + w - 5, left + w + 4)
        if right is None:
            right = left + w - 1  # covered by ink that overflows the box (clipped at its edge)
            inferred.append('right')
    else:
        # the first vertical line right of the text (a neighbour's left edge may follow it)
        cand = R.lines_in(colour, 'v', 0, top + 3, 0, bottom - 3, left + 0.4 * est_w, left + 1.5 * est_w + 8)
        if not cand:
            cand = R.lines_in(colour, 'v', 0, top + 3, 0, bottom - 3, left + 0.4 * est_w, left + 1.5 * est_w + 8, pct=85)
        right = cand[0] if cand else None
    if right is None:
        return None
    return {'top': top - 0.5, 'bottom': bottom + 0.5, 'left': left - 0.5, 'right': right + 0.5, 'wrapped': wrapped,
            'inferred': inferred}


def measure_text_v(R, s):
    px = s['px']
    col = s['outline']
    est = s['box']['w'] or s.get('est_w') or 0.7 * px * len(s['str'])
    ob = outline_box(R, s, col, px=px, est_w=est)
    if not ob:
        return {'error': 'outline not found'}
    bw = s.get('border', 1)
    ct, cb = ob['top'] + bw, ob['bottom'] - bw
    cl, cr = ob['left'] + bw, ob['right'] - bw
    if s['box'].get('w'):
        cr = min(cr, cl + s['box']['w'] - 2 * bw)  # never read a neighbour's ink
    ink = R.ink_extent(cl + 1.3, ct + 1.3, cr - 1.3, cb - 1.3)
    if not ink:
        return {'error': 'no ink', 'box': ob}
    res = {'box': ob, 'box_h': ob['bottom'] - ob['top'], 'content_h': cb - ct,
           'ink_top': ink['top'] - ct, 'ink_bottom': ink['bottom'] - ct,
           'clipped_bottom': (cb - ink['bottom']) < 1.8, 'clipped_top': (ink['top'] - ct) < 1.8,
           'clipped_right': (cr - ink['right']) < 1.8}
    chars = [c for c in s['str'] if c != ' ']
    n_lines = 1
    if ob.get('wrapped'):
        # a natural box that wrapped (the box was narrower than the string): n equal lines
        n_lines = max(2, int(round(res['content_h'] / (1.325 * px))))
        res['wrapped'] = True
        if abs(res['content_h'] / n_lines / px - 1.325) > 0.04:
            return {'error': 'wrapped, and the bottom found (%.1f px) is not a whole number of lines' % res['content_h'], 'box': ob}
    res['lines'] = n_lines
    res['line_h'] = res['content_h'] / n_lines
    if n_lines == 1:
        gl = R.glyphs(ink, len(chars))
        if not gl and s.get('too_wide'):
            # a string wider than its box on purpose: the glyphs past the cut are missing
            for m in range(len(chars) - 1, 0, -1):
                gl = R.glyphs(ink, m)
                if gl:
                    chars = chars[:m]
                    break
        if gl:
            res['glyphs'] = {c: {'top': g['top'] - ct, 'bottom': g['bottom'] - ct, 'left': g['left'] - cl, 'right': g['right'] - cl}
                             for c, g in zip(chars, gl)}
    else:
        # glyphs line by line (tops relative to their own line's top), chars assigned in order
        lh = res['line_h']
        rest = list(chars)
        out = {}
        for k in range(n_lines):
            lk = R.ink_extent(cl + 1.3, ct + k * lh + (1.3 if k == 0 else 0), cr - 1.3, ct + (k + 1) * lh - (1.3 if k == n_lines - 1 else 0))
            if not lk or not rest:
                break
            for m in range(len(rest), 0, -1):
                gl = R.glyphs(lk, m)
                if gl:
                    break
            if not gl:
                out = None
                break
            for c, g in zip(rest[:len(gl)], gl):
                out[c] = {'top': g['top'] - ct - k * lh, 'bottom': g['bottom'] - ct - k * lh, 'line': k}
            rest = rest[len(gl):]
        if out and not rest:
            res['glyphs'] = out
    res['ink_mid_minus_box_mid'] = (res['ink_top'] + res['ink_bottom']) / 2 - res['content_h'] / 2
    return res


def measure_text_w(R, s):
    ob = outline_box(R, s, s['outline'], w_known=False, h_known=False, px=s['px'], est_w=s['est_w'])
    if not ob:
        return {'error': 'outline not found'}
    bw = s.get('border', 1)
    ink = R.ink_extent(ob['left'] + bw + 1.3, ob['top'] + bw + 1.3, ob['right'] - bw - 1.3, ob['bottom'] - bw - 1.3)
    out = {'box': ob, 'outer_w': ob['right'] - ob['left'], 'content_w': ob['right'] - ob['left'] - 2 * bw,
           'content_h': ob['bottom'] - ob['top'] - 2 * bw}
    if ink:
        out['ink_left'] = ink['left'] - ob['left'] - bw
        out['ink_right'] = ob['right'] - bw - ink['right']
    return out


def measure_wrap(R, s):
    b = s['box']
    col = s['outline']
    fs = s['px']
    top, _ = R.line_peak(col, 'h', b['x'] + 3, 0, b['x'] + b['w'] - 3, 0, b['y'] - 4, b['y'] + 4)
    left, _ = R.line_peak(col, 'v', 0, b['y'] + 3, 0, b['y'] + 20, b['x'] - 4, b['x'] + 4)
    right, _ = R.line_peak(col, 'v', 0, b['y'] + 3, 0, b['y'] + 20, b['x'] + b['w'] - 5, b['x'] + b['w'] + 4)
    if top is None or left is None or right is None:
        return {'error': 'outline not found'}
    if b.get('h'):
        bottom, _ = R.line_peak(col, 'h', left + 3, 0, right - 3, 0, top + b['h'] - 5, top + b['h'] + 4)
    else:
        # the box may be taller than the slot the generator guessed (more lines than expected):
        # take the first horizontal line below the text where the left side ends (a corner)
        _, lst = R.line_peak(col, 'v', 0, top + 3, 0, top + 20, left - 2, left + 2)
        bottom = None
        for c in R.lines_in(col, 'h', left + 3, 0, right - 3, 0, top + 0.8 * fs, b['y'] + s['slot']['h'] + 4 * fs):
            sub, _, _ = R.crop(col, left - 1, c + 3, left + 1, c + 6)  # see outline_box.corner_ok
            if sub.size == 0 or float(np.percentile(sub.max(axis=1), 50)) < 0.5 * lst:
                bottom = c
                break
    if bottom is None:
        return {'error': 'bottom not found'}
    # line centres +- 0.5 = the 1 px border; content starts at its inner edge
    ct, cb, cl, cr = top + 0.5, bottom - 0.5, left + 0.5, right - 0.5
    ink = R.ink_extent(cl + 1.3, ct + 1.3, cr - 1.3, cb - 1.3)
    out = {'box': {'top': top - 0.5, 'bottom': bottom + 0.5, 'left': left - 0.5, 'right': right + 0.5}, 'content_h': cb - ct}
    if not ink:
        out['error'] = 'no ink'
        return out
    m = ink['mask']
    ox, oy = ink['origin']
    rows = m.any(axis=1)
    lines = []
    i = 0
    gap = max(2, int(0.12 * fs * S))
    while i < len(rows):
        if rows[i]:
            j = i
            last = i
            while j < len(rows) and (rows[j] or j - last < gap):
                if rows[j]:
                    last = j
                j += 1
            seg = m[i:last + 1]
            cols = np.nonzero(seg.any(axis=0))[0]
            lines.append({'top': oy + i / S - ct, 'bottom': oy + (last + 1) / S - ct,
                          'left': ox + cols[0] / S - cl, 'right': cr - (ox + (cols[-1] + 1) / S)})
            i = last + 1
        else:
            i += 1
    out['lines'] = len(lines)
    out['line_boxes'] = lines
    if len(lines) >= 2:
        out['line_pitch'] = float(np.median(np.diff([l['bottom'] for l in lines])))
        if not b.get('h') and abs(out['content_h'] - len(lines) * out['line_pitch']) > 0.4 * out['line_pitch']:
            return {'error': 'bottom ambiguous: %.1f px for %d lines of %.1f (another outline?)' % (out['content_h'], len(lines), out['line_pitch'])}
        L = np.array([l['left'] for l in lines])
        Rr = np.array([l['right'] for l in lines])
        spread = {'left': float(np.ptp(L)), 'right': float(np.ptp(Rr)), 'center': float(np.ptp(L - Rr))}
        out['align'] = min(spread, key=spread.get)
        out['align_spread'] = spread
    # ellipsis: the last line ends in three small dots of equal size
    if lines:
        ll = lines[-1]
        i0 = int(round((ll['top'] + ct - oy) * S))
        i1 = int(round((ll['bottom'] + ct - oy) * S))
        seg = m[max(0, i0):i1]
        lab, k = ndi.label(seg)
        objs = ndi.find_objects(lab)
        comps = sorted([(sl[1].start, (sl[1].stop - sl[1].start) * (sl[0].stop - sl[0].start), sl[0].stop) for sl in objs if sl is not None])
        dots = comps[-3:]
        small = (0.3 * fs * S) ** 2  # a dot with ~1 px camera bloom on each side
        areas = [a for _, a, _ in dots]
        out['ellipsis'] = bool(len(dots) == 3 and max(areas) <= small and max(areas) < 1.6 * min(areas)
                               and np.ptp([b for _, _, b in dots]) < 0.1 * fs * S)
    out['ink_outside_box'] = False
    return out


def measure_row(R, s):
    x0, y0, x1, y1 = s['region']
    out = {}
    for part in ('big', 'small'):
        col = s[part]['outline']
        bb, _ = R.mask_bbox(col, x0, y0, x1, y1)
        if not bb:
            return {'error': part + ' outline not found'}
        ink = R.ink_extent(bb[0] + 1.7, bb[1] + 1.7, bb[0] + bb[2] - 1.7, bb[1] + bb[3] - 1.7)
        out[part] = {'box': bb, 'ink_bottom': ink['bottom'] if ink else None, 'ink_top': ink['top'] if ink else None}
    out['box_bottom_diff'] = (out['small']['box'][1] + out['small']['box'][3]) - (out['big']['box'][1] + out['big']['box'][3])
    if out['big']['ink_bottom'] and out['small']['ink_bottom']:
        out['ink_bottom_diff'] = out['small']['ink_bottom'] - out['big']['ink_bottom']
    return out


def _nearest(hyp, got, key=None):
    def flat(v):
        if isinstance(v, dict):
            return [float(v[k]) if not isinstance(v[k], str) else v[k] for k in sorted(v)]
        return [float(a) for a in v]

    best = None
    ds = {}
    for name, exp in hyp.items():
        e = flat(exp)
        g = flat(got)
        if any(isinstance(a, str) for a in e):
            d = sum(0 if a == b else 10 for a, b in zip(e, g))
        else:
            d = sum(abs(a - b) for a, b in zip(e, g))
        ds[name] = round(d, 2)
        if best is None or d < ds[best]:
            best = name
    srt = sorted(ds.values())
    margin = srt[1] - srt[0] if len(srt) > 1 else None
    return best, ds, margin


def _rect_ch(c, alone=False):
    """Score channel for a colour. White next to pink / cyan outlines needs 'neutral' (white, not
    tinted); a white shape alone in its region (ring, corners) reads best from plain luma, which
    has no colour-fringe holes at the edges (Band 11 photos 2026-09-29)."""
    if c == 'white':
        return 'luma' if alone else 'neutral'
    return c


def measure_rect(R, s):
    m = s['metric']
    if m == 'bbox':
        x0, y0, x1, y1 = s['region']
        bb, _ = R.mask_bbox(_rect_ch(s.get('colour', 'any')), x0, y0, x1, y1)
        got = bb if bb else [0, 0, 0, 0]
        best, ds, margin = _nearest(s['hyp'], got)
        return {'bbox': [round(v, 2) for v in got], 'verdict': best, 'distances': ds, 'margin': margin, 'missing': bb is None}
    if m == 'ring':
        x0, y0, x1, y1 = s['region']
        bb, mm = R.mask_bbox(_rect_ch(s.get('colour', 'white'), alone=True), x0, y0, x1, y1)
        if not bb:
            return {'error': 'nothing drawn'}
        mask, ox, oy = mm
        ys_, xs_ = np.nonzero(mask)
        mask = mask[ys_.min():ys_.max() + 1, xs_.min():xs_.max() + 1]
        H_, W_ = mask.shape
        cy, cx = H_ // 2, W_ // 2

        def run(line):
            # the first bright run from the edge (a leading dark pixel or two is edge rounding)
            on = np.nonzero(line)[0]
            if not len(on) or on[0] > S:
                return 0.0
            off = np.nonzero(~line[on[0]:])[0]
            return (off[0] if len(off) else len(line) - on[0]) / S

        got = {'l': run(mask[cy, :]), 'r': run(mask[cy, ::-1]), 't': run(mask[:, cx]), 'b': run(mask[::-1, cx])}
        best, ds, margin = _nearest(s['hyp'], got)
        return {'thickness': {k: round(v, 2) for k, v in got.items()}, 'verdict': best, 'distances': ds, 'margin': margin}
    if m == 'corners':
        x0, y0, x1, y1 = s['region']
        bb, mm = R.mask_bbox(_rect_ch(s.get('colour', 'white'), alone=True), x0, y0, x1, y1)
        if not bb:
            return {'error': 'nothing drawn'}
        mask, ox, oy = mm
        ys, xs = np.nonzero(mask)
        a0, a1, b0, b1 = ys.min(), ys.max(), xs.min(), xs.max()
        sub = mask[a0:a1 + 1, b0:b1 + 1]
        got = {}
        for k, (fy, fx) in {'tl': (1, 1), 'tr': (1, -1), 'bl': (-1, 1), 'br': (-1, -1)}.items():
            q = sub[::fy, ::fx]
            n = min(q.shape)
            d = n
            for i in range(n):
                if q[i, i]:
                    d = i
                    break
            got[k] = round(d / S / ARC, 2)
        best, ds, margin = _nearest(s['hyp'], got)
        return {'radius': got, 'bbox': [round(v, 2) for v in bb], 'verdict': best, 'distances': ds, 'margin': margin}
    if m == 'colour_at':
        got = {}
        for k, (x, y) in s['points'].items():
            rgb, _ = R.mean(x - 1, y - 1, x + 1, y + 1)
            got[k] = colour_name(rgb, getattr(R, 'white', None))
        best, ds, margin = _nearest(s['hyp'], got)
        return {'colours': got, 'verdict': best, 'distances': ds, 'margin': margin}
    if m == 'luma_pair':
        a, _ = R.mean(*s['a'])
        b, _ = R.mean(*s['b'])
        la = 0.299 * a[0] + 0.587 * a[1] + 0.114 * a[2]
        lb = 0.299 * b[0] + 0.587 * b[1] + 0.114 * b[2]
        ratio = la / lb if lb > 1 else 0.0
        best, ds, margin = _nearest(s['hyp'], {'ratio': ratio})
        return {'luma_a': round(la, 1), 'luma_b': round(lb, 1), 'ratio': round(ratio, 3), 'verdict': best, 'distances': ds, 'margin': margin}
    return {'error': 'unknown metric ' + m}


def measure_corner(R, s):
    """Screen corner radius from a white square in the corner: the visible boundary of the square
    (first lit pixel along each row and each column, from the screen edge) is fitted with a circle
    (least squares), so it works whether or not the arc reaches the square's middle row. The
    circle's centre minus its radius gives the hidden strip along each edge."""
    b = s['box']
    k = s['corner']
    x0, y0, w, h = b['x'], b['y'], b['w'], b['h']
    sub, oy, ox = R.crop('white', x0, y0, x0 + w, y0 + h)
    pk = np.percentile(sub, 99)
    if pk < 60:
        return {'error': 'corner square not visible'}
    m = sub > pk / 2
    fy = 1 if k[0] == 't' else -1
    fx = 1 if k[1] == 'l' else -1
    q = m[::fy, ::fx]  # corner at (0, 0), screen edges along row 0 and column 0
    n = min(q.shape)
    d = next((i for i in range(n) if q[i, i]), n) / S
    pts = []
    for i in range(S, q.shape[0] - 2 * S):   # rows: first lit column
        on = np.nonzero(q[i])[0]
        if len(on) and on[0] > 0:
            pts.append((on[0] / S, (i + 0.5) / S))
    for j in range(S, q.shape[1] - 2 * S):   # columns: first lit row
        on = np.nonzero(q[:, j])[0]
        if len(on) and on[0] > 0:
            pts.append(((j + 0.5) / S, on[0] / S))
    out = {'diag_inset_px': round(d, 2)}
    P = np.array(pts, float)
    if len(P) >= 10:
        # algebraic (Kasa) circle fit, then keep the points on the arc (not the straight edges)
        for _ in range(3):
            A = np.c_[2 * P[:, 0], 2 * P[:, 1], np.ones(len(P))]
            bb = (P ** 2).sum(1)
            cx, cy, c = np.linalg.lstsq(A, bb, rcond=None)[0]
            r = math.sqrt(max(c + cx * cx + cy * cy, 0))
            res = np.abs(np.hypot(P[:, 0] - cx, P[:, 1] - cy) - r)
            keep = (res < max(0.6, 2.5 * np.median(res))) & (P[:, 0] < cx) & (P[:, 1] < cy)
            if keep.sum() < 10 or keep.all():
                break
            P = P[keep]
        res = np.hypot(P[:, 0] - cx, P[:, 1] - cy) - r
        out.update({'radius_px': round(r, 1), 'edge_hidden_x_px': round(cx - r, 2), 'edge_hidden_y_px': round(cy - r, 2),
                    'arc_points': int(len(P)), 'fit_rms_px': round(float(np.sqrt((res ** 2).mean())), 2)})
    else:
        out['radius_px'] = round(d / ARC, 1)
        out['note'] = 'too few arc points; radius from the diagonal alone (edges assumed 0)'
    return out


def measure_cap(R, s):
    """Capsule end (Band 10 / 11): a white cap the full width of the page and taller than the end
    radius. Its visible outline is the screen's end arc: a circle fitted to it gives the radius, the
    centre (x should be W/2) and the hidden rows at that end (centre - radius); the cap's last rows
    are the straight sides, whose first / last lit column are the hidden columns. The half-max edge
    of a saturated white area reads `bloom` px outside the true edge (the ruler fit's estimate), so
    the radius is reduced and the hidden strips increased by it.

    design_scale: W/2 over the fitted radius. A capsule's radius is half the panel's width, so with
    designWidth = the panel width (1 design px = 1 panel px) this is ~1.00-1.03 (the hidden columns
    make it a little over 1). Far from 1 means the page is drawn scaled: fix designWidth."""
    b = s['box']
    top = s['end'] == 'top'
    W = R.Wr / S
    sub, oy, ox = R.crop('white', b['x'], b['y'], b['x'] + b['w'], b['y'] + b['h'])
    pk = np.percentile(sub, 99)
    if pk < 60:
        return {'error': 'cap not visible'}
    m = ndi.binary_opening(sub > pk / 2, structure=np.ones((3, 3)))
    if not top:
        m = m[::-1]  # the screen's end at row 0 either way; d = distance from that end (band px)
    Hc, Wc = m.shape
    keep_rows = Hc - 2 * S  # not the cap's own inner edge
    pts = []
    for j in range(Wc):
        on = np.nonzero(m[:keep_rows, j])[0]
        if len(on) and 0 < on[0]:
            pts.append(((j + 0.5) / S, on[0] / S))
    lefts, rights = [], []
    for i in range(keep_rows):
        on = np.nonzero(m[i])[0]
        if not len(on):
            continue
        if on[0] > 0:
            pts.append((on[0] / S, (i + 0.5) / S))
        if on[-1] < Wc - 1:
            pts.append(((on[-1] + 1) / S, (i + 0.5) / S))
        lefts.append(((i + 0.5) / S, on[0] / S))
        rights.append(((i + 0.5) / S, (on[-1] + 1) / S))
    P = np.array(pts, float)
    P = P[P[:, 1] < 0.85 * Hc / S]
    if len(P) < 20:
        return {'error': 'too few arc points (%d)' % len(P)}
    for _ in range(6):
        A = np.c_[2 * P[:, 0], 2 * P[:, 1], np.ones(len(P))]
        cx, cd, c = np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)[0]
        r = math.sqrt(max(c + cx * cx + cd * cd, 0))
        res = np.abs(np.hypot(P[:, 0] - cx, P[:, 1] - cd) - r)
        keep = (res < max(0.6, 2.5 * np.median(res))) & (P[:, 1] < cd)
        if keep.sum() < 20 or keep.all():
            break
        P = P[keep]
    res = np.hypot(P[:, 0] - cx, P[:, 1] - cd) - r
    bloom = getattr(R, 'bloom', 0.0)
    straight = [v for d, v in lefts if d > cd + 1]
    straight_r = [v for d, v in rights if d > cd + 1]
    r_true = r - bloom
    out = {'radius_raw_px': round(r, 2), 'radius_px': round(r_true, 2), 'bloom_px': round(bloom, 2),
           'centre_x': round(cx + ox, 2), 'centre_from_end_px': round(cd, 2),
           'hidden_end_px': round(max(0.0, cd - r_true), 2),
           'arc_points': int(len(P)), 'fit_rms_px': round(float(np.sqrt((res ** 2).mean())), 2),
           'centre_offset_x': round(cx + ox - W / 2, 2), 'design_scale': round((W / 2) / r_true, 4)}
    if straight:
        out['hidden_left_px'] = round(max(0.0, float(np.median(straight)) + ox + bloom), 2)
    if straight_r:
        out['hidden_right_px'] = round(max(0.0, W - (float(np.median(straight_r)) + ox) + bloom), 2)
    out['straight_rows'] = len(straight)
    return out


def measure_comb(R, s):
    vals = []
    for x in s['xs']:
        sub, oy, ox = R.crop('white', x - 0.5, s['y0'], x + 1.5, s['y1'])
        if sub.size == 0:
            continue
        p = sub.max(axis=1)
        if p.max() < 60:
            vals.append(None)
            continue
        idx = np.nonzero(p > p.max() / 2)[0]
        if s['edge'] == 'top':
            vals.append(oy + idx[0] / S - s['y0'])
        else:
            vals.append(s['y1'] - (oy + (idx[-1] + 1) / S))
    good = [v for v in vals if v is not None]
    return {'hidden_px': round(float(np.median(good)), 2) if good else None, 'per_line': [None if v is None else round(v, 2) for v in vals]}


def measure_swatch(R, s):
    b = s['box']
    mx, my = b['w'] * 0.2, b['h'] * 0.2
    rgb, sd = R.mean(b['x'] + mx, b['y'] + my, b['x'] + b['w'] - mx, b['y'] + b['h'] - my)
    return {'rgb': [round(float(v), 1) for v in rgb], 'luma': round(float(0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]), 1), 'sd': round(sd, 2)}


def measure_ramp(R, s):
    def prof(r):
        sub, oy, ox = R.crop('luma', r['x'], r['y'] + r['h'] * 0.25, r['x'] + r['w'], r['y'] + r['h'] * 0.75)
        return sub.mean(axis=0)

    a, b = prof(s['a']), prof(s['b'])
    n = min(len(a), len(b))
    q = [int(n * f) for f in (0.1, 0.25, 0.5, 0.75, 0.9)]
    return {'alpha': [round(float(a[i]), 1) for i in q], 'grey': [round(float(b[i]), 1) for i in q],
            'rms_diff': round(float(np.sqrt(((a[:n] - b[:n]) ** 2).mean())), 1)}


MEASURE = {'text_v': measure_text_v, 'text_w': measure_text_w, 'wrap': measure_wrap, 'row': measure_row,
           'rect': measure_rect, 'corner': measure_corner, 'cap': measure_cap, 'comb': measure_comb, 'swatch': measure_swatch,
           'background': measure_swatch,
           'ramp': measure_ramp}


def read_barcode(R, code):
    if not code:
        return None
    vals = []
    for i in range(8):
        x = code['x'] + i * code['pitch']
        v, _ = R.mean(x + code['cell'] * 0.2, code['y'] + code['h'] * 0.2, x + code['cell'] * 0.8, code['y'] + code['h'] * 0.8)
        vals.append(float(v.mean()))
    hi = min(vals[0], vals[7])
    lo = min(vals)
    if hi < 60 or hi - lo < 30:
        return None
    bits = [1 if v > (hi + lo) / 2 else 0 for v in vals]
    if bits[0] != 1 or bits[7] != 1:
        return None
    data = bits[1:6]
    if sum(data) % 2 != bits[6]:
        return None
    return int(''.join(map(str, data)), 2)


def measure_photo(path, layout, page_id=None, annotate_dir=None):
    img = load_photo(path)
    bars = []
    for p in layout['pages']:
        key = json.dumps(p.get('bar') or layout['frame']['bar'], sort_keys=True)
        if key not in [json.dumps(b, sort_keys=True) for b in bars]:
            bars.append(p.get('bar') or layout['frame']['bar'])
    if page_id is not None:
        pg = next(p for p in layout['pages'] if p['id'] == page_id)
        bars = [pg.get('bar') or layout['frame']['bar']]
    best = None
    errors = []
    for bar in bars:
        try:
            f = Fit(img, layout, bar).run()
        except RuntimeError as e:
            errors.append(str(e))
            continue
        if best is None or (f.n_ticks, -max(f.rms)) > (best.n_ticks, -max(best.rms)):
            best = f
    if best is None:
        return {'photo': os.path.basename(path), 'error': '; '.join(errors)}
    f = best
    rect = f.rectify()
    R = Rect(rect, white=ruler_white(rect, layout))
    R.bloom = f.bloom
    pid = page_id
    if pid is None:
        for p in layout['pages']:
            if (p.get('bar') or layout['frame']['bar']) != f.bar_spec:
                continue
            got = read_barcode(R, p.get('code') or layout['frame'].get('code'))
            if got is not None:
                pid = got
                break
    if pid is None:
        return {'photo': os.path.basename(path), 'error': 'page barcode not readable; pass --page N', 'fit': _fit_info(f)}
    page = next((p for p in layout['pages'] if p['id'] == pid), None)
    if page is None:
        return {'photo': os.path.basename(path), 'error': 'page %d not in the layout' % pid}
    out = {'photo': os.path.basename(path), 'page': pid, 'page_key': page['key'], 'kit': (layout.get('app') or {}).get('version'),
           'fit': _fit_info(f), 'samples': []}
    for s in page['samples']:
        fn = MEASURE.get(s['type'])
        if not fn:
            continue
        try:
            r = fn(R, s)
        except Exception as e:  # keep going: one bad sample shouldn't lose the photo
            r = {'error': '%s: %s' % (type(e).__name__, e)}
        out['samples'].append({'id': s['id'], 'type': s['type'], 'spec': s, 'result': r})
    _mark_overlaps(out['samples'])
    if annotate_dir:
        os.makedirs(annotate_dir, exist_ok=True)
        annotate(R, out, os.path.join(annotate_dir, os.path.splitext(os.path.basename(path))[0] + '.annot.png'))
    return json.loads(json.dumps(out, default=_plain))


def _mark_overlaps(samples):
    """A natural (no height) text box that wrapped grows downwards over whatever was placed below
    it. Samples it covers are unreliable (foreign ink, hidden outlines): turn them into errors."""
    grown = []
    for m in samples:
        sp, r = m['spec'], m['result']
        if m['type'] == 'wrap' and not sp['box'].get('h'):
            slot_b = sp['slot']['y'] + sp['slot']['h']
            if 'error' in r:
                grown.append((m['id'], sp['box']['x'], sp['box']['y'], sp['box']['w'], slot_b + 3 * 1.33 * sp['px']))
            elif r['box']['bottom'] > slot_b + 1:
                grown.append((m['id'], sp['box']['x'], sp['box']['y'], sp['box']['w'], r['box']['bottom']))
            continue
        if m['type'] != 'text_v' or sp.get('regime') != 'nat' or len(sp['str']) < 2:
            continue
        if r.get('wrapped'):
            grown.append((m['id'], sp['box']['x'], sp['box']['y'], sp['box']['w'], r['box']['bottom']))
        elif 'error' in r:  # not found: probably wrapped off the page; assume two lines
            grown.append((m['id'], sp['box']['x'], sp['box']['y'], sp['box']['w'], sp['box']['y'] + 2 * 1.33 * sp['px'] + 2))
    # top to bottom: a box covered by one above it can't itself be trusted to have grown
    order = sorted(samples, key=lambda m: ((m['spec'].get('box') or m['spec'].get('slot') or {}).get('y', 0)))
    for m in order:
        b = m['spec'].get('box') or m['spec'].get('slot')
        if not b or 'error' in m['result']:
            continue
        bx, by, bw_, bh = b['x'], b['y'], b.get('w') or 0, b.get('h') or (m['spec'].get('slot') or {}).get('h') or 0
        for gid, gx, gy, gw, gb in grown:
            if gid == m['id']:
                continue
            if gx < bx + bw_ and bx < gx + gw and gy < by + bh and by < gb:
                m['result'] = {'error': 'covered by %s, which wrapped' % gid, 'was': m['result']}
                grown = [g for g in grown if g[0] != m['id']]
                break


def _fit_info(f):
    return {'rms_band_px': [round(v, 3) for v in f.rms], 'ticks': f.n_ticks, 'dropped': f.n_dropped, 'bloom_px': round(f.bloom, 2),
            'photo_px_per_band_px': [round(v, 3) for v in f.scale], 'edges': f.edge, 'ok': f.ok, 'notes': f.notes}


def annotate(R, out, path):
    im = R.img.copy()
    sc = 2  # draw at S, save at S/2... keep lines visible
    for s in out['samples']:
        r = s['result']
        box = r.get('box')
        if isinstance(box, dict):
            p0 = (int(box['left'] * S), int(box['top'] * S))
            p1 = (int(box['right'] * S), int(box['bottom'] * S))
            cv2.rectangle(im, p0, p1, (0, 255, 0), 2)
            if 'ink_top' in r and 'content_h' in r:
                for v in (r['ink_top'], r['ink_bottom']):
                    y = int((box['top'] + 1 + v) * S)
                    cv2.line(im, (p0[0], y), (p1[0], y), (255, 140, 0), 2)
        bb = r.get('bbox')
        if bb:
            cv2.rectangle(im, (int(bb[0] * S), int(bb[1] * S)), (int((bb[0] + bb[2]) * S), int((bb[1] + bb[3]) * S)), (0, 255, 0), 2)
        if r.get('verdict'):
            sp = s['spec']
            reg = sp.get('slot') or {}
            x = int(reg.get('x', 0) * S)
            y = int((reg.get('y', 0) + reg.get('h', 12)) * S) - 6
            cv2.putText(im, r['verdict'][:18], (x, y), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 0), 2)
    Image.fromarray(cv2.resize(im, (im.shape[1] // sc, im.shape[0] // sc), interpolation=cv2.INTER_AREA)).save(path)


# ---------------------------------------------------------------------------------------------
# profile
# ---------------------------------------------------------------------------------------------
def get_path(d, path, create=False):
    """path: 'a.b.c', or a list of keys when a key contains a dot (a string like ':.,-/%')."""
    keys = path if isinstance(path, (list, tuple)) else path.split('.')
    cur = d
    for k in keys[:-1]:
        if k not in cur:
            if not create:
                return None, None
            cur[k] = {}
        cur = cur[k]
    return cur, keys[-1]


def set_fact(profile, path, value, source, status='measured', extra=None):
    parent, key = get_path(profile, path, create=True)
    fact = {'value': value, 'status': status, 'source': source, 'date': datetime.date.today().isoformat()}
    if extra:
        fact.update(extra)
    old = parent.get(key)
    if isinstance(old, dict) and 'note' in old and 'note' not in fact:
        fact['note'] = old['note']
    parent[key] = fact


def wmean(pairs):
    pairs = [(v, w) for v, w in pairs if v is not None]
    if not pairs:
        return None
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs)


# Verdict names that mean "the band does what the CSS says" / "it doesn't" (profile `supported`).
POSITIVE = {'honoured', 'clamped', 'clips_at_padding_box', 'draws_outside', 'round_clip', 'drawn', 'scaled',
            'stretched', 'fill', 'contain', 'cover', 'matches_opaque_grey', 'shrink_wrap'}
NEGATIVE = {'ignored', 'ignored_full', 'square', 'no_clip', 'missing', 'all_zero', 'invisible', 'square_clip',
            'clips', 'child_shrunk', 'all_corners', 'natural_top_left', 'natural_centred', 'none_top_left', 'differs'}


def supported(verdict):
    return True if verdict in POSITIVE else False if verdict in NEGATIVE else None


def apply_results(profile, results):
    """Merge measured page results into the profile. Returns the list of fact paths written."""
    written = []
    photos = sorted({r['photo'] for r in results if 'samples' in r})

    def src(kind):
        ps = sorted({r['photo'] for r in results if 'samples' in r and any(s['type'] == kind for s in r['samples'])})
        return 'photos ' + ', '.join(ps)

    def put(path, value, kind, extra=None):
        set_fact(profile, path, value, src(kind), extra=extra)
        written.append(path)

    samples = [s for r in results if 'samples' in r and r['fit']['ok'] for s in r['samples']]
    tv = [s for s in samples if s['type'] == 'text_v' and 'error' not in s['result']]
    nat = [s for s in tv if s['spec']['regime'] == 'nat']
    # line box
    if nat:
        per = {}
        for s in nat:
            per.setdefault(s['spec']['px'], []).append(s['result'].get('line_h', s['result']['content_h']))
        lb = wmean([(s['result'].get('line_h', s['result']['content_h']) / s['spec']['px'], s['spec']['px']) for s in nat])
        put('font.line_box_em', round(lb, 4), 'text_v', {'by_size_px': {str(k): round(float(np.mean(v)), 2) for k, v in sorted(per.items())}})
        # ink per glyph class, relative to the line box top, from natural boxes
        for chars, name in (('0123456789', 'digit'), ('H', 'cap'), ('g', 'descender')):
            tops, bots = [], []
            for s in nat:
                gl = s['result'].get('glyphs') or {}
                for ch in chars:
                    g = gl.get(ch)
                    if not g:
                        continue
                    tops.append((g['top'] / s['spec']['px'], s['spec']['px']))
                    bots.append((g['bottom'] / s['spec']['px'], s['spec']['px']))
            if tops:
                put('font.ink.%s.top_em' % name, round(wmean(tops), 4), 'text_v')
                put('font.ink.%s.bottom_em' % name, round(wmean(bots), 4), 'text_v')
    # regimes
    L = profile.get('font', {}).get('line_box_em', {}).get('value')
    dig = profile.get('font', {}).get('ink', {}).get('digit', {})
    t0, b0 = (dig.get('top_em') or {}).get('value'), (dig.get('bottom_em') or {}).get('value')
    if L and t0 is not None and b0 is not None:
        # A string wider than its box (it could wrap, but a box with an explicit height draws one
        # line, cut at the right) is placed differently: measured separately as regime "overflow_x".
        def over_x(s):
            return bool(s['spec'].get('too_wide')) or (len(s['spec']['str']) > 1 and bool(s['result'].get('clipped_right')))

        for regime, path in (('tall', 'font.regime.taller_box'), ('short', 'font.regime.shorter_box'),
                             ('overflow_x', 'font.regime.taller_box_text_too_wide')):
            errs = {'centre': [], 'top': [], 'bottom': []}
            clipped = []
            for s in tv:
                if regime == 'overflow_x':
                    if s['spec']['regime'] != 'tall' or not over_x(s):
                        continue
                elif s['spec']['regime'] != regime or over_x(s):
                    continue
                gl = s['result'].get('glyphs') or {}
                g = next((gl[c] for c in '0123456789' if c in gl), None)
                if g is None:
                    if len(s['spec']['str']) > 1:
                        continue  # a string whose digit couldn't be isolated (cut off, merged)
                    g = {'top': s['result']['ink_top'], 'bottom': s['result']['ink_bottom']}
                pxs = s['spec']['px']
                hc = s['result']['content_h']
                Lp = L * pxs
                for rule, shift in (('centre', (hc - Lp) / 2), ('top', 0.0), ('bottom', hc - Lp)):
                    pt = max(0.0, t0 * pxs + shift)
                    pb = min(hc, b0 * pxs + shift)
                    errs[rule].append((abs(pt - g['top']) + abs(pb - g['bottom'])) / pxs)
                # clipped: the DIGIT's ink reaches the content edge (a descender 1-2 px from the edge
                # of a 1.5 em box at 24 px isn't a clip: Band 11 photos 2026-09-29)
                clipped.append(bool(g['top'] < 1.8 or g['bottom'] > hc - 1.8))  # ink is read 1.3 px inside the content box
            if errs['centre']:
                mean_err = {k: float(np.mean(v)) for k, v in errs.items()}
                rule = min(mean_err, key=mean_err.get)
                put(path + '.rule', rule, 'text_v', {'fit_error_em': {k: round(v, 4) for k, v in mean_err.items()}, 'samples': len(errs['centre'])})
                put(path + '.clipped', any(clipped), 'text_v')
    # advance widths
    tw = [s for s in samples if s['type'] == 'text_w' and 'error' not in s['result']]
    digits = {}
    strings = {}
    for s in tw:
        st, pxs, wt = s['spec']['str'], s['spec']['px'], s['spec']['weight']
        em_w = s['result']['content_w'] / pxs
        strings.setdefault(wt, {}).setdefault(st, []).append((em_w, pxs))
        if wt == 'bold' and len(set(st)) == 1 and st[0].isdigit():
            digits.setdefault(st[0], []).append((em_w / len(st), pxs))
    for d, v in sorted(digits.items()):
        put(['font', 'advance_em', d], round(wmean(v), 4), 'text_w')
    for wt, table in strings.items():
        for st, v in table.items():
            put(['font', 'string_em', wt, st], round(wmean(v), 4), 'text_w')
    b0000 = strings.get('bold', {}).get('0000')
    sp = strings.get('bold', {}).get('0 0 0 0')
    if b0000 and sp:
        put(['font', 'advance_em', ' '], round((wmean(sp) - wmean([(a, w) for a, w in b0000 if w == 32] or b0000)) / 3, 4), 'text_w')
    n48 = [a for a, w in strings.get('normal', {}).get('0000', [])]
    b48 = [a for a, w in (b0000 or []) if w == 48]
    if n48 and b48:
        put('font.weights.normal_differs_from_bold', abs(n48[0] - b48[0]) > 0.02, 'text_w', {'normal_0000_em': round(n48[0], 4), 'bold_0000_em': round(b48[0], 4)})
    # wrap
    for s in samples:
        if s['type'] != 'wrap' or 'error' in s['result']:
            continue
        k = s['spec']['key']
        r = s['result']
        rec = {kk: r.get(kk) for kk in ('lines', 'line_pitch', 'align', 'ellipsis', 'content_h')}
        put('text.wrap.' + k, rec, 'wrap')
        lh = (s['spec'].get('css') or {}).get('line-height')
        if lh and k.startswith('lh') and not s['spec']['box'].get('h'):
            want = int(str(lh).replace('px', ''))
            nat = (profile.get('font', {}).get('line_box_em') or {}).get('value')
            got = r['content_h']
            verdict = 'honoured' if abs(got - want) < 1.5 else 'ignored' if nat and abs(got - nat * s['spec']['px']) < 1.5 else 'other'
            put('text.line_height_css', verdict, 'wrap', {'supported': supported(verdict), 'detail': {'css': lh, 'px': s['spec']['px'], 'content_h': round(got, 2)}})
    for s in samples:
        if s['type'] == 'row' and 'error' not in s['result']:
            put('text.row.' + s['spec']['align'], {k: s['result'].get(k) for k in ('box_bottom_diff', 'ink_bottom_diff')}, 'row')
    # rect facts
    for s in samples:
        if s['type'] == 'rect' and s['spec'].get('fact') and 'verdict' in s['result']:
            r = s['result']
            v = r['verdict']
            ds = r.get('distances') or {}
            if r.get('margin') is not None and r['margin'] < 1e-6 and ds:
                # two hypotheses predict the same picture: the page can't tell them apart
                v = '|'.join(sorted(k for k, d in ds.items() if d - min(ds.values()) < 1e-6))
            put(s['spec']['fact'].split('.', 1), v, 'rect', {'supported': supported(v) if '|' not in v else None, 'what': s['spec'].get('what'),
                                               'detail': {k: r[k] for k in r if k not in ('verdict',)}})
    # geometry
    cs = [s for s in samples if s['type'] == 'corner' and 'error' not in s['result']]
    if cs:
        put('screen.corner_radius_px', {s['spec']['corner']: s['result']['radius_px'] for s in cs}, 'corner')
        put('screen.corner_detail', {s['spec']['corner']: s['result'] for s in cs}, 'corner')
    for s in samples:
        if s['type'] == 'comb' and s['result'].get('hidden_px') is not None:
            put('screen.hidden_px.' + s['spec']['edge'], s['result']['hidden_px'], 'comb')
    # capsule ends (Band 10 / 11): radius, hidden rows / columns, and the design-px scale check
    caps = {s['spec']['end']: s['result'] for s in samples if s['type'] == 'cap' and 'error' not in s['result']}
    cap_sides = False
    if caps:
        rad = {k: v['radius_px'] for k, v in caps.items()}
        put('screen.shape', 'capsule', 'cap')
        put('screen.end_radius_px', rad, 'cap', {'note': 'radius of each semicircular end (bloom-corrected), band px'})
        put('screen.corner_radius_px', {'tl': rad.get('top'), 'tr': rad.get('top'), 'bl': rad.get('bottom'), 'br': rad.get('bottom')}, 'cap',
            {'note': 'capsule: each end is one arc; given per corner so profile.js safeArea / xRange work unchanged'})
        put('screen.cap_detail', caps, 'cap')
        for k, v in caps.items():
            put('screen.hidden_px.' + k, v['hidden_end_px'], 'cap')
        hl = [v['hidden_left_px'] for v in caps.values() if v.get('hidden_left_px') is not None]
        hr = [v['hidden_right_px'] for v in caps.values() if v.get('hidden_right_px') is not None]
        if hl and hr:
            put('screen.hidden_px.left', round(float(np.median(hl)), 2), 'cap')
            put('screen.hidden_px.right', round(float(np.median(hr)), 2), 'cap')
            cap_sides = True
        sc = float(np.mean([v['design_scale'] for v in caps.values()]))
        off = max(abs(v['centre_offset_x']) for v in caps.values())
        one = abs(sc - 1) < 0.06 and off < 4
        Wd = profile['device']['screen']['w']['value'] if isinstance(profile['device']['screen'].get('w'), dict) else profile['device']['screen']['w']
        put('device.design_scale', round(sc, 4), 'cap', {'one_to_one': one, 'centre_offset_x': off,
            'note': 'W/2 over the fitted end radius: ~1.00-1.03 when 1 design px = 1 panel px (a capsule end radius is half the panel width)'})
        if one:
            put('device.design_width', Wd, 'cap', {'note': 'manifest designWidth %s draws 1 design px per panel px: the end arcs fit radius %s centred at x %s'
                                                   % (Wd, rad, [v['centre_x'] for v in caps.values()])})
        else:
            print('WARNING: the capsule outline says the page is drawn at %.3f panel px per design px (centre offset %.1f px): '
                  'the kit\'s designWidth is wrong for this band, and every other fact from these photos is in design px' % (1 / sc, off))
    fits = [r['fit']['edges'] for r in results if 'fit' in r and r['fit']['ok']]
    lv = [e['left_first_visible_x'] for e in fits if e.get('left_first_visible_x') is not None]
    rv = [e['right_last_visible_x'] for e in fits if e.get('right_last_visible_x') is not None]
    if lv and not cap_sides:
        W = profile['device']['screen']['w']['value'] if isinstance(profile['device']['screen'].get('w'), dict) else profile['device']['screen']['w']
        note = {'note': 'from the outer ends of the ruler ticks (bloom-corrected), +-1 px; the Screen geometry page measures it directly'}
        set_fact(profile, 'screen.hidden_px.left', round(max(0.0, float(np.median(lv))), 2), 'rulers in photos ' + ', '.join(photos), extra=note)
        written.append('screen.hidden_px.left')
        if rv:
            set_fact(profile, 'screen.hidden_px.right', round(max(0.0, W - float(np.median(rv))), 2), 'rulers in photos ' + ', '.join(photos), extra=note)
            written.append('screen.hidden_px.right')
    # colour
    sw = [s for s in samples if s['type'] == 'swatch']
    if sw:
        # Black: the page's big empty area (kit 2.0.0 'background' sample) when measured; else the
        # #000000 grey swatch. Red / green / blue ramps are judged on their own channel (blue is
        # only 0.114 of luma), grey and surface on luma. A row whose own darkest swatch already reads
        # above black is contaminated (bloom from brighter neighbours in narrow swatches: Band 11
        # photos 2026-09-29, #000000 at luma 45 over a black of 3): it is then judged against that
        # swatch instead, and says so.
        bgs = [s['result'] for s in samples if s['type'] == 'background' and 'rgb' in s['result']]
        g0 = [s['result'] for s in sw if s['spec']['group'] == 'grey' and s['spec']['value'] == 0]
        black = bgs[0] if bgs else (g0[0] if g0 else {'rgb': [0.0, 0.0, 0.0], 'luma': 0.0, 'sd': 1.0})
        thr = max(4.0, 4 * float(black.get('sd') or 1.0))
        CH = {'red': 0, 'green': 1, 'blue': 2}

        def level(res, group):
            return float(res['rgb'][CH[group]]) if group in CH else float(res['luma'])

        for group in ('grey', 'red', 'green', 'blue', 'surface'):
            g = sorted([s for s in sw if s['spec']['group'] == group], key=lambda s: s['spec']['value'])
            if not g:
                continue
            base = level(black, group)
            extra = {}
            if group == 'grey' and g[0]['spec']['value'] == 0 and level(g[0]['result'], group) - base > thr:
                extra['contaminated'] = 'the #000000 swatch reads %.1f over black %.1f (glare / bloom from neighbours); judged against it instead' % (
                    level(g[0]['result'], group), base)
                base = level(g[0]['result'], group)
            vis = [s['spec']['value'] for s in g if level(s['result'], group) - base > thr]
            floor = min(vis) if vis else None
            extra.update({'levels': {s['spec']['hex']: round(level(s['result'], group), 1) for s in g}, 'black_level': round(base, 1),
                          'measure': 'channel' if group in CH else 'luma', 'threshold': round(thr, 1),
                          'note': 'lowest value the camera saw above black (the lowest step on the page is %s); confirm by eye' % g[0]['spec']['hex']})
            put('colour.floor.' + group, floor, 'swatch', extra)
        put('colour.brand', {s['spec']['hex']: s['result']['rgb'] for s in sw if s['spec']['group'] == 'brand'}, 'swatch')
    for s in samples:
        if s['type'] == 'ramp':
            put(s['spec']['fact'], 'matches_opaque_grey' if s['result']['rms_diff'] < 12 else 'differs', 'ramp', {'detail': s['result']})
    return written


def load_json(p):
    with open(p) as f:
        return json.load(f)


def _plain(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o).__name__)


# Profiles live in the workspace's devices/<model>/ (profile.json, evidence/, photos/); a model
# without one reads the plugin's shipped default (workspace.py).
# Sections of a vela-device-profile/2: quick-app facts are nested under "quickapp"; apply_results
# and `set` work on a flat view (font, css, ... next to device and screen) and nest them back.
QUICKAPP_KEYS = ('font', 'text', 'colour', 'css', 'animation', 'image', 'behaviour')
TOP_ORDER = ('schema', 'about', 'updated', 'firmware', 'device', 'screen', 'quickapp', 'face')


def flat_view(prof):
    """{..., quickapp: {font, css, ...}} -> {..., font, css, ...} (shares the nested objects)."""
    if 'quickapp' not in prof:
        return dict(prof), False
    v = {k: x for k, x in prof.items() if k != 'quickapp'}
    v.update(prof['quickapp'])
    return v, True


def nest_view(view, nested):
    """Inverse of flat_view: quick-app keys back under "quickapp", top-level keys in TOP_ORDER."""
    if not nested:
        return view
    q = {k: view[k] for k in QUICKAPP_KEYS if k in view}
    rest = {k: x for k, x in view.items() if k not in QUICKAPP_KEYS}
    rest['quickapp'] = q
    out = {k: rest[k] for k in TOP_ORDER if k in rest}
    out.update({k: x for k, x in rest.items() if k not in out})
    return out


def profile_arg(a, write=False):
    """--profile PATH wins; otherwise the workspace's devices/<--device>/profile.json (for reading,
    the shipped default when the workspace has none; for writing, seeded from that default)."""
    if a.profile:
        return a.profile
    if write:
        return ws.write_profile_path(a.device, a.workspace)
    return ws.read_profile_path(a.device, a.workspace)


def save_json(p, d):
    with open(p, 'w') as f:
        json.dump(d, f, indent=1, ensure_ascii=False, default=_plain)
        f.write('\n')


# ---------------------------------------------------------------------------------------------
# synthetic self-test
# ---------------------------------------------------------------------------------------------
def render_synthetic(layout, page, rule_short='top', rule_tall='centre', rule_wide='top', line_em=1.3, K=4, corner_r=0, capsule_inset=None):
    """Draw a page at K px per band px the way the band would (rulers, bar, barcode, text samples).
    corner_r: a rounded-rectangle screen mask; capsule_inset: a capsule mask (semicircle ends) whose
    straight sides are that many px inside the page's left and right edges."""
    from PIL import ImageDraw, ImageFont
    W, H = layout['screen']['w'], layout['screen']['h']
    im = Image.new('RGB', (W * K, H * K), (0, 0, 0))
    dr = ImageDraw.Draw(im)
    fr = layout['frame']
    col = {'white': (255, 255, 255), 'yellow': (255, 214, 10), 'pink': (255, 45, 149), 'cyan': (0, 229, 255), 'green': (60, 255, 60)}

    def rect(x, y, w, h, c):
        dr.rectangle((x * K, y * K, (x + w) * K - 1, (y + h) * K - 1), fill=c)

    for i, t in enumerate(fr['ticks']):
        ln = fr['tick_len'][t]
        c = col['yellow'] if t == 2 else col['white']
        rect(0, i * fr['tick_every'], ln, 1, c)
        rect(W - ln, i * fr['tick_every'], ln, 1, c)
    bar = page.get('bar') or fr['bar']
    rect(bar['x'], bar['y'], bar['len'], bar['h'], col['yellow'])
    code = page.get('code') or fr['code']
    bits = [1] + [(page['id'] >> b) & 1 for b in range(4, -1, -1)]
    bits += [sum(bits[1:]) % 2, 1]
    for i, b in enumerate(bits):
        if b:
            rect(code['x'] + i * code['pitch'], code['y'], code['cell'], code['h'], col['white'])
    font_path = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
    for s in page['samples']:
        if s['type'] not in ('text_v', 'text_w'):
            continue
        pxs = s['px']
        f = ImageFont.truetype(font_path, pxs * K)
        asc = 0.95  # baseline below the line-box top, em (synthetic font model)
        Lp = round(line_em * pxs)
        tw = f.getlength(s['str']) / K
        x, y = s['box']['x'], s['box']['y']
        if s['type'] == 'text_w':
            w = math.ceil(tw) + 2
            h = Lp + 2
        else:
            w = s['box']['w']
            h = s['box']['h'] or Lp + 2
        hc = h - 2
        tall_rule = rule_wide if s.get('too_wide') else rule_tall
        shift = 0 if hc >= Lp and s['type'] == 'text_w' else (
            (hc - Lp) / 2 if (hc >= Lp and tall_rule == 'centre') or (hc < Lp and rule_short == 'centre') else 0)
        # glyphs into a clipped layer (the band clips a label's ink to its own box)
        layer = Image.new('L', (w * K, h * K), 0)
        ImageDraw.Draw(layer).text((K, (1 + shift + asc * pxs) * K), s['str'], font=f, fill=255, anchor='ls')
        lay = np.asarray(layer).copy()
        lay[: K, :] = 0
        lay[(h - 1) * K:, :] = 0
        im.paste(Image.new('RGB', layer.size, (255, 255, 255)), (x * K, y * K), Image.fromarray(lay))
        c = col[s['outline']]
        dr.rectangle((x * K, y * K, (x + w) * K - 1, (y + h) * K - 1), outline=c, width=K)
    # the other sample types, drawn as their FIRST hypothesis says (so its verdict must win)
    for s in page['samples']:
        t = s['type']
        if t == 'corner' or t == 'swatch' or t == 'cap':
            b = s['box']
            c = col['white'] if t in ('corner', 'cap') else tuple(int(s['hex'][i:i + 2], 16) for i in (1, 3, 5))
            rect(b['x'], b['y'], b['w'], b['h'], c)
        elif t == 'comb':
            for x in s['xs']:
                rect(x, s['y0'], 1, s['y1'] - s['y0'], col['white'])
        elif t == 'rect':
            first = next(iter(s['hyp'].values()))
            c = col.get(s.get('colour'), col['white'])
            m = s['metric']
            if m == 'bbox' and first[2] > 0:
                rect(first[0], first[1], first[2], first[3], c)
            elif m == 'ring':
                x0, y0, x1, y1 = s['region']
                x0, y0, x1, y1 = x0 + 6, y0 + 6, x1 - 6, y1 - 6
                rect(x0, y0, x1 - x0, y1 - y0, c)
                rect(x0 + first['l'], y0 + first['t'], x1 - x0 - first['l'] - first['r'], y1 - y0 - first['t'] - first['b'], (0, 0, 0))
            elif m == 'corners':
                x0, y0, x1, y1 = s['region']
                r = max(first.values())
                box = ((x0 + 6) * K, (y0 + 6) * K, (x1 - 6) * K - 1, (y1 - 6) * K - 1)
                if r:
                    dr.rounded_rectangle(box, radius=r * K, fill=c, corners=tuple(first[k] > 0 for k in ('tl', 'tr', 'br', 'bl')))
                else:
                    dr.rectangle(box, fill=c)
            elif m == 'colour_at':
                for k, (x, y) in s['points'].items():
                    rect(x - 2, y - 2, 4, 4, col[first[k]])
    if corner_r:
        mask = Image.new('L', im.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.size[0] - 1, im.size[1] - 1), radius=corner_r * K, fill=255)
        im = Image.composite(im, Image.new('RGB', im.size, (0, 0, 0)), mask)
    if capsule_inset is not None:
        mask = Image.new('L', im.size, 0)
        r = (W - 2 * capsule_inset) / 2
        ImageDraw.Draw(mask).rounded_rectangle((capsule_inset * K, 0, (W - capsule_inset) * K - 1, im.size[1] - 1), radius=r * K, fill=255)
        im = Image.composite(im, Image.new('RGB', im.size, (0, 0, 0)), mask)
    return im


def selftest(devices=('band10pro', 'band11')):
    """Synthetic end-to-end check for every layout: render pages as the band would (a rounded-corner
    screen for the Band 10 Pro, a capsule with 2 px hidden at each side for the Band 11), warp and
    blur them like a handheld photo, and check that page ID, ruler fit, line box, regimes (incl. a
    string wider than its box), advance widths, box-model verdicts and the screen outline (corner
    radius / capsule end radius, hidden edges, design scale) come back right."""
    ok = True
    for dev in devices:
        ok = _selftest_device(dev) and ok
    print('selftest', 'PASS' if ok else 'FAIL')
    return 0 if ok else 1


def _selftest_device(dev):
    import tempfile
    from PIL import ImageFont
    layout = load_json(os.path.join(HERE, 'layouts', dev + '.json'))
    W, H = layout['screen']['w'], layout['screen']['h']
    capsule = layout['screen'].get('shape') == 'capsule'
    INSET = 2  # capsule: hidden columns on each side
    rng = np.random.default_rng(3)
    ok = True
    tmp = tempfile.mkdtemp()
    results = []
    keys = [p['key'] for p in layout['pages'] if p['key'].startswith('tv')] + ['th1', 'bx1', 'bx2', 'geo', 'colour']
    print('--- %s (%d x %d, %s): pages %s' % (dev, W, H, 'capsule, %d px hidden each side' % INSET if capsule else 'corner radius 30', ' '.join(keys)))
    for key in keys:
        page = next(p for p in layout['pages'] if p['key'] == key)
        K = 4
        band = np.asarray(render_synthetic(layout, page, K=K, corner_r=0 if capsule else 30,
                                           capsule_inset=INSET if capsule else None)).astype(np.float32)
        # place the screen in a 3000 x 4000 photo with keystone, rotation and blur
        scale = 3.3 / K
        cx, cy = 1500, 2000
        src = np.float32([[0, 0], [W * K, 0], [W * K, H * K], [0, H * K]])
        half = np.array([W * K * scale / 2, H * K * scale / 2])
        dst = np.float32([[cx - half[0] - 12, cy - half[1] + 9], [cx + half[0] + 10, cy - half[1] - 6],
                          [cx + half[0] + 22, cy + half[1] + 14], [cx - half[0] - 20, cy + half[1] - 3]])
        M = cv2.getPerspectiveTransform(src, dst)
        photo = cv2.warpPerspective(band, M, (3000, 4000), flags=cv2.INTER_AREA)
        photo = cv2.GaussianBlur(photo, (0, 0), 1.3)
        photo = np.clip(photo * 1.15 + rng.normal(0, 3, photo.shape) + 8, 0, 255).astype(np.uint8)
        p = os.path.join(tmp, key + '.png')
        Image.fromarray(photo).save(p)
        r = measure_photo(p, layout)
        results.append(r)
        if 'error' in r:
            print('FAIL', key, r['error'])
            ok = False
            continue
        print('%-6s page %2d  fit rms %s  ticks %d  scale %s' % (key, r['page'], r['fit']['rms_band_px'], r['fit']['ticks'], r['fit']['photo_px_per_band_px']))
        if r['page'] != page['id'] or not r['fit']['ok']:
            print('FAIL page/fit', r['page'], page['id'], r['fit']['notes'])
            ok = False
        for s in r['samples']:
            res, sp = s['result'], s['spec']
            if 'error' in res:
                print('FAIL', s['id'], res['error'])
                ok = False
            elif sp['type'] == 'rect' and sp['metric'] in ('bbox', 'ring', 'corners', 'colour_at') and res.get('verdict') != next(iter(sp['hyp'])):
                print('FAIL', s['id'], sp['metric'], 'verdict', res.get('verdict'), res.get('distances'))
                ok = False
            elif sp['type'] == 'corner' and abs(res['radius_px'] - 30) > 3:
                print('FAIL', s['id'], 'corner radius', res['radius_px'], '(want 30)')
                ok = False
            elif sp['type'] == 'comb' and (res['hidden_px'] is None or abs(res['hidden_px']) > 0.6):
                print('FAIL', s['id'], 'comb', res['hidden_px'])
                ok = False
            elif sp['type'] == 'cap':
                want_r = (W - 2 * INSET) / 2
                print('       cap %-6s radius %.2f (want %.1f) hidden end %.2f left %s right %s centre x %.2f design scale %.3f rms %.2f' % (
                    sp['end'], res['radius_px'], want_r, res['hidden_end_px'], res.get('hidden_left_px'), res.get('hidden_right_px'),
                    res['centre_x'], res['design_scale'], res['fit_rms_px']))
                if (abs(res['radius_px'] - want_r) > 1.5 or res['hidden_end_px'] > 0.8 or abs(res['centre_offset_x']) > 1.0
                        or abs((res.get('hidden_left_px') or -9) - INSET) > 0.8 or abs((res.get('hidden_right_px') or -9) - INSET) > 0.8):
                    print('FAIL', s['id'], 'capsule end')
                    ok = False
    prof = {'device': {'screen': {'w': W}}, 'font': {}}
    apply_results(prof, results)
    lb = prof['font'].get('line_box_em', {}).get('value')
    rules = prof['font'].get('regime', {})
    tall = rules.get('taller_box', {}).get('rule', {}).get('value')
    short = rules.get('shorter_box', {}).get('rule', {}).get('value')
    wide = rules.get('taller_box_text_too_wide', {}).get('rule', {}).get('value')
    clipped = rules.get('shorter_box', {}).get('clipped', {}).get('value')
    adv0 = prof['font'].get('advance_em', {}).get('0', {}).get('value')
    f = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf', 1000)
    true0 = f.getlength('0') / 1000
    print('line box %.4f (want 1.30), taller %s (want centre), shorter %s (want top), too wide %s (want top), clipped %s, advance "0" %s (want %.3f)' % (
        lb or -1, tall, short, wide, clipped, adv0, true0))
    ok = ok and lb and abs(lb - 1.30) < 0.01 and tall == 'centre' and short == 'top' and wide == 'top' and clipped
    ok = ok and adv0 and abs(adv0 - true0) < 0.01
    if capsule:
        sc = prof['device'].get('design_scale', {})
        er = prof.get('screen', {}).get('end_radius_px', {}).get('value')
        hid = {k: v.get('value') for k, v in prof.get('screen', {}).get('hidden_px', {}).items()}
        dw = prof['device'].get('design_width', {}).get('value')
        print('capsule: end radius %s, hidden %s, design scale %s (1:1 %s), design_width %s' % (er, hid, sc.get('value'), sc.get('one_to_one'), dw))
        ok = ok and sc.get('one_to_one') is True and dw == W and er and all(abs(v - (W - 2 * INSET) / 2) < 1.5 for v in er.values())
        ok = ok and abs(hid.get('left', -9) - INSET) < 0.8 and abs(hid.get('right', -9) - INSET) < 0.8 and hid.get('top', 9) < 0.8 and hid.get('bottom', 9) < 0.8
    print('%s: %s' % (dev, 'PASS' if ok else 'FAIL'))
    return bool(ok)


# ---------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run', help='measure photos and update the profile')
    r.add_argument('photos', nargs='+')
    r.add_argument('--device', default='band10pro', help='band model: <workspace>/devices/<device>/profile.json')
    r.add_argument('--workspace', default=None, help='workspace root (default: $MIBAND_WORKSPACE, else the nearest folder with devices/)')
    r.add_argument('--profile', default=None, help='explicit profile path (overrides --device)')
    r.add_argument('--layout', default=None, help='default: layouts/<profile device id>.json')
    r.add_argument('--page', type=int, default=None, help='page id, when the barcode is missing (legacy photos)')
    r.add_argument('--out', default=None, help='annotated images, not committed (default <workspace>/devices/<device>/results)')
    r.add_argument('--evidence', default=None, help='per-photo result JSON, committed (default <workspace>/devices/<device>/evidence)')
    r.add_argument('--dry-run', action='store_true', help="measure and print, don't touch the profile")
    s_ = sub.add_parser('set', help='record an observation (e.g. from the animation page)')
    s_.add_argument('path')
    s_.add_argument('value', help='JSON value (true, 1.5, "centre", {...}); bare words are strings')
    s_.add_argument('--source', required=True)
    s_.add_argument('--status', default='measured', choices=['measured', 'assumed', 'unknown'])
    s_.add_argument('--device', default='band10pro')
    s_.add_argument('--profile', default=None)
    s_.add_argument('--workspace', default=None)
    sh = sub.add_parser('show', help='print every fact with its status')
    sh.add_argument('--device', default='band10pro')
    sh.add_argument('--profile', default=None)
    sh.add_argument('--workspace', default=None)
    st = sub.add_parser('selftest')
    st.add_argument('--device', action='append', default=None, help='layout(s) to test (default: band10pro and band11)')
    a = ap.parse_args(argv)

    if a.cmd == 'selftest':
        return selftest(tuple(a.device) if a.device else ('band10pro', 'band11'))
    if a.cmd == 'set':
        ppath = profile_arg(a, write=True)
        prof, nested = flat_view(load_json(ppath))
        try:
            v = json.loads(a.value)
        except ValueError:
            v = a.value
        path = a.path[len('quickapp.'):] if a.path.startswith('quickapp.') else a.path
        set_fact(prof, path, v, a.source, status=a.status)
        save_json(ppath, nest_view(prof, nested))
        print('set', a.path, '=', json.dumps(v), '(%s)' % a.status)
        return 0
    if a.cmd == 'show':
        prof = load_json(profile_arg(a))

        def walk(d, pre):
            for k, v in d.items():
                p = pre + '.' + k if pre else k
                if isinstance(v, dict) and 'status' in v and 'value' in v:
                    val = json.dumps(v['value'])
                    print('%-9s %-48s %s' % (v['status'], p, val if len(val) < 70 else val[:67] + '...'))
                elif isinstance(v, dict):
                    walk(v, p)
        walk(prof, '')
        return 0
    ppath = profile_arg(a, write=not a.dry_run)
    if not os.path.exists(ppath):
        print('no profile for %s at %s: seed one first (seed-profile.mjs)' % (a.device, ppath))
        return 1
    prof, nested = flat_view(load_json(ppath))
    dev = prof['device']['id']
    lpath = a.layout or os.path.join(HERE, 'layouts', dev + '.json')
    layout = load_json(lpath)
    evidence = a.evidence or os.path.join(ws.devices_dir(a.workspace), dev, 'evidence')
    if a.out is None:
        a.out = os.path.join(ws.devices_dir(a.workspace), dev, 'results')
    results = []
    for ph in a.photos:
        res = measure_photo(ph, layout, page_id=a.page, annotate_dir=a.out)
        res['layout'] = os.path.basename(lpath)
        res['measured_at'] = datetime.datetime.now().isoformat(timespec='seconds')
        results.append(res)
        if 'error' in res:
            print('%s: ERROR %s' % (res['photo'], res['error']))
            continue
        fi = res['fit']
        print('%s: page %d (%s), rulers rms %.2f/%.2f band px, %d ticks, %.2f photo px per band px%s' % (
            res['photo'], res['page'], res['page_key'], fi['rms_band_px'][0], fi['rms_band_px'][1], fi['ticks'],
            min(fi['photo_px_per_band_px']), '' if fi['ok'] else '  NOT USED: ' + '; '.join(fi['notes'])))
        if not a.dry_run:
            os.makedirs(evidence, exist_ok=True)
            save_json(os.path.join(evidence, os.path.splitext(res['photo'])[0] + '.json'), res)
        for s in res['samples']:
            rr = s['result']
            brief = {k: rr[k] for k in rr if k in ('verdict', 'content_h', 'ink_top', 'ink_bottom', 'clipped_bottom', 'content_w', 'lines', 'align', 'ellipsis', 'radius_px', 'hidden_px', 'luma', 'error', 'ratio')}
            print('   %-12s %-8s %s' % (s['id'], s['type'], json.dumps({k: (round(v, 2) if isinstance(v, float) else v) for k, v in brief.items()})))
    if a.dry_run:
        return 0
    # The profile is rebuilt from ALL evidence for this device (earlier sessions too); for each page
    # of each layout only the newest photo counts, so a retake replaces the old one.
    newest = {}
    for fn in sorted(os.listdir(evidence)):
        if fn.endswith('.json'):
            r = load_json(os.path.join(evidence, fn))
            if 'samples' not in r:
                continue
            # kit versions are kept apart (2.0.0's pages differ from 1.0.0's); within one, a retake wins
            k = (r.get('layout'), r.get('kit'), r.get('page_key'))
            if k not in newest or r.get('measured_at', '') > newest[k].get('measured_at', ''):
                newest[k] = r
    written = apply_results(prof, list(newest.values()))
    prof['updated'] = datetime.date.today().isoformat()
    save_json(ppath, nest_view(prof, nested))
    print('profile %s: %d facts written' % (ppath, len(written)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
