# miband-dev

A [Claude Code](https://claude.com/claude-code) subagent, plus the tools it relies on, for building
watch faces and Vela JS apps for Xiaomi Smart Bands (Band 10, 10 Pro and 11) and installing them
from an Android phone over adb.

The agent keeps the band's official companion, Mi Fitness, and installs through
AstroBox. Its rules come from real installs on
real bands. They cover how AstroBox re-pairs the band and why you should never interrupt it,
recovering a band app you can't exit, Vela text metrics measured from photos, and why animations
restart on re-render.

## What's here

| Path | What it is |
|---|---|
| `.claude/agents/miband-dev.md` | The agent. Copy it into your repo's `.claude/agents/` (or `~/.claude/agents/`). |
| `tools/sideload.sh` | Pushes an `.rpk` or face `.bin` to the phone, installs it through AstroBox, then hands the band back to Mi Fitness. |
| `tools/vela-calib/` | Calibration kit: a Vela app that draws measurement pages, and `measure.py`, which reads photos of them into a device profile. |
| `devices/<model>/profile.json` | Device profiles: how the band really renders text, boxes, colour, CSS and animation, each fact marked `measured`, `assumed` or `unknown`. The Band 10 Pro profile is measured from 17 photos. |
| `devices/DEVICES.md` | Template for your phones and bands (adb serials, firmware, what's installed). |
| `templates/` | `PROJECT.md` starters for a new band app or watch face. |
| `signing/make-keys.sh` | Makes the shared signing key for the phone APK and band `.rpk`. They must share it for phone ⇄ band messages to work. |
| `vendor/` | Notes and a patch for [band10-toolkit](https://github.com/utsabfdahal/band10-toolkit), the watch-face builder the agent uses. |

## The layout the agent expects

```
README.md            map + project registry (one row per project)
devices/             DEVICES.md; <model>/profile.json, evidence/, CALIBRATION.md
apps/<project>/      a band app + phone companion: PROJECT.md, band/, phone/
faces/<project>/     a watch face: PROJECT.md, generate.ts, layout.json, manifest.json, assets/
vendor/              band10-toolkit clone (ignored) + patches/ + README.md
tools/               vela-calib, sideload.sh
signing/             the shared key (keys ignored)
templates/           PROJECT-app.md, PROJECT-face.md
```

`apps/` and `faces/` are where your own projects go. None are included here.

## Requirements

- An Android phone with USB debugging on, Mi Fitness, and AstroBox.
- `adb`, Node.js, and Xiaomi's `aiot-toolkit` for Vela apps. For an Android companion, JDK 21 and the
  Android SDK. For the calibration kit, Python 3 with OpenCV.
- A Claude Design canvas per project. The agent designs every screen there before building.

## Using it

1. Put this layout in a repo, or copy the pieces you need into yours.
2. Fill in `devices/DEVICES.md` for your phones and bands.
3. In Claude Code, ask for band work ("build a Band 10 Pro app that …", "install the new face").
   The agent reads `README.md`, the project's `PROJECT.md` and the device profile first.

Every Bluetooth pairing prompt and every Connect button stays with you: the agent is told never to
press them.
