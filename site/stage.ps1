# Builds the publish folder for GitHub Pages and for site/preview.ps1.
# Usage:  pwsh site/stage.ps1 -Out <dir>
param(
    [Parameter(Mandatory = $true)]
    [string]$Out
)

$ErrorActionPreference = 'Stop'
$Site = $PSScriptRoot
$Root = Split-Path -Parent $Site
$OutFull = if ([System.IO.Path]::IsPathRooted($Out)) { $Out } else { Join-Path (Get-Location) $Out }

if (Test-Path $OutFull) { Remove-Item -Recurse -Force $OutFull }
New-Item -ItemType Directory -Path $OutFull | Out-Null

$pages = @('index.html', 'styles.css', 'ring.js', 'site.js')
foreach ($f in $pages) {
    $src = Join-Path $Site $f
    if (-not (Test-Path $src)) { throw "Missing page file: $src" }
    Copy-Item $src (Join-Path $OutFull $f)
}

$imagesSrc = Join-Path $Root 'docs\images'
$imagesDst = Join-Path $OutFull 'images'
New-Item -ItemType Directory -Path $imagesDst | Out-Null
Copy-Item (Join-Path $imagesSrc '*') $imagesDst

$personasDst = Join-Path $OutFull 'personas'
New-Item -ItemType Directory -Path $personasDst | Out-Null
Copy-Item (Join-Path $Site 'personas\*.jpg') $personasDst

$iconsDst = Join-Path $OutFull 'brush-icons'
New-Item -ItemType Directory -Path $iconsDst | Out-Null
Copy-Item (Join-Path $Site 'brush-icons\*.png') $iconsDst

$icon = Join-Path $Root 'assets\icon-256.png'
if (-not (Test-Path $icon)) { throw "Missing favicon source: $icon" }
Copy-Item $icon (Join-Path $OutFull 'favicon.png')

Write-Host "Staged -> $OutFull"
