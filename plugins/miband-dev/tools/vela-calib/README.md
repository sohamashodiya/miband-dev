# Vela calibration kit

> **In the miband-dev plugin** this kit is read-only. The measure scripts run from here and read and
> write only your workspace (`--workspace DIR`, `MIBAND_WORKSPACE`, or the nearest folder with a
> `devices/` folder): `devices/<model>/profile.json` (created from the plugin's default in
> `data/profiles/<model>/` on the first write), `evidence*/`, `results*/`. Generating and building
> write into the kit, so they run from a copy in your workspace (the new-project skill's `copy-kit.sh vela-calib`).
> Commands below are written from that copy (`cd tools/vela-calib`, photos under `../../devices/`).

Measure how a Xiaomi Vela wearable really draws quick-app UI, once per device model, and keep the
answers in a **device profile** that layout code reads instead of guessing. Built after BART Watch
2.0.8–2.0.12 lost five builds to guessed text placement on the Band 10 Pro. Any Vela device with a
**device spec** (`devices/<id>/device.json`) can be calibrated: rectangular, rounded, capsule and
round screens (see "Device spec" and "A new device" below; `devices/KNOWN_DEVICES.md` lists the
known Vela wearables).

| Piece | What it is |
|---|---|
| `devices/<device>/device.json` (repo root) | The **device spec**: screen size and shape, quick-app design width, face canvas and packer, firmware. Both kits generate from it |
| `device-spec.mjs`, `device_spec.py` | Load and validate specs; each shape's visible outline (the kits' placement test) |
| `new-device.mjs` | Onboard a device: spec, seeded profile, both kits' layouts (checked), `CALIBRATION.md`, printed next steps |
| `src/` (generated) → `dist/com.soham.velacalib.<device>.debug.<v>.rpk` | **Vela Calib**, a band app of full-screen test pages, one build per device (21 pages on the Band 10 Pro, 24 on the Band 10 / 11, 26 on a 466 px round watch) |
| `gen/gen.mjs`, `gen/images.py`, `gen/build.mjs` | Generate the pages (`src/pages/index/index.ux`, manifest, test PNGs) and `layouts/<device>.json`, the list of every sample and where it is; build every onboarded device's .rpk |
| `seed-profile.mjs` | Seed `devices/<new model>/profile.json` from its spec: screen spec and firmware filled in, every fact `unknown` |
| `test/layout-check.mjs`, `test/specs/` | The layout checks (used by `npm test` and `new-device.mjs`); two synthetic devices for the tests (a 466 px circle, a 390 x 450 rounded rectangle with 80 px corners) |
| `measure.py` | Reads one photo per page, corrects scale and tilt from the rulers, measures every sample, writes the profile |
| `devices/<device>/profile.json` (repo root) | The device profile. Every fact says `measured`, `assumed` or `unknown`, where it came from, and when. Tied to one firmware (`firmware.version`) |
| `devices/<device>/evidence/*.json` | Per-photo measurements the profile is built from (committed; the photos in `devices/<device>/photos/` aren't) |
| `profile.js` | Helpers for layout code: line heights, the smallest box that keeps the ink, widths, safe area, colour floor, CSS support |
| `profile-node.mjs`, `export.mjs` | Load a profile in Node; write a self-contained `device.js` into a band app's `src/common/` |
| `layouts/legacy-bart-2.0.11.json`, `legacy-bart-2.0.12.json`, `legacy-kit-1.0.0-band10pro.json` | Layouts of the two BART calibration screens and of kit 1.0.0, so their photos can be re-measured (`--layout`) |

## Build

```sh
cd tools/vela-calib
npm run build        # images.py, then gen.mjs + aiot build per onboarded device (a spec + layouts/<id>.json) ->
                     #   dist/com.soham.velacalib.band11.debug.2.0.0.rpk, dist/com.soham.velacalib.band10pro.debug.2.0.0.rpk
npm test             # profile.js; layout checks for every spec (devices/*/device.json) and the synthetic
                     # ones; measure.py selftest (band10pro, band11, synthetic circle and rect)
```

Building needs a writable copy of the kit in your workspace (`<workspace>/tools/vela-calib`, see the
`calibrate-quickapp` skill) with `npm install` run there (aiot-toolkit) and `sign/` holding the
workspace's shared key (`make-keys.sh` from the `new-project` skill; gitignored; never regenerate it).
The package is `com.soham.velacalib`; it has no phone companion.

**One .rpk per device.** Each build is generated for its screen with `designWidth` = the screen
width (336, 212, 466...), so 1 design px = 1 panel px and the rulers mean band px. Install the build
whose name matches the device (all share the package, so one replaces another). `aiot build` empties
`dist/` each time, so build with `npm run build` (all onboarded devices; it leaves `src/` as the
Band 10 Pro's). A single device: `npm run build -- band11` (then the other devices' rpks are gone
until the next full build, and `src/` holds that device's pages until `node gen/gen.mjs band10pro`).
The kit checks its own scale: the start and geometry pages print what `@system.device` reports,
and on a capsule or a circle `measure.py` fits the outline and reports `device.design_scale`
(W/2 over the end radius / circle radius, ~1.00-1.03 when 1:1); a scaled page also loses its right
ruler (the fit says so). A new device: `node new-device.mjs` (below).

## Device spec

`devices/<id>/device.json` (schema `vela-device-spec/1`) says what a device **is**; the profile says
what it **does**. Both kits read only the spec to generate pages; nothing in the kits names a model.

```json
{
 "schema": "vela-device-spec/1", "id": "watchs4", "name": "Xiaomi Watch S4 (47 mm)", "also": [], "verified": false,
 "screen": { "w": 466, "h": 466, "shape": "circle", "corner_radius": null, "diag_in": 1.43, "ppi": 326, "source": "..." },
 "quickapp": { "design_width": 466, "status": "assumed" },
 "face": { "canvas": { "w": 466, "h": 466 }, "id_digit": null, "builder": "pack.mts", "device_type": "462", "status": "experimental", "note": "..." },
 "firmware": { "version": null },
 "calib": {}
}
```

- `screen.shape`: `rect` (square corners, or `corner_radius`), `rounded_rect` (`corner_radius` in
  band px; null = assume 0.2 x the short side, generous on purpose), `capsule` (semicircle ends of
  radius w / 2, h > w), `circle` (w = h). The outline is the kits' placement assumption (every sample
  stays 4 px inside it); the geometry page measures the real one.
- `quickapp.design_width`: what apps build with once the geometry page confirms 1:1 (the kit itself
  always builds with the screen width).
- `face`: `canvas`, `id_digit` (face ids are `8<digit><build><face>`; 1 = Band 11, 2 = Band 10 Pro,
  9 = the synthetic test specs; null until onboarded, then `new-device.mjs` assigns the next free
  one), `builder` (`band10-toolkit` only for 212 x 520, else `pack.mts`), `device_type` (the
  community FPRJ DeviceType when known; informational, the packer doesn't write it), `status`
  (`verified` once F1 has been photographed on the device, else `experimental`).
- `verified`: the spec was checked against the device (calibration photos). `calib`: per-device kit
  overrides, e.g. `calib.quickapp.text_slack: "measured"` (the Band 10 Pro's glyph widths are known,
  so its text slots are tighter), `calib.quickapp.text_w_words` (extra strings), and
  `calib.face.frame` (the Band 10 Pro's and Band 11's face frames are pinned: build 1 was
  photographed with them).
- `devices/KNOWN_DEVICES.md` lists Vela wearables with sources; specs exist for the ones whose
  screen is well documented, all unverified until calibrated.

## A new device

```sh
node tools/vela-calib/new-device.mjs watchs4                     # a spec that already exists
node tools/vela-calib/new-device.mjs mywatch --w 466 --h 466 --shape circle --name "..." [--diag 1.43 --ppi 326 --firmware V]
```

It writes (or keeps) the spec, seeds `devices/<id>/profile.json` (every fact unknown), generates this
kit's `layouts/<id>.json` and checks it (every sample slot inside the outline, clear of the rulers,
bar and barcode, no overlaps, enough visible ruler ticks), generates the face kit's pages
(`tools/face-calib/faces/<id>/`), writes `devices/<id>/CALIBRATION.md` from `devices/CALIBRATION.md`,
and prints the build and photo steps. It never touches a phone or band.

Sizes follow the sample area, not the model: Text V sizes whose "8" takes at most 80 % of the area
width and whose 1.5 em box fits its height; four-digit strings at 48 px or 40 px; box-model columns
with 8 px gaps unless 4 px fits another; narrower areas (< 200 px) get the smaller "too wide"
sample. A screen whose sample area is under 140 x 280 px is refused.

Install it like any band app (`tools/sideload.sh dist/*.rpk`, AstroBox; see the agent rules for the
pairing prompts). Bump `VERSION` in `gen/gen.mjs` when you change the pages.

## Using it on the band

- **Tap** or **swipe left/up**: next page. **Swipe down**: previous page. **Swipe right**: exit.
- The screen stays on while you use it (released after 3 idle minutes and on exit).
- Every page has the same frame, so each photo is measurable on its own:
  - **rulers** down both edges: a 1 px tick every 10 px (tick top = y), 14 px long every 50,
    22 px long and **yellow** every 100; the left ruler starts at x 0, the right one ends at x W
    (on a capsule only the ticks on the straight sides show: ~37 per side, plenty for the fit).
    **Round screens** have no straight edge: the rulers are two straight tick columns inside the
    circle, 0.62 R either side of the centre (x 89 and 377 on a 466 px watch), over the rows where
    both columns are 4 px inside it (y 60-410: 36 ticks and 4 yellow per side); `layouts/<id>.json`
    records them as `frame.ruler`. Their outer ends aren't the screen's edge, so the hidden edges come
    from the geometry page only;
  - a **yellow bar exactly 200 × 4 px** at (110, 456) on the Band 10 Pro, **160 × 4 px** at (26, 462)
    on the Band 10 / 11, 200 x 4 centred low in a circle (on the Screen geometry page it's mid-screen);
  - a **barcode** (8 cells: on, the page number in 5 bits, parity, on) left of the bar (rectangles)
    or under it (capsules, circles), so `measure.py` knows which page a photo shows;
  - the page number and name in grey at the top.

## The pages (kit 2.0.0)

Page numbers differ per device (the barcode identifies each photo; `node gen/gen.mjs <device>` prints
the list). Band 10 Pro: 0 start, 1–6 Text V, 7–10 Text W, 11–13 Wrap, 14–16 Box, 17 geometry,
18 colour, 19 images, 20 animation. Band 10 / 11: 0 start, 1–4 Text V, 5–9 Text W, 10–14 Wrap,
15–18 Box, 19 geometry, 20 colour, 21–22 images, 23 animation.

| Page | What it measures |
|---|---|
| Start | instructions, and the `@system.device` line (screen size, shape, density; yellow): photograph it once per model |
| Text V | **Vertical text metrics.** "Hg8" at 24–96 px (where it fits) and "8" above, each in three boxes: **cyan** = no height (the natural line box), **pink** = explicit height 1.5 em, **green** = explicit height 0.9 em. Every box is wider than its string with worst-case slack (glyphs 15 % wider than the Band 10 Pro's on a new model), so nothing wraps. Plus two pink "8H" boxes cut through the H on purpose: the string-wider-than-its-box regime. Band 10 Pro sizes to 240 px, Band 10 / 11 to 140 px |
| Text W | **Advance widths.** Each string in a shrink-wrapped `<text>` with a 1 px pink outline: every digit ×4 (48 px; 40 px on the 212 px screen), "0000" at 24/96 (linearity; "00" at 96 on the 212 px screen), "min", "NOW", "Checking…", "0 0 0 0" (space width), the alphabet (in halves on the 212 px screen), punctuation, BART's strings (Band 10 Pro only); normal vs bold weight; whether an absolute `<text>` with no width shrink-wraps or stretches |
| Wrap | 136 px boxes at 20 px: text-align left / center / right, `lines: 2` + ellipsis, `lines: 1` + ellipsis, `lines: 2` without ellipsis, explicit height shorter than the text, `line-height` 32 / 40 / 48 / 72, a word longer than the box, "5" + "min" in a flex row with align-items flex-end and baseline. Slots hold a worst-case word wrap at 1.5 em per line |
| Box | Box model in 80 × 96 slots, each with named hypotheses: padding, box-sizing, margin, **negative margins** (top, left), absolute position origin, border widths 1/2/4/8, per-side border width and colour, border-radius (single, **per corner**, override, on an outline, 999 px pill), overflow hidden / visible (absolute child, so flex shrinking can't confound it), **flex-shrink 0**, overflow hidden + radius, opacity, z-index, static translate and rotate, % width, justify-content, box-shadow, text with a background and radius |
| Screen geometry | Rounded rectangle (Band 10 Pro): white 48 × 48 squares in the four corners (1.2 x the corner radius when that is larger) and 1 px combs from the top and bottom edges (hidden rows). Capsule (Band 10 / 11): a white cap over each end, full width and 115 px tall: the arc fit gives the end radius, its centre, the hidden rows, the hidden columns (straight rows) and the **design scale**. Circle: white boxes over everything outside the rulers (top, bottom, left, right); every lit pixel next to an unlit one inside the boxes is on the screen's circle, and a circle fit to them (360 degrees of arc) gives the radius, centre, all four hidden edges and the design scale. All: the `@system.device` line, and note anything the system draws over the app; rect and capsule also get hidden columns from the ruler ends on every page |
| Colour floor | Grey ramp #000000–#606060 in steps of 8, red / green / blue ramps #10–#80, dark surfaces #202020–#484848, brand colours |
| Images | A 32 px checker PNG at 1×, 2×, 1.5×, 0.5× and stretched; PNG8 and greyscale PNGs; a soft-alpha disc as RGBA, PNG8 + tRNS and hard alpha; `object-fit` fill / contain / none, and cover on a patterned image (a white block at source columns 16–31: cover, fill and contain put it in different places); an alpha ramp over an opaque grey ramp |
| Animation | **Watch, don't photograph.** 8 s runs with a **finish marker**: a square turns yellow for the last 10 % of its path (a yellow tick under each lane marks where), which it only reaches if nothing restarts it. A: control (must turn yellow, or the marker doesn't work on this band); B: class rebound every 3 s; C: a class binding that never changes, page re-rendered every 1 s; D: `steps(4, end)`; E: translateX 0 → 600 px; F: an image whose `src` is swapped every 3 s (dims instead of turning yellow); G: opacity alternate; H: **BART's pattern**, a class reading a field of an object replaced every 1 s |

## Photo procedure

One photo per page except the animation page (watched) and optionally the start page.

1. **Room:** ordinary indoor light, no lamp or window reflecting in the band's glass. **No flash.**
2. **Phone:** **portrait**, main camera at 1× (not ultra-wide, not portrait/night mode). If the
   main camera can't focus that close, use 2× (not macro, not ultra-wide).
3. **Band:** upright (the strap vertical, the screen's long side along the photo's long side),
   screen facing the phone, flat on a table or held still.
4. **Straight on:** the phone parallel to the band's screen and centred over it. A small tilt is
   corrected from the rulers; more than ~10° loses precision.
5. **Close:** at least 2.5 photo px per band px (`measure.py` warns below 2.0). Band 10 Pro: the
   screen fills at least a third of the photo's width. Band 10 / 11 (16.5 × 40.5 mm): the screen
   fills at least a third of the photo's **height** (about half is ideal).
6. **Everything in frame:** both rulers top to bottom, the yellow bar and the barcode (on the Band
   10 / 11 the barcode is under the bar, near the bottom end). No finger over the screen.
7. **Focus and exposure:** tap the band's screen on the phone to focus; if the white looks blown
   out, drag the exposure down a step (less bloom = sharper edges).
8. Go to the next page on the band (tap) and repeat. Order doesn't matter: the barcode identifies
   each photo; a retake of a page simply replaces the older one.

**Animation page:** watch it for about 20 s (or record a video) and note, per lane, whether the
square reaches the right end and turns yellow (F: dims), jumps back early without turning yellow
(and how often), stops, or jumps in steps. Record the answers with `measure.py set` (below).

## Measuring

```sh
cd tools/vela-calib
mkdir -p ../../devices/band10pro/photos   # gitignored
# copy the photos in (adb pull, or the mtp-transfer skill), then:
python3 measure.py run ../../devices/band10pro/photos/*.jpg            # updates devices/band10pro/profile.json
python3 measure.py run ../../devices/band10pro/photos/*.jpg --dry-run  # measure and print only
python3 measure.py show                                                # every fact and its status
# another model: --device band11 (devices/band11/profile.json, evidence in devices/band11/evidence/)
```

Per photo it prints the page, the ruler fit (rms residual in band px; want < 0.5), the scale, and
one line per sample; annotated rectified images go to `results/` (gitignored) for a visual check.
A photo whose fit is bad is reported but not used. The profile is then rebuilt from all evidence in
`devices/<device>/evidence/` (newest photo per page wins), so photos from different sessions add up.

Observations (animation page, system overlay):

```sh
python3 measure.py set animation.lane_B '"restarts every 3 s"' --source "anim page, 2026-10-01"
python3 measure.py set animation.class_binding_rerender_restarts true --source "anim page lane C"
python3 measure.py set screen.system_overlay '"none"' --source "geometry page, 2026-10-01"
```

Old BART calibration photos (no barcode): `--layout layouts/legacy-bart-2.0.11.json --page 0`.

How it measures: the yellow bar and the yellow ticks give a rough similarity; every white tick is
then found next to its inner end (away from any bezel glare) and a homography is fitted to the
tick ends and the bar ends, with outliers dropped. Camera **bloom** (a saturated 1 px tick reads
3–4 px thick) is estimated from the tick thickness and taken out of the geometry. Outlines are
located by the centre of their 1 px line (bloom-free); ink edges are at half brightness and still
include the bloom (≈1 px per side), which errs on the safe side (ink measured slightly large). The
synthetic self-test (`python3 measure.py selftest`) renders pages of the Band 10 Pro, the Band 10 /
11 and the two synthetic specs in `test/specs/`, warps and blurs them like a photo (rounded corners
at 5/8 of the kit's assumed radius for rectangles, a capsule with 2 px hidden at each side, a circle
with 2 px hidden all round), and checks that the page, line box, centring rules (including a string
wider than its box), advance widths, box-model verdicts, corner radius, capsule end radius, circle
radius, hidden edges and design scale come back right. `--device X`, `--layout L.json` or
`--spec S.json` test others.

## The profile

`devices/<device>/profile.json`, schema `vela-device-profile/2`. Top level: `firmware` (the version
every fact was measured on; re-run the kit after a firmware update), `device` and `screen` (the
panel). `quickapp` holds how the Vela JS-app renderer draws (font, text, colour, css, animation,
image, behaviour); `face` holds the watch-face engine's facts (widgets, image lists, Lua layer,
always-on), which are a different renderer and are never inferred from `quickapp`. `profile.js`
looks a path up at the top level, then inside `quickapp`, so the paths below keep their short form
(`font.line_box_em` = `quickapp.font.line_box_em`); face facts are addressed in full
(`face.colour.floor.grey`). `measure.py set` takes either form. Every leaf fact is

```json
{ "value": 1.3231, "status": "measured", "source": "photos calib.jpg, calib2.jpg", "date": "2026-09-27", ...extra }
```

`status`: **measured** (a device photo or observation), **assumed** (a spec, a font file, another
band model; usable, but replace it by measuring), **unknown** (`value` null; code that needs it must
measure it first). Main groups:

| Path | Meaning |
|---|---|
| `device.screen.{w,h,diag_in,ppi,mm_per_px}` | panel size |
| `font.family`, `font.line_box_em` (+ `by_size_px`) | system font; one line's natural height in em |
| `font.ascent_em`, `font.descent_em`, `font.baseline_em` | vertical font metrics (baseline from the line-box top) |
| `font.ink.{digit,cap,descender}.{top_em,bottom_em}` | ink extents from the line-box top |
| `font.regime.taller_box.rule` / `.shorter_box.rule` | where the band puts the line in a `<text>` taller / shorter than its line box: `centre`, `top` or `bottom`; `.clipped` |
| `font.ink_clipped_to_own_box` | a `<text>` never draws ink outside its box, whatever `overflow` says |
| `font.advance_em.<char>` | advance widths; `font.string_em.<weight>.<string>` whole strings; `font.advance_safety.{assumed,measured}` |
| `font.weights.normal_differs_from_bold` | is there a regular face |
| `text.line_height_css`, `text.wrap.<case>`, `text.row.<align>` | CSS line-height, wrapping, alignment, ellipsis, flex-row alignment |
| `screen.corner_radius_px`, `screen.hidden_px.{left,right,top,bottom}`, `screen.system_overlay` | visible area |
| `screen.shape`, `screen.end_radius_px.{top,bottom}` | capsule screens: each end's arc (also written per corner to `corner_radius_px`, so `safeArea` / `xRange` work unchanged) |
| `screen.radius_px`, `screen.round_detail` | round screens: the fitted circle (radius also per corner in `corner_radius_px`: a rounded rectangle whose radius is half its side is the circle, so `safeArea` / `xRange` work unchanged) |
| `device.design_width`, `device.design_scale` | the manifest designWidth that draws 1:1; W/2 over the capsule end radius (~1.00-1.03 = 1:1) |
| `colour.floor.{grey,red,green,blue,surface}` | lowest channel value visibly above black; `colour.brand` |
| `css.<feature>` | verdict (hypothesis name) + `supported` true/false; `css.compiler_accepts` = what the compiler takes (not what renders) |
| `image.*`, `animation.*`, `behaviour.*` | image formats and scaling, animation restarts, exit and install behaviour |

## Using the profile in code

```js
// Node (tests, generators)
import { loadProfile } from '../../tools/vela-calib/profile-node.mjs'
const device = loadProfile('band10pro')

// Band app: node tools/vela-calib/export.mjs band10pro <app>/src/common/device.js
import device from '../common/device'

device.lineH(96)               // natural height of one line at 96 px
device.inkIn(240, 224)         // where a 240 px digit's ink lands in a 224 px <text> (and if it's cut)
device.minBoxH(240)            // smallest <text> height that keeps a 240 px digit whole (+2 px + 0.03 em)
device.width('12 min', 40)     // conservative width in px; device.fits(s, px, avail)
device.safeArea(), device.xRange(y, pad)   // visible area, usable x at row y (throws until measured)
device.colourFloor(), device.visible('#303030')
device.supports('negative_margin')         // true / false / null (unknown)
device.need('font.ink.cap.top_em')         // any fact; throws with "calibrate this" when unknown
device.unknowns()                          // what's left to measure
```

Nothing falls back to a default: a helper that needs an unknown fact throws and names the page that
measures it.
