#!/usr/bin/env bash
# Creates ONE signing identity for a workspace and exports it in the two formats the projects need:
#   - <workspace>/signing/band.p12 + keystore.properties -> signs the Android phone app (Gradle)
#   - <band app>/sign/{debug,release}/                    -> private.pem + certificate.pem, signs the band .rpk
#
# Mi Fitness only relays interconnect messages between a phone app and a band app that are signed
# with the same certificate, so both builds must come from this key. Run ONCE per workspace, then
# back up <workspace>/signing/ somewhere private: losing it means reinstalling every app.
#
#   make-keys.sh [--workspace DIR]             create the key and copy the PEMs into every band app
#                                              it finds; with a key already there it never
#                                              regenerates it and just does --sync (idempotent)
#   make-keys.sh --sync [--workspace DIR]      copy the existing key's PEMs into band apps that
#                                              don't have sign/ yet (a new project)
#
# Band apps found: <workspace>/apps/*/band and <workspace>/tools/vela-calib (the calibration kit's
# workspace copy). Add others as extra arguments (paths relative to the workspace).
# The workspace is --workspace, else $MIBAND_WORKSPACE, else the current directory. Nothing is
# written outside it. Needs openssl (OPENSSL=... to pick one; OpenSSL 3 preferred).
set -euo pipefail

WS="${MIBAND_WORKSPACE:-$PWD}"
SYNC=0
EXTRA=()
while (( $# )); do
  case "$1" in
    --workspace) WS="$2"; shift 2 ;;
    --sync) SYNC=1; shift ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    *) EXTRA+=("$1"); shift ;;
  esac
done
WS="$(cd "$WS" && pwd)"
SIGN="$WS/signing"
P12="$SIGN/band.p12"
PROPS="$SIGN/keystore.properties"
ALIAS="band"
if [[ -z "${OPENSSL:-}" ]]; then
  OPENSSL=openssl
  for c in /opt/homebrew/opt/openssl@3/bin/openssl /usr/local/opt/openssl@3/bin/openssl; do
    [[ -x "$c" ]] && { OPENSSL="$c"; break; }
  done
fi

band_apps() {
  local d
  for d in "$WS"/apps/*/band "$WS"/tools/vela-calib; do
    [[ -f "$d/package.json" ]] && echo "${d#$WS/}"
  done
  for d in "${EXTRA[@]+"${EXTRA[@]}"}"; do echo "$d"; done
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if [[ -f "$P12" ]] && (( ! SYNC )); then
  echo "Key exists ($P12): never regenerated; copying its PEMs to band apps that lack them (--sync)."
  SYNC=1
fi

if (( SYNC )); then
  [[ -f "$P12" && -f "$PROPS" ]] || { echo "No key in $SIGN yet: run make-keys.sh without --sync first." >&2; exit 1; }
  PASS="$(sed -n 's/^storePassword=//p' "$PROPS")"
  "$OPENSSL" pkcs12 -in "$P12" -passin "pass:$PASS" -nocerts -nodes 2>/dev/null \
    | "$OPENSSL" pkey -out "$TMP/private.pem"
  "$OPENSSL" pkcs12 -in "$P12" -passin "pass:$PASS" -clcerts -nokeys 2>/dev/null \
    | "$OPENSSL" x509 -out "$TMP/certificate.pem"
else
  mkdir -p "$SIGN"
  PASS="$("$OPENSSL" rand -hex 24)"
  # 1. Key + self-signed certificate (RSA 2048, 30 years), packed as PKCS#12.
  "$OPENSSL" req -newkey rsa:2048 -nodes -x509 -days 10950 \
    -subj "/CN=Band apps/O=Personal" \
    -keyout "$TMP/private.pem" -out "$TMP/certificate.pem" 2>/dev/null
  "$OPENSSL" pkcs12 -export -name "$ALIAS" \
    -inkey "$TMP/private.pem" -in "$TMP/certificate.pem" \
    -out "$P12" -passout "pass:$PASS"
  # 2. Gradle signing config for the phone app.
  cat > "$PROPS" <<EOF
storeFile=$P12
storePassword=$PASS
keyAlias=$ALIAS
keyPassword=$PASS
EOF
  chmod 600 "$P12" "$PROPS"
  echo "Created $P12"
fi

# 3. PEMs for the band apps (aiot-toolkit reads sign/debug and sign/release).
while IFS= read -r app; do
  [[ -z "$app" ]] && continue
  if (( SYNC )) && [[ -f "$WS/$app/sign/release/private.pem" ]]; then continue; fi
  for kind in debug release; do
    mkdir -p "$WS/$app/sign/$kind"
    cp "$TMP/private.pem" "$TMP/certificate.pem" "$WS/$app/sign/$kind/"
    chmod 600 "$WS/$app/sign/$kind/private.pem"
  done
  echo "Signing PEMs -> $app/sign/"
done < <(band_apps)

echo "SHA-256 of certificate (should match the APK's signer):"
"$OPENSSL" x509 -in "$TMP/certificate.pem" -noout -fingerprint -sha256
