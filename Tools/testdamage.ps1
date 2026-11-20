# Purpose: Runs the automated headless progressive vehicle damage test (-WSPC2TestDamage)
#   covering Light/Moderate wall collisions, Heavy corner tire blowout, rim sparks, Wrecked stall,
#   and full DoResetVehicle/RepairAll restoration, then prints all ChaosDamage & TestDamage telemetry.
# Command: .\Tools\testdamage.ps1 [-TimeoutSeconds 180]
# Inputs: WSPC2.uproject, /Game/VehicleTemplate/Maps/VehicleBasic, Config/DefaultGame.ini
# Outputs: Filtered LogWSPC2 telemetry lines from %TEMP%\wspc2_testdamage.log to stdout.
param(
    [int]$TimeoutSeconds = 180
)

$project = Join-Path (Split-Path $PSScriptRoot -Parent) "WSPC2.uproject"
$editor = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$log = Join-Path $env:TEMP "wspc2_testdamage.log"
Remove-Item $log -ErrorAction SilentlyContinue

$arguments = @("`"$project`"", "/Game/VehicleTemplate/Maps/VehicleBasic", "-abslog=`"$log`"",
    "-game", "-nullrhi", "-nosound", "-unattended", "-nosplash", "-WSPC2TestDamage")

$process = Start-Process $editor -ArgumentList $arguments -PassThru -WindowStyle Hidden
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)

while ((Get-Date) -lt $deadline -and -not $process.HasExited) {
    if ((Test-Path $log) -and (Select-String -Path $log -Pattern "TestDamage: COMPLETE|Fatal error" -Quiet)) { break }
    Start-Sleep -Seconds 2
}

if (-not $process.HasExited) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
}

if (Test-Path $log) {
    Select-String -Path $log -Pattern "TestDamage|ChaosDamage|Fatal error|Ensure condition|LogWSPC2: Warning|LogWSPC2: Error" |
        ForEach-Object { $_.Line -replace '^\[[^\]]+\]\[\s*\d+\]LogWSPC2:\s*', '' }
} else {
    "No log produced."
}
