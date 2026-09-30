// Checks one generated layout (layouts/<id>.json): each sample's worst-case slot is on screen,
// inside the visible outline (capsule ends, rounded corners or circle, with the kit's margin), clear
// of the rulers, the bar and the barcode, and no two slots overlap; the frame itself is inside the
// outline; enough ruler ticks are visible for the fit; one barcode per page, at most 32 pages.
// Used by test/layout.test.mjs and new-device.mjs. Throws (assert) on the first problem.
import assert from 'node:assert/strict'

const overlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h

export function checkLayout(L, { version = '2.0.0' } = {}) {
  const dev = L.device
  assert.equal(L.app.version, version, `${dev} layout is from kit ${version} (run npm run gen)`)
  const W = L.screen.w
  const H = L.screen.h
  const RUL = L.frame.tick_len[2] + 1
  const vis = L.frame.visible
  const ruler = L.frame.ruler || { left_x: 0, right_x: W, y0: 0 }
  const every = L.frame.tick_every
  const tickY = (i) => ruler.y0 + i * every
  const inside = (x, y, m = vis.margin) => {
    if (vis.shape === 'capsule') {
      const r = vis.end_radius
      const dy = y < r ? r - y : y > H - r ? y - (H - r) : 0
      return Math.hypot(x - W / 2, dy) <= r - m + 1e-9
    }
    if (vis.shape === 'circle') return Math.hypot(x - W / 2, y - H / 2) <= vis.radius - m + 1e-9
    const r = vis.corner_radius
    if (x < m || y < m || x > W - m || y > H - m) return false
    if (r <= m) return true
    const cx = Math.min(Math.max(x, r), W - r)
    const cy = Math.min(Math.max(y, r), H - r)
    return Math.hypot(x - cx, y - cy) <= r - m + 1e-9
  }
  const rectInside = (r) => [[r.x, r.y], [r.x + r.w, r.y], [r.x, r.y + r.h], [r.x + r.w, r.y + r.h]].every(([a, b]) => inside(a, b))
  let checked = 0
  const codes = new Set()
  // enough ruler ticks where the outline shows their outer ends, for the homography (measure.py
  // wants >= 12 in all; ask for 40) and at least 3 yellow ones for the rough similarity
  let visibleRows
  if (vis.shape === 'circle') {
    visibleRows = L.frame.ticks.map((_, i) => i).filter((i) => inside(ruler.left_x, tickY(i), 0) && inside(ruler.right_x, tickY(i), 0))
    assert.equal(visibleRows.length, L.frame.ticks.length, `${dev}: every circle ruler tick is inside the circle`)
  } else {
    const [s0, s1] = L.frame.straight_y
    visibleRows = L.frame.ticks.map((_, i) => i).filter((i) => tickY(i) >= s0 && tickY(i) <= s1)
  }
  assert.ok(2 * visibleRows.length >= 40, `${dev}: ${2 * visibleRows.length} ticks on the straight sides`)
  const yellow = L.frame.ticks.filter((t, i) => t === 2 && visibleRows.includes(i)).length
  assert.ok(2 * yellow >= 3, `${dev}: yellow ticks visible`)
  assert.ok(L.frame.bar.len <= ruler.right_x - ruler.left_x - 2 * RUL, `${dev}: bar clear of the rulers`)
  for (const p of L.pages) {
    const bar = { x: p.bar.x, y: p.bar.y - 2, w: p.bar.len, h: p.bar.h + 4 }
    const code = { x: p.code.x - 2, y: p.code.y - 2, w: 7 * p.code.pitch + p.code.cell + 4, h: p.code.h + 4 }
    const lb = p.label
    const label = { x: lb.x, y: lb.y, w: lb.w, h: Math.ceil(1.5 * lb.px) }
    for (const [k, r] of Object.entries({ bar, code, label })) assert.ok(rectInside(r), `${dev} page ${p.key}: ${k} inside the visible screen`)
    const rs = []
    for (const s of p.samples) {
      if (['corner', 'comb', 'cap', 'round'].includes(s.type)) continue // the geometry page's edge probes
      const r = s.slot
      assert.ok(r && r.w > 0 && r.h > 0, `${dev} ${s.id}: has a slot`)
      assert.ok(r.x >= 0 && r.y >= 0 && r.x + r.w <= W && r.y + r.h <= H, `${dev} ${s.id} on screen`)
      assert.ok(rectInside(r), `${dev} ${s.id} inside the visible outline: ${JSON.stringify(r)}`)
      assert.ok(r.x >= ruler.left_x + RUL && r.x + r.w <= ruler.right_x - RUL, `${dev} ${s.id} clear of the rulers (${r.x}..${r.x + r.w})`)
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
  const geo = L.pages.find((p) => p.key === 'geo')
  assert.ok(geo, 'geometry page')
  const probe = { rect: 'corner', capsule: 'cap', circle: 'round' }[vis.shape]
  assert.ok(geo.samples.some((s) => s.type === probe), `${dev}: geometry page has ${probe} samples`)
  return { pages: L.pages.length, slots: checked }
}
