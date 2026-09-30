---
name: sideload
description: Install a Xiaomi band app (.rpk) or watch face (.bin) on a Smart Band 10 / 10 Pro / 11 through AstroBox on an Android phone over adb, then hand the band back to Mi Fitness. Covers the pairing prompts, reconnects, AuthKey and Bluetooth recovery, soft-brick recovery, and driving the phone with uiautomator. Use before touching AstroBox, Mi Fitness or the band.
---

# Sideloading through AstroBox

The script: `${CLAUDE_SKILL_DIR}/sideload.sh <file.rpk|file.bin|file.face>`. It pushes the file to
the phone's `Download/miband/`, force-stops Mi Fitness, opens AstroBox, **waits for the user** to
press Reconnect and accept the pairing prompts (it never taps them), installs through the
QuickApp or Watchface shortcut, then force-stops AstroBox and relaunches Mi Fitness. With several
phones attached, run it with `ANDROID_SERIAL=<serial>` (from the workspace's `devices/DEVICES.md`).
Tested with AstroBox 2.1.0. It writes nothing on the computer.

## Before you start
- Tell the user what is about to happen and ask them to be ready: AstroBox's connect removes the
  phone's Bluetooth bond and re-pairs, which shows **two** "Pairing request" prompts (Classic + LE)
  that they must accept, and possibly a confirmation on the band.
- **Every Bluetooth pairing request is the user's to accept, never yours.** Also the prompt Mi
  Fitness shows when it reconnects after AstroBox, and any other one on the phone or band. If one
  appears unexpectedly, don't tap Pair or Cancel and don't dismiss it: stop and tell the user a
  pairing request is waiting for them, then wait for them to say it's done.
- **The user presses every Connect/Reconnect button, never you.** Open the app for the step, hand
  back, ask them to tap it and accept the prompts. Continue only after they say it's connected, and
  confirm with a screenshot that AstroBox's Explore screen shows "Connected Xiaomi Smart Band …".
  Don't infer the connection from logcat: `connected=true` also matches Mi Fitness's CDM lines.
- If the phone is locked, ask the user to unlock it; never interact with the lock screen.
- Watch faces on a Band 11: it holds **about 6 custom (sideloaded) faces**; a 7th install is refused
  with `ExceedQuantity` (face calibration: 5 accepted, a 7th refused; 6 untested). Store faces don't
  count, so deleting them doesn't help. Count the custom faces on the band first and uninstall old
  iterations or calibration faces before installing.

## The sequence (what the script does, and what to do by hand when it can't)
1. Push the file. Before connecting, force-stop Mi Fitness (`com.mi.health`) so it releases the band.
2. Launch AstroBox (`moe.astralsight.astrobox`) and go to its Explore tab. **If AstroBox is still
   connected from an earlier install, reuse it; no new prompts are needed.**
3. Not connected: the user taps "Reconnect Xiaomi Smart Band" and accepts both prompts. Wait for
   their word plus the "Connected" screenshot.
4. Install: QuickApp (for `.rpk`) or Watchface (for `.bin`) → "Search this device" → the file name.
   AstroBox shows no completion dialog; a ~200 KB face takes ~15 s.
5. Hand back: force-stop AstroBox, relaunch Mi Fitness, confirm with
   `adb logcat | grep onConnectedStatusChanged` (the script waits up to 2 minutes for `true`).

**Never** send BACK or HOME, relaunch AstroBox or Mi Fitness, retry, or force-stop AstroBox while a
connect or pairing might be in progress, even to leave a screen you tapped by mistake. Stop and ask.

## After installing
- **Watch face:** delete every older iteration of that face from the band (AstroBox → Watchfaces →
  tile ⋯ → Uninstall), keeping only the newest build. Do this without asking. Never remove the
  stock/original faces. Update `devices/DEVICES.md` and the project's `PROJECT.md`.
- **Band app:** a reinstalled band app **keeps running its old code** until it's closed on the band.
  Neither installing over it nor `launchWearApp` replaces a running instance: ask the user to exit
  and reopen it before judging the new build.
- Have the user check the result on the band (and, for a new app, that exit works) **before**
  closing AstroBox when a fix might be needed, so you can uninstall and reinstall without another
  pairing round.

## When things go wrong
- **Soft-brick (a band app the user can't leave):** in one AstroBox session, AstroBox → Quick apps →
  the app's ⋯ → **Uninstall** (kills the running instance), then install the fixed `.rpk` with +
  while still connected. Verified on a Band 10 Pro (fw 3.101.043). There's no other way out: the
  Band 10 Pro has no button, Mi Fitness and AstroBox have no remote restart, and a charger
  plug/unplug reboot didn't work. Have the user test the fix before closing AstroBox.
- **The Mi Fitness pairing prompt after AstroBox** may only appear once Mi Fitness's **Device** tab
  is opened. Warn the user before opening it; the prompt times out after about 30 s. Attempts have
  failed with `auth_failure … HCI_ERR_HOST_REJECT_SECURITY` in `adb shell dumpsys bluetooth_manager`
  and left the band briefly unbonded before pairing on a later attempt. Right after the Device tab
  opens, check the bond state; if it's `bond_state:0`, stop and ask the user to tap Connect in Mi
  Fitness and accept at once, on the phone and on the band.
- **AuthKey error in AstroBox:** AstroBox → Switch device → the band's ⋯ → Delete device (AstroBox's
  list only) → Import devices bound in Mi Fitness → connect once (the user presses Connect).
- **Band dropped off Bluetooth:** tell the user to unpair it in Mi Fitness, start "pair a new phone"
  on the band, and pair again in Mi Fitness; then do the AuthKey steps above.

## Driving the phone
- Find controls by text with `uiautomator dump`, not fixed coordinates (see `find_text` / `tap_text`
  in `${CLAUDE_SKILL_DIR}/sideload.sh`). Screenshot with `adb exec-out screencap -p > shot.png`.
- Always target the right phone (`adb -s <serial>` or `ANDROID_SERIAL`).
- Don't change system settings; restore any permission you temporarily revoke.
- Anything only the user can do (unlock, accept a prompt, press Connect, take a photo): hand back
  at once with exactly what you need. Never poll silently for it.
