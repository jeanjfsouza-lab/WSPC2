"""Lists the material slots, triangle counts and Nanite state of the patrol car's meshes (commandlet).

  UnrealEditor-Cmd.exe D:/Github/WSPC2/WSPC2.uproject -run=pythonscript -script="D:/Github/WSPC2/Tools/inspect_patrol_meshes.py"

Reads the City Sample vehicle13_Car meshes. Writes nothing; logs lines starting with PATROLMESH.
"""
import unreal

ROOT = "/Game/CitySampleVehicles/vehicle13_Car/Mesh/"
MESHES = ["SM_vehCar_vehicle13_No_Wheel", "SM_Wheel_Front_L_vehCar_vehicle13", "SM_Wheel_Rear_L_vehCar_vehicle13"]

for name in MESHES:
    mesh = unreal.EditorAssetLibrary.load_asset(ROOT + name)
    if not mesh:
        unreal.log("PATROLMESH missing %s" % name)
        continue
    b = mesh.get_bounds()
    nanite = mesh.get_editor_property("nanite_settings")
    unreal.log("PATROLMESH %s: bounds origin (%.1f, %.1f, %.1f) extent (%.1f, %.1f, %.1f), %d LODs, LOD0 %d triangles, nanite %s"
               % (name, b.origin.x, b.origin.y, b.origin.z, b.box_extent.x, b.box_extent.y, b.box_extent.z,
                  mesh.get_num_lods(), mesh.get_num_triangles(0), nanite.get_editor_property("enabled")))
    for index, slot in enumerate(mesh.static_materials):
        material = slot.material_interface.get_name() if slot.material_interface else None
        unreal.log("PATROLMESH   slot %d %s -> %s" % (index, slot.material_slot_name, material))
