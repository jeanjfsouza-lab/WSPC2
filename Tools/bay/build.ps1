<#
Runs one of the Tools/bay editor scripts in the headless Unreal editor. By default build_bay.py, which
(re)builds stages of /Game/Bay/Maps/WSPC2_Bay.

  .\Tools\bay\build.ps1 [-Stages "sectors,sea,light"] [-Sectors "CC1"] [-WaitMinutes 15] [-Surfaces]
  .\Tools\bay\build.ps1 -Script merge_towers.py [-Towers "BPP_NYG_Ref_N1,..."]
  .\Tools\bay\build.ps1 -Script unit_faces.py -Commandlet

-Commandlet runs the script without the editor's windows and renderer (for scripts that only read assets).
-NullRHI runs the full editor without a video device: for the stages that place things (sectors, buildings,
props) when the video driver is unusable. Not for "ground", "sea", "light" or "materials", which need it.
-Map is the map the editor opens when it starts. Default: the engine's empty Entry map, because build_bay.py
opens the maps it needs itself: since the Bay was split into district sublevels (2026-11-20) it loads only the
sublevels a build changes, and opening the Bay's persistent map first would load all of them for nothing.
-Surfaces runs Tools/bay/apply_bay_surfaces.py afterwards (grip per surface, Bay meshes only); use it with any build that
includes the "sectors" stage.

Inputs   Saved/Bay (see the script's own header for what it reads)
Outputs  whatever the script writes; Saved/Logs/bay_<script>.log; prints the log lines the script tagged
         (BAY for build_bay.py, TOWERS for merge_towers.py)

Nobody may compile while an editor runs, and another session may be running the game (car tests): the
launcher waits until nothing is compiling and enough memory is free for one more instance.
#>
param(
    [string]$Script = "build_bay.py",
    [string]$Stages = "",
    [string]$Sectors = "",
    [string]$Towers = "",
    [string]$Structures = "",
    [int]$WaitMinutes = 15,
    [double]$MinFreeGB = 5.5,
    [switch]$Surfaces,
    [switch]$Commandlet,
    [switch]$NullRHI,
    [string]$Map = "/Engine/Maps/Entry"
)

$project = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$editor = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
$name = [IO.Path]::GetFileNameWithoutExtension($Script)
$log = Join-Path $project "Saved\Logs\bay_$name.log"
# An editor that did not die properly keeps its log open: the next editor then writes somewhere else and this
# script would print the old log's lines as if they were new. Use a log of its own name in that case.
if (Test-Path $log) {
    try { $probe = [IO.File]::Open($log, 'Open', 'ReadWrite', 'None'); $probe.Close() }
    catch {
        $log = Join-Path $project ("Saved\Logs\bay_{0}_{1:HHmmss}.log" -f $name, (Get-Date))
        Write-Output "BUILD the usual log is held by another process; this run writes $log"
    }
}
$path = (Join-Path $PSScriptRoot $Script) -replace '\\', '/'
$tag = @{ "build_bay" = "BAY"; "merge_towers" = "TOWERS"; "unit_faces" = "FACES"; "extra_units" = "EXTRA"; "fix_usage_flags" = "USAGE" }[$name]
if (-not $tag) { $tag = "BAY" }
if (-not (Test-Path $path)) { Write-Output "BUILD no such script: $path"; exit 1 }

$deadline = (Get-Date).AddMinutes($WaitMinutes)
while ($true) {
    $busy = Get-Process UnrealBuildTool*, ShaderCompileWorker* -ErrorAction SilentlyContinue
    $free = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB
    if (-not $busy -and $free -ge $MinFreeGB) { break }
    if ((Get-Date) -gt $deadline) {
        Write-Output ("BUILD gave up waiting: {0} build processes running, {1:N1} GB free" -f @($busy).Count, $free)
        exit 2
    }
    Start-Sleep -Seconds 10
}

# which district sublevel each sector and structure goes to (build_bay.py reads Saved/Bay/levels.json)
if ($name -eq "build_bay") {
    python -P (Join-Path $PSScriptRoot "plan_levels.py") | Select-Object -Last 1
}

$env:BAY_STAGES = $Stages
$env:BAY_SECTORS = $Sectors
$env:BAY_TOWERS = $Towers
$env:BAY_STRUCTURES = $Structures
$started = Get-Date
if ($Commandlet) {
    & $editor (Join-Path $project "WSPC2.uproject") -run=pythonscript "-script=$path" -unattended -nosplash "-abslog=$($log -replace '\\','/')" | Out-Null
} elseif ($NullRHI) {
    & $editor (Join-Path $project "WSPC2.uproject") @(if ($Map) { $Map }) "-ExecutePythonScript=$path" -unattended -nullrhi -nosplash -nosound "-abslog=$($log -replace '\\','/')" | Out-Null
} else {
    & $editor (Join-Path $project "WSPC2.uproject") @(if ($Map) { $Map }) "-ExecutePythonScript=$path" -unattended -RenderOffscreen -nosplash -nosound "-abslog=$($log -replace '\\','/')" | Out-Null
}
$code = $LASTEXITCODE
Write-Output ("BUILD {0}: exit {1} after {2:N0} s" -f $Script, $code, ((Get-Date) - $started).TotalSeconds)
if (Test-Path $log) {
    Select-String -Path $log -Pattern "LogPython: $tag (?!inspect)" | ForEach-Object { $_.Line -replace '^.*LogPython: ', '' }
    Select-String -Path $log -Pattern "LogPython: Error|Traceback|Ran out of memory|Unable to build Nanite" | Select-Object -First 8 | ForEach-Object { "BUILD PROBLEM " + ($_.Line -replace '^\[[^\]]+\]\[\s*\d+\]', '') }
}

# -Surfaces: give every drivable surface of the Bay its grip again. The map builders assign plain materials,
# so the grip pass (a commandlet) has to run after any stage that re-imports meshes. It is the Bay's own pass,
# Tools/bay/apply_bay_surfaces.py: the same code as Tools/surfaces/apply_surfaces.py, on the Bay's folder only
# (the pass over every map stops at a mesh of the first city that is damaged on disk; see that script).
if ($Surfaces) {
    $surfaceLog = Join-Path $project "Saved\Logs\bay_surfaces.log"
    $surfaceScript = (Join-Path $PSScriptRoot "apply_bay_surfaces.py") -replace '\\', '/'
    $started = Get-Date
    & $editor (Join-Path $project "WSPC2.uproject") -run=pythonscript "-script=$surfaceScript" -unattended -nosplash "-abslog=$($surfaceLog -replace '\\','/')" | Out-Null
    Write-Output ("BUILD apply_bay_surfaces.py: exit {0} after {1:N0} s" -f $LASTEXITCODE, ((Get-Date) - $started).TotalSeconds)
    if (Test-Path $surfaceLog) {
        Select-String -Path $surfaceLog -Pattern "SURFACES " | ForEach-Object { $_.Line -replace '^.*(SURFACES )', '$1' }
    }
}
exit $code
