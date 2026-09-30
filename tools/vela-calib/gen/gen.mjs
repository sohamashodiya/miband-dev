#!/usr/bin/env node
// Generates the calibration app's single page (src/pages/index/index.ux), its manifest, and the
// layout file measure.py reads (layouts/<device>.json). Every test element sits at a position
// computed here, so the band markup and the measurement always agree. Don't edit index.ux by hand.
//
//   node gen/gen.mjs [band10pro|band11]      (default band10pro; `npm run gen` runs images.py first)
//
// Frame on every page (identical to the BART 2.0.11 calibration screen, which photographed well):
//   - rulers down both edges: a 1 px tick every 10 px (top edge of the tick = y), 8 px long,
//     14 px every 50, 22 px and yellow every 100; left ruler starts at x 0, right ruler ends at x W
//   - a yellow scale bar exactly BAR_LEN x 4 px near the bottom
//   - a page barcode (8 cells: on, 5 bits of the page number, even parity, on) left of the bar,
//     so measure.py identifies each photo by itself
//   - a grey page label at the top
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.join(HERE, '..')

const DEVICES = {
  band10pro: { name: 'Xiaomi Smart Band 10 Pro', w: 336, h: 480 },
  band11: { name: 'Xiaomi Smart Band 10 / 11', w: 212, h: 520 }
}
const DEVICE = process.argv[2] || 'band10pro'
const D = DEVICES[DEVICE]
if (!D) throw new Error('unknown device ' + DEVICE + ' (known: ' + Object.keys(DEVICES).join(', ') + ')')
const W = D.w
const H = D.h

const VERSION = { name: '1.0.0', code: 1 }
const PACKAGE = 'com.soham.velacalib'

// ---- frame geometry (band px) -------------------------------------------------------------
const TICK_EVERY = 10
const TICKS = Array.from({ length: Math.floor((H - 1) / TICK_EVERY) + 1 }, (_, i) => (i % 10 === 0 ? 2 : i % 5 === 0 ? 1 : 0))
const TICK_LEN = [8, 14, 22]
const WIDE = W >= 300
const BAR = WIDE ? { x: 110, y: H - 24, len: 200, h: 4 } : { x: Math.round((W - 150) / 2), y: H - 24, len: 150, h: 4 }
const CODE = WIDE ? { x: 38, y: H - 28, cell: 6, pitch: 8, h: 10 } : { x: BAR.x, y: H - 40, cell: 6, pitch: 8, h: 10 }
const LABEL = { x: WIDE ? 50 : 40, y: 4, px: 16 }
const AREA = { x0: 24, x1: W - 24, y0: 28, y1: Math.min(BAR.y, CODE.y) - 6 }

// Colours. Outline colours are saturated and never white, so measure.py can tell outline from ink.
const C = {
  white: '#ffffff', yellow: '#ffd60a', pink: '#ff2d95', cyan: '#00e5ff', green: '#3cff3c',
  grey: '#9a9a9a', dim: '#505050'
}
const REGIME_COLOUR = { nat: C.cyan, tall: C.pink, short: C.green }

// ---- width estimates (packing only; the profile holds the real numbers) -------------------
// fit.js table (max of Noto Sans Bold and MiSans Latin Bold, em). Only used to leave room.
const G = {
  ' ': 0.283, ',': 0.32, '.': 0.3, '-': 0.462, '/': 0.438, ':': 0.3, '%': 0.902, '…': 0.963,
  0: 0.64, 1: 0.572, 2: 0.594, 3: 0.6, 4: 0.616, 5: 0.606, 6: 0.627, 7: 0.572, 8: 0.645, 9: 0.627,
  A: 0.723, B: 0.683, C: 0.704, D: 0.75, E: 0.603, F: 0.583, G: 0.735, H: 0.765, I: 0.389, J: 0.53,
  K: 0.708, L: 0.583, M: 0.943, N: 0.813, O: 0.791, P: 0.65, Q: 0.815, R: 0.666, S: 0.622, T: 0.623,
  U: 0.756, V: 0.728, W: 1.071, X: 0.741, Y: 0.703, Z: 0.643, a: 0.599, b: 0.632, c: 0.555,
  d: 0.632, e: 0.597, f: 0.39, g: 0.632, h: 0.65, i: 0.299, j: 0.298, k: 0.62, l: 0.298, m: 0.975,
  n: 0.65, o: 0.625, p: 0.632, q: 0.632, r: 0.447, s: 0.509, t: 0.434, u: 0.65, v: 0.571, w: 0.856,
  x: 0.578, y: 0.571, z: 0.502
}
const em = (s) => [...String(s)].reduce((a, c) => a + (G[c] === undefined ? 1 : G[c]), 0)
const LINE_EST = 1.33 // for slots only

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
    if (it.w > area.x1 - area.x0 || it.h > area.y1 - area.y0) throw new Error('item too big: ' + JSON.stringify({ w: it.w, h: it.h, k: it.key }))
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
{
  const p = page('start', 'Vela calib: start')
  const lines = [
    [30, 'Vela calib ' + VERSION.name],
    [22, 'One photo per page:'],
    [22, 'straight on, whole screen'],
    [22, 'and both rulers in frame.'],
    [22, 'Tap / swipe left: next'],
    [22, 'Swipe down: previous'],
    [22, 'Swipe right: exit'],
    [20, `${DEVICE} ${W}x${H}`]
  ]
  let y = 40
  for (const [s, t] of lines) {
    p.els.push(txt(abs(40, y, W - 80, undefined, { 'font-size': px(s), color: C.white, 'font-weight': 'bold' }), t))
    y += Math.ceil(s * 1.4) + 6
  }
}

