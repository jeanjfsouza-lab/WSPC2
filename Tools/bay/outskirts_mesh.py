"""Builds the outskirts round the Bay's map as meshes (Blender): far ground, far water and the exit roads.

  blender -b --factory-startup --python Tools/bay/outskirts_mesh.py

Input:  Saved/Bay/outskirts/ground.npz, outskirts.json (plan_outskirts.py)
Output: Saved/Bay/outskirts/Outskirts.glb   meshes in metres, x east, y north, z up:
          Bay_Outskirts_Fine_<i>     the near ring (a vertex every 50 m), in tiles, with a skirt 25 m down along
                                     the frame (under the landscape's edge) and along its outer edge (under the
                                     coarse ring), so no crack shows between them
          Bay_Outskirts_Coarse_<i>   the far ring (every 400 m)
          Bay_Outskirts_Water_<i>    flat water at 0 m beyond the sea sheet (sea_mesh.py, 16 km), for the rivers
          Bay_Outskirts_Road_<n>_<i> each exit road, a strip on the ground, in pieces of about a kilometre
        Material slots: Outskirts (UVs 0..1 over the coarse extent, north at v = 0, for colour.png), Water, Road.
No collision is wanted on any of it: the player never gets there (build_bay.py, stage "outskirts").
"""
import json
import math
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import solidkit
from common import DATA

OUT = os.path.join(DATA, "outskirts")
SKIRT_M = 25.0
TILES = 4                                     # the near ring in TILES x TILES pieces (each culls on its own)
SEA = (-7200.0, -7725.0, 8800.0, 8275.0)      # sea_mesh.py: the sheet the sea already covers (x0, y0, x1, y1)
ROAD_PIECE_M = 1000.0


