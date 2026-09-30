// Node loader for device profiles: loadProfile('band11') -> makeProfile(<profile.json>).
//
// Where a profile comes from (same rules as workspace.py for measure.py / measure_face.py):
//   1. the workspace's devices/<id>/profile.json, when it exists (your own calibration wins);
//   2. otherwise the default shipped with the miband-dev plugin, data/profiles/<id>/profile.json.
// The workspace is MIBAND_WORKSPACE when set, else the nearest folder above the current directory
// (then above this file) that has a devices/ folder, else the current directory. Nothing here
// writes; writers (measure.py, seed-profile.mjs) write only into the workspace.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { makeProfile } from './profile.js'

const HERE = path.dirname(fileURLToPath(import.meta.url))
// Shipped defaults: <plugin>/data/profiles when this file runs from the plugin (tools/vela-calib).
export const DEFAULTS_DIR = path.resolve(HERE, '..', '..', 'data', 'profiles')

function findUp(start) {
  let d = path.resolve(start)
  for (;;) {
    if (fs.existsSync(path.join(d, 'devices')) && fs.statSync(path.join(d, 'devices')).isDirectory()) return d
    const up = path.dirname(d)
    if (up === d) return null
    d = up
  }
}

// The user's workspace root (their repo with devices/, apps/, faces/, signing/).
export function workspaceRoot() {
  if (process.env.MIBAND_WORKSPACE) return path.resolve(process.env.MIBAND_WORKSPACE)
  return findUp(process.cwd()) || findUp(HERE) || process.cwd()
}

export function workspaceDevicesDir() {
  return path.join(workspaceRoot(), 'devices')
}

// Kept for older callers: the workspace's devices/ folder.
export const DEVICES_DIR = workspaceDevicesDir()

// The profile to read: workspace devices/<id>/profile.json if present, else the shipped default
// (or the path itself when given a .json path).
export function profilePath(idOrPath) {
  if (idOrPath.endsWith('.json')) return path.resolve(idOrPath)
  const mine = path.join(workspaceDevicesDir(), idOrPath, 'profile.json')
  if (fs.existsSync(mine)) return mine
  const shipped = path.join(DEFAULTS_DIR, idOrPath, 'profile.json')
  if (fs.existsSync(shipped)) return shipped
  throw new Error(`no profile for "${idOrPath}": looked for ${mine} and ${shipped}. ` +
    'Calibrate the model first (seed-profile.mjs, then the calibration kit).')
}

// Where a writer puts the profile: always the workspace.
export function workspaceProfilePath(id) {
  return path.join(workspaceDevicesDir(), id, 'profile.json')
}

// 'workspace' or 'default' (the plugin's shipped profile), for messages.
export function profileOrigin(file) {
  return path.resolve(file).startsWith(DEFAULTS_DIR + path.sep) ? 'default' : 'workspace'
}

export function loadProfile(idOrPath) {
  return makeProfile(JSON.parse(fs.readFileSync(profilePath(idOrPath), 'utf8')))
}

export { makeProfile }
