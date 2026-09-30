// Node loader for device profiles: loadProfile('band10pro') -> makeProfile(devices/band10pro/profile.json).
// Profiles live in the repo's devices/<model>/ folder, one per band model (see devices/DEVICES.md).
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { makeProfile } from './profile.js'

const HERE = path.dirname(fileURLToPath(import.meta.url))
export const DEVICES_DIR = path.resolve(HERE, '..', '..', 'devices')

// devices/<id>/profile.json (or the path itself when given a .json path)
export function profilePath(idOrPath) {
  return idOrPath.endsWith('.json') ? path.resolve(idOrPath) : path.join(DEVICES_DIR, idOrPath, 'profile.json')
}

export function loadProfile(idOrPath) {
  return makeProfile(JSON.parse(fs.readFileSync(profilePath(idOrPath), 'utf8')))
}

export { makeProfile }
