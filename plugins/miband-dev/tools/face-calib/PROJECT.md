# Face calibration kit: project notes

Read this before working on the kit. It applies only to the kit; the facts it measures live in
`devices/<model>/` and apply to every face on that model.

## What and who
- A developer tool: calibration watch faces of test patterns for the face engine, and
  `measure_face.py`, which turns photos of them into the `face` section of a device profile. The
  user takes the photos. See `README.md` for the faces, the photo procedure and the facts.
- Style: measurability only. Black ground, white ink, saturated pink/cyan/green markers that are
  never white, yellow only for the ruler 100s and the scale bar. No design mock-ups (test patterns,
  like `tools/vela-calib`).

## Devices
- Band 11 / Band 10 (212 × 520 capsule): `band11`. Output: the `face` key of
  `devices/band11/profile.json` (the rest belongs to the quick-app kit). Until 2026-09-29 it was a
  face-only `profile.face.json`; merged into `profile.json` and removed.
- Band 10 Pro (336 × 480): `band10pro`. Output: the `face` key of `devices/band10pro/profile.json`.
  **Faces for this model are unverified**: band10-toolkit only targets the Band 10 (`o66`); the kit
  packs 336 × 480 faces with the toolkit's native packer directly (`pack.mts`). Install F1 alone
  first.

## Code
- `gen.py` generates everything under `faces/` and `layouts/` (don't hand-edit). `KIT_BUILD` is in
  every face id (`8<model><build:5><face:2>`); bump it whenever a page changes.
- `build.sh`: Band 11 through the toolkit CLI; Band 10 Pro and F8 (Lua on AOD) through `pack.mts`.
- `measure_face.py` imports `tools/vela-calib/measure.py` read-only (another kit, another owner).

## State
- 2026-09-28: build 1 generated, packaged for both models (16 `.bin`), selftest PASS (both models,
  two synthetic truths).
- 2026-09-29: Band 11 F1-F5 photographed and measured (below). F6-F8 not installed yet (ExceedQuantity).
- Unknowns before the first photos: whether the Band 10 Pro accepts these faces at all; whether an
  AOD script element is harmless (F8); whether `root:Label`, `root:Object`, `lvgl.Timer`, `zoom` /
  `scale` exist in the band's Lua binding (all wrapped in pcall, so a missing one shows a pink
  status square rather than stopping the script).

## First Band 11 run (2026-09-29, a Band 11, fw 4.100.139, phone main camera, macro focus)
- **Install limit: ExceedQuantity.** Round 1: with one everyday face + F1-F5 installed (6 custom faces), F6
  was refused with `ExceedQuantity` (a 7th). Round 2: after deleting F1-F4, F6, F7, F8 installed
  (5 custom: the everyday face, F5-F8). So the cap is about 6 custom faces: 5 accepted, the 7th refused, 6
  itself not tested on its own. Install in batches and delete each batch before the next.
- **Why F2-F5 first failed to measure (kit bug, fixed in measure_face.py; photos were fine):** the
  photos have the band lying sideways. `vm.Fit` (tools/vela-calib) takes the scale bar's direction
  from PCA and forces it to point right in the photo (`u[0] > 0`); with a vertical bar `u[0]` is ~0,
  so the sign follows the slightest tilt. F1 happened to come out right. In F2-F5 it flipped, the
  similarity was 180 degrees off, and on the symmetric capsule the fit locked onto the wrong ticks
  (16 ticks, rms 3.2 px, "6-7 px per band px"). `measure_photo` now tries the photo in all four
  orientations and keeps the best fit (the barcode must read in it). Result: all five fit
  (rms 0.23-0.36 px, 66-76 ticks, 4.5-5.0 photo px per band px); the selftest now also photographs
  pages sideways both ways.
  The same cause explains quick-app kit pages 11, 14, 21 (they fit and read once turned upright). Its
  page 19 (Screen geo) is different: that page draws its text in **yellow**, which derails the bar and
  tick detection in any orientation.
