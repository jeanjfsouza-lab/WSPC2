"""Builds /Game/Bay/Maps/WSPC2_Bay, the Bay city, from the data in Saved/Bay (full editor with a GPU).

  UnrealEditor-Cmd.exe D:/Github/WSPC2/WSPC2.uproject -ExecutePythonScript="D:/Github/WSPC2/Tools/bay/build_bay.py" -unattended -RenderOffscreen -nosplash -nosound

Environment variables:
  BAY_STAGES    comma list of stages to (re)build; default "sectors,sea,light"
  BAY_SECTORS   comma list of sectors for the "sectors" stage; default: every sector with a mesh on disk

Stages. Each owns its outliner folders and only removes and rebuilds what is its own.
  materials creates /Game/Bay/Materials: Megascans scans (sidewalk, concrete, asphalt) on the Megascans master
            and M_BayWild, the sectors' natural ground: the landscape's layers blended by Saved/Bay/paint_map.png
            (imported as T_BayPaintMap; run build_surface.py first, and this stage again whenever the paint changes)
  ground    the landscape of the whole map from Saved/Bay/landscape.r16 and layer_*.raw (folder Bay/Ground);
            needs a GPU, takes a few minutes
  sectors   imports Saved/Bay/sectors/<name>/<name>_Ground.glb into /Game/Bay/Generated/<name>, gives each
            material slot its material and places the mesh (folder Bay/Sectors/<name>)
  buildings places the buildings of Saved/Bay/sectors/<name>/lots.json (folder Bay/Buildings/<name>)
  props     places street furniture and street trees of Saved/Bay/sectors/<name>/props.json
            (folder Bay/Props/<name>)
  structures imports the bridges, Saved/Bay/structures/<name>/<name>.glb (span_mesh.py), into
            /Game/Bay/Generated/<name>, places them with the lamps of their props.json (folder
            Bay/Structures/<name>); BAY_STRUCTURES limits which
  sea       a flat sheet of water at 0 m (folder Bay/Water); stands in until the landscape stage exists
  propassets imports the props the city makes itself (Saved/Bay/props, stop_sign.py) into /Game/Bay/Props; run it
            once before "props" when they change
  country   the trees and shrubs of the hills round the city, Saved/Bay/country/trees.json (plan_country.py),
            one instanced actor per mesh and 1 km tile (folder Bay/Country/<tile>)
  training  the layouts of the training ground, Saved/Bay/training/layouts.json (plan_training.py) and the two
            meshes of training_mesh.py: every operation's cones, ramp and targets as tagged actors, hidden until
            the layout director placed with them shows one (folder Bay/Training/<layout>)
  light     sun, sky, fog, exposure and the player start (folders Bay/Lighting, Bay/Start)
  review    creates /Game/Bay/Review/BP_BayReviewGameMode, the game mode without a car that tour.ps1 uses
  inspect   builds nothing: logs the parameters of the materials listed in INSPECT, to plan new instances

Reads   Saved/Bay/sectors/*/, Saved/Bay/start.json (optional: {"location": [x, y, z] in cm, "yaw": deg})
Writes  /Game/Bay/** and the map. Logs lines starting with BAY.
After a rebuild run Tools/surfaces/apply_surfaces.py so the surfaces get their grip back (it must list
/Game/Bay/Generated among its mesh folders).
"""
import json
import os

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
DATA = os.path.join(PROJECT, "Saved", "Bay")
MAP = "/Game/Bay/Maps/WSPC2_Bay"
GENERATED = "/Game/Bay/Generated"
GAME_MODE = "/Game/VehicleTemplate/Blueprints/BP_VehicleAdvGameMode"
WATER_MATERIAL = "/Game/Prop/kit_ocean/Material/MI_ocean"

# light: the sun is the first city's (3150 lux, calibrated for the City Sample buildings)
SKY_INTENSITY = 1.6
EXPOSURE_MIN_EV, EXPOSURE_MAX_EV = 8.0, 10.5

BAY_MATERIALS = "/Game/Bay/Materials"
MS = "/Game/Megascans/Surfaces"
GROUND_MASTER = "M_BayGround"
# Megascans scans as instances of the Bay ground master (ground_master() below). The Fab master M_MS_Srf was
# tried first and renders these scans black: it expects a packed metallic/roughness texture they do not have.
# name: (albedo, normal, metres per repeat, tint, (min roughness, max roughness)).
# The meshes' UVs repeat every 4 m, so tiling = 4 / metres.
MS_INSTANCES = {
    "MI_Bay_Sidewalk": (MS + "/Dirty_Sidewalk_2x2_M_00/ugxjcdpn_4K_Albedo", MS + "/Dirty_Sidewalk_2x2_M_00/ugxjcdpn_4K_Normal",
                        2.0, (0.92, 0.92, 0.92), (0.70, 0.92)),
    "MI_Bay_ConcreteFloor": (MS + "/Rough_Concrete_Floor_2x2/Rough_Concrete_Floor_2x2_C", MS + "/Rough_Concrete_Floor_2x2/Rough_Concrete_Floor_2x2_N",
                             2.0, (0.85, 0.85, 0.85), (0.72, 0.95)),
    "MI_Bay_Concrete": (MS + "/Concrete_Castinsitu_uflnbcofw/uflnbcofw_8K_Albedo", MS + "/Concrete_Castinsitu_uflnbcofw/uflnbcofw_8K_Normal",
                        4.0, (0.80, 0.80, 0.80), (0.65, 0.90)),
    "MI_Bay_Curb": (MS + "/Concrete_Castinsitu_uflnbcofw/uflnbcofw_8K_Albedo", MS + "/Concrete_Castinsitu_uflnbcofw/uflnbcofw_8K_Normal",
                    2.0, (1.0, 1.0, 1.0), (0.60, 0.85)),
    "MI_Bay_AsphaltMS": (MS + "/Cast_In_Situ_Concrete_Wall_vcfice0/Asphalt_Road_2x2_M_02/tiggcjdo_8K_Albedo",
                         MS + "/Cast_In_Situ_Concrete_Wall_vcfice0/Asphalt_Road_2x2_M_02/tiggcjdo_8K_Normal",
                         4.0, (0.62, 0.62, 0.64), (0.78, 0.96)),
    # (the lawn of the parks, MI_Bay_Grass, is an instance of M_BayLawn: see lawn_master() below)
    # the paving of the squares (a sector's "plazas"): stone slabs, a little lighter than the blocks' concrete
    # the paths of the parks (a sector's "paths"): the pack's fine pale gravel, warmed (the landscape's beach sand)
    "MI_Bay_Path": ("/Game/CityPark/Textures/Ground/T_Ground03_D", "/Game/CityPark/Textures/Ground/T_Ground03_N",
                    2.0, (1.30, 1.22, 1.05), (0.80, 0.96)),
    "MI_Bay_Plaza": ("/Game/ProceduralBuildingGenerator/Textures/Stone_tiles_floor_03_2K_Base_Color",
                     "/Game/ProceduralBuildingGenerator/Textures/Stone_tiles_floor_03_2K_Normal",
                     3.0, (0.33, 0.30, 0.26), (0.62, 0.90)),      # (the scan is almost white: at 0.95, and still at 0.5, the squares burnt out in the sun)
    # the stadium's pitch: the same grass, watered and mown in stripes of two greens (the lawn's own tint reads as
    # dry grass beside the seats)
    "MI_Bay_Pitch": ("/Game/CityPark/Textures/Ground/T_Ground02_D", "/Game/CityPark/Textures/Ground/T_Ground02_N",
                     3.0, (0.55, 1.05, 0.45), (0.86, 0.98)),
    "MI_Bay_PitchAlt": ("/Game/CityPark/Textures/Ground/T_Ground02_D", "/Game/CityPark/Textures/Ground/T_Ground02_N",
                        3.0, (0.46, 0.90, 0.38), (0.86, 0.98)),
    # the stone of the campaign's public buildings (place_mesh.py): the cast concrete, warmed to a limestone
    "MI_Bay_Stone": (MS + "/Concrete_Castinsitu_uflnbcofw/uflnbcofw_8K_Albedo", MS + "/Concrete_Castinsitu_uflnbcofw/uflnbcofw_8K_Normal",
                     4.0, (1.06, 0.98, 0.84), (0.70, 0.92)),
}
# material of each slot of the generated ground meshes
SLOT_MATERIALS = {
    "Road": BAY_MATERIALS + "/MI_Bay_AsphaltMS",
    "PaintWhite": "/Game/City/Materials/M_Paint_White",
    "PaintYellow": "/Game/City/Materials/M_Paint_Yellow",
    "Curb": BAY_MATERIALS + "/MI_Bay_Curb",
    "Sidewalk": BAY_MATERIALS + "/MI_Bay_Sidewalk",
    "Concrete": BAY_MATERIALS + "/MI_Bay_Concrete",
    "Lot": BAY_MATERIALS + "/MI_Bay_ConcreteFloor",
    "Grass": BAY_MATERIALS + "/MI_Bay_Grass",
    "Wild": BAY_MATERIALS + "/M_BayWild",
    "Plaza": BAY_MATERIALS + "/MI_Bay_Plaza",
    "Path": BAY_MATERIALS + "/MI_Bay_Path",
}
# A sector's natural ground (its "wild", slot Wild): painted like the landscape round the city, layer for layer. The
# material M_BayWild (wild_master() below) calls the landscape material's own layer function with the Bay landscape's
# own values, and blends the layers by Saved/Bay/paint_map.png (build_surface.py), read by world position.
WILD_MASTER = "M_BayWild"
LAYER_FUNCTION = "/Game/CityPark/Materials/BaseMaterial/MaterialFunction/MF_LandscapeLayer1"
PAINT_MAP = BAY_MATERIALS + "/T_BayPaintMap"
WILD_LAYERS = ["Grass", "DryGrass", "Dirt", "Sand", "Rock"]     # the paint map's red, green, blue, alpha; rock is the rest
WILD_UV_PER_QUAD = 2.0      # a sector mesh's UVs count 4 m, the landscape's count its 2 m quads: tiling times this
# The lawn of the parks and gardens (slot Grass, MI_Bay_Grass): the landscape's grass layer through the landscape's
# own layer function, as M_BayWild does for natural ground. The landscape turns into each layer's far colour with
# distance; the lawn used the same grass texture without that, so from the street the two looked alike and from the
# air every park and garden stood out as a pale rectangle against dark olive hills (2026-11-19).
LAWN_MASTER = "M_BayLawn"
LAWN_INSTANCE = "MI_Bay_Grass"
LAWN_TINT = (0.95, 1.0, 0.90)       # a lawn is watered: a little greener than the hills' grass, near and far

