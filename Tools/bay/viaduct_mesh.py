"""Builds one viaduct of the Bay city as meshes (Blender): a road of the network's level 1 carried over the ground (an
overpass across a freeway, a flyover ramp of an interchange, an elevated stretch), on a concrete deck with barriers
and a girder, piers on footings, and a walled fill under each end where the deck comes down near the ground.

  blender -b --factory-startup --python Tools/bay/viaduct_mesh.py -- <viaduct>

Input:  Saved/Bay/network.json (the viaduct's edge, of level 1, and its height profile), Tools/bay/structures.py
        (VIADUCTS), Tools/bay/sectors.py (the levels of the sectors it crosses: the ground under it, as their meshes
        have it), Saved/Bay/terrain_base.npz (ground where no road is near)
Output: Saved/Bay/structures/<name>/<name>.glb     meshes in metres, x east, y north, z up, in pieces of about
                                                   SEGMENT_M (solidkit.export_objects)
        Saved/Bay/structures/<name>/props.json     street lamps along the deck, as a bridge's (Unreal cm)
        Saved/Bay/structures/<name>/views.txt      review cameras (tour.ps1 -Structure <name>)
        Saved/Bay/structures/<name>/viaduct.json   stations of the fills and piers, least clearance (for notes)
Material slots: Road, PaintWhite, PaintYellow, Curb, Sidewalk, Concrete.

How. The deck is the edge's own road section (common.SECTIONS of its class) swept along the centre line every
STEP_M, so its lanes, kerbs and paint carry on from the roads at its two ends, which the sectors build on the ground
(sector_roads leaves level-1 edges to the structures). Every part is a closed body (solidkit), so Blender turns all
faces outwards. Where the girder's underside comes within FILL_CLEAR_M of the ground (the ends, where the deck meets
the road it carries on), the deck stands on a fill between retaining walls; elsewhere on a pier every PIER_EVERY_M
or so: one column under a narrow deck, two under a cap beam under a wide one, each on a footing below the ground.
Lamps: one every LAMP_EVERY_M on the barriers, alternating sides.

Junctions on a structure (2026-11-20, the Trevo Sul's elevated ring and the ramps that join it): the other level-1
roads that share an end with this one are its joiners. Where a joiner's carriageway runs, this deck's barrier opens
(lies flat on the deck), so traffic passes from one deck to the other; where this deck lies on a wider joiner's
deck, its surface sits JOIN_DROP_M lower, so the two never share a plane (the wider one's lanes show through).
No lamp stands where the barrier is open.
"""
import json
import math
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import roadgeom
import sectors
import solidkit
import structures
from common import CURB_M, DATA, SECTIONS, bilinear, load_json, to_pixel

SLOTS = ["Road", "PaintWhite", "PaintYellow", "Curb", "Sidewalk", "Concrete"]
UV_M = 4.0
STEP_M = 3.0
SEGMENT_M = 42.0
SLAB_M = 0.35               # deck slab under the road surface
BARRIER_W, BARRIER_H = 0.45, 1.0
GIRDER_M = 1.2              # depth of the concrete girder under the slab
FILL_CLEAR_M = 2.5          # less room than this under the girder: the deck stands on a walled fill
PIER_EVERY_M = 30.0
FOOTING_M = 1.5             # piers and walls go this far into the ground
CAP_M = 0.9                 # cap beam under a wide deck
LAMP_EVERY_M = 36.0
LAMP = "/Game/Prop/Kit_StreetLamp_C/Mesh/streetLampC"
JOIN_DROP_M = 0.04          # a deck lying on a wider joining deck sits this much lower


