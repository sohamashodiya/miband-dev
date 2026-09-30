# Calibrating a device (template)

Every device's notes live in `devices/<id>/CALIBRATION.md`. `node tools/vela-calib/new-device.mjs <id> ...`
writes one from the template below (placeholders in `{{...}}` are filled in), next to the device spec
(`device.json`) and the seeded profile (`profile.json`). Keep it current: status first, then what the
photos showed, then what is still open. The plugin's `data/profiles/band11/CALIBRATION.md` is a filled-in example.

In the miband-dev plugin this template ships as `data/CALIBRATION.md`; `new-device.mjs` writes the filled-in
copy into your workspace. `tools/...` below are the workspace copies of the kits.

<!-- TEMPLATE START -->
# {{NAME}} calibration (`{{ID}}`)

**Status ({{DATE}}): onboarded, nothing measured.** Spec `device.json` is unverified (from the
maker's spec); profile `profile.json` seeded with every fact `unknown`. Nothing has been installed
or photographed.

- Screen: {{W}} x {{H}} px, {{SHAPE}}, {{DIAG}}, {{PPI}} (spec; the geometry page measures the
  visible outline).
- Firmware: {{FIRMWARE}}. The profile's `firmware.version` is the firmware its facts were measured
  on; after a firmware update, re-run the kits and compare.
- Quick-app kit: Vela Calib 2.0.0, {{PAGES}} pages (0 start, {{GEO}} Screen geometry, {{ANIM}}
  Animation), layout `tools/vela-calib/layouts/{{ID}}.json`, built as
  `tools/vela-calib/dist/com.soham.velacalib.{{ID}}.debug.2.0.0.rpk` (designWidth {{W}}).
- Faces: {{FACE_STATUS}}. Pages in `tools/face-calib/faces/{{ID}}/`.

## Quick app (`quickapp` section)
1. `cd tools/vela-calib && npm run build -- {{ID}}`, then install the rpk through AstroBox
   (the `sideload` skill's `sideload.sh`; every pairing prompt is the user's to accept).
2. Open Vela Calib. Page 0 prints a yellow `@system.device` line: note the screen size and shape it
   reports and compare them with `device.json`.
3. Photograph pages **{{PHOTO_PAGES}}** (not {{ANIM}}) into `devices/{{ID}}/photos/` (gitignored), one
   photo each (`tools/vela-calib/README.md` "Photo procedure"):
   - phone portrait, straight on, no flash, no reflections, main camera at 1x (2x if it can't focus);
   - close: at least 2.5 photo px per band px;
   - both rulers, the yellow bar and the barcode in frame (on a round screen the rulers are the two
     tick columns inside the circle);
   - page {{GEO}} (Screen geometry): also note whether the system draws anything over the app.
4. Page {{ANIM}} (Animation): watch ~20 s; per lane, does the square reach the end (marker), jump back
   early, stop or step?
5. `cd tools/vela-calib && python3 measure.py run ../../devices/{{ID}}/photos/*.jpg --device {{ID}}`.
   Check `device.design_scale` ~1.00-1.03 and `one_to_one: true`. If not, stop: the design width is
   wrong for this device and every fact would be in the wrong units.
6. Record observations with `python3 measure.py set <path> <value> --device {{ID}} --source "..."`
   (animation lanes A-H, `screen.system_overlay`, `behaviour.system_back_swipe_single_page`).
7. When the photos confirm the spec, set `"verified": true` in `device.json`.

## Watch face (`face` section)
Faces other than the Band 10 / 11's 212 x 520 are packed by `tools/face-calib/pack.mts` and are
**experimental on each device until F1 is photographed on it.**
1. `tools/face-calib/build.sh {{ID}}`.
2. Install **F1 alone first** and check it installs and draws. If AstroBox or the device rejects it,
   stop and record how (the format for this device is then unknown; compare a stock face's header).
3. Then the rest in batches (a Band 11 holds about 6 custom faces; count them first), one photo per
   page (F7 and F8 also in always-on, exposure locked), and
   `python3 tools/face-calib/measure_face.py run <photos> --device {{ID}}`.
4. Delete the calibration faces afterwards (never the stock faces).

## What the photos showed
(nothing yet)

## Still open
- Everything in `profile.json` (`python3 tools/vela-calib/measure.py show --device {{ID}}`).
