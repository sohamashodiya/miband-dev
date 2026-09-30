#!/usr/bin/env bash
# Sets up (or completes) a miband-dev workspace. Idempotent: it only adds what's missing and never
# overwrites a file the user has. Writes only inside the workspace.
#   init-workspace.sh [--workspace DIR]     (default: $MIBAND_WORKSPACE, else the current directory)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
T="$HERE/templates"
WS="${MIBAND_WORKSPACE:-$PWD}"
[[ "${1:-}" == "--workspace" ]] && WS="$2"
mkdir -p "$WS"
WS="$(cd "$WS" && pwd)"
case "$WS/" in "$(cd "$HERE/../.." && pwd)/"*) echo "Refusing: $WS is inside the plugin." >&2; exit 2 ;; esac

did() { echo "  + $1"; }
kept() { echo "  = $1 (exists, kept)"; }

echo "Workspace: $WS"
if git -C "$WS" rev-parse --git-dir >/dev/null 2>&1; then kept "git repository"; else git -C "$WS" init -q && did "git init"; fi
for d in devices apps faces; do
  if [[ -d "$WS/$d" ]]; then kept "$d/"; else mkdir -p "$WS/$d" && did "$d/"; fi
done
copy_new() { # template, destination
  if [[ -e "$WS/$2" ]]; then kept "$2"; else mkdir -p "$(dirname "$WS/$2")"; cp "$T/$1" "$WS/$2"; did "$2"; fi
}
copy_new README-workspace.md README.md
copy_new DEVICES.md devices/DEVICES.md
copy_new faces-package.json faces/package.json
# .gitignore: add any template line that's missing (comments and blank lines only on a new file)
if [[ -e "$WS/.gitignore" ]]; then
  added=0
  while IFS= read -r line; do
    [[ -z "$line" || "$line" == \#* ]] && continue
    grep -qxF -- "$line" "$WS/.gitignore" || { echo "$line" >> "$WS/.gitignore"; added=$((added + 1)); }
  done < "$T/workspace.gitignore"
  if (( added )); then did ".gitignore (+$added lines)"; else kept ".gitignore"; fi
else
  cp "$T/workspace.gitignore" "$WS/.gitignore"; did ".gitignore"
fi
echo "Next: fill in devices/DEVICES.md (phone, adb serial, band, firmware). Signing key: make-keys.sh when the first band app starts."
