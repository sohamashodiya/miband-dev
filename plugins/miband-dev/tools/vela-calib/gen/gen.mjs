#!/usr/bin/env node
// Generates the calibration app's single page (src/pages/index/index.ux), its manifest, and the
// layout file measure.py reads (layouts/<device>.json). Every test element sits at a position
// computed here, so the band markup and the measurement always agree. Don't edit index.ux by hand.
//
//   node gen/gen.mjs <device id>      (devices/<id>/device.json; default band10pro; `npm run gen` runs images.py first)
//
// One .rpk per device (`npm run build` builds all of them, see gen/build.mjs): each is generated
// for its screen with designWidth = the screen width, so 1 design px = 1 panel px. The geometry
// page and the start page show what @system.device reports, and measure.py checks the scale from
// the screen's own outline (a capsule's end radius, a circle's radius), so a wrong design width
// can't go unnoticed.
//
// Frame on every page:
//   - rulers down both edges: a 1 px tick every 10 px (top edge of the tick = y), 8 px long,
//     14 px every 50, 22 px and yellow every 100; left ruler starts at x 0, right ruler ends at x W.
//     On a capsule (Band 10 / 11) only the ticks on the straight sides are visible, which is plenty.
//     On a circle the rulers are two straight columns inside the circle (layout frame.ruler).
//   - a yellow scale bar exactly BAR.len x 4 px near the bottom (200 px on the Band 10 Pro, 160 px
//     on the 212 px wide capsule, where it has to stay clear of the rounded end)
//   - a page barcode (8 cells: on, 5 bits of the page number, even parity, on) next to the bar,
//     so measure.py identifies each photo by itself
//   - a grey page label at the top
// Every sample sits in a slot sized for the worst case (glyphs up to ~15 % wider and lines up to
// 1.5 em tall on a new model), inside the visible screen, and clear of the rulers, bar and barcode.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { loadSpec, geometry, insidePt } from '../device-spec.mjs'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.join(HERE, '..')

// The device comes from its spec (devices/<id>/device.json, or --spec PATH): screen size and shape.
//   node gen/gen.mjs <id>                          pages in src/ + layouts/<id>.json
//   node gen/gen.mjs --spec PATH [--layout-only] [--layout-out PATH]
//     --layout-only: write only the layout (no src/), e.g. to check a device the kit hasn't built for.
// The shape's outline (capsule ends, rounded corners, circle) is the kit's placement assumption;
// the geometry page measures the real one.
const argv = process.argv.slice(2)
const optv = (k) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : undefined }
const LAYOUT_ONLY = argv.includes('--layout-only')
const specArg = optv('spec') || argv.find((a, i) => !a.startsWith('--') && !['--spec', '--layout-out'].includes(argv[i - 1])) || 'band10pro'
const SPEC = loadSpec(specArg)
const DEVICE = SPEC.id
const D = Object.assign({ name: SPEC.name }, geometry(SPEC))

// The kit inside the miband-dev plugin is read-only: generating writes src/ and layouts/ into the
// kit, so it runs only from a copy in your workspace (the new-project skill's copy-kit.sh vela-calib).
// A layout-only run that writes its layout elsewhere (--layout-out, as the tests do) is fine.
if (fs.existsSync(path.join(ROOT, '..', '..', '.claude-plugin', 'plugin.json')) && !(LAYOUT_ONLY && optv('layout-out'))) {
  console.error('This is the plugin\'s read-only copy of the kit. Copy it into your workspace first:\n' +
    '  ' + path.join(ROOT, '..', '..', 'skills', 'new-project', 'copy-kit.sh') + ' vela-calib   (from the workspace root; then npm install there)')
  process.exit(2)
}
const W = D.w
const H = D.h
const CAPSULE = D.shape === 'capsule'
const CIRCLE = D.shape === 'circle'
const KIT = (SPEC.calib && SPEC.calib.quickapp) || {}

const VERSION = { name: '2.0.0', code: 2 }
const PACKAGE = 'com.soham.velacalib'

// ---- frame geometry (band px) -------------------------------------------------------------
const TICK_EVERY = 10
const TICK_LEN = [8, 14, 22]
const MARGIN = 4 // every sample keeps this far inside the (assumed) visible outline
const RUL = TICK_LEN[2] + 1
const floor10 = (v) => Math.floor(v / 10) * 10
// Is (x, y) inside the visible screen, m px in from its outline (the kit's assumed outline)?
const inside = (x, y, m = MARGIN) => insidePt(D, x, y, m)
const rectInside = (r, m = MARGIN) => [[r.x, r.y], [r.x + r.w, r.y], [r.x, r.y + r.h], [r.x + r.w, r.y + r.h]].every(([a, b]) => inside(a, b, m))

// Rulers: rect and capsule screens have them down the very edges (left ruler from x 0, right ruler
// ending at x W, every row). A circle has no straight edge, so its rulers are two straight columns
// inside the circle (at 0.62 R from the centre), over the rows where their outer ends are visible.
let RULER
if (!CIRCLE) {
  RULER = { left_x: 0, right_x: W, y0: 0, n: Math.floor((H - 1) / TICK_EVERY) + 1 }
} else {
  const lx = Math.round(W / 2 - 0.62 * D.radius)
  const rows = []
  for (let y = 0; y < H; y += TICK_EVERY) if (inside(lx, y) && inside(lx, y + 1) && inside(W - lx, y) && inside(W - lx, y + 1)) rows.push(y)
  RULER = { left_x: lx, right_x: W - lx, y0: rows[0], n: rows.length }
}
const TICKS = Array.from({ length: RULER.n }, (_, i) => { const k = (RULER.y0 + i * TICK_EVERY) / TICK_EVERY; return k % 10 === 0 ? 2 : k % 5 === 0 ? 1 : 0 })
const RL = { x0: RULER.left_x + RUL, x1: RULER.right_x - RUL } // clear of both rulers

// The frame, pushed k px further in until every part of it is inside the outline (k = 0 for the
// Band 10 Pro and Band 11, whose layouts this reproduces exactly). The bar and barcode boxes carry
// the layout test's 2 px of clearance.
let BAR, CODE, LABEL, AREA
const frameOk = () => {
  const bar = { x: BAR.x, y: BAR.y - 2, w: BAR.len, h: BAR.h + 4 }
  const code = { x: CODE.x - 2, y: CODE.y - 2, w: 7 * CODE.pitch + CODE.cell + 4, h: CODE.h + 4 }
  const label = { x: LABEL.x, y: LABEL.y, w: LABEL.w, h: Math.ceil(1.5 * LABEL.px) }
  const area = { x: AREA.x0, y: AREA.y0, w: AREA.x1 - AREA.x0, h: AREA.y1 - AREA.y0 }
  return area.w > 0 && area.h > 0 && [bar, code, label, area].every((r) => rectInside(r))
}
function frameAt(k) {
  if (D.shape === 'rect') {
    const len = Math.min(200, floor10(W - 136))
    BAR = { x: W - 26 - len - k, y: H - 24 - k, len, h: 4 }
    CODE = { x: 38 + k, y: H - 28 - k, cell: 6, pitch: 8, h: 10 }
    LABEL = { x: 50 + k, y: 5 + k, w: W - 100 - 2 * k, px: 16, align: 'left' }
    AREA = { x0: 24, x1: W - 24, y0: 28 + k, y1: Math.min(BAR.y, CODE.y) - 6 }
  } else if (CAPSULE) {
    // Capsule: the bottom end narrows below y = H - endR, so the bar sits just inside the straight
    // part (its ends keep > 8 px from the arc) and the barcode, only 62 px wide, goes under it.
    const len = Math.min(160, floor10(W - 52))
    BAR = { x: Math.round((W - len) / 2), y: H - 58 - k, len, h: 4 }
    CODE = { x: Math.round(W / 2) - 31, y: BAR.y + 12, cell: 6, pitch: 8, h: 10 }
    LABEL = { x: Math.round(W / 2) - 58, y: 26 + k, w: 116, px: 16, align: 'center' }
    AREA = { x0: 24, x1: W - 24, y0: 52 + k, y1: BAR.y - 6 }
  } else {
    // Circle: bar and barcode stacked and centred low in the circle, below the rulers' last rows;
    // the label centred near the top; samples between the rulers.
    const len = Math.min(200, floor10(RULER.right_x - RULER.left_x - 2 * RUL - 8))
    const bx = Math.round((W - len) / 2)
    const fits = (y) => rectInside({ x: bx, y: y - 2, w: len, h: 8 }) && rectInside({ x: Math.round(W / 2) - 33, y: y + 10, w: 66, h: 14 })
    let by = H - 1
    while (by > H / 2 && !fits(by)) by--
    BAR = { x: bx, y: by - k, len, h: 4 }
    CODE = { x: Math.round(W / 2) - 31, y: BAR.y + 12, cell: 6, pitch: 8, h: 10 }
    const lw = Math.min(200, floor10(W / 2))
    let ly = 5
    while (ly < H / 2 && !rectInside({ x: Math.round((W - lw) / 2), y: ly, w: lw, h: 24 })) ly++
    LABEL = { x: Math.round((W - lw) / 2), y: ly + k, w: lw, px: 16, align: 'center' }
    const x0 = RL.x0 + 1
    const x1 = RL.x1 - 1
    let y0 = LABEL.y + 30
    while (y0 < H && !(inside(x0, y0) && inside(x1, y0))) y0++
    let y1 = BAR.y - 6
    while (y1 > 0 && !(inside(x0, y1) && inside(x1, y1))) y1--
    AREA = { x0, x1, y0, y1 }
  }
}
let fk = 0
for (frameAt(fk); !frameOk(); frameAt(fk)) {
  fk += 2
  if (fk > Math.min(W, H) / 4) throw new Error(`${DEVICE}: can't fit the frame (rulers, bar, barcode, label, sample area) inside a ${W} x ${H} ${D.shape}`)
}
const AW = AREA.x1 - AREA.x0
const AH = AREA.y1 - AREA.y0
if (AW < 140 || AH < 280) throw new Error(`${DEVICE}: sample area ${AW} x ${AH} px is too small for the kit's pages (needs 140 x 280)`)
// Size choices below follow the sample area, not the model: a narrow area (< 200 px, e.g. the
// 212 px capsule) gets smaller test strings.
const NARROW = AW < 200

