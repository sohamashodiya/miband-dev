# Band 11 (and Band 10) calibration

**Status (2026-09-29): quick app measured.** Vela Calib 2.0.0, a Band 11 (fw 4.100.139), 23
photos 2026-09-28 plus 4 retakes (`photos/retake1/`), all fitted; evidence in `evidence/`. 141
facts measured (design scale 1:1, capsule ends r = 103.3 / 103.4 px, hidden edges, line box, ink,
regimes, digit / space widths, wrap, CSS, images, colour floors, animation). See
`tools/vela-calib/PROJECT.md` "First Band 11 run". The `face` section is the face kit's.

Paths: `tools/...` are in the miband-dev plugin (`${CLAUDE_PLUGIN_ROOT}/tools/...`, read-only) or in
your workspace copy of a kit; `devices/<model>/...` (photos, evidence, your profile) are in your
workspace. This file ships with the plugin's default profile (`data/profiles/<model>/`).

Still unknown and worth measuring or observing: `screen.system_overlay` (note it on page 19),
`behaviour.system_back_swipe_single_page` / `exit_pattern` (does the system swipe exit a
single-page app on the Band 11?), `font.advance_tracking`, `font.baseline_em` (only derivable),
`text.align` / `natural_box_wraps` / `lines_without_ellipsis` summaries (the wrap facts hold the
data), letter advances (only whole strings measured). `colour.floor.grey` (8) is from a contaminated
row (bloom in 8 px swatches): confirm by eye before relying on anything under ~#20.

- Screen: 212×520 capsule (semicircle ends of radius ~106 px), 1.72", 326 ppi, 16.5 × 40.5 mm (1 band px = 0.078 mm).
- Firmware: 4.100.139 on the measured band (`firmware.version` in the profile).
- Profile: `profile.json`, seeded by `tools/vela-calib/seed-profile.mjs`: screen spec `assumed`,
  firmware set, every other fact `unknown` (except `font.advance_safety`, kit policy).
