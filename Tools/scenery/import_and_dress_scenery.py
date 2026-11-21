"""Imports all prepared scenery GLBs from ASSETS TO USE/02_Cenario_Preparados/ into
/Game/Scenery/Imported/ (git-ignored) in Unreal Engine 5.8, creates custom Quixel
Megascans / OvergrownFactoryENV / Downtown_West / CityPark PBR MaterialInstances, and
dresses:
  - Nuclear Power Plant (CoolingTower, ReactorDome, TurbineHall) with weathered Quixel
    8K concrete, bottom-dirt grunge, rusted steel & industrial cladding
  - Port of Oakland STS Gantry Crane (SM_Port_STSCrane, from crane_harbour.glb) with
    weathered marine painted steel, oxidized orange boom accents, rusty bogies & dusty glass
  - Intermodal Container Well-Cars (Single & Double-Stack) + 5 container livery variants
  - 4 Suburban Houses + 16 ready-to-place color/wall/roof MaterialInstance variants using
    Quixel Megascans 4K Stucco, Downtown_West Plaster/Brick/WoodTrim & CityPark RoofTiles

Run with the editor closed:
  UnrealEditor-Cmd.exe WSPC2.uproject -run=pythonscript -script=Tools/scenery/import_and_dress_scenery.py -unattended -nop4 -nosplash -nosound -nullrhi

Inputs:
  ASSETS TO USE/02_Cenario_Preparados/manifest.json
  ASSETS TO USE/02_Cenario_Preparados/<Category>/*.glb

Outputs:
  /Game/Scenery/Imported/Materials/MI_*
  /Game/Scenery/Imported/<Category>/*
  /Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_House*_Var* (16 variants)
  /Game/Scenery/Imported/06_Ferrovia_Vagoes/Variants/SM_Rail_WellCar_*_Var* (5 variants)
"""
import json
import os
import unreal

PROJECT_DIR = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
PREP_ROOT = os.path.join(PROJECT_DIR, "ASSETS TO USE", "02_Cenario_Preparados")
MANIFEST_PATH = os.path.join(PREP_ROOT, "manifest.json")

DEST_ROOT = "/Game/Scenery/Imported"
MAT_DIR = f"{DEST_ROOT}/Materials"

TRANSLUCENT_MODES = {
    unreal.BlendMode.BLEND_TRANSLUCENT,
    unreal.BlendMode.BLEND_ALPHA_COMPOSITE,
    unreal.BlendMode.BLEND_ADDITIVE,
}

EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
ATOOLS = unreal.AssetToolsHelpers.get_asset_tools()
REGISTRY = unreal.AssetRegistryHelpers.get_asset_registry()


def load_mat(path: str):
    m = EAL.load_asset(path)
    if not m:
        unreal.log_warning(f"WSPC2SCENERY missing material: {path}")
    return m


def load_tex(path: str):
    t = EAL.load_asset(path)
    if not t:
        unreal.log_warning(f"WSPC2SCENERY missing texture: {path}")
    return t


def make_mi(name: str, parent_path: str, scalars=None, vectors=None, textures=None):
    """Creates or updates a MaterialInstanceConstant under /Game/Scenery/Imported/Materials/."""
    full_path = f"{MAT_DIR}/{name}"
    parent = load_mat(parent_path)
    if not parent:
        return None
    mi = EAL.load_asset(full_path)
    if not mi:
        factory = unreal.MaterialInstanceConstantFactoryNew()
        mi = ATOOLS.create_asset(name, MAT_DIR, unreal.MaterialInstanceConstant, factory)
    if not mi:
        unreal.log_warning(f"WSPC2SCENERY failed creating MI: {full_path}")
        return None
    MEL.set_material_instance_parent(mi, parent)
    for k, v in (scalars or {}).items():
        MEL.set_material_instance_scalar_parameter_value(mi, k, float(v))
    for k, v in (vectors or {}).items():
        MEL.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(v[0], v[1], v[2], v[3]))
    for k, tp in (textures or {}).items():
        tex = load_tex(tp)
        if tex:
            MEL.set_material_instance_texture_parameter_value(mi, k, tex)
    MEL.update_material_instance(mi)
    EAL.save_asset(full_path, only_if_is_dirty=False)
    return mi