// Colours. Outline colours are saturated and never white, so measure.py can tell outline from ink.
const C = {
  white: '#ffffff', yellow: '#ffd60a', pink: '#ff2d95', cyan: '#00e5ff', green: '#3cff3c',
  grey: '#9a9a9a', dim: '#505050'
}
const REGIME_COLOUR = { nat: C.cyan, tall: C.pink, short: C.green }

// ---- width estimates (packing only; the profile holds the real numbers) -------------------
// fit.js table (max of Noto Sans Bold and MiSans Latin Bold, em), raised to the Band 10 Pro's
// measured advances where those are wider (profile 2026-09-27: 0 .659, 6 .642, 8 .658, space .339).
// A lower bound for a new model; SLACK_W covers glyphs up to ~15 % wider plus 1 px tracking.
const G = {
  ' ': 0.339, ',': 0.32, '.': 0.3, '-': 0.462, '/': 0.438, ':': 0.3, '%': 0.902, '…': 0.963,
  0: 0.66, 1: 0.572, 2: 0.604, 3: 0.62, 4: 0.623, 5: 0.621, 6: 0.643, 7: 0.572, 8: 0.658, 9: 0.627,
  A: 0.723, B: 0.683, C: 0.704, D: 0.75, E: 0.603, F: 0.583, G: 0.735, H: 0.765, I: 0.389, J: 0.53,
  K: 0.708, L: 0.583, M: 0.943, N: 0.813, O: 0.791, P: 0.65, Q: 0.815, R: 0.666, S: 0.622, T: 0.623,
  U: 0.756, V: 0.728, W: 1.071, X: 0.741, Y: 0.703, Z: 0.643, a: 0.599, b: 0.632, c: 0.555,
  d: 0.632, e: 0.597, f: 0.39, g: 0.632, h: 0.65, i: 0.299, j: 0.298, k: 0.62, l: 0.298, m: 0.975,
  n: 0.65, o: 0.625, p: 0.632, q: 0.632, r: 0.447, s: 0.509, t: 0.434, u: 0.65, v: 0.571, w: 0.856,
  x: 0.578, y: 0.571, z: 0.502
}
const em = (s) => [...String(s)].reduce((a, c) => a + (G[c] === undefined ? 1 : G[c]), 0)
// Slack over those widths / the Band 10 Pro's measured 1.327 em line box. A device whose own
// metrics were measured (spec calib.quickapp.text_slack "measured": the Band 10 Pro) needs a little
// margin; any other gets room for glyphs up to ~15 % wider (+ margin) and lines up to 1.5 em.
const MEASURED_FONT = KIT.text_slack === 'measured'
const SLACK_W = MEASURED_FONT ? 1.08 : 1.2
const SLACK_LINE = MEASURED_FONT ? 1.4 : 1.5
// Worst-case outer width of a 1 px outlined <text> holding s at px: slack, 1 px tracking per glyph, border.
const worstW = (s, px) => Math.ceil(em(s) * px * SLACK_W) + [...String(s)].length + 2
const lineSlot = (px, lines = 1) => Math.ceil(SLACK_LINE * px * lines) + 2

// ---- element model ------------------------------------------------------------------------
// el(tag, css, opts): css is an object of CSS properties (kebab-case) -> value.
function el(tag, css, opts = {}) {
  return { tag, css, text: opts.text, attrs: opts.attrs || {}, kids: opts.kids || [], rawClass: opts.rawClass }
}
const abs = (x, y, w, h, extra = {}) => Object.assign({ position: 'absolute', left: px(x), top: px(y) },
  w === undefined ? {} : { width: px(w) }, h === undefined ? {} : { height: px(h) }, extra)
function px(v) { return typeof v === 'number' ? v + 'px' : v }
const fill = (x, y, w, h, colour, extra = {}) => el('div', abs(x, y, w, h, Object.assign({ 'background-color': colour }, extra)))
const txt = (css, text) => el('text', css, { text })

// ---- pages --------------------------------------------------------------------------------
const pages = []
function page(key, title, opts = {}) {
  const p = { id: pages.length, key, title, els: [], samples: [], notes: opts.notes || [], observe: opts.observe || [],
    bar: opts.bar || BAR, code: opts.code || CODE, label: opts.label || LABEL }
  pages.push(p)
  return p
}
// Every sample carries `slot`: the worst-case footprint it may draw into (checked by the layout
// test: inside the screen, no overlaps, clear of the rulers, the bar and the barcode).
function sample(p, s) {
  s.id = s.id || `${p.key}.${p.samples.length}`
  p.samples.push(s)
  return s
}

// First-fit decreasing-height shelf packing of items {w, h, place(p, x, y)} over pages made by mk().
function pack(items, mk, area = AREA, gapX = 6, gapY = 8) {
  const sorted = items.slice().sort((a, b) => b.h - a.h)
  const shelves = [] // {p, y, h, x}
  const made = []
  const pageY = new Map()
  for (const it of sorted) {
    if (it.w > area.x1 - area.x0 || it.h > area.y1 - area.y0) throw new Error('item too big: ' + JSON.stringify({ w: it.w, h: it.h, k: it.key, area }))
    let sh = shelves.find((s) => s.x + it.w <= area.x1 && it.h <= s.h)
    if (!sh) {
      let p = made.find((q) => pageY.get(q) + it.h <= area.y1)
      if (!p) { p = mk(made.length); made.push(p); pageY.set(p, area.y0) }
      sh = { p, y: pageY.get(p), h: it.h, x: area.x0 }
      pageY.set(p, sh.y + it.h + gapY)
      shelves.push(sh)
    }
    it.place(sh.p, sh.x, sh.y)
    sh.x += it.w + gapX
  }
  return made
}

// ---- 0. start ---------------------------------------------------------------------------------
// Lines wrap in a column, so they never overlap whatever the font. {{info}} is what
// @system.device getInfo reports (screen size, shape, density): a check that the kit was built
// for this model (photograph it once).
{
  const p = page('start', 'Vela calib: start')
  const lines = [
    [26, 'Vela calib ' + VERSION.name],
    [18, 'One photo per page: portrait, straight on, whole screen and both rulers in frame.'],
    [18, 'Tap / swipe left: next. Swipe down: previous. Swipe right: exit.'],
    [16, `Built for ${DEVICE} ${W}x${H}, designWidth ${W}`],
    [16, '{{info}}']
  ]
  const kids = lines.map(([s, t], i) => el('text', { width: px(AW), 'font-size': px(s), color: i === 4 ? C.yellow : C.white, 'font-weight': 'bold', 'margin-bottom': '8px', 'flex-shrink': 0 }, { text: t }))
  p.els.push(el('div', abs(AREA.x0, AREA.y0, AW, AH, { 'flex-direction': 'column' }), { kids }))
}

// ---- 1. text vertical metrics ---------------------------------------------------------------
// Each string in three boxes: natural (no height, cyan), tall (explicit 1.5 em, pink) and short
// (explicit 0.9 em, green). Every box is wider than its string (worst case), so natural boxes never
// wrap and explicit ones measure the plain regime. Two extra pink boxes ("8H" cut after the H's
// middle) measure the "string wider than its box" regime on purpose (too_wide).
{
  // Sizes whose "8" box takes at most 80 % of the area's width and whose 1.5 em box fits its height
  // (212 px capsule: up to 140 px; Band 10 Pro: up to 240 px)
  const SIZES = [24, 32, 48, 72, 96, 140, 180, 240].filter((s) => worstW('8', s) + 4 <= 0.8 * AW && Math.round(1.5 * s) <= AH)
  const strOf = (s) => (s <= 96 && worstW('Hg8', s) + 4 <= AW ? 'Hg8' : '8')
  const items = []
  const place = (str, s, regime, w, boxH, slotH, extra = {}) => (p, x, y) => {
    const css = abs(x, y, w, boxH, {
      'font-size': px(s), 'font-weight': 'bold', color: C.white,
      'border-width': '1px', 'border-color': REGIME_COLOUR[regime]
    })
    p.els.push(txt(css, str))
    sample(p, Object.assign({
      type: 'text_v', str, px: s, regime, weight: 'bold', outline: regime === 'nat' ? 'cyan' : regime === 'tall' ? 'pink' : 'green',
      box: { x, y, w, h: boxH === undefined ? null : boxH }, slot: { x, y, w, h: slotH },
      height_css: boxH === undefined ? 'auto' : boxH, border: 1
    }, extra))
  }
  for (const s of SIZES) {
    for (const regime of ['nat', 'tall', 'short']) {
      const str = strOf(s)
      const w = worstW(str, s) + 4
      const boxH = regime === 'tall' ? Math.round(1.5 * s) : regime === 'short' ? Math.round(0.9 * s) : undefined
      const slotH = boxH === undefined ? lineSlot(s) : boxH
      items.push({ key: `${s}-${regime}`, w, h: slotH, place: place(str, s, regime, w, boxH, slotH) })
    }
  }
  for (const s of [48, NARROW ? 72 : 96]) {
    // the "8" whole (even 15 % wider), the "H" cut near its middle (even 15 % narrower)
    const w = Math.ceil((G['8'] + 0.5 * G.H) * s) + 2
    const boxH = Math.round(1.5 * s)
    items.push({ key: `${s}-wide`, w, h: boxH, place: place('8H', s, 'tall', w, boxH, boxH, { too_wide: true }) })
  }
  pack(items, (i) => page(`tv${i + 1}`, `Text V ${i + 1}`, {
    notes: ['cyan: no height (natural line box)', 'pink: height 1.5 em', 'green: height 0.9 em', 'pink "8H": string wider than its box']
  }), AREA, 6, 6)
}

