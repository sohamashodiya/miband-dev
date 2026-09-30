---
name: calibrate-quickapp
description: Measure how a Xiaomi Vela band or watch draws quick-app (Vela JS) UI with the Vela Calib kit and write the device profile's quickapp facts from photos; onboard a new device (rect, rounded, capsule or round screen) with new-device.mjs. Use when a band app needs a fact the profile doesn't have or marks unknown, for a new device, after a firmware update, or when a device photo contradicts the profile.
---

# Quick-app calibration (Vela Calib)

Kit: `${CLAUDE_PLUGIN_ROOT}/tools/vela-calib/` (read-only). Read its `README.md` (pages, photo
procedure, profile schema) and `PROJECT.md` (history and known issues) before changing anything.
Shipped profiles: `${CLAUDE_PLUGIN_ROOT}/data/profiles/<model>/profile.json` plus `CALIBRATION.md`
(what is measured, what is still unknown, the exact photo steps per model).

## Device specs and known devices
What a device *is* (screen size and shape `rect | rounded_rect | capsule | circle`, the quick-app
design width, the face canvas and packer, firmware) is its **device spec**, `device.json`; both kits
generate from it and name no model. The plugin ships specs as defaults in
`${CLAUDE_PLUGIN_ROOT}/data/profiles/<id>/device.json`, listed with sources and confidence in
`${CLAUDE_PLUGIN_ROOT}/data/KNOWN_DEVICES.md`:
- **calibrated:** `band10pro` (quick app and faces), `band11` (quick app and faces; the Band 10
  shares its screen);
- **specs only, unverified:** `band9`, `band9pro`, `redmiwatch5`, `redmiwatch6`, `watchs3`,
  `watchs4`, `watchs4-41`, `watchs5`. Nothing about how they render is known until they are
  onboarded and photographed.
A spec in the workspace's `devices/<id>/device.json` overrides the shipped one (same rule as
profiles).

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
"${CLAUDE_PLUGIN_ROOT}/skills/new-project/copy-kit.sh" vela-calib   # idempotent; also refreshes tools/plugin-defaults/
(cd tools/vela-calib && npm install)          # aiot-toolkit
"${CLAUDE_PLUGIN_ROOT}/skills/new-project/make-keys.sh" --sync   # gives it sign/ (the workspace key)
```
Then `cd tools/vela-calib && npm run build` → one `.rpk` per model in `dist/`. Install with the
`sideload` skill. The copy's `measure.py` reads and writes the same workspace `devices/`. Band apps'
`npm run device` uses this copy's `export.mjs`. The copy reads the shipped profiles and specs from
`tools/plugin-defaults/` (gitignored), which `copy-kit.sh` refreshes from the installed plugin every
time it runs: run it again after a plugin update. Run the kit's own `npm test` in the plugin copy.

## Rules
- **Unknown fact = measure first.** If the fact a UI needs isn't in the profile (or is `unknown`),
  add a calibration page for it: add the page to `gen/gen.mjs` (with a sample type `measure.py` can
  read, or an `observe` entry), bump the kit's `VERSION`, build and install it, ask the user for
  the photo, run `measure.py run … --device <model>`, and only then build the UI. Prefer `measured`
  facts; treat `assumed` ones as provisional and replace them when a page covers them.
- **A new device (any Vela band or watch) must be onboarded and calibrated before any UI work for
  it.** From the workspace root:
  ```sh
  node "$K/new-device.mjs" <id>                       # a known device (shipped spec)
  node "$K/new-device.mjs" <id> --w W --h H --shape rect|rounded_rect|capsule|circle --name "…" \
       [--corner-radius R] [--diag IN] [--ppi PPI] [--firmware V]
  ```
  It touches no device and writes only into the workspace: the spec `devices/<id>/device.json`
  (unverified; a known device's shipped spec is used as is, copied in when it needs a face id
  digit), a profile with every fact `unknown` (unless a shipped profile exists), and
  `devices/<id>/CALIBRATION.md` from `${CLAUDE_PLUGIN_ROOT}/data/CALIBRATION.md`. It generates and
  checks both kits' pages (every sample inside the outline, clear of the frame, no overlaps): from
  the plugin only into a temporary folder, so run `copy-kit.sh vela-calib` and `copy-kit.sh
  face-calib` (new-project skill) and then `node tools/vela-calib/new-device.mjs <id>` in the
  workspace to generate them for real. Then follow the steps it prints: check
  the spec against the maker's page, `npm run build -- <id>` in the workspace copy, install
  (`sideload`), compare page 0's `@system.device` line with the spec, photograph every page into
  `devices/<id>/photos/`, `measure.py run --device <id>`, record observations, do the faces
  (`calibrate-face`), set `"verified": true` in the spec, and record the status in
  `devices/<id>/CALIBRATION.md` and `devices/DEVICES.md`.
- **Round screens** (Watch S3 / S4 / S5, 466–480 px circles) have no straight edge: the rulers are
  two straight tick columns inside the circle, which must both be in frame with the bar and the
  barcode. They are proven only on the kit's synthetic photos so far; the first real round-watch
  photos may need measurer fixes, so check every fit.
- Screens narrower than 212 px (Band 9: 192 px) get quick-app pages, but the face kit refuses them.
- On a capsule or circle check `device.design_scale` (~1.00–1.03, `one_to_one: true`) after the
  geometry page. If not 1:1 the design width is wrong for the device: stop, fix the spec, re-shoot.
- When a device photo contradicts the profile, the photo wins: re-measure, update the profile (with
  its source), then fix the layout.
- The kit is a test pattern: no design mock-ups needed. Black ground, white ink, pink/cyan/green
  outlines, yellow only for the ruler 100s and the scale bar.
