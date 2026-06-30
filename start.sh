#!/usr/bin/env bash
set -e

if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

PORT=${APP_PORT:-5000}

docker compose up -d

echo ""
echo "✓ Recollect is running"
echo "→ http://localhost:${PORT}"