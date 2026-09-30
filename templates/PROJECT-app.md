# <Project>: project notes

Read this before any <Project> work. These facts apply only to this project.
(Copied from `templates/PROJECT-app.md`. Add the project to `README.md`'s registry.)

## What and who
- What it does, in one or two lines. Spec: `REQUIREMENTS.md` (if any).
- **Who uses it** (age, eyesight, language, how they hold the band) and what that means for the UI.

## Devices
- Phone: <model>, adb serial `<serial>` (always pass `-s`). Band: <model> (`devices/<model>/`).
- Add both to `devices/DEVICES.md`. The band model needs a calibrated profile before any UI work.

## Code
- `band/`: Vela JS app, package `com.soham.<name>`. `npm test`; `npm run build` → `dist/*.rpk` (`prebuild` runs `npm run device`: `node ../../../tools/vela-calib/export.mjs <model> src/common/device.js`). `node_modules` → `../../bandlink/band/node_modules`; `sign/` = copy of the shared PEMs (add the app to `signing/make-keys.sh`'s `BAND_APPS`).
- `phone/`: Kotlin companion, same package, keystore `../../../signing/keystore.properties`. `JAVA_HOME=/opt/homebrew/opt/openjdk@21 ./gradlew testDebugUnitTest assembleDebug`.
- Must let the user exit on the band (`onBackPress`, swipe right, touch fallback).

## Style
- Project-only style rules.

## Design project
- "<Project> · Design": <URL> (also in the registry). Scale: <px per mm>, phone <w × h mm>, band <w × h mm>.

## Versions
- On the device: band <x.y.z> (versionCode N), phone <x.y.z>. Built, not installed: …

## Learned on the device
- Dated facts from device tests.
