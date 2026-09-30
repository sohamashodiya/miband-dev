# miband-dev

A [Claude Code](https://claude.com/claude-code) plugin for building watch faces and Vela JS apps
for Xiaomi Smart Bands (Band 10, 10 Pro and 11) and installing them from an Android phone over adb.

It keeps the band's official companion, Mi Fitness, and installs through AstroBox. Its rules come
from real installs on real bands: how AstroBox re-pairs the band and why you must never interrupt
it, recovering a band app you can't exit, Vela text metrics and watch-face engine behaviour
measured from photos, and why animations restart on re-render.

## Install

In Claude Code:

```
/plugin marketplace add sohamashodiya/miband-dev
/plugin install miband-dev@miband-dev
```

(From a shell: `claude plugin marketplace add sohamashodiya/miband-dev`, then
`claude plugin install miband-dev@miband-dev`.) Run `/reload-plugins` or start a new session. To
update later: `/plugin marketplace update miband-dev`, then update the plugin from `/plugin`.

## What you get

| Piece | What it is |
|---|---|
| Agent `miband-dev:miband-dev` | Does the band work: builds, installs, checks on the device. Holds the always-true safety rules and loads a skill for each step. |
| Skill `sideload` | Installs an `.rpk` or face `.bin` through AstroBox (`sideload.sh`), hands the band back to Mi Fitness; pairing, AuthKey and Bluetooth recovery; driving the phone over adb. |
| Skill `build-face` | Watch faces with [band10-toolkit](https://github.com/utsabfdahal/band10-toolkit): IDs, widgets, the Lua layer, image formats, colour floor, the notification dot, the custom-face cap. |
| Skill `build-band-app` | Vela JS band apps and Android companions: profile-driven layout, measured text placement, animation restarts, the exit rule, messaging through Mi Fitness. |
| Skill `calibrate-quickapp` | The Vela Calib kit: a band app of test pages plus `measure.py`, which reads photos of them into a device profile. |
| Skill `calibrate-face` | The face calibration kit: eight test faces plus `measure_face.py` for the profile's watch-face facts. |
| Skill `new-project` | Workspace setup, project templates, `DEVICES.md`, the shared signing key (`make-keys.sh`), design mock-ups. |
| `data/profiles/` | Measured default device profiles for `band10pro` and `band11`, with their evidence and `CALIBRATION.md`. |
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

Ask the agent to set it up (the `new-project` skill copies the templates in and walks you through
`DEVICES.md` and the signing key).

**Profiles:** every size and position the agent uses comes from the band model's device profile.
If your workspace has `devices/<model>/profile.json`, that one is used; otherwise the plugin's
shipped default. The calibration scripts write only into your workspace: the first measurement
for a model copies the default there and measures on top of it, so your calibration overrides the
default and survives plugin updates.

## What's measured

| Model | Quick app (`quickapp`) | Watch face (`face`) |
|---|---|---|
| Band 10 Pro (336×480) | measured: Vela Calib 1.0.0, 17 photos, firmware 3.101.043 | unknown (no face calibration yet; 336×480 faces are unverified) |
| Band 11 (212×520 capsule; the Band 10 shares the screen) | measured: Vela Calib 2.0.0, 27 photos, firmware 4.100.139 | measured: face kit build 1, 13 photos plus observations, firmware 4.100.139 |

Facts that are still `unknown` are listed in each model's `CALIBRATION.md`; the agent measures
before it relies on one. Tested with Band 10 Pro firmware 3.101.043, Band 11 firmware 4.100.139 and
AstroBox 2.1.0. A different firmware means re-running the kit before trusting the profile.

The Band 11 holds about **6 custom (sideloaded) faces**; the 7th is refused with `ExceedQuantity`.
The agent deletes older builds of a face after each install and counts before installing.

## Requirements

- An Android phone with USB debugging on, **Mi Fitness** (paired with the band) and **AstroBox**.
- `adb`, Node.js, and Xiaomi's `aiot-toolkit` for Vela apps (installed per app with `npm install`).
- For an Android companion: JDK 21 (`JAVA_HOME`) and the Android SDK.
- For watch faces: git and Node.js for band10-toolkit (set up once per workspace).
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