# painted surfaces of the structures (span_mesh.py): name: (colour, roughness, metallic)
PAINT_MASTER = "M_BayPaint"
PAINT_INSTANCES = {
    "MI_Bay_BridgeSteel": ((0.46, 0.50, 0.52), 0.55, 0.30),         # light grey bridge paint
    "MI_Bay_Railing": ((0.09, 0.10, 0.11), 0.45, 0.75),
    "MI_Bay_Plinth": ((0.33, 0.32, 0.30), 0.90, 0.0),               # cast stone base under a building
    "MI_Bay_TunnelTile": ((0.62, 0.61, 0.56), 0.36, 0.0),           # light lining on a tunnel's walls
    # the stadium (stadium_mesh.py): its seats, in blocks of two colours, and the roof's upper face
    "MI_Bay_SeatBlue": ((0.03, 0.09, 0.30), 0.55, 0.0),
    "MI_Bay_SeatWhite": ((0.72, 0.72, 0.70), 0.55, 0.0),
    "MI_Bay_RoofSheet": ((0.70, 0.71, 0.70), 0.42, 0.20),
    # the campaign's places (place_mesh.py): window glass, signal red (a cross, an engine bay's door), white
    # render, brick-red paint
    "MI_Bay_Glass": ((0.020, 0.034, 0.050), 0.12, 0.90),
    "MI_Bay_SignRed": ((0.50, 0.03, 0.02), 0.45, 0.0),
    "MI_Bay_Plaster": ((0.74, 0.73, 0.70), 0.85, 0.0),
    "MI_Bay_BrickRed": ((0.30, 0.11, 0.07), 0.85, 0.0),
}
PLINTH_MATERIAL = BAY_MATERIALS + "/MI_Bay_Plinth"
# surfaces that give light (the lines of lamps under a tunnel's roof): name: (colour, luminance in nits).
# The sun here is 3150 lux and the exposure goes down to EV 8, where a wall needs some 170 lux to read as
# mid-grey; two lines of lamps 0.8 m wide, 5 m above the road, give that at about 900 nits.
GLOW_MASTER = "M_BayGlow"
GLOW_INSTANCES = {
    "MI_Bay_TunnelLight": ((1.0, 0.90, 0.72), 900.0),
}
STRUCTURE_SLOTS = {"Steel": BAY_MATERIALS + "/MI_Bay_BridgeSteel", "Rail": BAY_MATERIALS + "/MI_Bay_Railing",
                   "Tile": BAY_MATERIALS + "/MI_Bay_TunnelTile", "Light": BAY_MATERIALS + "/MI_Bay_TunnelLight",
                   "Seat": BAY_MATERIALS + "/MI_Bay_SeatBlue", "SeatAlt": BAY_MATERIALS + "/MI_Bay_SeatWhite",
                   "Roof": BAY_MATERIALS + "/MI_Bay_RoofSheet", "Pitch": BAY_MATERIALS + "/MI_Bay_Pitch",
                   "PitchAlt": BAY_MATERIALS + "/MI_Bay_PitchAlt", "Stone": BAY_MATERIALS + "/MI_Bay_Stone",
                   "Glass": BAY_MATERIALS + "/MI_Bay_Glass", "Red": BAY_MATERIALS + "/MI_Bay_SignRed",
                   "Plaster": BAY_MATERIALS + "/MI_Bay_Plaster", "Brick": BAY_MATERIALS + "/MI_Bay_BrickRed"}

# Landscape: the City Park landscape material blends layers "1".."9"; same setup as the first city
# (Tools/citymap/build_citymap.py), so Tools/surfaces/apply_surfaces.py tags the same layer infos.
LANDSCAPE_PARENT = "/Game/CityPark/Materials/Ground/MI_Landscape"
LAYER_INFO = "/Game/CityPark/Maps/Showcase_sharedassets/%d_LayerInfo"
CP = "/Game/CityPark/Textures"
PNL = "/Game/PN_GrassLibrary/Textures/LandscapeTextures"
# our layer -> (material layer number, diffuse, normal, tiling, roughness, specular, normal strength, far colour)
LAYER_SETUP = {
    # (2026-11-17, the landscape repainted as the Bay Area's hills: "Dirt" is bare earth on steep sunny slopes, "Rock"
    # grey scree on the steepest faces (no tileable rock texture in the project; the gravel reads as rock from afar),
    # "DryGrass" the golden grass of the hills, warmed by its tint. The grip of each layer number is set on the shared
    # layer infos by Tools/surfaces/apply_surfaces.py: 2 and 7 are dirt, 4 rock.)
    "Grass":    (1, CP + "/Ground/T_Ground02_D", CP + "/Ground/T_Ground02_N", 1.33, 0.90, 0.12, 1.5, (0.105, 0.107, 0.023)),
    "Dirt":     (2, PNL + "/ground_II_albedo", PNL + "/ground_II_normal", 1.0, 0.92, 0.10, 1.5, (0.262, 0.198, 0.102)),
    # (2026-11-18: the beach. The Megascans "sand" used here until then is a dark wet mud, and a virtual texture: the
    # landscape material samples its layers with ordinary samplers, so it came out as its far colour alone, a rust-brown
    # band along every shore; and the sectors' natural ground, which calls the same layer function, did not compile with
    # it. The pack's fine pale gravel, warmed by its tint, is a pebbly sand; its far colour is the tinted mean.)
    "Sand":     (3, CP + "/Ground/T_Ground03_D", CP + "/Ground/T_Ground03_N", 0.8, 0.88, 0.12, 1.0, (0.290, 0.232, 0.132)),
    "Rock":     (4, CP + "/Ground/T_Ground03_D", CP + "/Ground/T_Ground03_N", 0.5, 0.90, 0.12, 2.0, (0.195, 0.165, 0.107)),
    "Asphalt":  (5, CP + "/Road/T_Asphalt_D", CP + "/Road/T_Asphalt_N", 1.6, 0.75, 0.30, 1.5, (0.068, 0.068, 0.066)),
    "Pavement": (6, "/Game/Deko_MatrixDemo/Shared/Textures/T_Concrete_03_C", "/Game/Deko_MatrixDemo/Shared/Textures/T_Concrete_03_N",
                 1.0, 0.75, 0.25, 1.5, (0.250, 0.229, 0.194)),
    "DryGrass": (7, CP + "/Ground/T_Ground05_D", CP + "/Ground/T_Ground05_N", 1.33, 0.92, 0.10, 1.5, (0.190, 0.145, 0.060)),
}
FAR_COLOR_DISTANCE = 30000.0
# the pack's asphalt is pale (albedo ~0.16); real asphalt is ~0.07. The dry grass scan is a dull olive straw: warmed
# a little towards the khaki gold of the hills in the dry season (its far colour above is the tinted mean; a first
# try at 1.45/1.30/1.10 read as pale sand dunes from the air)
LAYER_TINT = {3: (1.50, 1.42, 1.24), 5: (0.45, 0.45, 0.45), 7: (1.05, 0.95, 1.0)}
INSPECT = ["/Game/Fab/Materials/Standard/M_MS_Srf", "/Game/Fab/Materials/Standard/M_MS_Base",
           "/Game/Road/Material/MI/M_Asphalt_Master_Inst", "/Game/Road/Material/MI/M_Sidewalk_Master_Inst",
           "/Game/MSPresets/MS_DefaultMaterial/MS_DefaultMaterial", "/Game/MetaRoad/Materials/Master/M_Road"]

assets = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary


def log(text):
    unreal.log("BAY " + text)


def stages():
    wanted = os.environ.get("BAY_STAGES", "")
    return [s.strip() for s in wanted.split(",") if s.strip()] or ["sectors", "sea", "light"]


def sector_names():
    wanted = [s.strip() for s in os.environ.get("BAY_SECTORS", "").split(",") if s.strip()]
    folder = os.path.join(DATA, "sectors")
    found = sorted(n for n in os.listdir(folder) if os.path.exists(os.path.join(folder, n, n + "_Ground.glb"))) \
        if os.path.isdir(folder) else []
    return [n for n in found if not wanted or n in wanted]


