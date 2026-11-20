"""Batch-imports prepared vehicle & wreck GLBs from ASSETS TO USE/01_Preparados/ into
/Game/Vehicles/Imported/ (git-ignored) in Unreal Engine 5.8 using manifest.json.

Run with the editor closed:
  UnrealEditor-Cmd.exe WSPC2.uproject -run=pythonscript -script=Tools/vehicles/import_vehicles.py

Optional environment filters:
  WSPC2_VEHICLE_CATEGORY          Filter by category folder (e.g. 01_Police, 02_Playable, 03_Traffic)
  WSPC2_VEHICLE_IDS               Comma-separated list of vehicle IDs to import (e.g. Police_Civil_Sedan,Hero_BMW_E30_Free)
  WSPC2_VEHICLE_ALLOW_RESTRICTED  Set to 1 to allow importing prototype-only assets (Forza game-rips, CC-BY-ND, Non-Commercial)

Inputs:
  ASSETS TO USE/01_Preparados/manifest.json
  ASSETS TO USE/01_Preparados/<Category>/<Id>/*.glb

Outputs:
  /Game/Vehicles/Imported/<Category>/<Id>/*
"""
import json
import os
import unreal

PROJECT_DIR = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
PREP_ROOT = os.path.join(PROJECT_DIR, "ASSETS TO USE", "01_Preparados")
MANIFEST_PATH = os.path.join(PREP_ROOT, "manifest.json")

RESTRICTED_TOKENS = ("FORZA", "CC-BY-ND", "NON-COMMERCIAL", "GAME-RIP")
TRANSLUCENT_BLEND_MODES = {
    unreal.BlendMode.BLEND_TRANSLUCENT,
    unreal.BlendMode.BLEND_ALPHA_COMPOSITE,
    unreal.BlendMode.BLEND_ADDITIVE,
}


def is_restricted_license(license_str: str) -> bool:
    upper = (license_str or "").upper()
    return any(tok in upper for tok in RESTRICTED_TOKENS)


def material_is_translucent(mat_iface) -> bool:
    if not mat_iface:
        return False
    try:
        bm = mat_iface.get_blend_mode()
        if bm in TRANSLUCENT_BLEND_MODES:
            return True
    except Exception:
        pass
    try:
        base = mat_iface.get_base_material()
        if base and base.get_blend_mode() in TRANSLUCENT_BLEND_MODES:
            return True
    except Exception:
        pass
    mname = mat_iface.get_name().lower()
    return any(k in mname for k in ("glass", "window", "windshield", "vidro"))


def import_glb(src_file: str, dest_path: str):
    task = unreal.AssetImportTask()
    task.filename = src_file
    task.destination_path = dest_path
    task.automated = True
    task.replace_existing = True
    task.save = True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    unreal.log("WSPC2VEHIMPORT imported %s -> %s" % (os.path.basename(src_file), list(task.imported_object_paths)))


def main():
    if not os.path.exists(MANIFEST_PATH):
        unreal.log_error("WSPC2VEHIMPORT missing manifest: %s" % MANIFEST_PATH)
        return

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        entries = json.load(f)

    filter_cat = os.environ.get("WSPC2_VEHICLE_CATEGORY", "").strip()
    raw_ids = os.environ.get("WSPC2_VEHICLE_IDS", "").strip()
    filter_ids = {s.strip() for s in raw_ids.split(",") if s.strip()} if raw_ids else set()
    allow_restricted = os.environ.get("WSPC2_VEHICLE_ALLOW_RESTRICTED", "0").strip() == "1"

    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    sm_subsys = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)

    imported_dirs = set()
    skipped_restricted = []
    for item in entries:
        if item.get("error"):
            continue
        cat = item.get("category", "")
        vid = item.get("id", "")
        if filter_cat and cat != filter_cat:
            continue
        if filter_ids and vid not in filter_ids:
            continue
        if not allow_restricted and is_restricted_license(item.get("license", "")):
            skipped_restricted.append(vid)
            continue

        src_dir = os.path.join(PREP_ROOT, cat, vid)
        dest_dir = f"/Game/Vehicles/Imported/{cat}/{vid}"
        for fname in item.get("files", []):
            fpath = os.path.join(src_dir, fname)
            if os.path.exists(fpath):
                import_glb(fpath, dest_dir)
                imported_dirs.add(dest_dir)

    # Configure Nanite accurately from actual UE material BlendModes (never leave Nanite ON with translucent glass)
    for dest_dir in sorted(imported_dirs):
        for data in registry.get_assets_by_path(dest_dir, recursive=True):
            if str(data.asset_class_path.asset_name) == "StaticMesh":
                mesh = data.get_asset()
                if not mesh:
                    continue
                translucent_slots = []
                for idx, slot in enumerate(mesh.static_materials):
                    if material_is_translucent(slot.material_interface):
                        translucent_slots.append(f"{idx}:{slot.material_interface.get_name()}")
                settings = mesh.get_editor_property("nanite_settings")
                if translucent_slots and settings.enabled:
                    settings.enabled = False
                    if sm_subsys:
                        sm_subsys.set_nanite_settings(mesh, settings, apply_changes=True)
                    else:
                        mesh.set_editor_property("nanite_settings", settings)
                bounds = mesh.get_bounds()
                dims_cm = [round(bounds.box_extent.x * 2, 1), round(bounds.box_extent.y * 2, 1), round(bounds.box_extent.z * 2, 1)]
                tri_n = max(mesh.get_num_triangles(0), mesh.get_num_nanite_triangles())
                unreal.log(
                    "WSPC2VEHIMPORT verified %s tris=%d mats=%d nanite=%s dims_cm=%s translucent=%s"
                    % (
                        mesh.get_name(),
                        tri_n,
                        len(mesh.static_materials),
                        bool(mesh.get_editor_property("nanite_settings").enabled),
                        dims_cm,
                        translucent_slots,
                    )
                )
        unreal.EditorAssetLibrary.save_directory(dest_dir, only_if_is_dirty=False, recursive=True)

    if skipped_restricted:
        unreal.log(
            "WSPC2VEHIMPORT skipped %d restricted/prototype assets (set WSPC2_VEHICLE_ALLOW_RESTRICTED=1 to include): %s"
            % (len(skipped_restricted), ", ".join(skipped_restricted))
        )
    unreal.log("WSPC2VEHIMPORT complete (%d vehicle folders)." % len(imported_dirs))


if __name__ == "__main__":
    main()
