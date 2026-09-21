$ErrorActionPreference = "Stop"
$scenarioRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $scenarioRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is not installed or not available in PATH."
}

docker compose up -d --build
docker compose ps
Write-Host "HMI: http://127.0.0.1:18080"
