# WSPC2 Scenery Asset Pipeline (`Tools/scenery/`)

End-to-end Blender 5.2 + Unreal Engine 5.8 pipeline that generates parametric landmarks and intermodal rail cars, normalizes external Sketchfab scenery models, imports them into `/Game/Scenery/Imported/`, dresses them with Quixel Megascans / project PBR material instances, builds the standalone `L_SceneryShowcase` verification level, and exports `bay_scenery_catalog.json` for optional integration into `Tools/bay/`.

## Git & Runtime Rules

- **Untracked / Optional:** `/Game/Scenery/Imported/` (`Content/Scenery/Imported/`) and `ASSETS TO USE/` are listed in `.gitignore`. Keep them optional at runtime or during Bay map builds — always check `unreal.EditorAssetLibrary.does_asset_exist(path)` with a procedural/native fallback instead of hard-requiring imported assets.
- **Nanite & RTX 3070 budget:** All **41 StaticMeshes** (20 base meshes + 16 suburban house variants + 5 intermodal well-car variants) have Nanite enabled (`nanite=True`), Z=0 base grounding, metric UVs, and <= 1024 px clamped GLB textures.
- **Agent Board Lock:** Always acquire the `unreal-editor` lock via `agent-board` before running any `UnrealEditor-Cmd.exe` step.

## Pipeline Commands (in Order)

Run with the Unreal Editor closed:

1. **Generate Nuclear Power Plant (`ASSETS TO USE/02_Cenario_Preparados/02_Usina_Nuclear/`):**
   ```powershell
   blender -b --factory-startup --python Tools/scenery/build_nuclear_plant.py
   ```
   Outputs `SM_Nuclear_CoolingTower.glb` (92 m shell, 36 V/X raker pairs), `SM_Nuclear_ReactorDome.glb` (PWR dome, 24 buttresses, steam pipes), and `SM_Nuclear_TurbineHall.glb` (turbine hall + 3 HV transformer bays).

2. **Generate US Standard-Gauge Intermodal Rail Cars (`ASSETS TO USE/02_Cenario_Preparados/06_Ferrovia_Vagoes/`):**
   ```powershell
   blender -b --factory-startup --python Tools/scenery/build_rail_cars.py
   ```
   Outputs `SM_Rail_WellCar_Single.glb`, `SM_Rail_WellCar_Double.glb` (1.435 m gauge, 0.88 m AAR coupler height, `+X` forward matching `Rail_EMD_GP7`, 17.4 m consist pitch), and normalized `SM_Rail_TankCar_Graffiti.glb`.

3. **Normalize Approved Sketchfab Scenery & Build Manifest (`ASSETS TO USE/02_Cenario_Preparados/manifest.json`):**
   ```powershell
   blender -b --factory-startup --python Tools/scenery/prepare_scenery_assets.py
   ```
   Normalizes the 14 retained Sketchfab assets including `SM_Port_STSCrane.glb` (reused `crane_harbour.glb` rescaled to 46 m tall with boom along `+X`, 4 m metric box UVs, 6 semantic slots) and `SM_Suburb_HouseD_Victorian.glb` (decimated cleanly to 68,000 tris).

4. **Import into UE 5.8, Build 26 MaterialInstances & Generate 21 Mesh Variants (`/Game/Scenery/Imported/`):**
   ```powershell
   & "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" WSPC2.uproject -run=pythonscript -script=Tools/scenery/import_and_dress_scenery.py -unattended -nop4 -nosplash -nosound -nullrhi
   ```
   Imports all 20 base meshes, builds **26 custom `MI_WSPC2_*` `MaterialInstanceConstant` assets**, dresses the Nuclear Plant and Port STS Crane, and creates **16 Suburban House variants** (`Var1..Var4` across `HouseA/B/C/D_Victorian`) and **5 Intermodal Well-Car livery variants**.

5. **Build Standalone Lumen/Nanite Showcase Map (`L_SceneryShowcase` + `views.txt`):**
   ```powershell
   & "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" WSPC2.uproject -ExecutePythonScript="Tools/scenery/build_showcase_map.py" -unattended -RenderOffscreen -nosplash -nosound
   ```

6. **Capture Automated 1280×720 Showcase Screenshots (`Saved/SceneryShowcase/shots/`):**
   ```powershell
   & "C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" WSPC2.uproject "/Game/Scenery/Imported/Maps/L_SceneryShowcase?game=/Game/Bay/Review/BP_BayReviewGameMode.BP_BayReviewGameMode_C" -game -RenderOffscreen -windowed -ResX=1280 -ResY=720 -unattended -nosound -WSPC2Views=D:/Github/WSPC2/Saved/SceneryShowcase/views.txt
   ```
   Last verified run (Pass 2): 10/10 shots captured cleanly at **115.3–126.1 fps** with Lumen + Nanite enabled.

## Material Architecture & Resolved UE 5.8 Shader Notes

Two material pitfalls identified during Pass-1 visual inspection are solved in `build_material_library()` (`Tools/scenery/import_and_dress_scenery.py`):

- **`M_MS_Srf` without packed `MetallicRoughnessTexture`:** `/Game/Fab/Materials/Standard/M_MS_Srf` expects a packed ARM/MetallicRoughness map; wiring isolated Albedo/Normal textures causes black or mirror-metallic walls under Lumen. All concrete, metal cladding, pipe steel, crane steel, shipping containers, and stucco facades now inherit from parent shaders with valid baked roughness/ARD maps:
  - `/Game/OvergrownFactoryENV/Material/MI_ConcreteGrunge` (`BaseLayer_Tiling=0.35`, `BottomDirtColor`)
  - `/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Wall_Facade_Concrete_New_01/MI_Ind_War_Wall_Facade_Concrete_New_01_A`
  - `/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Roof_Painted_01/MI_Ind_War_Roof_Painted_01`
  - `/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Sheet_Metal_Rusty_01/MI_Ind_War_Sheet_Metal_Rusty_01_A` & `_B`
  - `/Game/Downtown_West/Materials/Buildings_Shared/MI_Building_Stucco`, `MI_Building_Stucco_White`, `MI_Building_Plaster_*`, `MI_Building_Bricks_*`, `MI_Trim_Wood_Metal_White`, `MI_Building_Wood_Trim_*`
- **Glossy `CityPark` Roof Tiles:** Stock `CityPark` `MI_RoofTile*` instances default to `Roughness=0.0` (and some `Metallic=0.3`), producing wet plastic highlights. `MI_WSPC2_Roof_*` child instances explicitly override `Metallic=0.0`, `Roughness=0.86–0.90`, and `spec=0.20–0.25`.

## Consuming `bay_scenery_catalog.json` in `Tools/bay/`

`Tools/scenery/bay_scenery_catalog.json` stores exact UE object paths, triangle counts, Nanite state, centimetre/metre bounding dimensions, and Bay district role mappings for all **41 StaticMeshes** and **26 active MaterialInstances**.

Example optional-load helper for `Tools/bay/` scripts:

```python
import json
from pathlib import Path
import unreal

def load_optional_scenery_catalog():
    catalog_path = Path(__file__).resolve().parents[1] / "scenery" / "bay_scenery_catalog.json"
    if not catalog_path.exists():
        return {}
    return json.loads(catalog_path.read_text(encoding="utf-8"))

def resolve_optional_mesh(asset_path: str, fallback_path: str | None = None):
    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        return asset_path
    if fallback_path and unreal.EditorAssetLibrary.does_asset_exist(fallback_path):
        return fallback_path
    return None
```