// ---- 1. text vertical metrics ---------------------------------------------------------------
// Each string in three boxes: natural (no height, cyan), tall (explicit 1.5 em, pink) and short
// (explicit 0.9 em, green). A <text>'s ink never leaves its own box on the band (BART 2.0.12 check
// photo: shorter boxes were cut at the bottom even with overflow visible), so slots are the boxes.
{
  const SIZES = [24, 32, 48, 72, 96, 140, 180, 240]
  const strOf = (s) => (s <= 96 ? 'Hg8' : '8')
  const items = []
  for (const s of SIZES) {
    for (const regime of ['nat', 'tall', 'short']) {
      const str = strOf(s)
      // Box width only has to hold the ink (a glyph cut at the right doesn't change its vertical
      // metrics); 0.58 em lets two 240 px "8"s share a row.
      const w = str.length === 1 ? Math.ceil(0.58 * s) + 2 : Math.ceil(em(str) * 0.93 * s) + 4
      const line = Math.ceil(LINE_EST * s) + 2
      const boxH = regime === 'tall' ? Math.round(1.5 * s) : regime === 'short' ? Math.round(0.9 * s) : undefined
      const slotH = boxH === undefined ? line : boxH
      items.push({
        key: `${s}-${regime}`, w, h: slotH,
        place(p, x, y) {
          const by = y
          const css = abs(x, by, w, boxH, {
            'font-size': px(s), 'font-weight': 'bold', color: C.white,
            'border-width': '1px', 'border-color': REGIME_COLOUR[regime]
          })
          p.els.push(txt(css, str))
          sample(p, {
            type: 'text_v', str, px: s, regime, weight: 'bold', outline: regime === 'nat' ? 'cyan' : regime === 'tall' ? 'pink' : 'green',
            box: { x, y: by, w, h: boxH === undefined ? null : boxH }, slot: { x, y, w, h: slotH },
            height_css: boxH === undefined ? 'auto' : boxH, border: 1
          })
        }
      })
    }
  }
  pack(items, (i) => page(`tv${i + 1}`, `Text V ${i + 1}`, {
    notes: ['cyan: no height (natural line box)', 'pink: height 1.5 em', 'green: height 0.9 em']
  }), AREA, 2, 6)
}

// ---- 2. text horizontal metrics (advance widths) ---------------------------------------------
// Each string sits in a flex row (no width), so its <text> box shrink-wraps: outer width = advance
// sum + 2 px border. Repeated glyphs ("0000") give per-glyph advances to 0.003 em.
{
  const specs = []
  for (let d = 0; d <= 9; d++) specs.push([String(d).repeat(4), 48, 'bold'])
  specs.push(['0000', 24, 'bold'], ['0000', 96, 'bold'], ['8888', 32, 'bold'])
  for (const w of ['min', 'NOW', 'min, maybe', 'Checking…', 'UPDATING…', 'later 21, 36 min', 'CHANGE AT', 'Embarcadero', 'Union City', 'Alerts ON', '0 0 0 0', ':.,-/%'])
    specs.push([w, 32, 'bold'])
  for (const w of ['abcdefghijklm', 'nopqrstuvwxyz', 'ABCDEFGHIJKLM', 'NOPQRSTUVWXYZ']) specs.push([w, 24, 'bold'])
  // Weight: the same strings in normal weight (does the band have a regular face at all?)
  specs.push(['0000', 48, 'normal'], ['Hg8 min', 32, 'normal'], ['Hg8 min', 32, 'bold'])
  const items = specs.map(([str, s, weight]) => {
    const w = Math.ceil(em(str) * 1.0 * s) + 6
    const h = Math.ceil(LINE_EST * s) + 2
    return {
      key: `${str}@${s}`, w, h,
      place(p, x, y) {
        p.els.push(el('div', abs(x, y, undefined, undefined, { 'flex-direction': 'row', 'align-items': 'flex-start' }), {
          kids: [txt({ 'font-size': px(s), 'font-weight': weight, color: C.white, 'border-width': '1px', 'border-color': C.pink, 'flex-shrink': 0 }, str)]
        }))
        sample(p, { type: 'text_w', str, px: s, weight, outline: 'pink', box: { x, y, w: null, h: null }, est_w: w - 6, border: 1 })
      }
    }
  })
  // A bare absolutely positioned <text> with no width: does it shrink-wrap or stretch?
  items.push({
    key: 'bare', w: 150, h: 46,
    place(p, x, y) {
      p.els.push(txt(abs(x, y, undefined, undefined, { 'font-size': '32px', 'font-weight': 'bold', color: C.white, 'border-width': '1px', 'border-color': C.cyan }), 'Hg8'))
      sample(p, {
        type: 'rect', what: 'absolute <text> with no width: box extent', metric: 'bbox', colour: 'cyan',
        region: [x - 2, y - 2, W - 1, y + 46], hyp: { shrink_wrap: [x, y, Math.ceil(em('Hg8') * 32) + 2, 44], stretch_to_right_edge: [x, y, W - x, 44] },
        fact: 'css.text_auto_width'
      })
    }
  })
  pack(items, (i) => page(`th${i + 1}`, `Text W ${i + 1}`, { notes: ['pink: flex-row wrapped <text>, no width'] }))
}

