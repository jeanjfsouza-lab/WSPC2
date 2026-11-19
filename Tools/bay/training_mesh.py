"""The two pieces of the training ground's layouts that no pack has: the ramp of operation 04 and a target stand.

  blender -b --factory-startup --python Tools/bay/training_mesh.py

Output: Saved/Bay/training/SM_Bay_TrainingRamp.glb     metres, long axis x, z up, origin at the centre of its footprint
                                                       on the ground. Material slots: Road, PaintWhite, Concrete
        Saved/Bay/training/SM_Bay_TrainingTarget.glb   metres, the plate faces +X, origin at the foot of the post.
                                                       Material slots: Steel, PaintWhite, PaintYellow
build_bay.py (stage "training") imports both into /Game/Bay/Training and gives the slots the Bay's own materials;
plan_training.py places them.

The ramp is the one the campaign's model has on the south straight of operation 04's yard: a table 4.27 m high
(4.4 m in the model's metres), 64 m long and 18 m wide between vertical side walls, with a ramp of 25 % at each end
(24 % in the model) and 24 m of table between them. Here the foot and the crest of each ramp are rounded (a 3 m
vertical curve each), so a car neither digs in at the foot nor leaves the ground before the crest at walking pace; a
kerb 30 cm high runs along both sides.
The target is a steel plate 50 cm square on a post, its centre 1.25 m above the ground.
UVs count metres / 4, like the sector meshes, so the Bay's asphalt and concrete tile as on the streets.
"""
import math
import os
import sys

import bmesh
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "Saved", "Bay", "training")
UV_M = 4.0
RAMP_TOP_M = 24.0
RAMP_RUN_M = 20.0           # each ramp, foot to crest
RAMP_H = 4.27
RAMP_W = 18.0
CURVE_M = 3.0               # length of the vertical curve at a ramp's foot and at its crest
KERB_W, KERB_H = 0.30, 0.30
LINE_IN, LINE_W = 0.45, 0.15        # the white edge line: distance from the kerb, width
FOOT_M = -0.40              # the side walls reach this far below the ground


def ramp_profile():
    """(distance from the west foot, height) along the ramp's whole length: foot curve, straight grade, crest curve,
    the table, and the same mirrored."""
    grade = RAMP_H / (RAMP_RUN_M - CURVE_M)             # the straight part's slope, so that the two curves fit
    half = []
    # foot curve: slope 0 -> grade over CURVE_M
    steps = 8
    for k in range(steps + 1):
        s = CURVE_M * k / steps
        half.append((s, grade * s * s / (2.0 * CURVE_M)))
    z_foot = grade * CURVE_M / 2.0
    s_crest = RAMP_RUN_M - CURVE_M
    half.append((s_crest, z_foot + grade * (s_crest - CURVE_M)))
    z_crest = half[-1][1]
    for k in range(1, steps + 1):
        s = CURVE_M * k / steps
        half.append((s_crest + s, z_crest + grade * s - grade * s * s / (2.0 * CURVE_M)))
    top = half[-1][1]
    half = [(s, z * RAMP_H / top) for s, z in half]     # exactly RAMP_H at the crest
    total = 2.0 * RAMP_RUN_M + RAMP_TOP_M
    return half + [(total - s, z) for s, z in reversed(half)]


def export(obj, name):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name + ".glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_materials="EXPORT")
    return path


