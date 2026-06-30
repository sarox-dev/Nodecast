param([string]$action)

$dir = "$env:USERPROFILE\.recollect"
Set-Location $dir

switch ($action) {
    "start" { docker compose up -d }
    "stop" { docker compose down }
    "restart" { docker compose restart }
    "update" {
        git pull
        docker compose up -d --build
    }
    default {
        Write-Host "Recollect CLI"
        Write-Host "recollect start | stop | restart | update"
    }
}