"""Normalizes, repairs, re-UV-maps, and optimizes the 14 retained Sketchfab scenery GLBs
from ASSETS TO USE/02_Cenario/ into ASSETS TO USE/02_Cenario_Preparados/ (ready for
UE 5.8 import + Quixel Megascans / OvergrownFactoryENV / Downtown_West material dressing).

Key operations:
  - crane_harbour.glb -> SM_Port_STSCrane.glb: scaled to real Port of Oakland 46 m height,
    grounded at Z=0, boom along +X, clean metric box UVs (4 m tile) & semantic material slots
    (M_Crane_PaintedSteel, M_Crane_AccentSteel, M_Crane_DarkMachinery, M_Crane_WheelsSteel,
    M_Crane_TrimSteel, M_Crane_CabGlass) so UE5 Quixel/OvergrownFactoryENV steel/rust materials
    wrap cleanly with zero stretching.
  - 4 Suburban Houses (SM_Suburb_HouseA/B/C/D_Victorian): metric scale, Z=0 grounded, clean
    OPAQUE/BLEND alpha modes, textures clamped <= 1024 px, victorian_house porch spindles
    decimated cleanly (226 MB -> ~15 MB), and secondary box-UV-projected wall/roof slots where
    needed so Quixel/Downtown_West/CityPark tiling materials align seamlessly across variants.
  - All other approved scenery models (rusted tank, container ship, Sokol crane, ATC tower,
    Taiwan signboards, lanterns, derelict rail car, Date Palm) normalized to real metres, Z=0,
    clean alpha modes, <= 1024 px textures, plus writes manifest.json.

Command:
  blender -b --factory-startup --python Tools/scenery/prepare_scenery_assets.py

Inputs:
  ASSETS TO USE/02_Cenario/<Category>/*.glb

Outputs:
  ASSETS TO USE/02_Cenario_Preparados/<Category>/<Id>.glb
  ASSETS TO USE/02_Cenario_Preparados/manifest.json
"""
import json
import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "ASSETS TO USE" / "02_Cenario"
OUT_ROOT = PROJECT_ROOT / "ASSETS TO USE" / "02_Cenario_Preparados"
OUT_ROOT.mkdir(parents=True, exist_ok=True)

GLASS_KW = ("glass", "transparat", "window_glass", "glasses")
MASK_KW = ("leaf", "leaves", "palm", "frond", "alpha", "decal", "grate", "sign", "lantern")

