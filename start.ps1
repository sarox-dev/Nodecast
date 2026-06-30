$envFile = ".env"

if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match "^([^#=]+)=(.*)$") {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2])
        }
    }
}

$port = if ($env:APP_PORT) { $env:APP_PORT } else { 5000 }

docker compose up -d

Write-Host ""
Write-Host "✓ Recollect is running"
Write-Host "→ http://localhost:$port"