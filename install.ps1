#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"
$Repo = "sarox-dev/Nodecast"
$TotalSteps = 8
$script:CurrentStep = 0

function Step([string]$Text) {
    $script:CurrentStep++
    Write-Host ("[{0}/{1}] " -f $script:CurrentStep, $TotalSteps) -ForegroundColor Cyan -NoNewline
    Write-Host $Text
}
function Done([string]$Text) { Write-Host "  + " -ForegroundColor Green -NoNewline; Write-Host $Text }
function Note([string]$Text) { Write-Host "  i " -ForegroundColor Cyan -NoNewline; Write-Host $Text }
function Warn([string]$Text) { Write-Host "  ! " -ForegroundColor Yellow -NoNewline; Write-Host $Text }
function Fail([string]$Text) { throw "Installation stopped: $Text" }
function Ask([string]$Prompt, [string]$Default) {
    $value = Read-Host $Prompt
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value
}
function Has-Command([string]$Name) { return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }
function Get-EnvValue([string]$Path, [string]$Key, [string]$Default = "") {
    if (-not (Test-Path $Path)) { return $Default }
    $match = Get-Content $Path | Select-String ("^{0}=" -f [regex]::Escape($Key)) | Select-Object -Last 1
    if (-not $match) { return $Default }
    return ($match.Line -split '=', 2)[1].Trim()
}

function Show-Title {
    $width = 80
    try { $width = $Host.UI.RawUI.WindowSize.Width } catch {}
    Write-Host ""
    if ($width -ge 76) {
        Write-Host "  _   _           _                     _   " -ForegroundColor Blue
        Write-Host " | \ | | ___   __| | ___  ___ __ _ ___| |_ " -ForegroundColor Blue
        Write-Host " |  \| |/ _ \ / _`` |/ _ \/ __/ _`` / __| __|" -ForegroundColor Cyan
        Write-Host " | |\  | (_) | (_| |  __/ (_| (_| \__ \ |_ " -ForegroundColor Cyan
        Write-Host " |_| \_|\___/ \__,_|\___|\___\__,_|___/\__|" -ForegroundColor Cyan
    } elseif ($width -ge 50) {
        Write-Host "+--------------------------------------------+" -ForegroundColor Cyan
        Write-Host "|              NODECAST SETUP                |" -ForegroundColor Cyan
        Write-Host "+--------------------------------------------+" -ForegroundColor Cyan
    } else {
        Write-Host "NODECAST SETUP" -ForegroundColor Cyan
    }
    Write-Host "Your knowledge layer. Your context. Your memory." -ForegroundColor DarkGray
    Write-Host ""
}

function Test-SafeInstallTarget([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $homeFull = [IO.Path]::GetFullPath($HOME)
    $root = [IO.Path]::GetPathRoot($full)
    if ($full -eq $homeFull -or $full -eq $root) { return $false }
    if (Test-Path $full) {
        $first = Get-ChildItem -LiteralPath $full -Force -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($first -and -not (Test-Path (Join-Path $full "app\version.json")) -and -not (Test-Path (Join-Path $full ".nodecast-install"))) {
            return $false
        }
    }
    return $true
}

function Test-SafeArchive([string]$Archive) {
    $entries = & tar -tzf $Archive
    if ($LASTEXITCODE -ne 0) { return $false }
    foreach ($entry in $entries) {
        if ($entry -match '^[\\/]' -or $entry -match '^[A-Za-z]:' -or $entry -match '(^|[\\/])\.\.([\\/]|$)') { return $false }
    }
    return $true
}

function Wait-Nodecast([int]$Port) {
    foreach ($attempt in 1..30) {
        try {
            Invoke-RestMethod "http://127.0.0.1:$Port/api/server/health" -TimeoutSec 2 | Out-Null
            return $true
        } catch { Start-Sleep -Seconds 1 }
    }
    return $false
}

function Protect-UserPath([string]$Path, [bool]$Directory) {
    if (-not (Has-Command "icacls") -or -not (Test-Path $Path)) { return }
    try {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $grant = if ($Directory) { "${identity}:(OI)(CI)F" } else { "${identity}:F" }
        & icacls $Path /inheritance:r /grant:r $grant | Out-Null
    } catch {
        Warn "Could not tighten permissions on $Path."
    }
}

Show-Title
Step "Checking this system"
if (-not (Has-Command "tar")) { Fail "tar is required to extract the verified release." }
if ($PSVersionTable.PSVersion.Major -lt 5) { Fail "PowerShell 5.1 or newer is required." }
Done ("Windows + PowerShell {0}" -f $PSVersionTable.PSVersion)

Step "Choosing an installation mode"
$Mode = $env:NODECAST_MODE
if (-not $Mode) {
    Write-Host ""
    Write-Host "  1  Docker - Recommended" -ForegroundColor Cyan
    Write-Host "     Most reliable, isolated, and fully supported." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  2  Native Python - Best effort" -ForegroundColor Cyan
    Write-Host "     No Docker required; compatibility depends on this system." -ForegroundColor DarkGray
    Write-Host ""
    $choice = Ask "Select installation mode [1]" "1"
    $Mode = if ($choice -eq "2") { "host" } else { "docker" }
}
if ($Mode -notin @("docker", "host")) { Fail "NODECAST_MODE must be 'docker' or 'host'." }

$PythonCommand = $null
if ($Mode -eq "docker") {
    if (-not (Has-Command "docker")) { Fail "Docker Desktop is required for Docker mode." }
    docker compose version | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "Docker Compose v2 is required." }
    docker info | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "Docker Desktop is installed, but its engine is not running." }
    Done "Docker Desktop and Compose are ready"
} else {
    if (Has-Command "python") { $PythonCommand = "python" }
    elseif (Has-Command "py") { $PythonCommand = "py" }
    else { Fail "Python 3.11 or newer is required for Native mode." }
    & $PythonCommand -c "import sys; raise SystemExit(sys.version_info < (3,11))"
    if ($LASTEXITCODE -ne 0) { Fail "Python 3.11 or newer is required." }
    & $PythonCommand -m venv --help | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "Python's venv module is required." }
    Warn "Native mode is best effort and depends on local Python and Windows services."
    Done ((& $PythonCommand --version) -join "")
}

