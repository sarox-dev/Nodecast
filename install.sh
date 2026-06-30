#!/usr/bin/env bash
set -e

REPO="https://github.com/sarox-dev/Recollect.git"
DIR="$(pwd)/Recollect"

echo "======================================"
echo " Recollect installer (current dir)"
echo "======================================"
echo ""
echo "Target directory: $DIR"
echo ""

# checks
command -v docker >/dev/null 2>&1 || {
  echo "Docker not installed"
  exit 1
}

command -v git >/dev/null 2>&1 || {
  echo "Git not installed"
  exit 1
}

if [ -d "$DIR/.git" ]; then
    echo "Recollect is already installed."

    read -rp "Update existing installation? [Y/n] " answer

    if [[ ! "$answer" =~ ^[Nn]$ ]]; then
        git -C "$DIR" pull --rebase
    else
        exit 0
    fi
else
    git clone "$REPO" "$DIR"
fi

cd "$DIR"

echo ""
echo "Setting up env..."

[ -f .env ] || cp .env.example .env 2>/dev/null || true

echo ""
echo "Starting Recollect..."

docker compose up -d

PORT=$(grep APP_PORT .env 2>/dev/null | cut -d '=' -f2)
PORT=${PORT:-5000}

echo ""
echo "======================================"
echo "✓ Recollect running"
echo "→ http://localhost:$PORT"
echo "======================================"