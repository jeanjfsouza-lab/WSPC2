# Plays one campaign mission on WSPC2_Bay, or lets the test autopilot drive it, and prints how it went.
#
#   .\Tools\mission.ps1 Op01              opens the game in a window on the mission (starts ~8 s after the map loads)
#   .\Tools\mission.ps1 Op03 -Autopilot   no window: the test autopilot drives, the game quits by itself at the end
#
# Inputs:  mission id (Op01..Op04, from /Game/Bay/Missions/DA_Missions), optional -Autopilot, -TimeoutSeconds, -ResX/-ResY.
# Outputs: the mission's messages and its result line (MISSAO CUMPRIDA / MISSAO FALHOU) in this terminal;
#          the full log in Saved\Logs\mission_<id>.log.
# The script waits for the game to close. UnrealEditor.exe is a windowed program, so a bare "& UnrealEditor.exe"
# returns at once and the run goes on unseen.
param(
    [Parameter(Position = 0)]
    [ValidatePattern('^Op\d\d$')]
    [string]$Mission = "Op01",
    [switch]$Autopilot,
    [int]$TimeoutSeconds = 0,
    [int]$ResX = 1600,
    [int]$ResY = 900
)

$root = Split-Path $PSScriptRoot -Parent
$project = Join-Path $root "WSPC2.uproject"
$engine = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64"
$log = Join-Path $root "Saved\Logs\mission_$Mission.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null

try {
    if (Test-Path $log) { Remove-Item $log -ErrorAction Stop }
} catch {
    Write-Warning "Another run is still writing $log. Wait for it to finish (or end it in Task Manager) and try again."
    exit 1
}

$arguments = @("`"$project`"", "/Game/Bay/Maps/WSPC2_Bay", "-game", "-nosplash", "-WSPC2Mission=$Mission", "-abslog=`"$log`"")
if ($Autopilot) {
    $exe = Join-Path $engine "UnrealEditor-Cmd.exe"
    $arguments += @("-nullrhi", "-nosound", "-unattended", "-WSPC2MissionAutopilot")
    if ($TimeoutSeconds -le 0) { $TimeoutSeconds = 420 }
    $process = Start-Process $exe -ArgumentList $arguments -PassThru -WindowStyle Hidden
    "Mission $Mission with the test autopilot, no window (pid $($process.Id)). It takes 1-3 minutes."
} else {
    $exe = Join-Path $engine "UnrealEditor.exe"
    $arguments += @("-windowed", "-ResX=$ResX", "-ResY=$ResY")
    $process = Start-Process $exe -ArgumentList $arguments -PassThru
    "Opening the game on mission $Mission (pid $($process.Id)). The window takes about a minute to appear; close it to end."
}

# Echo the mission's own messages as they arrive, and the running status every 10 s.
$printed = 0
$lastStatus = [DateTime]::MinValue
$deadline = if ($TimeoutSeconds -gt 0) { (Get-Date).AddSeconds($TimeoutSeconds) } else { [DateTime]::MaxValue }
$strip = '^\[[^\]]+\]\[\s*\d+\]LogWSPC2: '

function Read-MissionLines {
    if (-not (Test-Path $log)) { return @() }
    try {
        $stream = [System.IO.File]::Open($log, 'Open', 'Read', 'ReadWrite')
        $reader = New-Object System.IO.StreamReader($stream)
        $text = $reader.ReadToEnd()
        $reader.Close()
    } catch { return @() }
    return @($text -split "`r?`n" | Where-Object { $_ -match 'LogWSPC2: Mission|Fatal error|Ensure condition' })
}

while (-not $process.HasExited -and (Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    $lines = Read-MissionLines
    for ($i = $printed; $i -lt $lines.Count; $i++) {
        $line = $lines[$i] -replace $strip, ''
        if ($line -like 'Mission status:*') {
            if (((Get-Date) - $lastStatus).TotalSeconds -lt 10) { continue }
            $lastStatus = Get-Date
        }
        $line
    }
    $printed = $lines.Count
}

if (-not $process.HasExited) {
    Write-Warning "Still running after $TimeoutSeconds s; stopping it."
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
}

$result = Read-MissionLines | Where-Object { $_ -match 'MISSAO (CUMPRIDA|FALHOU)|Fatal error' } | Select-Object -Last 1
if ($result) {
    "Result: " + ($result -replace $strip, '')
} else {
    "No result line: the mission did not finish (closed early, or see $log)."
}
