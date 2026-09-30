---
name: build-face
description: Build or change a Xiaomi Smart Band 10 / 10 Pro / 11 (or other Vela device) watch face with band10-toolkit or the pack.mts packer (face IDs, number and image-list widgets, the Lua layer, image formats, colour floor, the notification dot, always-on, the custom-face cap). Use for any watch face design, generator, build or on-device fix.
---

# Building watch faces

Design first: mock the face (every state: normal, always-on, notification dot, extreme values) and
get the user's approval before touching the generator (see the agent's "Design first" rule).

## The toolkit and the build
- Faces (`faces/<name>/` in the workspace) are band10-toolkit projects: `manifest.json`,
  `layout.json`, `assets/`, optional `script/`. Faces made by a generator script: **edit the
  generator, not its outputs.**
- One-time setup (clone, pin, patch, `npm install`, `faces/package.json`):
  `${CLAUDE_PLUGIN_ROOT}/vendor/README.md`. The toolkit lives in the workspace's
  `vendor/band10-toolkit/`, never in the plugin.
- Generate: `cd faces && npx tsx <name>/generate.ts`. Build: `cd faces && npm run
  validate|build|package -- <name>` (or from the workspace root `npm --prefix vendor/band10-toolkit
  run band10 -- package faces/<name>`); output `faces/<name>/dist/<name>.bin`. Studio preview:
  `npm run preview -- <name>`, opened in the user's browser. The studio renders the toolkit's
  assumptions; only the band is the truth.
- **The toolkit is third-party** (upstream + the patch). Change it only in the workspace clone, then
  refresh the patch (`git -C vendor/band10-toolkit diff > vendor/patches/band10-toolkit.patch`) and
  commit it in the workspace. Never reset or update the clone without saving the diff first. Don't
  put your faces in its `examples/`.
- **Canvas sizes:** band10-toolkit builds only 212×520 (Band 10 / 11). Other canvases (Band 10 Pro
  336×480, round watches) are packed with the same native packer by
  `${CLAUDE_PLUGIN_ROOT}/tools/face-calib/pack.mts` (see how `build.sh` there calls it). Verified on
  the Band 10 Pro (all 8 calibration faces accepted and measured, 2026-09-29); on any other device a
  face is **experimental until F1 of the face kit has been photographed on it** (its spec's
  `face.status`). Round screens have only been exercised on synthetic photos.
- Install: the `sideload` skill.

## Rules learned on the device
- **Bump `manifest.json` `id` for every build.** Reinstalling an existing ID is silently ignored.
- **After each install, delete every older iteration of that face from the band** (AstroBox →
  Watchfaces → tile ⋯ → Uninstall), keeping only the newest build. Do this without asking. Never
  remove the stock/original faces.
- **The Band 11 holds about 6 custom (sideloaded) faces.** A 7th install is refused with
  `ExceedQuantity` (face calibration, 2026-09-29: 5 accepted, a 7th refused). Store faces don't
  count, so deleting them doesn't help. Before installing, count the custom faces on the band and
  uninstall old iterations or calibration faces first. The Band 10 Pro accepted all 8 calibration
  faces (at least 8; its cap is unknown).
- **Number widgets re-centre on the digits actually drawn** (Band 11 face calibration, 2026-09-29):
  a `center` widget is centred on its x, a `right` one ends at x; spacing is signed; no zero padding
  unless leadingZero.
- **The Lua layer** is for layouts widgets can't express (a proportional-width centred time, mixed
  images): `script/main.lua` plus images, packed as a type-5 element;
  `dataman.subscribe("timeHourHigh"|"timeHourLow"|"timeMinuteHigh"|"timeMinuteLow"|"dateWeek"|"dateDay", …)`,
  values are ×256. Lua also runs on the always-on face (F8, 2026-09-29), but the toolkit patch only
  puts `script/` on the normal face, so an AOD script needs `${CLAUDE_PLUGIN_ROOT}/tools/face-calib/pack.mts`-style
  packing.
- **Image lists:** a value below the first frame shows the first frame; above the last, the last;
  an in-between value shows the frame at or below it (fallback `floor`, measured on the Band 10 Pro;
  the Band 11 couldn't tell yet).
  All frames in an image list must be the same size. For a short value that must stay centred with
  an icon (battery 0–100), pre-render every value as one centred image-list frame instead of a
  number widget; centre small units (%) on the digit cap height, not the baseline.
- **Lua images:** PNG (RGBA, PNG8 + tRNS, grey + alpha, RGB) and LVGL v9 ARGB8888 `.bin` render
  correctly on the Band 11; LVGL v8 true-colour-alpha (32/16 bit) and v9 RGB565 render garbled
  there. On the Band 10 Pro, LVGL v8 true-colour-alpha 32-bit `.bin` also draws correctly (16-bit
  doesn't show). Read `face.lua.image_format` for the device; prefer PNG. `Image:set{zoom=512}`
  scales; `scale` does nothing.
- **Data sources:** the hour source follows the band's 12/24-hour setting. °F is source
  `temperatureF` (`40009031`, packed as `D031`).
- **Colour floor:** read `face.colour.floor` from the profile, never a fixed number. Band 11 faces
  (photos 2026-09-29): `#10` and up distinct from black on every grey ramp (`#08` is black; red/blue
  `#20`, green `#30`), replacing an earlier by-eye rule of about `#40`; confirm by eye before relying
  on anything under about `#20`. Band 10 Pro faces: `#18` on every grey ramp (red/blue `#30`, green
  and surfaces `#20`). Quick apps are a different renderer (`quickapp.colour.floor`); never use one
  for the other.
- **The notification dot:** the Band 11 draws a red dot over the face when there are unread
  notifications: about 18 px across, centred at (106, 14), bottom at y 24
  (`face.screen.status_clear_top_px` = 25). Keep the top 25 px clear of anything important and
  don't put red there; content can start around y 30–44 (reserving the top 85 px wasted space).
  The Band 10 Pro draws the same kind of dot, about 19 px across centred near (168, 23):
  `status_clear_top_px` = 33, so keep its top 33 px clear.
- Always-on on the Band 10 Pro, and its Lua timer and seconds updates, are still `unknown`: observe
  or measure (`calibrate-face`) before a face depends on them.
- Any `face` fact that is `unknown` must be measured with a face (`calibrate-face`) before a face
  depends on it. Never use a `quickapp` fact for a face.

## Checking on the device
Ask the user for a photo of the band, then pull only the newest one
(`adb shell ls -t /sdcard/DCIM/Camera/ | head -1`). Keep the design mock-ups in sync with what
landed, and record the installed ID in `PROJECT.md` and `devices/DEVICES.md`.
