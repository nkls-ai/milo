#!/bin/bash
# Makes a self-signed "Milo Dev" code-signing identity in the login keychain, once per Mac.
# build-app.sh signs with it, so macOS keeps Milo's permissions across rebuilds. Not for distribution:
# that needs a Developer ID from Apple.
set -euo pipefail
NAME="${MILO_SIGN_IDENTITY:-Milo Dev}"
if security find-identity -p codesigning | grep -q "\"$NAME\""; then
  echo "\"$NAME\" already exists"; exit 0
fi
DIR=$(mktemp -d)
trap 'rm -rf "$DIR"' EXIT
openssl req -x509 -newkey rsa:2048 -keyout "$DIR/key.pem" -out "$DIR/cert.pem" -days 3650 -nodes -subj "/CN=$NAME" \
  -addext "keyUsage=critical,digitalSignature" -addext "extendedKeyUsage=critical,codeSigning" \
  -addext "basicConstraints=critical,CA:false" 2>/dev/null
openssl pkcs12 -export -legacy -inkey "$DIR/key.pem" -in "$DIR/cert.pem" -out "$DIR/id.p12" -passout pass:milo -name "$NAME"
security import "$DIR/id.p12" -k ~/Library/Keychains/login.keychain-db -P milo -T /usr/bin/codesign
echo "made \"$NAME\". Rebuild Milo, then add him once more in System Settings › Privacy & Security."
