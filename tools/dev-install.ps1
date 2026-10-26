<#
.SYNOPSIS
  Developer install: run Radial Menu for ZBrush straight from this checkout (or remove it with -Uninstall).
  End users should use the installer from the GitHub Releases page instead.

.DESCRIPTION
  - Adds this checkout's bridge folder to the USER environment variable ZBRUSH_PLUGIN_PATH, keeping every entry
    already there (other tools put their own folders in the same variable). No admin rights needed.
  - Writes %APPDATA%\RadialMenu\launch.json (by running the app's --check once), which tells the ZBrush
    bridge how to start the app and the Studio from source.
  - Creates a Start menu shortcut "Radial Menu Studio (dev)".
  - Checks that the Python has the runtime dependencies (requirements.txt).
  ZBrush reads ZBRUSH_PLUGIN_PATH only when it starts, so restart ZBrush afterwards.
  Run with -WhatIf to see what would happen.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$Uninstall,
    [string]$Python = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe')
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$BridgeDir = Join-Path $Root 'bridge'
$Main = Join-Path $Root 'radial_menu\main.py'
$Icon = Join-Path $Root 'assets\icon.ico'
$Shortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'Radial Menu Studio (dev).lnk'

$current = [Environment]::GetEnvironmentVariable('ZBRUSH_PLUGIN_PATH', 'User')
$entries = @(if ($current) { $current -split ';' | ForEach-Object { $_.Trim() } | Where-Object { $_ } })
$ours = $entries | Where-Object { $_.TrimEnd('\') -ieq $BridgeDir }
Write-Host "ZBRUSH_PLUGIN_PATH (user) now: $(if ($current) { $current } else { '<not set>' })"

if ($Uninstall) {
    if ($ours -and $PSCmdlet.ShouldProcess('ZBRUSH_PLUGIN_PATH (user)', "remove $BridgeDir")) {
        $new = ($entries | Where-Object { $_.TrimEnd('\') -ine $BridgeDir }) -join ';'
        [Environment]::SetEnvironmentVariable('ZBRUSH_PLUGIN_PATH', $(if ($new) { $new } else { $null }), 'User')
        Write-Host "Removed. ZBRUSH_PLUGIN_PATH (user) is now: $(if ($new) { $new } else { '<not set>' })"
    }
    if ((Test-Path $Shortcut) -and $PSCmdlet.ShouldProcess($Shortcut, 'remove shortcut')) { Remove-Item $Shortcut }
    Write-Host 'Restart ZBrush to unload the bridge.'
    return
}

if (-not (Test-Path $Python)) { throw "Python not found at $Python. Pass -Python <path to python.exe 3.12>." }
& $Python -I -c 'import PIL, webview' 2>$null
if ($LASTEXITCODE -ne 0) { throw "This Python lacks the dependencies. Run: `"$Python`" -m pip install -r `"$Root\requirements.txt`"" }
$Pythonw = Join-Path (Split-Path $Python) 'pythonw.exe'

if (-not $ours -and $PSCmdlet.ShouldProcess('ZBRUSH_PLUGIN_PATH (user)', "append $BridgeDir")) {
    $new = (@($entries) + $BridgeDir) -join ';'
    [Environment]::SetEnvironmentVariable('ZBRUSH_PLUGIN_PATH', $new, 'User')
    Write-Host "Registered. ZBRUSH_PLUGIN_PATH (user) is now: $new"
}
if ($PSCmdlet.ShouldProcess("$env:APPDATA\RadialMenu\launch.json", 'write (via --check)')) {
    & $Python -I $Main --check | Out-Null
    Write-Host "launch.json written for this checkout."
}
if ($PSCmdlet.ShouldProcess($Shortcut, 'create Start menu shortcut')) {
    $lnk = (New-Object -ComObject WScript.Shell).CreateShortcut($Shortcut)
    $lnk.TargetPath = $Pythonw
    $lnk.Arguments = "-I `"$Main`" --studio"
    $lnk.WorkingDirectory = $Root
    $lnk.IconLocation = $Icon
    $lnk.Description = 'Radial Menu Studio (running from source)'
    $lnk.Save()
    Write-Host "Shortcut: $Shortcut"
}
Write-Host "`nRestart ZBrush once. Then press Q over ZBrush. Logs: $env:LOCALAPPDATA\RadialMenu"
