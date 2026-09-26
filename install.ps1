#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"
$Repo = "sarox-dev/Nodecast"

function Step($Text) { Write-Host "● " -ForegroundColor Cyan -NoNewline; Write-Host $Text }
function Done($Text) { Write-Host "✓ " -ForegroundColor Green -NoNewline; Write-Host $Text }
function Ask($Prompt, $Default) { $v = Read-Host $Prompt; if ([string]::IsNullOrWhiteSpace($v)) { $Default } else { $v } }

Write-Host ""
Write-Host "╭────────────────────────────────────────────╮" -ForegroundColor Cyan
Write-Host "│              NODECAST SETUP                │" -ForegroundColor Cyan
Write-Host "╰────────────────────────────────────────────╯" -ForegroundColor Cyan
Write-Host "Local-first memory for you and your agents." -ForegroundColor DarkGray
Write-Host ""

$Mode = $env:NODECAST_MODE
if (-not $Mode) {
    Write-Host "  1  Docker  " -ForegroundColor Cyan -NoNewline; Write-Host "isolated, easiest to maintain" -ForegroundColor DarkGray
    Write-Host "  2  Host    " -ForegroundColor Cyan -NoNewline; Write-Host "native Python service, lighter runtime" -ForegroundColor DarkGray
    $choice = Ask "Install method [1]" "1"
    $Mode = if ($choice -eq "2") { "host" } else { "docker" }
}

$AutoUpdate = $env:NODECAST_AUTO_UPDATE
if (-not $AutoUpdate) {
    $answer = Ask "Enable automatic updates? [Y/n]" "Y"
    $AutoUpdate = if ($answer -match '^[Nn]$') { "false" } else { "true" }
}
$DefaultDir = Join-Path $HOME "Nodecast"
$InstallDir = $env:NODECAST_INSTALL_DIR
if (-not $InstallDir) { $InstallDir = Ask "Install directory [$DefaultDir]" $DefaultDir }

if ($Mode -eq "docker") {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker is required for Docker mode." }
    docker compose version | Out-Null
} else {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Python 3.11 or newer is required for Host mode." }
    python -c "import sys; raise SystemExit(sys.version_info < (3,11))"
    if ($LASTEXITCODE -ne 0) { throw "Python 3.11 or newer is required." }
}

Step "Downloading the latest GitHub release"
$release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest"
$tag = $release.tag_name
$temp = Join-Path ([IO.Path]::GetTempPath()) ("nodecast-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $temp | Out-Null
try {
    $zip = Join-Path $temp "release.zip"
    Invoke-WebRequest -Uri "https://github.com/$Repo/archive/refs/tags/$tag.zip" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath (Join-Path $temp "extract") -Force
    $source = Get-ChildItem (Join-Path $temp "extract") -Directory | Select-Object -First 1
    if (-not (Test-Path (Join-Path $source.FullName "app\version.json"))) { throw "Downloaded release is incomplete." }
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Get-ChildItem $source.FullName -Force | Where-Object { $_.Name -notin @('.env','contents','.venv','.git') } | ForEach-Object {
        $destination = Join-Path $InstallDir $_.Name
        if (Test-Path $destination) { Remove-Item $destination -Recurse -Force }
        Copy-Item $_.FullName -Destination $InstallDir -Recurse -Force
    }
} finally { Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue }

$EnvFile = Join-Path $InstallDir ".env"
if (-not (Test-Path $EnvFile)) { Copy-Item (Join-Path $InstallDir ".env.example") $EnvFile }
$lines = @(Get-Content $EnvFile | Where-Object { $_ -notmatch '^AUTO_UPDATE_DEFAULT=' })
$lines += "AUTO_UPDATE_DEFAULT=$AutoUpdate"
$lines | Set-Content $EnvFile -Encoding utf8
$portLine = Get-Content $EnvFile | Select-String '^APP_PORT=' | Select-Object -Last 1
$AppPort = if ($portLine) { ($portLine.Line -split '=',2)[1] } else { "5000" }
New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "contents") | Out-Null

if ($Mode -eq "docker") {
    Step "Building the Docker installation"
    Push-Location $InstallDir; try { docker compose up -d --build } finally { Pop-Location }
} else {
    Step "Creating the native Python environment"
    python -m venv (Join-Path $InstallDir ".venv")
    & (Join-Path $InstallDir ".venv\Scripts\python.exe") -m pip install --disable-pip-version-check -q -r (Join-Path $InstallDir "requirements.txt")
    $python = Join-Path $InstallDir ".venv\Scripts\python.exe"
    $args = "-m uvicorn app.main:app --host 127.0.0.1 --port $AppPort"
    $action = New-ScheduledTaskAction -Execute $python -Argument $args -WorkingDirectory $InstallDir
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName "Nodecast" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName "Nodecast"
}

Step "Installing the host-side update service"
$env:NODECAST_INSTALL_DIR = $InstallDir; $env:NODECAST_MODE = $Mode; $env:NODECAST_APP_PORT = $AppPort
& (Join-Path $InstallDir "scripts\install-updater.ps1")
if ($AutoUpdate -ne "true") { Write-Host "  Update checks are installed but remain inactive until the admin enables them in Settings." -ForegroundColor DarkGray }

Write-Host ""
Write-Host "╭────────────────────────────────────────────╮" -ForegroundColor Green
Write-Host "│  Nodecast $tag is ready" -ForegroundColor Green
Write-Host "╰────────────────────────────────────────────╯" -ForegroundColor Green
Write-Host "  Mode:      $Mode"
Write-Host "  Address:   http://localhost:$AppPort"
Write-Host "  Directory: $InstallDir"
