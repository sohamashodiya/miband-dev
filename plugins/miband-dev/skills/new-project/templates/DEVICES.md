# Devices

Every phone and band your projects run on. Several phones are often attached at once, so always
pass `adb -s <serial>` (or `ANDROID_SERIAL=<serial>`). Each band **model** has one device profile;
every UI size comes from it.

This file lives in your workspace (`devices/DEVICES.md`). Keep serials, Bluetooth addresses and
account IDs out of any public copy of it.

## Phones

| Phone | Owner / user | adb serial | Android | On it | Used by |
|---|---|---|---|---|---|
| <model>, <diagonal>", <w>×<h>, <ppi> ppi, <w> × <h> mm | <who> | `<serial>` (USB or wireless) | <version> | Mi Fitness <version>, AstroBox <version> | `apps/<project>` |

## Bands

| Band | Model (profile) | Paired to | Firmware | Installed (custom) | Used by |
|---|---|---|---|---|---|
| Xiaomi Smart Band 10 Pro, 336×480, 1.74" | `band10pro` | <phone> | <firmware> | <app and version> | `apps/<project>` |
| Xiaomi Smart Band 11, 212×520, 1.72", 326 ppi | `band11` | <phone> | <firmware> | <face and ID> | `faces/<project>` |

Keep this table current: after every install, update the "Installed" column here as well as the
project's `PROJECT.md`. The Band 11 holds about 6 custom faces; list them here.

## Profiles

| Model | Profile in use | Firmware it was measured on | Quick app (`quickapp`) | Watch face (`face`) |
|---|---|---|---|---|
| `band10pro` | plugin default (or `devices/band10pro/profile.json` once you calibrate) | 3.101.043 | measured (Vela Calib 1.0.0, 17 photos, 2026-09-27) | measured (face kit build 1 at 336×480 via pack.mts, 9 photos, 2026-09-29) |
| `band11` | plugin default (or `devices/band11/profile.json` once you calibrate) | 4.100.139 | measured (Vela Calib 2.0.0, 27 photos, 2026-09-28/29) | measured (face kit build 1, 13 photos, 2026-09-29/30) |

Other devices: onboard with the calibration kit's `new-device.mjs` (the plugin ships unverified
specs for the Band 9 / 9 Pro, REDMI Watch 5 / 6 and Watch S3 / S4 / S5; see its `data/KNOWN_DEVICES.md`).

Rules:
- Each model also has a **device spec** (`device.json`: screen size and shape, design width, face
  canvas and packer, firmware); both calibration kits generate from it. A workspace
  `devices/<model>/device.json` overrides the plugin's shipped one.
- One profile per band **model**, tied to the firmware it was measured on (`firmware.version`).
  If your band's firmware differs, re-run the calibration kit and compare before trusting it.
- A workspace profile (`devices/<model>/profile.json`) overrides the plugin's shipped default.
  The kits create it (a copy of the default) the first time they write a measurement.
- Builds generate from the profile (`npm run device`, run before every build); never copy numbers by hand.
- A fact that is missing or `unknown` must be measured (add a calibration page) before UI depends on it.
- `quickapp` facts describe the Vela JS-app renderer; `face` facts describe the watch-face engine.
  One never stands in for the other.
- A new band model is calibrated (whole kit, new profile) before any UI work for it.
