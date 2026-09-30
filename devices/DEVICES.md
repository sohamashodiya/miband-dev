# Devices

Every phone and band your projects run on. Several phones are often attached at once, so always
pass `adb -s <serial>`. Each band **model** has one device profile in `devices/<model>/` (see
"Profiles" below); every UI size comes from it.

Fill in the two tables for your own devices. Keep serials, Bluetooth addresses and account IDs
out of any public copy of this file.

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
project's `PROJECT.md`.

## Profiles

| Model | Profile | Firmware it was measured on | Quick app (`quickapp`) | Watch face (`face`) |
|---|---|---|---|---|
| `band10pro` | `devices/band10pro/profile.json` | 3.101.043 | measured (Vela Calib 1.0.0, 17 photos, 2026-09-27) | unknown (not calibrated) |
| `band11` | none yet | - | pending: run the kit (`devices/band11/CALIBRATION.md`) | pending |

Rules:
- One profile per band **model**, tied to the firmware it was measured on (`firmware.version`).
  After a firmware update, re-run the calibration kit (`tools/vela-calib`) and compare before
  trusting the profile.
- Builds generate from the profile (`npm run device`, run before every build); never copy numbers by hand.
- A fact that is missing or `unknown` must be measured (add a calibration page) before UI depends on it.
- `quickapp` facts describe the Vela JS-app renderer; `face` facts describe the watch-face engine.
  One never stands in for the other.
- A new band model is calibrated (whole kit, new profile) before any UI work for it.
