"""Brings the posed officers into Unreal, seats them in the game's patrol car and builds a small map to look at them.

  & "C:\\Program Files\\Epic Games\\UE_5.8\\Engine\\Binaries\\Win64\\UnrealEditor-Cmd.exe" "D:\\Github\\WSPC2\\WSPC2.uproject"
      /Game/VehicleTemplate/Maps/VehicleBasic -ExecutePythonScript="D:/Github/WSPC2/Tools/crew/build_crew_preview.py"
      -unattended -RenderOffscreen -nosplash -nosound
  then the pictures:  powershell -File Tools/crew/shoot_crew_preview.ps1

Input:  Saved/Crew/SM_Crew_<Role>.fbx and crew_<role>.json (Tools/crew/pose_crew.py, for each role made),
        Saved/Crew/crew_poses.json (pose_crew.py -- --keys: the key poses the game blends), Saved/Crew/export/parts.json
        (Tools/crew/export_crew_parts.py); /Game/CitySampleCrowd (optional Epic pack) and
        /Game/CitySampleVehicles/vehicle13_Car (the patrol body)
Output: /Game/Crew/Meshes/SM_Crew_Driver, SM_Crew_Gunner   each officer, posed, one static mesh in the car's own space
        /Game/Crew/Materials/MI_Crew_Shirt, MI_Crew_Trousers   the crowd's shirt and slacks in police navy
        /Game/Crew/DA_Crew_Patrol                    UWSPC2CrewProfile: each officer's body, face, hair and head
                                                     transform; the Patrol preset (WSPC2VehicleProfile.cpp) points at
                                                     it and AWSPC2SportsCar seats them in the car at run time
        /Game/Crew/Maps/CrewPreview                  the patrol body at the origin with the officers, their faces and
                                                     hair, a floor, sun and sky; game mode: the Bay's review mode
        log lines tagged CREW
The face and the hair cards are placed as they are (the face a skeletal mesh in its rest pose), carried to the seat by
crew_<role>.json's transform: in a fixed pose the face only moves with the head.
Everything under /Game/Crew is derived from Epic's crowd pack: git-ignored, and the game runs without it (empty seats).
The crew profile needs the game module built with UWSPC2CrewProfile; with an older module it is skipped (logged).
"""
import json
import os

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
CREW = os.path.join(PROJECT, "Saved", "Crew")
FOLDER = "/Game/Crew"
MAP = FOLDER + "/Maps/CrewPreview"
CREW_PROFILE = FOLDER + "/DA_Crew_Patrol"     # the Patrol preset's CrewProfile (Source/WSPC2/WSPC2VehicleProfile.cpp)
CROWD = "/Game/CitySampleCrowd/Character"
CARDS = CROWD + "/Shared/Materials/MetaHuman/HairCards/"
ROLES = {   # each officer's own face and hair (cards mesh and its material)
    "driver": (CROWD + "/Male/m_002/Face/m_002_nrw_FaceMesh",
               CROWD + "/Male/m_002/Hair/Hair/Hair_S_CurlyFade_Cards/Hair_S_CurlyFade_CardsMesh_Group0_LOD0", CARDS + "MI_Hair_Cards_M_CurlyFade"),
    "gunner": (CROWD + "/Male/m_003/Face/m_003_nrw_FaceMesh",
               CROWD + "/Male/m_003/Hair/Hair/Hair_M_SideSweptFringe_CardsMesh_Group0_LOD0", CARDS + "MI_Hair_Cards_M_SideSweptFringe"),
}
GUN_MATERIAL = "/Game/Bay/Materials/MI_Bay_Railing"     # dark gunmetal paint, for the placeholder pistol
CAR = "/Game/CitySampleVehicles/vehicle13_Car"
CAR_PARTS = [CAR + "/WSPC2/SM_Body_NoFrontBrakes", CAR + "/Mesh/SM_All_Trans_vehCar_vehicle13", CAR + "/WSPC2/SM_Brake_FL",
             CAR + "/WSPC2/SM_Brake_FR"] + [CAR + "/Mesh/SM_Wheel_%s_vehCar_vehicle13" % w for w in ("Front_L", "Front_R", "Rear_L", "Rear_R")]
