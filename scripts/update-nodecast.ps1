#!/usr/bin/env pwsh
$ConfigPath = Join-Path $HOME ".nodecast" "config"
if (-not (Test-Path $ConfigPath)) {
    Write-Host "Nodecast not configured. Run install-updater.ps1 first."
    exit 1
}

$Config = Get-Content $ConfigPath | ForEach-Object {
    $parts = $_ -split "=", 2
    if ($parts.Count -eq 2) { @{ $parts[0] = $parts[1] } }
}
$InstallDir = $Config.INSTALL_DIR
$AppPort = if ($Config.APP_PORT) { $Config.APP_PORT } else { "5000" }

try {
    $Health = Invoke-RestMethod -Uri "http://localhost:$AppPort/api/server/health" -ErrorAction Stop
} catch {
    exit 0
}

if (-not $Health.can_update) {
    exit 0
}

Set-Location $InstallDir
try {
    git pull origin main 2>&1 | Out-Null
} catch {
    exit 0
}

docker compose down 2>&1 | Out-Null
docker compose up -d --build 2>&1 | Out-Null