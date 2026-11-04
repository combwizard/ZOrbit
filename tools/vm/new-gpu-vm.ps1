<#
.SYNOPSIS
  Makes the GPU VM: a copy of the test VM with a share of the host's graphics card. Or refreshes its driver.

.DESCRIPTION
  A VM with a GPU partition (GPU-P) cannot keep memory in a checkpoint or be restored while it runs, so each restore
  is a boot, and it has to hold the same driver as the host. That is why this is a second VM: the test VM stays a
  plain Windows that a host driver update cannot break, and this one is for what needs real graphics.

  - Copies the checkpoint "vanilla" of the test VM to a new VM. The copy resumes from memory and shuts down cleanly,
    so nothing the checkpoint held only in the disk cache is lost.
  - Copies the host's NVIDIA driver into the VM, adds the GPU partition and takes the checkpoint "gpu".
  - Run it again after a host driver update: the VM has to have the same driver as the host. The VM itself is kept.
  Needs the host account in "Hyper-V Administrators" and the test VM made by new-test-vm.ps1. Windows on a PC and
  GeForce cards are outside what Microsoft supports for GPU-P, so this is for tools only.
  docs\building.md ("A VM with a graphics card") says more.

.EXAMPLE
  pwsh tools\vm\new-gpu-vm.ps1
#>
#requires -Version 7
[CmdletBinding()]
param(
    [string]$Name = 'ZOrbit GPU',
    [string]$From = 'vanilla',      # the test VM's checkpoint to copy
    [int]$MemoryGB = 12,
    [int]$Cpus = 8
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'TestVM.psm1') -Force
$cred = Get-TestVMCredential        # the copy has the test VM's login

$partitionable = Get-VMHostPartitionableGpu | Where-Object Name -match 'VEN_10DE' | Select-Object -First 1     # NVIDIA's PCI id
if (-not $partitionable) { throw 'The host has no NVIDIA card that Hyper-V can partition.' }
$driver = Get-HostGpuDriver
if (-not (Test-Path $driver.Folder)) { throw "No driver folder at $($driver.Folder)." }
Write-Host "Host card: $($driver.Name), driver $($driver.Version)"

function Wait-GuestDesktop {
    <# As Wait-TestVM, for a VM the module is not pointing at yet. #>
    $until = (Get-Date).AddSeconds(300)
    while ((Get-Date) -lt $until) {
        try {
            $ok = Invoke-Command -VMName $Name -Credential $cred -ErrorAction Stop -ScriptBlock {
                [bool](Get-Process explorer -ErrorAction SilentlyContinue | Where-Object SessionId -gt 0) -and
                -not (Get-Process FirstLogonAnim -ErrorAction SilentlyContinue)
            }
            if ($ok) { return }
        } catch { }
        Start-Sleep -Seconds 3
    }
    throw "'$Name' did not reach the desktop within 300 seconds."
}

function Install-GuestDriver {
    <# With the VM running and no GPU partition: copies the driver in. Windows looks for it in HostDriverStore. #>
    $guestStore = 'C:\Windows\System32\HostDriverStore\FileRepository'
    $tar = Join-Path ([IO.Path]::GetTempPath()) "zorbit-gpu-driver-$PID.tar"
    tar -cf $tar -C (Split-Path $driver.Folder) (Split-Path $driver.Folder -Leaf)
    if ($LASTEXITCODE -ne 0) { throw 'tar could not pack the driver folder.' }
    $session = New-PSSession -VMName $Name -Credential $cred
    try {
        Invoke-Command -Session $session -ArgumentList $guestStore -ScriptBlock {
            param($store)
            if (Test-Path $store) { Remove-Item (Join-Path $store '*') -Recurse -Force }   # an older driver's folder
            New-Item -ItemType Directory -Force $store | Out-Null
        }
        Copy-VMFile -Name $Name -SourcePath $tar -DestinationPath 'C:\zorbit-test\driver.tar' -FileSource Host -CreateFullPath -Force
        Invoke-Command -Session $session -ArgumentList $guestStore -ScriptBlock {
            param($store)
            tar -xf C:\zorbit-test\driver.tar -C $store
            if ($LASTEXITCODE -ne 0) { throw 'tar could not unpack the driver in the VM.' }
            Remove-Item C:\zorbit-test\driver.tar -Force
            Write-VolumeCache C
        }
        # What programs load from System32 rather than from the driver's own folder.
        Get-ChildItem C:\Windows\System32\nvapi64.dll, C:\Windows\System32\nvml.dll -File -ErrorAction SilentlyContinue | ForEach-Object {
            Copy-Item $_.FullName -Destination "C:\Windows\System32\$($_.Name)" -ToSession $session -Force
        }
    } finally {
        Remove-PSSession $session
        Remove-Item $tar -Force -ErrorAction SilentlyContinue
    }
}

