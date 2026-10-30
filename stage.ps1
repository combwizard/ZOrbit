# Builds the publish folder for GitHub Pages and for preview.ps1.
# Usage:  pwsh stage.ps1 -Out <dir>
param(
    [Parameter(Mandatory = $true)]
    [string]$Out
)

$ErrorActionPreference = 'Stop'
$Site = $PSScriptRoot
$OutFull = if ([System.IO.Path]::IsPathRooted($Out)) { $Out } else { Join-Path (Get-Location) $Out }

if (Test-Path $OutFull) { Remove-Item -Recurse -Force $OutFull }
New-Item -ItemType Directory -Path $OutFull | Out-Null

$pages = @('index.html', 'styles.css', 'ring.js', 'site.js', 'favicon.png', 'CNAME')
foreach ($f in $pages) {
    $src = Join-Path $Site $f
    if (-not (Test-Path $src)) { throw "Missing page file: $src" }
    Copy-Item $src (Join-Path $OutFull $f)
}

foreach ($dir in @('images', 'personas', 'brush-icons')) {
    Copy-Item -Recurse (Join-Path $Site $dir) (Join-Path $OutFull $dir)
}

Write-Host "Staged -> $OutFull"
