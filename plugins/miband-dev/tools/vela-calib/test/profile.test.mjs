// profile.js against the seeded Band 10 Pro profile and a synthetic one.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { loadProfile, makeProfile, profilePath, workspaceProfilePath } from '../profile-node.mjs'

const HERE = path.dirname(fileURLToPath(import.meta.url))
let n = 0
const t = (name, fn) => { fn(); n++ }

// These tests check the profiles shipped with the plugin: point the workspace at an empty folder so
// a user's own devices/<model>/profile.json can't stand in for them (child processes inherit it).
process.env.MIBAND_WORKSPACE = fs.mkdtempSync(path.join(os.tmpdir(), 'vc-ws-'))

t('workspace profile overrides the shipped default; writers target the workspace', () => {
  const shipped = profilePath('band11')
  assert.ok(shipped.includes(path.join('data', 'profiles', 'band11')), shipped)
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'vc-ws-'))
  const saved = process.env.MIBAND_WORKSPACE
  process.env.MIBAND_WORKSPACE = ws
  try {
    const mine = workspaceProfilePath('band11')
    assert.equal(mine, path.join(ws, 'devices', 'band11', 'profile.json'))
    assert.equal(profilePath('band11'), shipped) // nothing in the workspace yet
    const doc = JSON.parse(fs.readFileSync(shipped, 'utf8'))
    doc.updated = '2099-01-01'
    fs.mkdirSync(path.dirname(mine), { recursive: true })
    fs.writeFileSync(mine, JSON.stringify(doc))
    assert.equal(profilePath('band11'), mine)
    assert.equal(loadProfile('band11').data.updated, '2099-01-01')
    assert.throws(() => profilePath('band99'), /no profile for "band99"/)
  } finally {
    process.env.MIBAND_WORKSPACE = saved
  }
})

const p = loadProfile('band10pro')

t('every leaf fact has a status and a source', () => {
  const walk = (o, pre) => {
    for (const [k, v] of Object.entries(o)) {
      const at = pre ? pre + '.' + k : k
      if (v && typeof v === 'object' && 'value' in v && 'status' in v) {
        assert.ok(['measured', 'assumed', 'unknown'].includes(v.status), at + ' status')
        assert.ok(v.source, at + ' source')
        if (v.status === 'unknown') assert.equal(v.value, null, at + ' unknown must be null')
      } else if (v && typeof v === 'object' && !Array.isArray(v)) walk(v, at)
    }
  }
  walk(p.data, '')
})

t('line box and natural heights', () => {
  const L = p.lineEm()
  assert.ok(L > 1.3 && L < 1.34, 'line box ' + L)
  assert.equal(p.lineH(96), Math.ceil(L * 96))
  assert.equal(p.lineH(24, 3), Math.ceil(L * 72))
})

t('taller boxes centre, shorter boxes top-align and clip (measured 2026-09-27)', () => {
  const tall = p.inkIn(96, 144)
  assert.equal(tall.rule, 'centre')
  assert.ok(Math.abs(tall.shift - (144 - p.lineEm() * 96) / 2) < 1e-9)
  const short = p.inkIn(240, 224)
  assert.equal(short.rule, 'top')
  assert.equal(short.shift, 0)
  assert.equal(short.clipped, true) // the BART 2.0.12 "8" was cut at the bottom
})

t('minBoxH keeps the digit ink whole with the margin, and never exceeds the line box', () => {
  for (const px of [24, 48, 96, 140, 180, 240]) {
    const h = p.minBoxH(px)
    const r = p.inkIn(px, h)
    assert.ok(!r.clipped, px + ' clipped')
    assert.ok(r.top >= p.defMargin(px) - 1e-9 && r.bottom <= h - p.defMargin(px) + 1e-9, px + ' margins')
    assert.ok(h <= p.lineH(px), px + ' <= line')
    assert.ok(!(h - 1 < p.lineH(px)) || p.inkIn(px, h - 1).clipped || p.inkIn(px, h - 1).bottom > h - 1 - p.defMargin(px), px + ' minimal')
  }
  // 2.0.12's tight 224 px box for a 240 px digit is too short under the measured top rule
  assert.ok(p.minBoxH(240) > 224)
})

