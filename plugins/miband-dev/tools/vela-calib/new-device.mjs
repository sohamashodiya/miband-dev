#!/usr/bin/env node
// Onboard a new Xiaomi Vela wearable for calibration. Writes nothing to any device.
//
//   node tools/vela-calib/new-device.mjs <id> --w 466 --h 466 --shape circle --name "Xiaomi Watch S4" \
//        [--corner-radius R] [--diag 1.43] [--ppi 326] [--firmware V] [--also "Other name, ..."] [--force]
//   node tools/vela-calib/new-device.mjs <id>          (the spec devices/<id>/device.json already exists,
//                                                       e.g. one from devices/KNOWN_DEVICES.md)
//
// shape: rect | rounded_rect (with --corner-radius; unknown -> 0.2 x the short side, measured later)
//        | capsule (semicircle ends, h > w) | circle (w == h).
//
// It (1) writes the device spec devices/<id>/device.json (unverified), (2) seeds
// devices/<id>/profile.json with every fact unknown, (3) generates the quick-app kit's layout
// (layouts/<id>.json) and checks it (every sample inside the screen's outline, clear of the frame,
// no overlaps), (4) generates the face kit's pages (tools/face-calib/faces/<id>/, layouts/<id>.json),
// (5) writes devices/<id>/CALIBRATION.md from devices/CALIBRATION.md, and (6) prints the build and
// photo steps. Re-running it on an onboarded device regenerates (3)-(4) and keeps the spec, profile
// and CALIBRATION.md (pass --force with --w/--h/--shape to replace the spec).
//
// Everything it writes goes into the user's workspace (profile-node.mjs workspaceRoot()): the spec,
// profile and CALIBRATION.md in devices/<id>/. Run from the miband-dev plugin's read-only copy of the
// kit, (3) and (4) only generate into a temporary folder to check them; run it again from the
// workspace copy of the kits (tools/vela-calib, tools/face-calib) to generate their pages there.
// A known device (data/profiles/<id>/device.json in the plugin) starts from that shipped spec.
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { DEVICES_DIR, SHAPES, loadSpec, makeSpec, nextIdDigit, specPath, workspaceSpecPath } from './device-spec.mjs'
import { seedProfile } from './seed-profile.mjs'
import { DEFAULTS_DIR, workspaceProfilePath, workspaceRoot } from './profile-node.mjs'
import { checkLayout } from './test/layout-check.mjs'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const REPO = workspaceRoot()
const rel = (p) => (p.startsWith(DEFAULTS_DIR + path.sep) ? 'miband-dev default ' + path.relative(path.resolve(DEFAULTS_DIR, '..', '..'), p)
  : path.relative(REPO, p).startsWith('..') ? p : path.relative(REPO, p))
// Running from the plugin's read-only copy: kit outputs go to a temporary folder (checked, not kept).
const IN_PLUGIN = fs.existsSync(path.join(HERE, '..', '..', '.claude-plugin', 'plugin.json'))
const TMP = IN_PLUGIN ? fs.mkdtempSync(path.join(os.tmpdir(), 'new-device-')) : null
const argv = process.argv.slice(2)
const id = argv[0]
const opt = (k) => { const i = argv.indexOf('--' + k); return i > 0 ? argv[i + 1] : undefined }
const num = (k) => (opt(k) !== undefined ? Number(opt(k)) : undefined)
if (!id || id.startsWith('--')) {
  console.error(`usage: node tools/vela-calib/new-device.mjs <id> --w W --h H --shape ${SHAPES.join('|')} [--name N] [--corner-radius R] [--diag IN] [--ppi PPI] [--firmware V] [--also "a, b"] [--force]`)
  process.exit(2)
}

