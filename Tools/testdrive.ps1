# Runs the automated test drive without a window and prints the measured numbers:
# 0-60 and 0-100 km/h times, the full-brake stopping distance, then handling:
#   power oversteer   full lock and full throttle from rest: peak sideslip (tail out past ~10 deg)
#   tap at 110        full lock for 0.4 s, hands off: does the car settle by itself
#   slide at 110      full lock and handbrake for 0.6 s, then countersteer: recovered or spun
#
#   .\Tools\testdrive.ps1
#   .\Tools\testdrive.ps1 -Override "MaxTorqueNm=420","bABS=False"
#   .\Tools\testdrive.ps1 -Vehicle Delivery      (any preset id of WSPC2VehicleProfile.cpp; default: Patrol)
#
# Overrides apply to this run only; permanent values live in Config\DefaultGame.ini.
param(
    [string[]]$Override = @(),
    [string]$Vehicle = "",
    [int]$TimeoutSeconds = 300,
    [switch]$Trace
)

$project = Join-Path (Split-Path $PSScriptRoot -Parent) "WSPC2.uproject"
$editor = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$log = Join-Path $env:TEMP "wspc2_testdrive.log"
Remove-Item $log -ErrorAction SilentlyContinue

$arguments = @("`"$project`"", "/Game/VehicleTemplate/Maps/VehicleBasic", "-abslog=`"$log`"",
    "-game", "-nullrhi", "-nosound", "-unattended", "-nosplash", "-WSPC2TestDrive")
if ($Vehicle) { $arguments += "-WSPC2Vehicle=$Vehicle" }

if ($Override.Count -gt 0) {
    $pairs = $Override | ForEach-Object { "[/Script/WSPC2.WSPC2VehicleTuning]:$_" }
    $arguments += "-ini:Game:" + ($pairs -join ",")
}

$process = Start-Process $editor -ArgumentList $arguments -PassThru -WindowStyle Hidden
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)

while ((Get-Date) -lt $deadline -and -not $process.HasExited) {
    if ((Test-Path $log) -and (Select-String -Path $log -Pattern "caught with countersteer|Fatal error" -Quiet)) { break }
    Start-Sleep -Seconds 2
}

Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue

if (Test-Path $log) {
    $pattern = if ($Trace) { "TestDrive:|TestTrace:|Wheel \d:|Car at height|Mass properties|Template body|PatrolCruiser|Vehicle audio|Fatal error|Ensure condition" } else { "TestDrive:|Fatal error|Ensure condition" }
    Select-String -Path $log -Pattern $pattern | ForEach-Object { $_.Line -replace '^\[[^\]]+\]\[\s*\d+\]LogWSPC2: ', '' }
} else {
    "No log produced."
}
