#!/usr/bin/env bash
set -e

CONFIG="${HOME}/.nodecast/config"
if [ ! -f "$CONFIG" ]; then
    echo "Nodecast not configured. Run install-updater.sh first."
    exit 1
fi

INSTALL_DIR=$(grep "^INSTALL_DIR=" "$CONFIG" | cut -d= -f2-)
APP_PORT=$(grep "^APP_PORT=" "$CONFIG" | cut -d= -f2-)
APP_PORT="${APP_PORT:-5000}"

HEALTH=$(curl -fsSL "http://localhost:${APP_PORT}/api/server/health" 2>/dev/null || echo "")
if [ -z "$HEALTH" ]; then
    exit 0
fi

CAN_UPDATE=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('can_update', False))" 2>/dev/null || echo "false")
if [ "$CAN_UPDATE" != "True" ]; then
    exit 0
fi

cd "$INSTALL_DIR"
git pull origin main 2>/dev/null || exit 0

docker compose down 2>/dev/null || true
docker compose up -d --build 2>/dev/null || true