$AutoUpdate = $env:NODECAST_AUTO_UPDATE
if (-not $AutoUpdate) {
    $answer = Ask "Enable automatic update checks? [Y/n]" "Y"
    $AutoUpdate = if ($answer -match '^[Nn]$') { "false" } else { "true" }
}
if ($AutoUpdate -notin @("true", "false")) { Fail "NODECAST_AUTO_UPDATE must be 'true' or 'false'." }
$DefaultDir = Join-Path $HOME "Nodecast"
$InstallDir = $env:NODECAST_INSTALL_DIR
if (-not $InstallDir) { $InstallDir = Ask "Install directory [$DefaultDir]" $DefaultDir }
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
if (-not (Test-SafeInstallTarget $InstallDir)) { Fail "The directory is unsafe or contains files that do not belong to Nodecast: $InstallDir" }
$PreviousMode = ""
$markerPath = Join-Path $InstallDir ".nodecast-install"
if (Test-Path $markerPath) {
    $markerMode = Get-Content $markerPath | Select-String '^mode=' | Select-Object -First 1
    if ($markerMode) { $PreviousMode = ($markerMode.Line -split '=', 2)[1].Trim() }
}
Done "Mode: $Mode | Directory: $InstallDir"

Step "Choosing accounts and network access"
$ExistingEnv = Join-Path $InstallDir ".env"
$AccountMode = $env:NODECAST_ACCOUNT_MODE
if (-not $AccountMode) {
    Write-Host ""
    Write-Host "  1  Personal" -ForegroundColor Cyan -NoNewline; Write-Host "  one Library member plus the owner control account" -ForegroundColor DarkGray
    Write-Host "  2  Shared" -ForegroundColor Cyan -NoNewline; Write-Host "    multiple independent member Libraries" -ForegroundColor DarkGray
    Write-Host ""
    $savedAccountMode = Get-EnvValue $ExistingEnv "NODECAST_ACCOUNT_MODE"
    $accountDefault = if ($savedAccountMode -eq "shared" -or (-not $savedAccountMode -and (Test-Path (Join-Path $InstallDir "app\version.json")))) { "2" } else { "1" }
    $accountChoice = Ask "Account setup [$accountDefault]" $accountDefault
    $AccountMode = if ($accountChoice -eq "2") { "shared" } else { "personal" }
}
if ($AccountMode -notin @("personal", "shared")) { Fail "NODECAST_ACCOUNT_MODE must be 'personal' or 'shared'." }

