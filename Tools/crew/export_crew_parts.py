"""Exports the parts of the patrol crew (one City Sample crowd officer) and the patrol car's body to FBX, for Blender.

  & "C:\\Program Files\\Epic Games\\UE_5.8\\Engine\\Binaries\\Win64\\UnrealEditor-Cmd.exe" "D:\\Github\\WSPC2\\WSPC2.uproject"
      /Game/VehicleTemplate/Maps/VehicleBasic -ExecutePythonScript="D:/Github/WSPC2/Tools/crew/export_crew_parts.py"
      -unattended -RenderOffscreen -nosplash -nosound
  (the full editor, not a commandlet: the FBX exporter of a skeletal mesh needs a renderer and stops a commandlet
  on an assertion; a small map, so the editor does not load the whole first city)

Input:  /Game/CitySampleCrowd (optional, git-ignored Epic pack: body, outfit, head, hair cards),
        /Game/CitySampleVehicles/vehicle13_Car (the patrol body)
Output: Saved/Crew/export/<part>.fbx      one file per part (PARTS below), at the asset's own scale and axes
        Saved/Crew/export/parts.json      per part: asset path, material slot names and the material on each slot,
                                          and the vector and scalar parameters of those materials (to tint a uniform)
Next:   blender -b --factory-startup --python Tools/crew/pose_crew.py  (seats the officer, writes Saved/Crew/*.fbx)
"""
import json
import os

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
OUT = os.path.join(PROJECT, "Saved", "Crew", "export")
CROWD = "/Game/CitySampleCrowd/Character"
PARTS = {
    "body": CROWD + "/Male/NormalWeight/Meshes/m_tal_nrw_body",
    "top": CROWD + "/Male/NormalWeight/Meshes/m_tal_nrw_buttonDown",
    "bottom": CROWD + "/Male/NormalWeight/Meshes/m_tal_nrw_slacks_belt",
    "shoes": CROWD + "/Male/NormalWeight/Meshes/m_tal_nrw_oxfords",
    "car": "/Game/CitySampleVehicles/vehicle13_Car/WSPC2/SM_Body_NoFrontBrakes",
    "glass": "/Game/CitySampleVehicles/vehicle13_Car/Mesh/SM_All_Trans_vehCar_vehicle13",
}
# Parts that only follow the head, rigidly: not exported, only listed (their slots and materials). The FBX exporter
# stops the editor on the MetaHuman face mesh ("Array index out of bounds" in MeshMergeUtilities, 2026-11-19), and a
# face needs no deforming in a seated pose: it is placed in Unreal with the head bone's move (pose_crew.py writes it)
RIGID = {
    "face": CROWD + "/Male/m_002/Face/m_002_nrw_FaceMesh",
    "hair": CROWD + "/Male/m_002/Hair/Hair/Hair_S_CurlyFade_Cards/Hair_S_CurlyFade_CardsMesh_Group0_LOD0",
}


def log(text):
    unreal.log("CREW " + text)


def material_info(material):
    out = {"path": material.get_path_name() if material else None, "vectors": {}, "scalars": {}}
    if isinstance(material, unreal.MaterialInterface):
        lib = unreal.MaterialEditingLibrary
        try:
            for name in lib.get_vector_parameter_names(material):
                v = lib.get_material_instance_vector_parameter_value(material, name) if isinstance(material, unreal.MaterialInstance) else None
                out["vectors"][str(name)] = [round(v.r, 3), round(v.g, 3), round(v.b, 3)] if v else None
            for name in lib.get_scalar_parameter_names(material):
                s = lib.get_material_instance_scalar_parameter_value(material, name) if isinstance(material, unreal.MaterialInstance) else None
                out["scalars"][str(name)] = s
        except Exception as error:
            out["error"] = str(error)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    report = {}
    for part, path in RIGID.items():
        asset = unreal.EditorAssetLibrary.load_asset(path)
        if not asset:
            log("MISSING %s: %s" % (part, path))
            continue
        materials = asset.get_editor_property("materials" if isinstance(asset, unreal.SkeletalMesh) else "static_materials")
        report[part] = {"asset": path, "class": asset.get_class().get_name(), "rigid": True,
                        "slots": [{"slot": str(m.get_editor_property("material_slot_name")),
                                   "material": material_info(m.get_editor_property("material_interface"))} for m in materials]}
        log("%s: listed %s (rigid, follows the head), %d slots" % (part, path, len(materials)))
    for part, path in PARTS.items():
        asset = unreal.EditorAssetLibrary.load_asset(path)
        if not asset:
            log("MISSING %s: %s" % (part, path))
            continue
        task = unreal.AssetExportTask()
        task.object = asset
        task.filename = os.path.join(OUT, part + ".fbx")
        task.automated = True
        task.prompt = False
        task.replace_identical = True
        options = unreal.FbxExportOption()
        options.set_editor_property("collision", False)
        options.set_editor_property("level_of_detail", False)
        try:
            options.set_editor_property("export_morph_targets", False)
        except Exception:
            pass
        task.options = options
        ok = unreal.Exporter.run_asset_export_task(task)
        slots = []
        if isinstance(asset, unreal.SkeletalMesh):
            for m in asset.get_editor_property("materials"):
                mat = m.get_editor_property("material_interface")
                slots.append({"slot": str(m.get_editor_property("material_slot_name")), "material": material_info(mat)})
            skeleton = asset.get_editor_property("skeleton")
            skeleton = skeleton.get_path_name() if skeleton else None
        else:
            for m in asset.get_editor_property("static_materials"):
                mat = m.get_editor_property("material_interface")
                slots.append({"slot": str(m.get_editor_property("material_slot_name")), "material": material_info(mat)})
            skeleton = None
        report[part] = {"asset": path, "class": asset.get_class().get_name(), "skeleton": skeleton, "slots": slots,
                        "fbx": task.filename, "exported": bool(ok)}
        log("%s: %s %s, %d slots -> %s" % (part, "exported" if ok else "NOT EXPORTED", path, len(slots), task.filename))
    with open(os.path.join(OUT, "parts.json"), "w") as f:
        json.dump(report, f, indent=1)
    log("DONE")


try:
    main()
finally:
    unreal.SystemLibrary.quit_editor()
