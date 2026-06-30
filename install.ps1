$repo = "https://github.com/sarox-dev/Recollect.git"
$dir = Get-Location

Write-Host "======================================"
Write-Host " Recollect installer (current dir)"
Write-Host "======================================"
Write-Host ""
Write-Host "Target directory: $dir"
Write-Host ""

# checks
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker not installed"
    exit 1
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Git not installed"
    exit 1
}

# install/update logic
if (Test-Path ".git") {
    Write-Host "Repo already exists. Updating..."
    git pull
} else {
    Write-Host "Cloning into current directory..."
    git clone $repo .
}

Write-Host ""
Write-Host "Setting up env..."

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env" -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Starting Recollect..."

docker compose up -d

# read port (best-effort)
$port = 5000
if (Test-Path ".env") {
    $envFile = Get-Content ".env"
    foreach ($line in $envFile) {
        if ($line -match "APP_PORT=(\d+)") {
            $port = $matches[1]
        }
    }
}

Write-Host ""
Write-Host "======================================"
Write-Host "✓ Recollect running"
Write-Host "→ http://localhost:$port"
Write-Host "======================================"