def instance(name, parent_path):
    """A material instance in /Game/Bay/Materials with the given parent, created or reused."""
    path = "%s/%s" % (BAY_MATERIALS, name)
    mi = assets.load_asset(path) if assets.does_asset_exist(path) else \
        tools.create_asset(name, BAY_MATERIALS, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    parent = assets.load_asset(parent_path)
    if not parent:
        raise RuntimeError("missing material " + parent_path)
    mel.set_material_instance_parent(mi, parent)
    return mi, path


def is_virtual(texture):
    return bool(texture and texture.get_editor_property("virtual_texture_streaming"))


def ground_master(virtual, default_albedo, default_normal):
    """The master material of the Bay city's ground surfaces, rebuilt from scratch on every run.

    Deliberately small, so thousands of square metres of it stay cheap on an 8 GB card:
      base colour  Albedo texture x Tint x a slow world-space noise (MacroLow..MacroHigh) that hides the tiling
      normal       Normal texture
      roughness    RoughnessMin..RoughnessMax by the albedo's brightness (dark, oily patches are smoother)
    UVs are the mesh's own (one unit = 4 m) times Tiling.

    There are two of it. The City Sample's Megascans scans are virtual textures; read through an ordinary
    sampler a virtual texture comes out black, and an ordinary texture cannot go into a virtual sampler.
    So M_BayGround_VT samples virtual textures and M_BayGround ordinary ones."""
    name = GROUND_MASTER + ("_VT" if virtual else "")
    path = "%s/%s" % (BAY_MATERIALS, name)
    mat = assets.load_asset(path) if assets.does_asset_exist(path) else \
        tools.create_asset(name, BAY_MATERIALS, unreal.Material, unreal.MaterialFactoryNew())
    mel.delete_all_material_expressions(mat)
    failed = []
    kinds = unreal.MaterialSamplerType
    colour_sampler = kinds.SAMPLERTYPE_VIRTUAL_COLOR if virtual else kinds.SAMPLERTYPE_COLOR
    normal_sampler = kinds.SAMPLERTYPE_VIRTUAL_NORMAL if virtual else kinds.SAMPLERTYPE_NORMAL

    def node(cls, x, y, **props):
        e = mel.create_material_expression(mat, cls, x, y)
        for key, value in props.items():
            e.set_editor_property(key, value)
        return e

    def wire(a, out, b, inp):
        if not mel.connect_material_expressions(a, out, b, inp):
            failed.append("%s.%s -> %s.%s" % (a.get_name(), out, b.get_name(), inp))

    def scalar(name, value, y):
        return node(unreal.MaterialExpressionScalarParameter, -1500, y, parameter_name=name, default_value=value)

    uv = node(unreal.MaterialExpressionTextureCoordinate, -1500, -300)
    uvs = node(unreal.MaterialExpressionMultiply, -1250, -260)
    wire(uv, "", uvs, "A")
    wire(scalar("Tiling", 1.0, -180), "", uvs, "B")
    albedo = node(unreal.MaterialExpressionTextureSampleParameter2D, -1000, -320, parameter_name="Albedo",
                  texture=default_albedo, sampler_type=colour_sampler)
    normal = node(unreal.MaterialExpressionTextureSampleParameter2D, -1000, 60, parameter_name="Normal",
                  texture=default_normal, sampler_type=normal_sampler)
    wire(uvs, "", albedo, "UVs")
    wire(uvs, "", normal, "UVs")
    # slow variation in world space: the noise node reads the world position by itself, one blotch per ~11 m
    noise = node(unreal.MaterialExpressionNoise, -1000, 440, scale=0.0009, quality=1, levels=2, turbulence=False,
                 output_min=0.0, output_max=1.0, noise_function=unreal.NoiseFunction.NOISEFUNCTION_GRADIENT_TEX)
    macro = node(unreal.MaterialExpressionLinearInterpolate, -720, 420)
    wire(scalar("MacroLow", 0.82, 640), "", macro, "A")
    wire(scalar("MacroHigh", 1.08, 720), "", macro, "B")
    wire(noise, "", macro, "Alpha")
    tint = node(unreal.MaterialExpressionVectorParameter, -1000, -560, parameter_name="Tint",
                default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0))
    tinted = node(unreal.MaterialExpressionMultiply, -720, -400)
    wire(albedo, "RGB", tinted, "A")
    wire(tint, "", tinted, "B")
    base = node(unreal.MaterialExpressionMultiply, -460, -300)
    wire(tinted, "", base, "A")
    wire(macro, "", base, "B")
    rough = node(unreal.MaterialExpressionLinearInterpolate, -460, -60)
    wire(scalar("RoughnessMin", 0.7, -60), "", rough, "A")
    wire(scalar("RoughnessMax", 0.95, 20), "", rough, "B")
    wire(albedo, "G", rough, "Alpha")
    for expr, out, prop in ((base, "", unreal.MaterialProperty.MP_BASE_COLOR), (normal, "RGB", unreal.MaterialProperty.MP_NORMAL),
                            (rough, "", unreal.MaterialProperty.MP_ROUGHNESS)):
        if not mel.connect_material_property(expr, out, prop):
            failed.append("%s -> %s" % (expr.get_name(), prop))
    mel.recompile_material(mat)
    assets.save_asset(path, only_if_is_dirty=False)
    if failed:
        log("MASTER MATERIAL %s: %d connections failed: %s" % (name, len(failed), "; ".join(failed)))
    return path


def build_materials():
    """The Bay city's own ground materials: Megascans scans as instances of the Bay ground master."""
    loaded = {name: (assets.load_asset(spec[0]), assets.load_asset(spec[1])) for name, spec in MS_INSTANCES.items()}
    masters = {}
    for virtual in (False, True):
        sample = next(((a, n) for a, n in loaded.values() if a and n and is_virtual(a) == virtual and is_virtual(n) == virtual), None)
        if virtual and not sample:
            continue                          # no virtual scan in use: that master is not needed
        if not sample:
            sample = (assets.load_asset("/Engine/EngineMaterials/DefaultDiffuse"), assets.load_asset("/Engine/EngineMaterials/DefaultNormal"))
        masters[virtual] = ground_master(virtual, sample[0], sample[1])
    log("materials: virtual textures %s in the project; scans: %s" % (
        "on" if unreal.SystemLibrary.get_console_variable_bool_value("r.VirtualTextures") else "OFF",
        ", ".join("%s %s" % (n, "virtual" if is_virtual(a) else "ordinary") for n, (a, _) in loaded.items())))
    for name, (albedo, normal, metres, tint, rough) in MS_INSTANCES.items():
        base, nrm = loaded[name]
        if not base or not nrm:
            log("MISSING texture for %s: %s / %s" % (name, albedo, normal))
            continue
        if is_virtual(base) != is_virtual(nrm):
            log("MIXED scan %s: albedo and normal differ in kind (virtual / ordinary); it will render wrong" % name)
        mi, path = instance(name, masters[is_virtual(base)])
        mel.set_material_instance_texture_parameter_value(mi, "Albedo", base)
        mel.set_material_instance_texture_parameter_value(mi, "Normal", nrm)
        mel.set_material_instance_scalar_parameter_value(mi, "Tiling", 4.0 / metres)
        mel.set_material_instance_scalar_parameter_value(mi, "RoughnessMin", rough[0])
        mel.set_material_instance_scalar_parameter_value(mi, "RoughnessMax", rough[1])
        mel.set_material_instance_vector_parameter_value(mi, "Tint", unreal.LinearColor(tint[0], tint[1], tint[2], 1.0))
        mel.update_material_instance(mi)
        assets.save_asset(path, only_if_is_dirty=False)
    log("materials: %d masters and %d Megascans instances in %s" % (len(masters), len(MS_INSTANCES), BAY_MATERIALS))


def import_paint_map():
    """Saved/Bay/paint_map.png as the texture T_BayPaintMap: plain values (not colours), not streamed virtually (a
    picture this size is made a virtual texture on import, and an ordinary sampler reads those black).
    Returns (texture, its corner in Unreal cm, its size in cm)."""
    with open(os.path.join(DATA, "landscape.json")) as f:
        spec = json.load(f).get("paint_map")
    if not spec or not os.path.exists(os.path.join(DATA, spec["file"])):
        raise RuntimeError("no paint map: run Tools/bay/build_surface.py")
    task = unreal.AssetImportTask()
    task.filename = os.path.join(DATA, spec["file"])
    task.destination_path, task.destination_name = PAINT_MAP.rsplit("/", 1)
    task.automated = True
    task.replace_existing = True
    task.save = True
    tools.import_asset_tasks([task])
    texture = assets.load_asset(PAINT_MAP)
    if not texture:
        raise RuntimeError("the paint map did not import: " + task.filename)
    texture.set_editor_property("virtual_texture_streaming", False)
    texture.set_editor_property("srgb", False)
    texture.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_BC7)
    texture.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
    texture.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    assets.save_asset(PAINT_MAP, only_if_is_dirty=False)
    log("paint map: %s, %d x %d, virtual %s" % (PAINT_MAP, texture.blueprint_get_size_x(), texture.blueprint_get_size_y(), is_virtual(texture)))
    return texture, spec["origin_cm"], spec["size_cm"]