// 1. the spec
const sp = specPath(id)
const wsp = workspaceSpecPath(id) // where the spec is (re)written: the workspace
const given = opt('w') !== undefined || opt('h') !== undefined || opt('shape') !== undefined
let spec
if (fs.existsSync(sp) && !(given && argv.includes('--force'))) {
  if (given) { console.error(`${rel(sp)} exists: edit it, or pass --force to replace it`); process.exit(1) }
  spec = loadSpec(id)
  console.log(`spec: ${rel(sp)} (existing, ${spec.verified ? 'verified' : 'UNVERIFIED'})`)
  if (spec.face && spec.face.id_digit == null) {
    spec.face.id_digit = nextIdDigit()
    fs.mkdirSync(path.dirname(wsp), { recursive: true })
    fs.writeFileSync(wsp, JSON.stringify(spec, null, 1) + '\n')
    console.log(`spec: face.id_digit ${spec.face.id_digit} assigned (face ids 8${spec.face.id_digit}<build><face>)`)
  }
} else {
  if (!given) { console.error(`no spec ${rel(sp)}: give --w, --h and --shape`); process.exit(2) }
  spec = makeSpec({
    id, name: opt('name'), w: num('w'), h: num('h'), shape: opt('shape'), cornerRadius: num('corner-radius'),
    diag: num('diag'), ppi: num('ppi'), firmware: opt('firmware'), idDigit: nextIdDigit(),
    also: opt('also') ? opt('also').split(',').map((s) => s.trim()).filter(Boolean) : []
  })
  fs.mkdirSync(path.dirname(wsp), { recursive: true })
  fs.writeFileSync(wsp, JSON.stringify(spec, null, 1) + '\n')
  console.log(`spec: ${rel(wsp)} written (UNVERIFIED: check it against the maker's spec page)`)
}
const { w, h, shape } = spec.screen

// 2. the profile
const pp = workspaceProfilePath(id)
const shippedProfile = path.join(DEFAULTS_DIR, id, 'profile.json')
let unknownFacts = null
if (fs.existsSync(pp)) console.log(`profile: ${rel(pp)} exists, kept`)
else if (fs.existsSync(shippedProfile)) console.log(`profile: using the shipped default ${rel(shippedProfile)} (the kits copy it into the workspace on their first write)`)
else {
  seedProfile({ id, name: spec.name, w, h, shape, diag: spec.screen.diag_in, ppi: spec.screen.ppi, firmware: spec.firmware && spec.firmware.version })
  unknownFacts = true
}

// 3. quick-app kit layout (layout only: src/ is regenerated by the build)
const lay = IN_PLUGIN ? path.join(TMP, 'layouts', id + '.json') : path.join(HERE, 'layouts', id + '.json')
fs.mkdirSync(path.dirname(lay), { recursive: true })
execFileSync(process.execPath, [path.join(HERE, 'gen', 'gen.mjs'), '--spec', specPath(id), '--layout-only', '--layout-out', lay], { stdio: 'pipe' })
const L = JSON.parse(fs.readFileSync(lay, 'utf8'))
const chk = checkLayout(L)
// pages to photograph: all but the start and the animation page, as ranges ("1-21, 23")
const shoot = L.pages.filter((p) => p.key !== 'start' && p.key !== 'anim').map((p) => p.id)
const PHOTO_PAGES = shoot.reduce((acc, n) => {
  const last = acc[acc.length - 1]
  if (last && last[1] === n - 1) last[1] = n
  else acc.push([n, n])
  return acc
}, []).map(([a, b]) => (a === b ? String(a) : `${a}-${b}`)).join(', ')
const localDate = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
console.log(`quick-app kit: ${rel(lay)}: ${chk.pages} pages, ${chk.slots} sample slots checked inside the ${shape} outline`)

// 4. face kit
let face = null
if (spec.face) {
  try {
    const out = execFileSync('python3', [path.join(HERE, '..', 'face-calib', 'gen.py'), id, ...(IN_PLUGIN ? ['--out', path.join(TMP, 'face')] : [])], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })
    face = out.split('\n')[0]
    console.log(`face kit: ${face}`)
  } catch (e) {
    console.log(`face kit: NOT generated: ${String(e.stderr || e.message).trim().split('\n').pop()}`)
  }
}