// ---- 2. text horizontal metrics (advance widths) ---------------------------------------------
// Each string sits in a flex row (no width), so its <text> box shrink-wraps: outer width = advance
// sum + 2 px border. Repeated glyphs ("0000") give per-glyph advances to 0.003 em. A string that
// can't fit the screen's width (worst case) is shown smaller (down to 20 px), repeated digits are
// halved ("0000" -> "00"), and anything still too wide is split at a space.
{
  const specs = []
  const DIG = worstW('0000', 48) + 6 <= AW ? 48 : 40 // four digits (+ worst-case slack) across the area (40 on the 164 px capsule area)
  for (let d = 0; d <= 9; d++) specs.push([String(d).repeat(4), DIG, 'bold'])
  specs.push(['0000', 24, 'bold'], ['0000', 96, 'bold'], ['8888', 32, 'bold'])
  // Generic strings; a spec can list its own (calib.quickapp.text_w_words: the Band 10 Pro adds BART Watch's)
  const WORDS = KIT.text_w_words || ['min', 'NOW', 'Checking…', '0 0 0 0', ':.,-/%']
  for (const w of WORDS) specs.push([w, 32, 'bold'])
  for (const w of ['abcdefghijklm', 'nopqrstuvwxyz', 'ABCDEFGHIJKLM', 'NOPQRSTUVWXYZ']) specs.push([w, 24, 'bold'])
  // Weight: the same strings in normal weight (does the band have a regular face at all?)
  specs.push(['0000', DIG, 'normal'], ['Hg8 min', 32, 'normal'], ['Hg8 min', 32, 'bold'])
  const ok = (s, p) => worstW(s, p) + 6 <= AW
  function fitW(str, p0, weight) {
    if (ok(str, p0)) return [[str, p0, weight]]
    if (str.length >= 2 && new Set(str).size === 1) return fitW(str.slice(0, Math.ceil(str.length / 2)), p0, weight)
    for (let p = p0 - 2; p >= 20; p -= 2) if (ok(str, p)) return [[str, p, weight]]
    const mid = (str.length - 1) / 2
    let cut = -1
    for (let i = 1; i < str.length - 1; i++) if (str[i] === ' ' && (cut < 0 || Math.abs(i - mid) < Math.abs(cut - mid))) cut = i
    const a = cut > 0 ? str.slice(0, cut) : str.slice(0, Math.ceil(str.length / 2))
    const b = cut > 0 ? str.slice(cut + 1) : str.slice(Math.ceil(str.length / 2))
    return [...fitW(a, p0, weight), ...fitW(b, p0, weight)]
  }
  const seen = new Set()
  const fitted = specs.flatMap(([s, p, w]) => fitW(s, p, w)).filter(([s, p, w]) => {
    const k = `${s}@${p}/${w}`
    if (seen.has(k)) return false
    seen.add(k)
    return true
  })
  const items = fitted.map(([str, s, weight]) => {
    const w = worstW(str, s) + 6
    const h = lineSlot(s)
    return {
      key: `${str}@${s}`, w, h,
      place(p, x, y) {
        p.els.push(el('div', abs(x, y, undefined, undefined, { 'flex-direction': 'row', 'align-items': 'flex-start' }), {
          kids: [txt({ 'font-size': px(s), 'font-weight': weight, color: C.white, 'border-width': '1px', 'border-color': C.pink, 'flex-shrink': 0 }, str)]
        }))
        sample(p, { type: 'text_w', str, px: s, weight, outline: 'pink', box: { x, y, w: null, h: null }, est_w: Math.ceil(em(str) * s), slot: { x, y, w, h }, border: 1 })
      }
    }
  })
  // A bare absolutely positioned <text> with no width: does it shrink-wrap or stretch? It gets a
  // whole shelf (the stretch hypothesis reaches the right edge).
  const bareH = lineSlot(32)
  items.push({
    key: 'bare', w: AW, h: bareH,
    place(p, x, y) {
      p.els.push(txt(abs(x, y, undefined, undefined, { 'font-size': '32px', 'font-weight': 'bold', color: C.white, 'border-width': '1px', 'border-color': C.cyan }), 'Hg8'))
      sample(p, {
        type: 'rect', what: 'absolute <text> with no width: box extent', metric: 'bbox', colour: 'cyan',
        region: [x - 2, y - 2, W - 1, y + bareH], slot: { x, y, w: AW, h: bareH },
        hyp: { shrink_wrap: [x, y, Math.ceil(em('Hg8') * 32) + 2, 44], stretch_to_right_edge: [x, y, W - x, 44] },
        fact: 'css.text_auto_width'
      })
    }
  })
  pack(items, (i) => page(`th${i + 1}`, `Text W ${i + 1}`, { notes: ['pink: flex-row wrapped <text>, no width'] }))
}

// ---- 3. wrapping, alignment, lines, ellipsis, line-height ---------------------------------------
// Slot heights come from a greedy word wrap of the string with worst-case widths, at 1.5 em per
// line (or the CSS line-height when larger), so a box that wraps into more lines than on the Band
// 10 Pro still stays inside its slot.
{
  const Q = 'The quick brown fox jumps over the dog'
  const BW = 136
  const specs = [
    { k: 'left', str: Q, s: 20, w: BW, css: { 'text-align': 'left' } },
    { k: 'center', str: Q, s: 20, w: BW, css: { 'text-align': 'center' } },
    { k: 'right', str: Q, s: 20, w: BW, css: { 'text-align': 'right' } },
    { k: 'lines2-ellipsis', str: Q, s: 20, w: BW, css: { lines: 2, 'text-overflow': 'ellipsis' } },
    { k: 'lines1-ellipsis', str: 'Embarcadero to Union City', s: 20, w: BW, css: { lines: 1, 'text-overflow': 'ellipsis' } },
    { k: 'lines2-clip', str: Q, s: 20, w: BW, css: { lines: 2 } },
    { k: 'height40', str: Q, s: 20, w: BW, h: 40, css: {} },
    { k: 'lineheight32', str: Q, s: 20, w: BW, css: { 'line-height': '32px' } },
    { k: 'longword', str: 'Embarcaderoembarcadero', s: 20, w: BW, css: {} },
    { k: 'lh48-at48', str: 'Hg8', s: 48, w: BW, css: { 'line-height': '48px' } },
    { k: 'lh72-at48', str: 'Hg8', s: 48, w: BW, css: { 'line-height': '72px' } },
    { k: 'lh40-at48-h48', str: 'Hg8', s: 48, w: BW, h: 48, css: { 'line-height': '40px' } }
  ]
  // Worst-case line count: greedy word wrap, letters broken inside a word longer than the line.
  function worstLines(str, s, inner) {
    const cw = (t) => em(t) * s * SLACK_W + [...t].length
    let lines = 1
    let cur = 0
    for (const word of str.split(' ')) {
      let ww = cw(word)
      if (cur > 0 && cur + cw(' ') + ww <= inner) { cur += cw(' ') + ww; continue }
      if (cur > 0) { lines++; cur = 0 }
      while (ww > inner) { lines++; ww -= inner }
      cur = ww
    }
    return lines
  }
  const items = specs.map((sp) => {
    const lh = Math.max(sp.css['line-height'] ? parseInt(sp.css['line-height'], 10) : 0, SLACK_LINE * sp.s)
    const lines = Math.min(sp.css.lines || 99, worstLines(sp.str, sp.s, sp.w - 2))
    const slotH = Math.ceil(Math.max(sp.h || 0, lines * lh)) + 4
    return {
      key: sp.k, w: sp.w, h: slotH,
      place(p, x, y) {
        const css = abs(x, y, sp.w, sp.h, Object.assign({ 'font-size': px(sp.s), 'font-weight': 'bold', color: C.white, 'border-width': '1px', 'border-color': C.pink }, sp.css))
        p.els.push(txt(css, sp.str))
        sample(p, { type: 'wrap', key: sp.k, str: sp.str, px: sp.s, css: sp.css, outline: 'pink', box: { x, y, w: sp.w, h: sp.h || null }, slot: { x, y, w: sp.w, h: slotH }, border: 1 })
      }
    }
  })
  // "min" beside a big number: flex row, align-items flex-end (bottom of the line boxes) and baseline
  const rowH = lineSlot(96)
  const rowW = Math.min(150, AW) // "5" at 96 px + "min" at 32 px is ~100 px; 150 unless the area is narrower
  for (const ai of ['flex-end', 'baseline']) {
    items.push({
      key: 'row-' + ai, w: rowW, h: rowH,
      place(p, x, y) {
        p.els.push(el('div', abs(x, y, undefined, undefined, { 'flex-direction': 'row', 'align-items': ai }), {
          kids: [
            txt({ 'font-size': '96px', 'font-weight': 'bold', color: C.white, 'border-width': '1px', 'border-color': C.cyan }, '5'),
            txt({ 'font-size': '32px', 'font-weight': 'bold', color: C.white, 'border-width': '1px', 'border-color': C.pink }, 'min')
          ]
        }))
        sample(p, { type: 'row', key: 'row-' + ai, align: ai, region: [x - 2, y - 2, x + rowW, y + rowH], slot: { x, y, w: rowW, h: rowH }, big: { str: '5', px: 96, outline: 'cyan' }, small: { str: 'min', px: 32, outline: 'pink' } })
      }
    })
  }
  pack(items, (i) => page(`tw${i + 1}`, `Wrap ${i + 1}`, { notes: [`pink: ${BW} px wide boxes at 20 px`] }))
}

