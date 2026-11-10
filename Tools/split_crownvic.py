"""Blender: split the sedan model into one body mesh and one wheel mesh.

blender -b --python split_crownvic.py -- <source.glb> <output dir>

- bakes every object's world transform into its vertices (the wheel parts are
  children of scaled, rotated tyre objects, so nothing can be moved or deleted before this)
- drops brand badges (objects and faces)
- keeps the front-left wheel (tyre, rim, disc, hub), centred on the origin, as Wheel;
  its 179k-triangle untextured tyre is decimated and given a rubber material
- joins everything else into Body
- writes layout.json with the wheel centres and body bounds (Blender axes, metres)
"""
import json
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

src, out_dir = sys.argv[sys.argv.index("--") + 1:]
os.makedirs(out_dir, exist_ok=True)

BADGE_MATERIALS = {"crownvic_ford_badges", "logo", "crownvic_honeycombgrille_badge"}
WHEEL_PARTS = {"Tire", "crownvic_lxsportD", "brake_disc_plainD", "brake_hub_5lD"}
TYRE_TARGET_TRIANGLES = 6000

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
bpy.context.view_layer.update()

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
print("imported mesh objects:", len(meshes))


def base_name(name):
    # 'brake_disc_plainD.002' -> 'brake_disc_plainD'
    head, _, tail = name.rpartition(".")
    return head if head and tail.isdigit() else name


def vertex_bounds(objs):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        for v in o.data.vertices:
            lo = Vector(map(min, lo, v.co))
            hi = Vector(map(max, hi, v.co))
    return lo, hi


def triangles(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def remove(objs):
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)


# 1. bake world transforms into the vertices, then flatten the hierarchy
worlds = {o: o.matrix_world.copy() for o in meshes}
for o in meshes:
    o.data = o.data.copy()  # instances share mesh data
    o.data.transform(worlds[o])
    if worlds[o].determinant() < 0:
        o.data.flip_normals()
    o.data.update()
for o in meshes:
    o.parent = None
for o in meshes:
    o.matrix_world = Matrix.Identity(4)
bpy.context.view_layer.update()

# 2. drop badge objects, and faces that still use a badge material
remove([o for o in meshes if "badge" in o.name.lower()])
meshes = [o for o in bpy.data.objects if o.type == "MESH"]

removed_faces = 0
for o in meshes:
    slots = [i for i, s in enumerate(o.material_slots) if s.material and base_name(s.material.name) in BADGE_MATERIALS]
    if not slots:
        continue
    bm = bmesh.new()
    bm.from_mesh(o.data)
    doomed = [f for f in bm.faces if f.material_index in slots]
    removed_faces += len(doomed)
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    bm.to_mesh(o.data)
    bm.free()
print("badge faces removed:", removed_faces)

# 3. locate the four wheels from their tyres
tyres = [o for o in meshes if base_name(o.name) == "Tire"]
centres = []
for t in tyres:
    lo, hi = vertex_bounds([t])
    centres.append((lo + hi) / 2)
    print("tyre", t.name, "centre", tuple(round(v, 4) for v in centres[-1]), "size", tuple(round(v, 4) for v in (hi - lo)))

# front left: car's left is +X, front is -Y
front_left = max(range(len(tyres)), key=lambda i: centres[i].x - centres[i].y)
keep_centre = centres[front_left]
tyre_lo, tyre_hi = vertex_bounds([tyres[front_left]])

wheel_objs = [o for o in meshes if base_name(o.name) in WHEEL_PARTS]
keep = []
for o in wheel_objs:
    lo, hi = vertex_bounds([o])
    if ((lo + hi) / 2 - keep_centre).length < 0.4:
        keep.append(o)
print("kept wheel parts:", sorted(o.name for o in keep))
remove([o for o in wheel_objs if o not in keep])

# 4. the tyre: far too dense and untextured
tyre = next(o for o in keep if base_name(o.name) == "Tire")
bpy.ops.object.select_all(action="DESELECT")
tyre.select_set(True)
bpy.context.view_layer.objects.active = tyre
mod = tyre.modifiers.new("Decimate", "DECIMATE")
mod.ratio = min(1.0, TYRE_TARGET_TRIANGLES / max(1, triangles(tyre)))
bpy.ops.object.modifier_apply(modifier=mod.name)

rubber = bpy.data.materials.new("WSPC2_TyreRubber")
rubber.use_nodes = True
bsdf = rubber.node_tree.nodes.get("Principled BSDF")
bsdf.inputs["Base Color"].default_value = (0.02, 0.02, 0.02, 1.0)
bsdf.inputs["Roughness"].default_value = 0.9
tyre.data.materials.clear()
tyre.data.materials.append(rubber)
print("tyre triangles after decimate:", triangles(tyre))

# 5. centre the wheel on its axle
for o in keep:
    o.data.transform(Matrix.Translation(-keep_centre))
    o.data.update()

body_objs = [o for o in bpy.data.objects if o.type == "MESH" and o not in keep]
body_lo, body_hi = vertex_bounds(body_objs)


def join(objs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = name
    joined.data.name = name
    return joined


body = join(body_objs, "CrownVic_Body")
wheel = join(keep, "CrownVic_Wheel")

for label, obj in (("body", body), ("wheel", wheel)):
    lo, hi = vertex_bounds([obj])
    print("JOINED", label, "min", tuple(round(v, 3) for v in lo), "max", tuple(round(v, 3) for v in hi), "tris", triangles(obj))


def export(obj, filename):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=os.path.join(out_dir, filename),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
    )


export(body, "CrownVic_Body.glb")
export(wheel, "CrownVic_Wheel.glb")

layout = {
    "axes": "Blender: +Z up, -Y is the front of the car, +X is the car's left",
    "wheel_centres": [[round(v, 4) for v in c] for c in centres],
    "kept_wheel_centre": [round(v, 4) for v in keep_centre],
    "tyre_size": [round(v, 4) for v in (tyre_hi - tyre_lo)],
    "body_min": [round(v, 4) for v in body_lo],
    "body_max": [round(v, 4) for v in body_hi],
    "body_triangles": triangles(body),
    "wheel_triangles": triangles(wheel),
}
with open(os.path.join(out_dir, "layout.json"), "w") as f:
    json.dump(layout, f, indent=2)
print("LAYOUT", json.dumps(layout))
