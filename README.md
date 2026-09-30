# miband-dev

A [Claude Code](https://claude.com/claude-code) plugin for building watch faces and Vela JS apps
for Xiaomi Smart Bands (Band 10, 10 Pro and 11, and other Xiaomi Vela wearables once calibrated)
and installing them from an Android phone over adb.

It keeps the band's official companion, Mi Fitness, and installs through AstroBox. Its rules come
from real installs on real bands: how AstroBox re-pairs the band and why you must never interrupt
it, recovering a band app you can't exit, Vela text metrics and watch-face engine behaviour
measured from photos, and why animations restart on re-render.

## 1. Install

In Claude Code:

```
/plugin marketplace add sohamashodiya/miband-dev
/plugin install miband-dev@miband-dev
```

Or from a terminal, in one line:

```sh
claude plugin marketplace add sohamashodiya/miband-dev && claude plugin install miband-dev@miband-dev
```

Then run `/reload-plugins` (or start a new session).

- **Update:** in Claude Code, `/plugin` → Installed → miband-dev → Update; or from a terminal
  `claude plugin marketplace update miband-dev && claude plugin update miband-dev@miband-dev`
  (restart Claude Code afterwards).
- **Uninstall:** `/plugin` → Installed → miband-dev → Uninstall; or
  `claude plugin uninstall miband-dev@miband-dev` (and `claude plugin marketplace remove miband-dev`
  to forget the marketplace too).

## 2. Set up a workspace

Open Claude Code in an empty folder (or an existing repo of your band projects) and run:

```
/miband-dev:new-project
```

It creates the folder layout, `README.md` (your project registry), `devices/DEVICES.md` (filled in
with you: your phone, its adb serial, your band and its firmware) and `.gitignore`, and makes the
signing key when you start your first band app. It is safe to run again: it only adds what's
missing. Later, it adds each new app or face project the same way.

The agent, its tools, the calibration kits and the measured device profiles ship **inside the
plugin**; nothing needs to be copied or downloaded by hand. Your workspace holds only your own
things: your projects, your device list, your signing key, and your own calibration if you ever
run one (the skills copy a calibration kit into the workspace at that point, because building it
writes files).

## Before you start: AstroBox and your Xiaomi account

The plugin installs apps and faces through **AstroBox**, a third-party community app for Android
(not made or endorsed by Xiaomi). To talk to your band, AstroBox needs the band's auth key, and it
gets it when **you sign in to your Xiaomi account inside AstroBox with your username and
password**. That means giving a third-party app your Xiaomi account credentials: decide for
yourself whether you're comfortable with that. If you go ahead, a strong password you use nowhere
else and two-factor authentication on the Xiaomi account are sensible.

How AstroBox behaves with the band: every AstroBox connect removes the phone's Bluetooth pairing
with the band and creates it again, so you'll see pairing prompts that **you** accept (the agent
never does). Mi Fitness, the band's normal companion, reconnects afterwards and may ask you to
confirm a pairing again.

## What you get

