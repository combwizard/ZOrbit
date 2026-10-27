<#
.SYNOPSIS
  Compiles bridge\zscript\ZOrbitBridge.txt to ZOrbitBridge.zsc with ZBrush 2022, without clicking through ZBrush.

.DESCRIPTION
  ZBrush compiles a ZScript .txt passed on its command line and writes the .zsc next to it, so this copies the
  source to a temporary folder, starts ZBrush with it, waits for the .zsc, closes ZBrush and puts the result in
  bridge\zscript. The committed .zsc is only replaced once a new one exists.

  Only one ZBrush can run at a time (any version), so close ZBrush before running this.
  If no .zsc appears (a syntax error in the script), ZBrush is left open so its error message can be read.
  Two header bytes differ from one compile to the next; the rest matches a compile through ZScript > Load.

.PARAMETER ZBrush
  The ZBrush folder (or ZBrush.exe) to compile with. Default: the installed ZBrush of -Year, found the way
  the app finds installations (zorbit\installs.py).

.PARAMETER Year
  Which installed ZBrush to use when -ZBrush is not given. Default 2022, the oldest supported version, so the
  plugin stays loadable in the newer ones.

.PARAMETER TimeoutSec
  How long to wait for the .zsc after starting ZBrush.
#>
[CmdletBinding()]
param(
    [string]$ZBrush,
    [int]$Year = 2022,
    [int]$TimeoutSec = 120
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Source = Join-Path $Root 'bridge\zscript\ZOrbitBridge.txt'
$Target = Join-Path $Root 'bridge\zscript\ZOrbitBridge.zsc'

# --- ZBrush.exe ---------------------------------------------------------------------------------------------
if (-not $ZBrush) {
    $py = @(
        (Join-Path $Root '.venv\Scripts\python.exe'),
        (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1)
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $py) { throw 'Python not found to look up ZBrush installations; pass -ZBrush <folder>.' }
    Push-Location $Root
    try {
        $ZBrush = & $py -c "from zorbit import installs; print(next((i['path'] for i in installs.find_installs() if i['year'] == $Year), ''))"
    } finally { Pop-Location }
    if (-not $ZBrush) { throw "ZBrush $Year is not installed; pass -ZBrush <folder>." }
}
$Exe = if ($ZBrush -like '*.exe') { $ZBrush } else { Join-Path $ZBrush 'ZBrush.exe' }
if (-not (Test-Path $Exe)) { throw "ZBrush.exe not found at $Exe" }
$Exe = (Resolve-Path $Exe).Path

# Only one ZBrush runs at a time, whatever the version: a second one quits straight away.
$running = Get-Process ZBrush -ErrorAction SilentlyContinue | Select-Object -First 1
if ($running) { throw "ZBrush is running ($($running.Path)). Close it first: only one ZBrush can run at a time." }

# --- compile ------------------------------------------------------------------------------------------------
$Work = Join-Path ([IO.Path]::GetTempPath()) ("zorbit-zsc-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Work | Out-Null
$WorkTxt = Join-Path $Work 'ZOrbitBridge.txt'
$WorkZsc = Join-Path $Work 'ZOrbitBridge.zsc'
Copy-Item $Source $WorkTxt

Write-Host "Compiling with $Exe ..."
$proc = Start-Process $Exe -ArgumentList "`"$WorkTxt`"" -WorkingDirectory (Split-Path $Exe) -PassThru
$watch = [Diagnostics.Stopwatch]::StartNew()
$size = -1
while ($watch.Elapsed.TotalSeconds -lt $TimeoutSec -and -not $proc.HasExited) {
    Start-Sleep -Milliseconds 500
    if (Test-Path $WorkZsc) {
        # Done once the file has stopped growing.
        $now = (Get-Item $WorkZsc).Length
        if ($now -gt 0 -and $now -eq $size) { break }
        $size = $now
    }
}

if (-not (Test-Path $WorkZsc) -or (Get-Item $WorkZsc).Length -eq 0) {
    if ($proc.HasExited) {
        Remove-Item $Work -Recurse -Force
        throw 'ZBrush quit without writing a .zsc.'
    }
    throw "No .zsc after $TimeoutSec s. ZBrush is left open: a script error shows there. Work folder: $Work"
}

if (-not $proc.CloseMainWindow() -or -not $proc.WaitForExit(15000)) {
    Write-Warning 'ZBrush did not close by itself; ending it.'
    $proc.Kill()
}

Copy-Item $WorkZsc $Target -Force
Remove-Item $Work -Recurse -Force
Write-Host ("Wrote {0} ({1:N0} bytes) in {2:N0} s" -f $Target, (Get-Item $Target).Length, $watch.Elapsed.TotalSeconds)