def material(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    return m


def make_object(name, verts, faces, uvs, slot):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    mesh.update()
    uv = mesh.uv_layers.new(name="UVMap")
    data = uv.data
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            vi = mesh.loops[li].vertex_index
            data[li].uv = (float(uvs[vi][0]), float(uvs[vi][1]))
    mesh.materials.append(material(slot))
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def grid_objects(prefix, h, x0, y0, step, hole, extent, tiles, skirt_inner, skirt_outer):
    """A height grid (row 0 north) as meshes, quads inside `hole` (x0, y0, x1, y1) left out, in tiles x tiles."""
    ny, nx = h.shape
    cx0, cy0, cx1, cy1 = extent
    xs = x0 + np.arange(nx) * step
    ys = y0 - np.arange(ny) * step
    objs = []
    for ty in range(tiles):
        for tx in range(tiles):
            r0, r1 = ty * (ny - 1) // tiles, (ty + 1) * (ny - 1) // tiles
            c0, c1 = tx * (nx - 1) // tiles, (tx + 1) * (nx - 1) // tiles
            index, verts, uvs, faces = {}, [], [], []

            def vid(r, c, dz=0.0, key=None):
                k = key or (r, c, dz)
                if k not in index:
                    index[k] = len(verts)
                    x, y = float(xs[c]), float(ys[r])
                    verts.append((x, y, float(h[r, c]) + dz))
                    uvs.append(((x - cx0) / (cx1 - cx0), (cy1 - y) / (cy1 - cy0)))
                return index[k]

            def inside(r, c):
                return hole[0] - 1e-3 <= xs[c] <= hole[2] + 1e-3 and hole[1] - 1e-3 <= ys[r] <= hole[3] + 1e-3

            for r in range(r0, r1):
                for c in range(c0, c1):
                    if all(inside(rr, cc) for rr, cc in ((r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1))):
                        continue
                    faces.append((vid(r + 1, c), vid(r + 1, c + 1), vid(r, c + 1), vid(r, c)))
            # skirts: along each boundary edge of the kept quads that lies on the hole's rim (inner) or on the grid's
            # outer rim (outer), a wall straight down
            edges = {}
            for f in faces:
                for a, b in zip(f, f[1:] + f[:1]):
                    edges[(min(a, b), max(a, b))] = edges.get((min(a, b), max(a, b)), 0) + 1
            for (a, b), n in list(edges.items()):
                if n != 1:
                    continue
                (xa, ya, za), (xb, yb, zb) = verts[a], verts[b]
                on_hole = (abs(xa - xb) < 1e-3 and (abs(xa - hole[0]) < 1e-3 or abs(xa - hole[2]) < 1e-3)) or \
                          (abs(ya - yb) < 1e-3 and (abs(ya - hole[1]) < 1e-3 or abs(ya - hole[3]) < 1e-3))
                on_outer = (abs(xa - xb) < 1e-3 and (abs(xa - xs[0]) < 1e-3 or abs(xa - xs[-1]) < 1e-3)) or \
                           (abs(ya - yb) < 1e-3 and (abs(ya - ys[0]) < 1e-3 or abs(ya - ys[-1]) < 1e-3))
                if (on_hole and skirt_inner) or (on_outer and skirt_outer):
                    a2, b2 = len(verts), len(verts) + 1
                    verts += [(xa, ya, za - SKIRT_M), (xb, yb, zb - SKIRT_M)]
                    uvs += [uvs[a], uvs[b]]
                    faces.append((a, b, b2, a2))
                    faces.append((a2, b2, b, a))           # both sides: it is seen from in and out
            if faces:
                objs.append(make_object("Bay_Outskirts_%s_%d" % (prefix, len(objs)), verts, faces, uvs, "Outskirts"))
    return objs


def main():
    with open(os.path.join(OUT, "outskirts.json")) as f:
        plan = json.load(f)
    g = dict(np.load(os.path.join(OUT, "ground.npz")))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    frame = plan["frame"]                                       # x0, y0, x1, y1
    fx0, fy0, fx1, fy1, _ = plan["fine"]
    cx0, cy0, cx1, cy1, _ = plan["coarse"]
    extent = (cx0, cy0, cx1, cy1)
    objects = []
    objects += grid_objects("Fine", g["fine_h"], float(g["fine_x0"]), float(g["fine_y0"]), float(g["fine_step"]),
                            frame, extent, TILES, True, True)
    objects += grid_objects("Coarse", g["coarse_h"], float(g["coarse_x0"]), float(g["coarse_y0"]), float(g["coarse_step"]),
                            (fx0, fy0, fx1, fy1), extent, 2, False, False)

    # far water: the coarse extent outside the sea sheet, at 0 m (only the rivers show it: the land stands above)
    sx0, sy0, sx1, sy1 = SEA
    rects = [(cx0, cy0, sx0, cy1), (sx1, cy0, cx1, cy1), (sx0, cy0, sx1, sy0), (sx0, sy1, sx1, cy1)]
    for i, (a0, b0, a1, b1) in enumerate(rects):
        verts = [(a0, b0, 0.0), (a1, b0, 0.0), (a1, b1, 0.0), (a0, b1, 0.0)]
        uvs = [((x - sx0) / (sx1 - sx0), (y - sy0) / (sy1 - sy0)) for x, y, _ in verts]
        objects.append(make_object("Bay_Outskirts_Water_%d" % i, verts, [(0, 1, 2, 3)], uvs, "Water"))

    # exit roads: strips on the ground, in pieces
    for ex in plan["exits"]:
        line = np.array(ex["line"], np.float64)
        half = ex["width_m"] / 2.0
        d = np.gradient(line[:, :2], axis=0)
        d /= np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-9)[:, None]
        nrm = np.stack([-d[:, 1], d[:, 0]], -1)
        s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(line[:, :2], axis=0).T))])
        piece = (s // ROAD_PIECE_M).astype(int)
        for p in range(piece.max() + 1):
            idx = np.nonzero(piece == p)[0]
            if p < piece.max():
                idx = np.append(idx, idx[-1] + 1)
            verts, uvs, faces = [], [], []
            for k, i in enumerate(idx):
                for side in (-1.0, 1.0):
                    x, y = line[i, :2] + nrm[i] * half * side
                    verts.append((float(x), float(y), float(line[i, 2])))
                    uvs.append(((side + 1) / 2.0, float(s[i]) / (2 * half)))
                if k:
                    a = 2 * (k - 1)
                    faces.append((a, a + 1, a + 3, a + 2))
            objects.append(make_object("Bay_Outskirts_Road_%s_%d" % (ex["name"], p), verts, faces, uvs, "Road"))

    path = os.path.join(OUT, "Outskirts.glb")
    faces = solidkit.export_objects(objects, path, sharp_deg=80.0)
    print("OUTSKIRTS_MESH %d meshes, %d faces -> %s" % (len(objects), faces, path))


main()