// ---- 4. box model ------------------------------------------------------------------------------
// Each test in its own 80 x 96 slot (everything it draws, under every hypothesis, stays inside);
// hypotheses are band px [x, y, w, h] of the measured colour.
{
  const S = { w: 80, h: 96 }
  const T = []
  const add = (key, what, fact, build) => T.push({ key, what, fact, build })
  const W_ = C.white
  const slotRegion = (x, y) => [x, y, x + S.w, y + S.h]

  add('padding', 'padding 10 inside a 1 px pink box: where the white child lands', 'css.padding', (x, y) => ({
    els: [el('div', abs(x + 4, y + 4, 72, 60, { 'border-width': '1px', 'border-color': C.pink, padding: '10px' }), { kids: [el('div', { width: '20px', height: '20px', 'background-color': W_ }) ] })],
    m: { metric: 'bbox', colour: 'white', region: slotRegion(x, y), hyp: { honoured: [x + 15, y + 15, 20, 20], ignored: [x + 5, y + 5, 20, 20] } }
  }))
  add('box-sizing', 'width 50 + padding 10 + border 1: outer width of the pink box', 'css.box_sizing', (x, y) => ({
    els: [el('div', abs(x + 4, y + 4, 50, 40, { 'border-width': '1px', 'border-color': C.pink, padding: '10px' }))],
    m: { metric: 'bbox', colour: 'pink', region: slotRegion(x, y), hyp: { border_box: [x + 4, y + 4, 50, 40], content_box: [x + 4, y + 4, 72, 62] } }
  }))
  add('margin', 'column: cyan has margin-top 12 under a 40 x 10 white bar', 'css.margin', (x, y) => ({
    els: [el('div', abs(x + 4, y + 4, 72, 80, { 'flex-direction': 'column' }), { kids: [
      el('div', { width: '40px', height: '10px', 'background-color': W_, 'flex-shrink': 0 }),
      el('div', { width: '40px', height: '10px', 'background-color': C.cyan, 'margin-top': '12px', 'flex-shrink': 0 })] })],
    m: { metric: 'bbox', colour: 'cyan', region: slotRegion(x, y), hyp: { honoured: [x + 4, y + 26, 40, 10], ignored: [x + 4, y + 14, 40, 10] } }
  }))
  add('neg-margin-top', 'column: cyan has margin-top -8 under a 40 x 20 white bar', 'css.negative_margin', (x, y) => ({
    els: [el('div', abs(x + 4, y + 20, 72, 60, { 'flex-direction': 'column' }), { kids: [
      el('div', { width: '40px', height: '20px', 'background-color': W_, 'flex-shrink': 0 }),
      el('div', { width: '40px', height: '10px', 'background-color': C.cyan, 'margin-top': '-8px', 'flex-shrink': 0 })] })],
    m: { metric: 'bbox', colour: 'cyan', region: slotRegion(x, y), hyp: { honoured: [x + 4, y + 32, 40, 10], ignored: [x + 4, y + 40, 40, 10] } }
  }))
  add('neg-margin-left', 'row: cyan has margin-left -10 after a 30 x 20 white box', 'css.negative_margin_left', (x, y) => ({
    els: [el('div', abs(x + 4, y + 20, 72, 30, { 'flex-direction': 'row' }), { kids: [
      el('div', { width: '30px', height: '20px', 'background-color': W_, 'flex-shrink': 0 }),
      el('div', { width: '30px', height: '20px', 'background-color': C.cyan, 'margin-left': '-10px', 'flex-shrink': 0 })] })],
    m: { metric: 'bbox', colour: 'cyan', region: slotRegion(x, y), hyp: { honoured: [x + 24, y + 20, 30, 20], ignored: [x + 34, y + 20, 30, 20] } }
  }))
  add('abs-in-parent', 'green 10 x 10, absolute left/top 20 inside a pink box at +10: parent- or page-relative', 'css.absolute_origin', (x, y) => ({
    els: [el('div', abs(x + 10, y + 10, 60, 60, { 'border-width': '1px', 'border-color': C.pink }), { kids: [fill(20, 20, 10, 10, C.green)] })],
    m: { metric: 'bbox', colour: 'green', region: [0, 0, W, H], hyp: { parent_border_box: [x + 30, y + 30, 10, 10], parent_content_box: [x + 31, y + 31, 10, 10], page: [20, 20, 10, 10] } }
  }))
  for (const bw of [1, 2, 4, 8]) {
    add('border' + bw, `border-width ${bw}, white, 60 x 50 box: drawn thickness`, 'css.border_width', (x, y) => ({
      els: [el('div', abs(x + 10, y + 20, 60, 50, { 'border-width': bw + 'px', 'border-color': W_ }))],
      m: { metric: 'ring', colour: 'white', region: [x + 4, y + 14, x + 76, y + 76], hyp: { honoured: { l: bw, t: bw, r: bw, b: bw } } }
    }))
  }
  add('border-left-width', 'border 1 + border-left-width 8', 'css.border_side_width', (x, y) => ({
    els: [el('div', abs(x + 10, y + 20, 60, 50, { 'border-width': '1px', 'border-left-width': '8px', 'border-color': W_ }))],
    m: { metric: 'ring', colour: 'white', region: [x + 4, y + 14, x + 76, y + 76], hyp: { honoured: { l: 8, t: 1, r: 1, b: 1 }, ignored: { l: 1, t: 1, r: 1, b: 1 } } }
  }))
  add('border-left-color', 'border 4 white + border-left-color pink', 'css.border_side_colour', (x, y) => ({
    els: [el('div', abs(x + 10, y + 20, 60, 50, { 'border-width': '4px', 'border-color': W_, 'border-left-color': C.pink }))],
    m: { metric: 'colour_at', points: { left: [x + 12, y + 45], top: [x + 40, y + 22] }, hyp: { honoured: { left: 'pink', top: 'white' }, ignored: { left: 'white', top: 'white' } } }
  }))
  add('radius', 'border-radius 20 on a 64 x 56 white fill', 'css.border_radius', (x, y) => ({
    els: [fill(x + 8, y + 20, 64, 56, W_, { 'border-radius': '20px' })],
    m: { metric: 'corners', colour: 'white', region: [x + 2, y + 14, x + 78, y + 82], hyp: { honoured: { tl: 20, tr: 20, br: 20, bl: 20 }, ignored: { tl: 0, tr: 0, br: 0, bl: 0 } } }
  }))
  add('radius-tl', 'border-top-left-radius 24 only', 'css.border_radius_per_corner', (x, y) => ({
    els: [fill(x + 8, y + 20, 64, 56, W_, { 'border-top-left-radius': '24px' })],
    m: { metric: 'corners', colour: 'white', region: [x + 2, y + 14, x + 78, y + 82], hyp: { honoured: { tl: 24, tr: 0, br: 0, bl: 0 }, ignored: { tl: 0, tr: 0, br: 0, bl: 0 }, all_corners: { tl: 24, tr: 24, br: 24, bl: 24 } } }
  }))
  add('radius-override', 'border-radius 20 then border-top-left-radius 0', 'css.border_radius_per_corner_override', (x, y) => ({
    els: [fill(x + 8, y + 20, 64, 56, W_, { 'border-radius': '20px', 'border-top-left-radius': '0px' })],
    m: { metric: 'corners', colour: 'white', region: [x + 2, y + 14, x + 78, y + 82], hyp: { honoured: { tl: 0, tr: 20, br: 20, bl: 20 }, ignored: { tl: 20, tr: 20, br: 20, bl: 20 }, all_zero: { tl: 0, tr: 0, br: 0, bl: 0 } } }
  }))
  add('radius-ring', 'border 3 white + border-radius 16, no fill', 'css.border_radius_outline', (x, y) => ({
    els: [el('div', abs(x + 8, y + 20, 64, 56, { 'border-width': '3px', 'border-color': W_, 'border-radius': '16px' }))],
    m: { metric: 'corners', colour: 'white', region: [x + 2, y + 14, x + 78, y + 82], hyp: { honoured: { tl: 16, tr: 16, br: 16, bl: 16 }, ignored: { tl: 0, tr: 0, br: 0, bl: 0 } } }
  }))
  add('pill', 'border-radius 999 on 64 x 32: clamped to 16?', 'css.border_radius_clamp', (x, y) => ({
    els: [fill(x + 8, y + 32, 64, 32, W_, { 'border-radius': '999px' })],
    m: { metric: 'corners', colour: 'white', region: [x + 2, y + 26, x + 78, y + 70], hyp: { clamped: { tl: 16, tr: 16, br: 16, bl: 16 }, square: { tl: 0, tr: 0, br: 0, bl: 0 } } }
  }))
  // Overflow: the 70 px child is ABSOLUTE (left/top 1), so flex shrinking can't narrow it (kit 1.0.0's
  // flex child left "clips" and "child shrunk" indistinguishable).
  add('overflow-hidden', 'overflow hidden 40 x 40 box, absolute child 70 wide', 'css.overflow_hidden', (x, y) => ({
    els: [el('div', abs(x + 4, y + 24, 40, 40, { 'border-width': '1px', 'border-color': C.pink, overflow: 'hidden' }), { kids: [fill(1, 1, 70, 20, W_)] })],
    m: { metric: 'bbox', colour: 'white', region: slotRegion(x, y), hyp: { clips_at_padding_box: [x + 5, y + 25, 38, 20], no_clip: [x + 5, y + 25, 70, 20] } }
  }))
  add('overflow-visible', 'default overflow, 40 x 40 box, absolute child 70 wide', 'css.overflow_visible', (x, y) => ({
    els: [el('div', abs(x + 4, y + 24, 40, 40, { 'border-width': '1px', 'border-color': C.pink }), { kids: [fill(1, 1, 70, 20, W_)] })],
    m: { metric: 'bbox', colour: 'white', region: slotRegion(x, y), hyp: { clips: [x + 5, y + 25, 38, 20], draws_outside: [x + 5, y + 25, 70, 20] } }
  }))
  add('flex-shrink', 'row 72 wide: white 44 (flex-shrink 0) + cyan 44 (flex-shrink 1): where the cyan lands', 'css.flex_shrink_zero', (x, y) => ({
    els: [el('div', abs(x + 4, y + 30, 72, 20, { 'flex-direction': 'row', overflow: 'hidden' }), { kids: [
      el('div', { width: '44px', height: '20px', 'background-color': W_, 'flex-shrink': 0 }),
      el('div', { width: '44px', height: '20px', 'background-color': C.cyan, 'flex-shrink': 1 })] })],
    m: { metric: 'bbox', colour: 'cyan', region: slotRegion(x, y), hyp: { honoured: [x + 48, y + 30, 28, 20], ignored: [x + 40, y + 30, 36, 20] } }
  }))
  add('overflow-radius', 'overflow hidden + radius 20: is a full-size child clipped round?', 'css.overflow_radius_clip', (x, y) => ({
    els: [el('div', abs(x + 10, y + 18, 60, 60, { 'border-radius': '20px', overflow: 'hidden' }), { kids: [el('div', { width: '60px', height: '60px', 'background-color': W_, 'flex-shrink': 0 })] })],
    m: { metric: 'corners', colour: 'white', region: [x + 4, y + 12, x + 76, y + 84], hyp: { round_clip: { tl: 20, tr: 20, br: 20, bl: 20 }, square_clip: { tl: 0, tr: 0, br: 0, bl: 0 } } }
  }))
  add('opacity', 'white fill at opacity 0.5 beside a #808080 fill', 'css.opacity', (x, y) => ({
    els: [fill(x + 6, y + 20, 32, 56, W_, { opacity: 0.5 }), fill(x + 42, y + 20, 32, 56, '#808080')],
    m: { metric: 'luma_pair', a: [x + 10, y + 26, x + 34, y + 70], b: [x + 46, y + 26, x + 70, y + 70], hyp: { honoured: { ratio: 1.0 }, ignored_full: { ratio: 2.0 }, invisible: { ratio: 0 } } }
  }))
  add('z-index', 'white z-index 2 drawn before cyan z-index 1, overlapping', 'css.z_index', (x, y) => ({
    els: [fill(x + 6, y + 20, 44, 44, W_, { 'z-index': 2 }), fill(x + 30, y + 40, 44, 44, C.cyan, { 'z-index': 1 })],
    m: { metric: 'colour_at', points: { overlap: [x + 40, y + 52] }, hyp: { honoured: { overlap: 'white' }, ignored: { overlap: 'cyan' } } }
  }))
  add('translate', 'static transform translateX(20px) on a 20 x 20 white square at +10', 'css.transform_translate', (x, y) => ({
    els: [fill(x + 10, y + 38, 20, 20, W_, { transform: 'translateX(20px)' })],
    m: { metric: 'bbox', colour: 'white', region: slotRegion(x, y), hyp: { honoured: [x + 30, y + 38, 20, 20], ignored: [x + 10, y + 38, 20, 20] } }
  }))
  add('rotate', 'static rotate(45deg) on a 56 x 4 bar', 'css.transform_rotate', (x, y) => ({
    els: [fill(x + 12, y + 46, 56, 4, W_, { transform: 'rotate(45deg)' })],
    m: { metric: 'bbox', colour: 'white', region: slotRegion(x, y), hyp: { honoured: [x + 19, y + 27, 42, 42], ignored: [x + 12, y + 46, 56, 4] } }
  }))
  add('percent-width', 'child width 50% of a 72 px parent', 'css.percent_width', (x, y) => ({
    els: [el('div', abs(x + 4, y + 30, 72, 30), { kids: [el('div', { width: '50%', height: '20px', 'background-color': W_ })] })],
    m: { metric: 'bbox', colour: 'white', region: slotRegion(x, y), hyp: { honoured: [x + 4, y + 30, 36, 20], ignored_full: [x + 4, y + 30, 72, 20] } }
  }))
  add('justify-center', 'row, justify-content center, 20 px child in 72', 'css.justify_content', (x, y) => ({
    els: [el('div', abs(x + 4, y + 30, 72, 30, { 'flex-direction': 'row', 'justify-content': 'center' }), { kids: [el('div', { width: '20px', height: '20px', 'background-color': W_, 'flex-shrink': 0 })] })],
    m: { metric: 'bbox', colour: 'white', region: slotRegion(x, y), hyp: { honoured: [x + 30, y + 30, 20, 20], ignored: [x + 4, y + 30, 20, 20] } }
  }))
  add('box-shadow', 'box-shadow 0 0 12px white on a 40 x 40 fill', 'css.box_shadow', (x, y) => ({
    els: [fill(x + 20, y + 28, 40, 40, W_, { 'box-shadow': '0px 0px 12px #ffffff' })],
    m: { metric: 'luma_pair', a: [x + 10, y + 40, x + 16, y + 56], b: [x + 26, y + 40, x + 54, y + 56], hyp: { honoured: { ratio: 0.3 }, ignored: { ratio: 0 } } }
  }))
  add('text-bg', 'text with background-color #505050 and radius 12 (a pill label)', 'css.text_background', (x, y) => ({
    els: [txt(abs(x + 4, y + 30, 72, 36, { 'font-size': '24px', 'font-weight': 'bold', color: W_, 'background-color': C.dim, 'border-radius': '12px', 'text-align': 'center' }), 'ON')],
    m: { metric: 'corners', colour: 'any', region: [x, y + 24, x + S.w, y + 72], hyp: { honoured: { tl: 12, tr: 12, br: 12, bl: 12 }, square: { tl: 0, tr: 0, br: 0, bl: 0 } } }
  }))

  // keep the declared order (not by height): all slots are the same size
  // 8 px gaps unless 4 px fits one more column (the 164 px capsule area: 2 columns instead of 1)
  const gx = Math.floor((AW + 8) / (S.w + 8)) === Math.floor((AW + 4) / (S.w + 4)) ? 8 : 4
  const gy = 6
  const cols = Math.floor((AW + gx) / (S.w + gx))
  const rows = Math.floor((AH + gy) / (S.h + gy))
  const perPage = cols * rows
  const made = []
  T.forEach((t, i) => {
    const k = i % perPage
    if (k === 0) made.push(page(`bx${made.length + 1}`, `Box ${made.length + 1}`))
    const p = made[made.length - 1]
    const x = AREA.x0 + (k % cols) * (S.w + gx)
    const y = AREA.y0 + Math.floor(k / cols) * (S.h + gy)
    const r = t.build(x, y)
    p.els.push(...r.els)
    sample(p, Object.assign({ type: 'rect', key: t.key, what: t.what, fact: t.fact, slot: { x, y, w: S.w, h: S.h } }, r.m))
  })
}

