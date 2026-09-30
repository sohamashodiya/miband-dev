# Band 10 Pro calibration

- Profile: `profile.json` (schema `vela-device-profile/2`), firmware **3.101.043**.
- Evidence: `evidence/*.json` (committed, one per photo); photos in `photos/` (gitignored, local only).
- Kit: `tools/vela-calib` (code; see its `README.md` for the photo procedure).

Paths: `tools/...` are in the miband-dev plugin (`${CLAUDE_PLUGIN_ROOT}/tools/...`, read-only) or in
your workspace copy of a kit; `devices/<model>/...` (photos, evidence, your profile) are in your
workspace. This file ships with the plugin's default profile (`data/profiles/<model>/`).

## Status (2026-09-29)
- **quickapp: measured.** Vela Calib 1.0.0, 17 photos on 2026-09-27 (IMG20260927202514-202836), plus the
  two BART calibration photos (`calib.jpg`, `calib2.jpg`, BART 2.0.11/2.0.12 screens). Line box, ink,
  box regimes, digit and space widths, screen edges and corner radius (~47 px), colour floor, CSS
  verdicts, image and animation observations. Still unknown: `animation.class_swap_restarts`,
  `animation.image_src_swap_restarts`. Letter widths are still `assumed` (font files).
- **face: measured.** Face calibration kit build 1, packed at 336 × 480 by `pack.mts` (band10-toolkit
  only builds 212 × 520): the band (fw 3.101.043) **accepted all 8 faces**, so it holds at least 8
  custom faces. 9 photos on 2026-09-29, evidence in `evidence-face/`. Results:
  - colour floor **#18** on all three grey ramps (red and blue #30, green #20, surfaces #20);
  - a red notification dot about 19 px across centred near (168, 23): `face.screen.status_clear_top_px`
    = **33**, keep the top 33 px clear and don't put red there;
  - corner radius ~47 px as faces draw it, hidden edges about 1 px left and right;
  - Lua runs (also on always-on); Lua images: PNG (RGBA, PNG8, grey, RGB), **LVGL v8 true-colour-alpha
    32-bit `.bin`** and v9 ARGB8888 `.bin` draw correctly; `zoom` scales, `scale` doesn't; dataman ×256;
  - number widgets re-centre on the digits drawn, signed spacing, no zero padding;
  - image lists: an in-between value shows the frame at or below it (**fallback floor**), below the
    first frame the first, above the last the last; weekday Sunday = 0, month 1-based.
  Still unknown: always-on behaviour (`aod.*`), `lua.timer_runs`, `widgets.number.second_updates`,
  `data_sources.hour_follows_12_24_setting`, `temperatureF_D031`: observe or retake before relying on them.
- Known 1.0.0 layout bugs to fix in the next kit version are listed in `tools/vela-calib/PROJECT.md`.

## Commands
```sh
# from the workspace root; K = ${CLAUDE_PLUGIN_ROOT}/tools/vela-calib
python3 $K/measure.py run devices/band10pro/photos/*.jpg --device band10pro   # rebuild your profile from all your evidence
python3 $K/measure.py show --device band10pro                                 # every fact and its status
python3 $K/measure.py set animation.class_swap_restarts true --device band10pro --source "anim page, <date>"
node tools/vela-calib/export.mjs band10pro apps/<project>/band/src/common/device.js   # or: npm run device in the app
```

## After a firmware update
Re-run the whole kit, compare the new profile with the old one (`git diff`), update
`firmware.version`, then rebuild every band app for this model (their `device.js` regenerates).