// 5. CALIBRATION.md
const cal = path.join(DEVICES_DIR, id, 'CALIBRATION.md')
if (!fs.existsSync(cal)) {
  const today = localDate()
  const tplPath = [path.join(DEVICES_DIR, 'CALIBRATION.md'), path.join(DEFAULTS_DIR, '..', 'CALIBRATION.md')].find((f) => fs.existsSync(f))
  const t = fs.readFileSync(tplPath, 'utf8')
  fs.mkdirSync(path.dirname(cal), { recursive: true })
  const body = t.slice(t.indexOf('<!-- TEMPLATE START -->') + '<!-- TEMPLATE START -->'.length).replace(/^\s+/, '')
  const shapeText = { rect: 'rectangle', rounded_rect: `rounded rectangle (corner radius ${spec.screen.corner_radius} px, assumed)`, capsule: `capsule (semicircle ends of radius ${w / 2} px)`, circle: `circle (radius ${w / 2} px)` }[shape]
  const fill = {
    ID: id, NAME: spec.name, W: w, H: h, SHAPE: shapeText, DATE: today,
    DIAG: spec.screen.diag_in ? `${spec.screen.diag_in}"` : 'unknown diagonal', PPI: spec.screen.ppi ? `${spec.screen.ppi} ppi` : 'unknown ppi',
    FIRMWARE: (spec.firmware && spec.firmware.version) || 'not recorded yet (read it in Mi Fitness)',
    PAGES: L.pages.length, PHOTO_PAGES, ANIM: L.pages.find((p) => p.key === 'anim').id, GEO: L.pages.find((p) => p.key === 'geo').id,
    FACE_STATUS: spec.face ? (spec.face.status === 'verified' ? 'verified (band10-toolkit target)' : `EXPERIMENTAL (${spec.face.builder}; ${w} x ${h} faces are unverified on this device until F1 is photographed)`) : 'no face section in the spec'
  }
  fs.writeFileSync(cal, body.replace(/\{\{(\w+)\}\}/g, (m, k) => (fill[k] !== undefined ? String(fill[k]) : m)))
  console.log(`notes: ${rel(cal)} written`)
} else console.log(`notes: ${rel(cal)} exists, kept`)

// 6. next steps
const geo = L.pages.find((p) => p.key === 'geo').id
const anim = L.pages.find((p) => p.key === 'anim').id
console.log(`
Next (nothing above touched a phone or band):
${IN_PLUGIN ? `  0. The kit pages above were only checked (in ${TMP}). Copy the kits into the workspace
     (the new-project skill's copy-kit.sh vela-calib, then copy-kit.sh face-calib) and run
     node tools/vela-calib/new-device.mjs ${id} there to generate them; the steps below use those copies.
` : ''}  1. Check ${rel(sp)} against the maker's spec page: size, shape${shape === 'rounded_rect' ? ', corner radius' : ''}, diagonal, ppi. Read the firmware in Mi Fitness and set it in the spec and profile.
  2. Build the quick-app kit:  cd tools/vela-calib && npm run build -- ${id}
     -> dist/com.soham.velacalib.${id}.debug.2.0.0.rpk (designWidth ${w}: 1 design px = 1 panel px)
  3. Install it through AstroBox (the sideload skill's sideload.sh; every pairing prompt is the user's), open Vela Calib.
     Page 0 prints @system.device: compare its screen size and shape with the spec.
  4. Photograph pages ${PHOTO_PAGES} (not ${anim}, the animation page: watch it) into devices/${id}/photos/
     (tools/vela-calib/README.md "Photo procedure"; the barcode names each page). ${shape === 'circle' ? 'Round screen: the rulers are the two tick columns inside the circle; keep both and the bar in frame.' : ''}
  5. cd tools/vela-calib && python3 measure.py run ../../devices/${id}/photos/*.jpg --device ${id}
     Check device.design_scale ~1.00-1.03 and one_to_one (page ${geo}); if not, stop: the design width is wrong.
  6. Record observations (animation lanes, system overlay): python3 measure.py set <path> <value> --device ${id} --source "..."
${spec.face ? `  7. Faces (${spec.face.status}): tools/face-calib/build.sh ${id}; install F1 ALONE first and check it shows;
     then the rest in batches (about 6 custom faces fit); photograph; python3 tools/face-calib/measure_face.py run <photos> --device ${id}
` : ''}  8. Update devices/${id}/CALIBRATION.md and devices/DEVICES.md; set "verified": true in the spec once the photos confirm it.`)