// ---- 5. screen geometry ---------------------------------------------------------------------
// Rounded rectangle (Band 10 Pro): white K x K squares in the four corners (the display's rounded
// mask cuts them; K = 48, or 1.2 x a larger corner radius) and a comb of 1 px lines from the top
// and bottom edges (hidden rows).
// Capsule (Band 10 / 11): a white cap over each end, full width and taller than the end radius:
// its visible outline is the screen's arc (radius, centre: which gives the hidden top / bottom rows
// and the design-px -> panel-px scale) and, in its straight rows, the hidden left / right columns.
// Circle: white caps all round the outside of the rulers (top, bottom, left, right boxes); the lit
// outline is the whole circle, fitted for radius, centre (hidden rows and columns) and design scale.
// Rect and capsule: the rulers' outer tick ends (on every page) show the hidden columns too. The bar
// and barcode move to the middle here (measure.py tries every bar position the layout lists).
{
  const gBar = { x: CAPSULE ? BAR.x : Math.round((W - BAR.len) / 2), y: Math.round(H / 2) - 2, len: BAR.len, h: BAR.h }
  const gCode = Object.assign({}, CODE, { x: CAPSULE ? CODE.x : CIRCLE ? CODE.x : gBar.x, y: gBar.y + 14 })
  if (D.shape === 'rect') {
    const K = D.cornerR <= 48 ? 48 : Math.ceil(1.2 * D.cornerR)
    const p = page('geo', 'Screen geometry', { bar: gBar, code: gCode, label: { x: K + 8, y: 26, w: W - 2 * K - 16, px: 16, align: 'left' } })
    const corners = { tl: [0, 0], tr: [W - K, 0], bl: [0, H - K], br: [W - K, H - K] }
    for (const [k, [x, y]] of Object.entries(corners)) {
      p.els.push(fill(x, y, K, K, C.white))
      sample(p, { type: 'corner', corner: k, box: { x, y, w: K, h: K } })
    }
    const xs = []
    for (let x = K + 12; x <= W - K - 12; x += 12) xs.push(x)
    for (const x of xs) p.els.push(fill(x, 0, 1, 20, C.white), fill(x, H - 20, 1, 20, C.white))
    sample(p, { type: 'comb', edge: 'top', xs, y0: 0, y1: 20 })
    sample(p, { type: 'comb', edge: 'bottom', xs, y0: H - 20, y1: H })
    p.els.push(txt(abs(40, gBar.y - 110, W - 80, undefined, { 'font-size': '20px', 'font-weight': 'bold', color: C.grey, 'text-align': 'center' }), 'Corners and edges. Note anything the system draws on top.'))
    p.els.push(txt(abs(40, gCode.y + 24, W - 80, undefined, { 'font-size': '16px', 'font-weight': 'bold', color: C.yellow, 'text-align': 'center' }), '{{info}}'))
    p.observe.push({ fact: 'screen.system_overlay', ask: 'Right after opening the app: does the band draw anything over the app (status dot, time, indicator)? Where?' })
  } else if (CAPSULE) {
    const K = D.endR + 9 // taller than the end radius: the last rows are the straight sides
    const p = page('geo', 'Screen geometry', { bar: gBar, code: gCode, label: { x: LABEL.x, y: K + 6, w: LABEL.w, px: 16, align: 'center' } })
    p.els.push(fill(0, 0, W, K, C.white))
    sample(p, { type: 'cap', end: 'top', box: { x: 0, y: 0, w: W, h: K } })
    p.els.push(fill(0, H - K, W, K, C.white))
    sample(p, { type: 'cap', end: 'bottom', box: { x: 0, y: H - K, w: W, h: K } })
    p.els.push(txt(abs(AREA.x0, K + 34, AW, undefined, { 'font-size': '16px', 'font-weight': 'bold', color: C.grey, 'text-align': 'center' }), 'Capsule ends and edges. Note anything the system draws on top.'))
    p.els.push(txt(abs(AREA.x0, gCode.y + 22, AW, undefined, { 'font-size': '16px', 'font-weight': 'bold', color: C.yellow, 'text-align': 'center' }), '{{info}}'))
    p.observe.push({ fact: 'screen.system_overlay', ask: 'Right after opening the app: does the band draw anything over the app (status dot, time, indicator)? Where?' })
  } else {
    // 8 px of black between the caps and the ruler ticks, so the fit still finds every tick
    const yT = RULER.y0 - 8
    const yB = RULER.y0 + (RULER.n - 1) * TICK_EVERY + 1 + 8
    const boxes = [[0, 0, W, yT], [0, yB, W, H - yB], [0, yT, RULER.left_x - 6, yB - yT], [RULER.right_x + 6, yT, W - RULER.right_x - 6, yB - yT]]
    const p = page('geo', 'Screen geometry', { bar: gBar, code: gCode, label: { x: AREA.x0, y: yT + 6, w: AW, px: 16, align: 'center' } })
    for (const [x, y, w, h] of boxes) p.els.push(fill(x, y, w, h, C.white))
    sample(p, { type: 'round', boxes, expect: { cx: W / 2, cy: H / 2, r: D.radius } })
    p.els.push(txt(abs(AREA.x0, gBar.y - 70, AW, undefined, { 'font-size': '16px', 'font-weight': 'bold', color: C.grey, 'text-align': 'center' }), 'Round edge. Note anything the system draws on top.'))
    p.els.push(txt(abs(AREA.x0, gCode.y + 22, AW, undefined, { 'font-size': '16px', 'font-weight': 'bold', color: C.yellow, 'text-align': 'center' }), '{{info}}'))
    p.observe.push({ fact: 'screen.system_overlay', ask: 'Right after opening the app: does the band draw anything over the app (status dot, time, indicator)? Where?' })
  }
}

