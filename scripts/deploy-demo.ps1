param(
    [string]$Topology = "examples/factory-demo.clab.yml"
)

$ErrorActionPreference = "Stop"
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$topologyPath = (Resolve-Path (Join-Path $workspaceRoot $Topology)).Path

if (-not $topologyPath.StartsWith($workspaceRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Topology must be inside the demo workspace."
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is not installed or not available in PATH."
}

if (-not (Get-Command containerlab -ErrorAction SilentlyContinue)) {
    throw "Containerlab is not installed or not available in PATH."
}

Write-Host "Deploying isolated factory demo: $topologyPath"
containerlab deploy --topo $topologyPath
containerlab inspect --topo $topologyPath
