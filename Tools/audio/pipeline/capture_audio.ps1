<#
Records what a player hears during one of the automated test runs, for listening and for analysis.

Runs the game with a test hook (-WSPC2TestDrive: launch, gears, braking, slides; -WSPC2TestDamage: wall hits,
crunch, glass; -WSPC2TestTrackAudit with -Map /Game/TestTrack/Maps/WSPC2_TestTrack: 33 traffic cars, showroom,
angled barriers) plus -WSPC2AudioCapture and -WSPC2AudioTrace, rendering offscreen: without rendering
(-nullrhi) the audio listener never follows the camera and stays at the map origin. The window stays hidden but
the game plays through the default output device, so the PC makes sound while it runs.

  powershell -File Tools/audio/pipeline/capture_audio.ps1 -Name patrol_bank
  powershell -File Tools/audio/pipeline/capture_audio.ps1 -Name patrol_stems -Stems
  powershell -File Tools/audio/pipeline/capture_audio.ps1 -Name classic_damage -Hook TestDamage -Vehicle Police_Fairheaven80_Retro
  powershell -File Tools/audio/pipeline/capture_audio.ps1 -Name nolimit -Hook TestDamage -Extra '-WSPC2NoMasterLimiter'

Inputs:  the built WSPC2Editor, the imported audio (ue_import_and_build_assets.py)
Outputs: Saved/Audio/Pipeline/capture/<Name>.wav and <Name>.log (game log with AudioTrace / AudioProof lines)
#>
param(
    [Parameter(Mandatory = $true)][string]$Name,
    [ValidateSet('TestDrive', 'TestDamage', 'TestTrackAudit')][string]$Hook = 'TestDrive',
    [string]$Vehicle = '',
    [int]$Seconds = 45,
    [string]$Map = '/Game/VehicleTemplate/Maps/VehicleBasic',
    [switch]$Stems,
    [string[]]$Extra = @(),
    [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$project = Join-Path $root 'WSPC2.uproject'
$editor = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$folder = Join-Path $root 'Saved\Audio\Pipeline\capture'
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$log = Join-Path $folder "$Name.log"
Remove-Item $log, (Join-Path $folder "$Name.wav") -ErrorAction SilentlyContinue

$arguments = @("`"$project`"", $Map, "-abslog=`"$log`"", '-game', '-RenderOffscreen', '-ResX=1280', '-ResY=720', '-windowed',
    '-unattended', '-nosplash', "-WSPC2$Hook", "-WSPC2AudioCapture=$Name", "-WSPC2AudioCaptureSeconds=$Seconds",
    '-WSPC2AudioCaptureDelay=1', '-WSPC2AudioTrace', '-ini:Engine:[Audio]:UnfocusedVolumeMultiplier=1.0')
if ($Vehicle) { $arguments += "-WSPC2Vehicle=$Vehicle" }
if ($Stems) { $arguments += '-WSPC2AudioStems' }
if ($Extra.Count -gt 0) { $arguments += $Extra }

$process = Start-Process $editor -ArgumentList $arguments -PassThru -WindowStyle Hidden
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline -and -not $process.HasExited) {
    if ((Test-Path $log) -and (Select-String -Path $log -Pattern 'AudioCapture: saved|Fatal error|Unhandled Exception' -Quiet)) {
        Start-Sleep -Seconds 2
        break
    }
    Start-Sleep -Seconds 2
}
Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
if (Test-Path $log) {
    Select-String -Path $log -Pattern 'Vehicle audio:|AudioProof|AudioCapture: saved|TestDrive: (0-|100-)|TestDamage: COMPLETE|Fatal error|Ensure condition' |
        ForEach-Object { $_.Line -replace '^\[[^\]]+\]\[\s*\d+\]Log\w+: ', '' }
} else {
    'No log produced.'
}