t('need() refuses unknown facts instead of guessing', () => {
  // a copy with the geometry and a CSS verdict marked unknown (the real profile has them measured)
  const q = makeProfile(JSON.parse(JSON.stringify(p.data)))
  const unk = () => ({ value: null, status: 'unknown', source: 'calibration page', date: 'x' })
  q.data.screen.corner_radius_px = unk()
  q.data.quickapp.font.ink.cap.top_em = unk()
  q.data.quickapp.css.absolute_origin = unk()
  assert.throws(() => q.need('screen.corner_radius_px'), /not known/)
  assert.throws(() => q.ink(32, 'cap'), /font.ink.cap/)
  assert.throws(() => q.safeArea(), /not known/)
  assert.equal(q.supports('absolute_origin'), null)
  assert.ok(q.unknowns().some((u) => u.path === 'screen.corner_radius_px'))
  assert.equal(p.supports('border_radius_per_corner'), false)
  assert.equal(p.supports('overflow_hidden'), true)
  assert.equal(p.supports('negative_margin'), true) // measured 2026-09-27 (Box 1 page, BART 2.0.13)
})

t('widths: assumed table x 1.1, measured glyphs x 1.02, whole strings win, + tracking under 30 px', () => {
  const a = p.fact('font.advance_em')
  for (const [s, c1, c2] of [['Ab', 'A', 'b'], ['10', '1', '0']]) {
    const k = (c) => (a[c].status === 'measured' ? 1.02 : 1.1)
    assert.ok(Math.abs(p.width(s, 100) - (a[c1].value * k(c1) + a[c2].value * k(c2)) * 100) < 1e-9, s)
  }
  const q = makeProfile(JSON.parse(JSON.stringify(p.data)))
  q.data.quickapp.font.advance_em['0'] = { value: 0.56, status: 'measured', source: 'x', date: 'x' }
  q.data.quickapp.font.string_em.bold = { NOW: { value: 2.0, status: 'measured', source: 'x', date: 'x' } }
  assert.ok(Math.abs(q.width('00', 50) - 0.56 * 1.02 * 100) < 1e-9)
  // under 30 px, + 1 px per glyph of measured tracking (font.advance_tracking)
  assert.ok(Math.abs(q.width('NOW', 10) - (2.0 * 1.02 * 10 + 3)) < 1e-9)
  assert.ok(Math.abs(q.width('NOW', 30) - 2.0 * 1.02 * 30) < 1e-9)
  assert.ok(Math.abs(q.width('00', 29) - (0.56 * 1.02 * 58 + 2)) < 1e-9)
  // assumed glyphs (letters, x 1.1) get no tracking; measured ones (digits, space) do
  assert.ok(Math.abs(p.width('A 1', 26) - (a.A.value * 1.1 + (a[' '].value + a['1'].value) * 1.02) * 26 - 2) < 1e-9)
  assert.equal(p.tracked('A'), false); assert.equal(p.tracked('1'), true); assert.equal(p.tracked(' '), true)
  assert.equal(p.tracking(26), 1); assert.equal(p.tracking(29.9), 1); assert.equal(p.tracking(30), 0); assert.equal(p.tracking(240), 0)
  const r = makeProfile(JSON.parse(JSON.stringify(p.data))); delete r.data.quickapp.font.advance_tracking
  assert.equal(r.tracking(10), 0)
  assert.throws(() => p.width('中', 20), /advance width/)
  assert.equal(p.fits('0', 20, 5), false)
  // a string measured whole with a dot in it is a single key, not a path
  assert.ok(p.fact('font.string_em.bold')[':.,-/%'])
})

t('safe area and corner insets once the geometry is known', () => {
  const q = makeProfile(JSON.parse(JSON.stringify(p.data)))
  const f = (v) => ({ value: v, status: 'measured', source: 'test', date: 'x' })
  Object.assign(q.data.screen.hidden_px, { top: f(0), bottom: f(0), left: f(1), right: f(1) })
  q.data.screen.corner_radius_px = f({ tl: 40, tr: 40, bl: 40, br: 40 })
  assert.deepEqual(q.safeArea(), { left: 1, top: 0, right: 335, bottom: 480, radius: 40 })
  assert.deepEqual(q.xRange(240), [1, 335])
  const [x0] = q.xRange(0)
  assert.equal(x0, 1 + 40) // at the very top row the corner eats the full radius
})

t('colour floor', () => {
  const g = p.data.quickapp.colour.floor.grey
  const floor = p.colourFloor()
  assert.equal(floor, g.value)
  const hex = (v) => '#' + v.toString(16).padStart(2, '0').repeat(3)
  assert.equal(p.visible(hex(floor)), true)
  assert.equal(p.visible(hex(Math.max(0, floor - 8))), false)
  assert.equal(p.visible('#404040'), true)
})

t('export.mjs writes a self-contained module that works', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vc-'))
  const dest = path.join(dir, 'device.mjs')
  execFileSync(process.execPath, [path.join(HERE, '..', 'export.mjs'), 'band10pro', dest])
  const src = fs.readFileSync(dest, 'utf8')
  assert.ok(!/^import /m.test(src), 'no imports')
  return import(dest).then((m) => assert.equal(m.default.lineH(96), p.lineH(96)))
})

