$repo = "https://github.com/sarox-dev/Recollect.git"
$dir = "$env:USERPROFILE\.recollect"

Write-Host "Checking dependencies..."

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Install Docker first"
    exit 1
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Install Git first"
    exit 1
}

if (Test-Path "$dir\.git") {
    Write-Host "1) Update"
    Write-Host "2) Reinstall"
    $choice = Read-Host "Choose"

    if ($choice -eq "1") {
        git -C $dir pull
    } else {
        Remove-Item -Recurse -Force $dir
        git clone $repo $dir
    }
} else {
    git clone $repo $dir
}

Set-Location $dir

Copy-Item ".env.example" ".env" -ErrorAction SilentlyContinue

docker compose up -d

Write-Host ""
Write-Host "Installed"

Write-Host "To add CLI:"
Write-Host "Add this to PATH or run:"
Write-Host "powershell -File recollect.ps1 start"