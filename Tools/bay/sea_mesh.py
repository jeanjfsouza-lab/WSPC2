"""Builds the sea of the Bay city as a mesh (Blender): one flat sheet at 0 m, with a hole along every tunnel.

  blender -b --factory-startup --python Tools/bay/sea_mesh.py

Input:  Saved/Bay/network.json, Tools/bay/structures.py (TUNNELS)
Output: Saved/Bay/sea/Sea.glb    mesh in metres, x east, y north, z = 0; one material slot, Water
        prints the sheet's size and the holes it has

Why: the sea used to be one plane across the whole map, hidden wherever land stands above it. A tunnel's road
goes below sea level, and there the plane showed: a sheet of water half way up the tunnel and across the foot
of its ramps. The sheet now leaves out the footprint of every tunnel (its walls' outer faces and two metres
more, all of it under ground that a sector builds). build_bay.py, stage "sea", places this mesh in place of
the engine's plane when the file exists. Run it again whenever a tunnel is added or moved.
UVs run from 0 to 1 across the sheet, as on the engine's plane it replaces.
"""
import os
import sys

import bpy
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import structures
from common import DATA, load_json

CENTRE = (800.0, 275.0)         # centre of the map's frame (the old plane stood here)
SIZE_M = 16000.0
HOLE_EXTRA_M = 2.0
FRAME_M = 60.0                  # a rectangle this far round each hole keeps the thin triangles of its rim short


def main():
    net = load_json("network.json")
    half = SIZE_M / 2.0
    x0, y0 = CENTRE[0] - half, CENTRE[1] - half
    sheet = [(x0, y0), (x0 + SIZE_M, y0), (x0 + SIZE_M, y0 + SIZE_M), (x0, y0 + SIZE_M)]
    holes = structures.tunnel_rings(net, HOLE_EXTRA_M)
    frames = []
    for _, ring in holes:
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        frames.append([(min(xs) - FRAME_M, min(ys) - FRAME_M), (max(xs) + FRAME_M, min(ys) - FRAME_M),
                       (max(xs) + FRAME_M, max(ys) + FRAME_M), (min(xs) - FRAME_M, max(ys) + FRAME_M)])
    verts, faces = [], []
    for ring in [sheet] + frames + [ring for _, ring in holes]:
        base = len(verts)
        verts += [Vector((p[0] - CENTRE[0], p[1] - CENTRE[1])) for p in ring]
        faces.append(list(range(base, base + len(ring))))
    hole_faces = set(range(1 + len(frames), len(faces)))
    v2, _, tris, _, _, orig = delaunay_2d_cdt(verts, [], faces, 1, 1e-4, True)
    keep = [tuple(tri) for tri, src in zip(tris, orig) if len(tri) == 3 and 0 in src and not hole_faces & set(src)]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    mesh = bpy.data.meshes.new("Bay_Sea")
    mesh.from_pydata([(v.x + CENTRE[0], v.y + CENTRE[1], 0.0) for v in v2], [], keep)
    mesh.materials.append(bpy.data.materials.new("Water"))
    uv = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        if poly.normal.z < 0:
            poly.flip()
    mesh.update()
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            co = mesh.vertices[mesh.loops[li].vertex_index].co
            uv.data[li].uv = ((co.x - x0) / SIZE_M, (co.y - y0) / SIZE_M)
    mesh.validate()
    obj = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    out_dir = os.path.join(DATA, "sea")
    os.makedirs(out_dir, exist_ok=True)
    glb = os.path.join(out_dir, "Sea.glb")
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_apply=True, export_materials="EXPORT")
    area = sum(p.area for p in mesh.polygons)
    print("SEA: sheet %.0f x %.0f km, %d triangles, %d holes (%s), %.0f m2 left out -> %s" % (
        SIZE_M / 1000.0, SIZE_M / 1000.0, len(mesh.polygons), len(holes), ", ".join(n for n, _ in holes),
        SIZE_M * SIZE_M - area, glb))


main()
