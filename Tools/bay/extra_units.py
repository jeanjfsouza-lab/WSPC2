"""Makes the buildings of the newer districts available to plan_lots.py: the warehouse kit and the suburban houses.

  .\\Tools\\bay\\build.ps1 -Script extra_units.py
  then  .\\Tools\\bay\\build.ps1 -Script unit_faces.py -Commandlet   (which side of each new model is its front)

Warehouses: imports Saved/Bay/industrial/Warehouses.glb (warehouse_kit.py) into /Game/Bay/Generated/Industrial,
turns Nanite on and gives each named slot its material (WAREHOUSE_SLOTS: the Scene_Warehouse pack's surfaces when the
pack is in the project, the Bay's own materials otherwise). These are original models and part of the repository.
Houses: the suburban and Victorian houses Tools/scenery imported into /Game/Scenery/Imported (bay_scenery_catalog.json,
"suburbs"). That folder is git-ignored (third-party models): a house that is not in the project is left out, and a
district that ends up with no models of its own builds with its fallback kind (plan_lots.py, DISTRICTS "fallback").

Every model becomes a unit as in Saved/CityMap/building_units.json: name, meshes, its bounds in metres (ue_lo/ue_hi in
the model's Unreal axes, lo/hi with y turned to the north) and its kind ("warehouse", "house", "victorian").

Input:  Saved/Bay/industrial/Warehouses.glb, warehouses.json; Tools/scenery/bay_scenery_catalog.json
Output: /Game/Bay/Generated/Industrial/*   the warehouse meshes
        Saved/Bay/extra_units.json         the units
"""
import json
import os

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
DATA = os.path.join(PROJECT, "Saved", "Bay")
FOLDER = "/Game/Bay/Generated/Industrial"
OUT = os.path.join(DATA, "extra_units.json")
CATALOG = os.path.join(PROJECT, "Tools", "scenery", "bay_scenery_catalog.json")
SW = "/Game/Scene_Warehouse/Assets/MS/Surfaces"
BAY = "/Game/Bay/Materials"
# slot -> materials to try, first found wins
WAREHOUSE_SLOTS = {
    "Wall": [SW + "/Ind_War_Sheet_Metal_Rusty_01/MI_Ind_War_Sheet_Metal_Rusty_01_A", BAY + "/MI_Bay_RoofSheet"],
    "Brick": [BAY + "/MI_Bay_BrickRed"],
    "Roof": [SW + "/Ind_War_Roof_Painted_01/MI_Ind_War_Roof_Painted_01", BAY + "/MI_Bay_RoofSheet"],
    "Door": [SW + "/Ind_War_Garage_Door_Metal_Worn_01/MI_Ind_War_Garage_Door_Metal_Worn_01", BAY + "/MI_Bay_Concrete"],
    "Concrete": [SW + "/Ind_War_Wall_Facade_Concrete_New_01/MI_Ind_War_Wall_Facade_Concrete_New_01_A", BAY + "/MI_Bay_Concrete"],
    "Glass": [BAY + "/MI_Bay_Glass"],
    "Trim": [BAY + "/MI_Bay_BridgeSteel", BAY + "/MI_Bay_Railing"],
}
# a second look for some models: the same mesh with the other rusty sheet (a duplicate asset, one more unit)
RUSTY_B = SW + "/Ind_War_Sheet_Metal_Rusty_01/MI_Ind_War_Sheet_Metal_Rusty_01_B"

assets = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()


def log(text):
    unreal.log("EXTRA " + text)


def first(paths):
    for p in paths:
        if assets.does_asset_exist(p):
            return assets.load_asset(p)
    return None


def unit(name, mesh_path, kind):
    mesh = assets.load_asset(mesh_path)
    box = mesh.get_bounding_box()
    lo = [box.min.x / 100.0, box.min.y / 100.0, box.min.z / 100.0]
    hi = [box.max.x / 100.0, box.max.y / 100.0, box.max.z / 100.0]
    return {"name": name, "kind": kind, "meshes": [mesh_path], "sections": [len(mesh.static_materials)],
            "ue_lo": lo, "ue_hi": hi, "lo": [lo[0], -hi[1], lo[2]], "hi": [hi[0], -lo[1], hi[2]], "blueprints": []}


def warehouses():
    glb = os.path.join(DATA, "industrial", "Warehouses.glb")
    if not os.path.exists(glb):
        log("no %s (run warehouse_kit.py)" % glb)
        return []
    if assets.does_directory_exist(FOLDER):
        assets.delete_directory(FOLDER)
    task = unreal.AssetImportTask()
    task.filename = glb
    task.destination_path = FOLDER
    task.automated = True
    task.replace_existing = True
    task.save = True
    tools.import_asset_tasks([task])
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.scan_paths_synchronous([FOLDER], True)
    mats = {slot: first(paths) for slot, paths in WAREHOUSE_SLOTS.items()}
    rusty_b = first([RUSTY_B])
    out = []
    for data in registry.get_assets_by_path(FOLDER, recursive=True):
        if str(data.asset_class_path.asset_name) != "StaticMesh":
            continue
        mesh = data.get_asset()
        name = str(data.asset_name)
        settings = mesh.get_editor_property("nanite_settings")
        settings.enabled = True
        mesh.set_editor_property("nanite_settings", settings)
        for index, slot in enumerate(mesh.static_materials):
            m = mats.get(str(slot.material_slot_name))
            if m:
                mesh.set_material(index, m)
        assets.save_loaded_asset(mesh)
        path = str(data.package_name)
        out.append(unit(name, path, "warehouse"))
        # a twin with the other rusty sheet on its walls, for the metal-clad ones
        if rusty_b and any(str(s.material_slot_name) == "Wall" for s in mesh.static_materials) and "Brick" not in name:
            twin_path = path + "_B"
            if assets.does_asset_exist(twin_path):
                assets.delete_asset(twin_path)
            twin = assets.duplicate_asset(path, twin_path)
            for index, slot in enumerate(twin.static_materials):
                if str(slot.material_slot_name) == "Wall":
                    twin.set_material(index, rusty_b)
            assets.save_loaded_asset(twin)
            out.append(unit(name + "_B", twin_path, "warehouse"))
    log("warehouses: %d units" % len(out))
    return out


def houses():
    if not os.path.exists(CATALOG):
        log("no scenery catalog: no houses")
        return []
    with open(CATALOG, encoding="utf-8") as f:
        catalog = json.load(f)
    out, missing = [], 0
    for item in catalog["categories"]["suburbs"]["assets"]:
        path = item["asset_path"]
        if not assets.does_asset_exist(path):
            missing += 1
            continue
        kind = "victorian" if "Victorian" in item["id"] else "house"
        out.append(unit(item["id"], path, kind))
    log("houses: %d units, %d not in the project" % (len(out), missing))
    return out


def main():
    units = warehouses() + houses()
    with open(OUT, "w") as f:
        json.dump(units, f, indent=1)
    for u in units:
        w, d, h = (u["ue_hi"][i] - u["ue_lo"][i] for i in range(3))
        log("%-52s %-9s %5.1f x %5.1f x %5.1f m" % (u["name"], u["kind"], w, d, h))
    log("DONE %d units -> %s" % (len(units), OUT))


main()