def import_glb(src_file: str, dest_dir: str):
    task = unreal.AssetImportTask()
    task.filename = src_file
    task.destination_path = dest_dir
    task.automated = True
    task.replace_existing = True
    task.save = True
    ATOOLS.import_asset_tasks([task])
    return list(task.imported_object_paths)


def find_static_mesh(dest_dir: str, asset_stem: str):
    for data in REGISTRY.get_assets_by_path(dest_dir, recursive=True):
        if str(data.asset_class_path.asset_name) == "StaticMesh":
            if str(data.asset_name) == asset_stem:
                return data.get_asset()
    # fallback: first static mesh under dest_dir
    for data in REGISTRY.get_assets_by_path(dest_dir, recursive=True):
        if str(data.asset_class_path.asset_name) == "StaticMesh":
            return data.get_asset()
    return None


def apply_slot_map(mesh, slot_map: dict):
    """Replaces StaticMesh materials by matching material slot name or assigned material name."""
    if not mesh:
        return 0
    changed = 0
    for idx, smat in enumerate(mesh.static_materials):
        sname = str(smat.material_slot_name)
        mname = smat.material_interface.get_name() if smat.material_interface else ""
        target = slot_map.get(sname) or slot_map.get(mname)
        if not target:
            # try case-insensitive substring fallback for exact keys
            sl, ml = sname.lower(), mname.lower()
            for k, v in slot_map.items():
                kl = k.lower()
                if kl == sl or kl == ml or kl in sl or kl in ml:
                    target = v
                    break
        if target:
            mesh.set_material(idx, target)
            changed += 1
    return changed


def configure_nanite_and_save(mesh, asset_path: str):
    if not mesh:
        return
    translucent = []
    for idx, smat in enumerate(mesh.static_materials):
        mi = smat.material_interface
        if not mi:
            continue
        is_tr = False
        try:
            if mi.get_blend_mode() in TRANSLUCENT_MODES:
                is_tr = True
        except Exception:
            pass
        try:
            base = mi.get_base_material()
            if base and base.get_blend_mode() in TRANSLUCENT_MODES:
                is_tr = True
        except Exception:
            pass
        if is_tr:
            translucent.append(f"{idx}:{mi.get_name()}")
    ns = mesh.get_editor_property("nanite_settings")
    if translucent:
        ns.enabled = False
    else:
        ns.enabled = True
    mesh.set_editor_property("nanite_settings", ns)
    EAL.save_asset(asset_path, only_if_is_dirty=False)
    b = mesh.get_bounds()
    dims = [round(b.box_extent.x * 2, 1), round(b.box_extent.y * 2, 1), round(b.box_extent.z * 2, 1)]
    tris = max(mesh.get_num_triangles(0), mesh.get_num_nanite_triangles())
    unreal.log(f"WSPC2SCENERY verified {mesh.get_name():34s} tris={tris:6d} mats={len(mesh.static_materials):2d} nanite={bool(ns.enabled)} dims_cm={dims} tr={translucent}")


