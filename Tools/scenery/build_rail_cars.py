"""Builds high-detail US Intermodal Well-Car / Container Freight Cars (Single-Stack and
Double-Stack) joined with corrugated 40ft ISO shipping containers in Blender 5.2, plus
normalizes graffiti_railway_tank.glb to exact US standard gauge (1.435 m) and +X forward
alignment matching Rail_EMD_GP7.glb.

Command:
  blender -b --factory-startup --python Tools/scenery/build_rail_cars.py

Inputs:
  ASSETS TO USE/02_Cenario/06_Ferrovia_Vagoes/graffiti_railway_tank.glb

Outputs:
  ASSETS TO USE/02_Cenario_Preparados/06_Ferrovia_Vagoes/SM_Rail_WellCar_Single.glb
  ASSETS TO USE/02_Cenario_Preparados/06_Ferrovia_Vagoes/SM_Rail_WellCar_Double.glb
  ASSETS TO USE/02_Cenario_Preparados/06_Ferrovia_Vagoes/SM_Rail_TankCar_Graffiti.glb
"""
import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_TANK = PROJECT_ROOT / "ASSETS TO USE" / "02_Cenario" / "06_Ferrovia_Vagoes" / "graffiti_railway_tank.glb"
OUT_DIR = PROJECT_ROOT / "ASSETS TO USE" / "02_Cenario_Preparados" / "06_Ferrovia_Vagoes"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def make_mat(name: str, color, roughness=0.68, metallic=0.55):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Alpha"].default_value = 1.0
    mat.blend_method = "OPAQUE"
    return mat


def apply_metric_box_uvs(bm: bmesh.types.BMesh, tile_m: float = 3.0):
    uv_layer = bm.loops.layers.uv.verify()
    inv = 1.0 / max(tile_m, 0.01)
    for f in bm.faces:
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


def add_box(bm, center: Vector, size: Vector, mat_idx: int, rot=(0.0, 0.0, 0.0)):
    mat = Matrix.Translation(center) @ Euler(rot, "XYZ").to_matrix().to_4x4() @ Matrix.Diagonal((size.x, size.y, size.z, 1.0))
    res = bmesh.ops.create_cube(bm, size=1.0, matrix=mat)
    vs = set(res["verts"])
    for f in bm.faces:
        if all(v in vs for v in f.verts):
            f.material_index = mat_idx


def add_cyl(bm, p0: Vector, p1: Vector, radius: float, segs: int, mat_idx: int):
    vec = p1 - p0
    length = vec.length
    if length < 1e-4:
        return
    mid = 0.5 * (p0 + p1)
    q = Vector((0, 0, 1)).rotation_difference(vec.normalized())
    res = bmesh.ops.create_cone(
        bm, cap_ends=True, cap_tris=False, segments=segs,
        radius1=radius, radius2=radius, depth=length,
        matrix=Matrix.Translation(mid) @ q.to_matrix().to_4x4()
    )
    vs = set(res["verts"])
    for f in bm.faces:
        if all(v in vs for v in f.verts):
            f.material_index = mat_idx
            f.smooth = True


