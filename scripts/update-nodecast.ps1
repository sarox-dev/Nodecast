#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"
$StateDir = Join-Path $HOME ".nodecast"
$ConfigPath = Join-Path $StateDir "config"
if (-not (Test-Path $ConfigPath)) { exit 0 }
$cfg = @{}
Get-Content $ConfigPath | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { $cfg[$matches[1]] = $matches[2] } }
$InstallDir = $cfg.INSTALL_DIR; $Mode = $cfg.MODE; $AppPort = if ($cfg.APP_PORT) { $cfg.APP_PORT } else { "5000" }
$Lock = Join-Path $StateDir "update.lock"
try { New-Item -ItemType Directory -Path $Lock -ErrorAction Stop | Out-Null } catch { exit 0 }
try {
    try { $health = Invoke-RestMethod "http://localhost:$AppPort/api/server/health" } catch { exit 0 }
    if (-not $health.can_update) { exit 0 }
    $release = Invoke-RestMethod "https://api.github.com/repos/sarox-dev/Nodecast/releases/latest"
    $latest = $release.tag_name.TrimStart('v')
    if ([version]$latest -le [version]$health.version) { exit 0 }

    $backup = Join-Path $StateDir ("backups\{0}-{1}" -f $health.version, (Get-Date -Format 'yyyyMMddHHmmss'))
    New-Item -ItemType Directory -Force -Path $backup | Out-Null
    Copy-Item (Join-Path $InstallDir ".env") $backup -Force
    Copy-Item (Join-Path $InstallDir "contents") $backup -Recurse -Force

    if ($Mode -eq "docker") {
        Push-Location $InstallDir; try { docker compose down } finally { Pop-Location }
    } else {
        Stop-ScheduledTask -TaskName "Nodecast" -ErrorAction SilentlyContinue
    }
    $temp = Join-Path ([IO.Path]::GetTempPath()) ("nodecast-update-" + [guid]::NewGuid())
    New-Item -ItemType Directory -Path $temp | Out-Null
    $installer = Join-Path $temp "install.ps1"
    $checksums = Join-Path $temp "SHA256SUMS"
    $assetRoot = "https://github.com/sarox-dev/Nodecast/releases/download/v$latest"
    Invoke-WebRequest "$assetRoot/install.ps1" -OutFile $installer
    Invoke-WebRequest "$assetRoot/SHA256SUMS" -OutFile $checksums
    $checksumLine = Get-Content $checksums | Where-Object { $_ -match '^[0-9a-fA-F]{64}\s+\*?install\.ps1$' } | Select-Object -First 1
    if (-not $checksumLine) { throw "Installer checksum is missing or invalid." }
    $expected = ($checksumLine -split '\s+')[0].ToLowerInvariant()
    $actual = (Get-FileHash -Algorithm SHA256 $installer).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { throw "Installer checksum verification failed." }
    $env:NODECAST_INSTALL_DIR = $InstallDir; $env:NODECAST_MODE = $Mode; $env:NODECAST_AUTO_UPDATE = "true"
    & $installer

    $healthy = $false
    1..30 | ForEach-Object {
        if (-not $healthy) {
            Start-Sleep -Seconds 2
            try { Invoke-RestMethod "http://localhost:$AppPort/api/version" | Out-Null; $healthy = $true } catch {}
        }
    }
    if (-not $healthy) { throw "Update completed but health check failed. Backup: $backup" }
} finally {
    if ($temp) { Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue }
    Remove-Item $Lock -Recurse -Force -ErrorAction SilentlyContinue
}
