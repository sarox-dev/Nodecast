#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"
$InstallDir = if ($env:NODECAST_INSTALL_DIR) { $env:NODECAST_INSTALL_DIR } else { (Get-Location).Path }
$Mode = if ($env:NODECAST_MODE) { $env:NODECAST_MODE } else { "docker" }
$AppPort = if ($env:NODECAST_APP_PORT) { $env:NODECAST_APP_PORT } else { "5000" }
$StateDir = Join-Path $HOME ".nodecast"
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
@("INSTALL_DIR=$InstallDir", "MODE=$Mode", "APP_PORT=$AppPort") | Set-Content (Join-Path $StateDir "config") -Encoding utf8
Copy-Item (Join-Path $InstallDir "scripts\update-nodecast.ps1") (Join-Path $StateDir "update.ps1") -Force

$pwsh = (Get-Command pwsh).Source
$action = New-ScheduledTaskAction -Execute $pwsh -Argument "-NoProfile -File `"$(Join-Path $StateDir 'update.ps1')`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Minutes 30)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "NodecastUpdate" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "Automatic updates enabled (checks every 30 minutes)."
