---
name: calibrate-face
description: Measure how a Xiaomi Vela device's watch-face engine draws (visible area, colour floor, image formats, number and image-list widgets, the Lua layer, always-on) with the face calibration kit, writing the device profile's face facts from photos. Use when a watch face needs a face fact that is unknown, for a device whose faces aren't verified yet, or after a firmware update.
---

# Watch-face calibration (face kit)

Kit: `${CLAUDE_PLUGIN_ROOT}/tools/face-calib/` (read-only). Read its `README.md` (the eight faces
F1–F8, the photo procedure, what each fact means) and `PROJECT.md` (the Band 11 runs and the
measurer fixes) first. Both shipped `face` sections are measured: Band 11 (build 1, fw 4.100.139,
13 photos) and Band 10 Pro (build 1 packed at 336×480 by `pack.mts`, fw 3.101.043, 9 photos; all 8
faces accepted). A few facts are still `unknown` (see each `CALIBRATION.md`).

**Faces at any canvas other than 212×520 are experimental on a device until F1 has been
photographed on it** (the spec's `face.status` says `experimental` or `verified`). On a new device,
install **F1 alone first**; if AstroBox or the device refuses it, stop and record how (the next
step would be comparing a stock face's header with ours). Round screens have only been exercised
on synthetic photos; screens narrower than 212 px aren't supported by the face kit.

## Measuring (no build needed)
From the workspace root (`--workspace DIR` or `MIBAND_WORKSPACE` to point elsewhere):
```sh
F="${CLAUDE_PLUGIN_ROOT}/tools/face-calib"
python3 "$F/measure_face.py" run devices/<model>/photos/face/*.jpg --device <model> --dry-run   # look first
python3 "$F/measure_face.py" run devices/<model>/photos/face/*.jpg --device <model>
python3 "$F/measure_face.py" show --device <model>
python3 "$F/measure_face.py" set lua.timer_runs true --device <model> --source "F6 watched, <date>"
python3 "$F/measure_face.py" selftest          # synthetic check of the measurer, ~6 minutes
```
It writes only the `face` key of the workspace's `devices/<model>/profile.json` (seeded from the
shipped default on first write; the quick-app kit owns the rest), per-photo
`devices/<model>/evidence-face/*.json` (commit these) and `devices/<model>/results-face/`
(gitignored). The profile's face section is rebuilt from all face evidence, newest photo per page
winning. Observations recorded with `set` are never overwritten by a photo run. It reuses the
quick-app kit's `measure.py` read-only.

## Building the calibration faces (needs a workspace copy)
Pre-built sources for the Band 11 and Band 10 Pro are in the kit's `faces/<id>/`; other devices get
theirs from `gen.py <id>` (or `new-device.mjs`) in the workspace copy. Packaging writes `dist/` next
to them, so it refuses to run inside the plugin. Once per workspace (both scripts are idempotent):
```sh
"${CLAUDE_PLUGIN_ROOT}/skills/new-project/setup-toolkit.sh"    # band10-toolkit, idempotent
"${CLAUDE_PLUGIN_ROOT}/skills/new-project/copy-kit.sh" face-calib   # idempotent
tools/face-calib/build.sh band11          # or another device id / all -> faces/<id>/f*/dist/*.bin
```
`pack.mts` imports the workspace's `vendor/band10-toolkit`. **Bump `KIT_BUILD` in `gen.py` whenever
a page changes** (every face id is `8<digit><build:5><face:2>`, the digit being the spec's
`face.id_digit`: 1 Band 11, 2 Band 10 Pro, 9 synthetic test specs, others assigned by
`new-device.mjs`; the band ignores a reinstalled id).

## Installing and photographing
- Install with the `sideload` skill; all pairing rules apply. One install per face; select it on the
  band, photograph, go to the next.
- **Custom-face cap:** a Band 11 holds about 6 custom faces (`ExceedQuantity` on the 7th), counting
  the user's own; a Band 10 Pro accepted all 8 calibration faces. Install the calibration faces in batches, photograph them, delete them, then
  install the rest.
- Photo rules (kit README): no flash, main camera at 1×, the screen filling at least a third of the
  photo width, both rulers + the yellow bar + the barcode in frame. For the always-on pairs (F7, F8)
  **lock AE/AF** on the normal view, keep still, let the band dim, shoot again; `measure_face.py`
  refuses the dim ratio when EXIF exposure × ISO differ by more than 5 %.
- Watch-only facts (seconds ticking, Lua timer, AOD behaviour, 12/24-hour setting): record with
  `measure_face.py set` (table in the kit README).

## Afterwards
Delete every calibration face from the band (AstroBox → Watchfaces → each "Calib F… b<build>" →
⋯ → Uninstall; never the stock faces), select the user's normal face again (from
`devices/DEVICES.md`), and hand the band back to Mi Fitness as usual. Update the model's
`CALIBRATION.md` in the workspace (`devices/<model>/CALIBRATION.md`; start from the shipped one)
and `devices/DEVICES.md`.