def wild_master():
    """The material of the sectors' natural ground, rebuilt from scratch on every run: the landscape's layers, each
    through the landscape material's own layer function (so texture, tint, tiling and the far colour that takes
    over with distance are the landscape's, value for value, read from the Bay landscape's material instance),
    blended by the paint map at the pixel's world position. A sector's hillside then cannot be told from the
    hill beyond its side.

    Once the material exists only the paint map is imported again (the material reads it by name): rebuilding the
    graph with the map open, where sectors already wear the material, has the editor refresh every one of them at
    each node set, a quarter of an hour of it (2026-11-18). BAY_WILD_REBUILD=1 forces the rebuild: after a change to
    the layers (LAYER_SETUP), with a build of this stage alone."""
    paint, origin, size = import_paint_map()
    if assets.does_asset_exist("%s/%s" % (BAY_MATERIALS, WILD_MASTER)) and not os.environ.get("BAY_WILD_REBUILD"):
        log("natural ground material %s/%s kept as it is; its paint map imported again" % (BAY_MATERIALS, WILD_MASTER))
        return "%s/%s" % (BAY_MATERIALS, WILD_MASTER)
    # the Bay landscape's instance as it is (the "ground" stage sets it; setting it again here would have the open
    # map's landscape refresh every component's material, minutes of it, for nothing)
    landscape = assets.load_asset(BAY_MATERIALS + "/MI_BayLandscape") or landscape_material()
    log("natural ground material: layers read from %s" % landscape.get_path_name())
    function = assets.load_asset(LAYER_FUNCTION)
    if not function:
        raise RuntimeError("missing material function " + LAYER_FUNCTION)
    path = "%s/%s" % (BAY_MATERIALS, WILD_MASTER)
    mat = assets.load_asset(path) if assets.does_asset_exist(path) else \
        tools.create_asset(WILD_MASTER, BAY_MATERIALS, unreal.Material, unreal.MaterialFactoryNew())
    mel.delete_all_material_expressions(mat)
    failed = []

    def node(cls, x, y, **props):
        e = mel.create_material_expression(mat, cls, x, y)
        for key, value in props.items():
            e.set_editor_property(key, value)
        return e

    def wire(a, out, b, inp):
        if not mel.connect_material_expressions(a, out, b, inp):
            failed.append("%s.%s -> %s.%s" % (a.get_name(), out, b.get_name(), inp))

    def constant(value, x, y):
        return node(unreal.MaterialExpressionConstant, x, y, r=float(value))

    def colour(value, x, y):
        return node(unreal.MaterialExpressionConstant3Vector, x, y, constant=unreal.LinearColor(value.r, value.g, value.b, 1.0))

    def two(a, b, x, y):
        return node(unreal.MaterialExpressionConstant2Vector, x, y, r=float(a), g=float(b))

    # where the pixel is on the paint map
    world = node(unreal.MaterialExpressionWorldPosition, -3000, -200)
    flat = node(unreal.MaterialExpressionComponentMask, -2800, -200, r=True, g=True, b=False, a=False)
    wire(world, "", flat, "")
    moved = node(unreal.MaterialExpressionSubtract, -2600, -200)
    wire(flat, "", moved, "A")
    wire(two(origin[0], origin[1], -2800, -80), "", moved, "B")
    uv = node(unreal.MaterialExpressionDivide, -2400, -200)
    wire(moved, "", uv, "A")
    wire(two(size[0], size[1], -2600, -80), "", uv, "B")
    sample = node(unreal.MaterialExpressionTextureSampleParameter2D, -2200, -200, parameter_name="PaintMap", texture=paint,
                  sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    wire(uv, "", sample, "UVs")
    painted = node(unreal.MaterialExpressionAdd, -1900, -120)
    wire(sample, "R", painted, "A")
    wire(sample, "G", painted, "B")
    painted2 = node(unreal.MaterialExpressionAdd, -1750, -80)
    wire(painted, "", painted2, "A")
    wire(sample, "B", painted2, "B")
    painted3 = node(unreal.MaterialExpressionAdd, -1600, -40)
    wire(painted2, "", painted3, "A")
    wire(sample, "A", painted3, "B")
    rest = node(unreal.MaterialExpressionOneMinus, -1450, -40)
    wire(painted3, "", rest, "")
    rock = node(unreal.MaterialExpressionSaturate, -1300, -40)
    wire(rest, "", rock, "")
    weights = [(sample, "R"), (sample, "G"), (sample, "B"), (sample, "A"), (rock, "")]

    sums = {"Diffuse": None, "Normal": None, "Specular": None, "Roughness": None}
    for row, (name, (weight, channel)) in enumerate(zip(WILD_LAYERS, weights)):
        n, diff, norm, tiling, _, _, _, _ = LAYER_SETUP[name]
        y = 300 + row * 520
        call = node(unreal.MaterialExpressionMaterialFunctionCall, -1500, y)
        try:
            call.set_material_function(function)
        except Exception:
            call.set_editor_property("material_function", function)
        scalar = lambda label: mel.get_material_instance_scalar_parameter_value(landscape, label)
        vector = lambda label: mel.get_material_instance_vector_parameter_value(landscape, label)
        inputs = {
            "Roughness": constant(scalar("Roughness %d" % n), -2000, y),
            "FarColorDistance": constant(scalar("FarColorDistance %d" % n), -2000, y + 40),
            "Specular": constant(scalar("Specular %d" % n), -2000, y + 80),
            "Normal": node(unreal.MaterialExpressionTextureObjectParameter, -2300, y + 120, parameter_name="Normal %s" % name,
                           texture=assets.load_asset(norm), sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL),
            "Tilling": constant(scalar("tilling %d" % n) * WILD_UV_PER_QUAD, -2000, y + 160),
            "Diffuse": node(unreal.MaterialExpressionTextureObjectParameter, -2300, y + 300, parameter_name="Diffuse %s" % name,
                            texture=assets.load_asset(diff), sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR),
            "Color": colour(vector("Color %d" % n), -2000, y + 200),
            "FarColor": colour(vector("Far Color %d" % n), -2000, y + 250),
            "Contrast": constant(scalar("Contrast %d" % n), -2000, y + 340),
            "Desaturation": constant(scalar("desaturation %d" % n), -2000, y + 380),
            "Normal Str": constant(scalar("NormalStr%d" % n), -2000, y + 420),
        }
        for pin, source in inputs.items():
            wire(source, "", call, pin)
        for k, output in enumerate(sums):
            part = node(unreal.MaterialExpressionMultiply, -1100, y + k * 110)
            wire(call, output, part, "A")
            wire(weight, channel, part, "B")
            if sums[output] is None:
                sums[output] = part
            else:
                total = node(unreal.MaterialExpressionAdd, -800 + row * 60, y + k * 110)
                wire(sums[output], "", total, "A")
                wire(part, "", total, "B")
                sums[output] = total
    normal = node(unreal.MaterialExpressionNormalize, -300, 900)
    wire(sums["Normal"], "", normal, "VectorInput")
    for expr, prop in ((sums["Diffuse"], unreal.MaterialProperty.MP_BASE_COLOR), (normal, unreal.MaterialProperty.MP_NORMAL),
                       (sums["Specular"], unreal.MaterialProperty.MP_SPECULAR), (sums["Roughness"], unreal.MaterialProperty.MP_ROUGHNESS)):
        if not mel.connect_material_property(expr, "", prop):
            failed.append("%s -> %s" % (expr.get_name(), prop))
    mel.recompile_material(mat)
    assets.save_asset(path, only_if_is_dirty=False)
    log("natural ground material %s: %d layers through %s; %s" % (
        path, len(WILD_LAYERS), LAYER_FUNCTION.rsplit("/", 1)[-1],
        ("%d CONNECTIONS FAILED: %s" % (len(failed), "; ".join(failed[:12]))) if failed else "every connection made"))
    return path


def lawn_master():
    """M_BayLawn and its instance MI_Bay_Grass (see LAWN_MASTER): the stage "lawn", run alone in a commandlet
    (see main()). The master is built once, and again with BAY_LAWN_REBUILD=1; the instance takes the landscape's
    grass layer values on every run. Returns False, and leaves the lawns' material as it was, when the master's
    graph did not connect."""
    name, _, _, _, _, _, _, far = LAYER_SETUP["Grass"]
    n = LAYER_SETUP["Grass"][0]
    landscape = assets.load_asset(BAY_MATERIALS + "/MI_BayLandscape") or landscape_material()
    function = assets.load_asset(LAYER_FUNCTION)
    if not function:
        raise RuntimeError("missing material function " + LAYER_FUNCTION)
    path = "%s/%s" % (BAY_MATERIALS, LAWN_MASTER)
    scalars = {"Roughness": "Roughness %d", "FarColorDistance": "FarColorDistance %d", "Specular": "Specular %d",
               "Tilling": "tilling %d", "Contrast": "Contrast %d", "Desaturation": "desaturation %d", "Normal Str": "NormalStr%d"}
    if not assets.does_asset_exist(path) or os.environ.get("BAY_LAWN_REBUILD"):
        mat = assets.load_asset(path) if assets.does_asset_exist(path) else \
            tools.create_asset(LAWN_MASTER, BAY_MATERIALS, unreal.Material, unreal.MaterialFactoryNew())
        mel.delete_all_material_expressions(mat)
        failed = []

        def node(cls, x, y, **props):
            e = mel.create_material_expression(mat, cls, x, y)
            for key, value in props.items():
                e.set_editor_property(key, value)
            return e

        def wire(a, out, b, inp):
            if not mel.connect_material_expressions(a, out, b, inp):
                failed.append("%s.%s -> %s.%s" % (a.get_name(), out, b.get_name(), inp))

        call = node(unreal.MaterialExpressionMaterialFunctionCall, -700, 0)
        try:
            call.set_material_function(function)
        except Exception:
            call.set_editor_property("material_function", function)
        for row, pin in enumerate(scalars):
            wire(node(unreal.MaterialExpressionScalarParameter, -1200, row * 90, parameter_name=pin, default_value=0.0), "", call, pin)
        white = unreal.LinearColor(1.0, 1.0, 1.0, 1.0)
        wire(node(unreal.MaterialExpressionVectorParameter, -1200, 700, parameter_name="Color", default_value=white), "", call, "Color")
        wire(node(unreal.MaterialExpressionVectorParameter, -1200, 900, parameter_name="FarColor", default_value=white), "", call, "FarColor")
        wire(node(unreal.MaterialExpressionTextureObjectParameter, -1200, 1100, parameter_name="Diffuse",
                  texture=assets.load_asset(LAYER_SETUP["Grass"][1]), sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR), "", call, "Diffuse")
        wire(node(unreal.MaterialExpressionTextureObjectParameter, -1200, 1300, parameter_name="Normal",
                  texture=assets.load_asset(LAYER_SETUP["Grass"][2]), sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL), "", call, "Normal")
        for output, prop in (("Diffuse", unreal.MaterialProperty.MP_BASE_COLOR), ("Normal", unreal.MaterialProperty.MP_NORMAL),
                             ("Specular", unreal.MaterialProperty.MP_SPECULAR), ("Roughness", unreal.MaterialProperty.MP_ROUGHNESS)):
            if not mel.connect_material_property(call, output, prop):
                failed.append("%s -> %s" % (output, prop))
        mel.recompile_material(mat)
        assets.save_asset(path, only_if_is_dirty=False)
        log("lawn material %s: %s" % (path, ("%d CONNECTIONS FAILED: %s" % (len(failed), "; ".join(failed))) if failed else "every connection made"))
        if failed:
            return False
    mi, mi_path = instance(LAWN_INSTANCE, path)
    for pin, label in scalars.items():
        value = mel.get_material_instance_scalar_parameter_value(landscape, label % n)
        mel.set_material_instance_scalar_parameter_value(mi, pin, value * (WILD_UV_PER_QUAD if pin == "Tilling" else 1.0))
    tint = mel.get_material_instance_vector_parameter_value(landscape, "Color %d" % n)
    mel.set_material_instance_vector_parameter_value(mi, "Color", unreal.LinearColor(
        tint.r * LAWN_TINT[0], tint.g * LAWN_TINT[1], tint.b * LAWN_TINT[2], 1.0))
    mel.set_material_instance_vector_parameter_value(mi, "FarColor", unreal.LinearColor(
        far[0] * LAWN_TINT[0], far[1] * LAWN_TINT[1], far[2] * LAWN_TINT[2], 1.0))
    mel.set_material_instance_texture_parameter_value(mi, "Diffuse", assets.load_asset(LAYER_SETUP["Grass"][1]))
    mel.set_material_instance_texture_parameter_value(mi, "Normal", assets.load_asset(LAYER_SETUP["Grass"][2]))
    mel.update_material_instance(mi)
    assets.save_asset(mi_path, only_if_is_dirty=False)
    log("lawn: %s is an instance of %s, the landscape's grass layer with its far colour" % (mi_path, path))
    return True


def landscape_material():
    mi, path = instance("MI_BayLandscape", LANDSCAPE_PARENT)
    for name, (n, diff, norm, tiling, rough, spec, nstr, far) in LAYER_SETUP.items():
        d, nm = assets.load_asset(diff), assets.load_asset(norm)
        if not d or not nm:
            log("MISSING texture for %s: %s / %s" % (name, diff, norm))
            continue
        mel.set_material_instance_texture_parameter_value(mi, "layer diff %d" % n, d)
        mel.set_material_instance_texture_parameter_value(mi, "layer normal %d" % n, nm)
        mel.set_material_instance_scalar_parameter_value(mi, "tilling %d" % n, tiling)
        mel.set_material_instance_scalar_parameter_value(mi, "Roughness %d" % n, rough)
        mel.set_material_instance_scalar_parameter_value(mi, "Specular %d" % n, spec)
        mel.set_material_instance_scalar_parameter_value(mi, "NormalStr%d" % n, nstr)
        mel.set_material_instance_scalar_parameter_value(mi, "FarColorDistance %d" % n, FAR_COLOR_DISTANCE)
        mel.set_material_instance_vector_parameter_value(mi, "Far Color %d" % n, unreal.LinearColor(far[0], far[1], far[2], 1.0))
        if n in LAYER_TINT:
            t = LAYER_TINT[n]
            mel.set_material_instance_vector_parameter_value(mi, "Color %d" % n, unreal.LinearColor(t[0], t[1], t[2], 1.0))
    mel.update_material_instance(mi)
    assets.save_asset(path, only_if_is_dirty=False)
    return mi


def build_ground(world, actors):
    """The landscape of the whole map, from Saved/Bay/landscape.r16 and layer_*.raw (build_surface.py)."""
    with open(os.path.join(DATA, "landscape.json")) as f:
        info = json.load(f)
    removed = remove_actors(actors, ["Bay/Ground"])
    mi = landscape_material()
    infos, files = [], []
    for name in info["layers"]:
        layer_info = assets.load_asset(LAYER_INFO % LAYER_SETUP[name][0])
        if not layer_info:
            raise RuntimeError("missing layer info %s" % (LAYER_INFO % LAYER_SETUP[name][0]))
        infos.append(layer_info)
        files.append(os.path.join(DATA, "layer_%s.raw" % name))
    vx, vy = info["vertices"]
    landscape = unreal.WSPC2CityTools.create_landscape_from_raw(
        world, os.path.join(DATA, "landscape.r16"), vx, vy, info["component_quads"], 1,
        unreal.Vector(*info["location_cm"]), unreal.Vector(*info["scale"]), mi, infos, files)
    if not landscape:
        raise RuntimeError("landscape creation failed")
    landscape.set_actor_label("BayLandscape")
    landscape.set_folder_path("Bay/Ground")
    log("ground: %d old actors removed; landscape %d x %d vertices, layers merged: %s" % (
        removed, vx, vy, unreal.WSPC2CityTools.update_landscape_now(landscape)))


def precise_uvs(mesh):
    """Stores the mesh's texture coordinates at full precision. The generated meshes are hundreds of metres
    across and their UVs count metres (one unit = 4 m); at the default 16 bits a coordinate near 100 moves in
    steps of 25 cm, so a strip of asphalt 11 cm wide between two painted lines gets one value across its
    width and the texture smears into stripes."""
    subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    settings = subsystem.get_lod_build_settings(mesh, 0)
    if not settings.get_editor_property("use_full_precision_u_vs"):
        settings.set_editor_property("use_full_precision_u_vs", True)
        subsystem.set_lod_build_settings(mesh, 0, settings)


def remove_actors(actors, folders):
    """Destroys the actors filed in one of the folders or below it. The folder must match whole: "Bay/Sectors/CC1"
    is not a prefix test, or rebuilding CC1 would also take CC10 to CC17 with it (it did, once: 2026-11-13)."""
    removed = 0
    for actor in actors.get_all_level_actors():
        path = str(actor.get_folder_path())
        if any(path == folder or path.startswith(folder + "/") for folder in folders):
            actors.destroy_actor(actor)
            removed += 1
    return removed


def build_sectors(world, actors):
    materials = {}
    for slot, path in SLOT_MATERIALS.items():
        materials[slot] = assets.load_asset(path)
        if not materials[slot]:
            log("MISSING material for slot %s: %s" % (slot, path))
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    for name in sector_names():
        folder = "%s/%s" % (GENERATED, name)
        removed = remove_actors(actors, ["Bay/Sectors/%s" % name])
        if assets.does_directory_exist(folder):
            assets.delete_directory(folder)
        task = unreal.AssetImportTask()
        task.filename = os.path.join(DATA, "sectors", name, name + "_Ground.glb")
        task.destination_path = folder
        task.automated = True
        task.replace_existing = True
        task.save = True
        tools.import_asset_tasks([task])
        registry.scan_paths_synchronous([folder], True)
        placed, unknown = 0, set()
        for data in registry.get_assets_by_path(folder, recursive=True):
            if str(data.asset_class_path.asset_name) != "StaticMesh":
                continue
            mesh = data.get_asset()
            settings = mesh.get_editor_property("nanite_settings")
            settings.enabled = False
            mesh.set_editor_property("nanite_settings", settings)
            precise_uvs(mesh)
            for index, slot in enumerate(mesh.static_materials):
                slot_name = str(slot.material_slot_name)
                if materials.get(slot_name):
                    mesh.set_material(index, materials[slot_name])
                else:
                    unknown.add(slot_name)
            body = mesh.get_editor_property("body_setup")
            if body:
                body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            assets.save_loaded_asset(mesh)
            actor = actors.spawn_actor_from_object(mesh, unreal.Vector(0, 0, 0))
            actor.set_actor_label(str(data.asset_name))
            actor.set_folder_path("Bay/Sectors/%s" % name)
            bounds = mesh.get_bounds()
            log("sector %s: %s, %d triangles, centre (%.0f, %.0f, %.0f) cm, extent (%.0f, %.0f, %.0f) cm" % (
                name, data.asset_name, mesh.get_num_triangles(0), bounds.origin.x, bounds.origin.y, bounds.origin.z,
                bounds.box_extent.x, bounds.box_extent.y, bounds.box_extent.z))
            placed += 1
        log("sector %s: %d old actors removed, %d meshes placed%s" % (
            name, removed, placed, ("; slots without a material: %s" % sorted(unknown)) if unknown else ""))


def rotator(yaw):
    r = unreal.Rotator()
    r.yaw = yaw
    return r


def build_buildings(world, actors):
    """Places each sector's buildings (Saved/Bay/sectors/<name>/lots.json, from plan_lots.py): one instanced
    actor per building mesh, one invisible box per building as its collision, and a plinth under each building
    whose model's walls stop short of the ground (plan_plinths.py)."""
    cube = assets.load_asset("/Engine/BasicShapes/Cube")
    if not paint_ready():
        build_paint_materials()
    plinth_material = assets.load_asset(PLINTH_MATERIAL)
    for name in sector_names():
        path = os.path.join(DATA, "sectors", name, "lots.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            layout = json.load(f)
        folder = "Bay/Buildings/%s" % name
        removed = remove_actors(actors, [folder])
        placed, missing = 0, []
        for mesh_path, rows in sorted(layout["instances"].items()):
            mesh = assets.load_asset(mesh_path)
            if not mesh:
                missing.append(mesh_path)
                continue
            transforms = [unreal.Transform(location=unreal.Vector(x, y, z), rotation=rotator(yaw), scale=unreal.Vector(s, s, s))
                          for x, y, z, yaw, s in rows]
            label = "%s_%s" % (name, mesh_path.rsplit("/", 1)[-1])
            if unreal.WSPC2CityTools.spawn_instanced_meshes(world, mesh, transforms, False, False, label, folder, 0.0, False):
                placed += len(rows)
        boxes = [unreal.Transform(location=unreal.Vector(x, y, z), rotation=rotator(yaw),
                                  scale=unreal.Vector(sx / 100.0, sy / 100.0, sz / 100.0))
                 for x, y, z, yaw, sx, sy, sz in layout["collision"]]
        if boxes:
            unreal.WSPC2CityTools.spawn_instanced_meshes(world, cube, boxes, True, True, "%s_BuildingCollision" % name, folder, 0.0, True)
        plinths = [unreal.Transform(location=unreal.Vector(x, y, z), rotation=rotator(yaw),
                                    scale=unreal.Vector(sx / 100.0, sy / 100.0, sz / 100.0))
                   for x, y, z, yaw, sx, sy, sz in layout.get("plinths", []) + layout.get("podiums", [])]
        if plinths:
            actor = unreal.WSPC2CityTools.spawn_instanced_meshes(world, cube, plinths, False, False, "%s_Plinths" % name, folder, 0.0, False)
            if actor and plinth_material:
                for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
                    component.set_material(0, plinth_material)
        log("buildings %s: %d old actors removed, %d buildings, %d mesh instances, %d plinths and podiums%s" % (
            name, removed, len(layout["buildings"]), placed, len(plinths), ("; MISSING meshes: %s" % missing) if missing else ""))


def build_props(world, actors):
    """Street furniture and street trees of each sector (Saved/Bay/sectors/<name>/props.json, from
    plan_props.py): one instanced actor per mesh. Furniture is solid; trees are solid too (a car stops at
    the trunk). Both stay out of ray tracing and distance fields and are culled with distance."""
    for name in sector_names():
        path = os.path.join(DATA, "sectors", name, "props.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            layout = json.load(f)
        folder = "Bay/Props/%s" % name
        removed = remove_actors(actors, [folder])
        placed, missing = {}, []
        for group, cull_cm in (("props", 60000.0), ("trees", 150000.0)):
            for mesh_path, rows in sorted(layout.get(group, {}).items()):
                mesh = assets.load_asset(mesh_path)
                if not mesh:
                    missing.append(mesh_path)
                    continue
                transforms = [unreal.Transform(location=unreal.Vector(x, y, z), rotation=rotator(yaw), scale=unreal.Vector(s, s, s))
                              for x, y, z, yaw, s in rows]
                label = "%s_%s" % (name, mesh_path.rsplit("/", 1)[-1])
                if unreal.WSPC2CityTools.spawn_instanced_meshes(world, mesh, transforms, True, False, label, folder, cull_cm, True):
                    placed[group] = placed.get(group, 0) + len(rows)
        log("props %s: %d old actors removed, %d furniture, %d trees%s" % (
            name, removed, placed.get("props", 0), placed.get("trees", 0), ("; MISSING meshes: %s" % missing) if missing else ""))


PROPS_FOLDER = "/Game/Bay/Props"
STOP_SIGN = PROPS_FOLDER + "/SM_Bay_StopSign"


def build_prop_assets():
    """Props the city makes itself (no pack has them), from Saved/Bay/props (stop_sign.py): the stop sign's texture,
    its material (an instance of the Bay ground master, the face sampled straight from the texture) and its mesh,
    in /Game/Bay/Props. plan_props.py places STOP_SIGN."""
    src = os.path.join(DATA, "props")
    tex_path = PROPS_FOLDER + "/T_Bay_StopSign"
    task = unreal.AssetImportTask()
    task.filename = os.path.join(src, "T_Bay_StopSign.png")
    task.destination_path = PROPS_FOLDER
    task.automated = True
    task.replace_existing = True
    task.save = True
    tools.import_asset_tasks([task])
    tex = assets.load_asset(tex_path)
    master = "%s/%s" % (BAY_MATERIALS, GROUND_MASTER)
    if not assets.does_asset_exist(master):
        build_materials()
    mi, mi_path = instance("MI_Bay_StopSign", master)
    if tex:
        mel.set_material_instance_texture_parameter_value(mi, "Albedo", tex)
    mel.set_material_instance_texture_parameter_value(mi, "Normal", assets.load_asset("/Engine/EngineMaterials/DefaultNormal"))
    for key, value in (("Tiling", 1.0), ("MacroLow", 1.0), ("MacroHigh", 1.0), ("RoughnessMin", 0.38), ("RoughnessMax", 0.55)):
        mel.set_material_instance_scalar_parameter_value(mi, key, value)
    mel.update_material_instance(mi)
    assets.save_asset(mi_path, only_if_is_dirty=False)
    folder = PROPS_FOLDER + "/StopSignImport"
    if assets.does_directory_exist(folder):
        assets.delete_directory(folder)
    task = unreal.AssetImportTask()
    task.filename = os.path.join(src, "SM_Bay_StopSign.glb")
    task.destination_path = folder
    task.automated = True
    task.replace_existing = True
    task.save = True
    tools.import_asset_tasks([task])
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.scan_paths_synchronous([folder], True)
    found = [d for d in registry.get_assets_by_path(folder, recursive=True) if str(d.asset_class_path.asset_name) == "StaticMesh"]
    if not found:
        log("propassets: MISSING the stop sign's mesh after importing %s" % task.filename)
        return
    if assets.does_asset_exist(STOP_SIGN):
        assets.delete_asset(STOP_SIGN)
    assets.rename_asset(str(found[0].package_name), STOP_SIGN)
    mesh = assets.load_asset(STOP_SIGN)
    settings = mesh.get_editor_property("nanite_settings")
    settings.enabled = False
    mesh.set_editor_property("nanite_settings", settings)
    for index in range(len(mesh.static_materials)):
        mesh.set_material(index, mi)
    body = mesh.get_editor_property("body_setup")
    if body:
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    assets.save_loaded_asset(mesh)
    assets.delete_directory(folder)
    bounds = mesh.get_bounds()
    log("propassets: %s (%d triangles, extent %.0f x %.0f x %.0f cm), texture %s, material %s" % (
        STOP_SIGN, mesh.get_num_triangles(0), bounds.box_extent.x * 2, bounds.box_extent.y * 2, bounds.box_extent.z * 2,
        "ok" if tex else "MISSING", mi_path))


TRAINING_FOLDER = "/Game/Bay/Training"
TRAINING_MESHES = ("SM_Bay_TrainingRamp", "SM_Bay_TrainingTarget")
TRAINING_SLOTS = {"Road": BAY_MATERIALS + "/MI_Bay_AsphaltMS", "PaintWhite": "/Game/City/Materials/M_Paint_White",
                  "PaintYellow": "/Game/City/Materials/M_Paint_Yellow", "Concrete": BAY_MATERIALS + "/MI_Bay_Concrete",
                  "Steel": BAY_MATERIALS + "/MI_Bay_Railing"}
LAYOUT_DIRECTOR = "/Script/WSPC2.WSPC2LayoutDirector"


def build_training(world, actors):
    """The layouts of the training ground (Saved/Bay/training/layouts.json, from plan_training.py): the ramp and the
    target (training_mesh.py) are imported into /Game/Bay/Training, and every layout's cones and pieces are placed
    as actors of their own in Bay/Training/<layout>, tagged "WSPC2Layout.<layout>" and hidden: the layout director
    placed with them (AWSPC2LayoutDirector) shows one layout when the game starts. Cones are movable and tagged
    "WSPC2Physics": the director lets the shown layout's cones simulate, so a car knocks them over."""
    path = os.path.join(DATA, "training", "layouts.json")
    removed = remove_actors(actors, ["Bay/Training"])
    if not os.path.exists(path):
        log("training: %d old actors removed; no %s (run plan_training.py)" % (removed, path))
        return
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not paint_ready():
        build_paint_materials()
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    for name in TRAINING_MESHES:
        source = os.path.join(DATA, "training", name + ".glb")
        if not os.path.exists(source):
            log("training: MISSING %s (run training_mesh.py)" % source)
            continue
        folder = "%s/%sImport" % (TRAINING_FOLDER, name)
        if assets.does_directory_exist(folder):
            assets.delete_directory(folder)
        task = unreal.AssetImportTask()
        task.filename = source
        task.destination_path = folder
        task.automated = True
        task.replace_existing = True
        task.save = True
        tools.import_asset_tasks([task])
        registry.scan_paths_synchronous([folder], True)
        found = [d for d in registry.get_assets_by_path(folder, recursive=True) if str(d.asset_class_path.asset_name) == "StaticMesh"]
        if not found:
            log("training: MISSING the mesh of %s after the import" % name)
            continue
        target = "%s/%s" % (TRAINING_FOLDER, name)
        if assets.does_asset_exist(target):
            assets.delete_asset(target)
        assets.rename_asset(str(found[0].package_name), target)
        mesh = assets.load_asset(target)
        settings = mesh.get_editor_property("nanite_settings")
        settings.enabled = False
        mesh.set_editor_property("nanite_settings", settings)
        precise_uvs(mesh)
        unknown = []
        for index, slot in enumerate(mesh.static_materials):
            material = assets.load_asset(TRAINING_SLOTS.get(str(slot.material_slot_name), ""))
            if material:
                mesh.set_material(index, material)
            else:
                unknown.append(str(slot.material_slot_name))
        body = mesh.get_editor_property("body_setup")
        if body:
            body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        assets.save_loaded_asset(mesh)
        assets.delete_directory(folder)
        bounds = mesh.get_bounds()
        log("training: %s, %d triangles, %.0f x %.0f x %.0f cm%s" % (
            target, mesh.get_num_triangles(0), bounds.box_extent.x * 2, bounds.box_extent.y * 2, bounds.box_extent.z * 2,
            ("; slots without a material: %s" % unknown) if unknown else ""))

    director_class = unreal.load_class(None, LAYOUT_DIRECTOR)
    if director_class:
        at = data["director"]
        director = actors.spawn_actor_from_class(director_class, unreal.Vector(at["x"], at["y"], at["z"]))
        director.set_actor_label("BayLayoutDirector")
        director.set_folder_path("Bay/Training")
    else:
        log("training: MISSING class %s (build the game module): the layouts will all stay hidden" % LAYOUT_DIRECTOR)
    meshes, missing = {}, set()
    for layout_name, layout in sorted(data["layouts"].items()):
        placed = 0
        for spec in layout["actors"]:
            if spec["mesh"] not in meshes:
                meshes[spec["mesh"]] = assets.load_asset(spec["mesh"])
            mesh = meshes[spec["mesh"]]
            if not mesh:
                missing.add(spec["mesh"])
                continue
            turn = rotator(spec["yaw"])
            turn.pitch = spec.get("pitch", 0.0)
            actor = actors.spawn_actor_from_object(mesh, unreal.Vector(spec["x"], spec["y"], spec["z"]), turn)
            s = spec.get("scale", 1.0)
            actor.set_actor_scale3d(unreal.Vector(s, s, s))
            actor.set_actor_label(spec["label"])
            actor.set_folder_path("Bay/Training/%s" % layout_name)
            tags = [data["tag_prefix"] + layout_name] + ([data["physics_tag"]] if spec.get("physics") else []) + list(spec.get("tags", []))
            actor.set_editor_property("tags", [unreal.Name(t) for t in tags])
            component = actor.static_mesh_component
            if spec.get("physics"):
                # movable, and its movement replicated, so the server's physics moves the cone on every machine (a
                # static mesh actor with this flag starts replicating by itself when play begins; "replicates"
                # cannot be set on a placed actor); it only starts to simulate when the director shows its layout
                component.set_mobility(unreal.ComponentMobility.MOVABLE)
                component.set_collision_profile_name("PhysicsActor")
                actor.set_editor_property("static_mesh_replicate_movement", True)
            actor.set_actor_hidden_in_game(True)
            placed += 1
        log("training %s (operation %02d): %d actors placed" % (layout_name, layout["operation"], placed))
    log("training: %d old actors removed, %d layouts%s" % (
        removed, len(data["layouts"]), ("; MISSING meshes: %s" % sorted(missing)) if missing else ""))


COUNTRY_CULL_CM = {"trees": 400000.0, "bushes": 120000.0}      # oaks on the hills read from across the bay


def build_country(world, actors):
    """Trees and shrubs of the country round the city (Saved/Bay/country/trees.json, from plan_country.py): one
    instanced actor per mesh and 1 km tile, so each tile culls and streams on its own. Trees are solid (a car stops
    at the trunk); shrubs are not. Both stay out of ray tracing and distance fields."""
    path = os.path.join(DATA, "country", "trees.json")
    removed = remove_actors(actors, ["Bay/Country"])
    if not os.path.exists(path):
        log("country: %d old actors removed; no %s (run plan_country.py)" % (removed, path))
        return
    with open(path) as f:
        layout = json.load(f)
    placed, missing, meshes = {}, set(), {}
    for tile, groups in sorted(layout["tiles"].items()):
        folder = "Bay/Country/%s" % tile
        for group in ("trees", "bushes"):
            for mesh_path, rows in sorted(groups.get(group, {}).items()):
                if mesh_path not in meshes:
                    meshes[mesh_path] = assets.load_asset(mesh_path)
                mesh = meshes[mesh_path]
                if not mesh:
                    missing.add(mesh_path)
                    continue
                transforms = [unreal.Transform(location=unreal.Vector(x, y, z), rotation=rotator(yaw), scale=unreal.Vector(s, s, s))
                              for x, y, z, yaw, s in rows]
                label = "Country_%s_%s" % (tile, mesh_path.rsplit("/", 1)[-1])
                if unreal.WSPC2CityTools.spawn_instanced_meshes(world, mesh, transforms, group == "trees", False, label, folder,
                                                                 COUNTRY_CULL_CM[group], True):
                    placed[group] = placed.get(group, 0) + len(rows)
    log("country: %d old actors removed, %d trees and %d shrubs in %d tiles%s" % (
        removed, placed.get("trees", 0), placed.get("bushes", 0), len(layout["tiles"]),
        ("; MISSING meshes: %s" % sorted(missing)) if missing else ""))


def build_sea(world, actors):
    """The sea: one flat sheet at 0 m, 16 km across. With Saved/Bay/sea/Sea.glb (sea_mesh.py) it is that mesh,
    which has a hole along every tunnel; without the file it is the engine's plane, and a tunnel that goes
    below sea level then shows water inside."""
    removed = remove_actors(actors, ["Bay/Water"])
    water = assets.load_asset(WATER_MATERIAL)
    folder = GENERATED + "/Sea"
    glb = os.path.join(DATA, "sea", "Sea.glb")
    sea, kind = None, "the engine's plane (no Sea.glb: tunnels below sea level will show water)"
    if assets.does_directory_exist(folder):
        assets.delete_directory(folder)
    if os.path.exists(glb):
        task = unreal.AssetImportTask()
        task.filename = glb
        task.destination_path = folder
        task.automated = True
        task.replace_existing = True
        task.save = True
        tools.import_asset_tasks([task])
        registry = unreal.AssetRegistryHelpers.get_asset_registry()
        registry.scan_paths_synchronous([folder], True)
        for data in registry.get_assets_by_path(folder, recursive=True):
            if str(data.asset_class_path.asset_name) != "StaticMesh":
                continue
            mesh = data.get_asset()
            settings = mesh.get_editor_property("nanite_settings")
            settings.enabled = False
            mesh.set_editor_property("nanite_settings", settings)
            precise_uvs(mesh)
            if water:
                for index in range(len(mesh.static_materials)):
                    mesh.set_material(index, water)
            assets.save_loaded_asset(mesh)
            sea = actors.spawn_actor_from_object(mesh, unreal.Vector(0, 0, 0))
            bounds = mesh.get_bounds()
            kind = "mesh %s, %d triangles, centre (%.0f, %.0f, %.0f) cm, extent (%.0f, %.0f, %.0f) cm" % (
                data.asset_name, mesh.get_num_triangles(0), bounds.origin.x, bounds.origin.y, bounds.origin.z,
                bounds.box_extent.x, bounds.box_extent.y, bounds.box_extent.z)
            break
    if sea is None:
        plane = assets.load_asset("/Engine/BasicShapes/Plane")
        sea = actors.spawn_actor_from_object(plane, unreal.Vector(80000.0, -27500.0, 0.0))     # centre of the map's frame
        sea.set_actor_scale3d(unreal.Vector(16000.0, 16000.0, 1.0))
        if water:
            sea.static_mesh_component.set_material(0, water)
    sea.set_actor_enable_collision(False)
    sea.set_actor_label("Sea")
    sea.set_folder_path("Bay/Water")
    log("sea: %d old actors removed; %s" % (removed, kind))


def build_light(world, actors):
    remove_actors(actors, ["Bay/Lighting", "Bay/Start"])
    for actor in actors.get_all_level_actors():
        if isinstance(actor, unreal.PlayerStart):
            actors.destroy_actor(actor)
    origin = unreal.Vector(0, 0, 0)
    sun_rot = unreal.Rotator(0, 0, 0)
    sun_rot.pitch, sun_rot.yaw = -48.0, -125.0
    sun = actors.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 30000), sun_rot)
    sun.set_actor_label("Sun")
    sun.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sun.light_component.set_editor_property("intensity", 3150.0)
    sun.light_component.set_editor_property("atmosphere_sun_light", True)
    sun.light_component.set_editor_property("dynamic_shadow_distance_movable_light", 60000.0)
    atmosphere = actors.spawn_actor_from_class(unreal.SkyAtmosphere, origin)
    atmosphere.set_actor_label("SkyAtmosphere")
    sky = actors.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 20000))
    sky.set_actor_label("SkyLight")
    sky.light_component.set_mobility(unreal.ComponentMobility.MOVABLE)
    sky.light_component.set_editor_property("real_time_capture", True)
    # between tall buildings a street only sees a strip of sky: the first city's sky light (1.0) left
    # shaded streets nearly black, so the sky counts for more here and the eye may open one more stop
    sky.light_component.set_editor_property("intensity", SKY_INTENSITY)
    fog = actors.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 500))
    fog.set_actor_label("Fog")
    fog.component.set_editor_property("fog_density", 0.0025)
    clouds = actors.spawn_actor_from_class(unreal.VolumetricCloud, origin)
    clouds.set_actor_label("Clouds")
    exposure = actors.spawn_actor_from_class(unreal.PostProcessVolume, origin)
    exposure.set_actor_label("Exposure")
    exposure.set_editor_property("unbound", True)
    settings = exposure.get_editor_property("settings")
    settings.set_editor_property("override_auto_exposure_min_brightness", True)
    settings.set_editor_property("auto_exposure_min_brightness", EXPOSURE_MIN_EV)
    settings.set_editor_property("override_auto_exposure_max_brightness", True)
    settings.set_editor_property("auto_exposure_max_brightness", EXPOSURE_MAX_EV)
    exposure.set_editor_property("settings", settings)
    for actor in (sun, atmosphere, sky, fog, clouds, exposure):
        actor.set_folder_path("Bay/Lighting")
    start = {"location": [150000.0, -22000.0, 600.0], "yaw": 0.0}
    start_file = os.path.join(DATA, "start.json")
    if os.path.exists(start_file):
        with open(start_file) as f:
            start = json.load(f)
    rot = unreal.Rotator(0, 0, 0)
    rot.yaw = start["yaw"]
    player_start = actors.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(*start["location"]), rot)
    player_start.set_actor_label("PlayerStart")
    player_start.set_folder_path("Bay/Start")
    log("player start at (%.0f, %.0f, %.0f) cm, yaw %.0f" % tuple(start["location"] + [start["yaw"]]))