def build_material_library():
    """Creates custom Quixel Megascans / AAA PBR MaterialInstances for Nuclear Plant,
    Port STS Crane, Intermodal Rail Cars, and Suburban House variations."""
    EAL.make_directory(MAT_DIR)
    M = {}

    # --- 1. NUCLEAR POWER PLANT MATERIALS (OvergrownFactoryENV BottomDirt + Scene_Warehouse Quixel Concrete/Rust) ---
    # Cooling tower & reactor shell: OvergrownFactoryENV ConcreteGrunge with large tiling (0.35) to avoid banding on 92m shells
    M["nuc_concrete_shell"] = make_mi(
        "MI_WSPC2_Nuclear_ConcreteShell",
        "/Game/OvergrownFactoryENV/Material/MI_ConcreteGrunge",
        scalars={"BaseLayer_Tiling": 0.35, "BaseLayer_B_Brightness": 0.90, "BaseLayer_B_Contrast": 1.08, "BaseLayer_Rough Intensity": 1.15},
        vectors={
            "BaseLayer_Tint": (0.86, 0.84, 0.80, 1.0),
            "BottomDirtColor": (0.14, 0.13, 0.11, 1.0),
            "MossColor": (0.16, 0.19, 0.12, 1.0),
        },
    )
    # Matte structural concrete (raker columns, basin, buttresses, plinths) inheriting Quixel Facade Concrete (proper ARD/Normal)
    M["nuc_concrete_quixel8k"] = make_mi(
        "MI_WSPC2_Nuclear_QuixelConcreteDark",
        "/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Wall_Facade_Concrete_New_01/MI_Ind_War_Wall_Facade_Concrete_New_01_A",
        scalars={"Min Roughness": 0.65, "Max Roughness": 0.95, "Normal Strength": 1.25},
        vectors={"Albedo Tint": (0.58, 0.56, 0.53, 1.0)},
    )
    M["nuc_cladding"] = make_mi(
        "MI_WSPC2_Nuclear_MetalCladding",
        "/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Roof_Painted_01/MI_Ind_War_Roof_Painted_01",
        scalars={"Min Roughness": 0.45, "Max Roughness": 0.85, "Normal Strength": 1.2},
        vectors={"Albedo Tint": (0.68, 0.72, 0.74, 1.0)},
    )
    M["nuc_rust"] = load_mat("/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Sheet_Metal_Rusty_01/MI_Ind_War_Sheet_Metal_Rusty_01_A")
    # Clean industrial steel pipe/stack shader without yellow trimsheet bands
    M["nuc_pipes"] = make_mi(
        "MI_WSPC2_Nuclear_PipeSteel",
        "/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Roof_Painted_01/MI_Ind_War_Roof_Painted_01",
        scalars={"Min Roughness": 0.42, "Max Roughness": 0.78, "Normal Strength": 1.15},
        vectors={"Albedo Tint": (0.54, 0.56, 0.58, 1.0)},
    )
    M["nuc_roof"] = load_mat("/Game/OvergrownFactoryENV/Material/MI_FactoryRoof")
    M["nuc_glass"] = load_mat("/Game/OvergrownFactoryENV/Material/MI_GlassWindow")

    # --- 2. PORT OF OAKLAND STS CRANE MATERIALS (Quixel Painted Roof/Steel + Rust + Machinery) ---
    M["crane_painted_blue"] = make_mi(
        "MI_WSPC2_PortCrane_OaklandBlueGrey",
        "/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Roof_Painted_01/MI_Ind_War_Roof_Painted_01",
        scalars={"Min Roughness": 0.48, "Max Roughness": 0.84, "Normal Strength": 1.2},
        vectors={"Albedo Tint": (0.42, 0.56, 0.66, 1.0)},
    )
    M["crane_accent_orange"] = make_mi(
        "MI_WSPC2_PortCrane_MaritimeOrange",
        "/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Sheet_Metal_Rusty_01/MI_Ind_War_Sheet_Metal_Rusty_01_A",
        scalars={"Min Roughness": 0.45, "Max Roughness": 0.80, "Normal Strength": 1.15},
        vectors={"Albedo Tint": (0.95, 0.36, 0.18, 1.0)},
    )
    M["crane_safety_yellow"] = make_mi(
        "MI_WSPC2_PortCrane_SafetyYellow",
        "/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Roof_Painted_01/MI_Ind_War_Roof_Painted_01",
        scalars={"Min Roughness": 0.45, "Max Roughness": 0.78, "Normal Strength": 1.1},
        vectors={"Albedo Tint": (0.95, 0.74, 0.16, 1.0)},
    )
    M["crane_wheels_rust"] = load_mat("/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Sheet_Metal_Rusty_01/MI_Ind_War_Sheet_Metal_Rusty_01_B")
    M["crane_machinery"] = make_mi(
        "MI_WSPC2_PortCrane_MachinerySteel",
        "/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Sheet_Metal_Rusty_01/MI_Ind_War_Sheet_Metal_Rusty_01_A",
        scalars={"Min Roughness": 0.45, "Max Roughness": 0.80, "Normal Strength": 1.1},
        vectors={"Albedo Tint": (0.35, 0.37, 0.40, 1.0)},
    )
    M["crane_glass"] = load_mat("/Game/OvergrownFactoryENV/Material/MI_GlassWindow")

    # --- 3. INTERMODAL RAIL WELL-CAR & SHIPPING CONTAINER LIVERIES ---
    M["rail_well_ochre"] = make_mi(
        "MI_WSPC2_Rail_WellCarTTX",
        "/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Sheet_Metal_Rusty_01/MI_Ind_War_Sheet_Metal_Rusty_01_A",
        scalars={"Normal Strength": 1.2, "Max Roughness": 0.80},
        vectors={"Albedo Tint": (0.88, 0.64, 0.22, 1.0)},
    )
    M["rail_bogie_rust"] = load_mat("/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Sheet_Metal_Rusty_01/MI_Ind_War_Sheet_Metal_Rusty_01_B")
    M["rail_wheel_steel"] = make_mi(
        "MI_WSPC2_Rail_WheelSteel",
        "/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Sheet_Metal_Rusty_01/MI_Ind_War_Sheet_Metal_Rusty_01_A",
        scalars={"Min Roughness": 0.35, "Max Roughness": 0.72},
        vectors={"Albedo Tint": (0.42, 0.42, 0.44, 1.0)},
    )
    # 5 seamless weathered container liveries (Quixel painted/rusty metal so real 3D container ribs don't get trimsheet seams)
    M["cont_red"] = make_mi(
        "MI_WSPC2_Container_RedRust",
        "/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Roof_Painted_01/MI_Ind_War_Roof_Painted_01",
        scalars={"Min Roughness": 0.55, "Max Roughness": 0.88, "Normal Strength": 1.1},
        vectors={"Albedo Tint": (0.64, 0.18, 0.14, 1.0)},
    )
    M["cont_navy"] = make_mi(
        "MI_WSPC2_Container_NavyBlue",
        "/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Roof_Painted_01/MI_Ind_War_Roof_Painted_01",
        scalars={"Min Roughness": 0.55, "Max Roughness": 0.88, "Normal Strength": 1.1},
        vectors={"Albedo Tint": (0.16, 0.28, 0.48, 1.0)},
    )
    M["cont_green"] = make_mi(
        "MI_WSPC2_Container_Evergreen",
        "/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Roof_Painted_01/MI_Ind_War_Roof_Painted_01",
        scalars={"Min Roughness": 0.55, "Max Roughness": 0.88, "Normal Strength": 1.1},
        vectors={"Albedo Tint": (0.16, 0.38, 0.24, 1.0)},
    )
    M["cont_ochre"] = make_mi(
        "MI_WSPC2_Container_IndustrialOchre",
        "/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Roof_Painted_01/MI_Ind_War_Roof_Painted_01",
        scalars={"Min Roughness": 0.55, "Max Roughness": 0.88, "Normal Strength": 1.1},
        vectors={"Albedo Tint": (0.72, 0.50, 0.18, 1.0)},
    )
    M["cont_grey"] = make_mi(
        "MI_WSPC2_Container_WeatheredGrey",
        "/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Roof_Painted_01/MI_Ind_War_Roof_Painted_01",
        scalars={"Min Roughness": 0.55, "Max Roughness": 0.88, "Normal Strength": 1.1},
        vectors={"Albedo Tint": (0.50, 0.52, 0.54, 1.0)},
    )

    # --- 4. SUBURBAN HOUSE VARIATIONS (Downtown_West Stucco/Plaster/Brick/WoodTrim + CityPark matte RoofTiles) ---
    # Using MI_Building_Stucco (M_Buildings_Master) instead of M_MS_Srf guarantees proper Roughness/Normal with world noise!
    M["wall_stucco_cream"] = make_mi(
        "MI_WSPC2_HouseWall_StuccoCream",
        "/Game/Downtown_West/Materials/Buildings_Shared/MI_Building_Stucco",
        scalars={"Texture1_Tiling": 1.0, "Albedo_Brightness": 1.05, "Normal_Intensity": 1.1},
        vectors={"Albedo_1_ColorOverlay": (0.94, 0.88, 0.76, 1.0)},
    )
    M["wall_stucco_sage"] = make_mi(
        "MI_WSPC2_HouseWall_StuccoSage",
        "/Game/Downtown_West/Materials/Buildings_Shared/MI_Building_Stucco",
        scalars={"Texture1_Tiling": 1.0, "Albedo_Brightness": 0.95, "Normal_Intensity": 1.1},
        vectors={"Albedo_1_ColorOverlay": (0.62, 0.72, 0.62, 1.0)},
    )
    M["wall_stucco_coastalblue"] = make_mi(
        "MI_WSPC2_HouseWall_StuccoBlue",
        "/Game/Downtown_West/Materials/Buildings_Shared/MI_Building_Stucco",
        scalars={"Texture1_Tiling": 1.0, "Albedo_Brightness": 0.95, "Normal_Intensity": 1.1},
        vectors={"Albedo_1_ColorOverlay": (0.54, 0.66, 0.78, 1.0)},
    )
    M["wall_stucco_terracotta"] = make_mi(
        "MI_WSPC2_HouseWall_StuccoTerracotta",
        "/Game/Downtown_West/Materials/Buildings_Shared/MI_Building_Stucco",
        scalars={"Texture1_Tiling": 1.0, "Albedo_Brightness": 0.95, "Normal_Intensity": 1.1},
        vectors={"Albedo_1_ColorOverlay": (0.85, 0.56, 0.44, 1.0)},
    )
    M["wall_stucco_white"] = make_mi(
        "MI_WSPC2_HouseWall_StuccoWhite",
        "/Game/Downtown_West/Materials/Buildings_Shared/MI_Building_Stucco_White",
        scalars={"Texture1_Tiling": 1.0, "Albedo_Brightness": 1.0, "Normal_Intensity": 1.1},
        vectors={"Albedo_1_ColorOverlay": (0.92, 0.90, 0.86, 1.0)},
    )
    # Downtown_West & CityPark wall materials (Plaster, Bricks, Sandstone, Wood Trim)
    M["wall_dw_plaster_a"] = load_mat("/Game/Downtown_West/Materials/Buildings_Shared/MI_Building_Plaster_A")
    M["wall_dw_plaster_c"] = load_mat("/Game/Downtown_West/Materials/Buildings_Shared/MI_Building_Plaster_C")
    M["wall_dw_sandstone"] = load_mat("/Game/Downtown_West/Materials/Buildings_Shared/MI_Building_SandstoneRed_beige")
    M["wall_dw_brick_brown"] = load_mat("/Game/Downtown_West/Materials/Buildings_Shared/MI_Building_Bricks_A_brown")
    M["wall_dw_brick_red"] = load_mat("/Game/Downtown_West/Materials/Buildings_Shared/MI_Building_Bricks_A_red")
    M["wall_cp_4"] = make_mi(
        "MI_WSPC2_HouseWall_CityParkTan",
        "/Game/CityPark/Materials/Buildings/MI_Wall02_4",
        scalars={"Metallic": 0.0, "Roughness": 0.82, "spec": 0.2},
    )

    # Matte Roof Tiles (fix CityPark defaults Roughness=0.0 & Metallic=0.3 that caused plastic/metallic glare!)
    M["roof_slate_dark"] = make_mi(
        "MI_WSPC2_Roof_CharcoalSlate",
        "/Game/CityPark/Materials/Buildings/MI_RoofTile01_1",
        scalars={"Metallic": 0.0, "Roughness": 0.88, "spec": 0.22},
        vectors={"diffuse color": (0.28, 0.29, 0.32, 1.0)},
    )
    M["roof_brown_2"] = make_mi(
        "MI_WSPC2_Roof_WarmBrown",
        "/Game/CityPark/Materials/Buildings/MI_RoofTile01_2",
        scalars={"Metallic": 0.0, "Roughness": 0.88, "spec": 0.22},
        vectors={"diffuse color": (0.42, 0.30, 0.22, 1.0)},
    )
    M["roof_terra_1"] = make_mi(
        "MI_WSPC2_Roof_Terracotta",
        "/Game/CityPark/Materials/Buildings/MI_RoofTile02_1",
        scalars={"Metallic": 0.0, "Roughness": 0.86, "spec": 0.25},
        vectors={"diffuse color": (0.58, 0.32, 0.22, 1.0)},
    )
    M["roof_grey_3"] = make_mi(
        "MI_WSPC2_Roof_WeatheredGrey",
        "/Game/CityPark/Materials/Buildings/MI_RoofTile01_1",
        scalars={"Metallic": 0.0, "Roughness": 0.90, "spec": 0.20},
        vectors={"diffuse color": (0.50, 0.50, 0.52, 1.0)},
    )
    M["roof_red_4"] = make_mi(
        "MI_WSPC2_Roof_RustRed",
        "/Game/CityPark/Materials/Buildings/MI_RoofTile02_4",
        scalars={"Metallic": 0.0, "Roughness": 0.86, "spec": 0.25},
        vectors={"diffuse color": (0.48, 0.22, 0.18, 1.0)},
    )

    # Trims (Downtown_West painted wood trims)
    M["trim_white"] = load_mat("/Game/Downtown_West/Materials/Buildings_Shared/MI_Trim_Wood_Metal_White")
    M["trim_brown"] = load_mat("/Game/Downtown_West/Materials/Buildings_Shared/MI_Building_Wood_Trim_Brown")
    M["trim_darkgrey"] = load_mat("/Game/Downtown_West/Materials/Buildings_Shared/MI_Building_Wood_Trim_DarkGrey")
    M["trim_blue"] = load_mat("/Game/Downtown_West/Materials/Buildings_Shared/MI_Building_Wood_Trim_Blue")
    M["trim_green"] = load_mat("/Game/Downtown_West/Materials/Buildings_Shared/MI_Building_Wood_Trim_darkerGreen")

    return M


