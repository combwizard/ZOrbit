<#
.SYNOPSIS
  Builds ZOrbit: PyInstaller onedir app, portable zip and (if Inno Setup is present) the installer.

.DESCRIPTION
  Creates/uses .venv (Python 3.12), installs requirements-dev.txt, makes assets\icon.ico if missing, runs
  PyInstaller with packaging\zorbit.spec, zips the result and compiles packaging\installer.iss with ISCC.

  Output:
    dist\ZOrbit\ZOrbit.exe
    dist\ZOrbit-<version>-portable.zip
    packaging\Output\ZOrbitSetup-<version>.exe

.PARAMETER SkipInstaller
  Build the app and the portable zip only.
#>
[CmdletBinding()]
param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root

function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Exe failed with exit code $LASTEXITCODE" }
}

# --- version (single source of truth: zorbit\paths.py) ---------------------------------------------------
$m = Select-String -Path (Join-Path $Root 'zorbit\paths.py') -Pattern '^VERSION\s*=\s*"([^"]+)"'
if (-not $m) { throw 'Could not read VERSION from zorbit\paths.py' }
$Version = $m.Matches[0].Groups[1].Value
Write-Host "== ZOrbit $Version ==" -ForegroundColor Cyan

# --- venv -----------------------------------------------------------------------------------------------------
$VenvPy = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPy)) {
    Write-Host 'Creating .venv (Python 3.12)...'
    $created = $false
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv (Join-Path $Root '.venv') 2>$null
        $created = ($LASTEXITCODE -eq 0) -and (Test-Path $VenvPy)
    }
    if (-not $created) {
        $cands = @(
            (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1),
            (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe')
        ) | Where-Object { $_ -and (Test-Path $_) }
        foreach ($c in $cands) {
            $v = & $c -c 'import sys; print("%d.%d" % sys.version_info[:2])'
            if ($v -eq '3.12') { Invoke-Native $c @('-m', 'venv', (Join-Path $Root '.venv')); $created = $true; break }
        }
    }
    if (-not $created -or -not (Test-Path $VenvPy)) { throw 'Python 3.12 not found. Install it and re-run.' }
}
Write-Host 'Installing requirements...'
Invoke-Native $VenvPy @('-m', 'pip', 'install', '--disable-pip-version-check', '-q', '--upgrade', 'pip')
Invoke-Native $VenvPy @('-m', 'pip', 'install', '--disable-pip-version-check', '-q', '-r', (Join-Path $Root 'requirements-dev.txt'))

# --- icon -----------------------------------------------------------------------------------------------------
if (-not (Test-Path (Join-Path $Root 'assets\icon.ico'))) {
    Write-Host 'assets\icon.ico missing; generating...'
    Invoke-Native $VenvPy @((Join-Path $Root 'assets\make_icon.py'))
}

# --- PyInstaller ----------------------------------------------------------------------------------------------
$AppDir = Join-Path $Root 'dist\ZOrbit'
if (Test-Path $AppDir) { Remove-Item $AppDir -Recurse -Force }
Write-Host 'Running PyInstaller...'
Invoke-Native $VenvPy @('-m', 'PyInstaller', (Join-Path $Root 'packaging\zorbit.spec'), '--noconfirm', '--clean',
                        '--distpath', (Join-Path $Root 'dist'), '--workpath', (Join-Path $Root 'build\pyinstaller'))
$Exe = Join-Path $AppDir 'ZOrbit.exe'
if (-not (Test-Path $Exe)) { throw "PyInstaller did not produce $Exe" }

# --- portable zip ---------------------------------------------------------------------------------------------
# Contains ZOrbit\ (the app) and bridge\ (the ZBrush plugin) so a portable user can point ZBRUSH_PLUGIN_PATH at it.
$Stage = Join-Path $Root 'build\portable'
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Path $Stage | Out-Null
Copy-Item $AppDir (Join-Path $Stage 'ZOrbit') -Recurse
New-Item -ItemType Directory -Path (Join-Path $Stage 'bridge') | Out-Null
Copy-Item (Join-Path $Root 'bridge\zorbit_bridge.py') (Join-Path $Stage 'bridge')
Copy-Item (Join-Path $Root 'LICENSE') $Stage
$Zip = Join-Path $Root "dist\ZOrbit-$Version-portable.zip"
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path (Join-Path $Stage '*') -DestinationPath $Zip -CompressionLevel Optimal
Write-Host "Portable zip: $Zip"

$bytes = (Get-ChildItem $AppDir -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ("App folder: {0:N1} MB" -f ($bytes / 1MB))

# --- installer ------------------------------------------------------------------------------------------------
if ($SkipInstaller) {
    Write-Host 'Skipping installer (-SkipInstaller).'
    return
}
$iscc = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1),
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) {
    Write-Warning 'Inno Setup 6 (ISCC.exe) not found; installer not built. Install it (winget install JRSoftware.InnoSetup) or use -SkipInstaller.'
    return
}
Write-Host "Compiling installer with $iscc ..."
Invoke-Native $iscc @("/DAppVersion=$Version", '/Q', (Join-Path $Root 'packaging\installer.iss'))
$Setup = Join-Path $Root "packaging\Output\ZOrbitSetup-$Version.exe"
if (-not (Test-Path $Setup)) { throw "Installer not found at $Setup" }
Write-Host "Installer: $Setup"
