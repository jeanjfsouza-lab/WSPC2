"""Builds one bridge of the Bay city as a mesh (Blender): deck with its paint, kerbs and sidewalks, parapets
and railings, a steel box girder that deepens over the main piers, the piers on their caissons, and the
parapet around each abutment platform.

  blender -b --factory-startup --python Tools/bay/span_mesh.py -- <structure>

Input:  Saved/Bay/network.json (the bridge's centre line and height profile), Tools/bay/structures.py
Output: Saved/Bay/structures/<name>/<name>.glb    mesh in metres, x east, y north, z up
        Saved/Bay/structures/<name>/props.json    street lamps along the deck, as a sector's props.json (Unreal cm)
        Saved/Bay/structures/<name>/span.json     stations of faces and piers, spans, heights (for cameras and notes)
Material slots: Road, PaintWhite, PaintYellow, Curb, Sidewalk, Concrete, Steel (girder), Rail (railings).

How. The deck is the bridge's own road section (common.SECTIONS["bridge"]) swept along the centre line between
the two abutment faces, so its carriageway, kerbs, sidewalks and paint carry on exactly from the road the
sector builds on the abutment. Every part is a closed solid, which lets Blender turn all faces outwards.
Where an end has no sector yet ("solid" approach) the deck runs on to the junction over a walled fill.
"""
import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import roadgeom
import structures
from common import CURB_M, DATA, load_json

SLOTS = ["Road", "PaintWhite", "PaintYellow", "Curb", "Sidewalk", "Concrete", "Steel", "Rail"]
UV_M = 4.0
STEP_M = 3.0                # deck cross-sections; the lane dashes (3 m on, 9 m off) fall on this grid
SLAB_M = 0.45               # deck slab thickness at the girder
EDGE_M = 0.35               # ... and at its outer edge
PARAPET_W, PARAPET_H = 0.35, 0.45
RAIL_TOP_M = 0.52           # top rail above the parapet
GIRDER_TOP_HALF, GIRDER_BOTTOM_HALF = 8.25, 5.5
DEPTH_SIDE, DEPTH_PIER, DEPTH_MID = 2.6, 5.6, 3.0      # girder depth: side spans, over a main pier, middle of the main span
CAISSON_TOP_M, CAISSON_FOOT_M = 1.2, -14.0
FILL_FOOT_M = -3.0
SOLID_CLEAR_M = 12.0        # a "solid" approach stops this far short of the junction it leads to
LAMP_EVERY_M = 36.0
# a suspension bridge (structures spec "suspension"): towers, main cables, hangers
TOWER_SAG_RATIO = 0.10      # cable sag over the main span, as a share of the span
CABLE_LOW_M = 3.0           # the cable's lowest point above the deck, at mid main span
TOWER_OUT_M = 0.6           # gap between the deck's outer edge and a tower leg
TOWER_LEG_ALONG, TOWER_LEG_ACROSS = 3.0, 2.0      # a leg's half sizes at its foot (it tapers upwards)
CABLE_R = 0.45              # main cable, half size
HANGER_EVERY_M = 12.0
ANCHOR_TOP_M = 3.0          # the cables' anchorage above the deck at the abutment face
ANCHOR_LEN_M = 12.0
LAMP = "/Game/Prop/Kit_StreetLamp_C/Mesh/streetLampC"


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

    def prism(self, bottom, top, slot):
        """A body between two loops of the same point count (bottom and top), e.g. a tapered pier."""
        self.sweep([bottom, top], lambda k, j: slot, slot)


UV_ORIGIN = [0.0, 0.0]      # set in main(): a whole number of UV repeats near the bridge, so the UVs stay small


