#!/usr/bin/env bash
# Copies a calibration kit from the plugin into the workspace (tools/<kit>/), only when it isn't
# there yet: building a kit writes files, and the plugin copy is read-only. Idempotent. It also
# refreshes tools/plugin-defaults/ (the plugin's shipped profiles and specs) for the copies to read.
#   copy-kit.sh vela-calib|face-calib [--workspace DIR]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$(cd "$HERE/../.." && pwd)"
KIT="${1:?usage: copy-kit.sh vela-calib|face-calib [--workspace DIR]}"
[[ "$KIT" == vela-calib || "$KIT" == face-calib ]] || { echo "unknown kit $KIT" >&2; exit 2; }
WS="${MIBAND_WORKSPACE:-$PWD}"
[[ "${2:-}" == "--workspace" ]] && WS="$3"
WS="$(cd "$WS" && pwd)"
DEST="$WS/tools/$KIT"
# The shipped profiles and device specs, for kit copies (they can't see the plugin): always refreshed,
# they are the plugin's defaults, never the user's data (that is devices/).
rm -rf "$WS/tools/plugin-defaults"
mkdir -p "$WS/tools/plugin-defaults"
cp -R "$PLUGIN/data/." "$WS/tools/plugin-defaults/"
echo "tools/plugin-defaults refreshed from the plugin (shipped profiles and device specs)"
if [[ -d "$DEST" ]]; then
  echo "tools/$KIT exists, kept (compare with $PLUGIN/tools/$KIT after a plugin update)"
  exit 0
fi
mkdir -p "$WS/tools"
cp -R "$PLUGIN/tools/$KIT" "$DEST"
find "$DEST" -name __pycache__ -prune -exec rm -rf {} +
echo "tools/$KIT copied from the plugin"
if [[ "$KIT" == vela-calib ]]; then echo "Next: (cd tools/vela-calib && npm install); make-keys.sh --sync gives it sign/"; fi
