#!/usr/bin/env pwsh
$Repo = "sarox-dev/Nodecast"
$InstallDir = Join-Path $HOME "Nodecast"

Write-Host "Installing Nodecast..."

# Check Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Docker is required."
    Write-Host "Install from: https://docs.docker.com/get-docker/"
    exit 1
}

# Get latest release tag from GitHub
Write-Host "Checking latest version..."
try {
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest"
    $latestTag = $release.tag_name
} catch {
    Write-Host "Error: Could not determine latest version."
    Write-Host "Visit https://github.com/$Repo/releases to install manually."
    exit 1
}
Write-Host "Latest version: $latestTag"

# Download and extract latest release
Write-Host "Downloading $latestTag..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Set-Location $InstallDir
Invoke-WebRequest -Uri "https://github.com/$Repo/archive/refs/tags/$latestTag.zip" -OutFile "release.zip"

Write-Host "Extracting..."
Expand-Archive -Path "release.zip" -DestinationPath "/tmp/nodecast-extract" -Force
$extracted = Get-ChildItem "/tmp/nodecast-extract/Nodecast-*" | Select-Object -First 1
if (-not $extracted) {
    Write-Host "Error: Extraction failed."
    Remove-Item "release.zip" -Force
    exit 1
}
Copy-Item -Path "$($extracted.FullName)\*" -Destination $InstallDir -Recurse -Force
Remove-Item -Path "release.zip" -Force
Remove-Item -Path "/tmp/nodecast-extract" -Recurse -Force

Write-Host "Setting up configuration..."

# If .env doesn't exist, copy from .env.example
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "  Created .env from .env.example"
    }
} else {
    # Merge new variables from .env.example into .env
    if (Test-Path ".env.example") {
        $exampleLines = Get-Content ".env.example"
        $existingKeys = (Get-Content ".env") | ForEach-Object { if ($_ -match "^(\w+)=") { $matches[1] } }
        foreach ($line in $exampleLines) {
            if ($line -match "^(\w+)=") {
                $key = $matches[1]
                if ($key -notin $existingKeys) {
                    Add-Content -Path ".env" -Value $line
                    Write-Host "  Added new config: $key"
                }
            }
        }
    }
}

# Start
Write-Host "Starting Nodecast..."
docker compose up -d
Write-Host ""
Write-Host "✓ Nodecast is running at http://localhost:5000"

# Auto-open browser
Start-Process "http://localhost:5000"
