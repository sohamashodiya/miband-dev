// Device specs: the one definition of a Vela wearable both calibration kits generate from.
//
//   devices/<id>/device.json   (schema vela-device-spec/1; see tools/vela-calib/README.md "Device spec")
//
// Where specs come from (same rule as profiles, see profile-node.mjs): the workspace's
// devices/<id>/device.json when it exists, else the known-device spec shipped with the miband-dev
// plugin (data/profiles/<id>/device.json). New specs are written only into the workspace.
//
// A spec says what the device IS (screen size and shape, the quick-app designWidth to build with,
// the watch-face canvas and how faces are packed, firmware). What the device DOES (text metrics,
// visible area, colour floor...) is measured into devices/<id>/profile.json by the kits.
//
// Shapes: 'rect' (square corners, or corner_radius), 'rounded_rect' (corner_radius, band px),
// 'capsule' (semicircular ends of radius w / 2; h > w), 'circle' (w == h, radius w / 2).
// Python twin: tools/vela-calib/device_spec.py (same rules; keep them in step).
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { DEFAULTS_DIR, workspaceDevicesDir } from './profile-node.mjs'

const HERE = path.dirname(fileURLToPath(import.meta.url))
// The workspace's devices/ folder (where new specs, profiles and CALIBRATION.md files go).
export const DEVICES_DIR = workspaceDevicesDir()
export const SCHEMA = 'vela-device-spec/1'
export const SHAPES = ['rect', 'rounded_rect', 'capsule', 'circle']

// The spec to read: the workspace's devices/<id>/device.json, else the shipped default; when neither
// exists, the workspace path (where a new one would go). A .json path is used as is.
export function specPath(idOrPath) {
  if (String(idOrPath).endsWith('.json')) return path.resolve(idOrPath)
  const mine = workspaceSpecPath(idOrPath)
  if (fs.existsSync(mine)) return mine
  const shipped = path.join(DEFAULTS_DIR, idOrPath, 'device.json')
  return fs.existsSync(shipped) ? shipped : mine
}

// Where a new or updated spec is written: always the workspace.
export function workspaceSpecPath(id) {
  return path.join(workspaceDevicesDir(), id, 'device.json')
}

export function loadSpec(idOrPath) {
  const p = specPath(idOrPath)
  if (!fs.existsSync(p)) throw new Error(`no device spec ${p} (create one: node tools/vela-calib/new-device.mjs <id> --w W --h H --shape S)`)
  const s = JSON.parse(fs.readFileSync(p, 'utf8'))
  validateSpec(s, p)
  return s
}

// Ids of every spec, the workspace's and the shipped defaults, sorted.
export function listSpecs() {
  const ids = new Set()
  for (const dir of [workspaceDevicesDir(), DEFAULTS_DIR]) {
    if (!fs.existsSync(dir)) continue
    for (const d of fs.readdirSync(dir)) if (fs.existsSync(path.join(dir, d, 'device.json'))) ids.add(d)
  }
  return [...ids].sort()
}

// The corner radius the kits assume when a rounded rectangle's isn't known: generous on purpose
// (content is kept inside it; the geometry page measures the real one).
export const defaultCornerRadius = (w, h) => Math.round(0.2 * Math.min(w, h))

export function validateSpec(s, where = 'spec') {
  const bad = (m) => { throw new Error(`${where}: ${m}`) }
  if (s.schema !== SCHEMA) bad(`schema must be ${SCHEMA}`)
  if (!/^[a-z0-9][a-z0-9_-]*$/.test(s.id || '')) bad('id must be lower-case letters, digits, - or _')
  const sc = s.screen || bad('screen missing')
  for (const k of ['w', 'h']) if (!Number.isInteger(sc[k]) || sc[k] < 100 || sc[k] > 2000) bad(`screen.${k} must be an integer 100-2000`)
  if (!SHAPES.includes(sc.shape)) bad(`screen.shape must be one of ${SHAPES.join(', ')}`)
  if (sc.shape === 'capsule' && !(sc.h > sc.w)) bad('a capsule is taller than it is wide')
  if (sc.shape === 'circle' && sc.w !== sc.h) bad('a circle has w == h')
  if (sc.corner_radius != null && (!(sc.corner_radius >= 0) || sc.corner_radius > Math.min(sc.w, sc.h) / 2)) bad('corner_radius must be 0..min(w, h) / 2')
  const q = s.quickapp || {}
  if (q.design_width != null && !Number.isInteger(q.design_width)) bad('quickapp.design_width must be an integer')
  const f = s.face
  if (f) {
    if (!f.canvas || !Number.isInteger(f.canvas.w) || !Number.isInteger(f.canvas.h)) bad('face.canvas {w, h} missing')
    // null until the device is onboarded (new-device.mjs assigns the next free digit)
    if (f.id_digit != null && (!Number.isInteger(f.id_digit) || f.id_digit < 1 || f.id_digit > 9)) bad('face.id_digit must be 1-9 (face ids are 8<digit><build><face>) or null')
    if (!['band10-toolkit', 'pack.mts'].includes(f.builder)) bad("face.builder must be 'band10-toolkit' or 'pack.mts'")
    if (f.builder === 'band10-toolkit' && (f.canvas.w !== 212 || f.canvas.h !== 520)) bad('band10-toolkit only builds 212 x 520 faces; use builder pack.mts')
    if (!['verified', 'experimental'].includes(f.status)) bad("face.status must be 'verified' or 'experimental'")
  }
  return s
}