- Other measure fixes from the real photos: colour names tolerant of the camera (the band's green
  #3CFF3C photographs as about (25, 214, 140); greys and white come out bluish); status squares judged
  by the dominant channel; the tile hole judged by luma against the white quadrant; the top-strip
  overlay ignores glare (only compact blobs inside the screen count; the photos had specular arcs
  and no status dot); the colour floor threshold is max(6, 2 sd), and `colour.floor.grey` is the
  lowest of the three grey ramps, because glare lifted one ramp's black swatch; F5's number regions
  no longer include the neighbouring widget's outline (a layout-only change, the faces are unchanged).
- **Measured (now the `face` key of devices/band11/profile.json), findings that change what we assumed:**
  - Colour floor: **#10** on all three grey ramps (background image, BGRA32 image, Lua fills); #08 is
    black. The old "below about #40 shows black" does not hold in this photo; confirm by eye before
    changing face palettes. Red #20, blue #20, green #30.
  - **Number widgets re-centre on the digits drawn**: steps 1368 in a 5-digit centre widget is centred
    on x, and a right widget ends at x (`number_anchor_fixed: false`). Spacing is signed (+6 -> 5.8,
    -3 -> -3.1). No zero padding; the % unit follows the last digit (gap ~1 px).
  - Lua images: PNG RGBA, PNG8+tRNS, grey+alpha and RGB PNG all correct, and **LVGL v9 ARGB8888 .bin
    correct**; v8 true-colour-alpha (32 and 16 bit) and v9 RGB565 garbled. `zoom = 512` scales,
    `scale = 512` doesn't (no error). Lua object fills work.
  - Image lists: a value below the first frame shows **the first frame** (not nothing); above the last
    shows the last; steps 1368 -> the 1000 frame; weekday Sunday = 0; month 1-based. Battery was 100,
    so floor/nearest/ceil can't be told apart yet (retake F5 at a battery level that isn't a multiple of 20).
  - Visible area: capsule end radius ~105 px, ends centred at x 105.7-106.0; hidden edges 0-1.2 px.
  - Hour widget showed 8 at 20:06: the band was on 12-hour time.

## Round 2 (2026-09-29, F6-F8, daylight, band upright, 2.8-3.5 photo px/band px)
- F6 measured as is. F7 normal, F7 AOD (handheld), F8 normal and F8 AOD first failed with "0 yellow
  ruler ticks": daylight on a tan table with an orange frame outscored the rulers on "yellow", and
  vm.Fit's thresholds are percentiles of the whole photo. **Kit fix:** `isolate_screen()` finds the
  band's dark screen (the largest dark region, content holes filled, convex hull), and the fit runs on
  the photo with everything outside it blanked. The hull isn't grown: a sliver of the white case
  lifted the brightness percentile above the dim AOD ticks. The mask only guides the fit; the
  unmasked photo is rectified (the first version clipped the status dot). The selftest's truth B now
  has that daylight backdrop. All 10 photos fit (rms 0.23-0.36 px).
- Status dot: detected with the max channel (red has little luma), on every normal page except F1,
  compact blobs over 12 px^2 only (glints are a few px). Red, centred (106, 14), 19-20 px with bloom,
  bottom at y 24.1 on F6, F7 and F8 -> `status_clear_top_px` 25. Not seen in round 1 (no unread
  notification then).
- AOD pair not exposure-locked (F7: 1/142 s ISO 155 vs 1/105 s ISO 50; F8: 1/1266 s ISO 432 vs
  1/94 s ISO 25): `aod.dim_ratio` stays unknown with the raw numbers and the within-photo level
  shape recorded (AOD: #808080 0.57 and #C0C0C0 0.84 of #FFFFFF; normal-view white clipped in the
  camera). Retake F7 with AE/AF locked and matching EXIF.
- Observations recorded by the main session with `set` (timer_runs, label_draws, aod.shows,
  aod.second_updates, lua.runs_on_aod, screen.system_overlay) are protected: a photo run never
  replaces a measured fact whose source isn't this kit's photos; it adds `photo_check` instead
  (both agree: the Lua and image squares are both drawn in the F8 AOD photo).
- `lua.dataman_scale` untested: F6 was shot at :50 (minute-low 0, raw 0).