REVIEW_FOLDER = "/Game/Bay/Review"
REVIEW_GAME_MODE = "BP_BayReviewGameMode"


def build_paint_materials():
    """Plain painted surfaces (a bridge's steel, railings): one small master, a colour, a roughness and a
    metallic value per instance; a slow world-space noise keeps large faces from looking flat."""
    path = "%s/%s" % (BAY_MATERIALS, PAINT_MASTER)
    mat = assets.load_asset(path) if assets.does_asset_exist(path) else \
        tools.create_asset(PAINT_MASTER, BAY_MATERIALS, unreal.Material, unreal.MaterialFactoryNew())
    mel.delete_all_material_expressions(mat)
    colour = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -700, -200)
    colour.set_editor_property("parameter_name", "Colour")
    colour.set_editor_property("default_value", unreal.LinearColor(0.5, 0.5, 0.5, 1.0))
    noise = mel.create_material_expression(mat, unreal.MaterialExpressionNoise, -700, 60)
    for key, value in (("scale", 0.004), ("quality", 1), ("levels", 2), ("turbulence", False), ("output_min", 0.86),
                       ("output_max", 1.05), ("noise_function", unreal.NoiseFunction.NOISEFUNCTION_GRADIENT_TEX)):
        noise.set_editor_property(key, value)
    base = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -420, -100)
    rough = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -420, 120)
    rough.set_editor_property("parameter_name", "Roughness")
    rough.set_editor_property("default_value", 0.5)
    metal = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -420, 220)
    metal.set_editor_property("parameter_name", "Metallic")
    metal.set_editor_property("default_value", 0.0)
    ok = [mel.connect_material_expressions(colour, "", base, "A"), mel.connect_material_expressions(noise, "", base, "B"),
          mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR),
          mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS),
          mel.connect_material_property(metal, "", unreal.MaterialProperty.MP_METALLIC)]
    mel.recompile_material(mat)
    assets.save_asset(path, only_if_is_dirty=False)
    for name, (rgb, roughness, metallic) in PAINT_INSTANCES.items():
        mi, mi_path = instance(name, path)
        mel.set_material_instance_vector_parameter_value(mi, "Colour", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0))
        mel.set_material_instance_scalar_parameter_value(mi, "Roughness", roughness)
        mel.set_material_instance_scalar_parameter_value(mi, "Metallic", metallic)
        mel.update_material_instance(mi)
        assets.save_asset(mi_path, only_if_is_dirty=False)
    # ...and the surfaces that give light: a colour and a luminance, unshaded by anything else
    glow_path = "%s/%s" % (BAY_MATERIALS, GLOW_MASTER)
    glow = assets.load_asset(glow_path) if assets.does_asset_exist(glow_path) else \
        tools.create_asset(GLOW_MASTER, BAY_MATERIALS, unreal.Material, unreal.MaterialFactoryNew())
    mel.delete_all_material_expressions(glow)
    tint = mel.create_material_expression(glow, unreal.MaterialExpressionVectorParameter, -700, -100)
    tint.set_editor_property("parameter_name", "Colour")
    tint.set_editor_property("default_value", unreal.LinearColor(1.0, 0.9, 0.7, 1.0))
    nits = mel.create_material_expression(glow, unreal.MaterialExpressionScalarParameter, -700, 120)
    nits.set_editor_property("parameter_name", "Luminance")
    nits.set_editor_property("default_value", 500.0)
    shine = mel.create_material_expression(glow, unreal.MaterialExpressionMultiply, -420, 0)
    ok += [mel.connect_material_expressions(tint, "", shine, "A"), mel.connect_material_expressions(nits, "", shine, "B"),
           mel.connect_material_property(shine, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR),
           mel.connect_material_property(tint, "", unreal.MaterialProperty.MP_BASE_COLOR)]
    mel.recompile_material(glow)
    assets.save_asset(glow_path, only_if_is_dirty=False)
    for name, (rgb, luminance) in GLOW_INSTANCES.items():
        mi, mi_path = instance(name, glow_path)
        mel.set_material_instance_vector_parameter_value(mi, "Colour", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0))
        mel.set_material_instance_scalar_parameter_value(mi, "Luminance", luminance)
        mel.update_material_instance(mi)
        assets.save_asset(mi_path, only_if_is_dirty=False)
    log("materials: paint master and %d instances, glow master and %d instances%s" % (
        len(PAINT_INSTANCES), len(GLOW_INSTANCES), "" if all(ok) else "; SOME CONNECTIONS FAILED"))