- Kit: Vela Calib **2.0.0**, `tools/vela-calib/dist/com.soham.velacalib.band11.debug.2.0.0.rpk`
  (designWidth 212; the Band 10 Pro build won't fit this screen). 24 pages.

## Quick app (`quickapp` section)
1. Install the band11 rpk through AstroBox (the `sideload` skill's `sideload.sh`, `ANDROID_SERIAL=<phone serial>`).
2. Open Vela Calib on the band. Page 0 shows a yellow `@system.device` line: it should read
   `screen 212x520 pill-shaped` (or similar). Photograph it once (a photo of page 0 is harmless to
   `measure.py`; read the line by eye and note it).
3. Photograph pages **1–22** into `devices/band11/photos/` (gitignored), one photo each:
   - phone **portrait**, band upright (strap vertical), so the capsule's long side runs along the
     photo's long side; straight on, no flash, no reflections;
   - close: the screen (40.5 mm tall) fills **at least a third of the photo's height, ideally about
     half** (>= 2.5 photo px per band px). Main camera at 1×; if it won't focus that close, 2×
     (not macro, not ultra-wide);
   - the rounded ends are black on most pages; only the straight sides need to be sharp. The
     **yellow bar** (160 px) and the **barcode under it** near the bottom end must be in frame;
   - tap to focus on the screen; lower the exposure a step if the white blooms.
   - Page 19 (Screen geometry, white caps over both ends): also note whether the system draws
     anything over the app (status dot, time) and where.
4. Page 23 (Animation): watch ~20 s or record a video; per lane, does the square reach the right end
   and turn yellow (F: dims), or jump back early / stop / step? Lane A must turn yellow.
5. `python3 "${CLAUDE_PLUGIN_ROOT}/tools/vela-calib/measure.py" run devices/band11/photos/*.jpg --device band11` (from the workspace root),
   then check the geometry line: `device.design_scale` ~1.00-1.03 and `one_to_one: true`. If not,
   the design width is wrong for this band: stop, fix the kit, re-shoot (every fact would be in
   the wrong units).
6. Record observations: `python3 measure.py set animation.lane_A '"..."' --device band11 --source "..."`
   (lanes A-H), `screen.system_overlay`, `behaviour.system_back_swipe_single_page` (does the
   system swipe exit the app?).
7. Letter advances stay `unknown` (only digits and space are measured per glyph; letters come as
   whole strings). Compare the alphabet strings with the Band 10 Pro's before adding a letter table.

Facts needed (at least): `font.line_box_em`, `font.ink.{digit,cap,descender}`, `font.regime.*`,
`font.advance_em` (digits, space, letters), `font.advance_tracking`, `text.*` (wrap, align,
too-wide), `screen.hidden_px.*`, `screen.corner_radius_px` (a capsule: the ends are semicircles),
`screen.system_overlay`, `colour.floor.grey`, the `css.*` verdicts, `image.*`, `animation.*`,
`behaviour.system_back_swipe_single_page`, and `device.design_width` (an app's
`@media (shape: pill-shaped)` scaling).

## Watch face (`face` section)

**Status (2026-09-29): measured.** Face calibration kit build 1 (`tools/face-calib`, faces
F1-F8), a Band 11 (fw 4.100.139), 13 photos in three rounds (`photos/face/`, `photos/face/round2/`, round 3 on 2026-09-30: F6 and F7 again),
evidence in `evidence-face/`, plus observations recorded with `measure_face.py set`. 56 face facts,
47 from photos. `measure_face.py` writes only the `face` key of `profile.json` (the face-only
`profile.face.json` was merged in and removed). See `tools/face-calib/PROJECT.md`.

What the faces showed, against what the earlier faces had suggested:
- **Colour floor #10** on all three grey ramps (background image, >256-colour image, Lua fills); #08
  is black. Not "below #40". Red and blue #20, green #30. Measured by camera: confirm by eye
  before relying on anything under ~#20.
- **Number widgets re-centre** on the digits drawn (`number_anchor_fixed: false`): a centre widget
  is centred on x, a right one ends at x. Signed spacing. No zero padding. Unit ~1 px after the
  last digit.
- **Lua images:** PNG (RGBA, PNG8+tRNS, grey+alpha, RGB) and **LVGL v9 ARGB8888 `.bin`** draw
  correctly; LVGL v8 (32/16 bit) and v9 RGB565 are garbled. `zoom = 512` scales; `scale` doesn't.
  `Label`, object fills and `lvgl.Timer` work. `HOR_RES/VER_RES` = 212 x 520. Lua and widget
  placement agree to 0.3 px.
- **Lua runs on always-on** (F8: the Lua square is drawn in the AOD view). AOD shows the face's own
  AOD view about 4 s after the last touch; the seconds number doesn't update in AOD.
- **Status dot:** a red notification dot, about 18 px across (19-20 px with camera bloom), centred at
  (106, 14), bottom at y 24, drawn over the face when there are unread notifications.
  `status_clear_top_px` = 25.
- Image lists: a value below the first frame shows the first frame; above the last shows the last;
  values above 255 work (steps). Weekday Sunday = 0, month 1-based. The measured band was on 12-hour time.
- Visible area: capsule ends r ~105 px as faces draw them (the quick-app kit fitted 103.3 / 103.4);
  hidden edges 0-1.1 px.
- Custom-face cap: the band refused a 7th custom face (`ExceedQuantity`) and accepted 5; 6 is
  untested. Install calibration faces in batches.

Still open (retake or observe):
- `aod.dim_ratio`: recorded as about 0.5 **by eye**; the F7 photo pairs weren't exposure-locked
  (EXIF 1/142 s ISO 155 vs 1/105 s ISO 50). A pair with AE/AF locked and matching EXIF exposure
  time and ISO would measure it.
- `widgets.image_list.fallback` (battery was 100): retake F5 at a battery level that isn't a
  multiple of 20.
- `lua.dataman_scale`: confirmed ×256 by the round-3 F6 photo (2026-09-30).
- `widgets.number.second_updates` (normal view), `data_sources.hour_follows_12_24_setting` (flip the
  setting and look): observe.
- `aod.colour_floor_grey`: #18 from an indoor round-3 F7 always-on photo (the earlier #30 came from
  a daylight photo with glare lifting black).