SPECS = [
    # 01_Suburbios_Casas
    {
        "id": "SM_Suburb_HouseA",
        "cat": "01_Suburbios_Casas",
        "src": "01_Suburbios_Casas/american_house.glb",
        "target_height_m": 8.6,
        "max_tex_px": 1024,
        "reproject_uv_mats": ["Wood058_2K", "RoofingTiles003_1K", "PaintedPlaster017_2K_Walls", "Bricks054_1K"],
        "uv_tile_m": 2.6,
    },
    {
        "id": "SM_Suburb_HouseB",
        "cat": "01_Suburbios_Casas",
        "src": "01_Suburbios_Casas/lp_americans_house_mobile.glb",
        "target_height_m": 7.4,
        "max_tex_px": 1024,
        "reproject_uv_mats": ["MHousWood", "MHousRoof", "MHouseWall"],
        "uv_tile_m": 2.4,
    },
    {
        "id": "SM_Suburb_HouseC",
        "cat": "01_Suburbios_Casas",
        "src": "01_Suburbios_Casas/suburban_house.glb",
        "target_height_m": 8.2,
        "max_tex_px": 1024,
        "reproject_uv_mats": ["siding", "roof", "white"],
        "uv_tile_m": 2.6,
    },
    {
        "id": "SM_Suburb_HouseD_Victorian",
        "cat": "01_Suburbios_Casas",
        "src": "01_Suburbios_Casas/victorian_house.glb",
        "target_height_m": 10.8,
        "max_tex_px": 1024,
        "target_tris": 68000,
        "reproject_uv_mats": ["outerwalls", "roofingbasis", "chimney", "adobe"],
        "uv_tile_m": 2.6,
    },
    # 02_Usina_Nuclear (rusted tank; CoolingTower/ReactorDome/TurbineHall come from build_nuclear_plant.py)
    {
        "id": "SM_Nuclear_RustedTank",
        "cat": "02_Usina_Nuclear",
        "src": "02_Usina_Nuclear/rusted_tank_storage_1.glb",
        "target_height_m": 11.5,
        "max_tex_px": 1024,
    },
    # 03_Porto
    {
        "id": "SM_Port_STSCrane",
        "cat": "03_Porto",
        "src": "03_Porto/crane_harbour.glb",
        "target_height_m": 46.0,
        "max_tex_px": 1024,
        "is_crane_harbour": True,
        "uv_tile_m": 4.0,
    },
    {
        "id": "SM_Port_ContainerShip",
        "cat": "03_Porto",
        "src": "03_Porto/container_ship.glb",
        "target_length_m": 195.0,
        "max_tex_px": 2048,
    },
    {
        "id": "SM_Port_CraneSokol",
        "cat": "03_Porto",
        "src": "03_Porto/port_crane_sokol.glb",
        "target_height_m": 34.0,
        "max_tex_px": 1024,
    },
    # 04_Aeroporto
    {
        "id": "SM_Airport_ATCTower",
        "cat": "04_Aeroporto",
        "src": "04_Aeroporto/air_traffic_control_tower.glb",
        "target_height_m": 38.0,
        "max_tex_px": 2048,
    },
    # 05_Chinatown
    {
        "id": "SM_Chinatown_Signboards",
        "cat": "05_Chinatown",
        "src": "05_Chinatown/taiwan_style_signboard_lowpoly.glb",
        "target_height_m": 7.5,
        "max_tex_px": 1024,
    },
    {
        "id": "SM_Chinatown_LanternSingle",
        "cat": "05_Chinatown",
        "src": "05_Chinatown/chinese_lantern.glb",
        "target_height_m": 0.85,
        "max_tex_px": 512,
    },
    {
        "id": "SM_Chinatown_LanternCluster",
        "cat": "05_Chinatown",
        "src": "05_Chinatown/oriental_lanterns.glb",
        "target_height_m": 2.2,
        "max_tex_px": 1024,
    },
    # 06_Ferrovia_Vagoes (derelict yard wagon; WellCar_Single/Double & TankCar come from build_rail_cars.py)
    {
        "id": "SM_Rail_DerelictWagon",
        "cat": "06_Ferrovia_Vagoes",
        "src": "06_Ferrovia_Vagoes/train_wagon.glb",
        "target_length_m": 18.5,
        "max_tex_px": 1024,
    },
    # 07_Palmeiras
    {
        "id": "SM_Flora_DatePalm",
        "cat": "07_Palmeiras",
        "src": "07_Palmeiras/date_palm.glb",
        "target_height_m": 13.5,
        "max_tex_px": 1024,
        "is_foliage": True,
    },
]


def bake_all_meshes():
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons) > 0]
    for o in meshes:
        mw = o.matrix_world.copy()
        o.data = o.data.copy()
        o.data.transform(mw)
        if mw.determinant() < 0:
            o.data.flip_normals()
        o.data.update()
        o.parent = None
        o.matrix_world = Matrix.Identity(4)
    for o in list(bpy.data.objects):
        if o not in meshes:
            bpy.data.objects.remove(o, do_unlink=True)
    return meshes


def mesh_bounds(meshes):
    lo = Vector((1e18, 1e18, 1e18))
    hi = Vector((-1e18, -1e18, -1e18))
    for o in meshes:
        for v in o.data.vertices:
            lo.x = min(lo.x, v.co.x); lo.y = min(lo.y, v.co.y); lo.z = min(lo.z, v.co.z)
            hi.x = max(hi.x, v.co.x); hi.y = max(hi.y, v.co.y); hi.z = max(hi.z, v.co.z)
    return lo, hi


