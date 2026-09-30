// Device profile helpers for Vela band UI: text boxes, widths, safe area, colour floor, CSS support.
//
// Every number comes from a device profile (devices/<model>/profile.json), written by measure.py
// from photos of the calibration app. Nothing here is a guess: a helper that needs a fact the
// profile marks "unknown" throws, naming the fact and the calibration page that measures it.
//
// Profile layout (schema vela-device-profile/2): `firmware`, `device` and `screen` at the top;
// `quickapp` (the Vela JS-app renderer: font, text, colour, css, animation, image, behaviour) and
// `face` (the watch-face engine). A path is looked up at the top level first, then inside
// `quickapp`, so quick-app paths keep their short form ('font.line_box_em', 'css.negative_margin').
// Face facts are always addressed in full ('face.colour.floor.grey'). Profiles in the old flat
// layout (schema /1) still load.
//
// Pure ES module, no Node APIs, so band code can use it too:
//   Node / tests:  import { loadProfile } from '.../tools/vela-calib/profile-node.mjs'
//   band app:      node tools/vela-calib/export.mjs band10pro <app>/src/common/device.js
//                  (BART: `npm run device`, also run before every build)
//                  then  import device from './device'   (the profile data and these helpers in one file)
//
// Units: band px (design px; designWidth = screen width) and em (x font-size).

const UNKNOWN = 'unknown'

