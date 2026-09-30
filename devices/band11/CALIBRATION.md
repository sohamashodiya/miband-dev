# Band 11 (and Band 10) calibration

**Pending: run the kit.** There is no `profile.json` for this model yet. Build no new Band 11 UI
until it exists (a new model is calibrated before UI work).

- Screen: 212×520 capsule, 1.72", 326 ppi, 16.5 × 40.5 mm (1 band px = 0.078 mm).
- Firmware: 4.100.139 on one band; others not recorded yet. Record it in the profile's
  `firmware.version`.

## Quick app (`quickapp` section)
1. `cd tools/vela-calib && node gen/gen.mjs band11` (writes the pages and `layouts/band11.json`),
   add `band11` to the kit's `DEVICES`, bump the kit version, `npm run build`, install through AstroBox.
2. Seed `devices/band11/profile.json` from `devices/band10pro/profile.json`'s shape with the screen
   size filled in and **every other fact `unknown`** (value null), `firmware.version` set.
3. Photograph every page into `devices/band11/photos/`, then
   `python3 measure.py run ../../devices/band11/photos/*.jpg --device band11`.

Facts needed (at least): `font.line_box_em`, `font.ink.{digit,cap,descender}`, `font.regime.*`,
`font.advance_em` (digits, space, letters), `font.advance_tracking`, `text.*` (wrap, align,
too-wide), `screen.hidden_px.*`, `screen.corner_radius_px` (a capsule: the ends are semicircles),
`screen.system_overlay`, `colour.floor.grey`, the `css.*` verdicts, `image.*`, `animation.*`,
`behaviour.system_back_swipe_single_page`, and `device.design_width` (BandLink's
`@media (shape: pill-shaped)` scaling).

## Watch face (`face` section)
Faces are drawn by the watch-face engine, not the quick-app renderer, so they need their own
section and their own calibration face (a band10-toolkit face of test patterns; not built yet).
What the faces have learned on the device so far, to be turned into measured facts:
- colour floor: fills below about `#40` per channel show as black (`face.colour.floor.grey`);
- the Lua layer needs PNG images, raw LVGL `.bin` renders garbled (`face.lua.image_format`);
- always-on can't run scripts (`face.lua.runs_on_aod`);
- number widgets have fixed anchors (`face.widgets.number_anchor_fixed`); image-list frames must all
  be the same size (`face.widgets.image_list_frames_same_size`);
- the hour source follows the 12/24-hour setting; °F is `40009031` → `D031`
  (`face.data_sources.*`);
- keep the top ~40 px clear for the status dot (`face.screen.status_clear_top_px`).
