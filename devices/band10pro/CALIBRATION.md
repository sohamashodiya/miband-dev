# Band 10 Pro calibration

- Profile: `profile.json` (schema `vela-device-profile/2`), firmware **3.101.043**.
- Evidence: `evidence/*.json` (committed, one per photo); photos in `photos/` (gitignored, local only).
- Kit: `tools/vela-calib` (code; see its `README.md` for the photo procedure).

## Status (2026-09-28)
- **quickapp: measured.** Vela Calib 1.0.0, 17 photos on 2026-09-27 (IMG20260927202514-202836), plus the
  two BART calibration photos (`calib.jpg`, `calib2.jpg`, BART 2.0.11/2.0.12 screens). Line box, ink,
  box regimes, digit and space widths, screen edges and corner radius (~47 px), colour floor, CSS
  verdicts, image and animation observations. Still unknown: `animation.class_swap_restarts`,
  `animation.image_src_swap_restarts`. Letter widths are still `assumed` (font files).
- **face: unknown.** No watch face has been built or photographed on this model. Every fact in the
  `face` section is `unknown`; measure before building a face for the Band 10 Pro.
- Known 1.0.0 layout bugs to fix in the next kit version are listed in `tools/vela-calib/PROJECT.md`.

## Commands
```sh
cd tools/vela-calib
python3 measure.py run ../../devices/band10pro/photos/*.jpg     # rebuild the profile from all evidence
python3 measure.py show                                          # every fact and its status
python3 measure.py set animation.class_swap_restarts true --source "anim page, <date>"
node export.mjs band10pro ../../apps/bart-watch/band/src/common/device.js   # or: npm run device in the app
```

## After a firmware update
Re-run the whole kit, compare the new profile with the old one (`git diff`), update
`firmware.version`, then rebuild every band app for this model (their `device.js` regenerates).
