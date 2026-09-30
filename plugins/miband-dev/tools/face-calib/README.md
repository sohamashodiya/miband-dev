# Face calibration kit

> **In the miband-dev plugin** this kit is read-only. The measure scripts run from here and read and
> write only your workspace (`--workspace DIR`, `MIBAND_WORKSPACE`, or the nearest folder with a
> `devices/` folder): `devices/<model>/profile.json` (created from the plugin's default in
> `data/profiles/<model>/` on the first write), `evidence*/`, `results*/`. Generating and building
> write into the kit, so they run from a copy in your workspace (the new-project skill's `copy-kit.sh face-calib`).
> Commands below are written from that copy (`cd tools/face-calib`, photos under `../../devices/`).

Measure how a device's **watch-face engine** draws: its visible area, colour floor, image formats,
number and image-list widgets, the Lua layer and always-on. It writes the `face` section of a
device profile. The quick-app kit (`tools/vela-calib`) measures the Vela JS-app renderer; the
face engine is a different renderer, so its facts are measured here with faces. Every device comes
from its spec, `devices/<id>/device.json` (face canvas, shape, face id digit, builder, status; see
`tools/vela-calib/README.md` "Device spec"); onboard a new one with `tools/vela-calib/new-device.mjs`.

| Piece | What it is |
|---|---|
| `gen.py` | Generates every calibration face (`faces/<model>/f<N>-<slug>/`, band10-toolkit projects) and `layouts/<model>.json`, the list of every sample and where it is, from the device's spec (`gen.py <id>`, `--spec PATH`, `--out DIR`) |
| `build.sh` | `gen.py`, then validate + package every face into `faces/<model>/f*/dist/*.bin` (`build.sh <id>`; default every device with a layout here) |
| `pack.mts` | Packs a face with the toolkit's native packer directly, for faces the toolkit CLI can't make (below) |
| `measure_face.py` | Reads the photos, writes the `face` facts; `selftest` renders every page synthetically and checks the facts come back |
| `devices/<model>/evidence-face/*.json` | Per-photo measurements (committed). Photos go in `devices/<model>/photos/face/` (gitignored) |

## Devices and sizes: experimental until photographed

band10-toolkit only targets the Band 10 (`o66`): its layout schema requires a 212 × 520 canvas,
its validator clips to 212 × 520, and its FPRJ output says `DeviceType="466"`. The **binary it
packs has no resolution or device field** (magic `5AA53412`, device flags `0x800`, id, name, then
element tables with x/y). So `pack.mts` builds every other canvas size from the same `wfDef.json`
through the same `packGmfDirectory()`.

- **Band 10 / 11 (212 × 520):** band10-toolkit's own target; faces install and draw (Band 11
  calibrated 2026-09-29).
