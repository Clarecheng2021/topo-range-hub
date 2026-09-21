$ErrorActionPreference = "Stop"
$scenarioRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $scenarioRoot
docker compose down