// ---- 6. colour ---------------------------------------------------------------------------------
{
  const p = page('colour', 'Colour floor')
  let y = AREA.y0
  const greys = Array.from({ length: 13 }, (_, i) => i * 8) // 0x00 .. 0x60
  const row = (vals, hexOf, h, tag) => {
    const n = vals.length
    const w = Math.floor((AW + 4) / n) - 4
    vals.forEach((v, i) => {
      const x = AREA.x0 + i * (w + 4)
      const hex = hexOf(v)
      p.els.push(fill(x, y, w, h, hex))
      sample(p, { type: 'swatch', group: tag, hex, value: v, box: { x, y, w, h }, slot: { x, y, w, h } })
    })
    y += h + 8
  }
  const hx = (v) => v.toString(16).padStart(2, '0')
  row(greys, (v) => '#' + hx(v).repeat(3), 40, 'grey')
  const ramp = [0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80]
  row(ramp, (v) => '#' + hx(v) + '0000', 30, 'red')
  row(ramp, (v) => '#00' + hx(v) + '00', 30, 'green')
  row(ramp, (v) => '#0000' + hx(v), 30, 'blue')
  row([0x20, 0x28, 0x30, 0x38, 0x40, 0x48], (v) => '#' + hx(v).repeat(3), 56, 'surface')
  const brand = ['#ffd60a', '#ff2d95', '#00e5ff', '#3cff3c', '#ff0000', '#0099cc', '#ff9933', '#339933', '#0a84ff', '#c8c8c8', '#808080', '#ffffff']
  row(brand.map((_, i) => i), (i) => brand[i], 36, 'brand')
  // An empty black area for the background level
  const bgY = y + 4
  const bg = { x: AREA.x0 + 20, y: bgY, w: AW - 40, h: Math.max(10, AREA.y1 - bgY - 4) }
  sample(p, { type: 'background', box: bg, slot: bg })
}

// ---- 7. images ------------------------------------------------------------------------------------
// Each image gets a slot as big as its largest hypothesis (+3 px): packed over as many pages as the
// screen needs (one on the Band 10 Pro).
{
  const img = (src, x, y, w, h, extra = {}) => el('image', Object.assign(abs(x, y, w, h), extra), { attrs: { src: '/common/img/' + src } })
  const list = [
    // [key, src, w, h, extra css, hypotheses of the drawn bbox]
    ['natural', 'checker32.png', undefined, undefined, {}, (x, y) => ({ natural: [x, y, 32, 32] })],
    ['x2', 'checker32.png', 64, 64, {}, (x, y) => ({ scaled: [x, y, 64, 64], natural_top_left: [x, y, 32, 32], natural_centred: [x + 16, y + 16, 32, 32] })],
    ['x1.5', 'checker32.png', 48, 48, {}, (x, y) => ({ scaled: [x, y, 48, 48], natural_top_left: [x, y, 32, 32], natural_centred: [x + 8, y + 8, 32, 32] })],
    ['x0.5', 'checker32.png', 16, 16, {}, (x, y) => ({ scaled: [x, y, 16, 16], cropped: [x, y, 16, 16] })],
    ['stretch', 'checker32.png', 64, 32, {}, (x, y) => ({ stretched: [x, y, 64, 32], natural_top_left: [x, y, 32, 32], contain_centred: [x + 16, y, 32, 32] })],
    ['png8', 'checker32_p8.png', 32, 32, {}, (x, y) => ({ drawn: [x, y, 32, 32], missing: [0, 0, 0, 0] })],
    ['grey8', 'checker32_l.png', 32, 32, {}, (x, y) => ({ drawn: [x, y, 32, 32], missing: [0, 0, 0, 0] })],
    ['disc', 'disc64.png', 64, 64, {}, (x, y) => ({ drawn: [x + 2, y + 2, 60, 60] })],
    ['disc-p8', 'disc64_p8.png', 64, 64, {}, (x, y) => ({ drawn: [x + 2, y + 2, 60, 60], missing: [0, 0, 0, 0] })],
    ['disc-hard', 'disc64_hard.png', 64, 64, {}, (x, y) => ({ drawn: [x + 2, y + 2, 60, 60] })],
    ['fit-fill', 'wide64x32.png', 64, 64, { 'object-fit': 'fill' }, (x, y) => ({ fill: [x, y, 64, 64], contain: [x, y + 16, 64, 32], none_top_left: [x, y, 64, 32] })],
    ['fit-contain', 'wide64x32.png', 64, 64, { 'object-fit': 'contain' }, (x, y) => ({ fill: [x, y, 64, 64], contain: [x, y + 16, 64, 32], none_top_left: [x, y, 64, 32] })],
    // wide64x32_q: black with one white column block at source x 16-31. Stretched (fill) it lands
    // at +16, 16 wide; cover (scaled 2x, centre 32 columns kept) at +0, 32 wide; contain at +16, 16 x 32.
    ['fit-cover', 'wide64x32_q.png', 64, 64, { 'object-fit': 'cover' }, (x, y) => ({ cover: [x, y, 32, 64], fill: [x + 16, y, 16, 64], contain: [x + 16, y + 16, 16, 32] })],
    ['fit-none', 'wide64x32.png', 64, 64, { 'object-fit': 'none' }, (x, y) => ({ fill: [x, y, 64, 64], contain: [x, y + 16, 64, 32], none_top_left: [x, y, 64, 32] })]
  ]
  const items = list.map(([key, src, w, h, extra, hyp]) => {
    const bw = Math.max(w || 32, 64)
    const bh = Math.max(h || 32, 32)
    return {
      key, w: bw + 6, h: bh + 6,
      place(p, x, y) {
        const ix = x + 3
        const iy = y + 3
        p.els.push(img(src, ix, iy, w, h, extra))
        sample(p, { type: 'rect', key, what: `image ${src} in ${w || 'auto'} x ${h || 'auto'} ${JSON.stringify(extra)}`, fact: 'image.' + key, metric: 'bbox', colour: 'any', region: [x, y, x + bw + 6, y + bh + 6], slot: { x, y, w: bw + 6, h: bh + 6 }, hyp: hyp(ix, iy), src })
      }
    }
  })
  // alpha ramp (white, alpha 0..255) above the same ramp as opaque greys: compare column by column
  const RW = AW >= 256 ? 256 : 128
  items.push({
    key: 'ramp', w: RW, h: 38,
    place(p, x, y) {
      p.els.push(img('alpha_ramp.png', x, y, RW, 16))
      p.els.push(img('grey_ramp.png', x, y + 22, RW, 16))
      sample(p, { type: 'ramp', key: 'alpha-vs-grey', a: { x, y, w: RW, h: 16 }, b: { x, y: y + 22, w: RW, h: 16 }, slot: { x, y, w: RW, h: 38 }, fact: 'image.alpha_blend' })
    }
  })
  pack(items, (i) => page(i === 0 ? 'img' : `img${i + 1}`, i === 0 ? 'Images' : `Images ${i + 1}`), AREA, 4, 6)
}

