// The generated layouts, for every device spec (devices/*/device.json) and the synthetic test
// specs (test/specs/*.json: a 466 px circle, a 390 x 450 rounded rectangle): each is generated
// afresh (layout only) and checked by checkLayout (test/layout-check.mjs). A committed
// layouts/<id>.json must equal the fresh one (else it is stale: npm run gen / npm run build).
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { listSpecs, loadSpec, specPath } from '../device-spec.mjs'
import { checkLayout } from './layout-check.mjs'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.join(HERE, '..')
const OUT = path.join(HERE, 'out')
fs.mkdirSync(OUT, { recursive: true })

// every spec validates; face id digits (face ids 8<digit><build><face>) are unique among real
// devices; 9 is the synthetic test specs'
const digits = new Map()
for (const id of listSpecs()) {
  const d = loadSpec(id).face?.id_digit
  if (d == null) continue
  assert.ok(d !== 9, `${id}: face id digit 9 is reserved for the synthetic test specs`)
  assert.ok(!digits.has(d), `${id} and ${digits.get(d)} share face id digit ${d}`)
  digits.set(d, id)
}

const specs = [
  ...listSpecs().map((id) => specPath(id)),
  ...fs.readdirSync(path.join(HERE, 'specs')).filter((f) => f.endsWith('.json')).sort().map((f) => path.join(HERE, 'specs', f))
]
for (const sp of specs) {
  const id = JSON.parse(fs.readFileSync(sp, 'utf8')).id
  const out = path.join(OUT, id + '.json')
  try {
    execFileSync(process.execPath, [path.join(ROOT, 'gen', 'gen.mjs'), '--spec', sp, '--layout-only', '--layout-out', out], { stdio: 'pipe' })
  } catch (e) {
    throw new Error(`gen.mjs failed for ${id}: ${String(e.stderr).split('\n').find((l) => l.startsWith('Error')) || e.message}`)
  }
  const L = JSON.parse(fs.readFileSync(out, 'utf8'))
  assert.equal(L.device, id)
  const committed = path.join(ROOT, 'layouts', id + '.json')
  if (fs.existsSync(committed)) assert.equal(fs.readFileSync(committed, 'utf8'), fs.readFileSync(out, 'utf8'), `layouts/${id}.json is stale: regenerate it (node gen/gen.mjs ${id})`)
  const r = checkLayout(L)
  console.log(`layout.test ${id} (${L.screen.w} x ${L.screen.h} ${L.frame.visible.shape}${fs.existsSync(committed) ? ', committed layout current' : ''}): ${r.pages} pages, ${r.slots} worst-case slots checked`)
}