NAVY = {"MI_Crew_Shirt": ("top", (0.018, 0.026, 0.060)), "MI_Crew_Trousers": ("bottom", (0.012, 0.016, 0.036))}
REVIEW_MODE = "/Game/Bay/Review/BP_BayReviewGameMode"
FLOOR_MATERIAL = "/Game/Bay/Materials/MI_Bay_AsphaltMS"
EXPOSURE_EV = (8.0, 10.5)          # as the Bay (build_bay.py EXPOSURE_MIN_EV, EXPOSURE_MAX_EV)

assets = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary


def log(text):
    unreal.log("CREW " + text)


def import_officer(role):
    name = "SM_Crew_" + role.capitalize()
    task = unreal.AssetImportTask()
    task.filename = os.path.join(CREW, name + ".fbx")
    task.destination_path = FOLDER + "/Meshes"
    task.destination_name = name
    task.automated = True
    task.replace_existing = True
    task.save = True
    ui = unreal.FbxImportUI()
    ui.set_editor_property("import_mesh", True)
    ui.set_editor_property("import_as_skeletal", False)
    ui.set_editor_property("import_materials", False)
    ui.set_editor_property("import_textures", False)
    ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
    data = ui.get_editor_property("static_mesh_import_data")
    data.set_editor_property("combine_meshes", True)
    data.set_editor_property("generate_lightmap_u_vs", False)
    data.set_editor_property("auto_generate_collision", False)
    task.options = ui
    tools.import_asset_tasks([task])
    mesh = assets.load_asset(FOLDER + "/Meshes/" + name)
    if not mesh:
        raise RuntimeError("the %s did not import" % role)
    return mesh


