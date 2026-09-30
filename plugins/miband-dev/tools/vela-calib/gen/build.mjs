#!/usr/bin/env node
// Builds one .rpk per band model: for each, generate the pages for its screen (designWidth = its
// width, so 1 design px = 1 panel px), run `aiot build`, and rename the output to
// dist/com.soham.velacalib.<device>.debug.<version>.rpk (same package, so installing one model's
// build replaces the other on a band; install the one for that band's model).
// The last model built is band10pro, so src/ in git stays the Band 10 Pro's pages.
//
//   npm run build                  (all models)
//   node gen/build.mjs band11      (just one; npm run build -- band11)
import fs from 'node:fs'
import path from 'node:path'
import { execFileSync, execSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.join(HERE, '..')

// The kit inside the miband-dev plugin is read-only: generating or building writes into the kit,
// so it runs only from a copy in your workspace (cp -R "<plugin>/tools/vela-calib" tools/).
if (fs.existsSync(path.join(ROOT, '..', '..', '.claude-plugin', 'plugin.json'))) {
  console.error('This is the plugin\'s read-only copy of the kit. Copy it into your workspace first:\n' +
    '  cp -R "' + ROOT + '" <workspace>/tools/vela-calib   (then npm install there)')
  process.exit(2)
}
const ALL = ['band11', 'band10pro']
const want = process.argv.slice(2)
const devices = want.length ? ALL.filter((d) => want.includes(d)) : ALL
if (!devices.length) throw new Error('unknown device(s) ' + want.join(', ') + ' (known: ' + ALL.join(', ') + ')')

execFileSync('python3', [path.join(HERE, 'images.py')], { stdio: 'inherit' })
const dist = path.join(ROOT, 'dist')
// aiot build empties dist/ every time: keep each model's rpk aside until all are built
const stage = fs.mkdtempSync(path.join(ROOT, 'build-stage-'))
const built = []
for (const dev of devices) {
  execFileSync(process.execPath, [path.join(HERE, 'gen.mjs'), dev], { stdio: 'inherit', cwd: ROOT })
  const { versionName } = JSON.parse(fs.readFileSync(path.join(ROOT, 'src/manifest.json'), 'utf8'))
  const out = path.join(dist, `com.soham.velacalib.debug.${versionName}.rpk`)
  if (fs.existsSync(out)) fs.rmSync(out)
  execSync('aiot build', { stdio: 'inherit', cwd: ROOT, env: Object.assign({}, process.env, { PATH: path.join(ROOT, 'node_modules', '.bin') + path.delimiter + process.env.PATH }) })
  if (!fs.existsSync(out)) throw new Error('aiot build did not write ' + out)
  const name = `com.soham.velacalib.${dev}.debug.${versionName}.rpk`
  fs.renameSync(out, path.join(stage, name))
  built.push([dev, name])
}
for (const [dev, name] of built) {
  const dest = path.join(dist, name)
  fs.renameSync(path.join(stage, name), dest)
  console.log(`${dev}: ${path.relative(ROOT, dest)} (${fs.statSync(dest).size} bytes)`)
}
fs.rmSync(stage, { recursive: true })
