"""Generates high-precision, architecturally accurate Nuclear Power Plant 3D assets
in Blender 5.2 with clean metric UVs and semantic material slots ready for UE 5.8
Quixel Megascans / OvergrownFactoryENV / Scene_Warehouse PBR materials.

Command:
  blender -b --factory-startup --python Tools/scenery/build_nuclear_plant.py

Inputs:
  None (parametric architectural geometry in real-world metres, Z=0 grounded)

Outputs:
  ASSETS TO USE/02_Cenario_Preparados/02_Usina_Nuclear/SM_Nuclear_CoolingTower.glb
  ASSETS TO USE/02_Cenario_Preparados/02_Usina_Nuclear/SM_Nuclear_ReactorDome.glb
  ASSETS TO USE/02_Cenario_Preparados/02_Usina_Nuclear/SM_Nuclear_TurbineHall.glb
"""
import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "ASSETS TO USE" / "02_Cenario_Preparados" / "02_Usina_Nuclear"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def make_pbr_mat(name: str, color, roughness: float = 0.78, metallic: float = 0.0, alpha: float = 1.0, emission=None):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        if alpha < 0.99:
            bsdf.inputs["Alpha"].default_value = alpha
            mat.blend_method = "BLEND"
        else:
            bsdf.inputs["Alpha"].default_value = 1.0
            mat.blend_method = "OPAQUE"
        if emission and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
            bsdf.inputs["Emission Strength"].default_value = 3.5
    return mat


def get_nuclear_materials():
    return {
        "concrete_dirty": make_pbr_mat("M_Nuclear_ConcreteDirty", (0.44, 0.43, 0.40), roughness=0.86, metallic=0.0),
        "concrete_dark": make_pbr_mat("M_Nuclear_ConcreteDark", (0.28, 0.28, 0.27), roughness=0.90, metallic=0.0),
        "metal_cladding": make_pbr_mat("M_Nuclear_MetalCladding", (0.42, 0.45, 0.47), roughness=0.58, metallic=0.45),
        "steel_rusted": make_pbr_mat("M_Nuclear_SteelRusted", (0.24, 0.19, 0.16), roughness=0.72, metallic=0.75),
        "pipe_steel": make_pbr_mat("M_Nuclear_PipeSteel", (0.36, 0.37, 0.39), roughness=0.48, metallic=0.85),
        "roof_metal": make_pbr_mat("M_Nuclear_RoofMetal", (0.26, 0.27, 0.29), roughness=0.62, metallic=0.60),
        "glass": make_pbr_mat("M_Nuclear_Glass", (0.09, 0.13, 0.16), roughness=0.12, metallic=0.1, alpha=1.0),
        "water_dark": make_pbr_mat("M_Nuclear_WaterDark", (0.04, 0.08, 0.09), roughness=0.08, metallic=0.0),
        "warning_red": make_pbr_mat("M_Nuclear_WarningRed", (0.72, 0.10, 0.08), roughness=0.35, metallic=0.1, emission=(0.95, 0.12, 0.08)),
    }


def apply_metric_box_uvs(bm: bmesh.types.BMesh, tile_m: float = 4.0):
    """Triplanar box-projected metric UVs (1 UV unit = tile_m metres) so Quixel textures tile crisply."""
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


def apply_cylindrical_uvs(bm: bmesh.types.BMesh, faces, circumference_tile_m: float = 6.0, height_tile_m: float = 6.0):
    """Seamless cylindrical UVs around Z axis (avoids seam stretching on hyperboloids/domes)."""
    uv_layer = bm.loops.layers.uv.verify()
    for f in faces:
        # Estimate face average radius & unwrap continuously per face to avoid 0/2pi seam tear
        angles = [math.atan2(l.vert.co.y, l.vert.co.x) for l in f.loops]
        if max(angles) - min(angles) > math.pi:
            angles = [a + 2.0 * math.pi if a < 0.0 else a for a in angles]
        radii = [math.hypot(l.vert.co.x, l.vert.co.y) for l in f.loops]
        r_avg = sum(radii) / max(len(radii), 1)
        for loop, ang in zip(f.loops, angles):
            arc = ang * r_avg
            loop[uv_layer].uv = (arc / circumference_tile_m, loop.vert.co.z / height_tile_m)