def new_object(name, bm, slots):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for slot in slots:
        # one material per name in the whole file: a second "PaintWhite" would be exported as "PaintWhite.001"
        # and the importer would find no material for that slot (the target's face, 2026-11-17)
        me.materials.append(bpy.data.materials.get(slot) or bpy.data.materials.new(slot))
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def ramp():
    slots = ["Road", "PaintWhite", "Concrete"]
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    profile = ramp_profile()
    total = profile[-1][0]
    x0 = -total / 2.0
    half = RAMP_W / 2.0

    def face(coords, slot, uvs):
        f = bm.faces.new([bm.verts.new(p) for p in coords])     # wound counter-clockwise seen from outside
        f.material_index = slots.index(slot)
        for loop, t in zip(f.loops, uvs):
            loop[uv].uv = t
        return f

    # the running surface in strips across its width: asphalt, white line, asphalt, white line, asphalt
    inner = half - KERB_W
    bands = [(-inner, -inner + LINE_IN, "Road"), (-inner + LINE_IN, -inner + LINE_IN + LINE_W, "PaintWhite"),
             (-inner + LINE_IN + LINE_W, inner - LINE_IN - LINE_W, "Road"), (inner - LINE_IN - LINE_W, inner - LINE_IN, "PaintWhite"),
             (inner - LINE_IN, inner, "Road")]
    for (s0, z0), (s1, z1) in zip(profile[:-1], profile[1:]):
        for y0, y1, slot in bands:
            face([(x0 + s0, y0, z0), (x0 + s1, y0, z1), (x0 + s1, y1, z1), (x0 + s0, y1, z0)], slot,
                 [(s0 / UV_M, y0 / UV_M), (s1 / UV_M, y0 / UV_M), (s1 / UV_M, y1 / UV_M), (s0 / UV_M, y1 / UV_M)])
        for side in (1.0, -1.0):
            ya, yb = side * inner, side * half              # kerb: inner face, top, outer wall down to the ground
            top0, top1 = z0 + KERB_H, z1 + KERB_H
            quads = [([(x0 + s0, ya, z0), (x0 + s1, ya, z1), (x0 + s1, ya, top1), (x0 + s0, ya, top0)], KERB_H),
                     ([(x0 + s0, ya, top0), (x0 + s1, ya, top1), (x0 + s1, yb, top1), (x0 + s0, yb, top0)], KERB_W),
                     ([(x0 + s0, yb, top0), (x0 + s1, yb, top1), (x0 + s1, yb, FOOT_M), (x0 + s0, yb, FOOT_M)], None)]
            for coords, depth in quads:
                if side < 0:
                    coords = coords[::-1]
                if depth is None:
                    uvs = [(c[0] / UV_M, c[2] / UV_M) for c in coords]
                else:
                    uvs = [(c[0] / UV_M, (c[1] if depth == KERB_W else c[2]) / UV_M) for c in coords]
                face(coords, "Concrete", uvs)
    # the kerbs' ends, at the two feet
    for end, (s, z) in ((0, profile[0]), (1, profile[-1])):
        for side in (1.0, -1.0):
            ya, yb = side * inner, side * half
            coords = [(x0 + s, ya, z), (x0 + s, ya, z + KERB_H), (x0 + s, yb, z + KERB_H), (x0 + s, yb, FOOT_M), (x0 + s, ya, FOOT_M)]
            if (side > 0) == (end == 1):
                coords = coords[::-1]
            face(coords, "Concrete", [(c[1] / UV_M, c[2] / UV_M) for c in coords])
    obj = new_object("SM_Bay_TrainingRamp", bm, slots)
    print("TRAINING ramp: %.1f x %.1f m, %.2f m high, steepest %.0f %% -> %s" % (
        total, RAMP_W, RAMP_H, 100.0 * RAMP_H / (RAMP_RUN_M - CURVE_M), export(obj, "SM_Bay_TrainingRamp")))
    bpy.data.objects.remove(obj)


def box(bm, uv, slots, lo, hi, slot, skip=()):
    """A box between two corners; each face wound to look outwards."""
    (ax, ay, az), (bx, by, bz) = lo, hi
    quads = {"-x": [(ax, by, az), (ax, ay, az), (ax, ay, bz), (ax, by, bz)], "+x": [(bx, ay, az), (bx, by, az), (bx, by, bz), (bx, ay, bz)],
             "-y": [(ax, ay, az), (bx, ay, az), (bx, ay, bz), (ax, ay, bz)], "+y": [(bx, by, az), (ax, by, az), (ax, by, bz), (bx, by, bz)],
             "-z": [(ax, by, az), (bx, by, az), (bx, ay, az), (ax, ay, az)], "+z": [(ax, ay, bz), (bx, ay, bz), (bx, by, bz), (ax, by, bz)]}
    for key, coords in quads.items():
        if key in skip:
            continue
        f = bm.faces.new([bm.verts.new(p) for p in coords])
        f.material_index = slots.index(slot)
        for loop in f.loops:
            loop[uv].uv = (0.5, 0.5)


def target():
    slots = ["Steel", "PaintWhite", "PaintYellow"]
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    box(bm, uv, slots, (-0.20, -0.20, 0.0), (0.20, 0.20, 0.02), "Steel")                    # base plate
    box(bm, uv, slots, (-0.025, -0.025, 0.02), (0.025, 0.025, 1.00), "Steel")               # post
    box(bm, uv, slots, (0.025, -0.25, 1.00), (0.035, 0.25, 1.50), "Steel", skip=("+x",))    # the plate: back and edges
    # its face (+X): white, with a yellow square in the middle
    x = 0.035
    rings = [(-0.25, 0.25, 1.00, 1.50), (-0.09, 0.09, 1.16, 1.34)]
    (oy0, oy1, oz0, oz1), (iy0, iy1, iz0, iz1) = rings
    white = [[(x, oy0, oz0), (x, oy1, oz0), (x, iy1, iz0), (x, iy0, iz0)], [(x, oy1, oz0), (x, oy1, oz1), (x, iy1, iz1), (x, iy1, iz0)],
             [(x, oy1, oz1), (x, oy0, oz1), (x, iy0, iz1), (x, iy1, iz1)], [(x, oy0, oz1), (x, oy0, oz0), (x, iy0, iz0), (x, iy0, iz1)]]
    for coords in white:
        f = bm.faces.new([bm.verts.new(p) for p in coords])
        f.material_index = slots.index("PaintWhite")
        for loop in f.loops:
            loop[uv].uv = (0.5, 0.5)
    f = bm.faces.new([bm.verts.new(p) for p in [(x, iy0, iz0), (x, iy1, iz0), (x, iy1, iz1), (x, iy0, iz1)]])
    f.material_index = slots.index("PaintYellow")
    for loop in f.loops:
        loop[uv].uv = (0.5, 0.5)
    obj = new_object("SM_Bay_TrainingTarget", bm, slots)
    print("TRAINING target -> %s" % export(obj, "SM_Bay_TrainingTarget"))
    bpy.data.objects.remove(obj)


if __name__ == "__main__":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ramp()
    target()