def reproject_box_uvs_for_slots(obj, slot_names_set, tile_m: float):
    """Applies clean triplanar box-projected metric UVs only to polygons using listed materials."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv_layer = bm.loops.layers.uv.verify()
    inv = 1.0 / max(tile_m, 0.01)
    target_indices = {
        idx for idx, ms in enumerate(obj.material_slots)
        if ms.material and (slot_names_set is None or ms.material.name in slot_names_set)
    }
    for f in bm.faces:
        if f.material_index not in target_indices:
            continue
        n = f.normal
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
        for loop in f.loops:
            co = loop.vert.co
            if az >= ax and az >= ay:
                u, v = co.x * inv, co.y * inv
            elif ax >= ay:
                u, v = co.y * inv, co.z * inv
            else:
                u, v = co.x * inv, co.z * inv
            loop[uv_layer].uv = (u, v)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def upgrade_crane_harbour_materials(obj):
    """Replaces raw untextured crane_harbour slots with clean semantic PBR slots ready for
    UE 5.8 Quixel / OvergrownFactoryENV marine painted steel & rusty machinery."""
    remap = {
        "Wheel":            ("M_Crane_PaintedSteel",  (0.32, 0.44, 0.48), 0.56, 0.65, 1.0),  # Port of Oakland weathered blue-grey steel
        "Paint_Rusted":     ("M_Crane_AccentSteel",   (0.58, 0.22, 0.14), 0.62, 0.55, 1.0),  # Maritime crane orange-red / oxidized boom accent
        "Wheeler":          ("M_Crane_DarkMachinery", (0.18, 0.19, 0.20), 0.65, 0.82, 1.0),  # Hoist trolley / dark oiled steel
        "Paint_Rusted.001": ("M_Crane_WheelsSteel",   (0.24, 0.22, 0.20), 0.72, 0.78, 1.0),  # Rail bogies & lower bumpers
        "Material.002":     ("M_Crane_TrimSteel",     (0.66, 0.54, 0.14), 0.55, 0.45, 1.0),  # Safety yellow lower trim
        "Transparat":       ("M_Crane_CabGlass",      (0.08, 0.14, 0.17), 0.10, 0.10, 0.42), # Tinted cab window glass
    }
    for ms in obj.material_slots:
        if not ms.material:
            continue
        old = ms.material.name
        cfg = remap.get(old)
        if not cfg:
            continue
        new_name, col, rough, met, alpha = cfg
        mat = bpy.data.materials.new(new_name)
        mat.use_nodes = True
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (*col, 1.0)
            bsdf.inputs["Roughness"].default_value = rough
            bsdf.inputs["Metallic"].default_value = met
            bsdf.inputs["Alpha"].default_value = alpha
        mat.blend_method = "BLEND" if alpha < 0.99 else "OPAQUE"
        ms.material = mat


def enforce_clean_alpha(is_foliage: bool = False):
    for mat in bpy.data.materials:
        if not mat.use_nodes or not mat.node_tree:
            continue
        nt = mat.node_tree
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if not bsdf:
            continue
        nl = mat.name.lower()
        a_in = bsdf.inputs.get("Alpha")
        if any(k in nl for k in GLASS_KW):
            mat.blend_method = "BLEND"
            if a_in and not a_in.is_linked and a_in.default_value >= 0.95:
                a_in.default_value = 0.35
        elif is_foliage or any(k in nl for k in MASK_KW):
            if a_in and a_in.is_linked:
                src = a_in.links[0].from_socket
                nt.links.remove(a_in.links[0])
                gt = nt.nodes.new("ShaderNodeMath")
                gt.operation = "GREATER_THAN"
                gt.inputs[1].default_value = 0.45
                nt.links.new(src, gt.inputs[0])
                nt.links.new(gt.outputs[0], a_in)
            mat.blend_method = "CLIP"
        else:
            if a_in:
                for l in list(a_in.links):
                    nt.links.remove(l)
                a_in.default_value = 1.0
            mat.blend_method = "OPAQUE"


def clamp_textures(max_px: int):
    for im in bpy.data.images:
        if im.size[0] == 0:
            continue
        if max(im.size[0], im.size[1]) > max_px:
            sc = max_px / float(max(im.size[0], im.size[1]))
            try:
                im.scale(max(4, int(round(im.size[0] * sc))), max(4, int(round(im.size[1] * sc))))
                im.pack()
            except Exception:
                pass


def process_spec(spec: dict):
    src_path = SRC_ROOT / spec["src"]
    if not src_path.exists():
        print("MISSING:", src_path)
        return None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(src_path))
    bpy.context.view_layer.update()

    meshes = bake_all_meshes()
    lo, hi = mesh_bounds(meshes)
    dims = hi - lo

    # Align longest horizontal axis along +X for linear assets (ship, crane, wagon)
    if spec.get("target_length_m") or spec.get("is_crane_harbour"):
        if dims.y > dims.x * 1.05:
            rot90 = Matrix.Rotation(math.radians(-90.0), 4, "Z")
            for o in meshes:
                o.data.transform(rot90)
                o.data.update()
            lo, hi = mesh_bounds(meshes)
            dims = hi - lo

    # Compute uniform metric scale factor
    if spec.get("target_height_m"):
        scale = float(spec["target_height_m"]) / max(dims.z, 1e-4)
    elif spec.get("target_length_m"):
        scale = float(spec["target_length_m"]) / max(dims.x, 1e-4)
    else:
        scale = 1.0

    ctr = Vector((0.5 * (lo.x + hi.x), 0.5 * (lo.y + hi.y), lo.z))
    xform = Matrix.Scale(scale, 4) @ Matrix.Translation(-ctr)
    for o in meshes:
        o.data.transform(xform)
        o.data.update()

    # Join into one clean StaticMesh object
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = spec["id"]
    obj.data.name = spec["id"]

    # Optional decimation for overly dense porch spindles (e.g. Victorian house 186k -> 68k)
    cur_tris = sum(max(0, len(p.vertices) - 2) for p in obj.data.polygons)
    if spec.get("target_tris") and cur_tris > spec["target_tris"]:
        mod = obj.modifiers.new("Decimate", "DECIMATE")
        mod.ratio = max(0.15, spec["target_tris"] / float(cur_tris))
        mod.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=mod.name)

    if spec.get("is_crane_harbour"):
        upgrade_crane_harbour_materials(obj)
        reproject_box_uvs_for_slots(obj, None, tile_m=spec.get("uv_tile_m", 4.0))
    else:
        if spec.get("reproject_uv_mats"):
            reproject_box_uvs_for_slots(obj, set(spec["reproject_uv_mats"]), tile_m=spec.get("uv_tile_m", 2.6))
        enforce_clean_alpha(is_foliage=spec.get("is_foliage", False))
        clamp_textures(spec.get("max_tex_px", 1024))

    # Clean zero-area faces
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bad = [f for f in bm.faces if f.calc_area() < 1e-9]
    if bad:
        bmesh.ops.delete(bm, geom=bad, context="FACES")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.validate(clean_customdata=True)
    obj.data.update()

    out_dir = OUT_ROOT / spec["cat"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{spec['id']}.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(out_path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_normals=True,
        export_texcoords=True,
        export_materials="EXPORT",
    )
    lo2, hi2 = mesh_bounds([obj])
    d2 = [round(v, 2) for v in (hi2 - lo2)]
    tris = sum(max(0, len(p.vertices) - 2) for p in obj.data.polygons)
    mats = [ms.material.name for ms in obj.material_slots if ms.material]
    print(f"PREPARED {spec['id']:28s} | {tris:6d} tris | dims={d2} | {len(mats):2d} mats | {out_path.stat().st_size/(1024*1024):.1f} MB")
    return {
        "id": spec["id"], "cat": spec["cat"], "file": f"{spec['cat']}/{spec['id']}.glb",
        "tris": tris, "dims_m": d2, "mats": mats, "mb": round(out_path.stat().st_size / (1024 * 1024), 2),
    }


def main():
    manifest = []
    for sp in SPECS:
        rec = process_spec(sp)
        if rec:
            manifest.append(rec)
    # Also scan procedural assets built by build_nuclear_plant.py and build_rail_cars.py
    known = {r["id"] for r in manifest}
    for glb in sorted(OUT_ROOT.rglob("*.glb")):
        if glb.stem in known:
            continue
        manifest.append({
            "id": glb.stem,
            "cat": glb.parent.name,
            "file": glb.relative_to(OUT_ROOT).as_posix(),
            "mb": round(glb.stat().st_size / (1024 * 1024), 2),
        })
    (OUT_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"SCENERY PREPARE DONE: {len(manifest)} prepared GLBs -> {OUT_ROOT / 'manifest.json'}")


if __name__ == "__main__":
    main()