def runs(ss):
    count = max(1, int(round((ss[-1] - ss[0]) / SEGMENT_M)))
    marks = sorted({min(range(len(ss)), key=lambda i: abs(ss[i] - (ss[0] + (ss[-1] - ss[0]) * k / count)))
                    for k in range(count + 1)})
    return [ss[a:b + 1] for a, b in zip(marks, marks[1:])]


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    name = args[0]
    net = load_json("network.json")
    edge = structures.viaduct_edge(net, name)
    road = roadgeom.Road(edge)
    sec = SECTIONS[edge["cls"]]
    half, side_w, lanes = road.half, sec["sidewalk"], sec["lanes"]
    d_side = half + side_w
    d_out = d_side + BARRIER_W
    length = road.length
    out_dir = os.path.join(DATA, "structures", name)
    os.makedirs(out_dir, exist_ok=True)
    uv_origin = (math.floor(float(road.xy[:, 0].min()) / UV_M) * UV_M, math.floor(float(road.xy[:, 1].min()) / UV_M) * UV_M)

    # the ground under the viaduct, as the sector each point lies in builds it (tunnel_mesh does the same)
    box = (float(road.xy[:, 0].min()), float(road.xy[:, 0].max()), float(road.xy[:, 1].min()), float(road.xy[:, 1].max()))
    field = roadgeom.HeightField(roadgeom.sector_roads(net, box, 120.0))
    own = []
    for sname, sspec in sectors.SECTORS.items():
        w_, e_, s_, n_ = sspec["box"]
        if e_ < box[0] - 30 or w_ > box[1] + 30 or n_ < box[2] - 30 or s_ > box[3] + 30:
            continue
        own.append((sectors.outline(sname), roadgeom.HeightField(roadgeom.sector_roads(net, sspec["box"], 80.0),
                                                                 levels=sectors.levels(sname, net))))
    base = np.load(os.path.join(DATA, "terrain_base.npz"))
    base_ground, water = base["ground"], base["water"]

    def z_at(s):
        return float(np.interp(s, road.s, road.z))

    def at(s, d, dz):
        p, _, n = road.at(s)
        return (float(p[0] + n[0] * d), float(p[1] + n[1] * d), z_at(s) + dz)

    def at_abs(s, d, z):
        p, _, n = road.at(s)
        return (float(p[0] + n[0] * d), float(p[1] + n[1] * d), z)

    def ground(s, d):
        p, _, n = road.at(s)
        x, y = float(p[0] + n[0] * d), float(p[1] + n[1] * d)
        # over open water (a lagoon a ramp crosses, 2026-11-16) the ground is the water's bed: the road heights the
        # field spreads from the shores round it are not ground there, and read so the whole ramp became a fill
        u, v = to_pixel(np.array([x]), np.array([y]))
        iu = int(np.clip(round(float(u[0])), 0, water.shape[1] - 1))
        iv = int(np.clip(round(float(v[0])), 0, water.shape[0] - 1))
        if water[iv, iu]:
            return float(bilinear(base_ground, np.array([x]), np.array([y]))[0]) + CURB_M
        f = next((fl for ring, fl in own if sectors.contains(ring, x, y)), field)
        return float(roadgeom.ground_heights(f, [(x, y)], base_ground)[0]) + CURB_M

    grid = [STEP_M * k for k in range(int(length / STEP_M) + 1)] + [length]
    grid = sorted(set(round(g, 3) for g in grid))
    under = {s: z_at(s) - SLAB_M - GIRDER_M for s in grid}
    high_ground = {s: max(ground(s, d) for d in (-d_out, 0.0, d_out)) for s in grid}
    low_ground = {s: min(ground(s, d) for d in (-d_out, 0.0, d_out)) for s in grid}
    fill = {s: under[s] - high_ground[s] < FILL_CLEAR_M for s in grid}
    # the fill only at the two ends: from each end in to the first station with room enough for a pier
    a_end = next((s for s in grid if not fill[s]), length)
    b_end = next((s for s in reversed(grid) if not fill[s]), 0.0)
    if a_end >= b_end:
        a_end, b_end = length / 2.0, length / 2.0               # never high enough: a fill from end to end

    solids = {}

    def sweep(key, ss, section, slot):
        for i, part in enumerate(runs(ss)):
            solid = solidkit.Solid()
            solid.sweep([section(s) for s in part], lambda k, j, part=part: slot(k, part[j], part[j + 1]))
            solids["%s_%02d" % (key, i)] = solid

    # ---- deck: barriers, sidewalks, kerbs, carriageway with its lane lines; a slab under it
    # ---- the other level-1 roads that meet this one at an end: barrier open on their carriageway, deck lower on theirs
    ends = {edge["a"], edge["b"]}
    joiners = [roadgeom.Road(e) for e in net["edges"]
               if e is not edge and e.get("level", 0) == 1 and ({e["a"], e["b"]} & ends)]

    def dist_to(r, x, y):
        a, b = r.xy[:-1], r.xy[1:]
        ab = b - a
        q = np.array([x, y])
        t = np.clip(((q - a) * ab).sum(axis=1) / np.maximum((ab ** 2).sum(axis=1), 1e-9), 0.0, 1.0)
        return float(np.sqrt((((a + ab * t[:, None]) - q) ** 2).sum(axis=1)).min())

    def on_joiner(x, y, extra):
        """Joiners whose carriageway (half width + extra) covers the point."""
        return [r for r in joiners if dist_to(r, x, y) < r.half + extra]

    open_cache = {}

    def barrier_open(s, side):
        key = (round(s, 3), side)
        if key not in open_cache:
            x, y, _ = at(s, side * (d_side + BARRIER_W * 0.5), 0.0)
            open_cache[key] = bool(on_joiner(x, y, -0.3))
        return open_cache[key]

    def drop(s, d):
        x, y, _ = at(s, d, 0.0)
        return -JOIN_DROP_M if any(r.half > half + 0.01 for r in on_joiner(x, y, BARRIER_W)) else 0.0

    lane_w = 2.0 * half / max(lanes, 1)
    marks = []                                            # (d, kind) of the lane lines, left to right across
    for k in range(1, lanes):
        d = half - k * lane_w
        if lanes % 2 == 0 and k == lanes // 2 and edge["cls"] not in ("ramp", "ring"):
            marks.append((d, "yellow"))
        else:
            marks.append((d, "dash"))
    profile = [(d_out, -SLAB_M, "Concrete"), (d_out, BARRIER_H, "Concrete"), (d_side, BARRIER_H, "Concrete")]
    if side_w > 0.0:
        profile += [(d_side, CURB_M, "Sidewalk"), (half, CURB_M, "Curb"), (half, 0.0, "Road")]
    else:
        profile += [(d_side, 0.0, "Road")]
        profile += [(half - 0.3, 0.0, "PaintWhite"), (half - 0.45, 0.0, "Road")]          # edge line
    for d, kind in marks:
        if kind == "yellow":
            profile += [(d + 0.185, 0.0, "PaintYellow"), (d + 0.075, 0.0, "Road"), (d - 0.075, 0.0, "PaintYellow"),
                        (d - 0.185, 0.0, "Road")]
        else:
            profile += [(d + 0.055, 0.0, "dash"), (d - 0.055, 0.0, "Road")]
    if side_w > 0.0:
        profile += [(-half, 0.0, "Curb"), (-half, CURB_M, "Sidewalk"), (-d_side, CURB_M, "Concrete")]
    else:
        profile += [(-(half - 0.45), 0.0, "PaintWhite"), (-(half - 0.3), 0.0, "Road"), (-d_side, 0.0, "Concrete")]
    profile += [(-d_side, BARRIER_H, "Concrete"), (-d_out, BARRIER_H, "Concrete"), (-d_out, -SLAB_M, "Concrete")]

    def deck_slot(k, s0, s1):
        slot = profile[k][2]
        if slot != "dash":
            return slot
        return "PaintWhite" if ((s0 + s1) / 2.0 - 5.0) % 12.0 < 3.0 else "Road"

    last = len(profile) - 1
    barrier_idx = {1: 1.0, 2: 1.0, last - 1: -1.0, last - 2: -1.0}   # the barrier's top corners, by side

    def deck_section(s):
        pts = []
        for i, (d, dz, _) in enumerate(profile):
            if i in barrier_idx and joiners and barrier_open(s, barrier_idx[i]):
                dz = 0.0
            pts.append(at(s, d, dz + (drop(s, d) if joiners and dz >= 0.0 else 0.0)))
        return pts

    sweep("Deck", grid, deck_section, deck_slot)

    # ---- girder under the slab where the deck stands on piers
    gw = max(1.2, d_out - 1.2)
    pier_s = [s for s in grid if a_end - STEP_M <= s <= b_end + STEP_M]
    if len(pier_s) >= 2:
        sweep("Girder", pier_s, lambda s: [at(s, gw, -SLAB_M - 0.02), at(s, -gw, -SLAB_M - 0.02),
                                           at(s, -gw * 0.8, -SLAB_M - GIRDER_M), at(s, gw * 0.8, -SLAB_M - GIRDER_M)],
              lambda k, s0, s1: "Concrete")

    # ---- the fills at the ends: a block between retaining walls from below the ground up to the slab
    for label, (s0, s1) in (("FillA", (0.0, a_end)), ("FillB", (b_end, length))):
        ss = [s for s in grid if s0 <= s <= s1]
        if len(ss) < 2:
            continue
        sweep(label, ss, lambda s: [at_abs(s, d_out, low_ground[s] - FOOTING_M), at(s, d_out, -SLAB_M - 0.02),
                                    at(s, -d_out, -SLAB_M - 0.02), at_abs(s, -d_out, low_ground[s] - FOOTING_M)],
              lambda k, s0_, s1_: "Concrete")

    # ---- piers between the fills, no further apart than PIER_EVERY_M where the ground lets them stand: never on a
    # carriageway below (a freeway's median will do), so a span over a road is as long as the road is wide
    wide = d_out > 7.5
    cols_d = [-d_out * 0.5, d_out * 0.5] if wide else [0.0]
    below = [r for r in roadgeom.sector_roads(net, box, 60.0)]

    def free(s):
        for dc in cols_d:
            p, _, n = road.at(s)
            q = np.array([p[0] + n[0] * dc, p[1] + n[1] * dc])
            for r in below:
                a, b = r.xy[:-1], r.xy[1:]
                ab = b - a
                t = np.clip(((q - a) * ab).sum(axis=1) / np.maximum((ab ** 2).sum(axis=1), 1e-9), 0.0, 1.0)
                d = float(np.sqrt((((a + ab * t[:, None]) - q) ** 2).sum(axis=1)).min())
                med = SECTIONS[r.cls]["median"] if r.cls in SECTIONS else 0.0
                if d - r.half < 1.6 and not (med >= 1.8 and d <= med / 2.0 - 0.8):
                    return False
        return True

    piers = []
    if b_end - a_end > 12.0:
        cand = [s for s in np.arange(a_end + 4.0, b_end - 4.0, 0.5) if free(float(s))]
        prev = a_end
        while b_end - prev > PIER_EVERY_M and cand:
            window = [s for s in cand if prev + 10.0 < s <= prev + PIER_EVERY_M]
            beyond = [s for s in cand if s > prev + PIER_EVERY_M]
            if window:
                nxt = max(window)
            elif beyond:
                nxt = min(beyond)
            else:
                break
            if b_end - nxt < 8.0:
                break
            piers.append(float(nxt))
            prev = nxt
    for i, s in enumerate(piers):
        bottom = z_at(s) - SLAB_M - GIRDER_M
        foot = min(ground(s, d) for d in (-d_out, 0.0, d_out)) - FOOTING_M
        solid = solidkit.Solid()
        cols = [(-d_out * 0.5, 0.8), (d_out * 0.5, 0.8)] if wide else [(0.0, 1.3)]
        top = bottom - (CAP_M if wide else 0.0)
        for dc, hw in cols:
            corners = [(s - 0.8, dc - hw), (s - 0.8, dc + hw), (s + 0.8, dc + hw), (s + 0.8, dc - hw)]
            solid.box([at_abs(ss, dd, foot) for ss, dd in corners], [at_abs(ss, dd, top) for ss, dd in corners])
        if wide:
            corners = [(s - 1.0, -(d_out - 1.0)), (s - 1.0, d_out - 1.0), (s + 1.0, d_out - 1.0), (s + 1.0, -(d_out - 1.0))]
            solid.box([at_abs(ss, dd, top) for ss, dd in corners], [at_abs(ss, dd, bottom + 0.05) for ss, dd in corners])
        solids["Pier_%02d" % i] = solid

    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects = [solidkit.build_object("Bay_%s_%s" % (name, key), solid, SLOTS, UV_M, uv_origin) for key, solid in solids.items()]
    glb = os.path.join(out_dir, "%s.glb" % name)
    faces = solidkit.export_objects(objects, glb)

    # ---- lamps on the barriers, alternating sides, the arm over the carriageway
    lamps = []
    for side, shift in ((1.0, 0.0), (-1.0, LAMP_EVERY_M / 2.0)):
        s = 9.0 + shift
        while s < length - 6.0:
            if joiners and barrier_open(s, side):
                s += LAMP_EVERY_M
                continue
            x, y, z = at(s, side * (d_side + BARRIER_W * 0.5), BARRIER_H)
            _, _, n = road.at(s)
            yaw = math.degrees(math.atan2(side * n[1], -side * n[0])) % 360.0
            lamps.append([round(x * 100, 1), round(-y * 100, 1), round(z * 100, 1), round(yaw, 1), 1.0])
            s += LAMP_EVERY_M
    with open(os.path.join(out_dir, "props.json"), "w") as f:
        json.dump({"structure": name, "props": {LAMP: lamps}, "trees": {}}, f)

    # ---- review cameras: name;x,y,z;look x,y,z in Unreal cm (y is south)
    def cam(label, s, d, up_abs, s_look, d_look, up_look_abs):
        p = at_abs(s, d, up_abs)
        q = at_abs(s_look, d_look, up_look_abs)
        return "%s_%s;%.0f,%.0f,%.0f;%.0f,%.0f,%.0f" % (name, label, p[0] * 100, -p[1] * 100, p[2] * 100, q[0] * 100, -q[1] * 100, q[2] * 100)

    mid = length / 2.0
    ground_mid = ground(mid, 0.0)
    views = [cam("deck_a", 2.0, -1.5, z_at(2.0) + 1.5, min(length, 60.0), -1.5, z_at(min(length, 60.0)) + 1.5),
             cam("deck_b", length - 2.0, 1.5, z_at(length - 2.0) + 1.5, max(0.0, length - 60.0), 1.5, z_at(max(0.0, length - 60.0)) + 1.5),
             cam("side_l", mid, d_out + 45.0, ground_mid + 6.0, mid, 0.0, z_at(mid) - 2.0),
             cam("side_r", mid, -(d_out + 45.0), ground_mid + 6.0, mid, 0.0, z_at(mid) - 2.0),
             cam("under", mid, d_out + 6.0, ground_mid + 1.7, mid, -d_out, z_at(mid) - 3.0),
             cam("air", mid, 60.0, z_at(mid) + 45.0, mid, 0.0, z_at(mid))]
    with open(os.path.join(out_dir, "views.txt"), "w") as f:
        f.write("\n".join(views) + "\n")
    least = min((under[s] - high_ground[s] for s in grid if a_end <= s <= b_end), default=0.0)
    info = {"structure": name, "title": structures.VIADUCTS[name]["title"], "length": round(length, 1),
            "fills": [[0.0, round(a_end, 1)], [round(b_end, 1), round(length, 1)]], "piers": [round(s, 1) for s in piers],
            "z_ends": [round(z_at(0.0), 2), round(z_at(length), 2)], "least_clearance": round(least, 2), "half_width": round(d_out, 2)}
    with open(os.path.join(out_dir, "viaduct.json"), "w") as f:
        json.dump(info, f, indent=1)
    print("VIADUCT %s: %.0f m, fills %.0f m and %.0f m at the ends, %d piers, least room under the girder %.2f m; "
          "%d meshes, %d faces, %d lamps; %d joining structures, barrier open at %d stations"
          % (name, length, a_end, length - b_end, len(piers), least, len(objects), faces, len(lamps), len(joiners),
             sum(1 for v in open_cache.values() if v)))
    print("VIADUCT %s: wrote %s" % (name, glb))


main()
