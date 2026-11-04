<#
  Drives the ZOrbit test VM from the host: checkpoints, commands and files over PowerShell Direct, keys and mouse
  through Hyper-V's virtual keyboard and mouse, and screenshots of the VM's screen. No network to the VM is used.

  Import-Module .\tools\vm\TestVM.psm1
  Restore-TestVM vanilla
  Copy-ToTestVM .\packaging\Output\ZOrbitSetup-1.2.3.exe C:\zorbit-test     # the second path is a folder
  Start-TestVMApp C:\zorbit-test\ZOrbitSetup-1.2.3.exe
  Save-TestVMScreen                      # writes a PNG and returns its path
  Send-TestVMKeys 'Ctrl+Alt+Z'

  Needs: the host account in "Hyper-V Administrators" (no elevation), and the VM made by new-test-vm.ps1, which
  writes the settings file this module reads (%LOCALAPPDATA%\ZOrbit-test-vm\vm.json: name, folder, user, password).
  Keys, mouse and screenshots use the VM's console. If Virtual Machine Connection is open in an enhanced session,
  the console shows the lock screen and input goes nowhere useful; run Connect-TestVMConsole to take it back.
  docs\building.md ("Test on a clean Windows") has the whole routine.
#>
#requires -Version 7

$ErrorActionPreference = 'Stop'
$script:Ns = 'root\virtualization\v2'
$script:ConfigPath = Join-Path $env:LOCALAPPDATA 'ZOrbit-test-vm\vm.json'

function Get-TestVMConfig {
    if (-not (Test-Path $script:ConfigPath)) { throw "No test VM settings at $script:ConfigPath. Run tools\vm\new-test-vm.ps1 first." }
    Get-Content $script:ConfigPath -Raw | ConvertFrom-Json
}

function Get-TestVMCredential {
    $c = Get-TestVMConfig
    New-Object System.Management.Automation.PSCredential($c.User, (ConvertTo-SecureString $c.Password -AsPlainText -Force))
}

function Get-VMSystem {
    $name = (Get-TestVMConfig).Name
    $vm = Get-CimInstance -Namespace $script:Ns -ClassName Msvm_ComputerSystem -Filter "ElementName='$name'"
    if (-not $vm) { throw "Hyper-V has no VM called '$name'." }
    $vm
}

# ---------- checkpoints and power ----------

function Restore-TestVM {
    <# Puts the VM back to a checkpoint and makes sure it is running, then waits until PowerShell Direct answers. #>
    param([Parameter(Mandatory)][string]$Checkpoint, [int]$TimeoutSec = 300)
    $name = (Get-TestVMConfig).Name
    $snap = Get-VMSnapshot -VMName $name -Name $Checkpoint
    Restore-VMSnapshot -VMSnapshot $snap -Confirm:$false
    if ((Get-VM $name).State -ne 'Running') { Start-VM $name }
    Wait-TestVM -TimeoutSec $TimeoutSec
}

function New-TestVMCheckpoint {
    <# Takes a standard checkpoint (memory included when running, so a restore comes back at the desktop). #>
    param([Parameter(Mandatory)][string]$Name)
    $vm = (Get-TestVMConfig).Name
    Get-VMSnapshot -VMName $vm -Name $Name -ErrorAction SilentlyContinue | Remove-VMSnapshot -Confirm:$false
    Checkpoint-VM -Name $vm -SnapshotName $Name
}

function Wait-TestVM {
    <#
      Waits until PowerShell Direct works, the first sign-in has finished its setup commands (windows-ready.txt) and
      someone is on the desktop (explorer.exe runs in a user session; only tester ever signs in).
    #>
    param([int]$TimeoutSec = 300)
    $cred = Get-TestVMCredential
    $name = (Get-TestVMConfig).Name
    $until = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $until) {
        try {
            $ok = Invoke-Command -VMName $name -Credential $cred -ErrorAction Stop -ScriptBlock {
                (Test-Path C:\zorbit-test\windows-ready.txt) -and
                [bool](Get-Process explorer -ErrorAction SilentlyContinue | Where-Object SessionId -gt 0) -and
                -not (Get-Process FirstLogonAnim -ErrorAction SilentlyContinue)   # "This might take a few minutes"
            }
            if ($ok) { return }
        } catch { }
        Start-Sleep -Seconds 3
    }
    throw "The test VM did not reach the desktop within $TimeoutSec seconds."
}