// ---- 3. wrapping, alignment, lines, ellipsis, line-height ---------------------------------------
{
  const Q = 'The quick brown fox jumps over the dog'
  const specs = [
    { k: 'left', str: Q, s: 20, w: 136, css: { 'text-align': 'left' } },
    { k: 'center', str: Q, s: 20, w: 136, css: { 'text-align': 'center' } },
    { k: 'right', str: Q, s: 20, w: 136, css: { 'text-align': 'right' } },
    { k: 'lines2-ellipsis', str: Q, s: 20, w: 136, css: { lines: 2, 'text-overflow': 'ellipsis' } },
    { k: 'lines1-ellipsis', str: 'Embarcadero to Union City', s: 20, w: 136, css: { lines: 1, 'text-overflow': 'ellipsis' } },
    { k: 'lines2-clip', str: Q, s: 20, w: 136, css: { lines: 2 } },
    { k: 'height40', str: Q, s: 20, w: 136, h: 40, css: {} },
    { k: 'lineheight32', str: Q, s: 20, w: 136, css: { 'line-height': '32px' } },
    { k: 'longword', str: 'Embarcaderoembarcadero', s: 20, w: 136, css: {} },
    { k: 'lh48-at48', str: 'Hg8', s: 48, w: 110, css: { 'line-height': '48px' } },
    { k: 'lh72-at48', str: 'Hg8', s: 48, w: 110, css: { 'line-height': '72px' } },
    { k: 'lh40-at48-h48', str: 'Hg8', s: 48, w: 110, h: 48, css: { 'line-height': '40px' } }
  ]
  const items = specs.map((sp) => {
    const lines = Math.max(1, Math.ceil((em(sp.str) * 0.95 * sp.s) / (sp.w - 4)))
    const lh = Math.max(sp.css['line-height'] ? parseInt(sp.css['line-height'], 10) : 0, LINE_EST * sp.s)
    const slotH = Math.ceil(Math.max(sp.h || 0, Math.min(sp.css.lines || 9, lines) * lh + 0.5 * lh)) + 2
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
  for (const ai of ['flex-end', 'baseline']) {
    items.push({
      key: 'row-' + ai, w: 150, h: 134,
      place(p, x, y) {
        p.els.push(el('div', abs(x, y, undefined, undefined, { 'flex-direction': 'row', 'align-items': ai }), {
          kids: [
            txt({ 'font-size': '96px', 'font-weight': 'bold', color: C.white, 'border-width': '1px', 'border-color': C.cyan }, '5'),
            txt({ 'font-size': '32px', 'font-weight': 'bold', color: C.white, 'border-width': '1px', 'border-color': C.pink }, 'min')
          ]
        }))
        sample(p, { type: 'row', key: 'row-' + ai, align: ai, region: [x - 2, y - 2, x + 150, y + 134], big: { str: '5', px: 96, outline: 'cyan' }, small: { str: 'min', px: 32, outline: 'pink' } })
      }
    })
  }
  pack(items, (i) => page(`tw${i + 1}`, `Wrap ${i + 1}`, { notes: ['pink: 136 px wide boxes at 20 px'] }))
}

// ---- 4. box model ------------------------------------------------------------------------------
// Each test in its own 88 x 96 slot; hypotheses are band px [x, y, w, h] of the measured colour.
{
  const S = { w: 88, h: 96 }
  const T = []
  const add = (key, what, fact, build) => T.push({ key, what, fact, build })
  const W_ = C.white

  add('padding', 'padding 10 inside a 1 px pink box: where the white child lands', 'css.padding', (x, y) => ({
    els: [el('div', abs(x + 4, y + 4, 80, 60, { 'border-width': '1px', 'border-color': C.pink, padding: '10px' }), { kids: [el('div', { width: '20px', height: '20px', 'background-color': W_ }) ] })],
    m: { metric: 'bbox', colour: 'white', region: [x, y, x + S.w, y + S.h], hyp: { honoured: [x + 15, y + 15, 20, 20], ignored: [x + 5, y + 5, 20, 20] } }
  }))
  add('box-sizing', 'width 80 + padding 10 + border 1: outer width of the pink box', 'css.box_sizing', (x, y) => ({
    els: [el('div', abs(x + 4, y + 4, 60, 40, { 'border-width': '1px', 'border-color': C.pink, padding: '10px' }))],
    m: { metric: 'bbox', colour: 'pink', region: [x, y, x + S.w, y + S.h], hyp: { border_box: [x + 4, y + 4, 60, 40], content_box: [x + 4, y + 4, 82, 62] } }
  }))
  add('margin', 'column: cyan has margin-top 12 under a 40 x 10 white bar', 'css.margin', (x, y) => ({
    els: [el('div', abs(x + 4, y + 4, 80, 80, { 'flex-direction': 'column' }), { kids: [
      el('div', { width: '40px', height: '10px', 'background-color': W_, 'flex-shrink': 0 }),
      el('div', { width: '40px', height: '10px', 'background-color': C.cyan, 'margin-top': '12px', 'flex-shrink': 0 })] })],
    m: { metric: 'bbox', colour: 'cyan', region: [x, y, x + S.w, y + S.h], hyp: { honoured: [x + 4, y + 26, 40, 10], ignored: [x + 4, y + 14, 40, 10] } }
  }))
  add('neg-margin-top', 'column: cyan has margin-top -8 under a 40 x 20 white bar', 'css.negative_margin', (x, y) => ({
    els: [el('div', abs(x + 4, y + 20, 80, 60, { 'flex-direction': 'column' }), { kids: [
      el('div', { width: '40px', height: '20px', 'background-color': W_, 'flex-shrink': 0 }),
      el('div', { width: '40px', height: '10px', 'background-color': C.cyan, 'margin-top': '-8px', 'flex-shrink': 0 })] })],
    m: { metric: 'bbox', colour: 'cyan', region: [x, y, x + S.w, y + S.h], hyp: { honoured: [x + 4, y + 32, 40, 10], ignored: [x + 4, y + 40, 40, 10] } }
  }))
  add('neg-margin-left', 'row: cyan has margin-left -10 after a 30 x 20 white box', 'css.negative_margin_left', (x, y) => ({
    els: [el('div', abs(x + 4, y + 20, 80, 30, { 'flex-direction': 'row' }), { kids: [
      el('div', { width: '30px', height: '20px', 'background-color': W_, 'flex-shrink': 0 }),
      el('div', { width: '30px', height: '20px', 'background-color': C.cyan, 'margin-left': '-10px', 'flex-shrink': 0 })] })],
    m: { metric: 'bbox', colour: 'cyan', region: [x, y, x + S.w, y + S.h], hyp: { honoured: [x + 24, y + 20, 30, 20], ignored: [x + 34, y + 20, 30, 20] } }
  }))
  add('abs-in-parent', 'green 10 x 10, absolute left/top 20 inside a pink box at +10: parent- or page-relative', 'css.absolute_origin', (x, y) => ({
    els: [el('div', abs(x + 10, y + 10, 60, 60, { 'border-width': '1px', 'border-color': C.pink }), { kids: [fill(20, 20, 10, 10, C.green)] })],
    m: { metric: 'bbox', colour: 'green', region: [0, 0, W, H], hyp: { parent_border_box: [x + 30, y + 30, 10, 10], parent_content_box: [x + 31, y + 31, 10, 10], page: [20, 20, 10, 10] } }
  }))
  for (const bw of [1, 2, 4, 8]) {
    add('border' + bw, `border-width ${bw}, white, 60 x 50 box: drawn thickness`, 'css.border_width', (x, y) => ({
      els: [el('div', abs(x + 14, y + 20, 60, 50, { 'border-width': bw + 'px', 'border-color': W_ }))],
      m: { metric: 'ring', colour: 'white', region: [x + 8, y + 14, x + 80, y + 76], hyp: { honoured: { l: bw, t: bw, r: bw, b: bw } } }
    }))
  }
  add('border-left-width', 'border 1 + border-left-width 8', 'css.border_side_width', (x, y) => ({
    els: [el('div', abs(x + 14, y + 20, 60, 50, { 'border-width': '1px', 'border-left-width': '8px', 'border-color': W_ }))],
    m: { metric: 'ring', colour: 'white', region: [x + 8, y + 14, x + 80, y + 76], hyp: { honoured: { l: 8, t: 1, r: 1, b: 1 }, ignored: { l: 1, t: 1, r: 1, b: 1 } } }
  }))
  add('border-left-color', 'border 4 white + border-left-color pink', 'css.border_side_colour', (x, y) => ({
    els: [el('div', abs(x + 14, y + 20, 60, 50, { 'border-width': '4px', 'border-color': W_, 'border-left-color': C.pink }))],
    m: { metric: 'colour_at', points: { left: [x + 16, y + 45], top: [x + 44, y + 22] }, hyp: { honoured: { left: 'pink', top: 'white' }, ignored: { left: 'white', top: 'white' } } }
  }))
  add('radius', 'border-radius 20 on a 72 x 56 white fill', 'css.border_radius', (x, y) => ({
    els: [fill(x + 8, y + 20, 72, 56, W_, { 'border-radius': '20px' })],
    m: { metric: 'corners', colour: 'white', region: [x + 2, y + 14, x + 86, y + 82], hyp: { honoured: { tl: 20, tr: 20, br: 20, bl: 20 }, ignored: { tl: 0, tr: 0, br: 0, bl: 0 } } }
  }))
  add('radius-tl', 'border-top-left-radius 24 only', 'css.border_radius_per_corner', (x, y) => ({
    els: [fill(x + 8, y + 20, 72, 56, W_, { 'border-top-left-radius': '24px' })],
    m: { metric: 'corners', colour: 'white', region: [x + 2, y + 14, x + 86, y + 82], hyp: { honoured: { tl: 24, tr: 0, br: 0, bl: 0 }, ignored: { tl: 0, tr: 0, br: 0, bl: 0 }, all_corners: { tl: 24, tr: 24, br: 24, bl: 24 } } }
  }))
  add('radius-override', 'border-radius 20 then border-top-left-radius 0', 'css.border_radius_per_corner_override', (x, y) => ({
    els: [fill(x + 8, y + 20, 72, 56, W_, { 'border-radius': '20px', 'border-top-left-radius': '0px' })],
    m: { metric: 'corners', colour: 'white', region: [x + 2, y + 14, x + 86, y + 82], hyp: { honoured: { tl: 0, tr: 20, br: 20, bl: 20 }, ignored: { tl: 20, tr: 20, br: 20, bl: 20 }, all_zero: { tl: 0, tr: 0, br: 0, bl: 0 } } }
  }))
  add('radius-ring', 'border 3 white + border-radius 16, no fill', 'css.border_radius_outline', (x, y) => ({
    els: [el('div', abs(x + 8, y + 20, 72, 56, { 'border-width': '3px', 'border-color': W_, 'border-radius': '16px' }))],
    m: { metric: 'corners', colour: 'white', region: [x + 2, y + 14, x + 86, y + 82], hyp: { honoured: { tl: 16, tr: 16, br: 16, bl: 16 }, ignored: { tl: 0, tr: 0, br: 0, bl: 0 } } }
  }))
  add('pill', 'border-radius 999 on 72 x 32: clamped to 16?', 'css.border_radius_clamp', (x, y) => ({
    els: [fill(x + 8, y + 32, 72, 32, W_, { 'border-radius': '999px' })],
    m: { metric: 'corners', colour: 'white', region: [x + 2, y + 26, x + 86, y + 70], hyp: { clamped: { tl: 16, tr: 16, br: 16, bl: 16 }, square: { tl: 0, tr: 0, br: 0, bl: 0 } } }
  }))
  add('overflow-hidden', 'overflow hidden 60 x 40 box, child 90 wide', 'css.overflow_hidden', (x, y) => ({
    els: [el('div', abs(x + 4, y + 24, 60, 40, { 'border-width': '1px', 'border-color': C.pink, overflow: 'hidden' }), { kids: [el('div', { width: '90px', height: '20px', 'background-color': W_, 'flex-shrink': 0 })] })],
    m: { metric: 'bbox', colour: 'white', region: [x, y, x + S.w, y + S.h], hyp: { clips_at_padding_box: [x + 5, y + 25, 58, 20], no_clip: [x + 5, y + 25, 90, 20] } }
  }))
  add('overflow-visible', 'default overflow, 60 x 40 box, child 90 wide', 'css.overflow_visible', (x, y) => ({
    els: [el('div', abs(x + 4, y + 24, 60, 40, { 'border-width': '1px', 'border-color': C.pink }), { kids: [el('div', { width: '90px', height: '20px', 'background-color': W_, 'flex-shrink': 0 })] })],
    m: { metric: 'bbox', colour: 'white', region: [x, y, x + S.w + 10, y + S.h], hyp: { clips: [x + 5, y + 25, 58, 20], draws_outside: [x + 5, y + 25, 90, 20], child_shrunk: [x + 5, y + 25, 58, 20] } }
  }))
  add('overflow-radius', 'overflow hidden + radius 20: is a full-size child clipped round?', 'css.overflow_radius_clip', (x, y) => ({
    els: [el('div', abs(x + 14, y + 18, 60, 60, { 'border-radius': '20px', overflow: 'hidden' }), { kids: [el('div', { width: '60px', height: '60px', 'background-color': W_, 'flex-shrink': 0 })] })],
    m: { metric: 'corners', colour: 'white', region: [x + 8, y + 12, x + 80, y + 84], hyp: { round_clip: { tl: 20, tr: 20, br: 20, bl: 20 }, square_clip: { tl: 0, tr: 0, br: 0, bl: 0 } } }
  }))
  add('opacity', 'white fill at opacity 0.5 beside a #808080 fill', 'css.opacity', (x, y) => ({
    els: [fill(x + 6, y + 20, 36, 56, W_, { opacity: 0.5 }), fill(x + 46, y + 20, 36, 56, '#808080')],
    m: { metric: 'luma_pair', a: [x + 10, y + 26, x + 38, y + 70], b: [x + 50, y + 26, x + 78, y + 70], hyp: { honoured: { ratio: 1.0 }, ignored_full: { ratio: 2.0 }, invisible: { ratio: 0 } } }
  }))
  add('z-index', 'white z-index 2 drawn before cyan z-index 1, overlapping', 'css.z_index', (x, y) => ({
    els: [fill(x + 10, y + 20, 44, 44, W_, { 'z-index': 2 }), fill(x + 34, y + 40, 44, 44, C.cyan, { 'z-index': 1 })],
    m: { metric: 'colour_at', points: { overlap: [x + 44, y + 52] }, hyp: { honoured: { overlap: 'white' }, ignored: { overlap: 'cyan' } } }
  }))
  add('translate', 'static transform translateX(20px) on a 20 x 20 white square at +10', 'css.transform_translate', (x, y) => ({
    els: [fill(x + 10, y + 38, 20, 20, W_, { transform: 'translateX(20px)' })],
    m: { metric: 'bbox', colour: 'white', region: [x, y, x + S.w, y + S.h], hyp: { honoured: [x + 30, y + 38, 20, 20], ignored: [x + 10, y + 38, 20, 20] } }
  }))
  add('rotate', 'static rotate(45deg) on a 56 x 4 bar', 'css.transform_rotate', (x, y) => ({
    els: [fill(x + 16, y + 46, 56, 4, W_, { transform: 'rotate(45deg)' })],
    m: { metric: 'bbox', colour: 'white', region: [x, y, x + S.w, y + S.h], hyp: { honoured: [x + 23, y + 27, 42, 42], ignored: [x + 16, y + 46, 56, 4] } }
  }))
  add('percent-width', 'child width 50% of an 80 px parent', 'css.percent_width', (x, y) => ({
    els: [el('div', abs(x + 4, y + 30, 80, 30), { kids: [el('div', { width: '50%', height: '20px', 'background-color': W_ })] })],
    m: { metric: 'bbox', colour: 'white', region: [x, y, x + S.w, y + S.h], hyp: { honoured: [x + 4, y + 30, 40, 20], ignored_full: [x + 4, y + 30, 80, 20] } }
  }))
  add('justify-center', 'row, justify-content center, 20 px child in 80', 'css.justify_content', (x, y) => ({
    els: [el('div', abs(x + 4, y + 30, 80, 30, { 'flex-direction': 'row', 'justify-content': 'center' }), { kids: [el('div', { width: '20px', height: '20px', 'background-color': W_, 'flex-shrink': 0 })] })],
    m: { metric: 'bbox', colour: 'white', region: [x, y, x + S.w, y + S.h], hyp: { honoured: [x + 34, y + 30, 20, 20], ignored: [x + 4, y + 30, 20, 20] } }
  }))
  add('box-shadow', 'box-shadow 0 0 12px white on a 40 x 40 fill', 'css.box_shadow', (x, y) => ({
    els: [fill(x + 24, y + 28, 40, 40, W_, { 'box-shadow': '0px 0px 12px #ffffff' })],
    m: { metric: 'luma_pair', a: [x + 14, y + 40, x + 20, y + 56], b: [x + 30, y + 40, x + 58, y + 56], hyp: { honoured: { ratio: 0.3 }, ignored: { ratio: 0 } } }
  }))
  add('text-bg', 'text with background-color #505050 and radius 12 (a pill label)', 'css.text_background', (x, y) => ({
    els: [txt(abs(x + 4, y + 30, 80, 36, { 'font-size': '24px', 'font-weight': 'bold', color: W_, 'background-color': C.dim, 'border-radius': '12px', 'text-align': 'center' }), 'ON')],
    m: { metric: 'corners', colour: 'any', region: [x, y + 24, x + S.w, y + 72], hyp: { honoured: { tl: 12, tr: 12, br: 12, bl: 12 }, square: { tl: 0, tr: 0, br: 0, bl: 0 } } }
  }))

  const items = T.map((t) => ({
    key: t.key, w: S.w, h: S.h,
    place(p, x, y) {
      const r = t.build(x, y)
      p.els.push(...r.els)
      sample(p, Object.assign({ type: 'rect', key: t.key, what: t.what, fact: t.fact, slot: { x, y, w: S.w, h: S.h } }, r.m))
    }
  }))
  // keep the declared order (not by height): all slots are the same size
  const made = []
  let i = 0
  const perPage = Math.floor((AREA.x1 - AREA.x0 + 6) / (S.w + 6)) * Math.floor((AREA.y1 - AREA.y0 + 8) / (S.h + 8))
  const cols = Math.floor((AREA.x1 - AREA.x0 + 6) / (S.w + 6))
  for (const it of items) {
    const k = i % perPage
    if (k === 0) made.push(page(`bx${made.length + 1}`, `Box ${made.length + 1}`))
    const p = made[made.length - 1]
    it.place(p, AREA.x0 + (k % cols) * (S.w + 6), AREA.y0 + Math.floor(k / cols) * (S.h + 8))
    i++
  }
}

// ---- 5. screen geometry ---------------------------------------------------------------------
// White K x K squares in the four corners (the display's rounded mask cuts them), a comb of 1 px
// lines from the top edge and from the bottom edge, and the rulers' outer tick ends (x 0 and x W,
// on every page) show how much of the panel is hidden. The bar and barcode move to the middle here
// so the bottom corners are free (measure.py tries every bar position the layout lists).
{
  const K = 48
  const gBar = { x: Math.round((W - BAR.len) / 2), y: Math.round(H / 2) - 2, len: BAR.len, h: BAR.h }
  const gCode = Object.assign({}, CODE, { x: gBar.x, y: gBar.y + 14 })
  const p = page('geo', 'Screen geometry', { bar: gBar, code: gCode, label: { x: K + 8, y: 26, px: 16 } })
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
  p.observe.push({ fact: 'screen.system_overlay', ask: 'Right after opening the app: does the band draw anything over the app (status dot, time, indicator)? Where?' })
}

// ---- 6. colour ---------------------------------------------------------------------------------
{
  const p = page('colour', 'Colour floor')
  const cw = Math.floor((AREA.x1 - AREA.x0 + 4) / 13) - 4
  let y = AREA.y0
  const greys = Array.from({ length: 13 }, (_, i) => i * 8) // 0x00 .. 0x60
  const row = (vals, hexOf, h, tag) => {
    const n = vals.length
    const w = Math.floor((AREA.x1 - AREA.x0 + 4) / n) - 4
    vals.forEach((v, i) => {
      const x = AREA.x0 + i * (w + 4)
      const hex = hexOf(v)
      p.els.push(fill(x, y, w, h, hex))
      sample(p, { type: 'swatch', group: tag, hex, value: v, box: { x, y, w, h } })
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
  sample(p, { type: 'background', box: { x: AREA.x0 + 20, y: bgY, w: AREA.x1 - AREA.x0 - 40, h: Math.max(10, AREA.y1 - bgY - 4) } })
  void cw
}

// ---- 7. images ------------------------------------------------------------------------------------
{
  const p = page('img', 'Images')
  const img = (src, x, y, w, h, extra = {}) => el('image', Object.assign(abs(x, y, w, h), extra), { attrs: { src: '/common/img/' + src } })
  const list = [
    // [key, src, w, h, extra css, hypotheses of the drawn white bbox, metric]
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
    ['fit-cover', 'wide64x32.png', 64, 64, { 'object-fit': 'cover' }, (x, y) => ({ fill: [x, y, 64, 64], cover: [x, y, 64, 64], contain: [x, y + 16, 64, 32] })],
    ['fit-none', 'wide64x32.png', 64, 64, { 'object-fit': 'none' }, (x, y) => ({ fill: [x, y, 64, 64], contain: [x, y + 16, 64, 32], none_top_left: [x, y, 64, 32] })]
  ]
  let x = AREA.x0
  let y = AREA.y0
  let rowH = 0
  for (const [key, src, w, h, extra, hyp] of list) {
    const bw = w || 32
    const bh = h || 32
    if (x + bw > AREA.x1) { x = AREA.x0; y += rowH + 12; rowH = 0 }
    p.els.push(img(src, x, y, w, h, extra))
    sample(p, { type: 'rect', key, what: `image ${src} in ${w || 'auto'} x ${h || 'auto'} ${JSON.stringify(extra)}`, fact: 'image.' + key, metric: 'bbox', colour: 'any', region: [x - 3, y - 3, x + Math.max(bw, 64) + 3, y + Math.max(bh, 32) + 3], hyp: hyp(x, y), src })
    x += Math.max(bw, 32) + 10
    rowH = Math.max(rowH, bh)
  }
  y += rowH + 14
  // alpha ramp (white, alpha 0..255) above the same ramp as opaque greys: compare column by column
  p.els.push(img('alpha_ramp.png', AREA.x0, y, 256, 16))
  p.els.push(img('grey_ramp.png', AREA.x0, y + 22, 256, 16))
  sample(p, { type: 'ramp', key: 'alpha-vs-grey', a: { x: AREA.x0, y, w: 256, h: 16 }, b: { x: AREA.x0, y: y + 22, w: 256, h: 16 }, fact: 'image.alpha_blend' })
}

// ---- 8. animation (observation page) ---------------------------------------------------------
// Lanes of 24 px squares. A is the control; the others test what restarts or breaks an animation.
// The page re-renders every second (the counter) and swaps B's class and F's src every 3 s.
const ANIM = {}
{
  const p = page('anim', 'Animation (watch it)')
  ANIM.page = p.id
  const lanes = [
    ['A', 'control: static class, 0 to 240 px in 4 s', 'an4', 'static'],
    ['B', 'class rebound every 3 s (k1/k2)', 'an4', 'classSwap'],
    ['C', 'class has a {{binding}} that never changes; page re-renders every 1 s', 'an4', 'classConst'],
    ['D', 'steps(4, end): four jumps', 'st4', 'static'],
    ['E', 'translateX 0 to 600 px in 6 s (leaves the screen)', 'an600', 'static'],
    ['F', 'image, src swapped every 3 s (identical files)', 'an4', 'srcSwap'],
    ['G', 'opacity 0 to 1, alternate', 'fade', 'static']
  ]
  let y = AREA.y0
  const laneH = Math.floor((AREA.y1 - AREA.y0 - 30) / lanes.length)
  for (const [k, what, anim, mode] of lanes) {
    p.els.push(txt(abs(AREA.x0, y, 20, undefined, { 'font-size': '18px', 'font-weight': 'bold', color: C.yellow }), k))
    p.els.push(fill(AREA.x0 + 24, y + 12, AREA.x1 - AREA.x0 - 24, 1, C.dim))
    const laneBox = el('div', abs(AREA.x0 + 24, y, AREA.x1 - AREA.x0 - 24, 24, { overflow: 'hidden' }), { kids: [] })
    let sq
    if (mode === 'srcSwap') sq = el('image', { width: '24px', height: '24px' }, { attrs: { src: '{{fSrc}}' }, rawClass: 'sq ' + anim })
    else if (mode === 'classSwap') sq = el('div', null, { rawClass: `sq ${anim} {{bCls}}` })
    else if (mode === 'classConst') sq = el('div', null, { rawClass: `sq ${anim} {{cCls}}` })
    else sq = el('div', null, { rawClass: 'sq ' + anim })
    laneBox.kids.push(sq)
    p.els.push(laneBox)
    p.observe.push({ fact: 'animation.lane_' + k, ask: `Lane ${k} (${what}): does it run smoothly to the right end and loop, or jump back early / stop?` })
    y += laneH
  }
  p.els.push(el('text', abs(AREA.x0, y + 2, AREA.x1 - AREA.x0, undefined, { 'font-size': '18px', 'font-weight': 'bold', color: C.grey }), { text: 't = {{cnt}} s   (B, F swap every 3 s)' }))
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

let blocks = ''
for (const p of pages) {
  const frameEls = []
  const lb = p.label
  const cd = p.code
  frameEls.push(txt(abs(lb.x, lb.y, W - lb.x - 30, undefined, { 'font-size': px(lb.px), 'font-weight': 'bold', color: C.grey, lines: 1 }), `${String(p.id).padStart(2, '0')} ${p.title}`))
  barcodeBits(p.id).forEach((b, i) => { if (b) frameEls.push(fill(cd.x + i * cd.pitch, cd.y, cd.cell, cd.h, C.white)) })
  frameEls.push(fill(p.bar.x, p.bar.y, p.bar.len, p.bar.h, C.yellow))
  const body = [...p.els, ...frameEls].map((e) => emit(e, '      ')).join('\n')
  blocks += `    <div if="{{pg === ${p.id}}}" class="pg">\n${body}\n    </div>\n`
}

const ux = `<template>
  <!-- GENERATED by tools/vela-calib/gen/gen.mjs for ${DEVICE} (${W} x ${H}). Do not edit by hand.
       ${pages.length} full-screen test pages. Tap or swipe left/up: next page; swipe down: previous;
       swipe right (or back): exit. Rulers: a 1 px tick every 10 px down both edges (tick top = y),
       14 px long every 50, 22 px and yellow every 100. Yellow bar: exactly ${BAR.len} x ${BAR.h} px at
       (${BAR.x}, ${BAR.y}) (geometry page: mid-screen). Barcode left of it: on, 5 bits of the page
       number, even parity, on.
       Only the animation page binds anything that changes (its classes are static except the
       two lanes that test rebinding). -->
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
    fSrc: '/common/img/sq_a.png',
    cnt: '0'
  },

  onInit() {
    this.touch = null
    this.navAt = 0
    this.secs = 0
    this.lastTouch = Date.now()
    this.kept = false
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
  left: 0px;
  top: 0px;
  width: ${TICK_LEN[2]}px;
  height: ${H}px;
  flex-direction: column;
}

.rr {
  position: absolute;
  left: ${W - TICK_LEN[2]}px;
  top: 0px;
  width: ${TICK_LEN[2]}px;
  height: ${H}px;
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

/* Animation page */
.sq {
  width: 24px;
  height: 24px;
  background-color: #ffffff;
}

.k1 { opacity: 1; }
.k2 { opacity: 1; }

@keyframes slide240 {
  0% { transform: translateX(0px); }
  100% { transform: translateX(240px); }
}

@keyframes slide600 {
  0% { transform: translateX(0px); }
  100% { transform: translateX(600px); }
}

@keyframes fadein {
  0% { opacity: 0; }
  100% { opacity: 1; }
}

.an4 {
  animation-name: slide240;
  animation-duration: 4000ms;
  animation-timing-function: linear;
  animation-iteration-count: infinite;
}

.st4 {
  animation-name: slide240;
  animation-duration: 4000ms;
  animation-timing-function: steps(4, end);
  animation-iteration-count: infinite;
}

.an600 {
  animation-name: slide600;
  animation-duration: 6000ms;
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
  screen: { w: W, h: H },
  frame: {
    tick_every: TICK_EVERY, tick_len: TICK_LEN, yellow_every: 100, ticks: TICKS,
    bar: BAR, code: CODE, label: LABEL,
    colours: C
  },
  pages: pages.map((p) => ({ id: p.id, key: p.key, title: p.title, bar: p.bar, code: p.code, notes: p.notes, observe: p.observe, samples: p.samples }))
}

const manifest = {
  package: PACKAGE,
  name: 'Vela Calib',
  versionName: VERSION.name,
  versionCode: VERSION.code,
  minPlatformVersion: 1200,
  minAPILevel: 1,
  icon: '/common/logo.png',
  deviceTypeList: ['watch'],
  features: [{ name: 'system.router' }, { name: 'system.app' }, { name: 'system.brightness' }],
  config: { logLevel: 'log', designWidth: W },
  router: { entry: 'pages/index', pages: { 'pages/index': { component: 'index', path: '/' } } }
}

fs.writeFileSync(path.join(ROOT, 'src/pages/index/index.ux'), ux)
fs.writeFileSync(path.join(ROOT, 'src/manifest.json'), JSON.stringify(manifest, null, 2) + '\n')
fs.writeFileSync(path.join(ROOT, 'src/app.ux'), '<script>\nexport default {}\n</script>\n')
fs.mkdirSync(path.join(ROOT, 'layouts'), { recursive: true })
fs.writeFileSync(path.join(ROOT, `layouts/${DEVICE}.json`), JSON.stringify(layout, null, 1) + '\n')
console.log(`${DEVICE}: ${pages.length} pages, ${pages.reduce((a, p) => a + p.samples.length, 0)} samples, ${cssClasses.size} classes`)
for (const p of pages) console.log(`  ${String(p.id).padStart(2)} ${p.key.padEnd(7)} ${p.title.padEnd(22)} ${p.samples.length} samples`)
