# Known Xiaomi Vela wearables

Which Xiaomi / REDMI wearables run Xiaomi Vela (sold as HyperOS on wearables), what their screens
are, and whether third-party quick apps (`.rpk`) and custom watch faces (`.bin`) can be installed
through AstroBox. Researched 2026-09-29 from the sources below; **not checked on any device unless
the row says so.** Before building for a device, onboard it
(`node tools/vela-calib/new-device.mjs <id>`) and calibrate it: the profile, not this table, is what
layouts use.

In the miband-dev plugin these specs ship as defaults in `data/profiles/<id>/device.json`; a spec in
your workspace's `devices/<id>/device.json` overrides the default, and `new-device.mjs` writes only
there.

A **spec** (`devices/<id>/device.json`) exists for every row marked with an id. Specs for devices
nobody has calibrated have `"verified": false` and no face id digit until they are onboarded.

## Table

| Device | Spec id | px (w x h) | Shape | Diagonal / ppi | Vela | AstroBox: quick apps / faces | Face DeviceType | Face tools | Confidence |
|---|---|---|---|---|---|---|---|---|---|
| Xiaomi Smart Band 10 (+NFC) | `band11` (same screen) | 212 x 520 | capsule | 1.72" / 326 | yes [V] | yes / yes (o66) | 466 | band10-toolkit, Mi-Create, EasyFace | **verified**: Band 11 calibrated, faces from band10-toolkit install and draw |
| Xiaomi Smart Band 11 (+NFC) | `band11` | 212 x 520 | capsule | 1.72" / 326 (ppi not published by Xiaomi; measured scale fits) | yes (AstroBox) | yes / yes (q66) | 666 (inferred) | band10-toolkit (same canvas as the Band 10) | **verified**: calibrated 2026-09-28/29 (quick app and faces) |
| Xiaomi Smart Band 10 Pro | `band10pro` | 336 x 480 | rounded rect (corner ~47 px measured) | 1.74" / 336 | yes (AstroBox) | yes / yes (p67) | 567 (inferred) | EasyFace; tools/face-calib pack.mts | **verified**: calibrated (quick app 2026-09-27; faces from pack.mts accepted and measured 2026-09-29) |
| Xiaomi Smart Band 9 (+NFC) | `band9` | 192 x 490 | capsule | 1.62" / 325 | yes [V] | yes / yes (n66) | 366 | Mi-Create, EasyFace | high (spec + support); the face kit's pages don't fit 192 px yet |
| Xiaomi Smart Band 9 Pro | `band9pro` | 336 x 480 | rounded rect (radius not published) | 1.74" / 336 | yes [V] | yes / yes (n67) | 367 | Mi-Create, EasyFace | high |
| Xiaomi Smart Band 8 Pro | none | 336 x 480 | rounded rect | 1.74" / 336 | yes [V] | not listed in AstroBox | 11 | Mi-Create, EasyFace | medium (no AstroBox path found) |
| REDMI Watch 5 | `redmiwatch5` | 432 x 514 | rounded rect | 2.07" / 324 | yes [V] | yes / yes (o65) | 465 | Mi-Create, EasyFace | high |
| REDMI Watch 6 | `redmiwatch6` | 432 x 514 | rounded rect | 2.07" / 324 | yes (AstroBox, HyperOS 3) | yes / yes (p65) | 565 (inferred) | EasyFace | high on specs, medium on the face id |
| REDMI Watch 4 | none | 390 x 450 | rounded rect | 1.97" / ~302 (calc.) | yes (codename n65) | not in AstroBox's list | 365 | Mi-Create, EasyFace | medium (installs need other tools) |
| Xiaomi Watch S3 | `watchs3` | 466 x 466 | circle | 1.43" / 326 | yes [V] | yes / yes (n62) | 362 | Mi-Create, EasyFace | high |
| Xiaomi Watch S4 47 mm (+eSIM), S4 Sport | `watchs4` | 466 x 466 | circle | 1.43" / 326 | yes [V] | yes / yes (o62; the Sport is grouped with it) | 462 | Mi-Create, EasyFace | high (S4), medium-high (Sport) |
| Xiaomi Watch S4 41 mm | `watchs4-41` | 466 x 466 | circle | 1.32" / 352 | yes (AstroBox, HyperOS 3) | yes / yes | unknown | none listed | high on specs, medium on the id |
| Xiaomi Watch S5 46 mm (+eSIM) | `watchs5` | 480 x 480 | circle | 1.48" / 323 | yes [V] | yes / yes (p62) | 562 (inferred) | EasyFace | high |
| Xiaomi Watch S5 41 mm | none | 466 x 466 (press reports only) | circle | 1.32" / unknown | yes (HyperOS 4) | quick apps listed, no faces yet | unknown | none | medium (no spec until the screen is confirmed) |
| Xiaomi Watch H1 | none | 466 x 466 | circle | 1.43" / 326 | yes [V] | not listed in AstroBox | unknown | none found | medium |
| Xiaomi Watch S1 Pro | none | 480 x 480 | circle | 1.47" / 326 | yes [V] | not listed in AstroBox | 4 | Mi-Create, EasyFace | medium |
| Xiaomi Smart Band 9 Active, REDMI Band 3, REDMI Watch 5 Active / 5 Lite | none | various | rect / rounded rect | | **no**: proprietary RTOS, not in Xiaomi's Vela list | no | 3651 / 3652 (Watch 5 Active / Lite) | Mi-Create (faces only) | medium: out of scope |
| Xiaomi Watch 2 / 2 Pro | none | | circle | | **no**: Wear OS | n/a | n/a | n/a | out of scope |