function Connect-TestVMConsole {
    <#
      Moves tester's session back to the VM's own screen. An enhanced session (Virtual Machine Connection's Remote
      Desktop mode) takes the session away from it, and then screenshots show the lock screen and keys go nowhere.
      This closes that window's connection; it can be opened again at any time.
    #>
    Invoke-TestVM {
        $id = (Get-Process explorer -ErrorAction SilentlyContinue | Where-Object SessionId -gt 0 | Select-Object -First 1).SessionId
        if (-not $id) { throw 'Nobody is signed in to the VM.' }
        if ((query user 2>$null) -match '\sconsole\s') { return }
        $a = New-ScheduledTaskAction -Execute 'tscon.exe' -Argument "$id /dest:console"
        Register-ScheduledTask -TaskName ZOrbitTscon -Action $a -User 'SYSTEM' -RunLevel Highest -Force | Out-Null
        Start-ScheduledTask ZOrbitTscon
        Start-Sleep -Seconds 3
        Unregister-ScheduledTask ZOrbitTscon -Confirm:$false
    }
}

# ---------- commands and files ----------

function Invoke-TestVM {
    <# Runs a script block in the VM as tester, in a background session (no desktop: use Start-TestVMApp for windows). #>
    param([Parameter(Mandatory)][scriptblock]$ScriptBlock, [object[]]$ArgumentList = @())
    Invoke-Command -VMName (Get-TestVMConfig).Name -Credential (Get-TestVMCredential) -ScriptBlock $ScriptBlock -ArgumentList $ArgumentList
}

function Copy-ToTestVM {
    param([Parameter(Mandatory)][string[]]$Path, [Parameter(Mandatory)][string]$Destination)
    $s = New-PSSession -VMName (Get-TestVMConfig).Name -Credential (Get-TestVMCredential)
    try {
        Invoke-Command -Session $s -ScriptBlock { param($d) New-Item -ItemType Directory -Force $d | Out-Null } -ArgumentList $Destination
        Copy-Item -Path $Path -Destination $Destination -ToSession $s -Recurse -Force
    } finally { Remove-PSSession $s }
}

function Copy-FromTestVM {
    param([Parameter(Mandatory)][string[]]$Path, [Parameter(Mandatory)][string]$Destination)
    $s = New-PSSession -VMName (Get-TestVMConfig).Name -Credential (Get-TestVMCredential)
    try {
        New-Item -ItemType Directory -Force $Destination | Out-Null
        Copy-Item -Path $Path -Destination $Destination -FromSession $s -Recurse -Force
    } finally { Remove-PSSession $s }
}

function Start-TestVMApp {
    <#
      Starts a program on tester's desktop (PowerShell Direct alone runs it where no one can see it), through a
      scheduled task of its own. Removing a task that is still running ends the program it started, so each start
      gets a new task, and tasks are removed here only once their program has closed.
    #>
    param([Parameter(Mandatory)][string]$FilePath, [string]$ArgumentList = '', [string]$WorkingDirectory = '')
    Invoke-TestVM -ArgumentList $FilePath, $ArgumentList, $WorkingDirectory -ScriptBlock {
        param($file, $arguments, $dir)
        Get-ScheduledTask -TaskName 'ZOrbitTestStart*' -ErrorAction SilentlyContinue | Where-Object State -ne 'Running' |
            Unregister-ScheduledTask -Confirm:$false
        $task = 'ZOrbitTestStart-{0:yyyyMMdd-HHmmss-fff}' -f (Get-Date)
        $action = if ($arguments) { New-ScheduledTaskAction -Execute $file -Argument $arguments } else { New-ScheduledTaskAction -Execute $file }
        if ($dir) { $action.WorkingDirectory = $dir }
        $principal = New-ScheduledTaskPrincipal -UserId "$env:COMPUTERNAME\tester" -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
        Register-ScheduledTask -TaskName $task -Action $action -Principal $principal -Settings $settings | Out-Null
        Start-ScheduledTask -TaskName $task
    }
}