def paint_ready():
    """True when every painted and every glowing material this script knows of exists already."""
    return all(assets.does_asset_exist("%s/%s" % (BAY_MATERIALS, n)) for n in list(PAINT_INSTANCES) + list(GLOW_INSTANCES))


def structure_names():
    wanted = [s.strip() for s in os.environ.get("BAY_STRUCTURES", "").split(",") if s.strip()]
    folder = os.path.join(DATA, "structures")
    found = sorted(n for n in os.listdir(folder) if os.path.exists(os.path.join(folder, n, n + ".glb"))) \
        if os.path.isdir(folder) else []
    return [n for n in found if not wanted or n in wanted]


def build_structures(world, actors):
    """Bridges and tunnels (Saved/Bay/structures/<name>/<name>.glb, from span_mesh.py and tunnel_mesh.py) and
    the lamps along the bridges' decks."""
    if not paint_ready():
        build_paint_materials()
    slots = dict(SLOT_MATERIALS)
    slots.update(STRUCTURE_SLOTS)
    materials = {slot: assets.load_asset(path) for slot, path in slots.items()}
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    for name in structure_names():
        folder = "%s/%s" % (GENERATED, name)
        outliner = "Bay/Structures/%s" % name
        removed = remove_actors(actors, [outliner])
        if assets.does_directory_exist(folder):
            assets.delete_directory(folder)
        task = unreal.AssetImportTask()
        task.filename = os.path.join(DATA, "structures", name, name + ".glb")
        task.destination_path = folder
        task.automated = True
        task.replace_existing = True
        task.save = True
        tools.import_asset_tasks([task])
        registry.scan_paths_synchronous([folder], True)
        placed, unknown = 0, set()
        # (Nanite off for bridges and tunnels: long thin bodies seen from inside and beneath. A structure that is one
        # big building with tens of thousands of small faces, the stadium, asks for it with an empty file named
        # "nanite" in its folder)
        nanite = os.path.exists(os.path.join(DATA, "structures", name, "nanite"))
        for data in registry.get_assets_by_path(folder, recursive=True):
            if str(data.asset_class_path.asset_name) != "StaticMesh":
                continue
            mesh = data.get_asset()
            settings = mesh.get_editor_property("nanite_settings")
            settings.enabled = nanite
            mesh.set_editor_property("nanite_settings", settings)
            precise_uvs(mesh)
            for index, slot in enumerate(mesh.static_materials):
                slot_name = str(slot.material_slot_name)
                if materials.get(slot_name):
                    mesh.set_material(index, materials[slot_name])
                else:
                    unknown.add(slot_name)
            body = mesh.get_editor_property("body_setup")
            if body:
                body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
            assets.save_loaded_asset(mesh)
            actor = actors.spawn_actor_from_object(mesh, unreal.Vector(0, 0, 0))
            actor.set_actor_label(str(data.asset_name))
            actor.set_folder_path(outliner)
            bounds = mesh.get_bounds()
            log("structure %s: %s, %d triangles, centre (%.0f, %.0f, %.0f) cm, extent (%.0f, %.0f, %.0f) cm" % (
                name, data.asset_name, mesh.get_num_triangles(0), bounds.origin.x, bounds.origin.y, bounds.origin.z,
                bounds.box_extent.x, bounds.box_extent.y, bounds.box_extent.z))
            placed += 1
        lamps = 0
        props_path = os.path.join(DATA, "structures", name, "props.json")
        if os.path.exists(props_path):
            with open(props_path) as f:
                layout = json.load(f)
            for mesh_path, rows in sorted(layout.get("props", {}).items()):
                mesh = assets.load_asset(mesh_path)
                if not mesh:
                    log("structure %s: MISSING mesh %s" % (name, mesh_path))
                    continue
                transforms = [unreal.Transform(location=unreal.Vector(x, y, z), rotation=rotator(yaw), scale=unreal.Vector(s, s, s))
                              for x, y, z, yaw, s in rows]
                if unreal.WSPC2CityTools.spawn_instanced_meshes(world, mesh, transforms, True, False,
                                                                "%s_%s" % (name, mesh_path.rsplit("/", 1)[-1]), outliner, 150000.0, True):
                    lamps += len(rows)
            lights = spawn_spot_lights(actors, name, outliner + "/Lights", layout.get("light", {}), layout.get("lights", []))
        else:
            lights = 0
        log("structure %s: %d old actors removed, %d meshes placed, %d lamps, %d lights%s" % (
            name, removed, placed, lamps, lights, ("; slots without a material: %s" % sorted(unknown)) if unknown else ""))


