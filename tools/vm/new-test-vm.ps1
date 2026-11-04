<#
.SYNOPSIS
  Makes the ZOrbit test VM in Hyper-V and installs Windows 11 Pro in it without any clicks.

.DESCRIPTION
  - Writes the answer file (autounattend.xml, with the password for the local account "tester": -Password, or a
    new random one) onto a small ISO, and saves the VM's name, folder and login to
    %LOCALAPPDATA%\ZOrbit-test-vm\vm.json for TestVM.psm1.
  - Makes a generation 2 VM with Secure Boot and a virtual TPM (Windows 11 needs both), fixed memory, the Default
    Switch for internet, and both ISOs in its DVD drives.
  - Starts it, presses a key so it boots from the Windows ISO, and waits until Windows is installed and tester is
    signed in on the desktop (about 15 to 30 minutes). Then it ejects both ISOs and takes the checkpoint "windows".
  Needs the host account in "Hyper-V Administrators"; no elevation. Run with -WhatIf to see the settings.
  docs\building.md ("Test on a clean Windows") says what to do next.

.EXAMPLE
  .\tools\vm\new-test-vm.ps1 -Iso C:\Users\you\Downloads\Windows11.iso -Folder D:\VMs
#>
#requires -Version 7
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory)][string]$Iso,
    [Parameter(Mandatory)][string]$Folder,   # one you can write to; Hyper-V's default under ProgramData needs elevation
    [string]$Name = 'ZOrbit Test',
    [int]$MemoryGB = 16,
    [int]$Cpus = 8,
    [int]$DiskGB = 160,
    [int]$Width = 1920,
    [int]$Height = 1080,
    [string]$Password   # a short one is easier to type when Windows asks; the VM is for tests only
)

$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
$Iso = (Resolve-Path $Iso).Path
$VmDir = Join-Path $Folder $Name
$Vhd = Join-Path $VmDir "$Name.vhdx"
$AnswerIso = Join-Path $VmDir 'answers.iso'
$ConfigDir = Join-Path $env:LOCALAPPDATA 'ZOrbit-test-vm'

if (Get-VM -Name $Name -ErrorAction SilentlyContinue) { throw "There is already a VM called '$Name'. Remove it first, or pick another -Name." }

Write-Host "VM '$Name' in $VmDir : $MemoryGB GB memory, $Cpus processors, $DiskGB GB disk, screen ${Width}x$Height"
Write-Host "Windows from $Iso"
if (-not $PSCmdlet.ShouldProcess($Name, 'create the VM and install Windows')) { return }

# ---- answer file and settings ----
$password = $Password
if (-not $password) {
    $alphabet = [char[]]'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
    $password = -join (1..20 | ForEach-Object { $alphabet[[Security.Cryptography.RandomNumberGenerator]::GetInt32($alphabet.Length)] })
}

New-Item -ItemType Directory -Force $VmDir, $ConfigDir | Out-Null
$staging = Join-Path ([IO.Path]::GetTempPath()) ("zorbit-answers-" + [guid]::NewGuid())
New-Item -ItemType Directory $staging | Out-Null
try {
    (Get-Content (Join-Path $Here 'autounattend.xml') -Raw).Replace('__PASSWORD__', [Security.SecurityElement]::Escape($password)).Replace('__TIMEZONE__', (Get-TimeZone).Id) |
        Set-Content (Join-Path $staging 'autounattend.xml') -Encoding utf8NoBOM

    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Runtime.InteropServices.ComTypes;
public static class ZOrbitIsoWriter {
    public static void Write(object stream, string path, int blockSize, int blocks) {
        var s = (IStream)stream;
        var buf = new byte[blockSize];
        using (var f = File.Create(path)) {
            for (int i = 0; i < blocks; i++) { s.Read(buf, blockSize, IntPtr.Zero); f.Write(buf, 0, blockSize); }
        }
    }
}
'@
    $fsi = New-Object -ComObject IMAPI2FS.MsftFileSystemImage
    $fsi.FileSystemsToCreate = 3   # ISO 9660 and Joliet
    $fsi.VolumeName = 'ANSWERS'
    $fsi.Root.AddTree($staging, $false)
    $img = $fsi.CreateResultImage()
    [ZOrbitIsoWriter]::Write($img.ImageStream, $AnswerIso, $img.BlockSize, $img.TotalBlocks)
} finally { Remove-Item -Recurse -Force $staging }