# ---------- screen ----------

function Save-TestVMScreen {
    <#
      Saves what the VM's screen shows as a PNG and returns the path. Hyper-V hands the picture over as 16-bit colour
      (RGB565), so colours are close but not exact: fine for checking layout and text, not for matching a colour value.
    #>
    param([string]$Path = (Join-Path ([IO.Path]::GetTempPath()) ("zorbit-vm-{0:yyyyMMdd-HHmmss-fff}.png" -f (Get-Date))))
    $vm = Get-VMSystem
    $settings = Get-CimAssociatedInstance -InputObject $vm -ResultClassName Msvm_VirtualSystemSettingData |
        Where-Object VirtualSystemType -eq 'Microsoft:Hyper-V:System:Realized'
    $head = Get-CimAssociatedInstance -InputObject $vm -ResultClassName Msvm_VideoHead | Select-Object -First 1
    $w = [int]$head.CurrentHorizontalResolution; $h = [int]$head.CurrentVerticalResolution
    $svc = Get-CimInstance -Namespace $script:Ns -ClassName Msvm_VirtualSystemManagementService
    $r = Invoke-CimMethod -InputObject $svc -MethodName GetVirtualSystemThumbnailImage -Arguments @{
        TargetSystem = $settings; WidthPixels = [uint16]$w; HeightPixels = [uint16]$h }
    if ($r.ReturnValue -ne 0 -or -not $r.ImageData) { throw "Hyper-V gave no screen picture (return value $($r.ReturnValue))." }
    Add-Type -AssemblyName System.Drawing
    $bmp = New-Object System.Drawing.Bitmap($w, $h, [System.Drawing.Imaging.PixelFormat]::Format16bppRgb565)
    $data = $bmp.LockBits((New-Object System.Drawing.Rectangle(0, 0, $w, $h)),
        [System.Drawing.Imaging.ImageLockMode]::WriteOnly, $bmp.PixelFormat)
    try {
        for ($y = 0; $y -lt $h; $y++) {
            [Runtime.InteropServices.Marshal]::Copy([byte[]]$r.ImageData, $y * $w * 2, [IntPtr]($data.Scan0.ToInt64() + $y * $data.Stride), $w * 2)
        }
    } finally { $bmp.UnlockBits($data) }
    $bmp.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
    $Path
}

# ---------- keyboard ----------

$script:Vk = @{
    Ctrl = 0x11; Control = 0x11; Shift = 0x10; Alt = 0x12; Win = 0x5B
    Enter = 0x0D; Return = 0x0D; Esc = 0x1B; Escape = 0x1B; Tab = 0x09; Space = 0x20; Backspace = 0x08
    Delete = 0x2E; Del = 0x2E; Insert = 0x2D; Home = 0x24; End = 0x23; PageUp = 0x21; PageDown = 0x22
    Left = 0x25; Up = 0x26; Right = 0x27; Down = 0x28; Menu = 0x5D
}
1..24 | ForEach-Object { $script:Vk["F$_"] = 0x6F + $_ }
[char[]]'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' | ForEach-Object { $script:Vk["$_"] = [int]$_ }

function Get-VKey([string]$Name) {
    $k = $script:Vk[$Name]
    if ($null -eq $k) { throw "Unknown key '$Name'." }
    $k
}

function Get-VMKeyboard { Get-CimAssociatedInstance -InputObject (Get-VMSystem) -ResultClassName Msvm_Keyboard }