"Inferred" face DeviceTypes follow the pattern of the confirmed ones (the AstroBox codename with its
letter turned into a digit: n = 3, o = 4, p = 5, q = 6, so Band 10 `o66` = 466); no tool confirms
them. No Xiaomi Smart Band 11 Pro was found.

## What the columns mean for these kits

- **Quick apps** (`tools/vela-calib`): any device with a spec can get a calibration build
  (`npm run build -- <id>` after onboarding). The kit builds with designWidth = the screen width and
  checks the scale from the screen's own outline (capsule ends, corners, or the circle), so a wrong
  assumption shows up in the first photos. Rectangular, capsule and round screens are supported.
- **Faces** (`tools/face-calib`): band10-toolkit only builds the Band 10's 212 x 520 canvas
  (DeviceType 466). Every other size is packed by `tools/face-calib/pack.mts` with the same native
  packer; the binary has no resolution or device field. That worked on the Band 10 Pro (336 x 480,
  all 8 calibration faces accepted and drawn, 2026-09-29). On every other device such faces are
  **experimental until F1 is photographed on it**; the spec's `face.status` says which.
  The face pages need 164 px between the rulers: screens narrower than 212 px (the Band 9's 192 px)
  need a compact page set that isn't written yet. Round screens (S3/S4/S5) fit.
- AstroBox publishes one resource package per device id; a quick app or face built for one screen
  is not accepted as-is on another (e.g. store apps ship separate circle / rect / narrow-rect rpks).

## Xiaomi's own guidance (quick apps)

- Design widths: Xiaomi's examples use 466 (circle) and 336 (rect); recommended design sizes are
  466 x 466 (circle), 336 x 480 (rect) and 192 x 490 (capsule). With no `designWidth` the base width
  is 480 px. These kits always build with designWidth = the screen's width (1 design px = 1 panel px).
- Shapes in media queries and `@system.device` `getInfo().screenShape`: `circle`, `rect`,
  `pill-shaped`. Xiaomi classifies by w/h: circle = 1, rect 0.5 to under 1, capsule over 0.3 and
  under 0.5.
- DPR = ppi / 160.

## Sources

- **[V]** Xiaomi's Vela device table: https://iot.mi.com/vela/quickapp/zh/guide/multi-screens/ (also
  `.../guide/design/multi-screens.html` and `.../guide/framework/style/media-query.html`). It lists
  Watch S1 Pro, Watch H1, Watch S3, Watch S4 Sport, Watch S4, REDMI Watch 5, Band 8 Pro, Band 9,
  Band 9 Pro, Band 10 and Watch S5. Band 10 Pro, Band 11, REDMI Watch 6 and the S4 41 mm aren't in it
  yet.
- **[AB]** AstroBox's device and resource lists: https://github.com/AstralSightStudios/AstroBox-Repo
  (`devices_v2.json`, `devices.json5`, `assets/docs/ResAdptV2.md`, resource counts in
  `index_v2.csv`).
- Face DeviceType ids: Mi-Create, https://github.com/ooflet/Mi-Create (`src/utils/project.py`,
  resolutions in `src/data/devices.json`); EasyFace device list, https://github.com/m0tral/EasyFace.
- band10-toolkit: https://github.com/utsabfdahal/band10-toolkit (`core/types.ts`: DeviceType 466,
  212 x 520).
- Official spec pages, `https://www.mi.com/global/product/<slug>/specs/`: `xiaomi-smart-band-9`,
  `-9-pro`, `-10`, `-10-pro`, `-11`, `xiaomi-watch-s3`, `xiaomi-watch-s4`, `xiaomi-watch-s4-41mm`,
  `xiaomi-watch-s5-46mm`, `redmi-watch-5`, `redmi-watch-6`, `redmi-watch-4`,
  `xiaomi-smart-band-9-active`, `redmi-watch-5-active`, `redmi-watch-5-lite` (they may refuse plain
  fetches; open them in a browser).
- Others: Band 10 Pro https://www.ithome.com/0/953/607.htm; Watch S5 41 mm
  https://www.gizmochina.com/2026/09/23/xiaomi-watch-s5-41mm-launched-specs-price/; REDMI Watch 4
  installs https://blog.iyatt.com/?p=17811; REDMI Band 3
  https://www.gizmochina.com/2024/10/31/redmi-band-3-launched-in-chin/; Watch H1
  https://gadgetsandwearables.com/technical-specs/xiaomi-watch-h1/.
