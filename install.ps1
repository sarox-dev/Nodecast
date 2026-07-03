#!/usr/bin/env pwsh
$Repo = "sarox-dev/Recollect"
$InstallDir = Join-Path $HOME "Recollect"
Write-Host "Installing Recollect..."

# Check Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Docker is required."
    Write-Host "Install from: https://docs.docker.com/get-docker/"
    exit 1
}

# Download latest release
Write-Host "Downloading latest release..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Set-Location $InstallDir
Invoke-WebRequest -Uri "https://github.com/$Repo/archive/refs/tags/v0.0.1.zip" -OutFile "release.zip"
Expand-Archive -Path "release.zip" -DestinationPath "/tmp/recollect-extract" -Force
$extracted = Get-ChildItem "/tmp/recollect-extract/Recollect-*" | Select-Object -First 1
Copy-Item -Path "$($extracted.FullName)\*" -Destination $InstallDir -Recurse -Force
Remove-Item -Path "release.zip" -Force
Remove-Item -Path "/tmp/recollect-extract" -Recurse -Force

# Setup .env from example if missing
if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

# Start
Write-Host "Starting Recollect..."
docker compose up -d
Write-Host ""
Write-Host "✓ Recollect is running at http://localhost:5000"

# Auto-open browser
Start-Process "http://localhost:5000"