function Send-TestVMKeys {
    <#
      Presses keys in the VM like a real keyboard, so low-level hooks see them. Each argument is one key or a chord
      such as 'Ctrl+Shift+Esc'; the modifiers are held while the last key is pressed. -HoldMs keeps a chord down.
    #>
    [CmdletBinding(PositionalBinding = $false)]
    param([Parameter(Mandatory, Position = 0, ValueFromRemainingArguments)][string[]]$Keys, [int]$HoldMs = 60, [int]$GapMs = 120)
    $kb = Get-VMKeyboard
    foreach ($chord in $Keys) {
        $parts = $chord -split '\+' | ForEach-Object { Get-VKey $_.Trim() }
        foreach ($k in $parts) { Invoke-CimMethod -InputObject $kb -MethodName PressKey -Arguments @{ keyCode = [uint32]$k } | Out-Null }
        Start-Sleep -Milliseconds $HoldMs
        [array]::Reverse($parts)
        foreach ($k in $parts) { Invoke-CimMethod -InputObject $kb -MethodName ReleaseKey -Arguments @{ keyCode = [uint32]$k } | Out-Null }
        Start-Sleep -Milliseconds $GapMs
    }
}

function Send-TestVMKeyDown { param([Parameter(Mandatory)][string]$Key)
    Invoke-CimMethod -InputObject (Get-VMKeyboard) -MethodName PressKey -Arguments @{ keyCode = [uint32](Get-VKey $Key) } | Out-Null }

function Send-TestVMKeyUp { param([Parameter(Mandatory)][string]$Key)
    Invoke-CimMethod -InputObject (Get-VMKeyboard) -MethodName ReleaseKey -Arguments @{ keyCode = [uint32](Get-VKey $Key) } | Out-Null }

# Characters to (virtual key, shift) for the UK layout the VM uses. Hyper-V's own TypeText drops and repeats keys.
# Hyper-V turns a virtual key into a key position as on a US keyboard, and the VM reads that position as UK, so
# the keys that differ use the US key in that place: ' and @ are US 0xDE, # and ~ US 0xDC, and ` US 0xC0. \ and |
# are on the extra key next to left Shift, which US keyboards lack, so they go as raw scan codes ($script:RawChars).
$script:UkChars = [Collections.Hashtable]::new([StringComparer]::Ordinal)   # 'a' and 'A' are different keys here
foreach ($c in [char[]]'abcdefghijklmnopqrstuvwxyz') { $script:UkChars[[string]$c] = @([int][char]::ToUpper($c), $false) }
foreach ($c in [char[]]'ABCDEFGHIJKLMNOPQRSTUVWXYZ') { $script:UkChars[[string]$c] = @([int]$c, $true) }
foreach ($c in [char[]]'0123456789') { $script:UkChars[[string]$c] = @([int]$c, $false) }
$shifted = @{ '!' = '1'; '"' = '2'; '$' = '4'; '%' = '5'; '^' = '6'; '&' = '7'; '*' = '8'; '(' = '9'; ')' = '0' }
foreach ($k in $shifted.Keys) { $script:UkChars[$k] = @([int][char]$shifted[$k], $true) }
$oem = @{ ' ' = 0x20, $false; "`t" = 0x09, $false; "`n" = 0x0D, $false
    ';' = 0xBA, $false; ':' = 0xBA, $true; '=' = 0xBB, $false; '+' = 0xBB, $true; ',' = 0xBC, $false; '<' = 0xBC, $true
    '-' = 0xBD, $false; '_' = 0xBD, $true; '.' = 0xBE, $false; '>' = 0xBE, $true; '/' = 0xBF, $false; '?' = 0xBF, $true
    "'" = 0xDE, $false; '@' = 0xDE, $true; '[' = 0xDB, $false; '{' = 0xDB, $true; ']' = 0xDD, $false; '}' = 0xDD, $true
    '#' = 0xDC, $false; '~' = 0xDC, $true; '`' = 0xC0, $false }
