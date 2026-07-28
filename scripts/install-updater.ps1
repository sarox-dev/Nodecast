#!/usr/bin/env pwsh
$NodecastDir = Join-Path $HOME ".nodecast"
New-Item -ItemType Directory -Force -Path $NodecastDir | Out-Null

# Detect install directory
if (Test-Path ".env") {
    $InstallDir = (Get-Location).Path
} elseif (Test-Path (Join-Path $HOME "Nodecast" ".env")) {
    $InstallDir = Join-Path $HOME "Nodecast"
} else {
    $InstallDir = Read-Host "Enter Nodecast install directory"
}

$EnvFile = Join-Path $InstallDir ".env"
$AppPort = "5000"
if (Test-Path $EnvFile) {
    $portLine = Get-Content $EnvFile | Select-String "^APP_PORT="
    if ($portLine) { $AppPort = $portLine.Line.Split("=")[1] }
}

# Save config
@"
INSTALL_DIR=$InstallDir
APP_PORT=$AppPort
"@ | Out-File -FilePath (Join-Path $NodecastDir "config") -Encoding ASCII

# Copy update script
Copy-Item -Path (Join-Path $InstallDir "scripts" "update-nodecast.ps1") -Destination (Join-Path $NodecastDir "update.ps1") -Force

# Install scheduled task
$Action = New-ScheduledTaskAction -Execute "pwsh" -Argument "-File `"$(Join-Path $NodecastDir 'update.ps1')`""
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15)
$Task = New-ScheduledTask -Action $Action -Trigger $Trigger -Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries)
Register-ScheduledTask -TaskName "NodecastAutoUpdate" -InputObject $Task -Force | Out-Null

Write-Host "✓ Auto-updater installed (checks every 15 min)"
Write-Host "  Config: $(Join-Path $NodecastDir 'config')"
Write-Host "  Update script: $(Join-Path $NodecastDir 'update.ps1')"