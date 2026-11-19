"""Builds one tunnel of the Bay city as meshes (Blender): the road with its paint and raised shoulders, the
retaining walls of the two open ramps with their parapets, and, where the road is deep enough, the box: lined
walls, a roof slab with two rows of lamps, and a wall over each portal.

  blender -b --factory-startup --python Tools/bay/tunnel_mesh.py -- <tunnel>

Input:  Saved/Bay/network.json (the tunnel's centre line and height profile), Tools/bay/structures.py (TUNNELS),
        Tools/bay/sectors.py (the levels of the sectors it runs under: the ground beside its ramps),
        Saved/Bay/terrain_base.npz (ground where no road is near)
Output: Saved/Bay/structures/<name>/<name>.glb     meshes in metres, x east, y north, z up: floor, each wall and
                                                   the roof in pieces of about SEGMENT_M (why: solidkit.export_objects)
        Saved/Bay/structures/<name>/carve.npz      the strip under which the landscape must lie below the
                                                   tunnel's floor (pts, z, tris): read by build_surface.py
        Saved/Bay/structures/<name>/views.txt      review cameras (tour.ps1 -Structure <name>)
        Saved/Bay/structures/<name>/tunnel.json    stations, portals, heights (for notes)
        Saved/Bay/structures/<name>/props.json     no street furniture; "lights": one spot light under each lamp
                                                   ([x, y, z] in Unreal cm) and "light": what kind (build_bay.py)
Material slots: Road, PaintWhite, PaintYellow, Curb, Sidewalk, Concrete, Tile (wall lining), Light (the lamps
under the roof: an emissive material).

How. Everything is a cross-section swept along the centre line, every 3 m: the floor (carriageway strips
with their paint, as on the bridges, so the lane lines carry on from the avenue), each wall, the roof. All are
closed bodies, so Blender turns each face outwards and what is seen from inside the tunnel faces the driver.
The walls of an open ramp stand TUNNEL_PARAPET_M above the ground beside them (the height the sector's own
ground mesh has there: both read the same height field). The roof begins and ends where structures.py says.
Lamps: LAMP_M long every LAMP_EVERY_M in two rows, one row half a step ahead of the other. The glowing faces
alone would leave the lighting to Lumen, which may be switched off or run coarse; so each lamp also gets a
real light, pointing straight down (nothing above the roof is lit by it) and casting no shadow (cheap).
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
from common import CURB_M, DATA, load_json

SLOTS = ["Road", "PaintWhite", "PaintYellow", "Curb", "Sidewalk", "Concrete", "Tile", "Light"]
UV_M = 4.0
STEP_M = 3.0                # cross-sections; the lane dashes (3 m on, 9 m off) and the lamps fall on this grid
SEGMENT_M = 42.0            # floor, walls and roof are cut into separate meshes about this long
FLOOR_M = 0.5               # floor slab under the road surface
KERB_M = 0.25               # the shoulders stand this far above the road
TILE_M = 2.6                # height of the light lining on the walls of the covered part
LIGHT_AT_M, LIGHT_W_M = 4.25, 0.8       # each row of lamps: distance from the axis, width
LAMP_M, LAMP_EVERY_M = 6.0, 12.0        # a lamp's length and the step from one to the next in its row
LAMP_CLEAR_OF_PORTAL_M = 2.0
# One spot light per lamp. 6500 cd from 4.8 m gives the road about 330 lux under a lamp and 170 between two,
# which the map's exposure range (it opens to EV 8 in the dark) shows as a lit tunnel, not a bright one.
LIGHT = {"candela": 6500.0, "radius_m": 18.0, "inner_deg": 58.0, "outer_deg": 80.0, "colour": [1.0, 0.90, 0.72],
         "below_roof_m": 0.12}
CARVE_EXTRA_M = 4.0         # the landscape is lowered this far beyond the walls' outer faces...
CARVE_BELOW_M = 0.8         # ...to this far below the floor slab


def runs(ss):
    """Cuts a list of stations into consecutive runs of about SEGMENT_M; neighbours share their end station."""
    count = max(1, int(round((ss[-1] - ss[0]) / SEGMENT_M)))
    marks = sorted({min(range(len(ss)), key=lambda i: abs(ss[i] - (ss[0] + (ss[-1] - ss[0]) * k / count)))
                    for k in range(count + 1)})
    return [ss[a:b + 1] for a, b in zip(marks, marks[1:])]


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    name = args[0]
    spec = structures.TUNNELS[name]
    net = load_json("network.json")
    road, s_a, s_b = structures.tunnel_layout(net, name)
    clear = spec.get("clear", structures.TUNNEL_CLEAR_M)
    half = road.half
    d_in = half + structures.TUNNEL_SHOULDER_M              # inner face of the walls
    d_out = d_in + structures.TUNNEL_WALL_M                 # outer face
    length = road.length
    out_dir = os.path.join(DATA, "structures", name)
    os.makedirs(out_dir, exist_ok=True)
    uv_origin = (math.floor(float(road.xy[:, 0].min()) / UV_M) * UV_M, math.floor(float(road.xy[:, 1].min()) / UV_M) * UV_M)

    # the ground beside the tunnel, as the sectors build it: carried by the streets around and by the levels of
    # the sector the point lies in (its "relief" and "over_tunnels" too), exactly as that sector's mesh has it;
    # outside every sector, by the streets alone
    box = (float(road.xy[:, 0].min()), float(road.xy[:, 0].max()), float(road.xy[:, 1].min()), float(road.xy[:, 1].max()))
    field = roadgeom.HeightField(roadgeom.sector_roads(net, box, 120.0))
    own = []
    for sname, sspec in sectors.SECTORS.items():
        w_, e_, s_, n_ = sspec["box"]
        if e_ < box[0] - 30 or w_ > box[1] + 30 or n_ < box[2] - 30 or s_ > box[3] + 30:
            continue
        own.append((sectors.outline(sname), roadgeom.HeightField(roadgeom.sector_roads(net, sspec["box"], 80.0),
                                                                 levels=sectors.levels(sname, net))))
    base_ground = np.load(os.path.join(DATA, "terrain_base.npz"))["ground"]

    def field_at(x, y):
        for ring, f in own:
            if sectors.contains(ring, x, y):
                return f
        return field

    def z_at(s):
        return float(np.interp(s, road.s, road.z))

    def at(s, d, dz):
        """World point at distance s along the tunnel, d metres left of its axis, dz above the road surface."""
        p, _, n = road.at(s)
        return (float(p[0] + n[0] * d), float(p[1] + n[1] * d), z_at(s) + dz)

    def at_abs(s, d, z):
        p, _, n = road.at(s)
        return (float(p[0] + n[0] * d), float(p[1] + n[1] * d), z)

    def ground(s, d):
        """Height of the ground (sidewalk level) beside the tunnel at station s, d metres left of the axis."""
        p, _, n = road.at(s)
        x, y = float(p[0] + n[0] * d), float(p[1] + n[1] * d)
        return float(roadgeom.ground_heights(field_at(x, y), [(x, y)], base_ground)[0]) + CURB_M

    def stations(s0, s1, extra=()):
        grid = [STEP_M * k for k in range(int(length / STEP_M) + 2)]
        return sorted(set([s0, s1] + [g for g in grid if s0 + 0.4 < g < s1 - 0.4] + [e for e in extra if s0 + 0.4 < e < s1 - 0.4]))

    solids = {}

    def sweep(key, ss, section, slot):
        """One closed body per run of stations. section(s): the cross-section at s; slot(k, s0, s1): the slot of
        the strip between section points k and k+1, from station s0 to s1."""
        for i, part in enumerate(runs(ss)):
            solid = solidkit.Solid()
            solid.sweep([section(s) for s in part], lambda k, j, part=part: slot(k, part[j], part[j + 1]))
            solids["%s_%02d" % (key, i)] = solid

    # ---- floor: the road with its paint, the kerbs and the two raised shoulders, mouth to mouth
    dash_in, dash_out = 3.4 - 0.055, 3.4 + 0.055
    profile = [(d_in, -FLOOR_M, "Concrete"), (d_in, KERB_M, "Sidewalk"), (half, KERB_M, "Curb"), (half, 0.0, "Road"),
               (dash_out, 0.0, "dash"), (dash_in, 0.0, "Road"),
               (0.185, 0.0, "PaintYellow"), (0.075, 0.0, "Road"), (-0.075, 0.0, "PaintYellow"), (-0.185, 0.0, "Road"),
               (-dash_in, 0.0, "dash"), (-dash_out, 0.0, "Road"),
               (-half, 0.0, "Curb"), (-half, KERB_M, "Sidewalk"), (-d_in, KERB_M, "Concrete"), (-d_in, -FLOOR_M, "Concrete")]
    floor_s = stations(0.0, length, [s_a, s_b])

    def floor_slot(k, s0, s1):
        slot = profile[k][2]
        if slot != "dash":
            return slot
        return "PaintWhite" if ((s0 + s1) / 2.0 - 5.0) % 12.0 < 3.0 else "Road"      # lane dashes: 3 m of paint every 12 m

    sweep("Floor", floor_s, lambda s: [at(s, d, dz) for d, dz, _ in profile], floor_slot)

    # ---- walls. Open ramps: retaining walls up to a parapet above the ground. Covered part: up to the roof,
    # the lower part lined
    parapet = structures.TUNNEL_PARAPET_M
    for ramp, (s0, s1) in (("RampA", (0.0, s_a)), ("RampB", (s_b, length))):
        for label, side in (("L", 1.0), ("R", -1.0)):
            sweep("%s_%s" % (ramp, label), stations(s0, s1),
                  lambda s, side=side: [at(s, side * d_in, -FLOOR_M), at_abs(s, side * d_in, ground(s, side * (d_out + 0.4)) + parapet),
                                        at_abs(s, side * d_out, ground(s, side * (d_out + 0.4)) + parapet), at(s, side * d_out, -FLOOR_M)],
                  lambda k, s0_, s1_: "Concrete")
    ss = stations(s_a, s_b)
    for label, side in (("L", 1.0), ("R", -1.0)):
        sweep("Wall_%s" % label, ss,
              lambda s, side=side: [at(s, side * d_in, -FLOOR_M), at(s, side * d_in, TILE_M), at(s, side * d_in, clear),
                                    at(s, side * d_out, clear), at(s, side * d_out, -FLOOR_M)],
              lambda k, s0_, s1_: "Tile" if k == 0 else "Concrete")

    # ---- roof slab over the covered part; two rows of lamps on its underside, one row half a step ahead
    l0, l1 = LIGHT_AT_M - LIGHT_W_M / 2, LIGHT_AT_M + LIGHT_W_M / 2
    top = clear + structures.TUNNEL_ROOF_M
    under = [(d_out, "Concrete"), (l1, "lamp+"), (l0, "Concrete"), (-l0, "lamp-"), (-l1, "Concrete"), (-d_out, "Concrete")]
    roof_profile = [(d, clear, slot) for d, slot in under] + [(-d_out, top, "Concrete"), (d_out, top, "Concrete")]
    lamps = []                                              # (station of its middle, side)
    for side, lead in ((1.0, 0.0), (-1.0, LAMP_EVERY_M / 2.0)):
        k = 0
        while lead + k * LAMP_EVERY_M + LAMP_M <= s_b - LAMP_CLEAR_OF_PORTAL_M:
            if lead + k * LAMP_EVERY_M >= s_a + LAMP_CLEAR_OF_PORTAL_M:
                lamps.append((lead + k * LAMP_EVERY_M + LAMP_M / 2.0, side))
            k += 1

    def roof_slot(k, s0, s1):
        slot = roof_profile[k][2]
        if not slot.startswith("lamp"):
            return slot
        side, mid = (1.0 if slot == "lamp+" else -1.0), (s0 + s1) / 2.0
        return "Light" if any(sd == side and abs(mid - at_s) < LAMP_M / 2.0 for at_s, sd in lamps) else "Concrete"

    sweep("Roof", ss, lambda s: [at(s, d, dz) for d, dz, _ in roof_profile], roof_slot)

    # ---- the wall over each portal: from the roof up to the parapets' height, across the whole trench
    head = structures.TUNNEL_HEAD_M
    for label, s_face, into in (("A", s_a, 1.0), ("B", s_b, -1.0)):
        crown = max(ground(s_face, d_out + 0.4), ground(s_face, -d_out - 0.4)) + parapet
        low = z_at(s_face) + top - 0.05
        s_back = s_face + into * head
        corners = [(s_face, d_out), (s_face, -d_out), (s_back, -d_out), (s_back, d_out)]
        solid = solidkit.Solid()
        solid.box([at_abs(s, d, low) for s, d in corners], [at_abs(s, d, crown) for s, d in corners])
        solids["Head_%s" % label] = solid

    # ---- Blender objects, each exported as a mesh of its own
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects = [solidkit.build_object("Bay_%s_%s" % (name, key), solid, SLOTS, UV_M, uv_origin) for key, solid in solids.items()]
    glb = os.path.join(out_dir, "%s.glb" % name)
    faces = solidkit.export_objects(objects, glb)

    # ---- the strip under which the landscape has to stay below the floor; under water (a tunnel marked
    # "under_water", between the banks) the opposite: the strip over which the river bed has to stay, a metre
    # above the roof, so the tunnel lies buried in the bed
    w = d_out + CARVE_EXTRA_M
    wet = structures.wet_span(net, name)

    def strip(stations, z_of):
        pts, zs, tris = [], [], []
        for s in stations:
            for d in (w, -w):
                x, y, _ = at(s, d, 0.0)
                pts.append((x, y))
                zs.append(z_of(s))
        for j in range(len(stations) - 1):
            if stations[j + 1] - stations[j] > STEP_M * 1.5:
                continue                                    # a gap: the stretch under the water
            a, b, c, d = 2 * j, 2 * j + 1, 2 * j + 3, 2 * j + 2
            tris += [(a, b, c), (a, c, d)]
        return np.array(pts), np.array(zs), np.array(tris, dtype=np.int64).reshape(-1, 3)

    dry = [s for s in floor_s if wet is None or s <= wet[0] or s >= wet[1]]
    pts, zs, tris = strip(dry, lambda s: z_at(s) - FLOOR_M - CARVE_BELOW_M)
    np.savez_compressed(os.path.join(out_dir, "carve.npz"), pts=pts, z=zs, tris=tris)
    bury_path = os.path.join(out_dir, "bury.npz")
    if wet is not None:
        under = [s for s in floor_s if wet[0] - STEP_M <= s <= wet[1] + STEP_M]
        pts, zs, tris = strip(under, lambda s: z_at(s) + top + structures.TUNNEL_BURY_M)
        np.savez_compressed(bury_path, pts=pts, z=zs, tris=tris)
        print("TUNNEL %s: under water from s %.0f to %.0f; bed held at least %.1f m over the roof there" % (
            name, wet[0], wet[1], structures.TUNNEL_BURY_M))
    elif os.path.exists(bury_path):
        os.remove(bury_path)

    # ---- review cameras: name;x,y,z;look x,y,z in Unreal cm (y is south)
    def cam(label, s, d, up, s_look, d_look, up_look):
        def point(ss_, dd, uu):
            p, t, n = road.at(min(max(ss_, 0.0), length))
            over = ss_ - min(max(ss_, 0.0), length)         # beyond a mouth: straight on along the axis
            x, y = p[0] + t[0] * over + n[0] * dd, p[1] + t[1] * over + n[1] * dd
            return "%.0f,%.0f,%.0f" % (x * 100, -y * 100, (z_at(min(max(ss_, 0.0), length)) + uu) * 100)
        return "%s_%s;%s;%s" % (name, label, point(s, d, up), point(s_look, d_look, up_look))

    mid = (s_a + s_b) / 2.0
    edge = structures.find_edge(net, structures.TUNNELS[name]["at"], "tunnel")

    def beyond(end):
        """A spot 30 m out along the street that carries on past one mouth (end 0: the road's first point, 1: its
        last), 24 m up, at that street's height: "x,y,z" in Unreal cm. Straight on along the axis when no street
        carries on (2026-11-17: a mouth where the street turns right away put the camera over a block's roofs)."""
        node = edge["a"] if end == 0 else edge["b"]
        p0 = road.at(0.0 if end == 0 else length)
        inward = (p0[1][0], p0[1][1]) if end == 0 else (-p0[1][0], -p0[1][1])
        best, best_dot = None, 0.3
        for e in net["edges"]:
            if e is edge or e.get("level", 0) != 0 or e["cls"] == "tunnel" or node not in (e["a"], e["b"]):
                continue
            pts = e["pts"] if e["a"] == node else e["pts"][::-1]
            run, prev = 0.0, pts[0]
            for p in pts[1:]:
                run += math.hypot(p[0] - prev[0], p[1] - prev[1])
                prev = p
                if run >= 12.0:
                    break
            dx, dy = prev[0] - pts[0][0], prev[1] - pts[0][1]
            dd = math.hypot(dx, dy) or 1.0
            straight_on = -(dx * inward[0] + dy * inward[1]) / dd           # 1 = carries straight on out of the mouth
            if straight_on > best_dot:
                best, best_dot = pts, straight_on
        if best is None:
            return None
        run = 0.0
        for a, b in zip(best[:-1], best[1:]):
            seg = math.hypot(b[0] - a[0], b[1] - a[1])
            if seg > 1e-6 and run + seg >= 30.0:
                t = (30.0 - run) / seg
                x, y, zz = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t
                return "%.0f,%.0f,%.0f" % (x * 100, -y * 100, (zz + 24.0) * 100)
            run += seg
        x, y, zz = best[-1][:3]
        return "%.0f,%.0f,%.0f" % (x * 100, -y * 100, (zz + 24.0) * 100)

    views = [cam("mouth_a", -14.0, -2.5, 1.5, s_a, 0.0, 2.2), cam("ramp_a", s_a * 0.45, -2.5, 1.5, s_a + 25.0, 0.0, 1.8),
             cam("inside_a", s_a + 12.0, -2.5, 1.5, s_a + 130.0, 0.0, 1.5), cam("inside_mid", mid, 2.5, 1.5, mid + 110.0, 0.0, 1.5),
             cam("inside_mid_back", mid, -2.5, 1.5, mid - 110.0, 0.0, 1.5), cam("inside_b", s_b - 12.0, 2.5, 1.5, s_b + 70.0, 0.0, 3.5),
             cam("out_b", s_b + 6.0, 2.5, 1.5, length + 20.0, 0.0, 1.8), cam("mouth_b", length + 14.0, 2.5, 1.5, s_b, 0.0, 2.2),
             # (2026-11-17: the views from above stood 34 m to the side of the ramp, which in a built block is a
             # roof or the inside of a building; they now stand over the street that carries on past each mouth,
             # 30 m back along the axis, and look down the ramp. The view beside the ramp stands just outside its
             # wall, on the strip the sectors keep clear, not 7 m out in whatever lot is there)
             cam("above_a", -30.0, 0.0, 24.0, s_a, 0.0, 0.0), cam("above_b", length + 30.0, 0.0, 24.0, s_b, 0.0, 0.0),
             # (2026-11-18: ...and at eye height above the ground it stands on, not above the mouth: where the ground
             # beside the ramp is higher than the mouth, a hillside cut, the camera stood inside the hill and looked up at
             # the wall from the trench the landscape leaves under a tunnel, sea and all)
             cam("rail_a", s_a * 0.55, d_out + 2.5, max(z_at(0.0), ground(s_a * 0.55, d_out + 2.5)) - z_at(s_a * 0.55) + 1.9,
                 s_a, -d_out, z_at(0.0) - z_at(s_a) + 0.5)]
    for k, (end, s_look) in enumerate(((0, s_a), (1, s_b))):
        spot = beyond(end)
        if spot:
            label, _, look = views[8 + k].split(";")
            views[8 + k] = ";".join((label, spot, look))
    with open(os.path.join(out_dir, "views.txt"), "w") as f:
        f.write("\n".join(views) + "\n")

    lights = []
    for at_s, side in lamps:
        x, y, z = at(at_s, side * LIGHT_AT_M, clear - LIGHT["below_roof_m"])
        lights.append([round(x * 100.0, 1), round(-y * 100.0, 1), round(z * 100.0, 1)])
    with open(os.path.join(out_dir, "props.json"), "w") as f:
        json.dump({"structure": name, "props": {}, "trees": {}, "light": LIGHT, "lights": lights}, f)
    info = {"structure": name, "title": spec["title"], "length": round(length, 1), "covered": [round(s_a, 1), round(s_b, 1)],
            "mouths": [[round(float(v), 2) for v in road.xy[0]], [round(float(v), 2) for v in road.xy[-1]]],
            "portals": [[round(v, 2) for v in at(s_a, 0.0, 0.0)], [round(v, 2) for v in at(s_b, 0.0, 0.0)]],
            "z_mouths": [round(z_at(0.0), 2), round(z_at(length), 2)], "z_floor": round(float(road.z.min()), 2),
            "clear": clear, "half_width": round(d_out, 2), "meshes": len(objects), "lamps": len(lamps),
            "ground_at_portals": [round(ground(s_a, d_out + 0.4), 2), round(ground(s_b, d_out + 0.4), 2)]}
    with open(os.path.join(out_dir, "tunnel.json"), "w") as f:
        json.dump(info, f, indent=1)
    cover = min(ground(s, side * (d_out + 0.4)) - (z_at(s) + top) for s in ss for side in (1.0, -1.0))
    print("TUNNEL %s: %.0f m mouth to mouth, covered %.0f m (s %.0f .. %.0f); floor down to %.2f m, %.1f m headroom; "
          "least ground over the roof %.2f m; %d meshes, %d faces, %d lamps, %d cameras" % (
              name, length, s_b - s_a, s_a, s_b, info["z_floor"], clear, cover, len(objects), faces, len(lamps), len(views)))
    print("TUNNEL %s: wrote %s" % (name, glb))


main()
