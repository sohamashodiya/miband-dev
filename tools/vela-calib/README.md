# Vela calibration kit

Measure how a Xiaomi Vela band really draws quick-app UI, once per band model, and keep the
answers in a **device profile** that layout code reads instead of guessing. Built after BART Watch
2.0.8–2.0.12 lost five builds to guessed text placement on the Band 10 Pro.

| Piece | What it is |
|---|---|
| `src/` (generated) → `dist/com.soham.velacalib.debug.<v>.rpk` | **Vela Calib**, a band app with 19 full-screen test pages |
| `gen/gen.mjs`, `gen/images.py` | Generate the pages (`src/pages/index/index.ux`, manifest, test PNGs) and `layouts/<device>.json`, the list of every sample and where it is |
| `measure.py` | Reads one photo per page, corrects scale and tilt from the rulers, measures every sample, writes the profile |
| `devices/<device>/profile.json` (repo root) | The device profile. Every fact says `measured`, `assumed` or `unknown`, where it came from, and when. Tied to one firmware (`firmware.version`) |
| `devices/<device>/evidence/*.json` | Per-photo measurements the profile is built from (committed; the photos in `devices/<device>/photos/` aren't) |
| `profile.js` | Helpers for layout code: line heights, the smallest box that keeps the ink, widths, safe area, colour floor, CSS support |
| `profile-node.mjs`, `export.mjs` | Load a profile in Node; write a self-contained `device.js` into a band app's `src/common/` |
| `layouts/legacy-bart-2.0.11.json`, `legacy-bart-2.0.12.json` | Layouts of the two BART calibration screens, so their photos (`calib.jpg`, `calib2.jpg`) can be re-measured |

## Build

```sh
cd tools/vela-calib
npm run build        # images.py + gen.mjs + aiot build -> dist/com.soham.velacalib.debug.1.0.0.rpk
npm test             # profile.js, layout sanity, measure.py synthetic end-to-end self-test
```

`node_modules` is a symlink to `../../apps/bandlink/band/node_modules`; `sign/` is a copy of
`apps/bandlink/band/sign` (the shared BandLink key, gitignored; never regenerate it). The package is `com.soham.velacalib`; it has
no phone companion. For another band model: `node gen/gen.mjs band11` (212 × 520) writes that
model's pages and `layouts/band11.json` (untested on a Band 11 so far).

Install it like any band app (`tools/sideload.sh dist/*.rpk`, AstroBox; see the agent rules for the
pairing prompts). Bump `VERSION` in `gen/gen.mjs` when you change the pages.

## Using it on the band

- **Tap** or **swipe left/up**: next page. **Swipe down**: previous page. **Swipe right**: exit.
- The screen stays on while you use it (released after 3 idle minutes and on exit).
- Every page has the same frame, so each photo is measurable on its own:
  - **rulers** down both edges: a 1 px tick every 10 px (tick top = y), 14 px long every 50,
    22 px long and **yellow** every 100; the left ruler starts at x 0, the right one ends at x 336;
  - a **yellow bar exactly 200 × 4 px** at (110, 456) (on the Screen geometry page it's mid-screen);
  - a **barcode** left of the bar (8 cells: on, the page number in 5 bits, parity, on), so
    `measure.py` knows which page a photo shows;
  - the page number and name in grey at the top.

## The pages (Band 10 Pro)

| # | Page | What it measures |
|---|---|---|
| 0 | Start | instructions (no photo) |
| 1–5 | Text V 1–5 | **Vertical text metrics.** "Hg8" at 24, 32, 48, 72, 96 px and "8" at 140, 180, 240 px, each in three boxes: **cyan** = no height (the natural line box), **pink** = explicit height 1.5 em, **green** = explicit height 0.9 em. Gives the line box, where the ink of digits / caps (H) / descenders (g) sits, the centring rule in taller boxes, the top-anchoring and clipping in shorter ones |
| 6–9 | Text W 1–4 | **Advance widths.** Each string in a shrink-wrapped `<text>` with a 1 px pink outline: every digit ×4 at 48 px (per-glyph advances to 0.003 em), "0000" at 24/48/96 (linearity), "min", "NOW", "min, maybe", "Checking…", "UPDATING…", "later 21, 36 min", "CHANGE AT", station names, "0 0 0 0" (space width), the alphabet, punctuation; normal vs bold weight; and whether an absolute `<text>` with no width shrink-wraps or stretches |
| 10–11 | Wrap 1–2 | 136 px boxes at 20 px: text-align left / center / right, `lines: 2` + ellipsis, `lines: 1` + ellipsis, `lines: 2` without ellipsis, explicit height shorter than the text, `line-height` 32 / 40 / 48 / 72, a word longer than the box, "5" + "min" in a flex row with align-items flex-end and baseline |
| 12–14 | Box 1–3 | Box model, each with named hypotheses: padding, box-sizing, margin, **negative margins** (top, left), absolute position origin, border widths 1/2/4/8, per-side border width and colour, border-radius (single, **per corner**, override, on an outline, 999 px pill), overflow hidden / visible / hidden + radius, opacity, z-index, static translate and rotate, % width, justify-content, box-shadow, text with a background and radius |
| 15 | Screen geometry | White 48 × 48 squares in the four corners (the corner radius), 1 px combs from the top and bottom edges (hidden rows), plus the ruler ends on every page (hidden columns). Also: note anything the system draws over the app |
| 16 | Colour floor | Grey ramp #000000–#606060 in steps of 8, red / green / blue ramps #10–#80, dark surfaces #202020–#484848, brand colours |
| 17 | Images | A 32 px checker PNG at 1×, 2×, 1.5×, 0.5× and stretched; PNG8 and greyscale PNGs; a soft-alpha disc as RGBA, PNG8 + tRNS and hard alpha; `object-fit` fill / contain / cover / none; an alpha ramp over an opaque grey ramp |
| 18 | Animation | **Watch, don't photograph.** Lanes A–G: control; class rebound every 3 s; a class binding that never changes while the page re-renders every 1 s; `steps(4, end)`; translateX 0 → 600 px; an image whose `src` is swapped every 3 s; opacity alternate |

## Photo procedure

One photo per page, 1–17. Page 18 is watched (see below).

1. **Room:** ordinary indoor light, no lamp or window reflecting in the band's glass. **No flash.**
2. **Phone:** **portrait**, main camera at 1× (not ultra-wide, not portrait/night mode).
3. **Band:** upright (the strap vertical), screen facing the phone, flat on a table or held still.
4. **Straight on:** the phone parallel to the band's screen and centred over it. A small tilt is
   corrected from the rulers; more than ~10° loses precision.
5. **Close:** the band's screen should fill at least a third of the photo's width (≥ 2.5 photo px
   per band px; `measure.py` warns below 2.0).
6. **Everything in frame:** both rulers top to bottom, the yellow bar and the barcode. No finger over
   the screen.
7. **Focus and exposure:** tap the band's screen on the phone to focus; if the white looks blown
   out, drag the exposure down a step (less bloom = sharper edges).
8. Go to the next page on the band (tap) and repeat. Order doesn't matter: the barcode identifies
   each photo; a retake of a page simply replaces the older one.

**Animation page (18):** watch it for about 15 s (or record a video) and note, per lane, whether
the square runs smoothly to the right end and loops, jumps back early (and how often), stops, or
jumps in steps. Record the answers with `measure.py set` (below).

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
synthetic self-test (`python3 measure.py selftest`) renders pages, warps and blurs them like a
photo, and checks that the page, line box, centring rules, advance widths, box-model verdicts,
corner radius and edge combs come back right.

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