def add_box(bm, center: Vector, size: Vector, mat_idx: int, rot_euler=(0.0, 0.0, 0.0)):
    mat = Matrix.Translation(center) @ Euler(rot_euler, "XYZ").to_matrix().to_4x4() @ Matrix.Diagonal((size.x, size.y, size.z, 1.0))
    res = bmesh.ops.create_cube(bm, size=1.0, matrix=mat)
    verts = set(res["verts"])
    faces = [f for f in bm.faces if all(v in verts for v in f.verts)]
    for f in faces:
        f.material_index = mat_idx
    return faces


def add_cylinder_between(bm, p0: Vector, p1: Vector, radius: float, segs: int, mat_idx: int, cap: bool = True):
    vec = p1 - p0
    length = vec.length
    if length < 1e-4:
        return []
    mid = 0.5 * (p0 + p1)
    quat = Vector((0, 0, 1)).rotation_difference(vec.normalized())
    mat = Matrix.Translation(mid) @ quat.to_matrix().to_4x4()
    res = bmesh.ops.create_cone(
        bm, cap_ends=cap, cap_tris=False, segments=segs,
        radius1=radius, radius2=radius, depth=length, matrix=mat
    )
    verts = set(res["verts"])
    faces = [f for f in bm.faces if all(v in verts for v in f.verts)]
    for f in faces:
        f.material_index = mat_idx
        f.smooth = True
    return faces


def finalize_and_export(name: str, bm: bmesh.types.BMesh, mats_list, out_path: Path, smooth_angle_deg: float = 35.0):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for m in mats_list:
        mesh.materials.append(m)
    mesh.validate(clean_customdata=True)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.update()

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

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
    print(f"BUILT {out_path.name:34s} | {tris:6d} tris | {len(mats_list)} mats | {out_path.stat().st_size/(1024*1024):.2f} MB")


