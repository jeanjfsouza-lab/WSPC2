<#
Takes the pictures of the crew preview: runs the game on /Game/Crew/Maps/CrewPreview through a few fixed cameras round
the patrol car (the -WSPC2Views test hook of AWSPC2PlayerController) and moves the pictures to Saved/Crew/shots.

  powershell -File Tools/crew/shoot_crew_preview.ps1 [-Tag v1]

Inputs   /Game/Crew/Maps/CrewPreview (Tools/crew/build_crew_preview.py); the cameras below (car space, cm: the car stands
         at the origin facing +x, the driver sits at y = -41.5, the gunner leans out of the passenger window at y = +100)
Outputs  Saved/Crew/shots/<tag>_NN_CREW_<camera>.png, Saved/Crew/views.txt, Saved/Logs/crew_views.log
Runs the game with the Bay's review game mode (no patrol car spawned). Waits, like Tools/bay/tour.ps1, until nothing
compiles and enough memory is free.
#>
param([string]$Tag = "v1", [int]$WaitMinutes = 15, [double]$MinFreeGB = 5.5)

$project = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$editor = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
$views = Join-Path $project "Saved\Crew\views.txt"
$shots = Join-Path $project "Saved\Crew\shots"
$log = Join-Path $project "Saved\Logs\crew_views.log"
$captures = Join-Path $project "Saved\Screenshots\Views"
@(
    "CREW_warmup;30,-330,135;0,-41,105",
    "CREW_door;30,-330,135;0,-41,105",
    "CREW_front;450,-40,160;-20,-41,110",
    "CREW_quarter;320,-330,210;0,-35,100",
    "CREW_high;120,-260,360;0,-40,90",
    "CREW_chase;-700,-10,250;0,-20,120",
    "CREW_passenger;5,35,120;5,-41,112",
    "CREW_gunner_front;520,260,210;20,95,145",
    "CREW_gunner_side;40,480,170;30,95,140",
    "CREW_gunner_rear;-480,320,250;20,95,145",
    "CREW_gunner_close;190,210,165;25,100,150"
) | Set-Content -Encoding ascii $views

$deadline = (Get-Date).AddMinutes($WaitMinutes)
while ($true) {
    $busy = Get-Process UnrealBuildTool*, ShaderCompileWorker* -ErrorAction SilentlyContinue
    $free = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB
    if (-not $busy -and $free -ge $MinFreeGB) { break }
    if ((Get-Date) -gt $deadline) { Write-Output ("SHOOT gave up waiting: {0:N1} GB free" -f $free); exit 2 }
    Start-Sleep -Seconds 10
}
New-Item -ItemType Directory -Force $shots | Out-Null
$started = Get-Date
$map = "/Game/Crew/Maps/CrewPreview?game=/Game/Bay/Review/BP_BayReviewGameMode.BP_BayReviewGameMode_C"
& $editor (Join-Path $project "WSPC2.uproject") $map -game -RenderOffscreen -windowed -ResX=1280 -ResY=720 -unattended -nosound `
    "-WSPC2Views=$($views -replace '\\','/')" "-abslog=$($log -replace '\\','/')" | Out-Null
$code = $LASTEXITCODE
$moved = 0
Get-ChildItem $captures -Filter "*_CREW_*.png" -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $started } | ForEach-Object {
    if ($_.Name -match '_warmup\.png$') { Remove-Item $_.FullName -Confirm:$false; return }
    Move-Item $_.FullName (Join-Path $shots ("{0}_{1}" -f $Tag, $_.Name)) -Force; $moved++
}
Write-Output ("SHOOT exit {0} after {1:N0} s, {2} pictures -> {3}" -f $code, ((Get-Date) - $started).TotalSeconds, $moved, $shots)
