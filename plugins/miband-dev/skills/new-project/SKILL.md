---
name: new-project
description: Set up (idempotently) a workspace for Xiaomi band apps and watch faces (folder layout, registry README, devices/DEVICES.md, .gitignore; the signing key, band10-toolkit and calibration kit copies when first needed), start a new band app or watch face project from the templates, and make its design mock-ups. Use for a first-time setup, a new project, or a new phone or band.
---

# Workspace and new projects

Scripts (all idempotent, all write only into the workspace): `${CLAUDE_SKILL_DIR}/init-workspace.sh`,
`make-keys.sh`, `setup-toolkit.sh`, `copy-kit.sh`. Templates (read-only): `${CLAUDE_SKILL_DIR}/templates/`.
The agent's tools, the kits and the shipped profiles stay in the plugin; only the user's own
projects and data (and kit copies, once they calibrate) live in the workspace.

## The workspace contract
```
README.md            map + project registry (one row per project)
devices/             DEVICES.md; <model>/profile.json (their calibration), evidence/, photos/ (ignored)
apps/<project>/      a band app + phone companion: PROJECT.md, band/, phone/, (design/)
faces/<project>/     a watch face: PROJECT.md, generate.ts, layout.json, manifest.json, assets/, script/
faces/package.json   runs the toolkit CLI for any face (node_modules -> the toolkit's)
vendor/              band10-toolkit clone (ignored) + patches/band10-toolkit.patch
tools/               workspace copies of the calibration kits (+ plugin-defaults/, ignored), only once needed
signing/             the shared key (keys ignored)
```
- **One folder per project** (`apps/<name>/` or `faces/<name>/`); nothing project-specific at the top level.
- Profiles and specs: `devices/<model>/profile.json` / `device.json` in the workspace override the
  plugin's shipped defaults (`${CLAUDE_PLUGIN_ROOT}/data/profiles/<model>/`). Never copy defaults in
  by hand; the kits create the workspace profile on their first write.

## First-time setup (`/miband-dev:new-project` in an empty folder or an existing repo)
Everything here is idempotent: run it again at any time and it only adds what's missing. Nothing
the user has is overwritten. Tell the user what each step adds.
1. **Layout and files:** `"${CLAUDE_SKILL_DIR}/init-workspace.sh"` from the workspace root. It runs
   `git init` if needed, creates `devices/`, `apps/`, `faces/`, and adds `README.md` (registry),
   `devices/DEVICES.md`, `faces/package.json` and `.gitignore` from the templates when they don't
   exist (an existing `.gitignore` only gets the missing lines).
2. **Fill in `devices/DEVICES.md` with the user:** each phone (model, screen, adb serial from
   `adb devices -l`, Android version, Mi Fitness and AstroBox versions) and each band (model,
   firmware from Mi Fitness, paired phone). Remind them to keep serials, Bluetooth addresses and
   account IDs out of any public copy.
3. **Check the band's firmware** against the profile's `firmware.version` (Band 10 Pro 3.101.043,
   Band 11 4.100.139). A different firmware means re-running calibration before trusting the
   profile (`calibrate-quickapp`, `calibrate-face`). A device with no shipped profile has to be
   onboarded and calibrated first (`calibrate-quickapp`).
4. **AstroBox:** make sure the user has read the README's "Before you start" (AstroBox is a
   third-party app; it needs them to sign in to their Xiaomi account in it to get the band's auth
   key; its connect re-pairs the band). It's their decision; don't sign in for them.
5. **Only when needed, later (each idempotent):**
   - first band app: `"${CLAUDE_SKILL_DIR}/make-keys.sh"` (creates the signing key once; later runs
     never regenerate it and just copy the PEMs into new band apps), and
     `"${CLAUDE_SKILL_DIR}/copy-kit.sh" vela-calib` (the band apps' `npm run device` uses its
     `export.mjs`). Tell the user to back up `signing/` privately: losing it means reinstalling
     every app, and phone ⇄ band messages only work when the APK and the `.rpk` share this
     certificate.
   - first watch face: `"${CLAUDE_SKILL_DIR}/setup-toolkit.sh"` (clones band10-toolkit into
     `vendor/`, pins it, applies the plugin's patch, `npm install`, links `faces/node_modules`).
   - first calibration: `"${CLAUDE_SKILL_DIR}/copy-kit.sh" vela-calib` / `face-calib` (the kits'
     builds write files, so they run from a workspace copy; the copy reads the shipped profiles and
     specs from `tools/plugin-defaults/`, refreshed on every run).
6. **Tools the user installs** (check with `which`, and say what's missing): `adb`, Node.js, git;
   JDK 21 and the Android SDK for companions; Python 3 with OpenCV, NumPy, SciPy and Pillow for
   calibration. On the phone: USB debugging, Mi Fitness, AstroBox.

## A new project
1. Copy `templates/PROJECT-app.md` or `templates/PROJECT-face.md` into the new folder as
   `PROJECT.md` and fill it in: target phone (with adb serial) and band, who uses it and what that
   means for the UI, style rules.
2. Add a row to `README.md`'s registry.
3. Make the design mock-ups (below) and get approval before any code.
4. Band app: package name `com.<you>.<name>`, the same for the APK and the `.rpk`; add
   `"device": "node ../../../tools/vela-calib/export.mjs <model> src/common/device.js"` and a
   `prebuild` that runs it (`copy-kit.sh vela-calib` provides it), a fit test that runs
   `export.mjs --check`, and run `make-keys.sh` for `sign/`. Details: `build-band-app`.
5. Face: a generator `faces/<name>/generate.ts` writing `assets/`, `layout.json`, `script/`.
   Details: `build-face`.

## Design mock-ups (every app and face, always)
The user can't tell what was built for each screen and scenario from code or install logs, so
**every** task that creates or changes UI creates or updates the project's mock-ups, including small
visual tweaks and fixes made after on-device testing.
- **Where:** if a design tool is available (for example the Artifact tool with a Design type), keep
  **one design project per app or face**, titled "<Project> · Design": look for an existing one
  first (the registry, the project's `PROJECT.md`, then the tool's listing) and update it; create
  one only when none exists. Otherwise mock the screens as images or an HTML page in the project's
  `design/` folder and open it in the user's browser. Record the link or path in the registry and
  in `PROJECT.md`.
- **Mock every screen and every state**, not just the happy path: empty/no data, loading, live,
  stale, disconnected, alert, snoozed, dismissed, settings, permission/setup prompts, errors. For a
  band app, draw the phone and the band side by side (Band 10 Pro 336×480, Band 10/11 212×520, the
  phone at its real dp size), so the user can check the whole flow across both devices.
- **True physical scale.** Look up each device's real screen size (diagonal and ppi) and compute
  width and height in mm. Pick one px-per-mm scale for the board and draw every device frame at it,
  with the band content scaled to its physical frame. Magnified detail views are fine, labelled
  with their zoom (e.g. "2.3× zoom"). Label each board with its scale, note the physical height in
  mm of key text on the band, and record the dimensions and scale in `PROJECT.md`.
- **Approval first** for new work; for fixes found on the device, fix the code, then update the
  board before reporting back. Include the link or path in your final report.

## Git conventions
Commit a restore point before a large edit and after each verified build. Prefix commit messages
with the project folder name (`<project>: band 2.0.16 …`, `repo: …` for cross-project changes).
Keep the registry's "on device" column current. Never commit signing keys (`signing/*.p12`,
`keystore.properties`, any `sign/`), APKs, calibration photos, or anyone's home address or other
personal details.