def spawn_spot_lights(actors, name, outliner, spec, places):
    """A structure's own lights (a tunnel's lamps): spot lights pointing straight down, so nothing above them is
    lit, without shadows and fully dynamic, so they cost little; not drawn from far away. places: [x, y, z] in cm."""
    down = unreal.Rotator()
    down.pitch = -90.0
    rgb = spec.get("colour", [1.0, 1.0, 1.0])
    count = 0
    for index, (x, y, z) in enumerate(places):
        actor = actors.spawn_actor_from_class(unreal.SpotLight, unreal.Vector(x, y, z), down)
        light = actor.get_component_by_class(unreal.SpotLightComponent)
        if not light:
            actors.destroy_actor(actor)
            continue
        light.set_mobility(unreal.ComponentMobility.MOVABLE)
        light.set_editor_property("intensity_units", unreal.LightUnits.CANDELAS)
        light.set_editor_property("intensity", float(spec.get("candela", 5000.0)))
        light.set_editor_property("attenuation_radius", float(spec.get("radius_m", 16.0)) * 100.0)
        light.set_editor_property("inner_cone_angle", float(spec.get("inner_deg", 55.0)))
        light.set_editor_property("outer_cone_angle", float(spec.get("outer_deg", 80.0)))
        light.set_editor_property("cast_shadows", False)
        light.set_editor_property("max_draw_distance", 35000.0)
        light.set_editor_property("max_distance_fade_range", 5000.0)
        light.set_light_color(unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0))
        actor.set_actor_label("%s_Light_%02d" % (name, index))
        actor.set_folder_path(outliner)
        count += 1
    return count


