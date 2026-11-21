<#
Makes all the data of one or more sectors of the Bay city, in the right order, without Unreal: ground mesh,
buildings, gardens, the buildings set on the final ground, furniture, review cameras. Run it before
build.ps1 places the sector in the map.

  .\Tools\bay\make_sector.ps1 -Sectors "CS6,CS7"              (a new sector, or one to plan again from scratch)
  .\Tools\bay\make_sector.ps1 -Sectors "CS3,CS4" -KeepLots    (a built sector whose ground changed: same buildings)
  .\Tools\bay\make_sector.ps1 -Sectors "CS3" -KeepLots -NoSurface   (one of many made in a row: the landscape is
                                                               left for the last one, or for build_surface.py)
  .\Tools\bay\make_sector.ps1 -Check                          (no sector made: is every built sector still what
                                                               the road network gives? run after editing
                                                               network_edits.py, terrain_base.py or sectors.py;
                                                               all 50-odd built sectors take about half an hour)
  .\Tools\bay\make_sector.ps1 -Check -Sectors "CW5,CW6"       (the same for the named sectors only: the
                                                               neighbours of an edit)

Steps for each sector (see the scripts' own headers):
  sector_prep.py                          where the land ends
  sector_mesh.py (Blender)                ground mesh, blocks
  plan_lots.py            [not -KeepLots] buildings; in a district with gardens it also writes yards.json
  sector_mesh.py again    [if yards.json] the same ground with the gardens laid as lawn
  seat_lots.py            [if yards.json or -KeepLots]  the buildings set on the final ground
  preview_sector.py, plan_props.py, plan_views.py
Afterwards run build_surface.py once (this script does it at the end) and then build.ps1.

Inputs   Saved/Bay/network.json, terrain_base.npz and the unit lists; Tools/bay/sectors.py
Outputs  Saved/Bay/sectors/<sector>/*  (glb, ground.npz, blocks.json, lots.json, yards.json, props.json,
         views.txt, ground.png, lots.png) and the landscape data of build_surface.py; one line per step
One heavy job at a time: do not run this while Unreal is building or touring.
#>
param(
    [string]$Sectors = "",
    [switch]$KeepLots,
    [switch]$NoSurface,
    [switch]$Check
)

$project = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $project
$here = "Tools/bay"

function Mesh([string]$sector, [string]$extra) {
    $out = if ($extra) { blender -b --factory-startup --python "$here/sector_mesh.py" -- $sector $extra 2>&1 }
           else { blender -b --factory-startup --python "$here/sector_mesh.py" -- $sector 2>&1 }
    $out | ForEach-Object { "$_" } | Where-Object { $_ -match "^SECTOR \S+: (curb|ignoring)|^CHECK |Traceback|Error|folded" } |
        ForEach-Object { $_.Substring(0, [Math]::Min(320, $_.Length)) }
}

if ($Check) {
    $built = python -c "import sys; sys.path.insert(0, 'Tools/bay'); import sectors; print(' '.join(k for k, v in sectors.SECTORS.items() if v['status'] in ('built', 'done')))"
    $names = $built.Split(' ')
    if ($Sectors) { $names = $Sectors.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ } }
    $lines = foreach ($s in $names) { Mesh $s "--check" }
    $lines | Where-Object { $_ -notmatch "unchanged|same surface" }
    # warnings (a folded road polygon ignored) are printed but are not sectors
    $checks = @($lines | Where-Object { $_ -match "^CHECK " })
    $fine = @($checks | Where-Object { $_ -match "unchanged|same surface" })
    Write-Output ("MAKE check: {0} of {1} sectors match the network; the others are listed above and must be made again with -KeepLots and rebuilt" -f $fine.Count, $checks.Count)
    exit 0
}

if (-not $Sectors) { Write-Output "MAKE give -Sectors `"A,B`" or -Check"; exit 1 }
foreach ($s in $Sectors.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }) {
    python -P "$here/sector_prep.py" $s
    Mesh $s ""
    $hadYards = Test-Path "Saved/Bay/sectors/$s/yards.json"
    if (-not $KeepLots) { python -P "$here/plan_lots.py" $s }
    $yards = Test-Path "Saved/Bay/sectors/$s/yards.json"
    # the ground again when gardens came or went (a sector whose kind of district changed loses or gains them)
    if (($yards -or $hadYards) -and -not $KeepLots) { Mesh $s "" | Where-Object { $_ -notmatch "^SECTOR" } }
    if ($yards -or $hadYards -or $KeepLots) { python -P "$here/seat_lots.py" $s }
    python -P "$here/preview_sector.py" $s 3 | Out-Null
    python -P "$here/plan_props.py" $s
    python -P "$here/plan_views.py" $s | Select-Object -Last 1
}
if (-not $NoSurface) { python -P "$here/build_surface.py" 2>&1 | Select-Object -Last 1 }
Write-Output "MAKE done: $Sectors"
