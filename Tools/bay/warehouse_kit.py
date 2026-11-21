"""Builds the industrial district's buildings: a kit of warehouses, sheds and old factory halls.

  blender -b --factory-startup --python Tools/bay/warehouse_kit.py

Every model is original and procedural (no third-party geometry). Each stands on its own footprint with its
street front on Blender -Y: roll-up loading doors in recessed frames, a personnel door, an office window band,
a dock canopy on the larger ones, downspouts and corner trims. Sides and back are plainer (a party wall to the
neighbour, a few vents), so unit_faces.py finds the front by its polygon count, as it does for the city's other
buildings. The walls start on a 0.8 m concrete plinth that runs 0.6 m into the ground, so no building shows
daylight under its walls on a sloping lot.

Material slots (named; build_bay.py / extra_units.py give each its Unreal material):
  Wall     corrugated sheet metal        Brick   brick of the old factory halls
  Roof     painted roof sheet            Door    roll-up door (one door spans its UV square)
  Concrete plinth, docks, parapet caps   Glass   windows
  Trim     painted steel: frames, canopies, downspouts, gutters
UVs are metric: 1 UV = 2 m on walls and roofs (the Megascans surfaces' scan size), one door per UV square.

Inputs:  none
Outputs: Saved/Bay/industrial/Warehouses.glb   one mesh per model, named SM_BayWarehouse_<name>
         Saved/Bay/industrial/warehouses.json  per model: footprint (w along the street, d deep), eave and top
                                                height, triangle count
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

PROJECT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(PROJECT, "Saved", "Bay", "industrial")
UV_M = 2.0
SLOTS = ["Wall", "Brick", "Roof", "Door", "Concrete", "Glass", "Trim"]
PLINTH_M = 0.8
INTO_GROUND_M = 0.6

# name: frontage w, depth d, eave height, roof ("gable", "saw", "flat"), wall slot, doors, dock canopy, office band
MODELS = {
    "GableS":    dict(w=24.0, d=36.0, h=7.0, roof="gable", wall="Wall", doors=2, dock=False, office=True),
    "GableM":    dict(w=32.0, d=48.0, h=9.0, roof="gable", wall="Wall", doors=3, dock=True, office=True),
    "GableL":    dict(w=44.0, d=62.0, h=11.0, roof="gable", wall="Wall", doors=4, dock=True, office=False),
    "SawM":      dict(w=36.0, d=40.0, h=8.0, roof="saw", wall="Wall", doors=2, dock=False, office=True),
    "SawBrick":  dict(w=40.0, d=48.0, h=9.0, roof="saw", wall="Brick", doors=2, dock=False, office=True),
    "FlatBrick": dict(w=28.0, d=40.0, h=12.0, roof="flat", wall="Brick", doors=1, dock=False, office=True, floors=3),
    "FlatL":     dict(w=52.0, d=70.0, h=10.0, roof="flat", wall="Wall", doors=5, dock=True, office=False),
    "Shop":      dict(w=16.0, d=24.0, h=6.0, roof="flat", wall="Brick", doors=2, dock=False, office=True),
}


class Builder:
    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")

    def quad(self, pts, slot, uv=None):
        """One face from 3-4 points; UVs metric on the face's own plane unless given."""
        verts = [self.bm.verts.new(p) for p in pts]
        face = self.bm.faces.new(verts)
        face.material_index = SLOTS.index(slot)
        if uv is None:
            a, b = Vector(pts[0]), Vector(pts[1])
            u_axis = (b - a).normalized() if (b - a).length > 1e-6 else Vector((1, 0, 0))
            n = face.normal if face.normal.length > 0 else Vector((0, 0, 1))
            v_axis = n.cross(u_axis).normalized()
            uv = [((Vector(p) - a).dot(u_axis) / UV_M, (Vector(p) - a).dot(v_axis) / UV_M) for p in pts]
        for loop, t in zip(face.loops, uv):
            loop[self.uv].uv = t
        return face

    def box(self, x0, y0, z0, x1, y1, z1, slot, skip=()):
        c = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        faces = {"-y": (0, 1, 5, 4), "+x": (1, 2, 6, 5), "+y": (2, 3, 7, 6), "-x": (3, 0, 4, 7), "+z": (4, 5, 6, 7), "-z": (3, 2, 1, 0)}
        for k, idx in faces.items():
            if k not in skip:
                self.quad([c[i] for i in idx], slot)

    def wall_x(self, y, x0, x1, z0, z1, slot, outward):
        """A wall in the plane y = const from x0 to x1, facing -y (outward < 0) or +y."""
        pts = [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)]
        self.quad(pts if outward < 0 else pts[::-1], slot)

    def wall_y(self, x, y0, y1, z0, z1, slot, outward):
        pts = [(x, y1, z0), (x, y0, z0), (x, y0, z1), (x, y1, z1)]
        self.quad(pts if outward > 0 else pts[::-1], slot)


