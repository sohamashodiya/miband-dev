#!/usr/bin/env python3
"""Face calibration kit: generate the calibration watch faces and the layout measure_face.py reads.

    python3 gen.py [<device id> ...|all] [--spec PATH] [--out DIR]     (default all)

A device is its spec, devices/<id>/device.json (tools/vela-calib/device-spec.mjs): the face canvas,
shape, face id digit and builder. "all" = every device that already has layouts/<id>.json here
(onboarded with tools/vela-calib/new-device.mjs). --spec builds from a spec file (the selftests'
synthetic devices); --out writes faces/ and layouts/ under DIR instead of this folder.

Writes, per model:
  faces/<model>/f<N>-<key>/   one band10-toolkit face project per page (manifest.json, layout.json,
                              assets/*.png, optional script/ with main.lua and its images,
                              preview.png, calib.json)
  layouts/<model>.json        every page, its barcode, where every sample is, what Lua draws

A face can't take taps, so each "page" is its own face with its own manifest id. Every page has the
same frame as the quick-app kit (tools/vela-calib): rulers down both edges (a 1 px tick every 10 px,
14 px every 50, 22 px and yellow every 100; tick top = y), a yellow scale bar of known length and an
8-cell page barcode (on, 5 bits of the page number, parity, on). On the Band 10/11 capsule the bar,
barcode and content stay on the straight part of the screen (y 106-414), clear of the semicircular
ends. On a circle the rulers are two straight columns inside it (layout frame.ruler), like the
quick-app kit's. All pixels are drawn at 1x with no anti-aliasing, so the page images are exact.

Frames: band11 and band10pro use the frame pinned in their spec (calib.face.frame: build 1 was
photographed with it). Any other device gets one computed here: the 164 x 330 px content block
centred between the rulers and as high as the outline allows (y >= 44), the barcode and a 150 px bar
under it. The content block needs 164 px between the rulers (screens >= 212 px wide; a circle
>= 342 px); a narrower screen is refused.

Everything here is generated: edit this file, never the faces/ output. Bump KIT_BUILD whenever a
page changes (every face id contains it; a reinstalled id is silently ignored by the band).
"""
import json
import math
import os
import shutil
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = HERE  # where faces/ and layouts/ go (--out)
KIT_BUILD = 1
FONT = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
sys.path.insert(0, os.path.join(HERE, '..', 'vela-calib'))
sys.dont_write_bytecode = True
import device_spec as ds  # noqa: E402

BLOCK_W, BLOCK_TOP, BLOCK_BOTTOM = 164, -2, 328   # content block: x ox-2 .. ox+162, y oy-2 .. oy+328
CODE_DY, BAR_DY = 340, 356                         # barcode and bar rows below oy (as on the Band 11)