// ---- 8. animation (observation page) ---------------------------------------------------------
// Lanes of 24 px squares, 8 s per run. Every lane that can shows a FINISH MARKER: the square turns
// yellow (lane F, an image: dims) for the last 10 % of its path, so it only changes if the run gets
// there; a lane restarted every 3 s never does. A (control) must turn yellow, or the marker itself
// doesn't work on this band. The page re-renders every second (the counter).
const ANIM = {}
const LANE_W = AW - 24
const TRAVEL = LANE_W - 24 // square's travel in its lane
{
  const p = page('anim', 'Animation (watch it)')
  ANIM.page = p.id
  const lanes = [
    ['A', 'control: static class, 8 s run; turns yellow at the end', 'fin8', 'static'],
    ['B', 'class rebound every 3 s (k1/k2)', 'fin8', 'classSwap'],
    ['C', 'class has a {{binding}} that never changes; page re-renders every 1 s', 'fin8', 'classConst'],
    ['D', 'steps(4, end): four jumps in 8 s', 'st8', 'static'],
    ['E', 'translateX 0 to 600 px in 8 s (leaves the screen)', 'an600', 'static'],
    ['F', 'image, src swapped every 3 s (identical files); dims at the end', 'imgfin8', 'srcSwap'],
    ['G', 'opacity 0 to 1, alternate, 2 s', 'fade', 'static'],
    ['H', 'BART pattern: class reads a field of an object replaced every 1 s', 'fin8', 'objectField']
  ]
  let y = AREA.y0
  const laneH = Math.floor((AH - 30) / lanes.length)
  for (const [k, what, anim, mode] of lanes) {
    p.els.push(txt(abs(AREA.x0, y, 20, undefined, { 'font-size': '18px', 'font-weight': 'bold', color: C.yellow }), k))
    p.els.push(fill(AREA.x0 + 24, y + 12, LANE_W, 1, C.dim))
    // the last 10 % of the path, marked on the lane so the watcher knows where yellow should start
    p.els.push(fill(AREA.x0 + 24 + Math.round(0.9 * TRAVEL), y + 26, LANE_W - Math.round(0.9 * TRAVEL), 2, C.yellow))
    const laneBox = el('div', abs(AREA.x0 + 24, y, LANE_W, 24, { overflow: 'hidden' }), { kids: [] })
    let sq
    if (mode === 'srcSwap') sq = el('image', { width: '24px', height: '24px' }, { attrs: { src: '{{fSrc}}' }, rawClass: 'sqi ' + anim })
    else if (mode === 'classSwap') sq = el('div', null, { rawClass: `sq ${anim} {{bCls}}` })
    else if (mode === 'classConst') sq = el('div', null, { rawClass: `sq ${anim} {{cCls}}` })
    else if (mode === 'objectField') sq = el('div', null, { rawClass: `sq ${anim} {{hv.c}}` })
    else sq = el('div', null, { rawClass: 'sq ' + anim })
    laneBox.kids.push(sq)
    p.els.push(laneBox)
    p.observe.push({ fact: 'animation.lane_' + k, ask: `Lane ${k} (${what}): does it run to the right end (turning yellow) and loop, or jump back early (never yellow) / stop?` })
    y += laneH
  }
  p.els.push(el('text', abs(AREA.x0, y + 2, AW, undefined, { 'font-size': '16px', 'font-weight': 'bold', color: C.grey }), { text: 't = {{cnt}} s  (B, F: 3 s; H: 1 s)' }))
}

// ---- emit ------------------------------------------------------------------------------------
const cssClasses = new Map() // css text -> class name
function classFor(css) {
  if (!css) return null
  const body = Object.entries(css).map(([k, v]) => `  ${k}: ${typeof v === 'number' && !['opacity', 'lines', 'z-index', 'flex-shrink', 'flex-grow'].includes(k) ? v + 'px' : v};`).join('\n')
  if (!cssClasses.has(body)) cssClasses.set(body, 'c' + cssClasses.size)
  return cssClasses.get(body)
}
function emit(e, ind) {
  const cls = [e.rawClass, classFor(e.css)].filter(Boolean).join(' ')
  const attrs = Object.entries(e.attrs).map(([k, v]) => ` ${k}="${v}"`).join('')
  const open = `${ind}<${e.tag}${cls ? ` class="${cls}"` : ''}${attrs}`
  if (e.tag === 'text') return `${open}>${escapeText(e.text)}</text>`
  if (!e.kids.length) return `${open}></${e.tag}>`
  return `${open}>\n${e.kids.map((k) => emit(k, ind + '  ')).join('\n')}\n${ind}</${e.tag}>`
}
function escapeText(t) { return String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }

function barcodeBits(id) {
  const bits = [1]
  for (let b = 4; b >= 0; b--) bits.push((id >> b) & 1)
  bits.push(bits.slice(1).reduce((a, v) => a ^ v, 0))
  bits.push(1)
  return bits
}

if (pages.length > 32) throw new Error(`${pages.length} pages: the barcode holds 5 bits (32 pages)`)
let blocks = ''
for (const p of pages) {
  const frameEls = []
  const lb = p.label
  const cd = p.code
  frameEls.push(txt(abs(lb.x, lb.y, lb.w, undefined, { 'font-size': px(lb.px), 'font-weight': 'bold', color: C.grey, lines: 1, 'text-align': lb.align }), `${String(p.id).padStart(2, '0')} ${p.title}`))
  barcodeBits(p.id).forEach((b, i) => { if (b) frameEls.push(fill(cd.x + i * cd.pitch, cd.y, cd.cell, cd.h, C.white)) })
  frameEls.push(fill(p.bar.x, p.bar.y, p.bar.len, p.bar.h, C.yellow))
  const body = [...p.els, ...frameEls].map((e) => emit(e, '      ')).join('\n')
  blocks += `    <div if="{{pg === ${p.id}}}" class="pg">\n${body}\n    </div>\n`
}

