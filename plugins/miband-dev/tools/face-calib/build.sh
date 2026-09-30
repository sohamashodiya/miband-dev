#!/usr/bin/env bash
# Face calibration kit: generate every page, then validate and package each face.
#   tools/face-calib/build.sh [<device id>|all]      (default all = every device with layouts/<id>.json)
# Devices whose spec says builder "band10-toolkit" (the Band 10 / 11, 212 x 520) go through the
# band10-toolkit CLI (validate + package), like any face project. Faces the CLI
# can't make (any other canvas size, e.g. every Band 10 Pro page, and F8, which puts the Lua layer
# on the always-on face) go through pack.mts, which calls the same native packer; those are
# experimental on their device until photographed. band10-toolkit faces are still validated by the
# CLI first.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
if [ -f "$ROOT/.claude-plugin/plugin.json" ]; then
  echo "This is the plugin's read-only copy of the kit. Copy it into your workspace first:" >&2
  echo "  $ROOT/skills/new-project/copy-kit.sh face-calib   (from the workspace root; faces also need setup-toolkit.sh)" >&2
  exit 2
fi
TK="$ROOT/vendor/band10-toolkit"
TSX="$TK/node_modules/.bin/tsx"
WHICH="${1:-all}"

cd "$HERE"
python3 gen.py "$WHICH"

LIST="$(python3 gen.py --list)"                 # "<id> <builder>" per onboarded device
builder_of() { echo "$LIST" | awk -v m="$1" '$1 == m { print $2 }'; }
models=($(echo "$LIST" | awk '{ print $1 }'))
[ "$WHICH" != all ] && models=("$WHICH")
for m in "${models[@]}"; do
  echo "== $m ($(builder_of "$m"))"
  for d in "$HERE"/faces/"$m"/f*/; do
    d="${d%/}"
    packer=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['packer'])" "$d/calib.json")
    if [ "$(builder_of "$m")" = band10-toolkit ]; then
      (cd "$TK" && INIT_CWD="$HERE" "$TSX" cli/index.ts validate "$d") | grep -v '^▲ WARNING WIDGET_CLIPPED\|^  Widget' || true
      (cd "$TK" && INIT_CWD="$HERE" "$TSX" cli/index.ts validate "$d" --json) \
        | python3 -c "import json,sys; r=json.load(sys.stdin); sys.exit(0 if r['valid'] else 1)"
    fi
    if [ "$packer" = toolkit-cli ]; then
      (cd "$TK" && INIT_CWD="$HERE" "$TSX" cli/index.ts package "$d") | grep -E '✓ Packaged|\.bin$'
    else
      "$TSX" "$HERE/pack.mts" "$d"
    fi
  done
done