def build_object(name, solid):
    """A Blender object from a solid: doubles welded, faces turned outwards, UVs by the face's direction."""
    bm = bmesh.new()
    verts = [bm.verts.new(p) for p in solid.v]
    bm.verts.ensure_lookup_table()
    for face, slot in zip(solid.f, solid.slot):
        try:
            f = bm.faces.new([verts[i] for i in face])
        except ValueError:
            continue                                    # a face that repeats a vertex or another face
        f.material_index = SLOTS.index(slot)
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
            x, y = co.x - UV_ORIGIN[0], co.y - UV_ORIGIN[1]
            loop[uv].uv = (x / UV_M, y / UV_M) if flat else ((x * tx + y * ty) / UV_M, co.z / UV_M)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for slot in SLOTS:
        mesh.materials.append(bpy.data.materials.get(slot) or bpy.data.materials.new(slot))
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    name = args[0]
    spec = structures.STRUCTURES[name]
    net = load_json("network.json")
    road, s_a, s_b, approaches, wings = structures.layout(net, name)
    half, walk = road.half, road.sidewalk
    UV_ORIGIN[0] = math.floor(float(road.xy[:, 0].min()) / UV_M) * UV_M
    UV_ORIGIN[1] = math.floor(float(road.xy[:, 1].min()) / UV_M) * UV_M
    out_dir = os.path.join(DATA, "structures", name)
    os.makedirs(out_dir, exist_ok=True)

    def z_at(s):
        return float(np.interp(s, road.s, road.z))

    def at(s, d, dz):
        """World point at distance s along the bridge, d metres left of its axis, dz above the road surface."""
        p, _, n = road.at(s)
        return (float(p[0] + n[0] * d), float(p[1] + n[1] * d), z_at(s) + dz)

    def at_abs(s, d, z):
        p, _, n = road.at(s)
        return (float(p[0] + n[0] * d), float(p[1] + n[1] * d), z)

    # ---- where the deck runs, and its spans
    s_first = SOLID_CLEAR_M if approaches[0] == "solid" else s_a
    s_last = road.length - SOLID_CLEAR_M if approaches[1] == "solid" else s_b
    length = s_b - s_a
    main = list(spec["main"])
    rest = (length - sum(main)) / 2.0
    n_side = max(1, int(round(rest / spec["side"])))
    spans = [rest / n_side] * n_side + main + [rest / n_side] * n_side
    joints = [s_a + float(x) for x in np.concatenate([[0.0], np.cumsum(spans)])]      # abutment, piers..., abutment
    piers = joints[1:-1]
    first_main, last_main = n_side, n_side + len(main) - 1                             # span indices of the main spans

    suspension = bool(spec.get("suspension"))

    def depth(s):
        """Girder depth: constant on the side spans, growing to the main piers, shallower at mid main span (a
        suspension bridge's deck hangs from its cables: the same depth all along)."""
        if suspension:
            return DEPTH_SIDE
        k = int(np.clip(np.searchsorted(joints, s, side="right") - 1, 0, len(spans) - 1))
        x = (s - joints[k]) / spans[k]
        if k < first_main or k > last_main:
            return DEPTH_SIDE
        if len(main) >= 3 and k == first_main:
            return DEPTH_SIDE + (DEPTH_PIER - DEPTH_SIDE) * x * x
        if len(main) >= 3 and k == last_main:
            return DEPTH_SIDE + (DEPTH_PIER - DEPTH_SIDE) * (1 - x) * (1 - x)
        return DEPTH_MID + (DEPTH_PIER - DEPTH_MID) * (2 * x - 1) ** 2

    def stations(s0, s1, extra=()):
        grid = [2.0 + STEP_M * k for k in range(int(road.length / STEP_M) + 2)]
        pts = sorted(set([s0, s1] + [g for g in grid if s0 + 0.4 < g < s1 - 0.4] + [e for e in extra if s0 + 0.4 < e < s1 - 0.4]))
        return pts

    solids = {}

    # ---- deck: slab, kerbs, sidewalks and parapets as one body; the carriageway's strips carry the paint
    out = half + walk + PARAPET_W                   # half-width of the whole deck
    dash_in, dash_out = 3.4 - 0.055, 3.4 + 0.055
    profile = [(out, -EDGE_M, "Concrete"), (out, CURB_M + PARAPET_H, "Concrete"), (half + walk, CURB_M + PARAPET_H, "Concrete"),
               (half + walk, CURB_M, "Sidewalk"), (half + roadgeom.CURB_W, CURB_M, "Curb"), (half, CURB_M, "Curb"),
               (half, 0.0, "Road"), (dash_out, 0.0, "dash"), (dash_in, 0.0, "Road"),
               (0.185, 0.0, "PaintYellow"), (0.075, 0.0, "Road"), (-0.075, 0.0, "PaintYellow"), (-0.185, 0.0, "Road"),
               (-dash_in, 0.0, "dash"), (-dash_out, 0.0, "Road"),
               (-half, 0.0, "Curb"), (-half, CURB_M, "Curb"), (-half - roadgeom.CURB_W, CURB_M, "Sidewalk"),
               (-half - walk, CURB_M, "Concrete"), (-half - walk, CURB_M + PARAPET_H, "Concrete"), (-out, CURB_M + PARAPET_H, "Concrete"),
               (-out, -EDGE_M, "Concrete"), (-GIRDER_TOP_HALF, -SLAB_M, "Concrete"), (GIRDER_TOP_HALF, -SLAB_M, "Concrete")]
    deck_s = stations(s_first, s_last, [s_a, s_b] + piers)

    def deck_slot(k, j):
        slot = profile[k][2]
        if slot != "dash":
            return slot
        mid = (deck_s[j] + deck_s[j + 1]) / 2.0     # lane dashes: 3 m of paint every 12 m, counted from the road's start
        return "PaintWhite" if (mid - 5.0) % 12.0 < 3.0 else "Road"

    deck = Solid()
    deck.sweep([[at(s, d, dz) for d, dz, _ in profile] for s in deck_s], deck_slot)
    solids["Deck"] = deck

    # ---- box girder between the abutment faces
    girder = Solid()
    girder_s = stations(s_a, s_b, piers)
    girder.sweep([[at(s, GIRDER_TOP_HALF, -SLAB_M), at(s, -GIRDER_TOP_HALF, -SLAB_M),
                   at(s, -GIRDER_BOTTOM_HALF, -SLAB_M - depth(s)), at(s, GIRDER_BOTTOM_HALF, -SLAB_M - depth(s))] for s in girder_s],
                 lambda k, j: "Steel", "Steel")
    solids["Girder"] = girder

    # ---- piers: a shaft that flares to the girder's width, on a caisson that goes down to the sea bed
    pier_body = Solid()
    centre = first_main + len(main) // 2             # the middle main span; pier i stands between spans i and i + 1
    towers = [s for i, s in enumerate(piers) if i in (centre - 1, centre)] if suspension else []
    for i, s in enumerate(piers):
        is_main = i in (centre - 1, centre)
        thick = 1.8 if is_main else 1.2             # half thickness along the bridge
        top_z = z_at(s) - SLAB_M - depth(s)
        if s not in towers:                         # a tower's legs carry the deck there (below)
            shaft_bottom = [at_abs(s - thick, 4.0, CAISSON_TOP_M), at_abs(s - thick, -4.0, CAISSON_TOP_M),
                            at_abs(s + thick, -4.0, CAISSON_TOP_M), at_abs(s + thick, 4.0, CAISSON_TOP_M)]
            shaft_top = [at_abs(s - thick, GIRDER_BOTTOM_HALF, top_z), at_abs(s - thick, -GIRDER_BOTTOM_HALF, top_z),
                         at_abs(s + thick, -GIRDER_BOTTOM_HALF, top_z), at_abs(s + thick, GIRDER_BOTTOM_HALF, top_z)]
            pier_body.prism(shaft_bottom, shaft_top, "Concrete")
        cw, ct = (8.0, 5.0) if is_main else (6.5, 3.4)
        if s in towers:
            cw = out + TOWER_OUT_M + TOWER_LEG_ACROSS + 2.0  # one caisson under both legs
        pier_body.prism([at_abs(s - ct, cw, CAISSON_FOOT_M), at_abs(s - ct, -cw, CAISSON_FOOT_M), at_abs(s + ct, -cw, CAISSON_FOOT_M), at_abs(s + ct, cw, CAISSON_FOOT_M)],
                        [at_abs(s - ct, cw, CAISSON_TOP_M), at_abs(s - ct, -cw, CAISSON_TOP_M), at_abs(s + ct, -cw, CAISSON_TOP_M), at_abs(s + ct, cw, CAISSON_TOP_M)],
                        "Concrete")
    solids["Piers"] = pier_body

    # ---- suspension (spec "suspension"): a tower on each main pier, two legs outside the deck joined by a beam under
    # the girder, one at mid height and a portal at the top; a main cable on each side, sagging over the main span
    # from tower top to tower top and running down over each side span to an anchorage block at the abutment face;
    # vertical hangers every HANGER_EVERY_M from the cables to outriggers under the deck's edges (2026-11-16, for the
    # Ponte Pensil Oeste). Grey steel and concrete, no particular bridge's colours.
    if suspension:
        sus = Solid()

        def box(p, q, r, s_ref, slot="Steel"):
            """A bar of square section (half size r) from p to q (3D points). A vertical one is turned square to the
            bridge at station s_ref; a sloping one has its sides vertical."""
            px, py, pz = p
            qx, qy, qz = q
            dx, dy = qx - px, qy - py
            run = math.hypot(dx, dy)
            if run < 1e-6:
                _, t, n = road.at(s_ref)
                tx, ty, nx, ny = float(t[0]), float(t[1]), float(n[0]), float(n[1])
                loop = lambda x, y, z: [(x + (tx + nx) * r, y + (ty + ny) * r, z), (x + (-tx + nx) * r, y + (-ty + ny) * r, z),
                                        (x + (-tx - nx) * r, y + (-ty - ny) * r, z), (x + (tx - nx) * r, y + (ty - ny) * r, z)]
            else:
                nx, ny = -dy / run * r, dx / run * r
                loop = lambda x, y, z: [(x + nx, y + ny, z - r), (x - nx, y - ny, z - r), (x - nx, y - ny, z + r), (x + nx, y + ny, z + r)]
            sus.sweep([loop(px, py, pz), loop(qx, qy, qz)], lambda k, j: slot, slot)

        main_len = towers[1] - towers[0]
        tower_h = TOWER_SAG_RATIO * main_len + CABLE_LOW_M + 4.0         # tower top above the deck at the tower
        d_cab = out + TOWER_OUT_M + TOWER_LEG_ACROSS                      # the legs' and the cables' plane
        tops = {}
        for tower_s in towers:
            z_deck = z_at(tower_s)
            z_top = z_deck + tower_h
            tops[tower_s] = z_top
            for side in (1.0, -1.0):
                d = side * d_cab
                # a leg tapering from the caisson to the top, as a stack of short prisms
                levels = np.linspace(CAISSON_TOP_M, z_top, 9)
                for z0, z1 in zip(levels[:-1], levels[1:]):
                    f0 = (z0 - CAISSON_TOP_M) / (z_top - CAISSON_TOP_M)
                    f1 = (z1 - CAISSON_TOP_M) / (z_top - CAISSON_TOP_M)
                    a0, c0 = TOWER_LEG_ALONG * (1 - 0.35 * f0), TOWER_LEG_ACROSS * (1 - 0.3 * f0)
                    a1, c1 = TOWER_LEG_ALONG * (1 - 0.35 * f1), TOWER_LEG_ACROSS * (1 - 0.3 * f1)
                    sus.prism([at_abs(tower_s - a0, d + c0, z0), at_abs(tower_s - a0, d - c0, z0), at_abs(tower_s + a0, d - c0, z0), at_abs(tower_s + a0, d + c0, z0)],
                              [at_abs(tower_s - a1, d + c1, z1), at_abs(tower_s - a1, d - c1, z1), at_abs(tower_s + a1, d - c1, z1), at_abs(tower_s + a1, d + c1, z1)],
                              "Steel")
            # beams between the legs: under the girder, at mid height above the deck, the portal at the top
            beam_z = [(z_deck - SLAB_M - depth(tower_s) - 2.2, z_deck - SLAB_M - depth(tower_s)),
                      (z_deck + 0.55 * tower_h, z_deck + 0.55 * tower_h + 3.0), (z_top - 5.0, z_top - 1.0)]
            for z0, z1 in beam_z:
                ha = TOWER_LEG_ALONG * 0.8
                sus.prism([at_abs(tower_s - ha, d_cab, z0), at_abs(tower_s - ha, -d_cab, z0), at_abs(tower_s + ha, -d_cab, z0), at_abs(tower_s + ha, d_cab, z0)],
                          [at_abs(tower_s - ha, d_cab, z1), at_abs(tower_s - ha, -d_cab, z1), at_abs(tower_s + ha, -d_cab, z1), at_abs(tower_s + ha, d_cab, z1)],
                          "Steel")

        t1, t2 = towers
        z_low = z_at((t1 + t2) / 2.0) + CABLE_LOW_M

        def cable_z(s):
            if t1 <= s <= t2:
                u = (s - t1) / (t2 - t1)
                chord = tops[t1] + (tops[t2] - tops[t1]) * u
                sag = (tops[t1] + tops[t2]) / 2.0 - z_low
                return chord - 4.0 * sag * u * (1.0 - u)
            if s < t1:                              # down over the side span to the anchorage at the face
                u = (s - s_a) / (t1 - s_a)
                z0, z1 = z_at(s_a) + ANCHOR_TOP_M, tops[t1]
                return z0 + (z1 - z0) * u - 4.0 * 0.03 * (t1 - s_a) * u * (1.0 - u)
            u = (s - t2) / (s_b - t2)
            z0, z1 = tops[t2], z_at(s_b) + ANCHOR_TOP_M
            return z0 + (z1 - z0) * u - 4.0 * 0.03 * (s_b - t2) * u * (1.0 - u)

        cab_s = sorted(set([s_a, t1, t2, s_b] + [float(v) for v in np.arange(s_a, s_b, 6.0)]))
        for side in (1.0, -1.0):
            d = side * d_cab
            pts = [at_abs(s, d, cable_z(s)) for s in cab_s]
            for (sp, p), q in zip(zip(cab_s[:-1], pts[:-1]), pts[1:]):
                box(p, q, CABLE_R, sp)
            # hangers and their outriggers
            s = s_a + HANGER_EVERY_M
            while s < s_b - HANGER_EVERY_M / 2:
                if all(abs(s - t) > 5.0 for t in towers):
                    z_bottom = z_at(s) - EDGE_M - 0.3
                    box(at_abs(s, d, z_bottom), at_abs(s, d, cable_z(s)), 0.12, s)
                    box(at_abs(s, side * (out - 0.3), z_bottom - 0.25), at_abs(s, d + side * 0.4, z_bottom - 0.25), 0.25, s)
                s += HANGER_EVERY_M
            # anchorage blocks at the two faces, where the cables come down
            for s_face, back in ((s_a, 1.0), (s_b, -1.0)):
                z_top = z_at(s_face) + ANCHOR_TOP_M + 1.0
                s0, s1 = sorted((s_face, s_face + back * ANCHOR_LEN_M))
                sus.prism([at_abs(s0, d + side * 2.5, z_top - 12.0), at_abs(s0, d - side * 2.5, z_top - 12.0),
                           at_abs(s1, d - side * 2.5, z_top - 12.0), at_abs(s1, d + side * 2.5, z_top - 12.0)],
                          [at_abs(s0, d + side * 2.5, z_top), at_abs(s0, d - side * 2.5, z_top),
                           at_abs(s1, d - side * 2.5, z_top), at_abs(s1, d + side * 2.5, z_top)], "Concrete")
        solids["Suspension"] = sus

    # ---- "solid" approaches: a walled fill under the deck from the abutment face back towards the junction
    fill = Solid()
    for approach, (f0, f1) in zip(approaches, ((s_first, s_a), (s_b, s_last))):
        if approach != "solid" or f1 - f0 < 1.0:
            continue
        fs = stations(f0, f1)
        w = out - 0.4
        fill.sweep([[at(s, w, -EDGE_M + 0.02), at(s, -w, -EDGE_M + 0.02), at_abs(s, -w, FILL_FOOT_M), at_abs(s, w, FILL_FOOT_M)] for s in fs],
                   lambda k, j: "Concrete")
    if fill.f:
        solids["Fill"] = fill

    # ---- railings on the parapets: two rails on posts
    rail = Solid()

    def bar(p, q, size, slot="Rail"):
        """A square bar from p to q (3D points)."""
        px, py, pz = p
        qx, qy, qz = q
        dx, dy, dz = qx - px, qy - py, qz - pz
        run = math.hypot(dx, dy)
        if run < 1e-6:                                  # vertical: a post
            loop = lambda x, y, z: [(x - size, y - size, z), (x + size, y - size, z), (x + size, y + size, z), (x - size, y + size, z)]
            rail.sweep([loop(px, py, pz), loop(qx, qy, qz)], lambda k, j: slot, slot)
            return
        nx, ny = -dy / run * size, dx / run * size
        loop = lambda x, y, z: [(x + nx, y + ny, z - size), (x - nx, y - ny, z - size), (x - nx, y - ny, z + size), (x + nx, y + ny, z + size)]
        rail.sweep([loop(px, py, pz), loop(qx, qy, qz)], lambda k, j: slot, slot)

    top = CURB_M + PARAPET_H
    for side in (1.0, -1.0):
        d = side * (half + walk + PARAPET_W / 2)
        for a, b in zip(deck_s[:-1], deck_s[1:]):
            for dz in (top + RAIL_TOP_M, top + RAIL_TOP_M * 0.5):
                bar(at(a, d, dz), at(b, d, dz), 0.03)
        for s in deck_s[::1]:
            bar(at(s, d, top - 0.02), at(s, d, top + RAIL_TOP_M), 0.035)

    # ---- around each abutment platform: a parapet with the same railing, from the deck's parapet out along
    # the face and back along the platform's side, so the drop to the water is closed
    wing = Solid()
    edge = structures.PLATFORM_HALF_M - 0.25
    for approach, wanted, s_face, back in zip(approaches, wings, (s_a, s_b), (-1.0, 1.0)):
        if approach != "sector" or not wanted:
            continue
        s_in = s_face + back * 0.2                   # just inside the platform
        for side in (1.0, -1.0):
            path = [(s_in, side * (half + walk + PARAPET_W / 2)), (s_in, side * edge), (s_face + back * (structures.PLATFORM_BACK_M - 0.3), side * edge)]
            for (sa, da), (sb, db) in zip(path[:-1], path[1:]):
                steps = max(1, int(math.ceil(max(abs(sb - sa), abs(db - da)) / STEP_M)))
                for i in range(steps):
                    s0_, d0_ = sa + (sb - sa) * i / steps, da + (db - da) * i / steps
                    s1_, d1_ = sa + (sb - sa) * (i + 1) / steps, da + (db - da) * (i + 1) / steps
                    p, q = at(s0_, d0_, 0.0), at(s1_, d1_, 0.0)
                    run = math.hypot(q[0] - p[0], q[1] - p[1])
                    if run < 1e-6:
                        continue                         # beyond the road's first point (a face close to its end)
                    nx, ny = -(q[1] - p[1]) / run * PARAPET_W / 2, (q[0] - p[0]) / run * PARAPET_W / 2
                    ex, ey = (q[0] - p[0]) / run * PARAPET_W / 2, (q[1] - p[1]) / run * PARAPET_W / 2      # overlap at corners
                    loop = lambda pt, sgn: [(pt[0] + nx + sgn * ex, pt[1] + ny + sgn * ey, pt[2] - 0.25), (pt[0] - nx + sgn * ex, pt[1] - ny + sgn * ey, pt[2] - 0.25),
                                            (pt[0] - nx + sgn * ex, pt[1] - ny + sgn * ey, pt[2] + top), (pt[0] + nx + sgn * ex, pt[1] + ny + sgn * ey, pt[2] + top)]
                    wing.sweep([loop(p, -1.0), loop(q, 1.0)], lambda k, j: "Concrete")
                    for dz in (top + RAIL_TOP_M, top + RAIL_TOP_M * 0.5):
                        bar((p[0], p[1], p[2] + dz), (q[0], q[1], q[2] + dz), 0.03)
                    bar((p[0], p[1], p[2] + top - 0.02), (p[0], p[1], p[2] + top + RAIL_TOP_M), 0.035)
                bar((q[0], q[1], q[2] + top - 0.02), (q[0], q[1], q[2] + top + RAIL_TOP_M), 0.035)
    if wing.f:
        solids["Wings"] = wing
    solids["Rails"] = rail

    # ---- Blender objects, joined and exported
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects = [build_object("Bay_%s_%s" % (name, key), solid) for key, solid in solids.items()]
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = obj.data.name = "Bay_%s" % name
    mesh = obj.data
    mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
    if hasattr(mesh, "set_sharp_from_angle"):
        mesh.set_sharp_from_angle(angle=math.radians(32.0))
    else:
        mesh.polygons.foreach_set("use_smooth", [False] * len(mesh.polygons))
    mesh.validate()
    glb = os.path.join(out_dir, "%s.glb" % name)
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_apply=True, export_materials="EXPORT")

    # ---- lamps along the deck, staggered between the two sidewalks; arm over the carriageway
    lamps = []
    for side, shift in ((1.0, 0.0), (-1.0, LAMP_EVERY_M / 2)):
        s = s_first + 9.0 + shift
        while s < s_last - 6.0:
            x, y, z = at(s, side * (half + 0.75), CURB_M)
            _, _, n = road.at(s)
            yaw = math.degrees(math.atan2(side * n[1], -side * n[0])) % 360.0       # Unreal yaw of the direction towards the axis
            lamps.append([round(x * 100, 1), round(-y * 100, 1), round(z * 100, 1), round(yaw, 1), 1.0])
            s += LAMP_EVERY_M
    with open(os.path.join(out_dir, "props.json"), "w") as f:
        json.dump({"structure": name, "props": {LAMP: lamps}, "trees": {}}, f)

    crest = max(deck_s, key=z_at)
    info = {"structure": name, "title": spec["title"], "length": round(length, 1), "faces": [round(s_a, 1), round(s_b, 1)],
            "deck": [round(s_first, 1), round(s_last, 1)], "spans": [round(x, 1) for x in spans], "piers": [round(x, 1) for x in piers],
            "crest": {"s": round(crest, 1), "z": round(z_at(crest), 2), "clearance": round(z_at(crest) - SLAB_M - depth(crest), 2)},
            "z_faces": [round(z_at(s_a), 2), round(z_at(s_b), 2)],
            "line": [[round(v, 2) for v in at(s, 0.0, 0.0)] for s in np.linspace(s_first, s_last, 41)],
            "normal": [float(road.at(crest)[2][0]), float(road.at(crest)[2][1])]}
    with open(os.path.join(out_dir, "span.json"), "w") as f:
        json.dump(info, f, indent=1)
    print("SPAN %s: deck %.0f m between faces (%.0f m built), %d spans: %s; crest %.1f m, %.1f m clear under the girder; "
          "%d faces, %d lamps" % (name, length, s_last - s_first, len(spans), " ".join("%.0f" % x for x in spans),
                                  info["crest"]["z"], info["crest"]["clearance"], len(mesh.polygons), len(lamps)))
    print("SPAN %s: wrote %s" % (name, glb))


main()