# ==============================================================================
# 1. HYPERBOLIC COOLING TOWER (SM_Nuclear_CoolingTower.glb)
# Real dimensions: 92 m tall, 70 m base diameter, 44 m throat at z=68 m, 48 m crown
# ==============================================================================
def build_cooling_tower():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    M = get_nuclear_materials()
    mats = [M["concrete_dirty"], M["concrete_dark"], M["steel_rusted"], M["pipe_steel"], M["water_dark"], M["warning_red"]]
    IDX_CONC, IDX_DARK, IDX_RUST, IDX_PIPE, IDX_WATER, IDX_RED = range(6)

    bm = bmesh.new()

    H_TOTAL = 92.0
    Z_INTAKE = 9.5       # bottom of hyperboloid shell (air intake height above basin)
    Z_THROAT = 68.0
    R_THROAT = 22.0      # 44 m diameter throat
    R_BASE_RING = 34.5   # 69 m diameter at Z_INTAKE
    R_CROWN = 24.4       # 48.8 m diameter at top

    # Solve asymmetric hyperbola r(z) = R_THROAT * sqrt(1 + ((z - Z_THROAT) / b)^2)
    b_low = (Z_THROAT - Z_INTAKE) / math.sqrt((R_BASE_RING / R_THROAT) ** 2 - 1.0)
    b_high = (H_TOTAL - Z_THROAT) / math.sqrt((R_CROWN / R_THROAT) ** 2 - 1.0)

    def shell_radius(z: float) -> float:
        b = b_low if z <= Z_THROAT else b_high
        return R_THROAT * math.sqrt(1.0 + ((z - Z_THROAT) / b) ** 2)

    def shell_thickness(z: float) -> float:
        # Thicker at bottom lintel (1.15m), thinner at throat (0.38m), stiffened crown (0.65m)
        t = (z - Z_INTAKE) / (H_TOTAL - Z_INTAKE)
        if t < 0.12:
            return 1.15 - 0.55 * (t / 0.12)
        if t > 0.92:
            return 0.45 + 0.35 * ((t - 0.92) / 0.08)
        return 0.45

    SEGS = 72
    RINGS = 32
    zs = [Z_INTAKE + (H_TOTAL - Z_INTAKE) * (i / RINGS) for i in range(RINGS + 1)]

    outer_rings = []
    inner_rings = []
    for z in zs:
        r_out = shell_radius(z)
        r_in = r_out - shell_thickness(z)
        oring, iring = [], []
        for s in range(SEGS):
            ang = 2.0 * math.pi * s / SEGS
            ca, sa = math.cos(ang), math.sin(ang)
            oring.append(bm.verts.new((r_out * ca, r_out * sa, z)))
            iring.append(bm.verts.new((r_in * ca, r_in * sa, z)))
        outer_rings.append(oring)
        inner_rings.append(iring)

    shell_faces = []
    for i in range(RINGS):
        for s in range(SEGS):
            sn = (s + 1) % SEGS
            fo = bm.faces.new((outer_rings[i][s], outer_rings[i][sn], outer_rings[i + 1][sn], outer_rings[i + 1][s]))
            fo.material_index = IDX_CONC
            fo.smooth = True
            shell_faces.append(fo)
            fi = bm.faces.new((inner_rings[i][sn], inner_rings[i][s], inner_rings[i + 1][s], inner_rings[i + 1][sn]))
            fi.material_index = IDX_DARK
            fi.smooth = True
            shell_faces.append(fi)

    # Bottom lintel lip & top stiffening crown walkway cornice
    for s in range(SEGS):
        sn = (s + 1) % SEGS
        fb = bm.faces.new((inner_rings[0][s], inner_rings[0][sn], outer_rings[0][sn], outer_rings[0][s]))
        fb.material_index = IDX_DARK
        ft = bm.faces.new((outer_rings[-1][s], outer_rings[-1][sn], inner_rings[-1][sn], inner_rings[-1][s]))
        ft.material_index = IDX_DARK

    # Exterior stiffening cornice ring at top + bottom lintel ring
    for z_ring, h_ring, protrude in ((H_TOTAL - 0.9, 1.4, 0.75), (Z_INTAKE + 0.6, 1.3, 0.45)):
        r0 = shell_radius(z_ring)
        r1 = r0 + protrude
        b0, b1, t0, t1 = [], [], [], []
        for s in range(SEGS):
            ang = 2.0 * math.pi * s / SEGS
            ca, sa = math.cos(ang), math.sin(ang)
            b0.append(bm.verts.new((r0 * ca, r0 * sa, z_ring - h_ring * 0.5)))
            b1.append(bm.verts.new((r1 * ca, r1 * sa, z_ring - h_ring * 0.5)))
            t0.append(bm.verts.new((r0 * ca, r0 * sa, z_ring + h_ring * 0.5)))
            t1.append(bm.verts.new((r1 * ca, r1 * sa, z_ring + h_ring * 0.5)))
        for s in range(SEGS):
            sn = (s + 1) % SEGS
            for quad in (
                (b1[s], b1[sn], t1[sn], t1[s]),
                (t0[s], t1[s], t1[sn], t0[sn]),
                (b1[s], b0[s], b0[sn], b1[sn]),
            ):
                f = bm.faces.new(quad)
                f.material_index = IDX_DARK
                f.smooth = True

    # 36 pairs of diagonal concrete V/X raker columns supporting shell above cold-water basin
    N_PAIRS = 36
    R_FOOT = R_BASE_RING + 2.6
    Z_BASIN_WALL = 2.1
    for i in range(N_PAIRS):
        ang_top = 2.0 * math.pi * i / N_PAIRS
        ang_l = ang_top - (math.pi / N_PAIRS)
        ang_r = ang_top + (math.pi / N_PAIRS)
        p_top = Vector((math.cos(ang_top) * (R_BASE_RING - 0.35), math.sin(ang_top) * (R_BASE_RING - 0.35), Z_INTAKE + 0.3))
        p_l = Vector((math.cos(ang_l) * R_FOOT, math.sin(ang_l) * R_FOOT, Z_BASIN_WALL - 0.2))
        p_r = Vector((math.cos(ang_r) * R_FOOT, math.sin(ang_r) * R_FOOT, Z_BASIN_WALL - 0.2))
        add_cylinder_between(bm, p_l, p_top, 0.44, 8, IDX_DARK, cap=True)
        add_cylinder_between(bm, p_r, p_top, 0.44, 8, IDX_DARK, cap=True)

    # Circular cold-water collection basin wall (outer radius 38.4m, height 2.3m) + dark water plane
    R_BASIN_OUT = R_FOOT + 1.4
    R_BASIN_IN = R_FOOT - 0.6
    bo0, bo1, bi0, bi1 = [], [], [], []
    for s in range(SEGS):
        ang = 2.0 * math.pi * s / SEGS
        ca, sa = math.cos(ang), math.sin(ang)
        bo0.append(bm.verts.new((R_BASIN_OUT * ca, R_BASIN_OUT * sa, 0.0)))
        bo1.append(bm.verts.new((R_BASIN_OUT * ca, R_BASIN_OUT * sa, Z_BASIN_WALL)))
        bi0.append(bm.verts.new((R_BASIN_IN * ca, R_BASIN_IN * sa, 0.0)))
        bi1.append(bm.verts.new((R_BASIN_IN * ca, R_BASIN_IN * sa, Z_BASIN_WALL)))
    for s in range(SEGS):
        sn = (s + 1) % SEGS
        for quad in (
            (bo0[s], bo0[sn], bo1[sn], bo1[s]),
            (bo1[s], bo1[sn], bi1[sn], bi1[s]),
            (bi1[s], bi1[sn], bi0[sn], bi0[s]),
        ):
            f = bm.faces.new(quad)
            f.material_index = IDX_DARK
            f.smooth = True

    # Dark water surface inside basin + interior baffle deck at z=10.5m
    w_ctr = bm.verts.new((0.0, 0.0, 1.5))
    w_ring = [bm.verts.new((R_BASIN_IN * math.cos(2 * math.pi * s / SEGS), R_BASIN_IN * math.sin(2 * math.pi * s / SEGS), 1.5)) for s in range(SEGS)]
    for s in range(SEGS):
        f = bm.faces.new((w_ctr, w_ring[s], w_ring[(s + 1) % SEGS]))
        f.material_index = IDX_WATER

    # Interior fill/drift-eliminator concrete ring at z=11.0m (prevents seeing empty void from ground)
    f_ctr = bm.verts.new((0.0, 0.0, Z_INTAKE + 1.8))
    r_fill = shell_radius(Z_INTAKE + 1.8) - 0.6
    f_ring = [bm.verts.new((r_fill * math.cos(2 * math.pi * s / SEGS), r_fill * math.sin(2 * math.pi * s / SEGS), Z_INTAKE + 1.8)) for s in range(SEGS)]
    for s in range(SEGS):
        f = bm.faces.new((f_ctr, f_ring[(s + 1) % SEGS], f_ring[s]))
        f.material_index = IDX_DARK

    # Top crown safety railing + 8 aviation warning lights around rim
    R_RAIL = R_CROWN + 0.55
    for i in range(36):
        ang = 2.0 * math.pi * i / 36
        ang_n = 2.0 * math.pi * ((i + 1) % 36) / 36
        p_base = Vector((R_RAIL * math.cos(ang), R_RAIL * math.sin(ang), H_TOTAL))
        p_top = p_base + Vector((0, 0, 1.25))
        p_top_n = Vector((R_RAIL * math.cos(ang_n), R_RAIL * math.sin(ang_n), H_TOTAL + 1.25))
        add_cylinder_between(bm, p_base, p_top, 0.05, 5, IDX_RUST)
        add_cylinder_between(bm, p_top, p_top_n, 0.045, 5, IDX_RUST)
        add_cylinder_between(bm, p_base + Vector((0, 0, 0.65)), p_top_n - Vector((0, 0, 0.60)), 0.035, 5, IDX_RUST)

    for i in range(8):
        ang = 2.0 * math.pi * i / 8
        pole_base = Vector((R_RAIL * math.cos(ang), R_RAIL * math.sin(ang), H_TOTAL))
        pole_top = pole_base + Vector((0, 0, 2.8))
        add_cylinder_between(bm, pole_base, pole_top, 0.08, 6, IDX_RUST)
        add_box(bm, pole_top + Vector((0, 0, 0.32)), Vector((0.45, 0.45, 0.55)), IDX_RED)

    # Vertical exterior maintenance ladder & rest platforms along +X meridian
    prev_l = None
    prev_r = None
    for step_i in range(28):
        z = Z_INTAKE + (H_TOTAL - Z_INTAKE) * (step_i / 27.0)
        r = shell_radius(z) + 0.65
        pl = Vector((r, -0.32, z))
        pr = Vector((r, 0.32, z))
        if prev_l is not None:
            add_cylinder_between(bm, prev_l, pl, 0.05, 5, IDX_RUST)
            add_cylinder_between(bm, prev_r, pr, 0.05, 5, IDX_RUST)
            add_cylinder_between(bm, pl, pr, 0.035, 5, IDX_RUST)
        if step_i in (9, 18):
            add_box(bm, Vector((r + 0.6, 0.0, z)), Vector((1.6, 2.8, 0.18)), IDX_RUST)
        prev_l, prev_r = pl, pr

    # Attached concrete cold-water pumphouse & 2 large return pipes on +X side
    add_box(bm, Vector((R_BASIN_OUT + 5.5, 0.0, 3.2)), Vector((11.0, 14.0, 6.4)), IDX_CONC)
    add_box(bm, Vector((R_BASIN_OUT + 5.5, 0.0, 6.55)), Vector((11.4, 14.4, 0.35)), IDX_DARK)
    for dy in (-2.4, 2.4):
        add_cylinder_between(bm, Vector((R_BASIN_OUT - 1.5, dy, 2.6)), Vector((R_BASIN_OUT + 13.5, dy, 2.6)), 0.72, 12, IDX_PIPE)

    # Apply metric UVs across everything, then cylindrical seamless UVs on the hyperboloid shell
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    apply_metric_box_uvs(bm, tile_m=4.5)
    apply_cylindrical_uvs(bm, shell_faces, circumference_tile_m=6.0, height_tile_m=6.0)

    finalize_and_export("SM_Nuclear_CoolingTower", bm, mats, OUT_DIR / "SM_Nuclear_CoolingTower.glb")


