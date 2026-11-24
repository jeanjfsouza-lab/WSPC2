<#
Optional helper: filters a Sonniss #GameAudioGDC bundle (downloaded by hand) down to vehicle sounds.

Nothing is downloaded here: the bundles are 7+ GB and their terms allow use inside games but no redistribution
(and no AI/ML training), so they never enter the public repository. Download the ZIPs yourself from
  https://gdc.sonniss.com/            (current GDC bundle)
  https://sonniss.com/gameaudiogdc/   (archive of earlier bundles)
then run:
  powershell -File Tools/audio/pipeline/fetch_sonniss_optional.ps1 -ZipFolder "D:\Downloads\Sonniss"

Inputs:  the folder holding the bundle ZIPs
Outputs: Saved/Audio/Pipeline/raw_sfx/sonniss/<zip name>/... only for entries whose name contains one of the
         keywords below. Anything made from them must be imported under /Game/Audio/Vehicles/ThirdParty/
         (git-ignored) and loaded at runtime with a fallback.
#>
param(
    [Parameter(Mandatory = $true)][string]$ZipFolder,
    [string[]]$Keywords = @('car', 'crash', 'metal', 'glass', 'scrape', 'tire', 'tyre', 'skid', 'engine', 'diesel', 'horn', 'siren')
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$target = Join-Path $root 'Saved\Audio\Pipeline\raw_sfx\sonniss'
New-Item -ItemType Directory -Force -Path $target | Out-Null
$pattern = '(' + (($Keywords | ForEach-Object { [regex]::Escape($_) }) -join '|') + ')'

$total = 0
foreach ($zipPath in Get-ChildItem -LiteralPath $ZipFolder -Filter '*.zip') {
    $zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath.FullName)
    try {
        foreach ($entry in $zip.Entries) {
            if ($entry.Name -and $entry.Name -match $pattern -and $entry.Name -match '\.(wav|flac|ogg)$') {
                $out = Join-Path (Join-Path $target $zipPath.BaseName) $entry.FullName
                New-Item -ItemType Directory -Force -Path (Split-Path -Parent $out) | Out-Null
                [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $out, $true)
                $total++
            }
        }
    }
    finally { $zip.Dispose() }
}
Write-Host "Extracted $total files matching '$pattern' into $target"