def model(spec):
    """The kit's model dict for a device spec: canvas, shape ('rrect' | 'capsule' | 'circle'), radius,
    face id digit, builder, and the frame (pinned in the spec, or computed)."""
    f = spec.get('face') or {}
    if not f:
        raise SystemExit('%s: the spec has no face section' % spec['id'])
    if f.get('id_digit') is None:
        raise SystemExit('%s: face.id_digit not assigned yet (onboard the device: node tools/vela-calib/new-device.mjs %s)' % (spec['id'], spec['id']))
    g = ds.geometry(spec)
    W, H = f['canvas']['w'], f['canvas']['h']
    if (W, H) != (g['w'], g['h']):
        raise SystemExit('%s: face canvas %dx%d differs from the screen %dx%d (not supported)' % (spec['id'], W, H, g['w'], g['h']))
    shape = {'rect': 'rrect', 'capsule': 'capsule', 'circle': 'circle'}[g['shape']]
    r = g.get('corner_r', g.get('end_r', g.get('radius')))
    M = dict(name=spec['name'], W=W, H=H, shape=shape, r=r, mdigit=f['id_digit'], builder=f['builder'],
             status=f.get('status', 'experimental'), geom=g, ruler=dict(left_x=0, right_x=W, y0=0, n=(H - 1) // TICK_EVERY + 1))
    pin = ((spec.get('calib') or {}).get('face') or {}).get('frame')
    if pin:
        M.update({k: pin[k] for k in ('ox', 'oy', 'bar', 'code', 'straight', 'r') if k in pin})
        return M
    if shape == 'circle':
        lx = round(W / 2 - 0.62 * r)
        rows = [y for y in range(0, H, TICK_EVERY) if all(ds.inside(g, x, yy, 4) for x in (lx, W - lx) for yy in (y, y + 1))]
        M['ruler'] = dict(left_x=lx, right_x=W - lx, y0=rows[0], n=len(rows))
        M['straight'] = None
    else:
        lo = r + 4 if shape == 'capsule' else r + 5
        M['straight'] = [int(math.ceil(lo / 10.0)) * 10, int((H - lo) // 10) * 10]
    ru = M['ruler']
    x0, x1 = ru['left_x'] + 24, ru['right_x'] - 24
    if x1 - x0 < BLOCK_W:
        raise SystemExit('%s: %d px between the rulers; the face pages need %d (a compact page set for narrow screens is not written yet)'
                         % (spec['id'], x1 - x0, BLOCK_W))
    ox = max(x0 + 2, int(round(W / 2 - BLOCK_W / 2 + 2)))
    cx = int(round(W / 2))
    for oy in range(44, H // 2, 2):
        code = dict(x=cx - 75, y=oy + CODE_DY, cell=6, pitch=8, h=10)
        bar = dict(x=cx - 75, y=oy + BAR_DY, len=150, h=4)
        parts = [(ox - 2, oy + BLOCK_TOP, BLOCK_W, BLOCK_BOTTOM - BLOCK_TOP), (code['x'] - 2, code['y'] - 2, 7 * 8 + 6 + 4, 14),
                 (bar['x'], bar['y'] - 2, bar['len'], 8)]
        if all(ds.rect_inside(g, *p, m=4) for p in parts):
            M.update(ox=ox, oy=oy, code=code, bar=bar)
            return M
    raise SystemExit('%s: the face pages (content block, barcode, bar) do not fit a %dx%d %s' % (spec['id'], W, H, shape))


def onboarded():
    """Devices with a face-kit layout here (and a spec)."""
    have = set(ds.list_ids())
    d = os.path.join(HERE, 'layouts')
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith('.json') and f[:-5] in have) if os.path.isdir(d) else []

C = {
    'white': (255, 255, 255), 'yellow': (255, 214, 10), 'pink': (255, 45, 149), 'cyan': (0, 229, 255),
    'green': (60, 255, 60), 'grey': (154, 154, 154), 'bits': (200, 200, 200), 'black': (0, 0, 0),
    'red': (255, 0, 0), 'blue': (0, 0, 255), 'pure_green': (0, 255, 0), 'fill': (192, 192, 192),
}
TICK_EVERY = 10
TICK_LEN = [8, 14, 22]

# Digit / frame cells: a 1 px pink outline, a white glyph, and the value in 4 grey squares (a 2 x 2
# grid of 4 x 4 px squares, 2 px apart), so measure_face.py can count cells and read values.
CELL_W, CELL_H = 16, 32
BITS_AT = (3, 19)           # bit block origin inside a digit cell
FRAME_W, FRAME_H = 64, 32
FRAME_BITS_AT = (46, 13)    # bit block origin inside an image-list frame
BIT_SQ, BIT_GAP = 4, 2
MINUS_CODE = 15
TILE = 32                   # image-format test tiles

def font(px):
    return ImageFont.truetype(FONT, px)


# ---------------------------------------------------------------------------------------------
# drawing helpers (band px, 1x, no anti-aliasing)
# ---------------------------------------------------------------------------------------------
class Canvas:
    def __init__(self, w, h, bg=(0, 0, 0, 255)):
        self.im = Image.new('RGBA', (w, h), bg)
        self.dr = ImageDraw.Draw(self.im)
        self.dr.fontmode = '1'

    def rect(self, x, y, w, h, c, a=255):
        if w <= 0 or h <= 0:
            return
        self.dr.rectangle((x, y, x + w - 1, y + h - 1), fill=tuple(c) + (a,))

    def outline(self, x, y, w, h, c):
        self.dr.rectangle((x, y, x + w - 1, y + h - 1), outline=tuple(c) + (255,), width=1)

    def text(self, x, y, s, px, c=C['grey'], anchor='la'):
        self.dr.text((x, y), s, font=font(px), fill=tuple(c) + (255,), anchor=anchor)

    def save(self, path, mode='RGBA'):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        (self.im if mode == 'RGBA' else self.im.convert(mode)).save(path)


def bits_of(v):
    return [(v >> 3) & 1, (v >> 2) & 1, (v >> 1) & 1, v & 1]


def bit_squares(bx, by):
    """Top-left corners of the 4 bit squares (bit 3, 2, 1, 0) relative to a cell."""
    p = BIT_SQ + BIT_GAP
    return [(bx, by), (bx + p, by), (bx, by + p), (bx + p, by + p)]


def draw_bits(cv, x, y, v, at):
    for (sx, sy), b in zip(bit_squares(*at), bits_of(v)):
        if b:
            cv.rect(x + sx, y + sy, BIT_SQ, BIT_SQ, C['bits'])


def digit_cell(ch, code):
    cv = Canvas(CELL_W, CELL_H)
    cv.outline(0, 0, CELL_W, CELL_H, C['pink'])
    cv.text(CELL_W // 2, 10, ch, 14, C['white'], anchor='mm')
    draw_bits(cv, 0, 0, code, BITS_AT)
    return cv


def unit_cell():
    cv = Canvas(12, CELL_H)
    cv.outline(0, 0, 12, CELL_H, C['green'])
    cv.text(6, 10, '%', 10, C['white'], anchor='mm')
    return cv


def frame_cell(label, index):
    cv = Canvas(FRAME_W, FRAME_H)
    cv.outline(0, 0, FRAME_W, FRAME_H, C['pink'])
    cv.text(4, FRAME_H // 2, label, 13, C['white'], anchor='lm')
    draw_bits(cv, 0, 0, index, FRAME_BITS_AT)
    return cv


def target_tile():
    """32 x 32 placement target: pink outline, white centre cross."""
    cv = Canvas(TILE, TILE)
    cv.outline(0, 0, TILE, TILE, C['pink'])
    cv.rect(TILE // 2, 4, 1, TILE - 8, C['white'])
    cv.rect(4, TILE // 2, TILE - 8, 1, C['white'])
    return cv


def tile_rgba(noise=False):
    """Image-format tile: quadrants white | red / green | blue and an 8 x 8 hole (alpha 0, RGB cyan)."""
    a = np.zeros((TILE, TILE, 4), np.uint8)
    h = TILE // 2
    a[:h, :h, :3] = C['white']
    a[:h, h:, :3] = C['red']
    a[h:, :h, :3] = C['pure_green']
    a[h:, h:, :3] = C['blue']
    a[..., 3] = 255
    if noise:  # > 256 distinct colours so the toolkit packs it as BGRA32 instead of a 256-colour palette
        yy, xx = np.mgrid[0:TILE, 0:TILE]
        k = yy * TILE + xx
        d = np.stack([k % 6, (k // 6) % 6, (k // 36) % 6], -1).astype(np.int16)
        base = a[..., :3].astype(np.int16)
        a[..., :3] = np.where(base > 127, base - d, base + d).clip(0, 255).astype(np.uint8)
    a[12:20, 12:20] = (0, 229, 255, 0)
    return a


def n_colours(im):
    a = np.asarray(im.convert('RGBA')).reshape(-1, 4)
    return len(np.unique(a.view(np.uint32)))


# ---------------------------------------------------------------------------------------------
# LVGL raw image files (the Lua layer's other image format; known to render garbled on Band 11)
# ---------------------------------------------------------------------------------------------
def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def lvgl_bins(a):
    """dict name -> bytes: LVGL v8 and v9 image files of the RGBA tile a."""
    h, w = a.shape[:2]
    px = a.reshape(-1, 4)
    out = {}
    # v8: u32 header cf:5 always_zero:3 reserved:2 w:11 h:11; CF_TRUE_COLOR_ALPHA = 5
    hdr8 = struct.pack('<I', 5 | (w << 10) | (h << 21))
    out['v8_tca32'] = hdr8 + b''.join(struct.pack('BBBB', p[2], p[1], p[0], p[3]) for p in px)          # LV_COLOR_DEPTH 32
    out['v8_tca16'] = hdr8 + b''.join(struct.pack('<HB', rgb565(p[0], p[1], p[2]), p[3]) for p in px)  # LV_COLOR_DEPTH 16
    # v9: magic 0x19, cf, flags u16, w u16, h u16, stride u16, reserved u16
    out['v9_argb8888'] = struct.pack('<BBHHHHH', 0x19, 0x10, 0, w, h, w * 4, 0) + b''.join(struct.pack('BBBB', p[2], p[1], p[0], p[3]) for p in px)
    out['v9_rgb565'] = struct.pack('<BBHHHHH', 0x19, 0x12, 0, w, h, w * 2, 0) + b''.join(struct.pack('<H', rgb565(p[0], p[1], p[2])) for p in px)
    return out


# ---------------------------------------------------------------------------------------------
# a page = one face project
# ---------------------------------------------------------------------------------------------
class Page:
    def __init__(self, kit, pid, face, key, title, theme='normal', bar=None, code=None):
        self.kit = kit
        self.id = pid
        self.face = face
        self.key = key
        self.title = title
        self.theme = theme
        self.bar = bar or kit.M['bar']
        self.code = code or kit.M['code']
        self.samples = []
        self.lua_ops = []
        self.observe = []
        self.notes = []

    def sample(self, s):
        s['id'] = s.get('id') or '%s.%d' % (self.key, len(self.samples))
        self.samples.append(s)
        return s

    def spec(self):
        return {'id': self.id, 'face': self.face, 'key': self.key, 'title': self.title, 'theme': self.theme,
                'bar': self.bar, 'code': self.code, 'samples': self.samples, 'lua_ops': self.lua_ops,
                'observe': self.observe, 'notes': self.notes}


class Face:
    """One toolkit project: normal page (+ optional AOD page), assets, widgets, Lua ops."""

    def __init__(self, kit, n, slug, title):
        self.kit = kit
        self.n = n
        self.slug = slug
        self.title = title
        self.dir = os.path.join(OUT, 'faces', kit.model, 'f%d-%s' % (n, slug))
        self.assets = {}      # rel path -> PIL image
        self.script_files = {}  # name -> bytes or PIL image
        self.widgets = {'normal': [], 'aod': []}
        self.digitsets = {}
        self.pages = {}
        self.lua = []          # Lua ops (drawn on the normal face; and on AOD when aod_script)
        self.aod_script = False

    @property
    def id(self):
        return '8%d%05d%02d' % (self.kit.M['mdigit'], KIT_BUILD, self.n)

    @property
    def name(self):
        return 'Calib F%d %s b%d' % (self.n, self.title, KIT_BUILD)

    @property
    def output(self):
        return 'calib-%s-f%d-%s' % (self.kit.model, self.n, self.slug)

    def asset(self, rel, img):
        self.assets[rel] = img.im if isinstance(img, Canvas) else img
        return rel

    def widget(self, theme, w):
        w.setdefault('z', len(self.widgets[theme]))
        w.setdefault('allowOverlap', True)
        self.widgets[theme].append(w)
        return w

    def image(self, theme, rel, img, x, y, wid=None):
        self.asset(rel, img)
        return self.widget(theme, {'id': wid or rel.split('/')[-1].split('.')[0] + '-' + str(len(self.widgets[theme])),
                                   'type': 'image', 'asset': rel, 'x': x, 'y': y})

    def digit_set(self, name='cell'):
        if name not in self.digitsets:
            ds = {'digits': [], 'minus': 'assets/digits/minus.png'}
            for d in range(10):
                ds['digits'].append(self.asset('assets/digits/%d.png' % d, digit_cell(str(d), d)))
            self.asset('assets/digits/minus.png', digit_cell('-', MINUS_CODE))
            self.digitsets[name] = ds
        return name

    def number(self, theme, source, x, y, count, align='left', spacing=0, lz=False, unit=False, wid=None):
        w = {'id': wid or '%s-%s-%d' % (source, align, len(self.widgets[theme])), 'type': 'number', 'source': source,
             'digitSet': self.digit_set(), 'digits': count, 'align': align, 'spacing': spacing, 'leadingZero': lz,
             'x': x, 'y': y}
        if unit:
            w['unitAsset'] = self.asset('assets/unit.png', unit_cell())
        return self.widget(theme, w)

    def image_list(self, theme, source, x, y, values, labels, wid):
        items = []
        for i, (v, lab) in enumerate(zip(values, labels)):
            rel = self.asset('assets/%s/%d.png' % (wid, i), frame_cell(lab, i))
            items.append({'value': v, 'asset': rel})
        return self.widget(theme, {'id': wid, 'type': 'image-list', 'source': source, 'fallback': 'floor', 'x': x, 'y': y, 'items': items})

    def script(self, name, data):
        self.script_files[name] = data
        return name

    # ---- write -------------------------------------------------------------------------------
    def write(self):
        if os.path.isdir(self.dir):
            for sub in ('assets', 'script'):
                shutil.rmtree(os.path.join(self.dir, sub), ignore_errors=True)
        os.makedirs(self.dir, exist_ok=True)
        for rel, im in self.assets.items():
            p = os.path.join(self.dir, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            im.save(p)
        M = self.kit.M
        layout = {
            '$schema': '../../../../../vendor/band10-toolkit/schemas/layout.schema.json',
            'formatVersion': 1,
            'canvas': {'width': M['W'], 'height': M['H'], 'clip': 'pill' if M['shape'] == 'capsule' else 'rectangle'},
            'assets': {'digitSets': self.digitsets},
            'normal': {'background': '#000000', 'widgets': self.widgets['normal']},
        }
        if self.widgets['aod']:
            layout['aod'] = {'enabled': True, 'background': '#000000', 'widgets': self.widgets['aod']}
        manifest = {
            '$schema': '../../../../../vendor/band10-toolkit/schemas/manifest.schema.json',
            'formatVersion': 1, 'id': self.id, 'name': self.name, 'author': 'miband-dev',
            'version': '1.0.%d' % KIT_BUILD,
            'description': 'Face calibration kit (tools/face-calib), %s, page(s) %s. Test patterns only; delete after photographing.'
                           % (M['name'], ', '.join(str(p.id) for p in self.pages.values())),
            'license': 'Personal use.', 'device': 'xiaomi-smart-band-10', 'preview': 'generated',
            'output': self.output, 'compiler': {'target': 'native', 'imageCompression': True},
        }
        dump(os.path.join(self.dir, 'layout.json'), layout)
        dump(os.path.join(self.dir, 'manifest.json'), manifest)
        dump(os.path.join(self.dir, 'calib.json'), {
            'generated_by': 'tools/face-calib/gen.py', 'model': self.kit.model, 'kit_build': KIT_BUILD,
            'pages': {t: p.id for t, p in self.pages.items()}, 'aodScript': self.aod_script,
            'packer': 'pack.mts' if (self.kit.M['builder'] != 'band10-toolkit' or self.aod_script) else 'toolkit-cli'})
        if self.lua:
            sd = os.path.join(self.dir, 'script')
            os.makedirs(sd, exist_ok=True)
            for name, data in self.script_files.items():
                p = os.path.join(sd, name)
                if isinstance(data, (bytes, bytearray)):
                    with open(p, 'wb') as f:
                        f.write(data)
                else:
                    (data.im if isinstance(data, Canvas) else data).save(p)
            with open(os.path.join(sd, 'main.lua'), 'w') as f:
                f.write(lua_source(self))
        # preview (used by pack.mts; the toolkit CLI renders its own)
        prev = self.assets[self.widgets['normal'][0]['asset']].copy()
        prev.save(os.path.join(self.dir, 'preview.png'))


def dump(path, obj):
    with open(path, 'w') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write('\n')


# ---------------------------------------------------------------------------------------------
# Lua source from the op list
# ---------------------------------------------------------------------------------------------
LUA_HEAD = '''-- Generated by tools/face-calib/gen.py ({name}, kit build {build}). Don't edit.
-- Every test runs in pcall and then draws a status square: green = the call returned, pink = it
-- raised an error. A test that returns can still draw nothing or draw garbage: the photo decides.
local lvgl = require("lvgl")
local DIR = SCRIPT_PATH or "/"
local root = lvgl.Object(nil, {{ w = lvgl.HOR_RES(), h = lvgl.VER_RES(), bg_opa = lvgl.OPA(0), border_width = 0, pad_all = 0 }})
root:clear_flag(lvgl.FLAG.SCROLLABLE)
root:clear_flag(lvgl.FLAG.CLICKABLE)
local function img(src, x, y)
  local o = root:Image {{ src = DIR .. src }}
  o:set {{ x = x, y = y }}
  return o
end
local function status(x, y, ok)
  img(ok and "st_ok.png" or "st_err.png", x, y)
end
local function try(x, y, fn)
  local ok = pcall(fn)
  status(x, y, ok)
  return ok
end
-- n digit cells from x (pitch {cw}), leading zeros; returns a setter and the first cell
local function counter(n, x, y)
  local cells = {{}}
  for i = 0, n - 1 do cells[i] = img("dg0.png", x + i * {cw}, y) end
  local function set(v)
    v = v // 1
    for i = n - 1, 0, -1 do
      cells[i]:set {{ src = DIR .. "dg" .. (v % 10) .. ".png" }}
      v = v // 10
    end
  end
  return set, cells
end
'''


def lua_source(face):
    out = [LUA_HEAD.format(name=face.name, build=KIT_BUILD, cw=CELL_W)]
    for op in face.lua:
        k = op['kind']
        sx, sy = op.get('status', (0, 0))
        if k == 'alive':
            out.append('status(%d, %d, true)  -- %s' % (op['x'], op['y'], op['test']))
        elif k == 'image':
            z = ''
            if op.get('zoom'):
                z = '; o:set { %s = %d }' % (op['zoom'], 512)
            out.append('try(%d, %d, function() local o = img("%s", %d, %d)%s end)  -- %s' % (sx, sy, op['file'], op['x'], op['y'], z, op['test']))
        elif k == 'fills':
            body = '\n'.join('  root:Object { x = %d, y = %d, w = %d, h = %d, bg_color = "%s", bg_opa = lvgl.OPA(100), border_width = 0, radius = 0, pad_all = 0 }'
                             % (f['x'], f['y'], f['w'], f['h'], f['hex']) for f in op['fills'])
            out.append('try(%d, %d, function()  -- %s\n%s\nend)' % (sx, sy, op['test'], body))
        elif k == 'label':
            out.append('try(%d, %d, function() root:Label { text = "%s", x = %d, y = %d, text_color = "#ffffff" } end)  -- %s'
                       % (sx, sy, op['text'], op['x'], op['y'], op['test']))
        elif k == 'timer':
            out.append('''try(%d, %d, function()  -- %s: the square blinks once a second if Lua timers run
  local sq = img("st_ok.png", %d, %d)
  local on = true
  lvgl.Timer { period = 1000, cb = function(t)
    on = not on
    if on then sq:clear_flag(lvgl.FLAG.HIDDEN) else sq:add_flag(lvgl.FLAG.HIDDEN) end
  end }
end)''' % (sx, sy, op['test'], op['x'], op['y']))
        elif k == 'digits':
            w = op['what']
            if w in ('hor_res', 'ver_res'):
                out.append('try(%d, %d, function() local set = counter(%d, %d, %d); set(lvgl.%s()) end)  -- %s'
                           % (sx, sy, op['n'], op['x'], op['y'], 'HOR_RES' if w == 'hor_res' else 'VER_RES', op['test']))
            elif w == 'hour':
                out.append('''try(%d, %d, function()  -- %s
  local dataman = require("dataman")
  local set, cells = counter(%d, %d, %d)
  local t = { hh = 0, hl = 0 }
  dataman.subscribe("timeHourHigh", cells[0], function(_, v) t.hh = v // 256; set(t.hh * 10 + t.hl) end)
  dataman.subscribe("timeHourLow", cells[1], function(_, v) t.hl = v // 256; set(t.hh * 10 + t.hl) end)
end)''' % (sx, sy, op['test'], op['n'], op['x'], op['y']))
            elif w == 'minute':
                out.append('''try(%d, %d, function()  -- %s
  local dataman = require("dataman")
  local set, cells = counter(%d, %d, %d)
  local t = { mh = 0, ml = 0 }
  dataman.subscribe("timeMinuteHigh", cells[0], function(_, v) t.mh = v // 256; set(t.mh * 10 + t.ml) end)
  dataman.subscribe("timeMinuteLow", cells[1], function(_, v) t.ml = v // 256; set(t.mh * 10 + t.ml) end)
end)''' % (sx, sy, op['test'], op['n'], op['x'], op['y']))
            elif w == 'raw_minute_low':
                out.append('''try(%d, %d, function()  -- %s: the raw dataman value (no // 256)
  local dataman = require("dataman")
  local set, cells = counter(%d, %d, %d)
  dataman.subscribe("timeMinuteLow", cells[%d], function(_, v) set(v) end)
end)''' % (sx, sy, op['test'], op['n'], op['x'], op['y'], op['n'] - 1))
        else:
            raise ValueError(k)
    return '\n'.join(out) + '\n'


# ---------------------------------------------------------------------------------------------
# the kit for one model
# ---------------------------------------------------------------------------------------------
class Kit:
    def __init__(self, spec):
        self.model = spec['id']
        self.M = model(spec)
        self.faces = []
        self.pages = []
        ru = self.M['ruler']
        ks = [(ru['y0'] + i * TICK_EVERY) // TICK_EVERY for i in range(ru['n'])]
        self.ticks = [2 if k % 10 == 0 else 1 if k % 5 == 0 else 0 for k in ks]

    def face(self, n, slug, title):
        f = Face(self, n, slug, title)
        self.faces.append(f)
        return f

    def page(self, face, pid, key, title, theme='normal', **kw):
        p = Page(self, pid, face.n, key, title, theme, **kw)
        face.pages[theme] = p
        self.pages.append(p)
        return p

    def frame(self, cv, p, label_at=None, label=True):
        """Rulers, bar, barcode and the page label, drawn into the page's background canvas."""
        M = self.M
        ru = M['ruler']
        for i, t in enumerate(self.ticks):
            ln = TICK_LEN[t]
            c = C['yellow'] if t == 2 else C['white']
            cv.rect(ru['left_x'], ru['y0'] + i * TICK_EVERY, ln, 1, c)
            cv.rect(ru['right_x'] - ln, ru['y0'] + i * TICK_EVERY, ln, 1, c)
        b = p.bar
        cv.rect(b['x'], b['y'], b['len'], b['h'], C['yellow'])
        cd = p.code
        bits = [1] + [(p.id >> k) & 1 for k in range(4, -1, -1)]
        bits += [sum(bits[1:]) % 2, 1]
        for i, on in enumerate(bits):
            if on:
                cv.rect(cd['x'] + i * cd['pitch'], cd['y'], cd['cell'], cd['h'], C['white'])
        if label:
            x, y = label_at or (M['ox'], M['oy'])
            cv.text(x, y, 'F%d %s  p%d b%d' % (p.face, p.title, p.id, KIT_BUILD), 12)

    def overlay_sample(self, p):
        """The top strip is left black on every page: anything lit there is drawn by the system."""
        M = self.M
        p.sample({'type': 'overlay', 'region': [24, 0, M['W'] - 24, M['oy'] - 6]})

    def bg(self):
        return Canvas(self.M['W'], self.M['H'])

    # ---- pages ---------------------------------------------------------------------------------
    def build(self):
        M = self.M
        W, H, ox, oy = M['W'], M['H'], M['ox'], M['oy']
        y0 = oy + 20
        status_img = {'st_ok.png': Canvas(6, 6), 'st_err.png': Canvas(6, 6)}
        status_img['st_ok.png'].rect(0, 0, 6, 6, C['green'])
        status_img['st_err.png'].rect(0, 0, 6, 6, C['pink'])

        def lua_common(face):
            for k, v in status_img.items():
                face.script(k, v)

        # ---------------- F1 geometry ----------------
        f = self.face(1, 'geometry', 'Geometry')
        if M['shape'] == 'capsule':
            # end radius R = W / 2 (Band 11: 106): grey fills over rows 30 .. R - 14 of each end
            R = int(W // 2)
            cxm = W // 2
            p = self.page(f, 1, 'geo', 'Geometry')
            cv = self.bg()
            self.frame(cv, p, label_at=(40, R + 44))
            xs = [cxm - 16, cxm - 8, cxm, cxm + 8, cxm + 16]
            for x in xs:
                cv.rect(x, 0, 1, 24, C['white'])
                cv.rect(x, H - 24, 1, 24, C['white'])
            cv.rect(0, 30, W, R - 43, C['fill'])            # rows 30 .. R - 14
            cv.rect(0, H - (R - 14), W, R - 43, C['fill'])  # rows H - R + 14 .. H - 30
            cv.text(W // 2, R + 94, 'Capsule ends', 13, C['grey'], anchor='mm')
            cv.text(W // 2, R + 114, 'and edges', 13, C['grey'], anchor='mm')
            cv.text(W // 2, R + 144, 'Note anything the', 11, C['grey'], anchor='mm')
            cv.text(W // 2, R + 159, 'system draws on top', 11, C['grey'], anchor='mm')
            p.sample({'type': 'comb', 'edge': 'top', 'xs': xs, 'y0': 0, 'y1': 24, 'centre_x': cxm})
            p.sample({'type': 'comb', 'edge': 'bottom', 'xs': xs, 'y0': H - 24, 'y1': H, 'centre_x': cxm})
            p.sample({'type': 'capsule_end', 'end': 'top', 'rows': [32, R - 16], 'expect': {'cx': cxm, 'cy': R, 'r': R}})
            p.sample({'type': 'capsule_end', 'end': 'bottom', 'rows': [H - (R - 16), H - 32], 'expect': {'cx': cxm, 'cy': H - R, 'r': R}})
        elif M['shape'] == 'circle':
            # grey fills over everything outside the rulers; their lit outline is the whole circle
            ru = M['ruler']
            yT = ru['y0'] - 8
            yB = ru['y0'] + (ru['n'] - 1) * TICK_EVERY + 1 + 8
            boxes = [[0, 0, W, yT], [0, yB, W, H - yB], [0, yT, ru['left_x'] - 6, yB - yT], [ru['right_x'] + 6, yT, W - ru['right_x'] - 6, yB - yT]]
            gbar = {'x': (W - M['bar']['len']) // 2, 'y': H // 2 - 2, 'len': M['bar']['len'], 'h': 4}
            gcode = dict(M['code'], x=gbar['x'], y=gbar['y'] + 14)
            p = self.page(f, 1, 'geo', 'Geometry', bar=gbar, code=gcode)
            cv = self.bg()
            self.frame(cv, p, label_at=(ru['left_x'] + 30, yT + 12))
            for x, y, w, h in boxes:
                cv.rect(x, y, w, h, C['fill'])
            cv.text(W // 2, gbar['y'] - 60, 'Round edge. Note anything', 13, C['grey'], anchor='mm')
            cv.text(W // 2, gbar['y'] - 42, 'the system draws on top.', 13, C['grey'], anchor='mm')
            p.sample({'type': 'round', 'boxes': boxes, 'expect': {'cx': W / 2, 'cy': H / 2, 'r': W / 2}})
        else:
            K = 48 if M['r'] <= 48 else int(math.ceil(1.2 * M['r']))
            gbar = {'x': (W - M['bar']['len']) // 2, 'y': H // 2 - 2, 'len': M['bar']['len'], 'h': 4}
            gcode = dict(M['code'], x=gbar['x'], y=gbar['y'] + 14)
            p = self.page(f, 1, 'geo', 'Geometry', bar=gbar, code=gcode)
            cv = self.bg()
            self.frame(cv, p, label_at=(K + 12, 30))
            for k, (x, y) in {'tl': (0, 0), 'tr': (W - K, 0), 'bl': (0, H - K), 'br': (W - K, H - K)}.items():
                cv.rect(x, y, K, K, C['white'])
                p.sample({'type': 'corner', 'corner': k, 'box': {'x': x, 'y': y, 'w': K, 'h': K}})
            xs = list(range(K + 12, W - K - 12 + 1, 12))
            for x in xs:
                cv.rect(x, 0, 1, 20, C['white'])
                cv.rect(x, H - 20, 1, 20, C['white'])
            cxc = min(xs, key=lambda x: abs(x - W // 2))   # the comb line nearest the centre (Band 10 Pro: 168)
            p.sample({'type': 'comb', 'edge': 'top', 'xs': xs, 'y0': 0, 'y1': 20, 'centre_x': cxc})
            p.sample({'type': 'comb', 'edge': 'bottom', 'xs': xs, 'y0': H - 20, 'y1': H, 'centre_x': cxc})
            cv.text(W // 2, gbar['y'] - 80, 'Corners and edges. Note anything', 13, C['grey'], anchor='mm')
            cv.text(W // 2, gbar['y'] - 62, 'the system draws on top.', 13, C['grey'], anchor='mm')
        p.sample({'type': 'ruler_edges', 'rows': M['straight']})
        p.observe.append({'fact': 'screen.system_overlay', 'ask': 'Does the band draw anything over the face (status dot, icons)? Where, what colour, and when (unread notification, disconnected, charging)?'})
        f.image('normal', 'assets/bg.png', cv, 0, 0, 'bg')

        # ---------------- F2 colour ----------------
        f = self.face(2, 'colour', 'Colour')
        p = self.page(f, 2, 'colour', 'Colour')
        cv = self.bg()
        self.frame(cv, p)
        self.overlay_sample(p)
        greys = [i * 8 for i in range(13)]
        hx = lambda v: '%02x' % v
        # A: grey ramp inside the (palette-encoded) background image
        for i, v in enumerate(greys):
            x = ox + 3 + i * 12
            cv.rect(x, y0, 10, 34, (v, v, v))
            p.sample({'type': 'swatch', 'group': 'grey', 'hex': '#' + hx(v) * 3, 'value': v, 'box': {'x': x, 'y': y0, 'w': 10, 'h': 34}})
        # B: the same ramp in an image with > 256 colours (the toolkit then packs it as BGRA32)
        rb = Canvas(154, 40)
        for i, v in enumerate(greys):
            rb.rect(i * 12, 0, 10, 34, (v, v, v))
            p.sample({'type': 'swatch', 'group': 'grey_rgba32', 'hex': '#' + hx(v) * 3, 'value': v, 'box': {'x': ox + 3 + i * 12, 'y': y0 + 44, 'w': 10, 'h': 34}})
        for i in range(308):
            c = (i % 256, 64 if i < 256 else 192, 200)
            rb.im.putpixel((i % 154, 38 + i // 154), c + (255,))
        assert n_colours(rb.im) > 256
        # C: the same ramp as Lua object fills
        fills = []
        for i, v in enumerate(greys):
            fills.append({'x': ox + 3 + i * 12, 'y': y0 + 90, 'w': 10, 'h': 34, 'hex': '#' + hx(v) * 3})
            p.sample({'type': 'swatch', 'group': 'grey_lua', 'hex': '#' + hx(v) * 3, 'value': v, 'box': {'x': ox + 3 + i * 12, 'y': y0 + 90, 'w': 10, 'h': 34}})
        ramp = [0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80]
        for row, (group, mk) in enumerate((('red', lambda v: (v, 0, 0)), ('green', lambda v: (0, v, 0)), ('blue', lambda v: (0, 0, v)))):
            for i, v in enumerate(ramp):
                x, y = ox + 5 + i * 19, y0 + 134 + row * 26
                cv.rect(x, y, 17, 22, mk(v))
                p.sample({'type': 'swatch', 'group': group, 'hex': '#%02x%02x%02x' % mk(v), 'value': v, 'box': {'x': x, 'y': y, 'w': 17, 'h': 22}})
        for i, v in enumerate([0x20, 0x28, 0x30, 0x38, 0x40, 0x48]):
            x, y = ox + 3 + i * 26, y0 + 214
            cv.rect(x, y, 24, 28, (v, v, v))
            p.sample({'type': 'swatch', 'group': 'surface', 'hex': '#' + hx(v) * 3, 'value': v, 'box': {'x': x, 'y': y, 'w': 24, 'h': 28}})
        f.image('normal', 'assets/bg.png', cv, 0, 0, 'bg')
        f.image('normal', 'assets/ramp_rgba32.png', rb, ox + 3, y0 + 44, 'ramp-rgba32')
        lua_common(f)
        f.lua.append({'kind': 'alive', 'test': 'alive', 'x': ox + 3, 'y': y0 + 250})
        f.lua.append({'kind': 'fills', 'test': 'object_fill', 'fills': fills, 'status': (ox + 150, y0 + 250)})
        p.sample({'type': 'status', 'test': 'alive', 'box': {'x': ox + 3, 'y': y0 + 250, 'w': 6, 'h': 6}})
        p.sample({'type': 'status', 'test': 'object_fill', 'box': {'x': ox + 150, 'y': y0 + 250, 'w': 6, 'h': 6}})
        p.notes.append('Rows: A grey in the background image (palette), B grey in a >256-colour image (BGRA32), C grey as Lua object fills, then red, green, blue ramps #10-#80 and surfaces #20-#48.')

        # ---------------- F3 images ----------------
        f = self.face(3, 'images', 'Images')
        p = self.page(f, 3, 'images', 'Images')
        cv = self.bg()
        self.frame(cv, p)
        self.overlay_sample(p)
        t = tile_rgba()
        tn = tile_rgba(noise=True)
        timg, tnimg = Image.fromarray(t), Image.fromarray(tn)
        assert n_colours(timg) <= 256 and n_colours(tnimg) > 256
        f.image('normal', 'assets/bg.png', cv, 0, 0, 'bg')   # bg first (z 0); drawn into below
        f.image('normal', 'assets/tile_idx.png', timg, ox + 4, y0, 'tile-idx')
        f.image('normal', 'assets/tile_rgba32.png', tnimg, ox + 44, y0, 'tile-rgba32')
        p.sample({'type': 'tile', 'layer': 'widget', 'variant': 'png_indexed', 'box': {'x': ox + 4, 'y': y0, 'w': TILE, 'h': TILE}, 'expect': 'rgba'})
        p.sample({'type': 'tile', 'layer': 'widget', 'variant': 'png_rgba32', 'box': {'x': ox + 44, 'y': y0, 'w': TILE, 'h': TILE}, 'expect': 'rgba'})
        # 50 % pink over a white square in the background
        cv.rect(ox + 84, y0, TILE, TILE, C['white'])
        bl = Canvas(TILE, TILE, (0, 0, 0, 0))
        bl.rect(0, 0, TILE, TILE, C['pink'], 128)
        f.image('normal', 'assets/blend.png', bl, ox + 84, y0, 'blend')
        p.sample({'type': 'blend', 'box': {'x': ox + 84, 'y': y0, 'w': TILE, 'h': TILE}, 'over': C['white'], 'top': C['pink'], 'alpha': 128,
                  'white_ref': {'x': ox + 4, 'y': y0, 'w': 16, 'h': 12}})
        # alpha ramp (white, alpha 0 -> 255) over black vs the opaque grey ramp it should equal
        ar = Canvas(150, 10, (0, 0, 0, 0))
        for i in range(150):
            a = round(255 * i / 149)
            ar.rect(i, 0, 1, 10, C['white'], a)
            cv.rect(ox + 5 + i, y0 + 54, 1, 10, (a, a, a))
        f.image('normal', 'assets/alpha_ramp.png', ar, ox + 5, y0 + 40, 'alpha-ramp')
        p.sample({'type': 'ramp', 'fact': 'image.alpha_over_black', 'a': {'x': ox + 5, 'y': y0 + 40, 'w': 150, 'h': 10}, 'b': {'x': ox + 5, 'y': y0 + 54, 'w': 150, 'h': 10}})
        # Lua tiles
        lua_common(f)
        pngs = {}
        pngs['t_png_rgba.png'] = timg
        pal = Image.new('P', (TILE, TILE))
        palette = [255, 255, 255, 255, 0, 0, 0, 255, 0, 0, 0, 255, 0, 229, 255]
        pal.putpalette(palette + [0] * (768 - len(palette)))
        lut = {(255, 255, 255): 0, (255, 0, 0): 1, (0, 255, 0): 2, (0, 0, 255): 3, (0, 229, 255): 4}
        pal.putdata([lut[tuple(px[:3])] for px in t.reshape(-1, 4)])
        pngs['t_png8.png'] = pal
        grey = Image.fromarray(t).convert('LA')
        pngs['t_png_grey.png'] = grey
        pngs['t_png_rgb.png'] = Image.fromarray(np.ascontiguousarray(t[..., :3]))
        for name, im in pngs.items():
            if name == 't_png8.png':
                path_im = im
                f.script_files[name] = _PalettePNG(path_im)
            else:
                f.script(name, im)
        for name, data in lvgl_bins(t).items():
            f.script('t_%s.bin' % name, data)
        row1 = [('png_rgba', 't_png_rgba.png', 'rgba'), ('png8', 't_png8.png', 'rgba'), ('png_grey', 't_png_grey.png', 'grey'), ('png_rgb', 't_png_rgb.png', 'rgb')]
        row2 = [('v8_tca32', 't_v8_tca32.bin', 'rgba'), ('v8_tca16', 't_v8_tca16.bin', 'rgba'), ('v9_argb8888', 't_v9_argb8888.bin', 'rgba'), ('v9_rgb565', 't_v9_rgb565.bin', 'rgb')]
        for r, row in enumerate((row1, row2)):
            for i, (var, fn, exp) in enumerate(row):
                x, y = ox + 4 + i * 40, y0 + 72 + r * 50
                f.lua.append({'kind': 'image', 'test': 'image_' + var, 'file': fn, 'x': x, 'y': y, 'status': (x + 13, y + 36), 'format': var})
                p.sample({'type': 'tile', 'layer': 'lua', 'variant': var, 'box': {'x': x, 'y': y, 'w': TILE, 'h': TILE}, 'expect': exp})
                p.sample({'type': 'status', 'test': 'image_' + var, 'box': {'x': x + 13, 'y': y + 36, 'w': 6, 'h': 6}})
        for i, how in enumerate(('zoom', 'scale')):
            x, y = ox + 20 + i * 80, y0 + 188
            f.lua.append({'kind': 'image', 'test': 'image_' + how, 'file': 't_png_rgba.png', 'x': x, 'y': y, 'zoom': how, 'status': (x + 13, y + 54), 'format': 'png_rgba'})
            p.sample({'type': 'tile', 'layer': 'lua', 'variant': 'png_rgba_' + how + '_x2', 'box': {'x': x, 'y': y, 'w': TILE, 'h': TILE}, 'expect': 'rgba', 'zoom_test': True})
            p.sample({'type': 'status', 'test': 'image_' + how, 'box': {'x': x + 13, 'y': y + 54, 'w': 6, 'h': 6}})
        f.lua.insert(0, {'kind': 'alive', 'test': 'alive', 'x': ox + 150, 'y': y0 + 242})
        p.sample({'type': 'status', 'test': 'alive', 'box': {'x': ox + 150, 'y': y0 + 242, 'w': 6, 'h': 6}})
        f.assets['assets/bg.png'] = cv.im
        p.notes.append('Top row (widget layer): 256-colour PNG tile, >256-colour tile, 50 % pink over white, alpha ramp over black above the opaque grey ramp it should match. Lua rows: PNG RGBA, PNG8+tRNS, grey+alpha PNG, RGB PNG; LVGL v8 true-colour-alpha (32 and 16 bit), v9 ARGB8888, v9 RGB565; then a PNG with zoom=512 and with scale=512.')

        # ---------------- F4 number widgets ----------------
        f = self.face(4, 'numbers', 'Numbers')
        p = self.page(f, 4, 'numbers', 'Numbers')
        cv = self.bg()
        self.frame(cv, p)
        self.overlay_sample(p)
        f.image('normal', 'assets/bg.png', cv, 0, 0, 'bg')
        rows = [
            ('steps', 'left', ox + 4, 5, 0, False, False, 'steps L5'),
            ('steps', 'center', ox + 80, 5, 0, False, False, 'steps C5'),
            ('steps', 'right', ox + 84, 5, 0, False, False, 'steps R5'),
            ('battery', 'center', ox + 80, 3, 0, False, True, 'batt C3 %'),
            None,
            ('steps', 'left', ox + 4, 5, 6, False, False, 'steps sp+6'),
            ('steps', 'left', ox + 4, 5, -3, False, False, 'steps sp-3'),
        ]
        for k, row in enumerate(rows):
            y = y0 + 8 + k * 44
            if row is None:
                for (src, x, lz, lab, region) in (('minute', ox + 4, True, 'min 0', [0, ox + 60]), ('hour', ox + 84, False, 'hr', [ox + 60, ox + 120]),
                                                  ('second', ox + 124, True, 's', [ox + 120, W])):
                    f.number('normal', src, x, y, 2, 'left', 0, lz, wid='%s-%d' % (src, k))
                    cv.rect(x, y - 7, 1, 5, C['cyan'])
                    cv.text(x + 3, y - 9, lab, 9)
                    p.sample({'type': 'number', 'source': src, 'x': x, 'y': y, 'align': 'left', 'count': 2, 'spacing': 0, 'lz': lz,
                              'region': region, 'row': k})
                continue
            src, align, x, n, sp, lz, unit, lab = row
            f.number('normal', src, x, y, n, align, sp, lz, unit=unit, wid='%s-%d' % (src, k))
            cv.rect(x, y - 7, 1, 5, C['cyan'])
            cv.text(x + 3 if align != 'right' else x - 3, y - 9, lab, 9, anchor='la' if align != 'right' else 'ra')
            p.sample({'type': 'number', 'source': src, 'x': x, 'y': y, 'align': align, 'count': n, 'spacing': sp, 'lz': lz, 'unit': 12 if unit else 0,
                      'region': [0, W], 'row': k})
        f.assets['assets/bg.png'] = cv.im
        p.observe.append({'fact': 'widgets.number.second_updates', 'ask': 'Row 5, right: does the seconds number change every second while the face is awake?'})
        p.notes.append('Cyan marks show each widget\'s x. Rows: steps left / centre / right (5 digits), battery centre (3 digits + % unit), minute (leading zero) + hour + second, steps with spacing +6 and -3.')

        # ---------------- F5 image lists ----------------
        f = self.face(5, 'lists', 'Lists')
        p = self.page(f, 5, 'lists', 'Lists')
        cv = self.bg()
        self.frame(cv, p)
        self.overlay_sample(p)
        f.image('normal', 'assets/bg.png', cv, 0, 0, 'bg')
        wk = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
        mo = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
        lists = [
            (0, ox + 4, 'number', 'battery', 3, 'battery'),
            (0, ox + 84, 'number', 'day', 2, 'day'),
            (1, ox + 4, 'list', 'battery', [0, 20, 40, 60, 80, 100], ['0', '20', '40', '60', '80', '100'], 'batt-steps'),
            (2, ox + 4, 'list', 'battery', [101, 102], ['101', '102'], 'batt-below'),
            (2, ox + 84, 'list', 'battery', [0, 1], ['0', '1'], 'batt-above'),
            (3, ox + 4, 'list', 'weekday', list(range(7)), wk, 'weekday'),
            (3, ox + 84, 'list', 'month', list(range(1, 13)), mo, 'month'),
            (4, ox + 4, 'list', 'steps', [0, 1000, 5000, 10000], ['0', '1k', '5k', '10k'], 'steps-steps'),
            (4, ox + 84, 'number', 'hour', 2, 'hour'),
            (4, ox + 120, 'number', 'minute', 2, 'minute'),
        ]
        for it in lists:
            row, x = it[0], it[1]
            y = y0 + 8 + row * 48
            cv.rect(x, y - 7, 1, 5, C['cyan'])
            if it[2] == 'number':
                src, n = it[3], it[4]
                f.number('normal', src, x, y, n, 'left', 0, src in ('hour', 'minute'), wid='%s-n%d' % (src, row))
                cv.text(x + 3, y - 9, src, 9)
                p.sample({'type': 'number', 'source': src, 'x': x, 'y': y, 'align': 'left', 'count': n, 'spacing': 0,
                          'lz': src in ('hour', 'minute'), 'region': [x - 2, x + n * CELL_W + 2], 'row': row})
            else:
                src, values, labels, wid = it[3], it[4], it[5], it[6]
                f.image_list('normal', src, x, y, values, labels, wid)
                cv.text(x + 3, y - 9, wid, 9)
                p.sample({'type': 'imagelist', 'source': src, 'list': wid, 'x': x, 'y': y, 'values': values, 'labels': labels})
        f.assets['assets/bg.png'] = cv.im
        p.notes.append('Each list frame carries its index in the bit squares. Battery frames at 0/20/.../100 (which frame for e.g. 57 %?), frames only above 100 (value below the first frame) and only 0/1 (value above the last), weekday, month, steps frames 0/1000/5000/10000; battery, day, hour and minute numbers give the true values.')

        # ---------------- F6 Lua layer ----------------
        f = self.face(6, 'lua', 'Lua')
        p = self.page(f, 6, 'lua', 'Lua')
        cv = self.bg()
        self.frame(cv, p)
        self.overlay_sample(p)
        f.image('normal', 'assets/bg.png', cv, 0, 0, 'bg')
        lua_common(f)
        tgt = target_tile()
        f.script('target.png', tgt)
        for d in range(10):
            f.script('dg%d.png' % d, digit_cell(str(d), d))
        scol = ox + 154
        f.lua.append({'kind': 'alive', 'test': 'alive', 'x': scol, 'y': y0 - 12})
        p.sample({'type': 'status', 'test': 'alive', 'box': {'x': scol, 'y': y0 - 12, 'w': 6, 'h': 6}})
        # placement pairs
        for k, (wx, lx) in enumerate(((ox + 4, ox + 84), (ox + 84, ox + 4))):
            y = y0 + k * 44
            f.image('normal', 'assets/target.png', tgt, wx, y, 'target-%d' % k)
            f.lua.append({'kind': 'image', 'test': 'place_%d' % k, 'file': 'target.png', 'x': lx, 'y': y, 'status': (scol, y + 13), 'format': 'png_rgba'})
            p.sample({'type': 'target', 'layer': 'widget', 'box': {'x': wx, 'y': y, 'w': TILE, 'h': TILE}})
            p.sample({'type': 'target', 'layer': 'lua', 'box': {'x': lx, 'y': y, 'w': TILE, 'h': TILE}})
            p.sample({'type': 'status', 'test': 'place_%d' % k, 'box': {'x': scol, 'y': y + 13, 'w': 6, 'h': 6}})
        y = y0 + 88
        for what, x, sy in (('hor_res', ox + 4, y + 4), ('ver_res', ox + 84, y + 20)):
            f.lua.append({'kind': 'digits', 'test': what, 'what': what, 'n': 3, 'x': x, 'y': y, 'status': (scol, sy)})
            p.sample({'type': 'digits', 'what': what, 'n': 3, 'x': x, 'y': y})
            p.sample({'type': 'status', 'test': what, 'box': {'x': scol, 'y': sy, 'w': 6, 'h': 6}})
            cv.text(x + 1, y - 9, what.replace('_', ' '), 9)
        y = y0 + 132
        for what, x, sy in (('hour', ox + 4, y + 4), ('minute', ox + 40, y + 20)):
            f.lua.append({'kind': 'digits', 'test': 'lua_' + what, 'what': what, 'n': 2, 'x': x, 'y': y, 'status': (scol, sy)})
            p.sample({'type': 'digits', 'what': what, 'n': 2, 'x': x, 'y': y})
            p.sample({'type': 'status', 'test': 'lua_' + what, 'box': {'x': scol, 'y': sy, 'w': 6, 'h': 6}})
        cv.text(ox + 5, y - 9, 'lua h m', 9)
        for src, x in (('hour', ox + 84), ('minute', ox + 120)):
            f.number('normal', src, x, y, 2, 'left', 0, True, wid='w-' + src)
            p.sample({'type': 'number', 'source': src, 'x': x, 'y': y, 'align': 'left', 'count': 2, 'spacing': 0, 'lz': True,
                      'region': [x - 2, x + 2 * CELL_W + 2], 'row': 3})
        cv.text(ox + 85, y - 9, 'widget h m', 9)
        y = y0 + 176
        f.lua.append({'kind': 'digits', 'test': 'raw_minute_low', 'what': 'raw_minute_low', 'n': 6, 'x': ox + 4, 'y': y, 'status': (scol, y + 13)})
        p.sample({'type': 'digits', 'what': 'raw_minute_low', 'n': 6, 'x': ox + 4, 'y': y})
        p.sample({'type': 'status', 'test': 'raw_minute_low', 'box': {'x': scol, 'y': y + 13, 'w': 6, 'h': 6}})
        cv.text(ox + 5, y - 9, 'raw timeMinuteLow', 9)
        y = y0 + 220
        f.lua.append({'kind': 'label', 'test': 'label', 'text': 'LUA 0123', 'x': ox + 4, 'y': y, 'status': (scol, y + 4)})
        p.sample({'type': 'status', 'test': 'label', 'box': {'x': scol, 'y': y + 4, 'w': 6, 'h': 6}})
        p.sample({'type': 'presence', 'what': 'lua_label', 'box': {'x': ox + 4, 'y': y, 'w': 100, 'h': 22}})
        y = y0 + 250
        fills = [{'x': ox + 4, 'y': y, 'w': 24, 'h': 16, 'hex': '#ffffff'}, {'x': ox + 32, 'y': y, 'w': 24, 'h': 16, 'hex': '#808080'},
                 {'x': ox + 60, 'y': y, 'w': 24, 'h': 16, 'hex': '#404040'}]
        f.lua.append({'kind': 'fills', 'test': 'object_fill', 'fills': fills, 'status': (scol, y)})
        p.sample({'type': 'status', 'test': 'object_fill', 'box': {'x': scol, 'y': y, 'w': 6, 'h': 6}})
        for fl in fills:
            p.sample({'type': 'swatch', 'group': 'lua_fill', 'hex': fl['hex'], 'value': int(fl['hex'][1:3], 16), 'box': {k: fl[k] for k in ('x', 'y', 'w', 'h')}})
        f.lua.append({'kind': 'timer', 'test': 'timer', 'x': ox + 100, 'y': y + 5, 'status': (scol, y + 10)})
        p.sample({'type': 'status', 'test': 'timer', 'box': {'x': scol, 'y': y + 10, 'w': 6, 'h': 6}})
        f.assets['assets/bg.png'] = cv.im
        p.observe.append({'fact': 'lua.timer_runs', 'ask': 'Bottom row: does the small green square right of the grey fills blink once a second?'})
        p.observe.append({'fact': 'lua.label_draws', 'ask': 'Is the text "LUA 0123" visible (row 6)? In what font/size?'})
        p.notes.append('Rows: placement targets (widget | Lua, then Lua | widget), Lua lvgl.HOR_RES() and VER_RES(), Lua hour/minute from dataman beside the widget hour/minute, the raw timeMinuteLow value, a Lua Label, Lua object fills and a timer. Status squares in the right column.')

        # ---------------- F7 always-on ----------------
        f = self.face(7, 'aod', 'AOD')
        for theme, pid in (('normal', 7), ('aod', 8)):
            p = self.page(f, pid, 'aod_' + theme, 'AOD' if theme == 'aod' else 'AOD test', theme=theme)
            cv = self.bg()
            self.frame(cv, p)
            if theme == 'normal':
                self.overlay_sample(p)
            for i, v in enumerate(greys):
                x = ox + 3 + i * 12
                cv.rect(x, y0, 10, 34, (v, v, v))
                p.sample({'type': 'swatch', 'group': 'aod_grey', 'hex': '#' + hx(v) * 3, 'value': v, 'box': {'x': x, 'y': y0, 'w': 10, 'h': 34}})
            for i, v in enumerate((0x80, 0xc0, 0xff)):
                x = ox + 4 + i * 52
                cv.rect(x, y0 + 44, 48, 28, (v, v, v))
                p.sample({'type': 'swatch', 'group': 'aod_level', 'hex': '#' + hx(v) * 3, 'value': v, 'box': {'x': x, 'y': y0 + 44, 'w': 48, 'h': 28}})
            y = y0 + 92
            for src, x in (('hour', ox + 4), ('minute', ox + 44), ('second', ox + 84)):
                cv.rect(x, y - 7, 1, 5, C['cyan'])
                cv.text(x + 3, y - 9, src[:3], 9)
                f.number(theme, src, x, y, 2, 'left', 0, True, wid='%s-%s' % (theme, src))
                p.sample({'type': 'number', 'source': src, 'x': x, 'y': y, 'align': 'left', 'count': 2, 'spacing': 0, 'lz': True,
                          'region': [x - 2, x + 2 * CELL_W + 2], 'row': 2})
            y = y0 + 136
            cv.rect(ox + 4, y - 7, 1, 5, C['cyan'])
            cv.text(ox + 7, y - 9, 'battery', 9)
            f.number(theme, 'battery', ox + 4, y, 3, 'left', 0, False, wid='%s-battery' % theme)
            p.sample({'type': 'number', 'source': 'battery', 'x': ox + 4, 'y': y, 'align': 'left', 'count': 3, 'spacing': 0, 'lz': False,
                      'region': [ox, ox + 3 * CELL_W + 4], 'row': 3})
            if theme == 'normal':
                cv.text(W // 2, y0 + 200, 'Photograph, then', 12, C['grey'], anchor='mm')
                cv.text(W // 2, y0 + 216, 'let the band dim', 12, C['grey'], anchor='mm')
                cv.text(W // 2, y0 + 232, 'to always-on', 12, C['grey'], anchor='mm')
            else:
                cv.text(W // 2, y0 + 216, 'ALWAYS-ON', 12, C['grey'], anchor='mm')
            f.widgets[theme].insert(0, {'id': 'bg-' + theme, 'type': 'image', 'asset': 'assets/bg_%s.png' % theme, 'x': 0, 'y': 0, 'z': 0, 'allowOverlap': True})
            f.asset('assets/bg_%s.png' % theme, cv)
            for i, w in enumerate(f.widgets[theme]):
                w['z'] = i
        f.pages['aod'].observe.append({'fact': 'aod.shows', 'ask': 'With always-on enabled on the band: after the screen dims, is this AOD page shown (barcode p8, "ALWAYS-ON")? How long until it dims?'})
        f.pages['aod'].observe.append({'fact': 'aod.second_updates', 'ask': 'In always-on: does the seconds number change? Do hour/minute update at the minute?'})
        f.pages['normal'].notes.append('Photograph the normal view (p7), then without moving the phone or changing exposure (lock AE/AF), let it dim and photograph the always-on view (p8): same swatches, so the ratio is the AOD dimming.')

        # ---------------- F8 always-on + Lua ----------------
        f = self.face(8, 'aodlua', 'AOD Lua')
        f.aod_script = True
        big = Canvas(24, 24)
        big.rect(0, 0, 24, 24, C['green'])
        lua_common(f)
        f.script('sq_big.png', big)
        for theme, pid in (('normal', 9), ('aod', 10)):
            p = self.page(f, pid, 'aodlua_' + theme, 'AOD Lua' if theme == 'aod' else 'AOD Lua test', theme=theme)
            cv = self.bg()
            self.frame(cv, p)
            cv.rect(ox + 4, y0, 24, 24, C['green'])
            cv.text(ox + 4, y0 + 30, 'image', 9)
            cv.text(ox + 84, y0 + 30, 'Lua', 9)
            p.sample({'type': 'presence', 'what': 'widget_square', 'box': {'x': ox + 4, 'y': y0, 'w': 24, 'h': 24}, 'colour': 'green'})
            p.sample({'type': 'presence', 'what': 'lua_square', 'box': {'x': ox + 84, 'y': y0, 'w': 24, 'h': 24}, 'colour': 'green'})
            if theme == 'normal':
                cv.text(W // 2, y0 + 120, 'Photograph, then', 12, C['grey'], anchor='mm')
                cv.text(W // 2, y0 + 136, 'let the band dim', 12, C['grey'], anchor='mm')
            else:
                cv.text(W // 2, y0 + 128, 'ALWAYS-ON + LUA', 12, C['grey'], anchor='mm')
            f.widgets[theme].insert(0, {'id': 'bg-' + theme, 'type': 'image', 'asset': 'assets/bg_%s.png' % theme, 'x': 0, 'y': 0, 'z': 0, 'allowOverlap': True})
            f.asset('assets/bg_%s.png' % theme, cv)
        f.lua.append({'kind': 'image', 'test': 'lua_square', 'file': 'sq_big.png', 'x': ox + 84, 'y': y0, 'status': (ox + 150, y0), 'format': 'png_rgba'})
        f.pages['aod'].observe.append({'fact': 'lua.runs_on_aod', 'ask': 'In always-on: is the right-hand green square (drawn by Lua) there, or only the left one (an image)?'})
        return self

    def write(self):
        for f in self.faces:
            f.write()
        layout = {
            'generated_by': 'tools/face-calib/gen.py', 'kit_build': KIT_BUILD, 'model': self.model, 'device': self.M['name'],
            'screen': {'w': self.M['W'], 'h': self.M['H'], 'shape': self.M['shape'], 'r': self.M['r'], 'straight_rows': self.M['straight']},
            'frame': {'tick_every': TICK_EVERY, 'tick_len': TICK_LEN, 'yellow_every': 100, 'ticks': self.ticks,
                      'bar': self.M['bar'], 'code': self.M['code'],
                      'colours': {k: '#%02x%02x%02x' % v for k, v in C.items()}},
            'cells': {'digit': {'w': CELL_W, 'h': CELL_H, 'bits_at': BITS_AT}, 'frame': {'w': FRAME_W, 'h': FRAME_H, 'bits_at': FRAME_BITS_AT},
                      'bit_sq': BIT_SQ, 'bit_gap': BIT_GAP, 'minus_code': MINUS_CODE, 'tile': TILE},
            'faces': [{'n': f.n, 'slug': f.slug, 'id': f.id, 'name': f.name, 'project': os.path.relpath(f.dir, OUT),
                       'bin': os.path.relpath(os.path.join(f.dir, 'dist', f.output + '.bin'), OUT),
                       'pages': {t: p.id for t, p in f.pages.items()}, 'lua_ops': f.lua, 'aod_script': f.aod_script} for f in self.faces],
            'pages': [p.spec() for p in self.pages],
        }
        if self.M['shape'] == 'circle':  # rulers inside the circle (absent: at the edges, from y 0)
            ru = self.M['ruler']
            layout['frame']['ruler'] = {'left_x': ru['left_x'], 'right_x': ru['right_x'], 'y0': ru['y0']}
        os.makedirs(os.path.join(OUT, 'layouts'), exist_ok=True)
        dump(os.path.join(OUT, 'layouts', self.model + '.json'), layout)
        return layout


class _PalettePNG:
    """A palette image saved with a tRNS entry making index 4 (the hole) transparent."""

    def __init__(self, im):
        self.im = im

    def save(self, path):
        self.im.save(path, transparency=4)


def main(argv):
    global OUT
    args = argv[1:]
    if args[:1] == ['--list']:          # onboarded devices and their face builder (build.sh)
        for m in onboarded():
            print(m, ds.load(m)['face']['builder'])
        return
    specs, ids = [], []
    i = 0
    while i < len(args):
        if args[i] == '--out':
            OUT = os.path.abspath(args[i + 1])
            i += 2
        elif args[i] == '--spec':
            specs.append(ds.load(args[i + 1]))
            i += 2
        else:
            ids.append(args[i])
            i += 1
    if not specs and (not ids or ids == ['all']):
        ids = onboarded()
    specs += [ds.load(m) for m in ids if m != 'all']
    # The kit inside the miband-dev plugin is read-only: writing faces/ and layouts/ here needs a
    # copy in the workspace (the new-project skill's copy-kit.sh face-calib); --out elsewhere is fine.
    if OUT == HERE and os.path.exists(os.path.join(HERE, '..', '..', '.claude-plugin', 'plugin.json')):
        sys.exit('This is the plugin\'s read-only copy of the kit. Copy it into your workspace first:\n'
                 '  %s/../../skills/new-project/copy-kit.sh face-calib   (from the workspace root; or pass --out DIR)' % HERE)
    for spec in specs:
        m = spec['id']
        kit = Kit(spec).build()
        kit.write()
        rel = lambda q: os.path.relpath(q, HERE) if OUT == HERE else q
        print('%s: %d faces, %d pages -> %s, %s (faces %s)' % (m, len(kit.faces), len(kit.pages), rel(os.path.join(OUT, 'faces', m)),
                                                              rel(os.path.join(OUT, 'layouts', m + '.json')), kit.M['status']))
        for f in kit.faces:
            print('  %s  %-24s %s' % (f.id, f.name, rel(f.dir)))


if __name__ == '__main__':
    main(sys.argv)
