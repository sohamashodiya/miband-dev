// The generated layouts (every device): each sample's worst-case slot is on screen, inside the
// visible outline (capsule ends / rounded corners, with the kit's margin), clear of the rulers, the
// bar and the barcode, and no two slots overlap. One barcode per page, at most 32 pages.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const DEVICES = ['band10pro', 'band11']

const overlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h

for (const dev of DEVICES) {
  const L = JSON.parse(fs.readFileSync(path.join(HERE, '..', 'layouts', dev + '.json'), 'utf8'))
  assert.equal(L.device, dev)
  assert.equal(L.app.version, '2.0.0', dev + ' layout is from kit 2.0.0 (run npm run gen)')
  const W = L.screen.w
  const H = L.screen.h
  const RUL = L.frame.tick_len[2] + 1
  const vis = L.frame.visible
  const inside = (x, y) => {
    const m = vis.margin
    if (vis.shape === 'capsule') {
      const r = vis.end_radius
      const dy = y < r ? r - y : y > H - r ? y - (H - r) : 0
      return Math.hypot(x - W / 2, dy) <= r - m + 1e-9
    }
    const r = vis.corner_radius
    if (x < m || y < m || x > W - m || y > H - m) return false
    const cx = Math.min(Math.max(x, r), W - r)
    const cy = Math.min(Math.max(y, r), H - r)
    return Math.hypot(x - cx, y - cy) <= r - m + 1e-9
  }
  const rectInside = (r) => [[r.x, r.y], [r.x + r.w, r.y], [r.x, r.y + r.h], [r.x + r.w, r.y + r.h]].every(([a, b]) => inside(a, b))
  let checked = 0
  const codes = new Set()
  if (vis.shape === 'capsule') {
    // enough ruler ticks on the straight sides for the homography (measure.py wants >= 12 in all)
    const [s0, s1] = L.frame.straight_y
    const straight = L.frame.ticks.filter((_, i) => i * L.frame.tick_every >= s0 && i * L.frame.tick_every <= s1).length
    assert.ok(2 * straight >= 40, `${dev}: ${2 * straight} ticks on the straight sides`)
    const yellow = L.frame.ticks.filter((t, i) => t === 2 && i * L.frame.tick_every >= s0 - 10 && i * L.frame.tick_every <= s1).length
    assert.ok(2 * yellow >= 3, `${dev}: yellow ticks visible`)
    assert.ok(L.frame.bar.len <= W - 2 * RUL, 'bar clear of the rulers')
  }
  for (const p of L.pages) {
    const bar = { x: p.bar.x, y: p.bar.y - 2, w: p.bar.len, h: p.bar.h + 4 }
    const code = { x: p.code.x - 2, y: p.code.y - 2, w: 7 * p.code.pitch + p.code.cell + 4, h: p.code.h + 4 }
    const lb = p.label
    const label = { x: lb.x, y: lb.y, w: lb.w, h: Math.ceil(1.5 * lb.px) }
    for (const [k, r] of Object.entries({ bar, code, label })) assert.ok(rectInside(r), `${dev} page ${p.key}: ${k} inside the visible screen`)
    const rs = []
    for (const s of p.samples) {
      if (['corner', 'comb', 'cap'].includes(s.type)) continue // the geometry page's edge probes
      const r = s.slot
      assert.ok(r && r.w > 0 && r.h > 0, `${dev} ${s.id}: has a slot`)
      assert.ok(r.x >= 0 && r.y >= 0 && r.x + r.w <= W && r.y + r.h <= H, `${dev} ${s.id} on screen`)
      assert.ok(rectInside(r), `${dev} ${s.id} inside the visible outline: ${JSON.stringify(r)}`)
      assert.ok(r.x >= RUL && r.x + r.w <= W - RUL, `${dev} ${s.id} clear of the rulers (${r.x}..${r.x + r.w})`)
      assert.ok(!overlap(r, bar), `${dev} ${s.id} clear of the bar`)
      assert.ok(!overlap(r, code), `${dev} ${s.id} clear of the barcode`)
      for (const q of rs) assert.ok(!overlap(r, q.r), `${dev} ${s.id} overlaps ${q.id}`)
      rs.push({ id: s.id, r })
      checked++
    }
    assert.ok(!codes.has(p.id))
    codes.add(p.id)
    assert.ok(p.id < 32, 'barcode holds 5 bits')
  }
  assert.ok(L.pages.find((p) => p.key === 'anim'), 'animation page')
  assert.ok(L.pages.find((p) => p.key === 'geo'), 'geometry page')
  console.log(`layout.test ${dev}: ${L.pages.length} pages, ${checked} worst-case slots checked`)
}
