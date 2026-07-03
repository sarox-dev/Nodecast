#!/usr/bin/env pwsh
$Repo = "sarox-dev/Recollect"
Write-Host "Installing Recollect..."

# Check Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Docker is required. Install from https://docs.docker.com/get-docker/"
    exit 1
}

# Clone or pull
if (Test-Path "Recollect") {
    Write-Host "Updating existing installation..."
    cd Recollect
    git pull
} else {
    Write-Host "Cloning repository..."
    git clone https://github.com/$Repo.git
    cd Recollect
}

# Start
Write-Host "Starting Recollect..."
docker compose up -d
Write-Host "Recollect is running at http://localhost:5000"
