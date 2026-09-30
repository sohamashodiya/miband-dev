---
name: build-band-app
description: Build or change a Vela JS quick app for a Xiaomi Smart Band 10 / 10 Pro / 11 and its optional Android companion (profile-driven layout with device.js, measured Vela text placement, animation restarts, the exit rule, phone-band messaging through Mi Fitness). Use for any band app UI, build, or companion work.
---

# Building band apps (Vela JS) and their phone companions

Design first: mock every band screen and the matching phone screens, at true physical scale, and
get the user's approval before building (see the agent's "Design first" rule and `new-project`).

## Layout comes from the device profile
- **Before any band UI work, load the device's profile and size and lay out using only it**: line
  heights, where ink sits in a box, the smallest box that keeps the ink, text widths, the safe area,
  the colour floor, which CSS works. Band apps are quick apps: use the `quickapp` section, never
  `face` facts.
- **Builds generate from the profile.** In band code, `src/common/device.js` is made by
  `node tools/vela-calib/export.mjs <model> src/common/device.js` as a build step (`npm run device`,
  run by `prebuild`), never edited or copied by hand. The app's fit test runs `export.mjs --check`
  and fails when `device.js` is stale. The command needs a stable path, so the workspace keeps a
  copy of the kit in `tools/vela-calib/` (`calibrate-quickapp` explains the copy); from the plugin
  it is `node "${CLAUDE_PLUGIN_ROOT}/tools/vela-calib/export.mjs" …`. `export.mjs` reads the
  workspace profile, else the shipped default, and writes only the file you name.
- In Node (tests, generators): `import { loadProfile } from '<kit>/profile-node.mjs'`,
  `loadProfile('<model>')`. Short quick-app paths like `font.line_box_em` resolve inside `quickapp`;
  face facts are `face.…`. Fit tests check layouts against the same helpers.
- The helpers (`profile.js`, also inside `device.js`): `device.lineH(px)`, `device.inkIn(px, boxH)`,
  `device.minBoxH(px)`, `device.width(str, px)` / `device.fits(str, px, avail)`,
  `device.safeArea()`, `device.xRange(y, pad)`, `device.colourFloor()`, `device.visible('#303030')`,
  `device.supports('negative_margin')`, `device.need('<path>')` (throws "calibrate this" when
  unknown), `device.unknowns()`. Nothing falls back to a default.
- **Never guess text metrics** (or any other rendering fact). A fact that isn't in the profile, or is
  `unknown`, must be measured first (`calibrate-quickapp`). Prefer `measured` facts; treat `assumed`
  ones as provisional.
- Colour floor for band apps: the profile's `quickapp.colour.floor`. On the Band 10 Pro the
  calibration photo (2026-09-27) showed `#181818` and up, and every `#202020`–`#484848` surface,
  distinct from black. Watch-face floors are a different renderer.

## Band app project pattern (`apps/<project>/band/`)
- Vela JS app built with aiot-toolkit. `npm test`, `npm run build` → `dist/*.rpk`.
- `node_modules`: its own `npm install`, or a symlink to another band app's (install once).
- `sign/` is a copy of the workspace's shared PEMs (`make-keys.sh --sync` from `new-project`).
- Install with the `sideload` skill. **A reinstalled band app keeps running its old code** until it's
  closed on the band; neither installing over it nor `launchWearApp` replaces a running instance.

## Every band app must let the user exit
On the Band 9 Pro / 10 Pro the system swipe-right does nothing for a single-page app, so implement
exit yourself: `onBackPress()` plus a page `@swipe` 'right' plus a raw touch fallback, all calling
`$app.exit()` → `@system.app` `terminate()` → `router.back()` (declare `system.app` in the
manifest). Never bind `@swipe` / `@longpress` on the page root without handling 'right'. Verify exit
on the band on every new app. If an app traps the user anyway, use the soft-brick recovery (agent
rules / `sideload`).

