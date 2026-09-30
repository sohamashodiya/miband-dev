#!/usr/bin/env bash
# Face calibration kit: generate every page, then validate and package each face.
#   tools/face-calib/build.sh [band11|band10pro|all]      (default all; run from the workspace copy)
# Band 11 faces go through the band10-toolkit CLI (validate + package), like any face
# project. Faces the CLI can't make (every Band 10 Pro page: its schema only allows
# 212 x 520; F8, which puts the Lua layer on the always-on face) go through pack.mts, which calls the
# same native packer. Band 11 F8 is still validated by the CLI first.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
if [ -f "$ROOT/.claude-plugin/plugin.json" ]; then
  echo "This is the plugin's read-only copy of the kit. Copy it into your workspace first:" >&2
  echo "  cp -R \"$HERE\" <workspace>/tools/face-calib   (needs <workspace>/vendor/band10-toolkit)" >&2
  exit 2
fi
TK="$ROOT/vendor/band10-toolkit"
TSX="$TK/node_modules/.bin/tsx"
WHICH="${1:-all}"

cd "$HERE"
python3 gen.py "$WHICH"

models=(band11 band10pro)
[ "$WHICH" != all ] && models=("$WHICH")
for m in "${models[@]}"; do
  echo "== $m"
  for d in "$HERE"/faces/"$m"/f*/; do
    d="${d%/}"
    packer=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['packer'])" "$d/calib.json")
    if [ "$m" = band11 ]; then
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
