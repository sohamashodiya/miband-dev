#!/usr/bin/env node
// Seeds the workspace's devices/<id>/profile.json for a band model that hasn't been calibrated yet: the same shape
// as the Band 10 Pro's profile (schema vela-device-profile/2), the screen spec filled in (status
// "assumed", from the maker's spec), the firmware, and EVERY other fact "unknown" (value null) with
// a source naming the calibration page that measures it. measure.py then fills it from photos.
//
//   node seed-profile.mjs band11 --name "Xiaomi Smart Band 11" --w 212 --h 520 --shape capsule \
//        --diag 1.72 --ppi 326 --firmware 4.100.139 --firmware-source "..." [--force]
//
// Two things are kept from the template instead of being made unknown, because they are kit
// policy rather than device facts: font.advance_safety (the width() safety factors).
import fs from 'node:fs'
import path from 'node:path'
import { profilePath, workspaceProfilePath } from './profile-node.mjs'

const argv = process.argv.slice(2)
const id = argv[0]
const opt = (k, d) => { const i = argv.indexOf('--' + k); return i > 0 ? argv[i + 1] : d }
if (!id || id.startsWith('--')) {
  console.error('usage: node seed-profile.mjs <id> --name N --w W --h H --shape rect|capsule --diag IN --ppi PPI --firmware V [--firmware-source S] [--force]')
  process.exit(2)
}
const dest = workspaceProfilePath(id) // always the workspace's devices/<id>/, never the plugin
if (fs.existsSync(dest) && !argv.includes('--force')) {
  console.error(`${dest} exists (pass --force to overwrite it, losing every measured fact)`)
  process.exit(1)
}
const w = Number(opt('w'))
const h = Number(opt('h'))
const diag = Number(opt('diag'))
const ppi = Number(opt('ppi'))
const shape = opt('shape', 'rect')
const fw = opt('firmware')
if (!w || !h || !diag || !ppi || !fw) throw new Error('--w, --h, --diag, --ppi and --firmware are required')
const today = new Date().toISOString().slice(0, 10)
const tpl = JSON.parse(fs.readFileSync(profilePath('band10pro'), 'utf8'))

const KIT = 'Vela Calib 2.0.0'
// Which page measures a fact (by path prefix; first match wins).
const PAGES = [
  ['device.design_width', `${KIT} Screen geometry page (capsule end radius = design scale) + the start page's getInfo line`],
  ['device.design_scale', `${KIT} Screen geometry page (capsule end radius = design scale)`],
  ['screen.system_overlay', `${KIT} Screen geometry page: observe (measure.py set)`],
  ['screen.', `${KIT} Screen geometry page (and the rulers on every page)`],
  ['quickapp.font.advance_em', `${KIT} Text W pages (digits, space); letters only from a font check`],
  ['quickapp.font.string_em', `${KIT} Text W pages`],
  ['quickapp.font.advance_tracking', `${KIT} Text W pages (0000 at 24 / 48 / 96 px)`],
  ['quickapp.font.weights', `${KIT} Text W pages (normal vs bold)`],
  ['quickapp.font.family', 'a Text W / Text V photo compared with the font files'],
  ['quickapp.font.', `${KIT} Text V pages`],
  ['quickapp.text.', `${KIT} Wrap pages`],
  ['quickapp.colour.', `${KIT} Colour floor page`],
  ['quickapp.css.compiler_accepts', 'aiot-toolkit build of a test page'],
  ['quickapp.css.', `${KIT} Box pages`],
  ['quickapp.image.', `${KIT} Images pages`],
  ['quickapp.animation.', `${KIT} Animation page: watch it (measure.py set)`],
  ['quickapp.behaviour.', 'observe on the band (measure.py set)'],
  ['face.', `no face calibration yet: build a face-engine calibration face for this model and photograph it (devices/${id}/CALIBRATION.md)`]
]
const sourceFor = (p) => (PAGES.find(([k]) => p.startsWith(k)) || [null, `${KIT}`])[1]
const unknown = (p) => ({ value: null, status: 'unknown', source: sourceFor(p), date: today })
const isFact = (n) => n && typeof n === 'object' && 'status' in n && 'value' in n

// Measurement details that only make sense for the template's own photos
const DROP = new Set(['screen.corner_detail', 'screen.cap_detail'])
function blank(o, pre) {
  const out = {}
  for (const [k, v] of Object.entries(o)) {
    const p = pre ? pre + '.' + k : k
    if (DROP.has(p)) continue
    if (p === 'quickapp.font.advance_safety') { out[k] = JSON.parse(JSON.stringify(v)); for (const f of Object.values(out[k])) { f.source = 'kit policy (profile.js width() safety), copied from band10pro; not a device fact'; f.date = today } continue }
    if (p === 'quickapp.font.string_em') { out[k] = { bold: {}, normal: {} }; continue } // strings are added as measured
    if (isFact(v)) out[k] = unknown(p)
    else if (v && typeof v === 'object' && !Array.isArray(v)) out[k] = blank(v, p)
    else if (k === 'about' || k === 'note') out[k] = v
    else out[k] = v
  }
  return out
}

const q = blank(tpl.quickapp, 'quickapp')
// facts kit 2.0.0 adds
q.css.flex_shrink_zero = unknown('quickapp.css.flex_shrink_zero')
q.animation.lane_H = unknown('quickapp.animation.lane_H')
q.animation.finish_marker = unknown('quickapp.animation.finish_marker')
const face = blank(tpl.face, 'face')
face.about = `Watch-face engine facts for this model. Nothing measured with a calibration face yet: every fact is unknown. Measure before a face depends on one (devices/${id}/CALIBRATION.md lists what faces have seen so far).`
const scr = blank(tpl.screen, 'screen')
if (shape === 'capsule') {
  scr.shape = { value: 'capsule', status: 'assumed', source: `maker's spec (${w}x${h} capsule); the Screen geometry page measures it`, date: today }
  scr.end_radius_px = unknown('screen.end_radius_px')
}
const mm = 25.4 / ppi
const profile = {
  schema: tpl.schema,
  about: tpl.about.replace(/Units: .*$/, 'Units: band px (= design px when designWidth = the screen width; the geometry page checks it) and em (x font-size).'),
  updated: today,
  firmware: { version: fw, note: tpl.firmware.note },
  device: {
    id,
    name: opt('name', id),
    firmware: { value: fw, status: 'measured', source: opt('firmware-source', 'Mi Fitness device page'), date: today },
    screen: {
      w, h,
      diag_in: { value: diag, status: 'assumed', source: "maker's spec", date: today },
      ppi: { value: ppi, status: 'assumed', source: "maker's spec", date: today },
      mm_per_px: { value: Math.round(mm * 10000) / 10000, status: 'assumed', source: `25.4 / ${ppi}`, date: today },
      size_mm: { value: [Math.round(w * mm * 10) / 10, Math.round(h * mm * 10) / 10], status: 'assumed', source: `${w} x ${h} px at ${Math.round(mm * 10000) / 10000} mm`, date: today }
    },
    design_width: unknown('device.design_width'),
    design_scale: unknown('device.design_scale')
  },
  screen: scr,
  quickapp: q,
  face
}
fs.mkdirSync(path.dirname(dest), { recursive: true })
fs.writeFileSync(dest, JSON.stringify(profile, null, 1) + '\n')
let n = 0
const count = (o) => { for (const v of Object.values(o)) { if (isFact(v)) { if (v.status === 'unknown') n++ } else if (v && typeof v === 'object' && !Array.isArray(v)) count(v) } }
count(profile)
console.log(`${dest}: seeded (${n} facts unknown, firmware ${fw})`)