function Add-GuestGpu {
    <# With the VM off: attaches the partition, starts the VM and checks that Windows in it sees the card. #>
    Add-VMGpuPartitionAdapter -VMName $Name -InstancePath $partitionable.Name
    Set-VM -VMName $Name -GuestControlledCacheTypes $true -LowMemoryMappedIoSpace 1GB -HighMemoryMappedIoSpace 32GB
    Start-VM -Name $Name
    Wait-GuestDesktop
    # -PresentOnly: once the partition has been removed and added back, Windows also lists the old card, as Unknown.
    $status = Invoke-Command -VMName $Name -Credential $cred -ScriptBlock {
        Get-PnpDevice -Class Display -PresentOnly | Where-Object FriendlyName -match 'NVIDIA' | Select-Object -First 1 -ExpandProperty Status
    }
    if ($status -ne 'OK') { throw "The VM's graphics card has status '$status'. See Device Manager in the VM." }
}

if (Get-VM -Name $Name -ErrorAction SilentlyContinue) {
    # A run that stopped while swapping the checkpoints at the end leaves "gpu-new", which is a whole checkpoint.
    $snap = Get-VMSnapshot -VMName $Name -Name gpu -ErrorAction SilentlyContinue
    $new = Get-VMSnapshot -VMName $Name -Name gpu-new -ErrorAction SilentlyContinue
    if ($new -and $snap) { $new | Remove-VMSnapshot -Confirm:$false }
    elseif ($new) {
        $new | Rename-VMSnapshot -NewName gpu
        $snap = Get-VMSnapshot -VMName $Name -Name gpu
    }
    if (-not $snap) {
        throw "'$Name' has no checkpoint ""gpu"", so an earlier run stopped halfway. Turn it off with Stop-VM -TurnOff, remove it with Remove-VM, delete its folder, and run this again."
    }
    Write-Host "'$Name' exists: copying the host's driver into it."
    Stop-VM -Name $Name -TurnOff -Force -ErrorAction SilentlyContinue
    Restore-VMSnapshot -VMSnapshot $snap -Confirm:$false
    Remove-VMGpuPartitionAdapter -VMName $Name
    Start-VM -Name $Name
    Wait-GuestDesktop
    Install-GuestDriver
    Stop-VM -Name $Name -Force      # a clean shutdown
    Add-GuestGpu
    $folder = (Get-VM -Name $Name).Path
} else {
    $test = Get-TestVMConfig
    $folder = Join-Path (Split-Path $test.Folder) $Name
    $export = "$folder-export"
    if (Test-Path $folder) { throw "$folder already exists. Remove it first, or pick another -Name." }
    Write-Host "Copying the checkpoint ""$From"" of '$($test.Name)' to $folder ..."
    New-Item -ItemType Directory -Force $export, "$folder\Virtual Hard Disks" | Out-Null
    try {
        Get-VMSnapshot -VMName $test.Name -Name $From | Export-VMSnapshot -Path $export
        $vmcx = Get-ChildItem $export -Recurse -Filter *.vmcx | Select-Object -First 1
        $vm = Import-VM -Path $vmcx.FullName -Copy -GenerateNewId -VirtualMachinePath $folder -SnapshotFilePath $folder `
            -SmartPagingFilePath $folder -VhdDestinationPath "$folder\Virtual Hard Disks"
    } finally { Remove-Item -LiteralPath $export -Recurse -Force -ErrorAction SilentlyContinue }
    Rename-VM -VM $vm -NewName $Name
    $vm = Get-VM -Name $Name

    Write-Host 'Resuming the copy, to save what it holds in memory...'
    Start-VM -VM $vm
    Wait-GuestDesktop
    Invoke-Command -VMName $Name -Credential $cred -ScriptBlock { Write-VolumeCache C }
    Write-Host 'Copying the driver...'
    Install-GuestDriver
    Stop-VM -VM $vm -Force          # a clean shutdown
    Set-VM -VM $vm -MemoryStartupBytes ($MemoryGB * 1GB) -ProcessorCount $Cpus -CheckpointType ProductionOnly `
        -AutomaticCheckpointsEnabled $false -AutomaticStartAction Nothing -AutomaticStopAction TurnOff
    Add-GuestGpu
}

# Take the new checkpoint before the old one goes, so a failure here leaves a VM that can still be restored.
Checkpoint-VM -Name $Name -SnapshotName gpu-new
Get-VMSnapshot -VMName $Name -Name gpu -ErrorAction SilentlyContinue | Remove-VMSnapshot -Confirm:$false
Rename-VMSnapshot -VMName $Name -Name gpu-new -NewName gpu

[pscustomobject]@{ Name = $Name; Folder = $folder; DriverVersion = $driver.Version } |
    ConvertTo-Json | Set-Content (Join-Path $env:LOCALAPPDATA 'ZOrbit-test-vm\gpu-vm.json') -Encoding utf8NoBOM
Write-Host "Took the checkpoint ""gpu"" with driver $($driver.Version). Next: Use-TestVM -Gpu, then Restore-TestVM gpu."
