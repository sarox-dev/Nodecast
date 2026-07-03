#!/usr/bin/env bash
set -e
REPO="sarox-dev/Recollect"
echo "Installing Recollect..."

# Check Docker
if ! command -v docker &>/dev/null; then
    echo "Error: Docker is required. Install from https://docs.docker.com/get-docker/"
    exit 1
fi

# Clone or pull
if [ -d "Recollect" ]; then
    echo "Updating existing installation..."
    cd Recollect
    git pull
else
    echo "Cloning repository..."
    git clone https://github.com/$REPO.git
    cd Recollect
fi

# Start
echo "Starting Recollect..."
docker compose up -d
echo "Recollect is running at http://localhost:5000"
