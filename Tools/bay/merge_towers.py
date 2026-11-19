"""Merges the tall City Sample buildings the Bay city's downtown uses into Nanite static meshes (full editor).

  UnrealEditor-Cmd.exe D:/Github/WSPC2/WSPC2.uproject -ExecutePythonScript="D:/Github/WSPC2/Tools/bay/merge_towers.py" -unattended -RenderOffscreen -nosplash -nosound

or through the launcher, which waits for memory:  .\\Tools\\bay\\build.ps1 -Script merge_towers.py

A City Sample building is a blueprint of hundreds to thousands of module pieces; placed as it is, a downtown
would be millions of instances. Each building is merged into a few static meshes ("parts") of at most 40
materials each, because Nanite builds at most 64 sections per mesh (see the vault note on merged buildings).

Reads   Saved/City/buildings.json (measured City Sample blueprints, from Tools/city/measure_buildings.py)
        environment variable BAY_TOWERS: optional comma list of unit names, to merge only those
Writes  /Game/Bay/Buildings/SM_<unit>_P<n> and Saved/Bay/tower_units.json (bounds of each merged unit in
        metres; the file is updated after every unit, so an interrupted run keeps what it finished)
Logs    lines starting with TOWERS. Units already in tower_units.json with their meshes on disk are skipped.
"""
import json
import os

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
SOURCE = os.path.join(PROJECT, "Saved", "City", "buildings.json")
OUT_JSON = os.path.join(PROJECT, "Saved", "Bay", "tower_units.json")
FOLDER = "/Game/Bay/Buildings"
MAX_MATERIALS_PER_PART = 40

# Towers of 75 to 290 m with a footprint a downtown lot can take, lightest to merge first.
UNITS = [
    "BPP_SFB_Dome_A1_N1",                       # 77 m, 43 x 48
    "BPP_Bldg_Hero_Mid_NYG_Triangle_B01_N1",    # 136 m, 36 x 50
    "BPP_SFB_Ref_N1",                           # 103 m, 88 x 119
    "BPP_SFD_RoundSplitTower_N1",               # 127 m, 45 x 93
    "BPP_Bldg_Hero_SFB_N1",                     # 120 m, 104 x 113
    "BPP_CHF_Ref_A1_N1",                        # 165 m, 28 x 29
    "BPP_CHC_Ref_A1_N1",                        # 127 m, 43 x 43
    "BPP_CHB_Ref_A1_N1",                        # 120 m, 36 x 27
    "BPP_CHE_Ref_A1_N1",                        # 138 m, 59 x 44
    "BPP_NYG_Ref_N1",                           # 269 m, 80 x 56
    "BPP_SFD_Ref_N1",                           # 257 m, 74 x 65
    "BPP_CHA_Ref_N1",                           # 136 m, 39 x 44
    "BPP_Bldg_Hero_Tower_CHE_B01_N1",           # 286 m, 63 x 69
    "BPP_Bldg_Hero_CHH_N1",                     # 128 m, 52 x 65
]

assets = unreal.EditorAssetLibrary


def log(text):
    unreal.log("TOWERS " + text)


def units():
    with open(SOURCE) as f:
        raw = json.load(f)
    groups = {}
    for e in raw:
        if e["instances"] == 0:
            continue
        key = e["name"].replace("_Level01", "").replace("A1l_", "A1_")
        groups.setdefault(key, []).append(e)
    wanted = [n.strip() for n in os.environ.get("BAY_TOWERS", "").split(",") if n.strip()] or UNITS
    out = []
    for key in wanted:
        if key not in groups:
            log("unknown unit %s" % key)
            continue
        parts = groups[key]
        out.append({"name": key, "blueprints": [p["blueprint"] for p in parts],
                    "pieces": sum(p["instances"] for p in parts)})
    return out


def material_keys(component):
    return {(m.get_path_name() if m else "None") for m in (component.get_material(i) for i in range(component.get_num_materials()))}


def parts_of(components):
    """Groups components so each group's merged mesh stays within Nanite's section limit."""
    keyed = sorted(((sorted(material_keys(c)), c) for c in components), key=lambda kc: kc[0])
    groups, current, mats = [], [], set()
    for keys, c in keyed:
        if current and len(mats | set(keys)) > MAX_MATERIALS_PER_PART:
            groups.append(current)
            current, mats = [], set()
        current.append(c)
        mats |= set(keys)
    if current:
        groups.append(current)
    return groups


def main():
    done = []
    if os.path.exists(OUT_JSON):
        with open(OUT_JSON) as f:
            done = json.load(f)
    have = {u["name"] for u in done if all(assets.does_asset_exist(m) for m in u["meshes"])}
    done = [u for u in done if u["name"] in have]
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    levels.new_level("/Temp/BayMergeScratch")
    for u in units():
        if u["name"] in have:
            log("already merged: %s" % u["name"])
            continue
        spawned = []
        for bp in u["blueprints"]:
            cls = assets.load_blueprint_class(bp)
            actor = actors.spawn_actor_from_class(cls, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0)) if cls else None
            if actor:
                spawned.append(actor)
        components = []
        for actor in spawned:
            components += list(actor.get_components_by_class(unreal.StaticMeshComponent))
        meshes = []
        for k, group in enumerate(parts_of(components)):
            existing = "%s/SM_%s_P%d" % (FOLDER, u["name"], k)
            if assets.does_asset_exist(existing):
                assets.delete_asset(existing)
            mesh = unreal.WSPC2CityTools.merge_components_to_static_mesh(group, "%s/%s_P%d" % (FOLDER, u["name"], k), True)
            if mesh:
                assets.save_loaded_asset(mesh)
                meshes.append(mesh)
        for actor in spawned:
            actors.destroy_actor(actor)
        if not meshes:
            log("FAILED %s" % u["name"])
            continue
        boxes = [m.get_bounding_box() for m in meshes]
        lo = [min(b.min.x for b in boxes), min(b.min.y for b in boxes), min(b.min.z for b in boxes)]
        hi = [max(b.max.x for b in boxes), max(b.max.y for b in boxes), max(b.max.z for b in boxes)]
        u["meshes"] = [m.get_path_name().split(".")[0] for m in meshes]
        u["sections"] = [m.get_num_sections(0) for m in meshes]
        u["nanite"] = [bool(m.get_editor_property("nanite_settings").enabled) for m in meshes]
        u["lo"] = [lo[0] / 100.0, -hi[1] / 100.0, lo[2] / 100.0]       # metres, y north
        u["hi"] = [hi[0] / 100.0, -lo[1] / 100.0, hi[2] / 100.0]
        u["ue_lo"] = [lo[0] / 100.0, lo[1] / 100.0, lo[2] / 100.0]      # metres, Unreal axes
        u["ue_hi"] = [hi[0] / 100.0, hi[1] / 100.0, hi[2] / 100.0]
        done.append(u)
        with open(OUT_JSON, "w") as f:
            json.dump(done, f, indent=1)
        log("merged %s: %.0f x %.0f x %.0f m, %d pieces in %d parts, sections %s" % (
            u["name"], u["hi"][0] - u["lo"][0], u["hi"][1] - u["lo"][1], u["hi"][2], u["pieces"], len(meshes), u["sections"]))
        unreal.SystemLibrary.collect_garbage()
    log("%d units in %s" % (len(done), OUT_JSON))


try:
    main()
    log("DONE")
except Exception as error:
    log("FAILED %r" % (error,))
    raise
finally:
    unreal.SystemLibrary.quit_editor()