| Piece | What it is |
|---|---|
| Agent `miband-dev:miband-dev` | Does the band work: builds, installs, checks on the device. Holds the always-true safety rules and loads a skill for each step. |
| Skill `sideload` | Installs an `.rpk` or face `.bin` through AstroBox (`sideload.sh`), hands the band back to Mi Fitness; pairing, AuthKey and Bluetooth recovery; driving the phone over adb. |
| Skill `build-face` | Watch faces with [band10-toolkit](https://github.com/utsabfdahal/band10-toolkit): IDs, widgets, the Lua layer, image formats, colour floor, the notification dot, the custom-face cap. |
| Skill `build-band-app` | Vela JS band apps and Android companions: profile-driven layout, measured text placement, animation restarts, the exit rule, messaging through Mi Fitness. |
| Skill `calibrate-quickapp` | The Vela Calib kit: a band app of test pages plus `measure.py`, which reads photos of them into a device profile; `new-device.mjs` to onboard a new device. |
| Skill `calibrate-face` | The face calibration kit: eight test faces plus `measure_face.py` for the profile's watch-face facts. |
| Skill `new-project` | Workspace setup, project templates, `DEVICES.md`, the shared signing key (`make-keys.sh`), design mock-ups. |
| `data/profiles/` | Measured default device profiles for `band10pro` and `band11` (with their evidence and `CALIBRATION.md`), and device specs (`device.json`) for every known device. |
| `data/KNOWN_DEVICES.md`, `data/CALIBRATION.md` | Known Xiaomi Vela wearables with sources and confidence; the per-device calibration notes template. |
| `vendor/` | Setup notes and a patch for band10-toolkit. |

Ask for band work in plain words ("build a Band 11 face that shows …", "install the new build",
"measure the colour floor on my band"), or call the agent with `@agent-miband-dev:miband-dev`.

## Your workspace

The plugin is read-only (Claude Code replaces it on every update). Your own things live in your
repo, the **workspace**: the current directory, or `MIBAND_WORKSPACE`.

```
README.md            map + project registry (one row per project)
devices/             DEVICES.md (your phones and bands); <model>/profile.json (your calibration),
                     evidence/, photos/ (ignored)
apps/<project>/      a band app + phone companion: PROJECT.md, band/, phone/
faces/<project>/     a watch face: PROJECT.md, generate.ts, layout.json, manifest.json, assets/
vendor/              band10-toolkit clone (ignored) + patches/
tools/               workspace copies of the calibration kits, when you build them
signing/             the shared signing key (never committed)
```

`/miband-dev:new-project` sets this up (step 2 above).

**Profiles:** every size and position the agent uses comes from the band model's device profile.
If your workspace has `devices/<model>/profile.json`, that one is used; otherwise the plugin's
shipped default. The calibration scripts write only into your workspace: the first measurement
for a model copies the default there and measures on top of it, so your calibration overrides the
default and survives plugin updates.

## Supported and known devices

Calibrated (measured profiles ship with the plugin):

| Device | Screen | Quick app (`quickapp`) | Watch face (`face`) |
|---|---|---|---|
| Xiaomi Smart Band 10 Pro | 336×480 rounded rect | measured: Vela Calib 1.0.0, 17 photos, firmware 3.101.043 | measured: face kit build 1 packed at 336×480 (`pack.mts`), all 8 faces accepted, 9 photos, firmware 3.101.043 |
| Xiaomi Smart Band 11 (the Band 10 shares the screen) | 212×520 capsule | measured: Vela Calib 2.0.0, 27 photos, firmware 4.100.139 | measured: face kit build 1 (band10-toolkit), 13 photos plus observations, firmware 4.100.139 |

Known, not calibrated: the plugin ships **unverified device specs** (screen size and shape from
maker and community sources) so the calibration kits can onboard them. Nothing about how they
render is known until you photograph the kits on one.

| Device | Spec id | Screen | Confidence in the spec |
|---|---|---|---|
| Xiaomi Smart Band 9 | `band9` | 192×490 capsule | high (the face kit doesn't fit 192 px yet) |
| Xiaomi Smart Band 9 Pro | `band9pro` | 336×480 rounded rect | high |
| REDMI Watch 5 | `redmiwatch5` | 432×514 rounded rect | high |
| REDMI Watch 6 | `redmiwatch6` | 432×514 rounded rect | high on the screen, medium on the face id |
| Xiaomi Watch S3 | `watchs3` | 466×466 circle | high |
| Xiaomi Watch S4 47 mm / S4 Sport | `watchs4` | 466×466 circle | high (S4), medium-high (Sport) |
| Xiaomi Watch S4 41 mm | `watchs4-41` | 466×466 circle | high on the screen, medium on the face id |
| Xiaomi Watch S5 46 mm | `watchs5` | 480×480 circle | high |

Sources and details: `plugins/miband-dev/data/KNOWN_DEVICES.md`. Any other Vela wearable
(rect, rounded, capsule or round screen) can be onboarded with the kit's `new-device.mjs`. **Round
screens are so far proven only on the kits' synthetic photos**, and watch faces at any canvas other
than 212×520 are **experimental on a device until F1 of the face kit has been photographed on it**
(verified on the Band 10 Pro).

Facts that are still `unknown` are listed in each model's `CALIBRATION.md`; the agent measures
before it relies on one. Tested with Band 10 Pro firmware 3.101.043, Band 11 firmware 4.100.139 and
AstroBox 2.1.0. A different firmware means re-running the kit before trusting the profile.

The Band 11 holds about **6 custom (sideloaded) faces**; the 7th is refused with `ExceedQuantity`
(the Band 10 Pro accepted at least 8). The agent deletes older builds of a face after each install
and counts before installing.

## Requirements

- An Android phone with USB debugging on, **Mi Fitness** (paired with the band) and **AstroBox**,
  signed in to your Xiaomi account (see "Before you start" above).
- For watch faces: the workspace set-up clones [band10-toolkit](https://github.com/utsabfdahal/band10-toolkit)
  into `vendor/` and applies the plugin's patch the first time you build a face.
- `adb`, Node.js, and Xiaomi's `aiot-toolkit` for Vela apps (installed per app with `npm install`).
- For an Android companion: JDK 21 (`JAVA_HOME`) and the Android SDK.
- git and Node.js for band10-toolkit.
- For calibration: Python 3 with OpenCV, NumPy, SciPy and Pillow, and a phone camera.
- Optional: a design tool in Claude (such as the Artifact tool's Design type) for mock-ups;
  without one the agent mocks screens as images or HTML in your workspace.

## Safety

This plugin drives your phone over adb (it taps through AstroBox and Mi Fitness). **Pairing
prompts and the Connect/Reconnect buttons stay with you:** the agent is told never to accept or
dismiss a Bluetooth pairing request, never to press Connect, and never to send BACK or HOME or
restart AstroBox while a connection might be in progress, because AstroBox removes and re-creates
the phone's Bluetooth bond on every connect and an interrupted connect leaves the band unpaired.
It stops and asks you instead. It won't touch the lock screen or change system settings. Keys,
photos and anything personal stay in your workspace; the agent is told never to commit keys, APKs
or calibration photos.

Not affiliated with Xiaomi, Mi Fitness, AstroBox or band10-toolkit.

## License

MIT. See [LICENSE](LICENSE).