## Vela text placement (measured)
Measured on the Band 10 Pro (2026-09-27, the BART Watch app's calibration photos and the kit's
photos); the Band 11 matches (line box 1.331 em, same ink). Use the profile's numbers in code; this
is the model to reason with:
- A `<text>` line's natural box is **1.327 em** (1.323–1.334 across 24–240 px; MiSans hhea 1.044 +
  0.282; budget 1.33, not 1.3).
- Where the line sits depends on the element's explicit height: **taller than the line box, the band
  centres it; shorter, the band TOP-ANCHORS it (the line starts at the element's top) and CLIPS
  everything past the element's bottom** (`overflow: visible` does not help). So "the band centres
  text" is only true for boxes taller than the line **whose string fits the width**.
- A string wider than its box: with no height it wraps (at spaces, then between letters) and the
  box grows; with an explicit height it is drawn on ONE line, cut at the right, and TOP-ANCHORED even
  in a taller box.
- Round digits' ink runs from about 0.25 em to 1.07 em below the line top (caps 0.26–1.07; "g"
  0.48–1.32, i.e. to the line box's bottom; the i dot of "min" from 0.165 em; baseline 1.044 em).
- A digit / caps / "min" can sit in a **tight, top-anchored box on the `<text>` itself**: height >=
  ink bottom + margin (one app used 1.075 em + 1.5 px + 1 px + 0.02 em), plus a **negative
  margin-top** giving back the empty top (ink top − margin); the page pays only the difference.
  Anything with descenders keeps its full line box.
- Never size a *wrapper div* smaller than its text's line box and never centre with padding: builds
  that did clipped numbers, and tight boxes built on a "centred" assumption (0.914 em + 4) cut every
  big digit's bottom.
- Negative margins compile (aiot emits `marginTop: "-52px"`) and **are honoured on the device**
  (check-screen photo, 2026-09-27: every digit whole and the lifted boxes in place).

## Vela animations restart on re-render
A `{{…}}` in an element's `class` compiles to a fresh array on every render, which re-applies the
class and restarts its CSS animation. Give animated elements static classes (switch with
`if`/`else`), bind only plain top-level values that are set when they change, and skip renders
whose view didn't change. Seen on the band: a train animation stopped at about 75% because of a 1 s
tick render whose class read `this.v`, replaced on every render. The calibration kit's animation
page ran a class bound to an unchanged top-level primitive smoothly through 1 s re-renders.
`steps()`, a 600 px translateX and opacity keyframes all work. On the Band 11, keyframe
`background-color` does not animate, a class swap restarts, and an image `src` swap doesn't; check
`animation.*` in the profile for the model you target, and measure what's `unknown`.

## Swipe pages
An installed app can be added to the swipe pages (the pages you reach by swiping sideways from the
watch face): on the band, press and hold one of those pages, then add a new page from an installed
app. Mi Fitness has no setting for these pages: its Device → Apps → "Cards" is the NFC wallet, and
System → "Sort apps" only orders the apps list. When someone wants an app one swipe from the face,
tell them this; no build change is needed. Found on a Band 11 with the stock World clock; whether a
sideloaded Vela app shows up in that list hasn't been checked.

## Phone companion (`apps/<project>/phone/`)
- Android app in Kotlin with Xiaomi's `xms-wearable` SDK in `app/libs`. Build with JDK 21:
  `JAVA_HOME=<JDK 21> ./gradlew assembleDebug` (keystore from the workspace's
  `signing/keystore.properties`).
- Messages go phone ⇄ Mi Fitness ⇄ band, and only when the APK and `.rpk` share the **package name
  and signing certificate** (the workspace's shared key from `make-keys.sh`; once made, never
  regenerate it).
- Debug with `adb logcat | grep -E "AppLinkLog|xms.wearable"`.
- A Mi Fitness restart (every AstroBox install causes one) silently drops the phone app's message
  listener while phone → band sends keep working. Re-register (`removeListener` then `addListener`;
  adding twice throws "you have registered") on band-app launch and periodically.

## Checking on the device
Ask the user for a photo, then pull only the newest one (`adb shell ls -t /sdcard/DCIM/Camera/ | head -1`).
When the photo contradicts the profile, the photo wins: re-measure (`calibrate-quickapp`), then fix
the layout. Keep the mock-ups in sync with what landed.
