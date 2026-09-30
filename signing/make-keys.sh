#!/usr/bin/env bash
# Creates ONE signing identity and exports it in the two formats the project needs:
#   - signing/bandlink.p12            -> signs the Android phone app (Gradle)
#   - <band app>/sign/{debug,release}/ -> private.pem + certificate.pem, signs the band .rpk
#     (apps/bandlink/band, apps/bart-watch/band, tools/vela-calib; add new band apps to BAND_APPS)
#
# Mi Fitness only relays interconnect messages between a phone app and a band app
# that are signed with the same certificate, so both builds must come from this key.
# Run once. Back up signing/ somewhere safe; losing it means reinstalling both apps.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SIGN="$ROOT/signing"
P12="$SIGN/bandlink.p12"
PROPS="$SIGN/keystore.properties"
ALIAS="bandlink"
OPENSSL="${OPENSSL:-/opt/homebrew/opt/openssl@3/bin/openssl}"

if [[ -f "$P12" ]]; then
  echo "Refusing to overwrite existing $P12 (delete it yourself if you really mean to)." >&2
  exit 1
fi

PASS="$("$OPENSSL" rand -hex 24)"

# 1. Key + self-signed certificate (RSA 2048, 30 years), packed as PKCS#12.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
"$OPENSSL" req -newkey rsa:2048 -nodes -x509 -days 10950 \
  -subj "/CN=BandLink/O=Personal" \
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

# 3. PEMs for the band app (aiot-toolkit reads sign/debug and sign/release).
BAND_APPS=(apps/bandlink/band apps/bart-watch/band tools/vela-calib)
for app in "${BAND_APPS[@]}"; do
  for kind in debug release; do
    mkdir -p "$ROOT/$app/sign/$kind"
    cp "$TMP/private.pem" "$TMP/certificate.pem" "$ROOT/$app/sign/$kind/"
    chmod 600 "$ROOT/$app/sign/$kind/private.pem"
  done
done
chmod 600 "$P12" "$PROPS"

echo "Created $P12"
echo "SHA-256 of certificate (should match the APK's signer):"
"$OPENSSL" x509 -in "$TMP/certificate.pem" -noout -fingerprint -sha256