const f2 = (v) => Math.round(v) // whole px in keyframes
const RULER_H = CIRCLE ? RULER.n * TICK_EVERY : H
const ux = `<template>
  <!-- GENERATED by tools/vela-calib/gen/gen.mjs for ${DEVICE} (${W} x ${H}, ${D.shape}). Do not edit by hand.
       ${pages.length} full-screen test pages. Tap or swipe left/up: next page; swipe down: previous;
       swipe right (or back): exit. Rulers: a 1 px tick every 10 px down both edges (tick top = y),
       14 px long every 50, 22 px and yellow every 100. Yellow bar: exactly ${BAR.len} x ${BAR.h} px at
       (${BAR.x}, ${BAR.y}) (geometry page: mid-screen). Barcode: on, 5 bits of the page number,
       even parity, on.
       Only the animation page binds anything that changes (its classes are static except the
       lanes that test rebinding). -->
  <div class="root" @swipe="onSwipe" @touchstart="onTouchStart" @touchend="onTouchEnd" @touchcancel="onTouchCancel">
    <div class="rl">
      <div for="{{tk}}" class="rc">
        <div if="{{$item === 2}}" class="k k100"></div>
        <div elif="{{$item === 1}}" class="k k50"></div>
        <div else class="k"></div>
      </div>
    </div>
    <div class="rr">
      <div for="{{tk}}" class="rc rcr">
        <div if="{{$item === 2}}" class="k k100"></div>
        <div elif="{{$item === 1}}" class="k k50"></div>
        <div else class="k"></div>
      </div>
    </div>
${blocks}  </div>
</template>

<script>
import app from '@system.app'
import router from '@system.router'
import brightness from '@system.brightness'
import device from '@system.device'

const PAGES = ${pages.length}
const ANIM_PAGE = ${ANIM.page}
const TICKS = ${JSON.stringify(TICKS)}
const IDLE_MS = 180000

export default {
  private: {
    pg: 0,
    tk: TICKS,
    bCls: 'k1',
    cCls: 'k1',
    hv: { c: 'k1' },
    fSrc: '/common/img/sq_a.png',
    cnt: '0',
    info: 'device: ...'
  },

  onInit() {
    this.touch = null
    this.navAt = 0
    this.secs = 0
    this.lastTouch = Date.now()
    this.kept = false
    this.readInfo()
  },

  // What the band says about itself: a check that this build (designWidth ${W}) matches the screen.
  readInfo() {
    try {
      device.getInfo({
        success: (r) => {
          const f = (k) => (r && r[k] !== undefined && r[k] !== null ? r[k] : '?')
          let s = 'screen ' + f('screenWidth') + 'x' + f('screenHeight') + ' ' + f('screenShape') + ', density ' + f('screenDensity')
          if (r && r.windowWidth !== undefined) s += ', window ' + r.windowWidth + 'x' + r.windowHeight
          if (r && r.windowLogicWidth !== undefined) s += ', logic ' + r.windowLogicWidth + 'x' + r.windowLogicHeight
          s += ', ' + f('model') + ', platform ' + f('platformVersionCode')
          this.info = s
        },
        fail: (d, code) => { this.info = 'getInfo failed ' + code }
      })
    } catch (e) {
      this.info = 'getInfo threw'
    }
  },

  onShow() {
    this.lastTouch = Date.now()
    this.keep(true)
    this.timer = setInterval(() => this.tick(), 1000)
  },

  onHide() {
    clearInterval(this.timer)
    this.keep(false)
  },

  onDestroy() {
    clearInterval(this.timer)
    this.keep(false)
  },

  // Screen stays on while the kit is used (photos take a while); released after 3 idle minutes.
  keep(on) {
    if (this.kept === on) return
    this.kept = on
    try { brightness.setKeepScreenOn({ keepScreenOn: on }) } catch (e) {}
  },

  tick() {
    if (Date.now() - this.lastTouch > IDLE_MS) this.keep(false)
    if (this.pg !== ANIM_PAGE) return
    this.secs += 1
    this.cnt = String(this.secs)
    // lane H: BART 2.0.x's pattern, a new object every tick whose field the class reads
    this.hv = { c: 'k1' }
    if (this.secs % 3 === 0) {
      this.bCls = this.bCls === 'k1' ? 'k2' : 'k1'
      this.fSrc = this.fSrc === '/common/img/sq_a.png' ? '/common/img/sq_b.png' : '/common/img/sq_a.png'
    }
  },

  go(d) {
    const now = Date.now()
    if (now - this.navAt < 400) return
    this.navAt = now
    this.pg = (this.pg + d + PAGES) % PAGES
    if (this.pg === ANIM_PAGE) { this.secs = 0; this.cnt = '0' }
  },

  // Exit: the Band 9 Pro / 10 Pro system back swipe does nothing for a single-page app, so all
  // three routes (onBackPress, @swipe right, raw touch) call exitApp.
  onBackPress() {
    this.exitApp()
    return true
  },

  onSwipe(e) {
    const d = e && e.direction
    if (d === 'right') this.exitApp()
    else if (d === 'left' || d === 'up') this.go(1)
    else if (d === 'down') this.go(-1)
  },

  onTouchStart(e) {
    this.lastTouch = Date.now()
    this.keep(true)
    const t = this.point(e)
    this.touch = t ? { x: t.x, y: t.y, at: Date.now() } : null
  },

  onTouchCancel() {
    this.touch = null
  },

  onTouchEnd(e) {
    const s = this.touch
    this.touch = null
    const t = this.point(e)
    if (!s || !t) return
    const dx = t.x - s.x
    const dy = t.y - s.y
    const dt = Date.now() - s.at
    if (dx > 60 && dx > Math.abs(dy) * 1.5 && dt < 1500) this.exitApp()
    else if (dx < -60 && -dx > Math.abs(dy) * 1.5 && dt < 1500) this.go(1)
    else if (dy > 60 && dy > Math.abs(dx) * 1.5 && dt < 1500) this.go(-1)
    else if (dy < -60 && -dy > Math.abs(dx) * 1.5 && dt < 1500) this.go(1)
    else if (Math.abs(dx) < 20 && Math.abs(dy) < 20 && dt < 800) this.go(1)
  },

  // touchend's touches is an empty (truthy) array, so read changedTouches first.
  point(e) {
    const list = (e && e.changedTouches && e.changedTouches.length ? e.changedTouches : e && e.touches) || []
    const p = list[0]
    if (!p) return null
    const x = p.globalX !== undefined ? p.globalX : (p.clientX !== undefined ? p.clientX : p.offsetX)
    const y = p.globalY !== undefined ? p.globalY : (p.clientY !== undefined ? p.clientY : p.offsetY)
    return typeof x === 'number' && typeof y === 'number' ? { x, y } : null
  },

  exitApp() {
    if (this.exiting) return
    this.exiting = true
    clearInterval(this.timer)
    this.keep(false)
    setTimeout(() => { this.exiting = false }, 1500)
    try { if (this.$app && typeof this.$app.exit === 'function') { this.$app.exit(); return } } catch (e) {}
    try { app.terminate(); return } catch (e) {}
    try { router.back() } catch (e) {}
    this.exiting = false
  }
}
</script>

<style>
.root {
  width: ${W}px;
  height: ${H}px;
  background-color: #000000;
}

.pg {
  position: absolute;
  left: 0px;
  top: 0px;
  width: ${W}px;
  height: ${H}px;
}

.rl {
  position: absolute;
  left: ${RULER.left_x}px;
  top: ${RULER.y0}px;
  width: ${TICK_LEN[2]}px;
  height: ${RULER_H}px;
  flex-direction: column;
}

.rr {
  position: absolute;
  left: ${RULER.right_x - TICK_LEN[2]}px;
  top: ${RULER.y0}px;
  width: ${TICK_LEN[2]}px;
  height: ${RULER_H}px;
  flex-direction: column;
}

.rc {
  width: ${TICK_LEN[2]}px;
  height: ${TICK_EVERY}px;
  flex-shrink: 0;
  flex-direction: column;
  align-items: flex-start;
}

.rcr { align-items: flex-end; }

.k {
  width: ${TICK_LEN[0]}px;
  height: 1px;
  flex-shrink: 0;
  background-color: #ffffff;
}

.k50 { width: ${TICK_LEN[1]}px; }
.k100 { width: ${TICK_LEN[2]}px; background-color: ${C.yellow}; }

/* Animation page: ${TRAVEL} px of travel in a ${LANE_W} px lane, 8 s per run */
.sq {
  width: 24px;
  height: 24px;
  background-color: #ffffff;
}

.sqi {
  width: 24px;
  height: 24px;
}

.k1 { opacity: 1; }
.k2 { opacity: 1; }

/* finish marker: white until 89 % of the path, yellow from 90 % */
@keyframes slidefin {
  0% { transform: translateX(0px); background-color: #ffffff; }
  89% { transform: translateX(${f2(0.89 * TRAVEL)}px); background-color: #ffffff; }
  90% { transform: translateX(${f2(0.9 * TRAVEL)}px); background-color: ${C.yellow}; }
  100% { transform: translateX(${TRAVEL}px); background-color: ${C.yellow}; }
}

/* the same for an image (no background): full opacity until 89 %, dimmed from 90 % */
@keyframes slidedim {
  0% { transform: translateX(0px); opacity: 1; }
  89% { transform: translateX(${f2(0.89 * TRAVEL)}px); opacity: 1; }
  90% { transform: translateX(${f2(0.9 * TRAVEL)}px); opacity: 0.35; }
  100% { transform: translateX(${TRAVEL}px); opacity: 0.35; }
}

@keyframes slideplain {
  0% { transform: translateX(0px); }
  100% { transform: translateX(${TRAVEL}px); }
}

@keyframes slide600 {
  0% { transform: translateX(0px); }
  100% { transform: translateX(600px); }
}

@keyframes fadein {
  0% { opacity: 0; }
  100% { opacity: 1; }
}

.fin8 {
  animation-name: slidefin;
  animation-duration: 8000ms;
  animation-timing-function: linear;
  animation-iteration-count: infinite;
}

.imgfin8 {
  animation-name: slidedim;
  animation-duration: 8000ms;
  animation-timing-function: linear;
  animation-iteration-count: infinite;
}

.st8 {
  animation-name: slideplain;
  animation-duration: 8000ms;
  animation-timing-function: steps(4, end);
  animation-iteration-count: infinite;
}

.an600 {
  animation-name: slide600;
  animation-duration: 8000ms;
  animation-timing-function: linear;
  animation-iteration-count: infinite;
}

.fade {
  animation-name: fadein;
  animation-duration: 2000ms;
  animation-timing-function: linear;
  animation-iteration-count: infinite;
  animation-direction: alternate;
}

/* Generated element classes */
${[...cssClasses.entries()].map(([body, name]) => `.${name} {\n${body}\n}`).join('\n\n')}
</style>
`

// The layout file: everything measure.py needs to find and judge each sample.
const layout = {
  generated_by: 'tools/vela-calib/gen/gen.mjs',
  app: { package: PACKAGE, version: VERSION.name },
  device: DEVICE,
  screen: { w: W, h: H, shape: D.shape },
  frame: {
    tick_every: TICK_EVERY, tick_len: TICK_LEN, yellow_every: 100, ticks: TICKS,
    bar: BAR, code: CODE, label: LABEL, area: AREA,
    // the outline the kit placed everything inside (an assumption; the geometry page measures it)
    visible: CAPSULE ? { shape: 'capsule', end_radius: D.endR, margin: MARGIN } : CIRCLE ? { shape: 'circle', radius: D.radius, margin: MARGIN } : { shape: 'rect', corner_radius: D.cornerR, margin: MARGIN },
    // rows where the screen's left and right edges are straight (hidden-column estimates use these;
    // a circle has none)
    straight_y: CAPSULE ? [D.endR, H - D.endR] : CIRCLE ? null : [D.cornerR, H - D.cornerR],
    colours: C
  },
  pages: pages.map((p) => ({ id: p.id, key: p.key, title: p.title, bar: p.bar, code: p.code, label: p.label, notes: p.notes, observe: p.observe, samples: p.samples }))
}

// Rulers not at the screen's edges (a circle): where they are. Absent = left ruler from x 0, right
// ruler ending at x W, ticks from y 0 (rect, capsule).
if (CIRCLE) layout.frame.ruler = { left_x: RULER.left_x, right_x: RULER.right_x, y0: RULER.y0 }

const manifest = {
  package: PACKAGE,
  name: 'Vela Calib',
  versionName: VERSION.name,
  versionCode: VERSION.code,
  minPlatformVersion: 1200,
  minAPILevel: 1,
  icon: '/common/logo.png',
  deviceTypeList: ['watch'],
  features: [{ name: 'system.router' }, { name: 'system.app' }, { name: 'system.brightness' }, { name: 'system.device' }],
  config: { logLevel: 'log', designWidth: W },
  router: { entry: 'pages/index', pages: { 'pages/index': { component: 'index', path: '/' } } }
}

if (!LAYOUT_ONLY) {
  fs.writeFileSync(path.join(ROOT, 'src/pages/index/index.ux'), ux)
  fs.writeFileSync(path.join(ROOT, 'src/manifest.json'), JSON.stringify(manifest, null, 2) + '\n')
  fs.writeFileSync(path.join(ROOT, 'src/app.ux'), '<script>\nexport default {}\n</script>\n')
}
const layoutOut = optv('layout-out') || path.join(ROOT, 'layouts', `${DEVICE}.json`)
fs.mkdirSync(path.dirname(layoutOut), { recursive: true })
fs.writeFileSync(layoutOut, JSON.stringify(layout, null, 1) + '\n')
console.log(`${DEVICE}: ${pages.length} pages, ${pages.reduce((a, p) => a + p.samples.length, 0)} samples, ${cssClasses.size} classes (kit ${VERSION.name})`)
for (const p of pages) console.log(`  ${String(p.id).padStart(2)} ${p.key.padEnd(7)} ${p.title.padEnd(22)} ${p.samples.length} samples`)