// The kits' geometry for a spec: layout shape ('rect' covers rounded rectangles, with cornerR),
// capsule end radius, circle radius. These are placement assumptions; the geometry pages measure
// the real outline.
export function geometry(s) {
  const { w, h, shape } = s.screen
  if (shape === 'capsule') return { w, h, shape: 'capsule', endR: w / 2 }
  if (shape === 'circle') return { w, h, shape: 'circle', radius: w / 2 }
  const cornerR = s.screen.corner_radius != null ? s.screen.corner_radius : shape === 'rect' ? 0 : defaultCornerRadius(w, h)
  return { w, h, shape: 'rect', cornerR }
}

// Is (x, y) inside the visible outline, m px in from it?
export function insidePt(g, x, y, m = 0) {
  const W = g.w
  const H = g.h
  if (g.shape === 'capsule') {
    const r = g.endR
    const dy = y < r ? r - y : y > H - r ? y - (H - r) : 0
    return Math.hypot(x - W / 2, dy) <= r - m + 1e-9
  }
  if (g.shape === 'circle') return Math.hypot(x - W / 2, y - H / 2) <= g.radius - m + 1e-9
  const r = g.cornerR
  if (x < m || y < m || x > W - m || y > H - m) return false
  if (r <= m) return true
  const cx = Math.min(Math.max(x, r), W - r)
  const cy = Math.min(Math.max(y, r), H - r)
  return Math.hypot(x - cx, y - cy) <= r - m + 1e-9
}

export const rectInsidePt = (g, r, m = 0) => [[r.x, r.y], [r.x + r.w, r.y], [r.x, r.y + r.h], [r.x + r.w, r.y + r.h]].every(([a, b]) => insidePt(g, a, b, m))

// A new spec from the new-device command's options (validated).
export function makeSpec(o) {
  const spec = {
    schema: SCHEMA,
    id: o.id,
    name: o.name || o.id,
    also: o.also || [],
    verified: false,
    about: 'The device definition both calibration kits generate from (tools/vela-calib, tools/face-calib). Measured facts live in profile.json, not here.',
    screen: {
      w: o.w, h: o.h, shape: o.shape,
      corner_radius: o.shape === 'rounded_rect' || o.shape === 'rect' ? (o.cornerRadius != null ? o.cornerRadius : o.shape === 'rect' ? 0 : defaultCornerRadius(o.w, o.h)) : null,
      diag_in: o.diag || null, ppi: o.ppi || null,
      source: o.source || "maker's spec (not yet checked by a calibration photo)"
    },
    quickapp: { design_width: o.designWidth || o.w, status: 'assumed' },
    face: {
      canvas: { w: o.faceW || o.w, h: o.faceH || o.h },
      id_digit: o.idDigit,
      builder: o.w === 212 && o.h === 520 && o.shape === 'capsule' ? 'band10-toolkit' : 'pack.mts',
      device_type: o.deviceType || null,
      status: 'experimental',
      note: 'Faces for this device are experimental until F1 installs and a photo of it measures.'
    },
    firmware: { version: o.firmware || null, note: 'the firmware the kits were last run on; profile.json firmware.version is authoritative for its facts' },
    calib: {}
  }
  if (spec.screen.corner_radius != null && o.cornerRadius == null && o.shape === 'rounded_rect') spec.screen.corner_radius_note = 'assumed (0.2 x the short side) until the geometry page measures it'
  return validateSpec(spec, o.id)
}

// The next free face id digit (face ids must not collide between devices). 9 is left to the
// synthetic test specs (never installed); 1 and 2 are the Band 11 and Band 10 Pro.
export function nextIdDigit() {
  const used = new Set(listSpecs().map((id) => { try { return loadSpec(id).face?.id_digit } catch { return null } }))
  for (let d = 3; d <= 8; d++) if (!used.has(d)) return d
  throw new Error('face id digits 1-8 are all used by onboarded devices: widen the face id scheme (tools/face-calib/gen.py Face.id)')
}
