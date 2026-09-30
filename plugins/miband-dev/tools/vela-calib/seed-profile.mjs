#!/usr/bin/env node
// Seeds the workspace's devices/<id>/profile.json (never the plugin's) for a device that hasn't been calibrated yet: the same shape as
// the Band 10 Pro's profile (schema vela-device-profile/2), the screen spec filled in (status
// "assumed", from the device spec / maker's spec), the firmware, and EVERY other fact "unknown"
// (value null) with a source naming the calibration page that measures it. measure.py then fills it
// from photos.
//
//   node seed-profile.mjs <id> [--force]              (reads devices/<id>/device.json)
//   node seed-profile.mjs <id> --name N --w W --h H --shape rect|rounded_rect|capsule|circle \
//        [--diag IN] [--ppi PPI] [--firmware V] [--firmware-source S] [--force]   (flags override the spec)
//
// Two things are kept from the template instead of being made unknown, because they are kit
// policy rather than device facts: font.advance_safety (the width() safety factors).
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { profilePath, workspaceProfilePath } from './profile-node.mjs'
import { specPath } from './device-spec.mjs'

// o: { id, name, w, h, shape, diag, ppi, firmware, firmwareSource, force }. Returns the path written.
export function seedProfile(o) {
  const { id } = o
  const dest = workspaceProfilePath(id) // always the workspace
  if (fs.existsSync(dest) && !o.force) throw new Error(`${dest} exists (pass --force to overwrite it, losing every measured fact)`)
  const { w, h, diag, ppi } = o
  const shape = o.shape || 'rect'
  const fw = o.firmware || null
  if (!w || !h) throw new Error('screen w and h are required (a device spec, or --w and --h)')
  const d0 = new Date()
  const today = `${d0.getFullYear()}-${String(d0.getMonth() + 1).padStart(2, '0')}-${String(d0.getDate()).padStart(2, '0')}`
  const opt = (k, d) => (k === 'name' ? o.name || d : k === 'firmware-source' ? o.firmwareSource || d : d)
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
  const DROP = new Set(['screen.corner_detail', 'screen.cap_detail', 'screen.round_detail'])
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
  scr.shape = { value: shape === 'rounded_rect' ? 'rect' : shape, status: 'assumed', source: `device spec (${w}x${h} ${shape}); the Screen geometry page measures it`, date: today }
  if (shape === 'capsule') scr.end_radius_px = unknown('screen.end_radius_px')
  if (shape === 'circle') scr.radius_px = unknown('screen.radius_px')
  const mm = ppi ? 25.4 / ppi : null
  const spec_ = (v, src) => (v ? { value: v, status: 'assumed', source: src, date: today } : { value: null, status: 'unknown', source: "maker's spec not recorded (devices/<id>/device.json screen)", date: today })
  const profile = {
    schema: tpl.schema,
    about: tpl.about.replace(/Units: .*$/, 'Units: band px (= design px when designWidth = the screen width; the geometry page checks it) and em (x font-size).'),
    updated: today,
    firmware: { version: fw, note: tpl.firmware.note },
    device: {
      id,
      name: opt('name', id),
      firmware: fw ? { value: fw, status: 'measured', source: opt('firmware-source', 'Mi Fitness device page'), date: today }
        : { value: null, status: 'unknown', source: 'read it from Mi Fitness (device page) and set firmware.version and this fact', date: today },
      screen: {
        w, h,
        diag_in: spec_(diag, "maker's spec"),
        ppi: spec_(ppi, "maker's spec"),
        mm_per_px: spec_(mm && Math.round(mm * 10000) / 10000, `25.4 / ${ppi}`),
        size_mm: spec_(mm && [Math.round(w * mm * 10) / 10, Math.round(h * mm * 10) / 10], `${w} x ${h} px at ${mm && Math.round(mm * 10000) / 10000} mm`)
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
  console.log(`${dest}: seeded (${n} facts unknown, firmware ${fw || 'unknown'})`)
  return dest
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const argv = process.argv.slice(2)
  const id = argv[0]
  const flag = (k) => { const i = argv.indexOf('--' + k); return i > 0 ? argv[i + 1] : undefined }
  if (!id || id.startsWith('--')) {
    console.error('usage: node seed-profile.mjs <id> [--name N --w W --h H --shape rect|rounded_rect|capsule|circle --diag IN --ppi PPI --firmware V --firmware-source S] [--force]')
    process.exit(2)
  }
  const spec = fs.existsSync(specPath(id)) ? JSON.parse(fs.readFileSync(specPath(id), 'utf8')) : null
  const sc = (spec && spec.screen) || {}
  const num = (k, d) => (flag(k) !== undefined ? Number(flag(k)) : d)
  try {
    seedProfile({
      id, name: flag('name') || (spec && spec.name), w: num('w', sc.w), h: num('h', sc.h), shape: flag('shape') || sc.shape,
      diag: num('diag', sc.diag_in), ppi: num('ppi', sc.ppi), firmware: flag('firmware') || (spec && spec.firmware && spec.firmware.version),
      firmwareSource: flag('firmware-source'), force: argv.includes('--force')
    })
  } catch (e) {
    console.error(e.message)
    process.exit(1)
  }
}
