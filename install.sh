#!/usr/bin/env bash
set -e
REPO="sarox-dev/Nodecast"

echo "Installing Nodecast..."
echo ""

# Check Docker
if ! command -v docker &>/dev/null 2>&1; then
    echo "Error: Docker is required."
    echo "Install from: https://docs.docker.com/get-docker/"
    exit 1
fi

# Ask install directory
DEFAULT_DIR="${HOME}/Nodecast"
read -r -p "Install to [${DEFAULT_DIR}]: " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_DIR}"

# Resolve tilde
INSTALL_DIR="${INSTALL_DIR/#\~/$HOME}"

# Create directory
mkdir -p "$INSTALL_DIR" || { echo "Error: Cannot create $INSTALL_DIR"; exit 1; }
cd "$INSTALL_DIR"

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
curl -fsSL "https://github.com/$REPO/archive/refs/tags/$LATEST_TAG.zip" -o release.zip

echo "Extracting..."
unzip -o release.zip -d /tmp/nodecast-extract/ >/dev/null 2>&1
EXTRACTED_DIR=$(find /tmp/nodecast-extract/ -maxdepth 1 -type d -name "Nodecast-**" | head -1)
if [ -z "$EXTRACTED_DIR" ]; then
    echo "Error: Extraction failed."
    rm -f release.zip
    exit 1
fi
if [ -d "$INSTALL_DIR/searxng" ]; then
    # searxng files may be root-owned from Docker; remove before overwrite
    sudo rm -rf "$INSTALL_DIR/searxng" 2>/dev/null || rm -rf "$INSTALL_DIR/searxng"
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

# Generate keys if missing
if [ -f .env ]; then
    if grep -q "^JWT_SECRET=$" .env || ! grep -q "^JWT_SECRET=" .env; then
        NEW_SECRET=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || echo "")
        if [ -n "$NEW_SECRET" ]; then
            if grep -q "^JWT_SECRET=" .env; then
                sed -i.bak "s/^JWT_SECRET=.*/JWT_SECRET=$NEW_SECRET/" .env && rm -f .env.bak
            else
                echo "JWT_SECRET=$NEW_SECRET" >> .env
            fi
            echo "  Generated JWT_SECRET"
        fi
    fi
    if grep -q "^ENCRYPTION_KEY=$" .env || ! grep -q "^ENCRYPTION_KEY=" .env; then
        NEW_KEY=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || echo "")
        if [ -n "$NEW_KEY" ]; then
            if grep -q "^ENCRYPTION_KEY=" .env; then
                sed -i.bak "s/^ENCRYPTION_KEY=.*/ENCRYPTION_KEY=$NEW_KEY/" .env && rm -f .env.bak
            else
                echo "ENCRYPTION_KEY=$NEW_KEY" >> .env
            fi
            echo "  Generated ENCRYPTION_KEY"
        fi
    fi
fi

# Read port from .env (or default 5000)
APP_PORT="${APP_PORT:-5000}"
if [ -f .env ]; then
    ENV_PORT=$(grep "^APP_PORT=" .env | cut -d= -f2)
    [ -n "$ENV_PORT" ] && APP_PORT="$ENV_PORT"
fi

# Start
echo ""
read -r -p "Start Docker containers now? [Y/n]: " START_NOW
START_NOW="${START_NOW:-Y}"
if [[ "$START_NOW" =~ ^[Yy]$ ]]; then
    echo "Starting Nodecast..."
    docker compose up -d
    echo ""
    echo "✓ Nodecast is running at http://localhost:${APP_PORT}"
    echo "  Installed to: $INSTALL_DIR"

    # Auto-open browser
    if command -v xdg-open &>/dev/null; then
        xdg-open "http://localhost:${APP_PORT}" 2>/dev/null || true
    elif command -v open &>/dev/null; then
        open "http://localhost:${APP_PORT}" 2>/dev/null || true
    fi
else
    echo ""
    echo "✓ Nodecast downloaded to: $INSTALL_DIR"
    echo "  Run 'docker compose up -d' in that directory to start."
fi