$NetworkAccess = $env:NODECAST_NETWORK_ACCESS
if (-not $NetworkAccess) {
    Write-Host ""
    Write-Host "  1  This device only" -ForegroundColor Cyan -NoNewline; Write-Host "  127.0.0.1; safest default" -ForegroundColor DarkGray
    Write-Host "  2  Trusted LAN" -ForegroundColor Cyan -NoNewline; Write-Host "       available to devices on your local network" -ForegroundColor DarkGray
    Write-Host ""
    $networkDefault = if ((Get-EnvValue $ExistingEnv "NODECAST_BIND_HOST") -eq "0.0.0.0") { "2" } else { "1" }
    $networkChoice = Ask "Network access [$networkDefault]" $networkDefault
    $NetworkAccess = if ($networkChoice -eq "2") { "lan" } else { "local" }
}
if ($NetworkAccess -notin @("local", "lan")) { Fail "NODECAST_NETWORK_ACCESS must be 'local' or 'lan'." }
$LanHost = $env:NODECAST_LAN_HOST
if ($NetworkAccess -eq "lan") {
    if (-not $LanHost) {
        $currentOrigin = Get-EnvValue $ExistingEnv "NODECAST_PUBLIC_ORIGIN"
        $currentHost = $currentOrigin -replace '^https?://', '' -replace ':\d+$', ''
        if ($currentHost -eq "localhost") { $currentHost = "" }
        $prompt = if ($currentHost) { "LAN IP address or hostname [$currentHost]" } else { "LAN IP address or hostname" }
        $LanHost = Ask $prompt $currentHost
    }
    if ($LanHost -notmatch '^[A-Za-z0-9.-]+$') { Fail "Enter a valid LAN IPv4 address or hostname without http:// or a port." }
    Warn "LAN mode trusts your local network. Do not expose this port directly to the internet."
}
Done "Accounts: $AccountMode | Network: $NetworkAccess"