# ---- the VM ----
$newVm = @{ Name = $Name; Generation = 2; Path = $Folder; MemoryStartupBytes = $MemoryGB * 1GB
    NewVHDPath = $Vhd; NewVHDSizeBytes = $DiskGB * 1GB }
if (Get-VMSwitch -Name 'Default Switch' -ErrorAction SilentlyContinue) { $newVm.SwitchName = 'Default Switch' }
else { Write-Warning 'There is no Default Switch, so the VM has no network. Add one in Hyper-V Manager to install ZBrush.' }
$vm = New-VM @newVm
Set-VM -VM $vm -ProcessorCount $Cpus -StaticMemory -CheckpointType Standard -AutomaticCheckpointsEnabled $false `
    -AutomaticStopAction ShutDown
Set-VMVideo -VM $vm -ResolutionType Single -HorizontalResolution $Width -VerticalResolution $Height
Set-VMFirmware -VM $vm -EnableSecureBoot On -SecureBootTemplate MicrosoftWindows
Set-VMKeyProtector -VM $vm -NewLocalKeyProtector
Enable-VMTPM -VM $vm
Enable-VMIntegrationService -VM $vm -Name 'Guest Service Interface'
$dvd = Add-VMDvdDrive -VM $vm -Path $Iso -Passthru
Add-VMDvdDrive -VM $vm -Path $AnswerIso
Set-VMFirmware -VM $vm -FirstBootDevice $dvd

# Only now: this file is what TestVM.psm1 drives, so a run that failed above must not take it from a working VM.
[pscustomobject]@{ Name = $Name; Folder = $VmDir; User = 'tester'; Password = $password } |
    ConvertTo-Json | Set-Content (Join-Path $ConfigDir 'vm.json') -Encoding utf8NoBOM
Write-Host "Login saved to $(Join-Path $ConfigDir 'vm.json') (user tester)."

# ---- install ----
Start-VM -VM $vm
# The Windows ISO asks to "press any key to boot from CD or DVD" for a few seconds. Press Z (it does nothing in
# Setup, where Space could follow a focused link) and only for the first seconds, before Setup's window is up.
$sys = Get-CimInstance -Namespace root\virtualization\v2 -ClassName Msvm_ComputerSystem -Filter "ElementName='$Name'"
$until = (Get-Date).AddSeconds(8)
while ((Get-Date) -lt $until) {
    $kb = Get-CimAssociatedInstance -InputObject $sys -ResultClassName Msvm_Keyboard -ErrorAction SilentlyContinue
    if ($kb) { Invoke-CimMethod -InputObject $kb -MethodName TypeKey -Arguments @{ keyCode = [uint32]0x5A } -ErrorAction SilentlyContinue | Out-Null }
    Start-Sleep -Milliseconds 500
}

Write-Host 'Installing Windows. This takes 15 to 30 minutes; you can watch it in Hyper-V Manager.'
Import-Module (Join-Path $Here 'TestVM.psm1') -Force
Wait-TestVM -TimeoutSec 3600
Write-Host 'Windows is installed and tester is signed in.'

Get-VMDvdDrive -VM $vm | Set-VMDvdDrive -Path $null
Remove-Item -LiteralPath $AnswerIso -Force   # it holds the password in plain text
Set-VMFirmware -VM $vm -FirstBootDevice (Get-VMHardDiskDrive -VM $vm)
New-TestVMCheckpoint -Name 'windows'
Write-Host "Took the checkpoint 'windows'. Next: install ZBrush in the VM, then take the checkpoint 'vanilla'."
