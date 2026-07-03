#!/usr/bin/env bash
set -e
REPO="sarox-dev/Recollect"
INSTALL_DIR="${HOME}/Recollect"
echo "Installing Recollect..."

# Check Docker
if ! command -v docker &>/dev/null 2>&1; then
    echo "Error: Docker is required."
    echo "Install from: https://docs.docker.com/get-docker/"
    exit 1
fi

# Download latest release
echo "Downloading latest release..."
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"
curl -fsSL "https://github.com/$REPO/archive/refs/tags/v0.0.1.zip" -o release.zip
unzip -o release.zip -d /tmp/recollect-extract/ >/dev/null 2>&1
cp -r /tmp/recollect-extract/Recollect-*/* "$INSTALL_DIR/"
rm -rf /tmp/recollect-extract/ release.zip

# Setup .env from example if missing
if [ ! -f .env ] && [ -f .env.example ]; then
    cp .env.example .env
    echo "Created .env from .env.example"
fi

# Start
echo "Starting Recollect..."
docker compose up -d
echo ""
echo "✓ Recollect is running at http://localhost:5000"

# Auto-open browser
if command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:5000 2>/dev/null || true
elif command -v open &>/dev/null; then
    open http://localhost:5000 2>/dev/null || true
fi