# ==============================================================================
# 2. PWR REACTOR CONTAINMENT DOME (SM_Nuclear_ReactorDome.glb)
# Real dimensions: 34 m diameter cylinder, 43 m total height, 24 vertical buttresses,
# equipment airlock hatch, exterior steel staircase & 3 main steam pipes
# ==============================================================================
def build_reactor_dome():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    M = get_nuclear_materials()
    mats = [M["concrete_dirty"], M["concrete_dark"], M["steel_rusted"], M["pipe_steel"], M["metal_cladding"], M["warning_red"]]
    IDX_CONC, IDX_DARK, IDX_RUST, IDX_PIPE, IDX_CLAD, IDX_RED = range(6)

    bm = bmesh.new()

    R_CYL = 17.0
    H_CYL = 30.0
    H_DOME = 12.5
    SEGS = 64

    # Heavy concrete base plinth apron
    res_base = bmesh.ops.create_cone(
        bm, cap_ends=True, cap_tris=False, segments=SEGS,
        radius1=R_CYL + 1.8, radius2=R_CYL + 1.4, depth=2.6,
        matrix=Matrix.Translation((0, 0, 1.3))
    )
    bverts = set(res_base["verts"])
    for f in bm.faces:
        if all(v in bverts for v in f.verts):
            f.material_index = IDX_DARK
            f.smooth = True

    # Main cylindrical containment wall + ellipsoidal dome cap
    cyl_faces = []
    rings = []
    # Cylinder rings
    for i in range(9):
        z = 2.4 + (H_CYL - 2.4) * (i / 8.0)
        ring = [bm.verts.new((R_CYL * math.cos(2 * math.pi * s / SEGS), R_CYL * math.sin(2 * math.pi * s / SEGS), z)) for s in range(SEGS)]
        rings.append(ring)
    # Ellipsoidal dome rings
    DOME_STEPS = 12
    for j in range(1, DOME_STEPS):
        phi = (math.pi * 0.5) * (j / DOME_STEPS)
        r = R_CYL * math.cos(phi)
        z = H_CYL + H_DOME * math.sin(phi)
        ring = [bm.verts.new((r * math.cos(2 * math.pi * s / SEGS), r * math.sin(2 * math.pi * s / SEGS), z)) for s in range(SEGS)]
        rings.append(ring)

    for i in range(len(rings) - 1):
        for s in range(SEGS):
            sn = (s + 1) % SEGS
            f = bm.faces.new((rings[i][s], rings[i][sn], rings[i + 1][sn], rings[i + 1][s]))
            f.material_index = IDX_CONC
            f.smooth = True
            cyl_faces.append(f)

    # Dome apex cap
    apex = bm.verts.new((0.0, 0.0, H_CYL + H_DOME))
    for s in range(SEGS):
        f = bm.faces.new((rings[-1][s], rings[-1][(s + 1) % SEGS], apex))
        f.material_index = IDX_CONC
        f.smooth = True
        cyl_faces.append(f)

    # Ring beam cornice at springline (z = H_CYL)
    for z_c, h_c, dr in ((H_CYL - 0.6, 1.8, 0.9), (H_CYL * 0.52, 0.7, 0.35)):
        res_r = bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=SEGS,
            radius1=R_CYL + dr, radius2=R_CYL + dr, depth=h_c,
            matrix=Matrix.Translation((0, 0, z_c))
        )
        rv = set(res_r["verts"])
        for f in bm.faces:
            if all(v in rv for v in f.verts):
                f.material_index = IDX_DARK
                f.smooth = True

    # 24 vertical prestressed concrete buttress ribs around cylinder
    for i in range(24):
        ang = 2.0 * math.pi * i / 24
        pos = Vector(((R_CYL + 0.35) * math.cos(ang), (R_CYL + 0.35) * math.sin(ang), 16.0))
        add_box(bm, pos, Vector((0.85, 0.75, 27.6)), IDX_DARK, rot_euler=(0.0, 0.0, ang))

    # Aviation beacon + lightning mast on top of dome
    add_cylinder_between(bm, Vector((0, 0, H_CYL + H_DOME - 0.3)), Vector((0, 0, H_CYL + H_DOME + 5.5)), 0.14, 8, IDX_RUST)
    add_box(bm, Vector((0, 0, H_CYL + H_DOME + 5.75)), Vector((0.55, 0.55, 0.65)), IDX_RED)

    # Heavy circular equipment airlock hatch & reinforced concrete alcove on +X side
    add_box(bm, Vector((R_CYL + 2.4, 0.0, 6.2)), Vector((6.5, 9.6, 12.4)), IDX_CONC)
    add_box(bm, Vector((R_CYL + 2.4, 0.0, 12.55)), Vector((6.9, 10.0, 0.4)), IDX_DARK)
    add_cylinder_between(bm, Vector((R_CYL + 5.3, 0.0, 5.2)), Vector((R_CYL + 6.4, 0.0, 5.2)), 3.2, 24, IDX_RUST)
    add_cylinder_between(bm, Vector((R_CYL + 6.2, 0.0, 5.2)), Vector((R_CYL + 6.7, 0.0, 5.2)), 2.6, 24, IDX_PIPE)

    # Auxiliary concrete fuel-handling annex wing on -Y side
    add_box(bm, Vector((-3.5, -(R_CYL + 5.8), 9.5)), Vector((22.0, 14.0, 19.0)), IDX_CONC)
    add_box(bm, Vector((-3.5, -(R_CYL + 5.8), 19.2)), Vector((22.6, 14.6, 0.5)), IDX_DARK)
    # Corrugated cladding upper penthouse on annex
    add_box(bm, Vector((-3.5, -(R_CYL + 5.8), 22.0)), Vector((16.0, 10.0, 5.2)), IDX_CLAD)
    # Rooftop exhaust stack
    add_cylinder_between(bm, Vector((3.0, -(R_CYL + 5.5), 24.0)), Vector((3.0, -(R_CYL + 5.5), 38.0)), 1.05, 16, IDX_PIPE)
    add_cylinder_between(bm, Vector((3.0, -(R_CYL + 5.5), 37.5)), Vector((3.0, -(R_CYL + 5.5), 38.5)), 1.25, 16, IDX_RED)

    # 3 heavy main steam & feedwater pipes exiting +Y side on steel A-frame supports
    for idx_p, dx in enumerate((-3.2, 0.0, 3.2)):
        z_pipe = 8.5 + idx_p * 0.0
        add_cylinder_between(bm, Vector((dx, R_CYL - 1.0, z_pipe)), Vector((dx, R_CYL + 14.0, z_pipe)), 0.58, 12, IDX_PIPE)
        add_cylinder_between(bm, Vector((dx, R_CYL + 14.0, z_pipe)), Vector((dx, R_CYL + 14.0, 1.5)), 0.58, 12, IDX_PIPE)
    for y_sup in (R_CYL + 4.5, R_CYL + 10.5):
        add_box(bm, Vector((0.0, y_sup, 7.8)), Vector((9.2, 0.45, 0.45)), IDX_RUST)
        add_cylinder_between(bm, Vector((-4.2, y_sup, 0.0)), Vector((-4.2, y_sup, 8.0)), 0.22, 6, IDX_RUST)
        add_cylinder_between(bm, Vector((4.2, y_sup, 0.0)), Vector((4.2, y_sup, 8.0)), 0.22, 6, IDX_RUST)

    # Exterior steel maintenance staircase tower on -X side
    x_st = -(R_CYL + 2.2)
    for cx in (-1.6, 1.6):
        for cy in (-2.2, 2.2):
            add_cylinder_between(bm, Vector((x_st + cx, cy, 0.0)), Vector((x_st + cx, cy, H_CYL)), 0.14, 6, IDX_RUST)
    for lvl in range(1, 8):
        zl = lvl * 3.8
        add_box(bm, Vector((x_st, 0.0, zl)), Vector((3.4, 4.6, 0.18)), IDX_RUST)
        add_box(bm, Vector((x_st, 2.25, zl + 0.65)), Vector((3.4, 0.08, 1.1)), IDX_RUST)
        add_box(bm, Vector((x_st, -2.25, zl + 0.65)), Vector((3.4, 0.08, 1.1)), IDX_RUST)
        add_box(bm, Vector((x_st - 1.65, 0.0, zl + 0.65)), Vector((0.08, 4.6, 1.1)), IDX_RUST)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    apply_metric_box_uvs(bm, tile_m=4.0)
    apply_cylindrical_uvs(bm, cyl_faces, circumference_tile_m=5.0, height_tile_m=5.0)

    finalize_and_export("SM_Nuclear_ReactorDome", bm, mats, OUT_DIR / "SM_Nuclear_ReactorDome.glb")


