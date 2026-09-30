---
name: calibrate-quickapp
description: Measure how a Xiaomi Vela band draws quick-app (Vela JS) UI with the Vela Calib kit and write the device profile's quickapp facts from photos. Use when a band app needs a fact the profile doesn't have or marks unknown, for a new band model, after a firmware update, or when a device photo contradicts the profile.
---

# Quick-app calibration (Vela Calib)

Kit: `${CLAUDE_PLUGIN_ROOT}/tools/vela-calib/` (read-only). Read its `README.md` (pages, photo
procedure, profile schema) and `PROJECT.md` (history and known issues) before changing anything.
Shipped profiles: `${CLAUDE_PLUGIN_ROOT}/data/profiles/<model>/profile.json` plus `CALIBRATION.md`
(what is measured, what is still unknown, the exact photo steps per model).

## Profiles: one per band model, tied to firmware
- Profiles are `band10pro` (quick app measured, fw 3.101.043) and `band11` (quick app and face
  measured, fw 4.100.139). Each fact is `{value, status, source, date}` with status `measured`,
  `assumed` or `unknown`.
- **Two sections, two renderers.** `quickapp` holds how the Vela JS-app renderer draws (font, text,
  colour, css, animation, image, behaviour); `face` holds the watch-face engine (`calibrate-face`).
  `device`, `screen` and `firmware` are shared at the top level. Never use a quick-app fact for a
  face or the other way round.
- `firmware.version` is the firmware the facts were measured on. When a band's firmware differs
  (check `devices/DEVICES.md` and Mi Fitness), re-run the kit and compare before trusting the
  profile, then update `firmware.version`. After that, rebuild every band app for the model (their
  `device.js` regenerates).
- **Workspace overrides default.** The kit reads the workspace's `devices/<model>/profile.json` if
  present, else the shipped default. Its first write for a model copies the default into the
  workspace and measures on top of it; later plugin updates don't touch the user's copy (diff it
  against the new default when the plugin updates).

## Running the measurements (no build needed)
From the workspace root (`--workspace DIR` or `MIBAND_WORKSPACE` to point elsewhere):
```sh
K="${CLAUDE_PLUGIN_ROOT}/tools/vela-calib"
python3 "$K/measure.py" run devices/<model>/photos/*.jpg --device <model> --dry-run   # look first
python3 "$K/measure.py" run devices/<model>/photos/*.jpg --device <model>             # write
python3 "$K/measure.py" show --device <model>                                         # every fact + status
python3 "$K/measure.py" set animation.lane_A '"reaches the end, turns yellow"' --device <model> --source "anim page, <date>"
```
Writes go to the workspace only: `devices/<model>/profile.json`, per-photo `evidence/*.json`
(commit these) and annotated `results/` (gitignored). The profile is rebuilt from all evidence for
the model, newest photo per page winning. Needs Python 3 with OpenCV, NumPy, SciPy and Pillow.
Photos: ask the user to take them (procedure in the kit README and the model's `CALIBRATION.md`),
then pull them into `devices/<model>/photos/` (gitignored).

## Building or changing the kit app (needs a workspace copy)
The kit's generators write into the kit, so they refuse to run inside the plugin. Once per workspace:
```sh
mkdir -p tools && cp -R "${CLAUDE_PLUGIN_ROOT}/tools/vela-calib" tools/
(cd tools/vela-calib && npm install)          # aiot-toolkit
"${CLAUDE_PLUGIN_ROOT}/skills/new-project/make-keys.sh" --sync   # gives it sign/ (the workspace key)
```
Then `cd tools/vela-calib && npm run build` → one `.rpk` per model in `dist/`. Install with the
`sideload` skill. The copy's `measure.py` reads and writes the same workspace `devices/`. Band apps'
`npm run device` uses this copy's `export.mjs`. The copy can't see the plugin's shipped defaults:
before relying on it, make sure `devices/<model>/profile.json` exists (run any `measure.py set` /
`run` from the plugin once, or copy the default in). Run the kit's own `npm test` in the plugin
copy (it tests the shipped profiles).

## Rules
- **Unknown fact = measure first.** If the fact a UI needs isn't in the profile (or is `unknown`),
  add a calibration page for it: add the page to `gen/gen.mjs` (with a sample type `measure.py` can
  read, or an `observe` entry), bump the kit's `VERSION`, build and install it, ask the user for
  the photo, run `measure.py run … --device <model>`, and only then build the UI. Prefer `measured`
  facts; treat `assumed` ones as provisional and replace them when a page covers them.
- **A new band model must be calibrated before any UI work for it:** add it to `DEVICES` in
  the workspace copy's `gen/gen.mjs` (and `gen/build.mjs`, `test/layout.test.mjs`), `node gen/gen.mjs
  <model>`, seed `devices/<model>/profile.json` with `node "$K/seed-profile.mjs" <model> --name …
  --w … --h … --shape … --diag … --ppi … --firmware …` (screen size and firmware filled in, every
  other fact `unknown`; it writes only into the workspace),
  photograph every page into `devices/<model>/photos/`, run `measure.py run --device <model>`, and
  record the status in `devices/<model>/CALIBRATION.md` and `devices/DEVICES.md`.
- On a capsule screen check `device.design_scale` (~1.00–1.03, `one_to_one: true`) after the
  geometry page. If not 1:1 the design width is wrong for the band: stop, fix the kit, re-shoot.
- When a device photo contradicts the profile, the photo wins: re-measure, update the profile (with
  its source), then fix the layout.
- The kit is a test pattern: no design mock-ups needed. Black ground, white ink, pink/cyan/green
  outlines, yellow only for the ruler 100s and the scale bar.
