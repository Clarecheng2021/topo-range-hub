$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $MyInvocation.MyCommand.Path)
docker compose up -d --build
docker compose ps
Write-Host "HMI: http://127.0.0.1:18082"