def uniform(parts):
    """The crowd's shirt and slacks as police navy (their own material, a child instance with the main colour set)."""
    out = {}
    for name, (part, colour) in NAVY.items():
        parent = assets.load_asset(parts[part]["slots"][0]["material"]["path"].split(".")[0])
        path = "%s/Materials/%s" % (FOLDER, name)
        mi = assets.load_asset(path) if assets.does_asset_exist(path) else \
            tools.create_asset(name, FOLDER + "/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(mi, parent)
        mel.clear_all_material_instance_parameters(mi)          # nothing left over from an earlier run
        # (A: the body of the garment, B: its second colour. Below the elbows the sleeves look pale in the pictures:
        # that is the sun through the side window on navy cloth, the torso being in the roof's shade)
        for param in ("A_CrowdColor_main", "B_CrowdColor_main"):
            mel.set_material_instance_vector_parameter_value(mi, param, unreal.LinearColor(colour[0], colour[1], colour[2], 1.0))
        mel.update_material_instance(mi)
        assets.save_asset(path, only_if_is_dirty=False)
        out[parent.get_name()] = mi
    return out


def dress(mesh, parts, navy):
    by_name = {"MI_Crew_Gun": assets.load_asset(GUN_MATERIAL)}
    for part in ("body", "top", "bottom", "shoes"):
        for slot in parts[part]["slots"]:
            path = slot["material"]["path"]
            if path:
                material = assets.load_asset(path.split(".")[0])
                by_name[material.get_name()] = navy.get(material.get_name(), material)
    dressed = []
    for i, slot in enumerate(mesh.get_editor_property("static_materials")):
        name = str(slot.get_editor_property("material_slot_name"))
        material = by_name.get(name) or by_name.get(name.split("_skinned")[0])
        if material is None:
            for key, value in by_name.items():
                if name.startswith(key) or key.startswith(name):
                    material = value
        if material:
            mesh.set_material(i, material)
            dressed.append("%s -> %s" % (name, material.get_name()))
        else:
            dressed.append("%s -> NOTHING" % name)
    assets.save_loaded_asset(mesh)
    log("%s's slots: %s" % (mesh.get_name(), "; ".join(dressed)))


def head_transform(role):
    with open(os.path.join(CREW, "crew_%s.json" % role)) as f:
        r = json.load(f)
    x = unreal.Vector(*r["x_axis"])
    z = unreal.Vector(*r["z_axis"])
    rot = unreal.MathLibrary.make_rot_from_xz(x, z)
    return unreal.Transform(unreal.Vector(*r["origin_cm"]), rot, unreal.Vector(*r["scale"]))


def soft(path):
    """The soft object path of an asset ("/Game/A/B"); an empty one when the asset is not there."""
    asset = assets.load_asset(path)
    if not asset:
        log("MISSING %s (left empty in the crew profile)" % path)
        return unreal.SoftObjectPath()
    return unreal.SystemLibrary.get_soft_object_path(asset)


def transform(record):
    """[x, y, z, qx, qy, qz, qw, scale] (crew_poses.json) as a Transform, the rotation kept as a quaternion."""
    t = unreal.Transform()
    t.set_editor_property("translation", unreal.Vector(record[0], record[1], record[2]))
    t.set_editor_property("rotation", unreal.Quat(record[3], record[4], record[5], record[6]))
    t.set_editor_property("scale3d", unreal.Vector(record[7], record[7], record[7]))
    return t


def write_crew_profile(officers, parts, navy):
    """The data the game reads to seat and pose the officers in the patrol car (UWSPC2CrewProfile,
    WSPC2VehicleProfile.h): the crowd's skeletal body and outfit, face and hair, and every key pose of
    Saved/Crew/crew_poses.json (Tools/crew/pose_crew.py --keys), plus the navy uniform's material swaps."""
    cls = getattr(unreal, "WSPC2CrewProfile", None)
    if cls is None:
        log("SKIPPED %s: the game module has no UWSPC2CrewProfile yet (build it, then run this again)" % CREW_PROFILE)
        return
    poses_path = os.path.join(CREW, "crew_poses.json")
    keys = json.load(open(poses_path)) if os.path.exists(poses_path) else None
    if keys is None:
        log("NO KEY POSES: %s is missing (run pose_crew.py -- --keys); the officers will not be drawn" % poses_path)
    if assets.does_asset_exist(CREW_PROFILE):
        profile = assets.load_asset(CREW_PROFILE)
    else:
        factory = unreal.DataAssetFactory()
        factory.set_editor_property("data_asset_class", cls)
        profile = tools.create_asset(CREW_PROFILE.rsplit("/", 1)[1], FOLDER, cls, factory)
    body_parts = [soft(parts[p]["asset"]) for p in ("body", "top", "bottom", "shoes") if p in parts]
    members = []
    for role, officer in officers.items():
        face_path, hair_path, hair_material = ROLES[role]
        member = unreal.WSPC2CrewMember()
        member.set_editor_property("role", role.capitalize())
        member.set_editor_property("body_mesh", soft(officer.get_path_name()))
        member.set_editor_property("body_parts", body_parts)
        member.set_editor_property("face_mesh", soft(face_path))
        member.set_editor_property("hair_mesh", soft(hair_path))
        member.set_editor_property("hair_material", soft(hair_material))
        member.set_editor_property("head_transform", head_transform(role))
        if keys:
            member.set_editor_property("bones", [unreal.Name(b) for b in keys["bones"]])
            poses = []
            for key in keys.get(role, []):
                pose = unreal.WSPC2CrewPose()
                pose.set_editor_property("name", key["name"])
                pose.set_editor_property("param", float(key["param"]))
                pose.set_editor_property("moves", [transform(k) for k in key["k"]])
                if key.get("grip"):
                    pose.set_editor_property("grip", transform(key["grip"]))
                poses.append(pose)
            member.set_editor_property("poses", poses)
            log("%s: %d key poses of %d bones" % (role, len(poses), len(keys["bones"])))
        members.append(member)
    profile.set_editor_property("members", members)
    profile.set_editor_property("swap_from", [unreal.Name(name) for name in navy])
    profile.set_editor_property("swap_to", [unreal.SystemLibrary.get_soft_object_path(mi) for mi in navy.values()])
    assets.save_loaded_asset(profile)
    log("crew profile %s: %s; uniform swaps %s" % (CREW_PROFILE, ", ".join(role for role in officers), ", ".join(navy)))


def spawn(actors, cls, location=unreal.Vector(0, 0, 0), rotation=unreal.Rotator(0, 0, 0), label=None):
    a = actors.spawn_actor_from_class(cls, location, rotation)
    if label:
        a.set_actor_label(label)
    return a


def build_map(officers):
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    # (an existing map is emptied and filled again: deleting it and making a new one under the same name fails)
    if assets.does_asset_exist(MAP):
        if not levels.load_level(MAP):
            raise RuntimeError("could not load " + MAP)
        for actor in actors.get_all_level_actors():
            actors.destroy_actor(actor)
    elif not levels.new_level(MAP):
        raise RuntimeError("could not create " + MAP)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    mode = assets.load_blueprint_class(REVIEW_MODE)
    if mode:
        world.get_world_settings().set_editor_property("default_game_mode", mode)
    # sun, sky, fog, clouds, exposure: the Bay's own (Tools/bay/build_bay.py, build_light), movable lights
    sun = spawn(actors, unreal.DirectionalLight, location=unreal.Vector(0, 0, 3000), rotation=unreal.Rotator(roll=0.0, pitch=-48.0, yaw=-125.0), label="Sun")
    sun.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sun.light_component.set_editor_property("intensity", 3150.0)
    sun.light_component.set_editor_property("atmosphere_sun_light", True)
    sky = spawn(actors, unreal.SkyLight, location=unreal.Vector(0, 0, 2000), label="Sky")
    sky.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sky.light_component.set_editor_property("real_time_capture", True)
    sky.light_component.set_editor_property("intensity", 1.6)
    spawn(actors, unreal.SkyAtmosphere, label="Atmosphere")
    fog = spawn(actors, unreal.ExponentialHeightFog, location=unreal.Vector(0, 0, 500), label="Fog")
    fog.component.set_editor_property("fog_density", 0.0025)
    spawn(actors, unreal.VolumetricCloud, label="Clouds")
    ppv = spawn(actors, unreal.PostProcessVolume, label="Exposure")
    ppv.set_editor_property("unbound", True)
    settings = ppv.get_editor_property("settings")
    settings.set_editor_property("override_auto_exposure_min_brightness", True)
    settings.set_editor_property("auto_exposure_min_brightness", EXPOSURE_EV[0])
    settings.set_editor_property("override_auto_exposure_max_brightness", True)
    settings.set_editor_property("auto_exposure_max_brightness", EXPOSURE_EV[1])
    ppv.set_editor_property("settings", settings)
    floor = spawn(actors, unreal.StaticMeshActor, label="Floor")
    fc = floor.static_mesh_component
    fc.set_static_mesh(assets.load_asset("/Engine/BasicShapes/Plane"))
    floor.set_actor_scale3d(unreal.Vector(80.0, 80.0, 1.0))
    material = assets.load_asset(FLOOR_MATERIAL)
    if material:
        fc.set_material(0, material)
    # the patrol body and the officer, all in the car's own space at the origin
    for path in CAR_PARTS:
        mesh = assets.load_asset(path)
        if not mesh:
            log("MISSING car part " + path)
            continue
        a = spawn(actors, unreal.StaticMeshActor, label=path.rsplit("/", 1)[1])
        a.static_mesh_component.set_static_mesh(mesh)
    for role, officer in officers.items():
        label = "Crew_" + role.capitalize()
        body = spawn(actors, unreal.StaticMeshActor, label=label)
        body.static_mesh_component.set_static_mesh(officer)
        face_path, hair_path, hair_material = ROLES[role]
        t = head_transform(role)
        face = assets.load_asset(face_path)
        if face:
            fa = spawn(actors, unreal.SkeletalMeshActor, t.translation, t.rotation.rotator(), label=label + "_Face")
            fa.set_actor_scale3d(t.scale3d)
            fa.skeletal_mesh_component.set_skeletal_mesh_asset(face)
        hair = assets.load_asset(hair_path)
        if hair:
            ha = spawn(actors, unreal.StaticMeshActor, t.translation, t.rotation.rotator(), label=label + "_Hair")
            ha.set_actor_scale3d(t.scale3d)
            ha.static_mesh_component.set_static_mesh(hair)
            hm = assets.load_asset(hair_material)
            if hm:
                ha.static_mesh_component.set_material(0, hm)
        log("%s: face and hair at %s, %s, scale %s" % (role, t.translation, t.rotation.rotator(), t.scale3d))
    if not levels.save_current_level():
        raise RuntimeError("could not save " + MAP)
    log("saved %s with %d actors" % (MAP, len(actors.get_all_level_actors())))


def main():
    with open(os.path.join(CREW, "export", "parts.json")) as f:
        parts = json.load(f)
    officers = {role: import_officer(role) for role in ROLES if os.path.exists(os.path.join(CREW, "SM_Crew_%s.fbx" % role.capitalize()))}
    if assets.does_asset_exist(FOLDER + "/Materials/MI_Crew_Sleeve"):    # a try of 2026-11-19, no longer used
        assets.delete_asset(FOLDER + "/Materials/MI_Crew_Sleeve")
    navy = uniform(parts)
    for role, officer in officers.items():
        dress(officer, parts, navy)
        b = officer.get_bounds()
        log("%s: bounds centre %s, half size %s (car space, cm)" % (role, b.origin, b.box_extent))
    write_crew_profile(officers, parts, navy)
    build_map(officers)
    log("DONE")


try:
    main()
finally:
    unreal.SystemLibrary.quit_editor()
