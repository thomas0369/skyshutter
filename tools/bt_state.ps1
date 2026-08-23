# Read or set the state of this machine's Bluetooth radio.
#
#   powershell -ExecutionPolicy Bypass -File bt_state.ps1            # report
#   powershell -ExecutionPolicy Bypass -File bt_state.ps1 -Action Off
#   powershell -ExecutionPolicy Bypass -File bt_state.ps1 -Action On
#
# Why this exists: after a few connect-and-scan cycles the Windows Bluetooth
# stack stops finding devices that are plainly in range -- measured 22.08.2026,
# five failed pairing attempts in a row, then everything found again right
# after a radio reset. Off, on, and about twelve seconds of patience is the
# only thing that has reliably cleared it. See docs/pairing.md, trap 5b.
#
# No admin rights needed; the WinRT radio API asks the user once and remembers.

param([string]$Action = "status")

Add-Type -AssemblyName System.Runtime.WindowsRuntime

# PowerShell cannot await WinRT operations on its own -- fish the generic
# AsTask overload out by reflection and drive it synchronously.
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
                   $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

function Await($op, $type) {
    $t = $asTaskGeneric.MakeGenericMethod($type).Invoke($null, @($op))
    $t.Wait(10000) | Out-Null
    $t.Result
}

[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null

Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$bt = $radios | Where-Object { $_.Kind -eq 'Bluetooth' }

if (-not $bt) {
    Write-Output "Bluetooth-Funk: nicht vorhanden"
    exit 1
}

if ($Action -ne "status") {
    Await ($bt.SetStateAsync($Action)) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
    Start-Sleep -Milliseconds 1200
}

Write-Output "Bluetooth-Funk: $($bt.State)"
