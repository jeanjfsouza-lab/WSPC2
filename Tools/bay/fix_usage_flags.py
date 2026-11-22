"""Sets "Used with Instanced Static Meshes" and "Used with Nanite" on every project material the Bay draws with.

  .\\Tools\\bay\\build.ps1 -Script fix_usage_flags.py -Commandlet

A material without these flags is drawn with the engine's grey default material on an instanced mesh or a Nanite
mesh in the game (bay_views.log warns "missing usage flag"). build_bay.py sets them on every mesh it instances as it
builds (spawn_instanced); this pass does the same at once for the materials of meshes built earlier, so the whole map
is right without building every sector again. It reads the materials of every static mesh under FOLDERS and the
materials directly under MATERIAL_FOLDERS, and changes only base materials inside /Game (never the engine's).

Input:  the assets of the folders below
Output: the changed base materials, saved; one log line per material changed ("USAGE ...")
"""
import unreal

FOLDERS = ["/Game/Bay", "/Game/Construction_VOL1", "/Game/Scene_RoadsideConstruction", "/Game/Scenery/Imported",
           "/Game/CityMap/Buildings"]
MATERIAL_FOLDERS = ["/Game/Surfaces/Materials", "/Game/Bay/Materials"]
FLAGS = ("used_with_instanced_static_meshes", "used_with_nanite")

assets = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def log(text):
    unreal.log("USAGE " + text)


def main():
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    materials = []
    for folder in FOLDERS:
        if not assets.does_directory_exist(folder):
            continue
        for data in registry.get_assets_by_path(folder, recursive=True):
            if str(data.asset_class_path.asset_name) == "StaticMesh":
                mesh = data.get_asset()
                materials += [s.material_interface for s in mesh.static_materials if s.material_interface]
    for folder in MATERIAL_FOLDERS:
        if not assets.does_directory_exist(folder):
            continue
        for data in registry.get_assets_by_path(folder, recursive=True):
            if str(data.asset_class_path.asset_name) in ("Material", "MaterialInstanceConstant"):
                materials.append(data.get_asset())
    seen, changed = set(), 0
    for m in materials:
        base = m.get_base_material()
        if base is None:
            continue
        key = base.get_path_name()
        if key in seen or not key.startswith("/Game/"):
            continue
        seen.add(key)
        missing = [f for f in FLAGS if not base.get_editor_property(f)]
        if not missing:
            continue
        for f in missing:
            base.set_editor_property(f, True)
        mel.recompile_material(base)
        assets.save_loaded_asset(base)
        changed += 1
        log("%s: %s" % (key, ", ".join(missing)))
    log("DONE %d base materials checked, %d changed" % (len(seen), changed))


main()
