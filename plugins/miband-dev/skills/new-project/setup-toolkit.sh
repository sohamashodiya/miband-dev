#!/usr/bin/env bash
# Sets up band10-toolkit (the watch-face builder) in the workspace: clone, pin, apply the plugin's
# patch, npm install, and link faces/node_modules. Idempotent: each step is skipped when done.
#   setup-toolkit.sh [--workspace DIR]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="$(cd "$HERE/../.." && pwd)"
PIN=549abf5046ce207327ca82fdc20b0320c27a3830
WS="${MIBAND_WORKSPACE:-$PWD}"
[[ "${1:-}" == "--workspace" ]] && WS="$2"
WS="$(cd "$WS" && pwd)"
TK="$WS/vendor/band10-toolkit"
PATCH="$WS/vendor/patches/band10-toolkit.patch"
mkdir -p "$WS/vendor/patches" "$WS/faces"
[[ -e "$PATCH" ]] || { cp "$PLUGIN/vendor/patches/band10-toolkit.patch" "$PATCH"; echo "  + vendor/patches/band10-toolkit.patch"; }
if [[ ! -d "$TK/.git" ]]; then
  git clone -q https://github.com/utsabfdahal/band10-toolkit.git "$TK"
  git -C "$TK" checkout -q "$PIN"
  echo "  + vendor/band10-toolkit (pinned $PIN)"
fi
if git -C "$TK" apply --reverse --check "$PATCH" 2>/dev/null; then
  echo "  = patch already applied"
else
  git -C "$TK" apply "$PATCH" && echo "  + patch applied"
fi
[[ -d "$TK/node_modules" ]] || { (cd "$TK" && npm install --silent) && echo "  + npm install"; }
[[ -e "$WS/faces/package.json" ]] || { cp "$HERE/templates/faces-package.json" "$WS/faces/package.json"; echo "  + faces/package.json"; }
[[ -e "$WS/faces/node_modules" ]] || { ln -sfn ../vendor/band10-toolkit/node_modules "$WS/faces/node_modules"; echo "  + faces/node_modules -> toolkit"; }
echo "band10-toolkit ready"