def build_review_mode():
    """A game mode for the camera tours: a child of the game's own game mode Blueprint (so its player
    controller, which carries the -WSPC2Views hook, is used; the C++ classes are abstract), but with no
    pawn. The pictures then do not depend on the patrol car.
    tour.ps1 selects it with ?game=/Game/Bay/Review/BP_BayReviewGameMode.BP_BayReviewGameMode_C"""
    path = "%s/%s" % (REVIEW_FOLDER, REVIEW_GAME_MODE)
    parent = assets.load_blueprint_class(GAME_MODE)
    if not parent:
        raise RuntimeError("missing game mode " + GAME_MODE)
    if assets.does_asset_exist(path):
        # deleting and recreating an asset of the same name in one run fails: keep it and change its parent
        blueprint = assets.load_asset(path)
        unreal.BlueprintEditorLibrary.reparent_blueprint(blueprint, parent)
    else:
        factory = unreal.BlueprintFactory()
        factory.set_editor_property("parent_class", parent)
        blueprint = tools.create_asset(REVIEW_GAME_MODE, REVIEW_FOLDER, unreal.Blueprint, factory)
    if not blueprint:
        raise RuntimeError("could not create " + path)
    unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    defaults = unreal.get_default_object(blueprint.generated_class())
    defaults.set_editor_property("default_pawn_class", None)
    unreal.BlueprintEditorLibrary.compile_blueprint(blueprint)
    assets.save_asset(path, only_if_is_dirty=False)
    controller = defaults.get_editor_property("player_controller_class")
    log("review game mode ready: %s (parent %s, controller %s, no pawn)" % (
        path, parent.get_name(), controller.get_name() if controller else "none"))


def inspect_materials():
    for path in INSPECT:
        material = assets.load_asset(path)
        if not material:
            log("inspect: missing %s" % path)
            continue
        base = material
        while isinstance(base, unreal.MaterialInstance):
            base = base.get_editor_property("parent")
        log("inspect %s (base %s)" % (path, base.get_path_name() if base else "?"))
        for kind, getter in (("texture", mel.get_texture_parameter_names), ("scalar", mel.get_scalar_parameter_names),
                             ("vector", mel.get_vector_parameter_names), ("switch", mel.get_static_switch_parameter_names)):
            names = sorted(str(n) for n in getter(base))
            log("inspect   %s: %s" % (kind, ", ".join(names)))


def main():
    todo = stages()
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if todo == ["inspect"]:
        inspect_materials()
        return
    if todo == ["lawn"]:
        # on its own, before any map is loaded, and in a commandlet (build.ps1 -Stages lawn -Commandlet): giving
        # MI_Bay_Grass another parent while the open map draws lawns with it stops the editor on an assertion of the
        # renderer ("UniformExpressionCache should be up to date", 2026-11-19)
        lawn_master()
        return
    if assets.does_asset_exist(MAP):
        if not levels.load_level(MAP):
            raise RuntimeError("could not load " + MAP)
    elif not levels.new_level(MAP):
        raise RuntimeError("could not create " + MAP)
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    game_mode = assets.load_blueprint_class(GAME_MODE)
    if game_mode:
        world.get_world_settings().set_editor_property("default_game_mode", game_mode)
    if "inspect" in todo:
        inspect_materials()
    if "review" in todo:
        build_review_mode()
    # sectors that no longer exist (BAY_REMOVE, a comma list): their actors and their imported meshes go
    for gone in [s.strip() for s in os.environ.get("BAY_REMOVE", "").split(",") if s.strip()]:
        removed = remove_actors(actors, ["Bay/Sectors/%s" % gone, "Bay/Buildings/%s" % gone, "Bay/Props/%s" % gone])
        if assets.does_directory_exist("%s/%s" % (GENERATED, gone)):
            assets.delete_directory("%s/%s" % (GENERATED, gone))
        log("sector %s removed from the map: %d actors" % (gone, removed))
    if "materials" in todo:
        build_materials()
        build_paint_materials()
        wild_master()
        lawn = assets.load_asset("%s/%s" % (BAY_MATERIALS, LAWN_INSTANCE))
        if not lawn or not lawn.get_editor_property("parent") or lawn.get_editor_property("parent").get_name() != LAWN_MASTER:
            log("lawn: %s is not an instance of %s yet; run build.ps1 -Stages lawn -Commandlet" % (LAWN_INSTANCE, LAWN_MASTER))
    if "propassets" in todo:
        build_prop_assets()
    if "ground" in todo:
        build_ground(world, actors)
    if "sectors" in todo:
        build_sectors(world, actors)
    if "buildings" in todo:
        build_buildings(world, actors)
    if "props" in todo:
        build_props(world, actors)
    if "structures" in todo:
        build_structures(world, actors)
    if "sea" in todo:
        build_sea(world, actors)
    if "country" in todo:
        build_country(world, actors)
    if "training" in todo:
        build_training(world, actors)
    if "light" in todo:
        build_light(world, actors)
    if not levels.save_current_level():
        raise RuntimeError("could not save the level")
    log("saved %s with %d actors (stages: %s)" % (MAP, len(actors.get_all_level_actors()), ", ".join(todo)))


try:
    main()
    log("DONE")
except Exception as error:
    log("FAILED %r" % (error,))
    raise
finally:
    unreal.SystemLibrary.quit_editor()