def roof_profile(m):
    """(x, z) points of the roof outline across the frontage, left to right, from eave to eave."""
    w, h = m["w"], m["h"]
    if m["roof"] == "gable":
        return [(-w / 2, h), (0.0, h + w * 0.12), (w / 2, h)]
    if m["roof"] == "flat":
        return [(-w / 2, h), (w / 2, h)]
    return None


def build(name, m):
    b = Builder()
    w, d, h = m["w"], m["d"], m["h"]
    x0, x1, y0, y1 = -w / 2, w / 2, -d / 2, d / 2
    wall = m["wall"]
    base = PLINTH_M
    # plinth all round, into the ground
    b.box(x0 - 0.08, y0 - 0.08, -INTO_GROUND_M, x1 + 0.08, y1 + 0.08, base, "Concrete", skip=("-z", "+z"))
    # side and back walls (plain), front wall cut around the doors
    b.wall_y(x0, y0, y1, base, h, wall, -1)
    b.wall_y(x1, y0, y1, base, h, wall, +1)
    b.wall_x(y1, x0, x1, base, h, wall, +1)
    doors = m["doors"]
    door_w = 4.2 if w >= 24 else 3.4
    door_h = min(5.2, h - 1.6) if m["roof"] != "flat" or m.get("floors", 1) == 1 else 4.2
    slots = [x0 + w * (k + 0.5) / doors for k in range(doors)] if doors else []
    if m.get("office") and doors:
        slots = [x0 + (w - 6.0) * (k + 0.5) / doors + 6.0 for k in range(doors)]   # the office takes the left 6 m
    # front wall as panels between the door openings
    xs = [x0]
    for cx in slots:
        xs += [cx - door_w / 2, cx + door_w / 2]
    xs.append(x1)
    for i in range(0, len(xs), 2):
        if xs[i + 1] - xs[i] > 0.01:
            b.wall_x(y0, xs[i], xs[i + 1], base, h, wall, -1)
    for cx in slots:
        b.wall_x(y0, cx - door_w / 2, cx + door_w / 2, base + door_h, h, wall, -1)          # lintel
        # the door itself 0.25 m in, with its frame: jambs, head and a sill
        b.quad([(cx - door_w / 2, y0 + 0.25, 0.0), (cx + door_w / 2, y0 + 0.25, 0.0),
                (cx + door_w / 2, y0 + 0.25, base + door_h), (cx - door_w / 2, y0 + 0.25, base + door_h)], "Door",
               uv=[(0, 0), (1, 0), (1, 1), (0, 1)])
        b.box(cx - door_w / 2 - 0.25, y0 - 0.12, 0.0, cx - door_w / 2, y0 + 0.25, base + door_h + 0.25, "Trim")
        b.box(cx + door_w / 2, y0 - 0.12, 0.0, cx + door_w / 2 + 0.25, y0 + 0.25, base + door_h + 0.25, "Trim")
        b.box(cx - door_w / 2, y0 - 0.12, base + door_h, cx + door_w / 2, y0 + 0.25, base + door_h + 0.25, "Trim")
        b.quad([(cx - door_w / 2, y0, base), (cx + door_w / 2, y0, base), (cx + door_w / 2, y0 + 0.25, base),
                (cx - door_w / 2, y0 + 0.25, base)][::-1], "Concrete")
        # bollards either side
        for bx in (cx - door_w / 2 - 0.6, cx + door_w / 2 + 0.6):
            b.box(bx - 0.12, y0 - 0.9, 0.0, bx + 0.12, y0 - 0.66, 1.1, "Trim")
    # office: a personnel door and a window band (or rows of windows on a factory hall)
    if m.get("office"):
        ox0, ox1 = x0 + 0.8, x0 + 5.2
        b.box(ox0 + 0.2, y0 - 0.1, base, ox0 + 1.3, y0 + 0.02, base + 2.3, "Door")
        b.box(ox0 + 0.05, y0 - 0.14, base + 2.3, ox0 + 1.45, y0 + 0.02, base + 2.45, "Trim")
        floors = m.get("floors", 1)
        rows = [(base + 1.1 + k * (h - base - 1.5) / floors, base + 2.4 + k * (h - base - 1.5) / floors) for k in range(floors)]
        for z0, z1 in rows:
            xa = ox0 + 1.8 if z0 < base + 2.0 else x0 + 1.0
            xb = ox1 if floors == 1 else x1 - 1.0
            n = max(1, int((xb - xa) / 2.2))
            for k in range(n):
                wx0 = xa + (xb - xa) * k / n + 0.15
                wx1 = xa + (xb - xa) * (k + 1) / n - 0.15
                if floors > 1 and any(abs((wx0 + wx1) / 2 - cx) < door_w / 2 + 0.8 for cx in slots) and z0 < base + door_h:
                    continue
                b.quad([(wx0, y0 - 0.02, z0), (wx1, y0 - 0.02, z0), (wx1, y0 - 0.02, z1), (wx0, y0 - 0.02, z1)], "Glass",
                       uv=[(0, 0), (1, 0), (1, 1), (0, 1)])
                b.box(wx0 - 0.08, y0 - 0.12, z0 - 0.12, wx1 + 0.08, y0 - 0.02, z0, "Trim")
                b.box(wx0 - 0.08, y0 - 0.1, z1, wx1 + 0.08, y0 - 0.02, z1 + 0.08, "Trim")
    # dock canopy over the doors
    if m.get("dock") and slots:
        cz = base + door_h + 0.6
        b.box(slots[0] - door_w, y0 - 3.2, cz, slots[-1] + door_w, y0, cz + 0.25, "Trim")
        for cx in (slots[0] - door_w + 0.3, slots[-1] + door_w - 0.3):
            b.box(cx - 0.1, y0 - 3.3, cz - 0.9, cx + 0.1, y0 - 3.1, cz, "Trim")
        b.box(slots[0] - door_w, y0 - 2.4, 0.0, slots[-1] + door_w, y0 - 0.02, base, "Concrete")   # the dock apron
    # corner trims and downspouts
    for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        b.box(cx - 0.12, cy - 0.12, base, cx + 0.12, cy + 0.12, h + 0.2, "Trim")
    for sx in (x0 + 0.6, x1 - 0.6):
        b.box(sx - 0.07, y0 - 0.2, base, sx + 0.07, y0 - 0.06, h, "Trim")
    # gutter along the front
    b.box(x0 - 0.1, y0 - 0.35, h - 0.15, x1 + 0.1, y0, h + 0.05, "Trim")
    # roof
    if m["roof"] == "saw":
        teeth = max(3, int(round(d / 10.0)))
        tooth = d / teeth
        rise = 3.2
        for k in range(teeth):
            ya, yb = y0 + k * tooth, y0 + (k + 1) * tooth
            # sloped sheet rising towards the back of the tooth, glazed upright face at its back
            b.quad([(x0, ya, h), (x1, ya, h), (x1, yb, h + rise), (x0, yb, h + rise)], "Roof")
            b.quad([(x1, yb, h), (x0, yb, h), (x0, yb, h + rise), (x1, yb, h + rise)], "Glass",
                   uv=[(0, 0), (w / 3.0, 0), (w / 3.0, 1), (0, 1)])
            for xx, sgn in ((x0, -1), (x1, 1)):
                tri = [(xx, ya, h), (xx, yb, h), (xx, yb, h + rise)]
                b.quad(tri if sgn > 0 else tri[::-1], wall)
        top = h + rise
    else:
        prof = roof_profile(m)
        for (ax, az), (bx_, bz) in zip(prof, prof[1:]):
            b.quad([(ax, y0 - 0.3, az), (bx_, y0 - 0.3, bz), (bx_, y1 + 0.3, bz), (ax, y1 + 0.3, az)][::-1], "Roof")
        if m["roof"] == "gable":
            for yy, sgn in ((y0, -1), (y1, 1)):
                tri = [(x0, yy, h), (x1, yy, h), (0.0, yy, h + w * 0.12)]
                b.quad(tri if sgn < 0 else tri[::-1], wall)
            # ridge vents
            for k in range(int(d / 12)):
                vy = y0 + (k + 0.5) * d / int(d / 12)
                b.box(-0.8, vy - 0.8, h + w * 0.12 - 0.1, 0.8, vy + 0.8, h + w * 0.12 + 0.7, "Trim", skip=("-z",))
            top = h + w * 0.12 + 0.7
        else:
            # parapet with a concrete cap, and roof units
            for (ax, ay, bx_, by_) in ((x0, y0, x1, y0 + 0.3), (x0, y1 - 0.3, x1, y1), (x0, y0, x0 + 0.3, y1), (x1 - 0.3, y0, x1, y1)):
                b.box(ax, ay, h, bx_, by_, h + 1.0, wall if m["wall"] == "Brick" else "Concrete", skip=("-z",))
                b.box(ax - 0.05, ay - 0.05, h + 1.0, bx_ + 0.05, by_ + 0.05, h + 1.15, "Concrete", skip=("-z",))
            for k in range(max(1, int(w * d / 900))):
                ux = x0 + w * (0.25 + 0.5 * ((k * 0.618) % 1.0))
                uy = y0 + d * (0.25 + 0.5 * ((k * 0.382) % 1.0))
                b.box(ux - 1.5, uy - 1.0, h, ux + 1.5, uy + 1.0, h + 1.4, "Trim", skip=("-z",))
            top = h + 1.4
    bm = b.bm
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
    mesh = bpy.data.meshes.new("SM_BayWarehouse_" + name)
    bm.to_mesh(mesh)
    bm.free()
    for s in SLOTS:
        mat = bpy.data.materials.get(s)
        if mat is None:
            mat = bpy.data.materials.new(s)
            mat.use_nodes = True        # exported as a named glTF material: Unreal makes a slot of that name
        mesh.materials.append(mat)
    obj = bpy.data.objects.new("SM_BayWarehouse_" + name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    tris = sum(len(p.vertices) - 2 for p in mesh.polygons)
    return {"w": w, "d": d, "eave": h, "top": round(top, 2), "tris": tris}


def main():
    os.makedirs(OUT, exist_ok=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    info = {}
    for name, m in MODELS.items():
        info["SM_BayWarehouse_" + name] = build(name, m)
    path = os.path.join(OUT, "Warehouses.glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_apply=True, export_materials="EXPORT")
    with open(os.path.join(OUT, "warehouses.json"), "w") as f:
        json.dump(info, f, indent=1)
    print("WAREHOUSES %d models -> %s: %s" % (len(info), path, {k: v["tris"] for k, v in info.items()}))


if __name__ == "__main__":
    main()
