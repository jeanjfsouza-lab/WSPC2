# WSPC2

Co-op police pursuit game (driver + gunner, simulation handling). Unreal Engine 5.8.4, C++, one runtime module in `Source/WSPC2`. Talk to the user in Brazilian Portuguese; write code, comments, logs and commits in English.

Project notes live in the Obsidian vault at `D:\Obsidian Valt\WSPC2`. Read `01 - Projeto/Estado Atual.md` first; update it and the day's note in `50 - Diário/` after relevant changes.

## Commands
- Build (editor closed): `& "C:\Program Files\Epic Games\UE_5.8\Engine\Build\BatchFiles\Build.bat" WSPC2Editor Win64 Development -Project="D:\Github\WSPC2\WSPC2.uproject" -WaitMutex`
- Measure handling: `.\Tools\testdrive.ps1` (add `-Override "Key=Value"` for one-off values, `-Trace` for detail)
- Unreal Python, commandlet: `UnrealEditor-Cmd.exe WSPC2.uproject -run=pythonscript -script="Tools/x.py"`
- Unreal Python, full editor: `UnrealEditor-Cmd.exe WSPC2.uproject -ExecutePythonScript="Tools/x.py" -unattended -RenderOffscreen -nosplash -nosound`
- Blender 5.2 is on the user PATH: `blender -b --factory-startup --python Tools/x.py -- <args>`
- Open the editor with `Abrir Editor.bat` (or `Abrir Editor com MCP.bat`), never bare.

## Rules
- Never `git add .`, `git add -A` or `git add Content`: ~22 GB of untracked asset packs sit outside `.gitignore`. Add files by name. Commit or push only when asked.
- Never edit `.uasset`/`.umap` as text. Never hand-write into `Binaries/`, `Intermediate/`, `DerivedDataCache/`.
- Git-ignored packs (`CitySample*`, `CrownVic`, ...) are optional: load at runtime with a fallback, never hard-require them.
- Handling values belong in `UWSPC2VehicleTuning` / `Config/DefaultGame.ini`, never hard-coded. Measure with `testdrive.ps1` before and after.
- Server-authoritative: clients ask through `Server` RPCs on `AWSPC2PlayerController`; visible state replicates with `OnRep_`.
- Maps are rebuilt from scratch by scripts in `Tools/`. Change the script, not only the map.
- New scripts start with a docstring: purpose, exact command, inputs, outputs.
- Target hardware is an RTX 3070 with 8 GB and 16 GB of RAM: use Nanite, instancing and light fallbacks for anything placed in bulk.
- Header changes with UCLASS/UPROPERTY/UFUNCTION need the editor closed and a full build.
- Log through `LogWSPC2`. Test hooks are command-line flags named `-WSPC2...`.
- The city is an original layout; no real brands, no layouts from existing games.

## Unreal MCP
`.mcp.json` points at the editor's built-in MCP server (`unreal-mcp`, `http://localhost:8000/mcp`). It only answers while the editor was started with `Abrir Editor com MCP.bat`. Use it to inspect and experiment; anything that must survive a map rebuild goes into the script in `Tools/`.

## Layout
- `Source/WSPC2` — game module (`AWSPC2SportsCar` is the patrol car despite the name)
- `Tools/city`, `Tools/citymap`, `Tools/testtrack` — map pipelines (Blender + Python + Unreal)
- `Config/DefaultGame.ini` — patrol car tuning
- `Saved/City`, `Saved/CityMap`, `Saved/TestTrack` — intermediate pipeline data
- `.claude/hooks` — guards that block edits to binary/generated files and bulk `git add`
