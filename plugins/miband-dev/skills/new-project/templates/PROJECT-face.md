# <Face>: <whose> watch face

Read this before any work on <Face>. These facts apply only to this project.
(Copied from the miband-dev plugin's `new-project` template. Add the face to `README.md`'s registry.)

## Devices and audience
- Phone: <model>, adb serial `<serial>`. Band: <model> (`devices/<model>/`, fw <x>). Add both to `devices/DEVICES.md`.
- Who wears it and what they asked for.

## Build and face IDs
- Folder: `faces/<name>/`. Generator `generate.ts` writes `assets/`, `layout.json`, `script/` (commit them; edit the generator, not its outputs).
- Build: `cd faces && npx tsx <name>/generate.ts && npm run package -- <name>` → `faces/<name>/dist/<name>.bin`.
- **Current ID `<id>` (v<x.y.z>)**, installed/active since <date>. Bump the ID for every build; after installing, uninstall the older builds.
- Stock faces on the band before any custom face: `ORIGINAL_WATCHFACE.md` (+ screenshot).

## Style
- Palette, type, layout in band px.

## Design mock-ups
- "<Face> · Design": <URL or path to the mock-ups> (also in the registry). Scale: <px per mm>.

## Limits and on-device lessons
- Face-engine facts belong in the profile's `face` section (`devices/<model>/profile.json`); measure unknown ones first.