# ==============================================================================
# 3. TURBINE HALL & STEP-UP TRANSFORMER YARD (SM_Nuclear_TurbineHall.glb)
# Real dimensions: 72 m x 32 m x 23 m main turbine hall + 3 blast-walled transformer bays
# ==============================================================================
def build_turbine_hall():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    M = get_nuclear_materials()
    mats = [M["concrete_dirty"], M["concrete_dark"], M["metal_cladding"], M["steel_rusted"], M["pipe_steel"], M["roof_metal"], M["glass"]]
    IDX_CONC, IDX_DARK, IDX_CLAD, IDX_RUST, IDX_PIPE, IDX_ROOF, IDX_GLASS = range(7)

    bm = bmesh.new()

    L, W, H = 72.0, 30.0, 22.0
    # Heavy reinforced concrete lower blast wall (0 -> 7.5m)
    add_box(bm, Vector((0, 0, 3.75)), Vector((L, W, 7.5)), IDX_CONC)
    # Upper corrugated steel cladding shell (7.5 -> 21.5m)
    add_box(bm, Vector((0, 0, 14.5)), Vector((L - 0.6, W - 0.6, 14.0)), IDX_CLAD)
    # Parapet & roof slab
    add_box(bm, Vector((0, 0, 21.8)), Vector((L + 0.4, W + 0.4, 0.8)), IDX_ROOF)
    # Roof monitor / skylight vent ridge along center
    add_box(bm, Vector((0, 0, 23.6)), Vector((L - 10.0, 7.2, 2.8)), IDX_CLAD)
    add_box(bm, Vector((0, 0, 25.15)), Vector((L - 9.4, 7.8, 0.35)), IDX_ROOF)

    # Structural exterior steel pilasters every 8 m along long walls
    for xi in range(-4, 5):
        x = xi * 8.0
        for sy in (-1.0, 1.0):
            add_box(bm, Vector((x, sy * (W * 0.5 + 0.15), 11.0)), Vector((0.65, 0.75, 22.0)), IDX_DARK)
            # Clerestory industrial window band between pilasters
            if xi < 4:
                add_box(bm, Vector((x + 4.0, sy * (W * 0.5 - 0.15), 17.5)), Vector((6.6, 0.35, 3.2)), IDX_GLASS)

    # Large roll-up maintenance bay doors on +X and -X ends
    for sx in (-1.0, 1.0):
        add_box(bm, Vector((sx * (L * 0.5 + 0.1), 0.0, 3.5)), Vector((0.4, 8.5, 7.0)), IDX_RUST)
        add_box(bm, Vector((sx * (L * 0.5 + 0.25), 0.0, 7.3)), Vector((0.8, 9.4, 0.7)), IDX_DARK)

    # 6 rooftop heavy industrial turbine exhaust stacks + HVAC boxes
    for xi in (-22.0, -13.0, -4.0, 5.0, 14.0, 23.0):
        add_cylinder_between(bm, Vector((xi, -7.5, 22.0)), Vector((xi, -7.5, 27.5)), 0.95, 14, IDX_PIPE)
        add_box(bm, Vector((xi, 7.8, 23.2)), Vector((4.2, 3.2, 2.4)), IDX_RUST)

    # Outdoor high-voltage step-up transformer yard on +Y side (3 bays with concrete blast firewalls)
    y_yard = W * 0.5 + 6.5
    # Concrete yard pad
    add_box(bm, Vector((0.0, y_yard, 0.3)), Vector((40.0, 13.0, 0.6)), IDX_DARK)
    # 4 concrete blast firewall dividers
    for xw in (-18.0, -6.0, 6.0, 18.0):
        add_box(bm, Vector((xw, y_yard - 0.5, 4.6)), Vector((0.75, 11.5, 8.6)), IDX_CONC)
    # 3 heavy step-up oil transformers + cooling radiator fins + 3 ceramic HV bushings each
    for xt in (-12.0, 0.0, 12.0):
        add_box(bm, Vector((xt, y_yard - 0.5, 2.8)), Vector((6.4, 4.6, 4.8)), IDX_RUST)
        # Conservator cylinder tank on top
        add_cylinder_between(bm, Vector((xt - 2.4, y_yard - 0.5, 6.2)), Vector((xt + 2.4, y_yard - 0.5, 6.2)), 0.65, 12, IDX_PIPE)
        # 3 angled HV insulator bushings
        for bx in (-1.8, 0.0, 1.8):
            add_cylinder_between(bm, Vector((xt + bx, y_yard + 0.8, 5.1)), Vector((xt + bx, y_yard + 2.2, 8.2)), 0.22, 8, IDX_PIPE)
    # High-voltage steel gantry portal frame over transformer yard
    for xp in (-18.0, -6.0, 6.0, 18.0):
        add_box(bm, Vector((xp, y_yard + 5.2, 7.5)), Vector((0.6, 0.6, 15.0)), IDX_RUST)
    add_box(bm, Vector((0.0, y_yard + 5.2, 14.5)), Vector((38.0, 0.85, 0.95)), IDX_RUST)

    # Condenser cooling water pipes entering -Y side
    for xp in (-16.0, -8.0, 8.0, 16.0):
        add_cylinder_between(bm, Vector((xp, -(W * 0.5), 2.4)), Vector((xp, -(W * 0.5 + 8.0), 2.4)), 0.78, 12, IDX_PIPE)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    apply_metric_box_uvs(bm, tile_m=4.0)

    finalize_and_export("SM_Nuclear_TurbineHall", bm, mats, OUT_DIR / "SM_Nuclear_TurbineHall.glb")


if __name__ == "__main__":
    build_cooling_tower()
    build_reactor_dome()
    build_turbine_hall()
    print("ALL NUCLEAR PLANT ASSETS BUILT SUCCESSFULLY")