Step "Downloading the latest verified release"
$headers = @{ Accept = "application/vnd.github+json"; "User-Agent" = "Nodecast-Installer" }
$release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers $headers
$tag = [string]$release.tag_name
if ($tag -notmatch '^v[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$') { Fail "GitHub returned an invalid release tag." }
$temp = Join-Path ([IO.Path]::GetTempPath()) ("nodecast-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $temp | Out-Null
try {
    $archiveName = "nodecast-$tag.tar.gz"
    $archive = Join-Path $temp $archiveName
    $checksums = Join-Path $temp "SHA256SUMS"
    $assetRoot = "https://github.com/$Repo/releases/download/$tag"
    Invoke-WebRequest -Uri "$assetRoot/$archiveName" -OutFile $archive -Headers $headers
    Invoke-WebRequest -Uri "$assetRoot/SHA256SUMS" -OutFile $checksums -Headers $headers
    $checksumLine = Get-Content $checksums | Where-Object { $_ -match "^[0-9a-fA-F]{64}\s+\*?$([regex]::Escape($archiveName))$" } | Select-Object -First 1
    if (-not $checksumLine) { Fail "The release checksum is missing or invalid." }
    $expected = ($checksumLine -split '\s+')[0].ToLowerInvariant()
    $actual = (Get-FileHash -Algorithm SHA256 $archive).Hash.ToLowerInvariant()
    if ($actual -ne $expected) { Fail "Release checksum verification failed." }
    if (-not (Test-SafeArchive $archive)) { Fail "The release archive contains an unsafe path." }
    Done "Nodecast $tag checksum verified"

    Step "Preparing application files"
    $extract = Join-Path $temp "extract"
    New-Item -ItemType Directory -Path $extract | Out-Null
    & tar -xzf $archive -C $extract
    if ($LASTEXITCODE -ne 0) { Fail "Could not extract the verified release." }
    $source = Get-ChildItem $extract -Directory | Select-Object -First 1
    if (-not $source -or -not (Test-Path (Join-Path $source.FullName "app\version.json")) -or -not (Test-Path (Join-Path $source.FullName "scripts\run-nodecast.py"))) {
        Fail "Downloaded release is incomplete."
    }
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Get-ChildItem $source.FullName -Force | Where-Object { $_.Name -notin @('.env','contents','.venv','.git','.nodecast-install') } | ForEach-Object {
        $destination = Join-Path $InstallDir $_.Name
        if (Test-Path $destination) { Remove-Item $destination -Recurse -Force }
        Copy-Item $_.FullName -Destination $InstallDir -Recurse -Force
    }
} finally {
    Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Force -Path (Join-Path $InstallDir "contents") | Out-Null
Set-Content (Join-Path $InstallDir ".nodecast-install") "mode=$Mode" -Encoding utf8
$EnvFile = Join-Path $InstallDir ".env"
if (-not (Test-Path $EnvFile)) { Copy-Item (Join-Path $InstallDir ".env.example") $EnvFile }
$lines = @(Get-Content $EnvFile | Where-Object { $_ -notmatch '^(AUTO_UPDATE_DEFAULT|NODECAST_ACCOUNT_MODE|NODECAST_BIND_HOST|NODECAST_PUBLIC_ORIGIN)=' })
$lines += "AUTO_UPDATE_DEFAULT=$AutoUpdate"
$lines += "NODECAST_ACCOUNT_MODE=$AccountMode"
$bindLine = if ($NetworkAccess -eq "lan") { "NODECAST_BIND_HOST=0.0.0.0" } else { "NODECAST_BIND_HOST=127.0.0.1" }
$lines += $bindLine
$lines | Set-Content $EnvFile -Encoding utf8
Protect-UserPath (Join-Path $InstallDir "contents") $true
Protect-UserPath $EnvFile $false
$portLine = Get-Content $EnvFile | Select-String '^APP_PORT=' | Select-Object -Last 1
$AppPortText = if ($portLine) { ($portLine.Line -split '=',2)[1].Trim() } else { "5000" }
$AppPort = 0
if (-not ([int]::TryParse($AppPortText, [ref]$AppPort)) -or $AppPort -lt 1 -or $AppPort -gt 65535) { Fail "APP_PORT in .env must be between 1 and 65535." }
$originHost = if ($NetworkAccess -eq "lan") { $LanHost } else { "localhost" }
Add-Content $EnvFile "NODECAST_PUBLIC_ORIGIN=http://${originHost}:$AppPort" -Encoding utf8
Done "Configuration and persistent data directory are ready"

Step "Installing Nodecast"
if ($Mode -eq "docker") {
    if ($PreviousMode -eq "host") {
        Stop-ScheduledTask -TaskName "Nodecast" -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName "Nodecast" -Confirm:$false -ErrorAction SilentlyContinue
    }
    Push-Location $InstallDir
    try { docker compose up -d --build; if ($LASTEXITCODE -ne 0) { Fail "Docker Compose could not start Nodecast." } }
    finally { Pop-Location }
    Done "Docker service started"
} else {
    if ($PreviousMode -eq "docker" -and (Has-Command "docker") -and (Test-Path (Join-Path $InstallDir "docker-compose.yml"))) {
        Push-Location $InstallDir
        try { docker compose down | Out-Null } finally { Pop-Location }
    }
    & $PythonCommand -m venv (Join-Path $InstallDir ".venv")
    if ($LASTEXITCODE -ne 0) { Fail "Could not create the Python virtual environment." }
    $venvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"
    & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $InstallDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Fail "Python dependencies could not be installed." }
    $runner = Join-Path $InstallDir "scripts\run-nodecast.py"
    $action = New-ScheduledTaskAction -Execute $venvPython -Argument ('"{0}"' -f $runner) -WorkingDirectory $InstallDir
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Stop-ScheduledTask -TaskName "Nodecast" -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName "Nodecast" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName "Nodecast"
    Done "Native Python task started"
}

Step "Verifying the running application"
if (-not (Wait-Nodecast $AppPort)) {
    if ($Mode -eq "docker") { Note "Run: docker compose --project-directory `"$InstallDir`" logs app" }
    else { Note "Open Task Scheduler and inspect the Nodecast task history." }
    Fail "Nodecast did not become healthy on port $AppPort."
}
Done "Health check passed on http://127.0.0.1:$AppPort"

Step "Configuring update checks"
$env:NODECAST_INSTALL_DIR = $InstallDir
$env:NODECAST_MODE = $Mode
$env:NODECAST_APP_PORT = [string]$AppPort
& (Join-Path $InstallDir "scripts\install-updater.ps1")
if ($AutoUpdate -eq "true") { Done "Automatic update checks are enabled" }
else { Note "The updater is installed but remains inactive until enabled by the owner." }

Write-Host ""
Write-Host "Nodecast $tag is ready." -ForegroundColor Green
Write-Host "--------------------------------------------" -ForegroundColor DarkGray
Write-Host "  Mode       $Mode"
Write-Host "  Accounts   $AccountMode"
Write-Host "  Access     $NetworkAccess"
Write-Host "  Address    " -NoNewline; Write-Host "http://localhost:$AppPort" -ForegroundColor Cyan
Write-Host "  Directory  $InstallDir"
Write-Host ""