def create_variant(base_mesh_path: str, variant_path: str, slot_map: dict):
    """Duplicates a StaticMesh asset cleanly, applies material overrides, and saves."""
    if EAL.does_asset_exist(variant_path):
        EAL.delete_asset(variant_path)
    ok = EAL.duplicate_asset(base_mesh_path, variant_path)
    if not ok:
        unreal.log_warning(f"WSPC2SCENERY failed duplicating {base_mesh_path} -> {variant_path}")
        return None
    mesh = EAL.load_asset(variant_path)
    n = apply_slot_map(mesh, slot_map)
    configure_nanite_and_save(mesh, variant_path)
    unreal.log(f"WSPC2SCENERY variant {variant_path.split('/')[-1]:36s} swapped={n} slots")
    return mesh


def main():
    if not os.path.exists(MANIFEST_PATH):
        unreal.log_error("WSPC2SCENERY missing manifest: " + MANIFEST_PATH)
        return

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        entries = json.load(f)

    # 1. Build our Quixel / AAA MaterialInstance library first
    M = build_material_library()

    # 2. Import all 20 prepared GLBs cleanly under /Game/Scenery/Imported/<Category>/<Id>
    imported_meshes = {}
    for item in entries:
        vid = item["id"]
        cat = item["cat"]
        src_file = os.path.join(PREP_ROOT, item["file"].replace("/", os.sep))
        if not os.path.exists(src_file):
            unreal.log_warning("WSPC2SCENERY missing GLB: " + src_file)
            continue
        dest_dir = f"{DEST_ROOT}/{cat}/{vid}"
        import_glb(src_file, dest_dir)
        mesh = find_static_mesh(dest_dir, vid)
        if mesh:
            imported_meshes[vid] = (mesh, mesh.get_path_name().split(".")[0])

    # 3. Dress Nuclear Power Plant assets with Quixel 8K Concrete + OvergrownFactoryENV BottomDirt + Rust
    nuclear_slots = {
        "M_Nuclear_ConcreteDirty": M["nuc_concrete_shell"],
        "M_Nuclear_ConcreteDark":  M["nuc_concrete_quixel8k"],
        "M_Nuclear_MetalCladding": M["nuc_cladding"],
        "M_Nuclear_SteelRusted":   M["nuc_rust"],
        "M_Nuclear_PipeSteel":     M["nuc_pipes"],
        "M_Nuclear_RoofMetal":     M["nuc_roof"],
        "M_Nuclear_Glass":         M["nuc_glass"],
    }
    for nid in ("SM_Nuclear_CoolingTower", "SM_Nuclear_ReactorDome", "SM_Nuclear_TurbineHall"):
        if nid in imported_meshes:
            mesh, mpath = imported_meshes[nid]
            n = apply_slot_map(mesh, nuclear_slots)
            configure_nanite_and_save(mesh, mpath)
            unreal.log(f"WSPC2SCENERY dressed {nid} ({n} Quixel/AAA slots)")

    # 4. Dress Port of Oakland STS Gantry Crane (reused crane_harbour.glb)
    if "SM_Port_STSCrane" in imported_meshes:
        mesh, mpath = imported_meshes["SM_Port_STSCrane"]
        crane_slots = {
            "M_Crane_PaintedSteel":  M["crane_painted_blue"],
            "M_Crane_AccentSteel":   M["crane_accent_orange"],
            "M_Crane_DarkMachinery": M["crane_machinery"],
            "M_Crane_WheelsSteel":   M["crane_wheels_rust"],
            "M_Crane_TrimSteel":     M["crane_safety_yellow"],
            "M_Crane_CabGlass":      M["crane_glass"],
        }
        n = apply_slot_map(mesh, crane_slots)
        configure_nanite_and_save(mesh, mpath)
        unreal.log(f"WSPC2SCENERY dressed SM_Port_STSCrane ({n} Quixel/AAA slots)")

    # 5. Dress Intermodal Well-Cars + create 5 ready-to-place livery variants
    rail_var_dir = f"{DEST_ROOT}/06_Ferrovia_Vagoes/Variants"
    EAL.make_directory(rail_var_dir)
    base_rail_slots = {
        "M_Rail_WellCar_Steel":   M["rail_well_ochre"],
        "M_Rail_Bogie_DarkSteel": M["rail_bogie_rust"],
        "M_Rail_Wheel_Steel":     M["rail_wheel_steel"],
        "M_Rail_Hardware_Steel":  M["rail_bogie_rust"],
    }
    if "SM_Rail_WellCar_Single" in imported_meshes:
        mesh, mpath = imported_meshes["SM_Rail_WellCar_Single"]
        s0 = dict(base_rail_slots, M_Rail_Container_A=M["cont_red"])
        apply_slot_map(mesh, s0)
        configure_nanite_and_save(mesh, mpath)
        create_variant(mpath, f"{rail_var_dir}/SM_Rail_WellCar_Single_VarNavy", dict(base_rail_slots, M_Rail_Container_A=M["cont_navy"]))
        create_variant(mpath, f"{rail_var_dir}/SM_Rail_WellCar_Single_VarGreen", dict(base_rail_slots, M_Rail_Container_A=M["cont_green"]))

    if "SM_Rail_WellCar_Double" in imported_meshes:
        mesh, mpath = imported_meshes["SM_Rail_WellCar_Double"]
        d0 = dict(base_rail_slots, M_Rail_Container_A=M["cont_red"], M_Rail_Container_B=M["cont_navy"])
        apply_slot_map(mesh, d0)
        configure_nanite_and_save(mesh, mpath)
        create_variant(mpath, f"{rail_var_dir}/SM_Rail_WellCar_Double_VarGreenOchre", dict(base_rail_slots, M_Rail_Container_A=M["cont_green"], M_Rail_Container_B=M["cont_ochre"]))
        create_variant(mpath, f"{rail_var_dir}/SM_Rail_WellCar_Double_VarNavyGrey", dict(base_rail_slots, M_Rail_Container_A=M["cont_navy"], M_Rail_Container_B=M["cont_grey"]))
        create_variant(mpath, f"{rail_var_dir}/SM_Rail_WellCar_Double_VarOchreRed", dict(base_rail_slots, M_Rail_Container_A=M["cont_ochre"], M_Rail_Container_B=M["cont_red"]))

    # 6. Create 16 Suburban House Variants (4 distinct wall/roof/trim combinations x 4 house models)
    house_var_dir = f"{DEST_ROOT}/01_Suburbios_Casas/Variants"
    EAL.make_directory(house_var_dir)

    house_recipes = {
        "SM_Suburb_HouseA": [
            ("Var1_QuixelCream_Slate",     {"Wood058_2K": M["wall_stucco_cream"],       "RoofingTiles003_1K": M["roof_slate_dark"],  "Window_Frame": M["trim_white"],    "Bricks054_1K": M["wall_dw_brick_brown"]}),
            ("Var2_QuixelSage_BrownRoof",  {"Wood058_2K": M["wall_stucco_sage"],        "RoofingTiles003_1K": M["roof_brown_2"],     "Window_Frame": M["trim_white"],    "Bricks054_1K": M["wall_dw_brick_red"]}),
            ("Var3_QuixelBlue_GreyRoof",   {"Wood058_2K": M["wall_stucco_coastalblue"], "RoofingTiles003_1K": M["roof_grey_3"],      "Window_Frame": M["trim_darkgrey"], "Bricks054_1K": M["wall_dw_brick_brown"]}),
            ("Var4_Terracotta_TerraRoof",  {"Wood058_2K": M["wall_stucco_terracotta"],  "RoofingTiles003_1K": M["roof_terra_1"],     "Window_Frame": M["trim_brown"],    "Bricks054_1K": M["wall_dw_sandstone"]}),
        ],
        "SM_Suburb_HouseB": [
            ("Var1_QuixelBlue_Slate",      {"MHousWood": M["wall_stucco_coastalblue"],  "MHousRoof": M["roof_slate_dark"],  "MHouseWall": M["wall_dw_brick_brown"]}),
            ("Var2_QuixelCream_Brown",     {"MHousWood": M["wall_stucco_cream"],        "MHousRoof": M["roof_brown_2"],     "MHouseWall": M["wall_dw_sandstone"]}),
            ("Var3_CityParkWall_Terra",    {"MHousWood": M["wall_cp_4"],                "MHousRoof": M["roof_terra_1"],     "MHouseWall": M["wall_dw_brick_red"]}),
            ("Var4_QuixelSage_GreyRoof",   {"MHousWood": M["wall_stucco_sage"],         "MHousRoof": M["roof_grey_3"],      "MHouseWall": M["wall_dw_brick_brown"]}),
        ],
        "SM_Suburb_HouseC": [
            ("Var1_QuixelWhite_Slate",     {"siding": M["wall_stucco_white"],           "roof": M["roof_slate_dark"],  "white": M["trim_white"]}),
            ("Var2_QuixelCream_Terra",     {"siding": M["wall_stucco_cream"],           "roof": M["roof_terra_1"],     "white": M["trim_brown"]}),
            ("Var3_DWPlaster_BrownRoof",   {"siding": M["wall_dw_plaster_a"],           "roof": M["roof_brown_2"],     "white": M["trim_darkgrey"]}),
            ("Var4_QuixelSage_GreyRoof",   {"siding": M["wall_stucco_sage"],            "roof": M["roof_grey_3"],      "white": M["trim_white"]}),
        ],
        "SM_Suburb_HouseD_Victorian": [
            ("Var1_OaklandBlue_Slate",     {"outerwalls": M["wall_stucco_coastalblue"], "roofingbasis": M["roof_slate_dark"],  "porch_pillars": M["trim_white"],    "corniches": M["trim_white"],    "chimney": M["wall_dw_brick_red"]}),
            ("Var2_OaklandCream_Brown",    {"outerwalls": M["wall_stucco_cream"],       "roofingbasis": M["roof_brown_2"],     "porch_pillars": M["trim_brown"],    "corniches": M["trim_brown"],    "chimney": M["wall_dw_brick_brown"]}),
            ("Var3_OaklandSage_Grey",      {"outerwalls": M["wall_stucco_sage"],        "roofingbasis": M["roof_grey_3"],      "porch_pillars": M["trim_white"],    "corniches": M["trim_green"],    "chimney": M["wall_dw_brick_brown"]}),
            ("Var4_OaklandTerra_RedRoof",  {"outerwalls": M["wall_stucco_terracotta"],  "roofingbasis": M["roof_red_4"],       "porch_pillars": M["trim_white"],    "corniches": M["trim_darkgrey"], "chimney": M["wall_dw_brick_red"]}),
        ],
    }

    for base_id, variants in house_recipes.items():
        if base_id not in imported_meshes:
            continue
        mesh, mpath = imported_meshes[base_id]
        # Also upgrade HouseD base mesh's noisy roof right away so even the base asset is realistic
        if base_id == "SM_Suburb_HouseD_Victorian":
            apply_slot_map(mesh, variants[0][1])
        configure_nanite_and_save(mesh, mpath)
        for v_suffix, slot_map in variants:
            create_variant(mpath, f"{house_var_dir}/{base_id}_{v_suffix}", slot_map)

    # 7. Finalize Nanite & save on all remaining base imported meshes
    dressed_already = {
        "SM_Nuclear_CoolingTower", "SM_Nuclear_ReactorDome", "SM_Nuclear_TurbineHall",
        "SM_Port_STSCrane", "SM_Rail_WellCar_Single", "SM_Rail_WellCar_Double",
        "SM_Suburb_HouseA", "SM_Suburb_HouseB", "SM_Suburb_HouseC", "SM_Suburb_HouseD_Victorian",
    }
    for vid, (mesh, mpath) in imported_meshes.items():
        if vid not in dressed_already:
            configure_nanite_and_save(mesh, mpath)

    EAL.save_directory(DEST_ROOT, only_if_is_dirty=False, recursive=True)
    unreal.log(f"WSPC2SCENERY COMPLETE: {len(imported_meshes)} base meshes + 16 house variants + 5 container railcar variants under {DEST_ROOT}")


if __name__ == "__main__":
    main()