- **Band 10 Pro (336 × 480): verified 2026-09-29.** The band (fw 3.101.043) accepted all 8
  pack.mts faces and they were photographed and measured (its profile's `face` section).
- **Every other device: EXPERIMENTAL until F1 is photographed on it.** Whether AstroBox and that
  device accept a face made this way is unknown; its spec's `face.status` stays `experimental`
  until then. Install **F1 alone first** and see if it installs and shows. If it's rejected, stop:
  the next step would be to pull a stock face `.bin` for that device and compare its header (device
  flags at `0x10`, face count/style fields) with ours.
- **Screens narrower than 212 px** (Band 9: 192 px) aren't supported: the pages' content needs
  164 px between the rulers, so `gen.py` refuses them (a compact page set would be needed).
- **Round screens** (Watch S3 / S4 / S5, 466-480 px) are supported: the rulers are two straight
  tick columns inside the circle (as in the quick-app kit), and F1 fills everything outside them so
  the lit outline is the whole circle (`round` sample, fitted by the quick-app kit's
  `measure_round`).

## Build

```sh
tools/face-calib/build.sh            # both models (or: band11 / band10pro)
python3 tools/face-calib/measure_face.py selftest
```

Devices whose spec says `builder: band10-toolkit` (the Band 10 / 11) go through the toolkit CLI
(`validate` + `package`, like any face project). Every other canvas size and F8 (which puts the Lua
layer on the always-on face, which the toolkit's patch never does) go through `pack.mts`. `pack.mts`
output for a Band 11 face has the same element table as the CLI's (checked on F4, F6, F7). **Bump
`KIT_BUILD` in `gen.py` whenever a page changes**: every face id is `8 <device digit> <build, 5
digits> <face, 2 digits>` (the digit is the spec's `face.id_digit`: 1 Band 11, 2 Band 10 Pro, 9 the
synthetic test specs, others assigned by `new-device.mjs`; build 1: Band 11 `810000101`-`810000108`,
Band 10 Pro `820000101`-`820000108`), and the band ignores a reinstalled id.

Frames: the Band 11's and Band 10 Pro's are pinned in their specs (`calib.face.frame`). Any other
device gets one computed by `gen.py`: the content block (164 × 330 px) centred between the rulers
as high as the outline allows (y >= 44), the barcode and a 150 px bar under it, everything 4 px
inside the outline.

## The faces

Each face is one "page" (a face can't take taps). F7 and F8 also have an always-on view, which is
a page of its own (its own barcode). Every page has the quick-app kit's frame: rulers down both
edges (1 px tick every 10 px, 14 px every 50, 22 px and **yellow** every 100; tick top = y; on a
round screen two tick columns inside the circle), a
**yellow scale bar** (Band 11: 150 × 4 at (31, 404); Band 10 Pro: 200 × 4 at (110, 456)), and an
8-cell **barcode** (on, page number in 5 bits, parity, on). On the Band 11 capsule the bar, barcode
and all samples stay on the straight part (y 106–414), clear of the semicircular ends. Digit and
list cells have a pink outline and carry their value in 4 grey bit squares, so the photo can be
read without OCR. The top strip (y < 42) is left black on every page, so anything drawn there is
the system's.

| Face | Name in AstroBox | Page | What it measures |
|---|---|---|---|
| F1 | Calib F1 Geometry b1 | 1 | Visible area as the face engine draws it. Capsule (Band 11): grey fills in both ends (circle fit: end radius and centre), 1 px combs at the top and bottom centre (hidden rows); rounded rectangle (Band 10 Pro): 48 px white corner squares (1.2 x the radius when larger; corner radius) and combs; circle: grey fills all round outside the rulers (circle fit: radius, centre, all four hidden edges). Rect / capsule: ruler tick ends give hidden columns (on every page) |
| F2 | Calib F2 Colour b1 | 2 | Colour floor: grey #00–#60 step 8 three ways (in the 256-colour background image, in a >256-colour BGRA32 image, as Lua object fills), red/green/blue #10–#80, surfaces #20–#48 |
| F3 | Calib F3 Images b1 | 3 | Widget layer: a 256-colour and a >256-colour PNG tile (the toolkit's two encodings), 50 % pink over white (alpha over another element), alpha ramp over black vs the opaque grey ramp. Lua layer: PNG RGBA / PNG8+tRNS / grey+alpha / RGB, LVGL v8 true-colour-alpha 32 and 16 bit, v9 ARGB8888 and RGB565 `.bin`, and a PNG with `zoom = 512` and `scale = 512`. Tiles are white/red/green/blue quadrants with a transparent (cyan under alpha 0) hole: tells correct, red/blue swapped, garbled, missing, alpha honoured or ignored |
| F4 | Calib F4 Numbers b1 | 4 | Number widgets: steps (5 digits) aligned left / centre / right (cyan marks = x), battery centre with a % unit, minute with leading zero + hour without + second, steps with spacing +6 and −3. Tells whether alignment follows the digits drawn or a fixed slot of `digits` cells, the real spacing, zero padding, unit gap |
| F5 | Calib F5 Lists b1 | 5 | Image lists: battery frames at 0/20/…/100 (which frame for an in-between value: floor / nearest / ceil), frames only at 101/102 (value below the first frame) and only 0/1 (above the last), weekday, month, steps frames 0/1000/5000/10000; battery, day, hour, minute numbers for the true values (checked against the photo's EXIF time) |
| F6 | Calib F6 Lua b1 | 6 | Lua layer vs widgets: placement targets side by side (Lua at x,y vs widget at x,y), `lvgl.HOR_RES()/VER_RES()`, Lua hour/minute from `dataman` beside widget hour/minute, the raw `timeMinuteLow` value (the ×256), a Lua `Label`, Lua object fills, a Lua timer. Green/pink status squares (right column) say whether each pcall returned |
| F7 | Calib F7 AOD b1 | 7 normal, 8 always-on | Same grey ramp, #80/#C0/#FF swatches and hour/minute/second/battery numbers in both views: AOD dimming ratio, AOD colour floor, what AOD shows |
| F8 | Calib F8 AOD Lua b1 | 9 normal, 10 always-on | A green square drawn as an image (left) and by Lua (right) in both views: does Lua run on always-on |

## Photo procedure

Install the faces through AstroBox (`tools/sideload.sh <bin>`; all the usual pairing rules apply).
One install per face; select it on the band, photograph, go to the next. On the Band 10 Pro,
install F1 first and check it shows before the rest.

1. **Room:** ordinary indoor light, no lamp or window reflecting in the band's glass. **No flash.**
2. **Phone:** portrait, main camera at 1× (not ultra-wide, portrait or night mode).
3. **Band:** upright, flat on a table, screen facing the phone. Straight on, centred; a little
   tilt is corrected from the rulers.
4. **Close:** the screen fills at least a third of the photo's width.
5. **Everything in frame:** both rulers, the yellow bar and the barcode.
6. **Focus/exposure:** tap the band's screen on the phone; if white looks blown out, drag
   exposure down a step.
7. Photograph each face's normal view right after selecting it (the barcode tells the pages apart;
   order doesn't matter; a retake replaces the older photo).
8. **F7 (always-on):** turn on always-on display on the band first. Photograph the normal view,
   then **lock exposure and focus** (long-press the band on the phone screen until "AE/AF lock"),
   keep the phone still, let the band dim, and photograph the always-on view. The dim ratio is only
   valid if exposure was locked.
9. **F8:** as F7: normal view, then the always-on view.

The band may lie in any orientation in the photo (upright, or sideways either way): `measure_face.py`
tries all four and keeps the best ruler fit.

**Install limit:** a Band 11 refused a 7th custom face with `ExceedQuantity` and accepted 5
(6 untested): a cap of about 6 custom faces, counting the user's own. Install the calibration faces
in batches, photograph them, delete them, then install the rest.

**Backgrounds and light:** the photo can be taken on any surface; the measure isolates the band's
dark screen first (a tan table or orange frame in daylight used to swamp the yellow-ruler detection).

**Always-on pairs (F7, F8):** the dim ratio needs identical exposure. Lock AE/AF on the normal view,
don't move, let it dim, shoot. `measure_face.py` compares EXIF exposure time x ISO and refuses the
ratio if they differ by more than 5 %.

Then copy the photos into `devices/<model>/photos/face/` and:

```sh
cd tools/face-calib
python3 measure_face.py run ../../devices/band11/photos/face/*.jpg --device band11 --dry-run   # look first (any onboarded device id)
python3 measure_face.py run ../../devices/band11/photos/face/*.jpg --device band11
python3 measure_face.py show --device band11
```

`results/` gets the rectified image of each photo for a visual check (gitignored).

## Watch, don't photograph

Record these with `measure_face.py set <path> <value> --source "<what you saw, date>" --device <model>`:

| Face | Watch for | Fact |
|---|---|---|
| F1 | Anything the system draws over the face (status dot, icons), where, what colour, when (unread notification, disconnected, charging) | `screen.status_overlay` (also detected automatically in the top strip of every page) |
| F4 | Does the seconds number (row 5, right) tick every second? | `widgets.number.second_updates` |
| F6 | Does the small green square right of the grey fills blink once a second? | `lua.timer_runs` |
| F6 | Is "LUA 0123" visible, in what font/size? | `lua.label_draws` (the photo also checks for ink) |
| F7 | After dimming: is the AOD view (barcode p8, "ALWAYS-ON") shown? How long until it dims? Does the seconds number change in AOD; do hour/minute update at the minute? | `aod.shows`, `aod.second_updates` |
| F8 | In AOD: is the right (Lua) square there? | `lua.runs_on_aod` (the photo decides it too) |
| any | The band's 12/24-hour setting (F5 compares the hour widget with the photo's time) | `data_sources.hour_follows_12_24_setting` |

## What it writes

Both models: the `face` key of `devices/<model>/profile.json` (nothing else in that file; the
quick-app kit owns the rest and keeps `face` when it rewrites the file). The Band 11 briefly used a
face-only `profile.face.json`, merged and removed on 2026-09-29. Every fact is `{value, status, source, date}`; the kit seeds any missing fact as
`unknown`. Main facts (paths inside `face`):

| Path | Meaning |
|---|---|
| `screen.hidden_px.{left,right,top,bottom}`, `screen.corner_radius_px`, `screen.capsule_ends`, `screen.corner_detail` | visible area as faces see it |
| `screen.status_overlay`, `screen.status_clear_top_px` | what the system draws in the top strip, and its bottom edge |
| `colour.floor.{grey,grey_rgba32,grey_lua,red,green,blue,surface}` | lowest channel value visibly above black, per encoding/layer |
| `image.encoding.{png_indexed,png_rgba32}`, `image.alpha_over_black`, `image.alpha_over_element` | widget-layer image rendering |
| `lua.runs`, `lua.image_format` (+ `per_format`), `lua.image_zoom`, `lua.api_status`, `lua.placement_offset_px`, `lua.canvas_px`, `lua.dataman_scale`, `lua.time_matches_widget`, `lua.label_draws`, `lua.timer_runs`, `lua.runs_on_aod` | the Lua layer |
| `widgets.placement_offset_px`, `widgets.number.align`, `widgets.number_anchor_fixed`, `widgets.number.{spacing_px,pads_to_count,leading_zero,unit_gap_px,second_updates}` | number widgets |
| `widgets.image_list.{fallback,below_first,above_last,u16_values}`, `widgets.image_list_frames_same_size` | image lists |
| `data_sources.{weekday_sunday_zero,month_one_based,hour_observed,hour_follows_12_24_setting,temperatureF_D031}` | data sources |
| `aod.{shows,dim_ratio,colour_floor_grey,number_widgets,second_updates}` | always-on |

Some verdicts need a lucky live value: alignment is only told apart when fewer digits are drawn
than the widget's `digits` (steps below 10 000, battery below 100); the image-list fallback when the
battery isn't a multiple of 20. The fact then lists every name that fits (`floor|nearest`); retake
later to separate them.

## Afterwards: delete the calibration faces

On the phone, in AstroBox (connected to the band): **Watchfaces** → each tile named
**"Calib F… b<build>"** → ⋯ → **Uninstall**. Delete all eight (and any older build's). Never remove
the stock faces. Then select the user's normal face again on the band (whatever it
showed before; `devices/DEVICES.md` in the workspace records it), and
hand the band back to Mi Fitness as usual.

## Self-test

`python3 measure_face.py selftest` renders every page of the Band 11, the Band 10 Pro and the two
synthetic specs in `tools/vela-calib/test/specs/` (a 466 px circle, a 390 × 450 rounded rectangle;
`--device X` / `--spec S.json` for others) the way a face engine would
(widgets composited in z order, number/image-list widgets filled from simulated live values, the
Lua ops drawn from the same op list `gen.py` turns into `main.lua`, dark values crushed, AOD dimmed,
a status dot, the capsule / rounded / circular mask), photographs it synthetically (keystone, rotation, blur,
noise, 3.2 photo px per band px), measures it and checks the facts. It runs two different "devices"
(truth A: fixed-slot centring, floor fallback, floor #30, some `.bin` formats garbled, no Lua on
AOD; truth B: the opposite choices, floor #40, Lua on AOD) so every verdict has to be read, not
assumed. About 6 minutes for the four devices. It imports `tools/vela-calib/measure.py` (Fit, Rect, barcode, corner,
comb, swatch, ramp, round, ruler_geom) read-only; a change to those functions' signatures there breaks this kit.