export function makeProfile(data) {
  const walkTo = (root, path) => path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), root)
  // Top level first ('device.screen.w', 'screen.hidden_px.left', 'face.lua.image_format'), then the
  // quick-app section ('font.line_box_em' -> quickapp.font.line_box_em).
  const node = (path) => {
    const top = walkTo(data, path)
    return top !== undefined || !data.quickapp ? top : walkTo(data.quickapp, path)
  }
  const isFact = (n) => n && typeof n === 'object' && 'status' in n && 'value' in n

  // The raw value of a fact (undefined when absent). Plain (non-fact) leaves are returned as is.
  function fact(path) {
    const n = node(path)
    return isFact(n) ? n.value : n
  }

  // 'measured' | 'assumed' | 'unknown' | undefined (absent)
  function status(path) {
    const n = node(path)
    return isFact(n) ? n.status : n === undefined ? undefined : 'measured'
  }

  // The value, or an error that says what to measure. Use this for anything layout depends on.
  function need(path) {
    const n = node(path)
    const v = isFact(n) ? n.value : n
    if (v === undefined || v === null || (isFact(n) && n.status === UNKNOWN)) {
      const where = isFact(n) && n.source ? ` (measure it: ${n.source})` : ''
      throw new Error(`device profile ${data.device && data.device.id}: "${path}" is not known${where}. Add or run a calibration page; don't guess.`)
    }
    return v
  }

  const lineEm = () => need('font.line_box_em')

  // Natural height of `lines` lines of <text> at `px` (no explicit height, no line-height).
  function lineH(px, lines = 1) {
    return Math.ceil(lineEm() * px * lines)
  }

  // Ink of a glyph class ('digit' | 'cap' | 'descender') in px from the top of a natural line box.
  function ink(px, kind = 'digit') {
    return { top: need(`font.ink.${kind}.top_em`) * px, bottom: need(`font.ink.${kind}.bottom_em`) * px }
  }

  // Where the band puts the line inside a <text> whose explicit (border-box) height is boxH, and
  // which part of the ink survives. border: the element's border width (content = boxH - 2 border).
  //   returns { shift, top, bottom, clipped } in px from the content top.
  function inkIn(px, boxH, kind = 'digit', border = 0) {
    const hc = boxH - 2 * border
    const L = lineEm() * px
    const i = ink(px, kind)
    const regime = hc >= L ? 'taller_box' : 'shorter_box'
    const rule = need(`font.regime.${regime}.rule`)
    const shift = rule === 'centre' ? (hc - L) / 2 : rule === 'bottom' ? hc - L : 0
    const clips = need('font.ink_clipped_to_own_box')
    const top = i.top + shift
    const bottom = i.bottom + shift
    const clipped = clips && (top < 0 || bottom > hc)
    return { shift, top: clips ? Math.max(0, top) : top, bottom: clips ? Math.min(hc, bottom) : bottom, clipped, regime, rule }
  }

  // Default breathing room between ink and a box edge: 2 px + 0.03 em (what BART 2.0.12 used).
  const defMargin = (px) => 2 + 0.03 * px

  // The smallest explicit height for a <text> at px that keeps the `kind` ink whole with `margin`
  // px of room above and below. Never more than the natural line box (which always keeps the ink).
  function minBoxH(px, kind = 'digit', margin = defMargin(px), border = 0) {
    const natural = lineH(px) + 2 * border
    for (let h = Math.ceil(ink(px, kind).bottom - ink(px, kind).top); h < natural; h++) {
      const r = inkIn(px, h, kind, border)
      if (!r.clipped && r.top >= margin && r.bottom <= h - 2 * border - margin) return h
    }
    return natural
  }

  // Offset to add to a <text>'s top so its ink top lands `margin` below where the box would start
  // (negative = move the element up). Only useful where negative offsets are honoured (absolute
  // positioning; negative margins only if css.negative_margin is measured as honoured).
  function inkTopOffset(px, boxH, kind = 'digit', margin = defMargin(px), border = 0) {
    return margin - (inkIn(px, boxH, kind, border).top + border)
  }

  // ---- widths ------------------------------------------------------------------------------
  function glyphEm(c, weight) {
    const n = node('font.advance_em')
    const f = n && n[c]
    if (!isFact(f) || f.value == null || f.status === UNKNOWN) return null
    const safety = f.status === 'measured' ? need('font.advance_safety.measured') : need('font.advance_safety.assumed')
    if (weight && weight !== 'bold' && fact('font.weights.normal_differs_from_bold') !== false) return null
    return f.value * safety
  }

  // Fixed tracking in band px per glyph at px (font.advance_tracking: measured 1 px per glyph below
  // 30 px, where the 1.02 safety on MEASURED widths no longer covers it). 0 when the profile doesn't
  // have it. It is added only to glyphs whose width is measured (and to strings measured whole): an
  // assumed advance carries the 1.1 safety, which already covers it (assumed letters measured
  // 0.92-1.00 x the table; 1 px at 26 px is <= 0.04 em).
  function tracking(px) {
    const n = node('font.advance_tracking')
    if (!isFact(n) || n.value == null || n.status === UNKNOWN) return 0
    return n.below_px == null || px < n.below_px ? n.value : 0
  }
  // Does c's width get tracking (its advance is measured)?
  function tracked(c) {
    const f = (node('font.advance_em') || {})[c]
    return isFact(f) && f.status === 'measured'
  }

  // Width of `s` at px in band px (conservative). A string measured as a whole wins (+ tracking per
  // glyph); otherwise the sum of per-glyph advances, each with its own safety (measured 1.02 +
  // tracking, assumed 1.1). Throws on a glyph the profile doesn't have.
  function width(s, px, weight = 'bold') {
    s = String(s)
    const t = tracking(px)
    const whole = node(`font.string_em.${weight}`)
    if (whole && isFact(whole[s]) && whole[s].status === 'measured') return whole[s].value * px * need('font.advance_safety.measured') + t * [...s].length
    let em = 0
    let n = 0
    for (const c of s) {
      const g = glyphEm(c, weight)
      if (g === null) throw new Error(`device profile: no ${weight} advance width for ${JSON.stringify(c)} (calibration page Text W)`)
      em += g
      if (tracked(c)) n++
    }
    return em * px + t * n
  }

  const fits = (s, px, avail, weight = 'bold') => width(s, px, weight) <= avail

  // ---- screen --------------------------------------------------------------------------------
  const W = () => need('device.screen.w')
  const H = () => need('device.screen.h')

  // Visible area in band px. Throws while an edge or the corner radius is unknown.
  function safeArea() {
    const hid = (e) => need(`screen.hidden_px.${e}`)
    const r = need('screen.corner_radius_px')
    const radius = typeof r === 'object' ? Math.max(...Object.values(r)) : r
    return { left: Math.ceil(hid('left')), top: Math.ceil(hid('top')), right: W() - Math.ceil(hid('right')), bottom: H() - Math.ceil(hid('bottom')), radius }
  }

  // Usable [x0, x1] on row y, keeping `pad` px from the visible edge and the rounded corners.
  function xRange(y, pad = 0) {
    const a = safeArea()
    const r = a.radius + pad
    const top = a.top + pad
    const bottom = a.bottom - pad
    let inset = pad
    const dy = y < top + r ? top + r - y : y > bottom - r ? y - (bottom - r) : 0
    if (dy > 0) inset = pad + r - Math.sqrt(Math.max(0, r * r - dy * dy))
    return [a.left + Math.ceil(inset), a.right - Math.ceil(inset)]
  }

  // ---- colour --------------------------------------------------------------------------------
  const colourFloor = () => need('colour.floor.grey')

  // True when a fill is visibly above black on this panel (brightest channel >= the floor).
  function visible(hex) {
    const v = String(hex).replace('#', '')
    const ch = [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16))
    return Math.max(...ch) >= colourFloor()
  }

  // ---- CSS -------------------------------------------------------------------------------------
  // true / false when measured or assumed, null when unknown. Name: 'border_radius_per_corner'.
  function supports(name) {
    const n = node('css.' + name)
    if (!isFact(n) || n.status === UNKNOWN) return null
    return n.supported === undefined ? null : n.supported
  }

  // Every unknown fact (for "what should I calibrate next?").
  function unknowns() {
    const out = []
    const walk = (o, pre) => {
      for (const [k, v] of Object.entries(o || {})) {
        const p = pre ? pre + '.' + k : k
        if (isFact(v)) { if (v.status === UNKNOWN) out.push({ path: p, source: v.source }) } else if (v && typeof v === 'object' && !Array.isArray(v)) walk(v, p)
      }
    }
    walk(data, '')
    return out
  }

  // The firmware the profile was measured on ('3.101.043'), or undefined.
  const firmware = () => (data.firmware && typeof data.firmware === 'object' ? data.firmware.version : data.firmware) || fact('device.firmware')

  return {
    data, id: data.device && data.device.id, firmware, fact, status, need, unknowns,
    lineEm, lineH, ink, inkIn, minBoxH, inkTopOffset, defMargin,
    width, tracking, tracked, fits, W, H, safeArea, xRange, colourFloor, visible, supports
  }
}

export default makeProfile
