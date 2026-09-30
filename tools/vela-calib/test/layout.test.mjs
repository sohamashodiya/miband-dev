// The generated layout: on screen, no overlaps, clear of the rulers, one barcode per page.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const L = JSON.parse(fs.readFileSync(path.join(HERE, '..', 'layouts', 'band10pro.json'), 'utf8'))
const W = L.screen.w
const H = L.screen.h
const RUL = L.frame.tick_len[2] + 1
let checked = 0

const rectOf = (s) => {
  const b = s.slot || s.box
  if (!b || b.x === undefined || b.x === null) return null
  return { x: b.x, y: b.y, w: b.w || s.est_w || 0, h: b.h || Math.ceil(1.33 * (s.px || 20)) + 2 }
}
const overlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h

const codes = new Set()
for (const p of L.pages) {
  const rs = []
  for (const s of p.samples) {
    const r = rectOf(s)
    if (!r) continue
    assert.ok(r.x >= 0 && r.y >= 0 && r.x + r.w <= W && r.y + r.h <= H, `${s.id} on screen`)
    if (p.key !== 'geo' && s.type !== 'rect') {
      assert.ok(r.x >= RUL && r.x + r.w <= W - RUL, `${s.id} clear of the rulers (${r.x}..${r.x + r.w})`)
      const bar = p.bar
      assert.ok(!overlap(r, { x: bar.x, y: bar.y - 2, w: bar.len, h: bar.h + 4 }), `${s.id} clear of the bar`)
    }
    for (const q of rs) assert.ok(!overlap(r, q.r), `${s.id} overlaps ${q.id}`)
    rs.push({ id: s.id, r })
    checked++
  }
  assert.ok(!codes.has(p.id))
  codes.add(p.id)
  assert.ok(p.id < 32, 'barcode holds 5 bits')
}
assert.ok(L.pages.find((p) => p.key === 'anim'), 'animation page')
console.log(`layout.test: ${L.pages.length} pages, ${checked} sample boxes checked`)
