#!/usr/bin/env bash
# Sideload a band app (.rpk) or watch face (.bin/.face) via AstroBox on the phone,
# then hand the band back to Mi Fitness.
#   tools/sideload.sh apps/bandlink/band/dist/com.soham.bandlink.debug.1.0.2.rpk
#   tools/sideload.sh faces/vriddhi/dist/vriddhi.bin
# Drives the phone over adb by finding on-screen text with uiautomator. Tested with
# AstroBox 2.1.0 on a Pixel 10 Pro; the file-picker steps use Android's DocumentsUI.
# With several phones attached, pick one with ANDROID_SERIAL=<serial> (see devices/DEVICES.md).
set -euo pipefail

FILE="${1:?usage: sideload.sh <file.rpk|file.bin|file.face>}"
NAME="$(basename "$FILE")"
case "$NAME" in
  *.rpk) BUTTON=QuickApp ;;
  *.bin|*.face) BUTTON=Watchface ;;
  *) echo "Unknown file type: $NAME" >&2; exit 1 ;;
esac
MIFIT=com.mi.health
ASTRO=moe.astralsight.astrobox

# Prints "x y" for the centre of the first node whose text contains $1 (empty if none).
find_text() {
  adb shell uiautomator dump /sdcard/ui.xml >/dev/null 2>&1 || true
  adb exec-out cat /sdcard/ui.xml | python3 -c '
import re, sys
needle = sys.argv[1]
for m in re.finditer(r"<node ([^>]*)>", sys.stdin.read()):
    a = dict(re.findall(r"([\w-]+)=\"([^\"]*)\"", m.group(1)))
    if needle in a.get("text", "") or needle in a.get("content-desc", ""):
        x1, y1, x2, y2 = map(int, re.findall(r"\d+", a["bounds"]))
        print((x1 + x2) // 2, (y1 + y2) // 2)
        break
' "$1"
}

# Waits up to $2 seconds for text $1, then taps it.
tap_text() {
  local deadline=$((SECONDS + ${2:-20})) xy
  while (( SECONDS < deadline )); do
    xy="$(find_text "$1")"
    if [[ -n "$xy" ]]; then adb shell input tap $xy; return 0; fi
    sleep 2
  done
  echo "Timed out waiting for \"$1\"" >&2
  return 1
}

wait_text() {
  local deadline=$((SECONDS + ${2:-20}))
  while (( SECONDS < deadline )); do
    [[ -n "$(find_text "$1")" ]] && return 0
    sleep 2
  done
  echo "Timed out waiting for \"$1\"" >&2
  return 1
}

echo "Pushing $NAME"
adb shell mkdir -p /sdcard/Download/bandlink
adb push "$FILE" /sdcard/Download/bandlink/ >/dev/null

echo "Freeing the band from Mi Fitness and connecting AstroBox"
adb shell am force-stop "$MIFIT"
adb shell monkey -p "$ASTRO" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
wait_text "Xiaomi Smart Band" 30
tap_text "Explore" 10   # AstroBox reopens on its last tab; the shortcuts live on Explore
sleep 2
# WARNING: AstroBox's connect removes the phone's Bluetooth bond to the band and re-pairs.
# Never retry, and never kill AstroBox mid-connect: that leaves the band unpaired.
if [[ -z "$(find_text "Connected Xiaomi")" ]]; then
  # The user presses Reconnect themselves (user rule, 2026-09-28); this script only waits for the result.
  echo ">>> On the phone, tap 'Reconnect Xiaomi Smart Band' in AstroBox, then accept BOTH Bluetooth 'Pairing request' prompts (Classic + LE), and confirm on the band if asked."
  if ! wait_text "Connected Xiaomi" 180; then
    echo "AstroBox did not connect. Leaving everything as is; check the phone and band before retrying." >&2
    exit 1
  fi
fi

echo "Installing via AstroBox"
tap_text "$BUTTON" 10
tap_text "Search this device" 15
adb shell input text "${NAME%.*}"
adb shell input keyevent 66
tap_text "${NAME:0:28}" 15
sleep 25   # transfer; AstroBox shows no completion dialog (a ~200 KB face takes ~15 s)

echo "Handing the band back to Mi Fitness"
adb shell am force-stop "$ASTRO"
adb logcat -c
adb shell monkey -p "$MIFIT" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
for _ in $(seq 1 24); do
  sleep 5
  if adb logcat -d | grep -q "onConnectedStatusChanged: .* true"; then
    echo "Mi Fitness reconnected."
    exit 0
  fi
done
echo "Mi Fitness hasn't reported a reconnect yet; check the band." >&2
exit 1
