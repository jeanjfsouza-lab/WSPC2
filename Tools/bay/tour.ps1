<#
Takes the review pictures of one sector of the Bay city: runs the game on WSPC2_Bay through the cameras of
Saved/Bay/sectors/<sector>/views.txt and moves the pictures into Saved/Bay/sectors/<sector>/shots.

  .\Tools\bay\tour.ps1 -Sector CC1 [-Tag roads] [-WaitMinutes 15]
  .\Tools\bay\tour.ps1 -Structure PCB [-Tag pass1]      (a bridge or tunnel: Saved/Bay/structures/<name>)
  .\Tools\bay\tour.ps1 -Structure TOL -Extra "-dpcvars=r.Lumen.DiffuseIndirect.Allow=0"   (try a console variable)

Inputs   Saved/Bay/sectors/<sector>/views.txt (Tools/bay/plan_views.py), the map /Game/Bay/Maps/WSPC2_Bay
Outputs  Saved/Bay/sectors/<sector>/shots/<tag>_NN_<camera>.png, Saved/Logs/bay_views.log,
         one line per camera with its frame rate (from the log's "Views:" lines)

The tour runs with /Game/Bay/Review/BP_BayReviewGameMode (build.ps1 -Stages review creates it), which spawns
no patrol car: the pictures do not depend on the state of the vehicle code, and the game starts faster.
Pass -WithCar to use the map's own game mode.
Another session may be running the game too (car tests): the script waits until nothing is compiling and
enough memory is free for one more instance.
#>
param(
    [string]$Sector = "",
    [string]$Structure = "",
    [string]$Tag = "shot",
    [int]$WaitMinutes = 15,
    [double]$MinFreeGB = 5.5,
    [switch]$WithCar,
    [string[]]$Extra = @()          # more arguments for the game, e.g. -Extra "-dpcvars=r.Lumen.DiffuseIndirect.Allow=0"
)

$project = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$editor = "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe"
# a bridge (-Structure) is reviewed like a sector: its cameras and pictures live in Saved/Bay/structures/<name>
$kind = "sectors"
if ($Structure) { $kind = "structures"; $Sector = $Structure }
if (-not $Sector) { Write-Output "TOUR needs -Sector <name> or -Structure <name>"; exit 1 }
$views = Join-Path $project "Saved\Bay\$kind\$Sector\views.txt"
$shots = Join-Path $project "Saved\Bay\$kind\$Sector\shots"
$log = Join-Path $project "Saved\Logs\bay_views.log"
$captures = Join-Path $project "Saved\Screenshots\Views"

if (-not (Test-Path $views)) { Write-Output "TOUR no views file: $views"; exit 1 }

$deadline = (Get-Date).AddMinutes($WaitMinutes)
while ($true) {
    $busy = Get-Process UnrealBuildTool*, ShaderCompileWorker* -ErrorAction SilentlyContinue
    $free = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB
    if (-not $busy -and $free -ge $MinFreeGB) { break }
    if ((Get-Date) -gt $deadline) {
        Write-Output ("TOUR gave up waiting: {0} build processes running, {1:N1} GB free" -f @($busy).Count, $free)
        exit 2
    }
    Start-Sleep -Seconds 10
}

New-Item -ItemType Directory -Force $shots | Out-Null
# The first camera of a tour is measured while the level is still settling (its game thread takes two or three
# times as long as on the others), and the larger the city grows the more that shows. A copy of the first
# camera goes ahead of the list as a warm-up; its picture and its figure are dropped.
$lines = @(Get-Content $views | Where-Object { $_.Trim() })
$run = Join-Path $project "Saved\Bay\$kind\$Sector\views_run.txt"
@("${Sector}_warmup;" + ($lines[0] -split ';', 2)[1]) + $lines | Set-Content -Encoding ascii $run
$views = $run
$started = Get-Date
$map = "/Game/Bay/Maps/WSPC2_Bay"
if (-not $WithCar) { $map += "?game=/Game/Bay/Review/BP_BayReviewGameMode.BP_BayReviewGameMode_C" }
& $editor (Join-Path $project "WSPC2.uproject") $map -game -RenderOffscreen -windowed `
    -ResX=1280 -ResY=720 -unattended -nosound "-WSPC2Views=$($views -replace '\\','/')" "-abslog=$($log -replace '\\','/')" @Extra | Out-Null
$code = $LASTEXITCODE

$moved = 0
Get-ChildItem $captures -Filter "*_${Sector}_*.png" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -ge $started } |
    ForEach-Object {
        if ($_.Name -match '_warmup\.png$') { Remove-Item $_.FullName -Confirm:$false; return }
        $name = $_.Name                                 # the warm-up took number 00: the others move back by one
        if ($name -match '^(\d+)_(.*)$') { $name = "{0:D2}_{1}" -f ([int]$Matches[1] - 1), $Matches[2] }
        Move-Item $_.FullName (Join-Path $shots ("{0}_{1}" -f $Tag, $name)) -Force; $moved++
    }

Write-Output ("TOUR {0}: exit {1} after {2:N0} s, {3} pictures -> {4}" -f $Sector, $code, ((Get-Date) - $started).TotalSeconds, $moved, $shots)
if (Test-Path $log) {
    Select-String -Path $log -Pattern "Views: .* fps" | Where-Object { $_.Line -notmatch "_warmup at" } |
        ForEach-Object { "TOUR " + ($_.Line -replace '^.*Views: ', '') }
    $fatal = Select-String -Path $log -Pattern "Fatal error|Ran out of memory" | Select-Object -First 2
    if ($fatal) { $fatal | ForEach-Object { "TOUR FAILED " + $_.Line } }
}
exit $code