t('profile layout: firmware, quickapp section with short paths, face section unknown', () => {
  assert.equal(p.firmware(), '3.101.043')
  assert.ok(p.data.quickapp && p.data.quickapp.font, 'quick-app facts live under quickapp')
  assert.equal(p.data.font, undefined, 'no quick-app facts at the top level')
  assert.equal(p.fact('font.line_box_em'), p.data.quickapp.font.line_box_em.value)
  assert.equal(p.fact('quickapp.font.line_box_em'), p.fact('font.line_box_em'))
  assert.equal(p.fact('device.screen.w'), 336)
  assert.equal(p.status('face.colour.floor.grey'), 'unknown')
  assert.throws(() => p.need('face.colour.floor.grey'), /not known/)
  assert.ok(p.unknowns().some((u) => u.path === 'face.lua.image_format'))
  // an old flat (schema /1) profile still loads
  const flat = JSON.parse(JSON.stringify(p.data))
  Object.assign(flat, flat.quickapp); delete flat.quickapp
  assert.equal(makeProfile(flat).lineH(96), p.lineH(96))
})

t('export.mjs --check passes on a fresh export and fails on a stale one', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vc-'))
  const dest = path.join(dir, 'device.js')
  const exp = path.join(HERE, '..', 'export.mjs')
  execFileSync(process.execPath, [exp, 'band10pro', dest])
  assert.ok(!/"face"/.test(fs.readFileSync(dest, 'utf8')), 'face section not exported')
  execFileSync(process.execPath, [exp, 'band10pro', dest, '--check'])
  fs.appendFileSync(dest, '// edited\n')
  assert.throws(() => execFileSync(process.execPath, [exp, 'band10pro', dest, '--check'], { stdio: 'pipe' }))
})

t('band11 profile: well formed; helpers refuse unknown facts; measured facts sane', () => {
  const b = loadProfile('band11')
  assert.equal(b.id, 'band11')
  assert.equal(b.firmware(), '4.100.139')
  assert.equal(b.W(), 212)
  assert.equal(b.H(), 520)
  const walk = (o, pre) => {
    for (const [k, v] of Object.entries(o)) {
      const at = pre ? pre + '.' + k : k
      if (v && typeof v === 'object' && 'value' in v && 'status' in v) {
        assert.ok(['measured', 'assumed', 'unknown'].includes(v.status), at + ' status')
        assert.ok(v.source, at + ' source')
        if (v.status === 'unknown') assert.equal(v.value, null, at + ' unknown must be null')
      } else if (v && typeof v === 'object' && !Array.isArray(v)) walk(v, at)
    }
  }
  walk(b.data, '')
  // measured from Vela Calib 2.0.0 photos (2026-09-29); before that every one of these was unknown
  if (b.status('font.line_box_em') === 'measured') {
    assert.ok(b.lineEm() > 1.3 && b.lineEm() < 1.36, 'band11 line box ' + b.lineEm())
    assert.equal(b.need('device.design_width'), 212) // the geometry page found 1 design px = 1 panel px
    assert.equal(b.fact('screen.shape'), 'capsule')
    const r = b.need('screen.end_radius_px')
    assert.ok(r.top > 100 && r.top < 106 && r.bottom > 100 && r.bottom < 106, 'end radius ' + JSON.stringify(r))
  }
  // until the kit's photos are measured, nothing about text or the screen is known
  if (b.status('font.line_box_em') === 'unknown') {
    assert.throws(() => b.lineH(20), /not known/)
    assert.throws(() => b.width('0', 20), /advance width/)
    assert.throws(() => b.safeArea(), /not known/)
    assert.equal(b.supports('negative_margin'), null)
  }
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vc-'))
  execFileSync(process.execPath, [path.join(HERE, '..', 'export.mjs'), 'band11', path.join(dir, 'device.js')])
})

t('a capsule profile (end radius per corner) gives capsule-shaped safe rows', () => {
  const q = makeProfile(JSON.parse(JSON.stringify(loadProfile('band11').data)))
  const f = (v) => ({ value: v, status: 'measured', source: 'test', date: 'x' })
  Object.assign(q.data.screen.hidden_px, { top: f(0), bottom: f(0), left: f(2), right: f(2) })
  q.data.screen.corner_radius_px = f({ tl: 104, tr: 104, bl: 104, br: 104 })
  assert.deepEqual(q.xRange(260), [2, 210])
  const [a, z] = q.xRange(0)
  assert.equal(a, 2 + 104) // the very top row of a capsule is its apex
  assert.equal(z, 210 - 104)
})

console.log(`profile.test: ${n} passed`)
