# Stage the site and serve it locally. Ctrl+C stops the server.
# Usage:  powershell -ExecutionPolicy Bypass -File site\preview.ps1 [-Port 8000]
param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$Site = $PSScriptRoot
$Preview = Join-Path $Site '.preview'

# Refuse if the port is already taken.
$taken = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($taken) {
    throw "Port $Port is already in use. Stop the other server, or pass -Port <n>."
}

& (Join-Path $Site 'stage.ps1') -Out $Preview

Write-Host "Serving http://127.0.0.1:$Port/  (Ctrl+C to stop)"
python -m http.server $Port --bind 127.0.0.1 --directory $Preview
