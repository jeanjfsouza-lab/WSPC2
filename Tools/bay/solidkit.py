"""Closed bodies for the structure meshers (Blender): a tunnel's slabs and walls, a bridge's deck. Not run on its own.

  import solidkit                       (inside Blender: tunnel_mesh.py)

Solid         vertices, faces and each face's material slot; sweep() skins a list of cross-sections
build_object  turns a Solid into a Blender object: doubles welded, every face turned outwards, UVs laid by the
              face's direction (floors by x and y, walls by their run and height), in repeats of uv_m metres
join_export   joins objects into one mesh and writes it as a .glb
export_objects  writes objects into one .glb as separate meshes (what a tunnel needs: see there)

Every part must be a closed body: that is what lets Blender tell inside from outside, so a wall that is seen
from within a tunnel faces the right way without anyone keeping track of winding.
(span_mesh.py has its own, older copy of Solid and build_object; the bridges in the map were built with it.)
"""
import math

import bmesh
import bpy


class Solid:
    """A closed body: vertices, faces (index tuples) and each face's material slot."""

    def __init__(self):
        self.v, self.f, self.slot = [], [], []

    def sweep(self, sections, slot_of, cap_slot="Concrete"):
        """Skin over a list of cross-sections (each a closed loop of 3D points, same count), capped at both ends.
        slot_of(k, j): slot of the strip between loop points k, k+1 and sections j, j+1."""
        base, m = len(self.v), len(sections[0])
        for sec in sections:
            self.v.extend(sec)
        for j in range(len(sections) - 1):
            for k in range(m):
                a, b = base + j * m + k, base + j * m + (k + 1) % m
                c, d = base + (j + 1) * m + (k + 1) % m, base + (j + 1) * m + k
                self.f.append((a, b, c, d))
                self.slot.append(slot_of(k, j))
        self.f.append(tuple(base + k for k in range(m)))
        self.slot.append(cap_slot)
        self.f.append(tuple(base + (len(sections) - 1) * m + k for k in reversed(range(m))))
        self.slot.append(cap_slot)

    def box(self, corners_low, corners_high, slot="Concrete"):
        """A body between two loops of the same point count (e.g. the four corners of a block, below and above)."""
        self.sweep([corners_low, corners_high], lambda k, j: slot, slot)


def build_object(name, solid, slots, uv_m=4.0, uv_origin=(0.0, 0.0)):
    bm = bmesh.new()
    verts = [bm.verts.new(p) for p in solid.v]
    bm.verts.ensure_lookup_table()
    for face, slot in zip(solid.f, solid.slot):
        try:
            f = bm.faces.new([verts[i] for i in face])
        except ValueError:
            continue                                    # a face that repeats a vertex or another face
        f.material_index = slots.index(slot)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        n = f.normal
        flat = abs(n.z) > 0.6
        tx, ty = (-n.y, n.x)
        size = math.hypot(tx, ty) or 1.0
        tx, ty = tx / size, ty / size
        for loop in f.loops:
            co = loop.vert.co
            x, y = co.x - uv_origin[0], co.y - uv_origin[1]
            loop[uv].uv = (x / uv_m, y / uv_m) if flat else ((x * tx + y * ty) / uv_m, co.z / uv_m)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for slot in slots:
        mesh.materials.append(bpy.data.materials.get(slot) or bpy.data.materials.new(slot))
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def export_objects(objects, path, sharp_deg=32.0):
    """Writes the objects into one .glb, each as a mesh of its own (Unreal then makes one static mesh per object),
    shaded smooth with sharp edges above the angle. Returns the number of faces written.
    Why separate meshes: Lumen keeps a distance field and a few flat "cards" per mesh. One mesh half a kilometre
    long gets a distance field too coarse to hold a wall, and no card that sees its inside: a tunnel made that way
    is black where it should be lit and lit where it should be dark. Short slabs and walls are held well."""
    faces = 0
    for obj in objects:
        mesh = obj.data
        mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
        if hasattr(mesh, "set_sharp_from_angle"):
            mesh.set_sharp_from_angle(angle=math.radians(sharp_deg))
        else:
            mesh.polygons.foreach_set("use_smooth", [False] * len(mesh.polygons))
        mesh.validate()
        faces += len(mesh.polygons)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_materials="EXPORT")
    return faces


def join_export(objects, name, path, sharp_deg=32.0):
    """Joins the objects into one named `name`, shades it smooth with sharp edges above the angle, writes the .glb.
    Returns the mesh."""
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    if len(objects) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = obj.data.name = name
    mesh = obj.data
    mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
    if hasattr(mesh, "set_sharp_from_angle"):
        mesh.set_sharp_from_angle(angle=math.radians(sharp_deg))
    else:
        mesh.polygons.foreach_set("use_smooth", [False] * len(mesh.polygons))
    mesh.validate()
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_materials="EXPORT")
    return mesh