def add_bogie(bm, cx: float, idx_dark: int, idx_wheel: int):
    """US Barber S-2 two-axle freight bogie centered at x=cx, railhead at z=0.0, gauge=1.435m."""
    WHEEL_R = 0.44      # 36-inch US freight wheel
    FLANGE_R = 0.475
    HALF_GAUGE = 0.725  # 1.45 m wheel tread center-to-center
    AXLE_DX = 0.88      # 1.76 m bogie wheelbase

    for dx in (-AXLE_DX, AXLE_DX):
        ax = cx + dx
        # Solid steel axle shaft
        add_cyl(bm, Vector((ax, -0.96, WHEEL_R)), Vector((ax, 0.96, WHEEL_R)), 0.085, 10, idx_dark)
        # Flanged left & right steel wheels
        for sy in (-1.0, 1.0):
            wy = sy * HALF_GAUGE
            # Main tread disc
            add_cyl(bm, Vector((ax, wy - 0.065, WHEEL_R)), Vector((ax, wy + 0.065, WHEEL_R)), WHEEL_R, 20, idx_wheel)
            # Inner flange ring
            fy = wy - sy * 0.068
            add_cyl(bm, Vector((ax, fy - 0.018, WHEEL_R)), Vector((ax, fy + 0.018, WHEEL_R)), FLANGE_R, 20, idx_wheel)
            # Outer bearing journal box
            add_box(bm, Vector((ax, sy * 0.96, WHEEL_R)), Vector((0.26, 0.20, 0.26)), idx_dark)

    # Heavy cast steel side-frames + central bolster & spring clusters
    for sy in (-1.0, 1.0):
        fy = sy * 0.95
        add_box(bm, Vector((cx, fy, WHEEL_R + 0.16)), Vector((2.28, 0.14, 0.22)), idx_dark)
        add_box(bm, Vector((cx, fy, WHEEL_R - 0.16)), Vector((1.40, 0.12, 0.14)), idx_dark)
        # Spring cluster columns
        for sx in (-0.16, 0.0, 0.16):
            add_cyl(bm, Vector((cx + sx, fy, WHEEL_R - 0.12)), Vector((cx + sx, fy, WHEEL_R + 0.14)), 0.065, 8, idx_dark)
    # Cross bolster & center pivot plate
    add_box(bm, Vector((cx, 0.0, WHEEL_R + 0.18)), Vector((0.46, 1.98, 0.26)), idx_dark)
    add_cyl(bm, Vector((cx, 0.0, WHEEL_R + 0.30)), Vector((cx, 0.0, WHEEL_R + 0.44)), 0.28, 14, idx_dark)


def add_iso_container_40ft(bm, cz_bottom: float, idx_body: int, idx_trim: int):
    """Detailed 40ft ISO shipping container (12.19 x 2.44 x 2.59 m) with real corrugated walls,
    corner castings, top/bottom rails and rear double doors with locking bars."""
    CL, CW, CH = 12.19, 2.44, 2.59
    cz = cz_bottom + CH * 0.5

    # Core structural box slightly inset so corrugation ribs stand proud cleanly
    add_box(bm, Vector((0.0, 0.0, cz)), Vector((CL - 0.08, CW - 0.08, CH - 0.08)), idx_body)

    # Top & bottom longitudinal side rails + end header/sill beams
    for sz in (cz_bottom + 0.09, cz_bottom + CH - 0.09):
        for sy in (-1.0, 1.0):
            add_box(bm, Vector((0.0, sy * (CW * 0.5 - 0.05), sz)), Vector((CL, 0.12, 0.18)), idx_body)
        for sx in (-1.0, 1.0):
            add_box(bm, Vector((sx * (CL * 0.5 - 0.05), 0.0, sz)), Vector((0.12, CW, 0.18)), idx_body)

    # 4 vertical corner posts + 8 ISO twist-lock corner castings
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            add_box(bm, Vector((sx * (CL * 0.5 - 0.07), sy * (CW * 0.5 - 0.07), cz)), Vector((0.16, 0.16, CH)), idx_body)
            for sz in (cz_bottom + 0.09, cz_bottom + CH - 0.09):
                add_box(bm, Vector((sx * (CL * 0.5 - 0.08), sy * (CW * 0.5 - 0.08), sz)), Vector((0.19, 0.19, 0.19)), idx_trim)

    # Vertical side wall corrugation ribs (real shipping container profile along +-Y walls)
    n_ribs = 38
    x0 = -CL * 0.5 + 0.35
    x1 = CL * 0.5 - 0.35
    for i in range(n_ribs):
        rx = x0 + (x1 - x0) * (i / (n_ribs - 1))
        for sy in (-1.0, 1.0):
            add_box(bm, Vector((rx, sy * (CW * 0.5 - 0.015), cz)), Vector((0.12, 0.045, CH - 0.34)), idx_body)

    # Roof corrugation ribs
    for i in range(0, n_ribs, 2):
        rx = x0 + (x1 - x0) * (i / (n_ribs - 1))
        add_box(bm, Vector((rx, 0.0, cz_bottom + CH - 0.015)), Vector((0.14, CW - 0.24, 0.04)), idx_body)

    # Rear (+X) double doors with 4 vertical galvanized locking rods & cam latches
    dx_door = CL * 0.5 - 0.01
    add_box(bm, Vector((dx_door, 0.0, cz)), Vector((0.04, 0.05, CH - 0.32)), idx_trim)
    for ry in (-0.82, -0.34, 0.34, 0.82):
        add_cyl(bm, Vector((dx_door + 0.035, ry, cz_bottom + 0.20)), Vector((dx_door + 0.035, ry, cz_bottom + CH - 0.20)), 0.022, 6, idx_trim)
        add_box(bm, Vector((dx_door + 0.05, ry + 0.08, cz_bottom + 1.05)), Vector((0.05, 0.18, 0.05)), idx_trim)


