#!/usr/bin/env bash
set -e
REPO="sarox-dev/Nodecast"
INSTALL_DIR="${HOME}/Nodecast"

echo "Installing Nodecast-*..."

# Check Docker
if ! command -v docker &>/dev/null 2>&1; then
    echo "Error: Docker is required."
    echo "Install from: https://docs.docker.com/get-docker/"
    exit 1
fi

# Get latest release tag from GitHub
echo "Checking latest version..."
LATEST_TAG=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | grep '"tag_name"' | cut -d'"' -f4)
if [ -z "$LATEST_TAG" ]; then
    echo "Error: Could not determine latest version."
    echo "Visit https://github.com/$REPO/releases to install manually."
    exit 1
fi
echo "Latest version: $LATEST_TAG"

# Download and extract latest release
echo "Downloading $LATEST_TAG..."
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"
curl -fsSL "https://github.com/$REPO/archive/refs/tags/$LATEST_TAG.zip" -o release.zip

echo "Extracting..."
unzip -o release.zip -d /tmp/nodecast-extract/ >/dev/null 2>&1
EXTRACTED_DIR=$(find /tmp/nodecast-extract/ -maxdepth 1 -type d -name "Nodecast-**" | head -1)
if [ -z "$EXTRACTED_DIR" ]; then
    echo "Error: Extraction failed."
    rm -f release.zip
    exit 1
fi
cp -r "$EXTRACTED_DIR"/. "$INSTALL_DIR/"
rm -rf /tmp/nodecast-extract/ release.zip

echo "Setting up configuration..."

# If .env doesn't exist, copy from .env.example
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "  Created .env from .env.example"
    fi
else
    # Merge new variables from .env.example into .env (without overwriting existing values)
    if [ -f .env.example ]; then
        while IFS='=' read -r key val; do
            # Skip comments and empty lines
            [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
            # If key not in .env, append it
            if ! grep -q "^${key}=" .env; then
                echo "${key}=${val}" >> .env
                echo "  Added new config: ${key}"
            fi
        done < .env.example
    fi
fi

# Start
echo "Starting Nodecast-*..."
docker compose up -d
echo ""
echo "✓ Nodecast-* is running at http://localhost:5000"

# Auto-open browser
if command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:5000 2>/dev/null || true
elif command -v open &>/dev/null; then
    open http://localhost:5000 2>/dev/null || true
fi
