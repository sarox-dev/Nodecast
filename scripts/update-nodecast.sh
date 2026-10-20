#!/usr/bin/env bash
set -Eeuo pipefail

STATE_DIR="${HOME}/.nodecast"
CONFIG="$STATE_DIR/config"
[[ -f "$CONFIG" ]] || exit 0
. "$CONFIG"
LOCK="$STATE_DIR/update.lock"
mkdir "$LOCK" 2>/dev/null || exit 0
trap 'rmdir "$LOCK"' EXIT

HEALTH="$(curl -fsSL "http://localhost:${APP_PORT:-5000}/api/server/health" 2>/dev/null || true)"
[[ -n "$HEALTH" ]] || exit 0
CAN_UPDATE="$(printf '%s' "$HEALTH" | python3 -c 'import json,sys; print(str(json.load(sys.stdin).get("can_update",False)).lower())' 2>/dev/null || true)"
[[ "$CAN_UPDATE" == "true" ]] || exit 0

CURRENT="$(printf '%s' "$HEALTH" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version","0.0.0"))')"
LATEST="$(curl -fsSL https://api.github.com/repos/sarox-dev/Nodecast/releases/latest | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tag_name","").lstrip("v"))')"
[[ -n "$LATEST" ]] || exit 0
NEWER="$(python3 - "$CURRENT" "$LATEST" <<'PY'
import re,sys
def v(s): return tuple(int(x) for x in re.findall(r'\d+',s)[:3])
print(str(v(sys.argv[2]) > v(sys.argv[1])).lower())
PY
)"
[[ "$NEWER" == "true" ]] || exit 0

BACKUP="$STATE_DIR/backups/$CURRENT-$(date +%Y%m%d%H%M%S)"
mkdir -p "$BACKUP"
cp -a "$INSTALL_DIR/.env" "$INSTALL_DIR/contents" "$BACKUP/"

if [[ "$MODE" == "docker" ]]; then
  (cd "$INSTALL_DIR" && docker compose down)
else
  if [[ "$(uname -s)" == "Darwin" ]]; then launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/dev.nodecast.app.plist" 2>/dev/null || true
  else systemctl --user stop nodecast.service; fi
fi

UPDATE_TMP="$(mktemp -d)"
trap 'rm -rf "$UPDATE_TMP"; rmdir "$LOCK" 2>/dev/null || true' EXIT
ASSET_ROOT="https://github.com/sarox-dev/Nodecast/releases/download/v${LATEST}"
curl -fsSL "$ASSET_ROOT/install.sh" -o "$UPDATE_TMP/install.sh"
curl -fsSL "$ASSET_ROOT/SHA256SUMS" -o "$UPDATE_TMP/SHA256SUMS"
EXPECTED="$(awk '$2 == "install.sh" { print $1 }' "$UPDATE_TMP/SHA256SUMS")"
[[ "$EXPECTED" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "Installer checksum is missing or invalid." >&2; exit 1; }
if command -v sha256sum >/dev/null; then
  ACTUAL="$(sha256sum "$UPDATE_TMP/install.sh" | awk '{ print $1 }')"
else
  ACTUAL="$(shasum -a 256 "$UPDATE_TMP/install.sh" | awk '{ print $1 }')"
fi
[[ "$ACTUAL" == "$EXPECTED" ]] || { echo "Installer checksum verification failed." >&2; exit 1; }
NODECAST_INSTALL_DIR="$INSTALL_DIR" NODECAST_MODE="$MODE" NODECAST_AUTO_UPDATE=true bash "$UPDATE_TMP/install.sh"

for _ in $(seq 1 30); do
  curl -fsSL "http://localhost:${APP_PORT:-5000}/api/version" >/dev/null 2>&1 && exit 0
  sleep 2
done
echo "Nodecast update completed but the health check failed. Backup: $BACKUP" >&2
exit 1