foreach ($k in $oem.Keys) { $script:UkChars[$k] = $oem[$k] }
$script:RawChars = @{ '\' = [byte[]](0x56, 0xD6); '|' = [byte[]](0x2A, 0x56, 0xD6, 0xAA) }   # key 0x56, Shift 0x2A

function Send-TestVMText {
    <# Types text one key at a time (UK layout; no characters outside it, such as letters with accents). #>
    param([Parameter(Mandatory)][string]$Text, [int]$KeyMs = 25)
    $kb = Get-VMKeyboard
    foreach ($ch in [char[]]($Text -replace "`r", '')) {
        $raw = $script:RawChars[[string]$ch]
        if ($raw) {
            Invoke-CimMethod -InputObject $kb -MethodName TypeScancodes -Arguments @{ Scancodes = $raw } | Out-Null
            Start-Sleep -Milliseconds ($KeyMs * 2)
            continue
        }
        $map = $script:UkChars[[string]$ch]
        if (-not $map) { throw "Send-TestVMText cannot type '$ch'." }
        $vk, $shift = $map
        if ($shift) { Invoke-CimMethod -InputObject $kb -MethodName PressKey -Arguments @{ KeyCode = [uint32]0x10 } | Out-Null }
        Invoke-CimMethod -InputObject $kb -MethodName PressKey -Arguments @{ KeyCode = [uint32]$vk } | Out-Null
        Start-Sleep -Milliseconds $KeyMs
        Invoke-CimMethod -InputObject $kb -MethodName ReleaseKey -Arguments @{ KeyCode = [uint32]$vk } | Out-Null
        if ($shift) { Invoke-CimMethod -InputObject $kb -MethodName ReleaseKey -Arguments @{ KeyCode = [uint32]0x10 } | Out-Null }
        Start-Sleep -Milliseconds $KeyMs
    }
}

# ---------- mouse ----------

$script:Buttons = @{ Left = 1; Right = 2; Middle = 3 }

function Get-VMMouse {
    $m = Get-CimAssociatedInstance -InputObject (Get-VMSystem) -ResultClassName Msvm_SyntheticMouse
    if (-not $m) { throw 'The VM has no synthetic mouse yet (Windows in the VM has not loaded its Hyper-V drivers).' }
    $m
}

function Move-TestVMMouse {
    <# Moves the pointer to screen pixel (X, Y) in the VM. #>
    param([Parameter(Mandatory)][int]$X, [Parameter(Mandatory)][int]$Y)
    Invoke-CimMethod -InputObject (Get-VMMouse) -MethodName SetAbsolutePosition -Arguments @{
        horizontalPosition = [int]$X; verticalPosition = [int]$Y } | Out-Null
}

function Set-TestVMMouseButton {
    <# Holds a button down (-Down) or lets it go, for drags. #>
    param([ValidateSet('Left', 'Right', 'Middle')][string]$Button = 'Left', [switch]$Down)
    Invoke-CimMethod -InputObject (Get-VMMouse) -MethodName SetButtonState -Arguments @{
        ButtonIndex = [uint32]$script:Buttons[$Button]; IsDown = [bool]$Down } | Out-Null
}

function Invoke-TestVMClick {
    param([int]$X = -1, [int]$Y = -1, [ValidateSet('Left', 'Right', 'Middle')][string]$Button = 'Left')
    if ($X -ge 0 -and $Y -ge 0) { Move-TestVMMouse $X $Y; Start-Sleep -Milliseconds 80 }
    Set-TestVMMouseButton -Button $Button -Down
    Start-Sleep -Milliseconds 60
    Set-TestVMMouseButton -Button $Button
}

Export-ModuleMember -Function Get-TestVMConfig, Get-TestVMCredential, Connect-TestVMConsole, Restore-TestVM, New-TestVMCheckpoint, Wait-TestVM,
    Invoke-TestVM, Copy-ToTestVM, Copy-FromTestVM, Start-TestVMApp, Save-TestVMScreen, Send-TestVMKeys, Send-TestVMKeyDown,
    Send-TestVMKeyUp, Send-TestVMText, Move-TestVMMouse, Set-TestVMMouseButton, Invoke-TestVMClick