def build_well_car(double_stack: bool, out_name: str):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    m_chassis = make_mat("M_Rail_WellCar_Steel", (0.48, 0.34, 0.12), roughness=0.68, metallic=0.65)  # weathered TTX yellow-ochre
    m_dark = make_mat("M_Rail_Bogie_DarkSteel", (0.14, 0.13, 0.12), roughness=0.74, metallic=0.80)
    m_wheel = make_mat("M_Rail_Wheel_Steel", (0.28, 0.27, 0.26), roughness=0.42, metallic=0.92)
    m_cont_a = make_mat("M_Rail_Container_A", (0.42, 0.14, 0.11), roughness=0.65, metallic=0.45)  # oxidized freight red
    m_cont_b = make_mat("M_Rail_Container_B", (0.12, 0.24, 0.36), roughness=0.65, metallic=0.45)  # maritime navy blue
    m_trim = make_mat("M_Rail_Hardware_Steel", (0.22, 0.22, 0.22), roughness=0.55, metallic=0.85)

    mats = [m_chassis, m_dark, m_wheel, m_cont_a, m_cont_b, m_trim]
    IDX_CH, IDX_DK, IDX_WH, IDX_CA, IDX_CB, IDX_TR = range(6)

    bm = bmesh.new()

    # Well-car total length over strikers = 16.4m (over couplers ~17.1m), bogie centers at +-6.75m
    BOGIE_X = 6.75
    WELL_L = 12.45
    WELL_OUT_W = 2.94
    WELL_IN_W = 2.50
    SIDE_T = (WELL_OUT_W - WELL_IN_W) * 0.5  # 0.22 m thick box-girder side walls

    # 1. Two Barber freight bogies
    add_bogie(bm, -BOGIE_X, IDX_DK, IDX_WH)
    add_bogie(bm, BOGIE_X, IDX_DK, IDX_WH)

    # 2. Drop-well side box girders (z=0.38 -> 1.48 m) + bottom cross-bearers (z=0.38 -> 0.52 m)
    for sy in (-1.0, 1.0):
        gy = sy * (WELL_IN_W * 0.5 + SIDE_T * 0.5)
        add_box(bm, Vector((0.0, gy, 0.94)), Vector((WELL_L, SIDE_T, 1.10)), IDX_CH)
        # Top flange lip & side stiffener ribs every 1.4m
        add_box(bm, Vector((0.0, gy, 1.50)), Vector((WELL_L + 0.1, SIDE_T + 0.08, 0.08)), IDX_CH)
        for xi in range(-4, 5):
            add_box(bm, Vector((xi * 1.40, sy * (WELL_OUT_W * 0.5 + 0.03), 0.94)), Vector((0.10, 0.07, 1.06)), IDX_CH)

    # Floor cross-bearers inside the well (seat containers at z = 0.54 m above railhead!)
    for xi in range(-5, 6):
        add_box(bm, Vector((xi * 1.18, 0.0, 0.45)), Vector((0.20, WELL_IN_W + 0.2, 0.16)), IDX_DK)
    # Four corner container support ledges
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            add_box(bm, Vector((sx * 6.02, sy * 1.15, 0.48)), Vector((0.45, 0.32, 0.12)), IDX_TR)

    # 3. Raised end platforms over bogies (x = +-6.22 to +-8.10, deck at z = 1.06 m)
    for sx in (-1.0, 1.0):
        # End shear deck & bolster hood
        add_box(bm, Vector((sx * 7.12, 0.0, 1.06)), Vector((1.95, WELL_OUT_W, 0.24)), IDX_CH)
        # Sloped bulkhead wall tying well to end deck
        add_box(bm, Vector((sx * 6.26, 0.0, 1.32)), Vector((0.18, WELL_OUT_W, 0.72)), IDX_CH)
        # Center sill & AAR Type-E knuckle coupler at z = 0.88 m (US standard height!)
        add_box(bm, Vector((sx * 7.65, 0.0, 0.88)), Vector((1.15, 0.36, 0.28)), IDX_DK)
        add_box(bm, Vector((sx * 8.35, 0.0, 0.88)), Vector((0.36, 0.28, 0.30)), IDX_TR)
        add_box(bm, Vector((sx * 8.54, sx * 0.07, 0.88)), Vector((0.20, 0.14, 0.28)), IDX_TR)
        # End crossover grating walkway & safety handrails
        add_box(bm, Vector((sx * 7.75, 0.0, 1.24)), Vector((0.52, WELL_OUT_W - 0.18, 0.06)), IDX_TR)
        for cy in (-1.35, -0.55, 0.55, 1.35):
            add_cyl(bm, Vector((sx * 8.02, cy, 1.24)), Vector((sx * 8.02, cy, 2.18)), 0.025, 6, IDX_TR)
        add_cyl(bm, Vector((sx * 8.02, -1.35, 2.18)), Vector((sx * 8.02, 1.35, 2.18)), 0.025, 6, IDX_TR)
        add_cyl(bm, Vector((sx * 8.02, -1.35, 1.72)), Vector((sx * 8.02, 1.35, 1.72)), 0.022, 6, IDX_TR)
        # Corner grab ladders on both sides
        for sy in (-1.0, 1.0):
            for lx in (sx * 7.35, sx * 7.85):
                add_cyl(bm, Vector((lx, sy * (WELL_OUT_W * 0.5 + 0.04), 0.50)), Vector((lx, sy * (WELL_OUT_W * 0.5 + 0.04), 1.95)), 0.022, 6, IDX_TR)
            for rz in (0.65, 0.98, 1.32, 1.65):
                add_cyl(bm, Vector((sx * 7.35, sy * (WELL_OUT_W * 0.5 + 0.04), rz)), Vector((sx * 7.85, sy * (WELL_OUT_W * 0.5 + 0.04), rz)), 0.018, 6, IDX_TR)

    # Handbrake wheel on +X end
    add_cyl(bm, Vector((8.05, 0.85, 1.85)), Vector((8.14, 0.85, 1.85)), 0.24, 14, IDX_TR)
    # Air brake reservoir tanks under +X end platform
    add_cyl(bm, Vector((6.9, -0.55, 0.72)), Vector((7.6, -0.55, 0.72)), 0.16, 10, IDX_DK)

    # 4. Seated 40ft ISO shipping container(s)
    add_iso_container_40ft(bm, cz_bottom=0.54, idx_body=IDX_CA, idx_trim=IDX_TR)
    if double_stack:
        add_iso_container_40ft(bm, cz_bottom=0.54 + 2.59 + 0.02, idx_body=IDX_CB, idx_trim=IDX_TR)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    apply_metric_box_uvs(bm, tile_m=3.0)

    mesh = bpy.data.meshes.new(out_name)
    bm.to_mesh(mesh)
    bm.free()
    for m in mats:
        mesh.materials.append(m)
    mesh.validate(clean_customdata=True)
    mesh.update()
    obj = bpy.data.objects.new(out_name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    out_path = OUT_DIR / f"{out_name}.glb"
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
    tris = sum(max(0, len(p.vertices) - 2) for p in mesh.polygons)
    print(f"BUILT {out_path.name:34s} | {tris:6d} tris | {len(mats)} mats | {out_path.stat().st_size/(1024*1024):.2f} MB")


def normalize_graffiti_tank_car():
    """Rotates graffiti_railway_tank.glb to +X forward, scales to US 15.2 m tank car length,
    grounds at Z=0, cleans alpha modes (OPAQUE/MASK), clamps textures <= 1024 px."""
    if not SRC_TANK.exists():
        print("SKIP missing:", SRC_TANK)
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(SRC_TANK))
    bpy.context.view_layer.update()

    meshes = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons) > 0]
    for o in meshes:
        mw = o.matrix_world.copy()
        o.data = o.data.copy()
        o.data.transform(mw)
        if mw.determinant() < 0:
            o.data.flip_normals()
        o.parent = None
        o.matrix_world = Matrix.Identity(4)
    for o in list(bpy.data.objects):
        if o not in meshes:
            bpy.data.objects.remove(o, do_unlink=True)

    # Rotate longest horizontal axis to +X
    lo = Vector((1e9, 1e9, 1e9)); hi = Vector((-1e9, -1e9, -1e9))
    for o in meshes:
        for v in o.data.vertices:
            lo.x = min(lo.x, v.co.x); lo.y = min(lo.y, v.co.y); lo.z = min(lo.z, v.co.z)
            hi.x = max(hi.x, v.co.x); hi.y = max(hi.y, v.co.y); hi.z = max(hi.z, v.co.z)
    dims = hi - lo
    if dims.y > dims.x * 1.05:
        rot90 = Matrix.Rotation(math.radians(-90.0), 4, "Z")
        for o in meshes:
            o.data.transform(rot90)
            o.data.update()

    lo = Vector((1e9, 1e9, 1e9)); hi = Vector((-1e9, -1e9, -1e9))
    for o in meshes:
        for v in o.data.vertices:
            lo.x = min(lo.x, v.co.x); lo.y = min(lo.y, v.co.y); lo.z = min(lo.z, v.co.z)
            hi.x = max(hi.x, v.co.x); hi.y = max(hi.y, v.co.y); hi.z = max(hi.z, v.co.z)
    dims = hi - lo
    scale = 15.2 / max(dims.x, 1e-4)
    ctr = Vector((0.5 * (lo.x + hi.x), 0.5 * (lo.y + hi.y), lo.z))
    xform = Matrix.Scale(scale, 4) @ Matrix.Translation(-ctr)
    for o in meshes:
        o.data.transform(xform)
        o.data.update()

    # Enforce OPAQUE on solid Wagon/Cistern, MASK on Alpha ladder/grating
    for mat in bpy.data.materials:
        if not mat.use_nodes or not mat.node_tree:
            continue
        nt = mat.node_tree
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if not bsdf:
            continue
        a_in = bsdf.inputs.get("Alpha")
        if "alpha" in mat.name.lower():
            if a_in and a_in.is_linked:
                src = a_in.links[0].from_socket
                nt.links.remove(a_in.links[0])
                gt = nt.nodes.new("ShaderNodeMath")
                gt.operation = "GREATER_THAN"
                gt.inputs[1].default_value = 0.5
                nt.links.new(src, gt.inputs[0])
                nt.links.new(gt.outputs[0], a_in)
            mat.blend_method = "CLIP"
        else:
            if a_in:
                for l in list(a_in.links):
                    nt.links.remove(l)
                a_in.default_value = 1.0
            mat.blend_method = "OPAQUE"

    for im in bpy.data.images:
        if im.size[0] > 1024 or im.size[1] > 1024:
            sc = 1024.0 / max(im.size[0], im.size[1])
            im.scale(max(4, int(round(im.size[0] * sc))), max(4, int(round(im.size[1] * sc))))
            im.pack()

    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = "SM_Rail_TankCar_Graffiti"
    obj.data.name = "SM_Rail_TankCar_Graffiti"

    out_path = OUT_DIR / "SM_Rail_TankCar_Graffiti.glb"
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
    tris = sum(max(0, len(p.vertices) - 2) for p in obj.data.polygons)
    print(f"NORMALIZED {out_path.name:30s} | {tris:6d} tris | {out_path.stat().st_size/(1024*1024):.2f} MB")


if __name__ == "__main__":
    build_well_car(double_stack=False, out_name="SM_Rail_WellCar_Single")
    build_well_car(double_stack=True, out_name="SM_Rail_WellCar_Double")
    normalize_graffiti_tank_car()
    print("ALL RAIL CAR ASSETS BUILT SUCCESSFULLY")
