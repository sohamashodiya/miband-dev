// Face calibration kit: pack a face project with the toolkit's native o66 packer directly.
//
//   vendor/band10-toolkit/node_modules/.bin/tsx tools/face-calib/pack.mts <project dir> [...]
//
// Used where the band10-toolkit CLI can't: its schema only accepts the Band 10's 212 x 520 canvas
// (so every Band 10 Pro page, 336 x 480), and its gmf step only puts the Lua script on the normal
// face (F8 puts it on the always-on face too, calib.json "aodScript"). It writes the same wfDef.json
// the toolkit's builder/gmf.ts writes (widget -> GMF element mapping copied from there) and calls
// the same packGmfDirectory() (builder/native.ts). The binary has no resolution or device field;
// whether a 336 x 480 face made this way installs on a Band 10 Pro is what F1 finds out.
import { copyFile, cp, mkdir, readdir, readFile, rm, stat, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { packGmfDirectory } from '../../vendor/band10-toolkit/builder/native.ts'
import { inspectWatchFace } from '../../vendor/band10-toolkit/parser/index.ts'
import { DATA_SOURCES } from '../../vendor/band10-toolkit/core/dataSources.ts'
import sharp from '../../vendor/band10-toolkit/node_modules/sharp/lib/index.js'

type Widget = Record<string, any>

const nameOf = (rel: string) => rel.replace(/\.png$/i, '').replace(/[^a-zA-Z0-9_-]+/g, '_')

async function size(file: string): Promise<[number, number]> {
  const m = await sharp(file).metadata()
  return [m.width ?? 0, m.height ?? 0]
}

async function pack(dir: string): Promise<void> {
  const manifest = JSON.parse(await readFile(path.join(dir, 'manifest.json'), 'utf8'))
  const layout = JSON.parse(await readFile(path.join(dir, 'layout.json'), 'utf8'))
  const calib = JSON.parse(await readFile(path.join(dir, 'calib.json'), 'utf8').catch(() => '{}'))
  if (!/^\d{9}$/.test(manifest.id)) throw new Error(`${dir}: id must be 9 digits`)
  const W = layout.canvas.width
  const H = layout.canvas.height
  const gmf = path.join(dir, 'build', 'gmf')
  await rm(path.join(dir, 'build'), { recursive: true, force: true })
  const problems: string[] = []

  async function stage(theme: 'normal' | 'aod', rel: string): Promise<string> {
    const src = path.join(dir, rel)
    await stat(src).catch(() => { throw new Error(`${dir}: missing asset ${rel}`) })
    const out = path.join(gmf, theme === 'normal' ? 'images' : 'images_aod')
    await mkdir(out, { recursive: true })
    const n = nameOf(rel)
    await copyFile(src, path.join(out, `${n}.png`))
    return n
  }

  async function element(theme: 'normal' | 'aod', w: Widget): Promise<Record<string, unknown>> {
    if (w.type === 'image') {
      const [iw, ih] = await size(path.join(dir, w.asset))
      if (w.x < 0 || w.y < 0 || w.x + iw > W || w.y + ih > H) problems.push(`${theme}/${w.id} extends outside ${W}x${H}`)
      return { type: 'element', x: w.x, y: w.y, image: await stage(theme, w.asset) }
    }
    if (w.type === 'number') {
      const set = layout.assets.digitSets[w.digitSet]
      const refs = [...set.digits, set.minus]
      const sizes = new Set(await Promise.all(refs.map(async (r: string) => (await size(path.join(dir, r))).join('x'))))
      if (sizes.size > 1) throw new Error(`${dir}: digit set ${w.digitSet} has mixed sizes`)
      const e: Record<string, unknown> = {
        type: 'widge_dignum', x: w.x, y: w.y, showCount: w.digits,
        align: ({ right: 0, left: 1, center: 2 } as Record<string, number>)[w.align],
        spacing: w.spacing ?? 0, showZero: w.leadingZero ?? false,
        dataSrc: DATA_SOURCES[w.source as keyof typeof DATA_SOURCES].fprjId,
        imageList: await Promise.all(refs.map((r: string) => stage(theme, r))),
      }
      if (w.unitAsset) e.image = await stage(theme, w.unitAsset)
      return e
    }
    if (w.type === 'image-list') {
      const items = [...w.items].sort((a: Widget, b: Widget) => a.value - b.value)
      const sizes = new Set(await Promise.all(items.map(async (i: Widget) => (await size(path.join(dir, i.asset))).join('x'))))
      if (sizes.size > 1) throw new Error(`${dir}: image-list ${w.id} has mixed frame sizes`)
      return {
        type: 'widge_imagelist', x: w.x, y: w.y,
        dataSrc: DATA_SOURCES[w.source as keyof typeof DATA_SOURCES].fprjId,
        imageList: await Promise.all(items.map((i: Widget) => stage(theme, i.asset))),
        imageIndexList: items.map((i: Widget) => i.value),
      }
    }
    throw new Error(`${dir}: widget type ${w.type} not supported by pack.mts`)
  }

  const themeElements = async (theme: 'normal' | 'aod') => {
    const t = theme === 'normal' ? layout.normal : layout.aod
    if (!t || (theme === 'aod' && !t.enabled)) return []
    const ws = [...t.widgets].filter((w: Widget) => w.visible !== false).sort((a: Widget, b: Widget) => a.z - b.z)
    const out = []
    for (const w of ws) out.push(await element(theme, w))
    return out
  }

  await mkdir(path.join(gmf, 'images'), { recursive: true })
  const def = {
    name: manifest.name, id: manifest.id, deviceType: 'xiaomi_band_10', previewImg: 'preview', forceIndex256: false,
    elementsNormal: await themeElements('normal'),
    elementsAod: await themeElements('aod'),
  }
  await copyFile(path.join(dir, 'preview.png'), path.join(gmf, 'images', 'preview.png'))
  const scriptSrc = path.join(dir, 'script')
  const hasScript = await stat(path.join(scriptSrc, 'main.lua')).then((s) => s.isFile(), () => false)
  if (hasScript) {
    await cp(scriptSrc, path.join(gmf, 'script'), { recursive: true })
    const files = (await readdir(scriptSrc)).filter((n) => !n.startsWith('.')).sort()
    const el = { type: 'element_script', x: 0, y: 0, scriptDir: 'script', scriptFiles: files, scriptEntry: 'main.lua' }
    def.elementsNormal.push(el)
    if (calib.aodScript) {
      if (!def.elementsAod.length) throw new Error(`${dir}: aodScript needs an AOD face`)
      def.elementsAod.push({ ...el })
    }
  }
  await writeFile(path.join(gmf, 'wfDef.json'), `${JSON.stringify(def, null, 2)}\n`)
  const outBin = path.join(dir, 'dist', `${manifest.output}.bin`)
  await mkdir(path.dirname(outBin), { recursive: true })
  await packGmfDirectory(gmf, outBin, manifest.compiler?.imageCompression ?? true)
  const bin = new Uint8Array(await readFile(outBin))
  const ins = inspectWatchFace(bin)
  if (ins.header.id !== manifest.id) throw new Error(`${dir}: packaged id ${ins.header.id} != manifest ${manifest.id}`)
  const warn = ins.warnings.filter((w: string) => !w.includes('device flags'))
  for (const p of problems) console.log(`  ▲ ${p}`)
  for (const w of warn) console.log(`  ▲ inspect: ${w}`)
  const faces = ins.faces.map((f: any) => `${f.elements.length} el`).join(' + ')
  console.log(`✓ ${manifest.id} ${manifest.name} (${W}x${H}${calib.aodScript ? ', Lua on AOD' : ''}): ${(bin.length / 1024).toFixed(1)} KiB, ${faces}`)
  console.log(`  ${outBin}`)
}

const dirs = process.argv.slice(2)
if (!dirs.length) {
  console.error('usage: tsx tools/face-calib/pack.mts <face project dir> [...]')
  process.exit(2)
}
for (const d of dirs) await pack(path.resolve(d))
