"""Street furniture and street trees of one sector of the Bay city.

  python -P Tools/bay/plan_props.py <sector>

Input:  Saved/Bay/network.json, Saved/Bay/sectors/<sector>/prep.json (shore), Tools/bay/sectors.py,
        Saved/Bay/sectors/<sector>/ground.npz (the sector's mesh: where a square's ground is), Saved/Bay/terrain_base.npz
Output: Saved/Bay/sectors/<sector>/props.json
            props  {mesh path: [[x, y, z, yaw, scale], ...]}   Unreal cm and degrees; solid things
            trees  {mesh path: [[x, y, z, yaw, scale], ...]}   street trees, each over a tree grate
        prints how many of each were placed

Everything is placed from the road geometry itself (roadgeom.Road), so each piece stands where the real
thing would: a fixed distance behind the kerb, clear of crossings and of each other.
  street lamps     every LAMP_SPACING_M, alternating sides, arm over the carriageway
  traffic signals  at junctions of three or more streets with sidewalks in the dense districts, where avenues
                   cross and where an avenue ends: for each arm, a mast on the far right corner as seen by the
                   traffic that crosses the junction into that arm, heads facing that traffic
  stop signs       everywhere else: on the side streets where an avenue goes through, on the stem of a T of
                   streets, on every arm where streets cross, on a lane coming out onto a street; near right
                   corner of the incoming traffic, just before the crossing
  street trees     between the lamps, on a grate, on streets and avenues with a sidewalk
  parking meters   beside every parking bay of a street
  hydrants, bins, mailboxes, news racks   a few per block face, near the corners
  bollards         along the top of the sea wall
  squares          the sector's "plazas": trees in a loose grid on grates, benches under them, bins
  benches          along the lines of the sector's "benches", looking to one side (a belvedere's rim)
  parks            the sector's "parks" (lawns): trees straight in the grass, benches along the edges
  gardens          the lawns plan_yards.py left behind and between the buildings: trees, thinly
  fences           the sector's "fences": panels of a fence kit end to end along a line, with gaps for gates
  pieces           the sector's "pieces": single things with a place of their own (a mast, a container)

Mesh conventions (measured in Saved/City/props.json):
  streetLampC                  arm along local +X
  SM_StreetLamp_A_StopLight_*  arm along local +Y, signal heads facing local +X (C: 6.2 m arm, D: 10.2 m)
"""
import json
import math
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import groundmesh
import roadgeom
import sectors
import structures
from common import CURB_M, DATA, load_json
from sectors import SECTORS

SEED = 4711
LAMP = "/Game/Prop/Kit_StreetLamp_C/Mesh/streetLampC"
SIGNAL_LONG = "/Game/Prop/Kit_StreetLamp_A/Mesh/SM_StreetLamp_A_StopLight_D"
SIGNAL_SHORT = "/Game/Prop/Kit_StreetLamp_A/Mesh/SM_StreetLamp_A_StopLight_C"
HYDRANT = "/Game/Megascans/3D_Assets/Fire_Hydrant_00/uiuhbegfa_LOD0"
METER = "/Game/Megascans/3D_Assets/Parking_Meter_00/ujpkaadfa_LOD0"
MAILBOX = "/Game/Megascans/3D_Assets/Mailbox_01/Mailbox_LOD0_ujijbfhba"
BOLLARD = "/Game/Megascans/3D_Assets/Metal_Bollard_00/uiyjbcega_LOD0"
CABINET = "/Game/Megascans/3D_Assets/Traffic_Control_Cabinet_00/uh4ffdmga_LOD0"
BIN = "/Game/Prop/Kit_Trashcan_A/Mesh/SM_Trashcan_A_01"
BENCH = "/Game/Prop/Kit_bench_RR/mesh/SM_street_bench"
NEWS = ["/Game/Prop/Kit_NewsDispenser_A/Mesh/SM_NewsDispenser_Small_A_01", "/Game/Prop/Kit_NewsDispenser_A/Mesh/SM_NewsDispenser_Large_A_01"]
GRATE = "/Game/Prop/Kit_TreeBase_A/Mesh/SM_TreeBase_SquareGrill_A"
STOP_SIGN = "/Game/Bay/Props/SM_Bay_StopSign"   # stop_sign.py, imported by build_bay.py stage "propassets"; face along +X
SIGNAL_DISTRICTS = ("downtown", "shoulder", "midtown")   # dense districts: signals at every junction
SIGNAL_SECTORS = ("CC", "PF")                            # ...and the whole Centro Civico with the Prefeitura
TREES = ["/Game/CityPark/Meshes/Flora/Trees/SM_Elm%02d" % i for i in range(7, 13)] + \
        ["/Game/CityPark/Meshes/Flora/Trees/SM_Maple%02d" % i for i in range(7, 13)]

LAMP_SPACING_M = 32.0
TREE_SPACING_M = 13.0
METER_SPACING_M = 6.4       # one parking bay
BOLLARD_SPACING_M = 2.6
JUNCTION_CLEAR_M = 9.0      # nothing but signals this close to where a junction begins
PARK_TREE_EVERY_M2 = 75.0   # one tree for this much lawn
YARD_TREE_EVERY_M2 = 150.0  # ...and for this much garden (plan_yards.py); a sector's "yard_tree_m2" overrides it


def ue_yaw(vx, vy):
    """Unreal yaw (degrees) of a world direction given east/north components (Unreal's y points south)."""
    return math.degrees(math.atan2(-vy, vx)) % 360.0


def main():
    name = sys.argv[1]
    sector = SECTORS[name]
    west, east, south, north = sector["box"]
    cut = sectors.outline(name)
    rng = random.Random(SEED + sum(ord(c) for c in name))
    net = load_json("network.json")
    # the street surface's height anywhere in the sector, exactly as the sector's mesh has it
    field = roadgeom.HeightField(roadgeom.sector_roads(net, sector["box"]), levels=sectors.levels(name, net))
    base_ground = np.load(os.path.join(DATA, "terrain_base.npz"))["ground"]

    mesh_ground = groundmesh.GroundMesh(name) if os.path.exists(os.path.join(DATA, "sectors", name, "ground.npz")) else None

    def walk_z(x, y):
        """Height of the sidewalk or block ground at a point: the sector's mesh itself where it has one (a
        triangle inside a block is flat, the height field under it is not), else the height field."""
        h = mesh_ground.at(x, y) if mesh_ground else None
        return h if h is not None else float(roadgeom.ground_heights(field, [(x, y)], base_ground)[0]) + CURB_M
    node_xy = {n["id"]: (n["x"], n["y"]) for n in net["nodes"]}
    node_z = {n["id"]: n["z"] for n in net["nodes"]}
    roads = []
    for e in net["edges"]:
        if e["level"] != 0 or e["cls"] in ("tunnel", "bridge"):
            continue
        xs = [p[0] for p in e["pts"]]
        ys = [p[1] for p in e["pts"]]
        if max(xs) < west - 80 or min(xs) > east + 80 or max(ys) < south - 80 or min(ys) > north + 80:
            continue
        roads.append(roadgeom.Road(e))
    roadgeom.street_polygons(roads, node_xy)          # sets each road's junction trims
    arms_at = {}
    for r in roads:
        arms_at.setdefault(r.a, []).append((r, True))
        arms_at.setdefault(r.b, []).append((r, False))

    props, trees, taken = {}, {}, []

    def inside(x, y):
        return sectors.contains(cut, x, y)

    def free(x, y, radius):
        return all((x - tx) ** 2 + (y - ty) ** 2 >= (radius + tr) ** 2 for tx, ty, tr in taken)

    # nothing stands inside a building, whoever asks: the buildings of the sector's plan (plan_lots.py runs first)
    import cv2
    footprints = []
    lots_path = os.path.join(DATA, "sectors", name, "lots.json")
    if os.path.exists(lots_path):
        with open(lots_path) as f:
            footprints = [np.array(b["corners"], dtype=np.float32).reshape(-1, 1, 2) for b in json.load(f)["buildings"]]
    # ...nor where a building of its own stands that the plan does not hold: a campaign place, the stadium (a lawn
    # under the west hospital would have its trees come up through the wards)
    footprints += [np.array(ring, dtype=np.float32).reshape(-1, 1, 2) for ring in sectors.solid_rings(name)]

    def in_building(x, y, radius):
        return any(cv2.pointPolygonTest(fp, (float(x), float(y)), True) > -(radius + 0.3) for fp in footprints)

    def put(table, mesh, x, y, z, yaw, scale=1.0, radius=0.5, force=False):
        if not inside(x, y) or (not force and not free(x, y, radius)) or in_building(x, y, min(radius, 1.0)):
            return False
        table.setdefault(mesh, []).append([round(x * 100, 1), round(-y * 100, 1), round(z * 100, 1), round(yaw % 360, 1), round(scale, 3)])
        taken.append((x, y, radius))
        return True

    def on_sidewalk(r, s, offset):
        """Point at distance s along road r, `offset` metres left of its centre (negative: right)."""
        p, t, n = r.at(s)
        z = float(np.interp(s, r.s, r.z)) + CURB_M
        return p[0] + n[0] * offset, p[1] + n[1] * offset, z, t, n

    count = {}

    def tally(what, ok):
        if ok:
            count[what] = count.get(what, 0) + 1

    # ---- how each junction is controlled (2026-11-17: every junction of three streets with sidewalks used to get
    # signals, down to two lanes meeting in a residential block). Decided from the junction alone (its roads and the
    # district it stands in), never from the sector doing the planting, so the sectors either side of a junction agree.
    def signal_area(node):
        """Whether the junction stands in a district where every junction has signals: the dense districts, and the
        Centro Civico (CC*) and the Prefeitura (PF1) whatever their district (downtown, all of it)."""
        x, y = node_xy[node]
        for k in district_order:
            w, e, s, n = SECTORS[k]["box"]
            if w - 1 <= x <= e + 1 and s - 1 <= y <= n + 1 and sectors.contains(outlines[k], x, y):
                return SECTORS[k].get("district") in SIGNAL_DISTRICTS or k.startswith(SIGNAL_SECTORS)
        return False

    def control(node, arms):
        """("signal", []), ("stop", [arms that get a stop sign]) or (None, [])."""
        walkable = [a for a in arms if a[0].sidewalk > 0]
        major = [a for a in arms if a[0].cls in ("arterial", "freeway")]
        minor = [a for a in arms if a[0].cls not in ("arterial", "freeway")]
        alleys = [a for a in arms if a[0].cls == "alley"]
        if len(walkable) >= 3:
            if signal_area(node) or not minor or len(major) == 1:
                return "signal", []
            if major:                                     # an avenue through: stop on the side streets
                return "stop", minor
            if len(arms) == 3:                            # a T of streets: stop on the stem only
                for i in range(3):
                    others = [arms[j] for j in range(3) if j != i]
                    d1, d2 = others[0][0].heading(others[0][1]), others[1][0].heading(others[1][1])
                    if d1[0] * d2[0] + d1[1] * d2[1] < -0.8:
                        return "stop", [arms[i]]
            return "stop", arms                           # all-way stop
        if alleys and len(alleys) < len(arms):            # a lane coming out onto a street
            return "stop", alleys
        if len(major) >= 2 and minor:
            return "stop", minor
        return None, []

    outlines = {k: sectors.outline(k) for k in SECTORS}
    district_order = sorted(SECTORS)

    # ---- traffic signals first: they decide the corners; stop signs at the junctions that have no signals
    for node, arms in arms_at.items():
        if node not in node_xy or len(arms) < 2:
            continue
        how, signed = control(node, arms)
        px, py = node_xy[node]
        if how == "stop":
            for r, at_start in signed:
                # on the right of the traffic coming in along this arm (the arm's left, seen from the junction), just
                # before the crossing, its face towards that traffic
                d = r.heading(at_start)
                left = (-d[1], d[0])
                trim = r.trim[0 if at_start else 1]
                off = r.half + (r.sidewalk * 0.5 if r.sidewalk > 0 else 0.6)
                x = px + d[0] * (trim + 1.5) + left[0] * off
                y = py + d[1] * (trim + 1.5) + left[1] * off
                tally("stop sign", put(props, STOP_SIGN, x, y, walk_z(x, y), ue_yaw(d[0], d[1]), radius=0.5, force=True))
            continue
        if how != "signal":
            continue
        walkable = [(r, at_start) for r, at_start in arms if r.sidewalk > 0]
        for r, at_start in walkable:
            d = r.heading(at_start)
            right = (d[1], -d[0])
            trim = r.trim[0 if at_start else 1]
            x = px + d[0] * (trim + 0.8) + right[0] * (r.half + 0.85)
            y = py + d[1] * (trim + 0.8) + right[1] * (r.half + 0.85)
            mesh = SIGNAL_LONG if r.half > 7.0 else SIGNAL_SHORT
            tally("signal", put(props, mesh, x, y, node_z[node] + CURB_M, ue_yaw(-d[0], -d[1]), radius=0.7, force=True))
        # the controller cabinet stands at one corner, behind the first arm's signal
        r, at_start = walkable[0]
        d = r.heading(at_start)
        right = (d[1], -d[0])
        trim = r.trim[0 if at_start else 1]
        x = px + d[0] * (trim + 3.2) + right[0] * (r.half + 2.6)
        y = py + d[1] * (trim + 3.2) + right[1] * (r.half + 2.6)
        tally("cabinet", put(props, CABINET, x, y, node_z[node] + CURB_M, ue_yaw(right[0], right[1]), radius=0.6))

    # ---- along every road with a sidewalk
    for r in roads:
        if r.sidewalk <= 0 or r.length < 30.0:
            continue
        start = r.trim[0] + JUNCTION_CLEAR_M
        end = r.length - r.trim[1] - JUNCTION_CLEAR_M
        if end - start < 6.0:
            continue
        for side in (1.0, -1.0):
            edge = side * r.half
            # lamps: staggered between the two sides
            s = start + (0.0 if side > 0 else LAMP_SPACING_M / 2)
            while s <= end:
                x, y, z, t, n = on_sidewalk(r, s, edge + side * 0.75)
                tally("lamp", put(props, LAMP, x, y, z, ue_yaw(-side * n[0], -side * n[1]), radius=0.6))
                s += LAMP_SPACING_M
            if sector.get("furniture") == "lamps":
                continue                                # a road out of town: lit, and nothing else on its sidewalks
            # hydrant near the first corner, bin and mailbox or news rack near the corners
            x, y, z, t, n = on_sidewalk(r, start + 3.0, edge + side * 0.6)
            if rng.random() < 0.5:
                tally("hydrant", put(props, HYDRANT, x, y, z, rng.uniform(0, 360), radius=0.9))
            x, y, z, t, n = on_sidewalk(r, end - 2.0, edge + side * 0.7)
            tally("bin", put(props, BIN, x, y, z, rng.uniform(0, 360), radius=0.7))
            if r.cls in ("street", "arterial") and rng.random() < 0.35:
                x, y, z, t, n = on_sidewalk(r, start + 6.5, edge + side * 0.8)
                tally("news rack", put(props, rng.choice(NEWS), x, y, z, ue_yaw(side * t[0], side * t[1]), radius=1.3))
            elif rng.random() < 0.3:
                x, y, z, t, n = on_sidewalk(r, start + 6.0, edge + side * 0.8)
                tally("mailbox", put(props, MAILBOX, x, y, z, ue_yaw(-side * n[0], -side * n[1]), radius=0.7))
            # street trees on their grates
            s = start + 4.0 + rng.uniform(0, 3.0)
            while s <= end - 3.0:
                x, y, z, t, n = on_sidewalk(r, s, edge + side * 1.45)
                if inside(x, y) and free(x, y, 2.4):
                    put(trees, rng.choice(TREES), x, y, z - 0.05, rng.uniform(0, 360), rng.uniform(0.8, 1.05), radius=1.6, force=True)
                    put(props, GRATE, x, y, z + 0.005, ue_yaw(t[0], t[1]), radius=0.0, force=True)
                    count["tree"] = count.get("tree", 0) + 1
                s += TREE_SPACING_M * rng.uniform(0.9, 1.15)
            # parking meters beside the parking bays of a street
            if r.cls == "street":
                s = start + 2.0
                while s <= end - 2.0:
                    x, y, z, t, n = on_sidewalk(r, s, edge + side * 0.45)
                    tally("parking meter", put(props, METER, x, y, z, ue_yaw(-side * n[0], -side * n[1]), radius=0.35))
                    s += METER_SPACING_M

    # ---- sea wall: bollards along its top, benches and lamps on the promenade behind it
    prep_path = os.path.join(DATA, "sectors", name, "prep.json")
    if os.path.exists(prep_path):
        with open(prep_path) as f:
            prep = json.load(f)
        window = (west - 40, east + 40, south - 40, north + 40)
        # no bollard or bench on a road that runs out over the wall (a bridge's approach), nor on an abutment
        # platform, whose edge carries the bridge's own parapet
        platforms = structures.platform_rings(net)
        all_roads = roadgeom.sector_roads(net, sector["box"])

        def clear_of_roads(x, y):
            for r in all_roads:
                if float(np.min(np.hypot(r.xy[:, 0] - x, r.xy[:, 1] - y))) <= r.half + r.sidewalk + 0.6:
                    return False
            return not structures.near_platform(platforms, x, y)

        for ring in prep["land"]:
            for i in range(len(ring)):
                a, b = ring[i], ring[(i + 1) % len(ring)]
                on_window = (abs(a[0] - window[0]) < 1 and abs(b[0] - window[0]) < 1) or (abs(a[0] - window[1]) < 1 and abs(b[0] - window[1]) < 1) or \
                            (abs(a[1] - window[2]) < 1 and abs(b[1] - window[2]) < 1) or (abs(a[1] - window[3]) < 1 and abs(b[1] - window[3]) < 1)
                length = math.hypot(b[0] - a[0], b[1] - a[1])
                if on_window or length < 3.0:
                    continue
                ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
                # which side is land: probe a point on the left
                lx, ly = -uy, ux
                mid = ((a[0] + b[0]) / 2 + lx * 1.5, (a[1] + b[1]) / 2 + ly * 1.5)
                import cv2
                land_left = cv2.pointPolygonTest(np.array(ring, dtype=np.float32).reshape(-1, 1, 2), (float(mid[0]), float(mid[1])), False) > 0
                ix, iy = (lx, ly) if land_left else (-lx, -ly)
                s = BOLLARD_SPACING_M / 2
                while s < length:
                    x, y = a[0] + ux * s + ix * 0.45, a[1] + uy * s + iy * 0.45
                    # (a terrace with a parapet along its walls needs no bollards)
                    if inside(x, y) and clear_of_roads(x, y) and not sector.get("parapet"):
                        tally("bollard", put(props, BOLLARD, x, y, walk_z(x, y), 0.0, radius=0.15))
                    s += BOLLARD_SPACING_M
                if length > 40.0:
                    s = 9.0
                    while s < length - 6.0:
                        x, y = a[0] + ux * s + ix * 2.2, a[1] + uy * s + iy * 2.2
                        if inside(x, y) and clear_of_roads(x, y):
                            tally("bench", put(props, BENCH, x, y, walk_z(x, y), ue_yaw(ux, uy), radius=1.2))
                        s += 18.0

    # ---- squares and waterfront greens: trees in a loose grid on their grates, benches under them, bins
    ground_path = os.path.join(DATA, "sectors", name, "ground.npz")
    if sector.get("plazas") and os.path.exists(ground_path):
        import cv2
        g = np.load(ground_path)
        cell = 0.5
        gw, gh = int((east - west) / cell) + 1, int((north - south) / cell) + 1
        is_ground = np.zeros((gh, gw), np.uint8)             # 1 where the mesh is block ground (not street, not water)
        # (block ground: plain, or the squares' own paving)
        ground_kinds = [k for k, kind in enumerate(g["kind_names"]) if str(kind) in ("ground", "plaza")]
        px = np.stack([(g["pts"][:, 0] - west) / cell, (north - g["pts"][:, 1]) / cell], axis=1)
        for tri in g["tris"][np.isin(g["kind"], ground_kinds)]:
            cv2.fillConvexPoly(is_ground, px[tri].round().astype(np.int32), 1)
        clear = cv2.distanceTransform(is_ground, cv2.DIST_L2, 5) * cell      # metres to the nearest kerb, wall or edge

        def room(x, y):
            u, v = int((x - west) / cell), int((north - y) / cell)
            return float(clear[v, u]) if 0 <= u < gw and 0 <= v < gh else 0.0

        for ring in sector["plazas"]:
            xs, ys = [p[0] for p in ring], [p[1] for p in ring]
            spacing = 8.5
            y = min(ys) + 3.0
            row = 0
            while y <= max(ys) - 2.0:
                x = min(xs) + 3.0 + (spacing / 2 if row % 2 else 0.0)
                while x <= max(xs) - 2.0:
                    tx, ty = x + rng.uniform(-0.8, 0.8), y + rng.uniform(-0.8, 0.8)
                    if sectors.contains(ring, tx, ty) and inside(tx, ty) and room(tx, ty) >= 2.6 and free(tx, ty, 2.4):
                        z = walk_z(tx, ty)
                        put(trees, rng.choice(TREES), tx, ty, z - 0.10, rng.uniform(0, 360), rng.uniform(0.85, 1.1), radius=1.6, force=True)
                        put(props, GRATE, tx, ty, z - 0.015, rng.choice((0.0, 90.0)), radius=0.0, force=True)
                        count["tree"] = count.get("tree", 0) + 1
                        # a bench beside every third tree, facing a random way; a bin now and then
                        if rng.random() < 0.34:
                            ang = rng.choice((0.0, 90.0, 180.0, 270.0))
                            # 3 m from the trunk: at 2.4 m (until 2026-11-13) the bench always fell inside the room
                            # the tree keeps free round itself, and no square ever got one
                            bx, by = tx + 3.0 * math.cos(math.radians(ang)), ty + 3.0 * math.sin(math.radians(ang))
                            if room(bx, by) >= 1.5 and inside(bx, by):
                                tally("bench", put(props, BENCH, bx, by, walk_z(bx, by), ue_yaw(-math.sin(math.radians(ang)), math.cos(math.radians(ang))), radius=1.2))
                        elif rng.random() < 0.12:
                            bx, by = tx + 1.9, ty + 1.9
                            if room(bx, by) >= 1.0 and inside(bx, by):
                                tally("bin", put(props, BIN, bx, by, walk_z(bx, by), rng.uniform(0, 360), radius=0.7))
                    x += spacing
                y += spacing * 0.9
                row += 1

    # ---- parks (the sector's lawns): trees straight in the grass, in loose clumps; benches along the edges
    if sector.get("parks") and os.path.exists(ground_path):
        import cv2
        g = np.load(ground_path)
        cell = 0.5
        gw, gh = int((east - west) / cell) + 1, int((north - south) / cell) + 1
        lawn = np.zeros((gh, gw), np.uint8)
        whole = np.zeros((gh, gw), np.uint8)                # the lawn with the paths that cross it (the sector's "paths")
        names = list(g["kind_names"])
        if "park" in names:
            px = np.stack([(g["pts"][:, 0] - west) / cell, (north - g["pts"][:, 1]) / cell], axis=1)
            for tri in g["tris"][g["kind"] == names.index("park")]:
                cv2.fillConvexPoly(lawn, px[tri].round().astype(np.int32), 1)
            whole = lawn.copy()
            if "path" in names:
                for tri in g["tris"][g["kind"] == names.index("path")]:
                    cv2.fillConvexPoly(whole, px[tri].round().astype(np.int32), 1)
        # (trees keep 2.5 m from the grass's edge, a path's edge too; the benches of the lawn's edge go by the lawn
        # with its paths, which have benches of their own, facing them: the sector's "benches")
        edge = cv2.distanceTransform(lawn, cv2.DIST_L2, 5) * cell               # metres to the grass's edge
        ys, xs = np.nonzero(edge >= 2.5)
        order = list(range(len(xs)))
        rng.shuffle(order)
        want = int(lawn.sum() * cell * cell / float(sector.get("park_tree_m2", PARK_TREE_EVERY_M2)))
        placed = 0
        for i in order:
            if placed >= want:
                break
            x, y = west + (xs[i] + 0.5) * cell, north - (ys[i] + 0.5) * cell
            if inside(x, y) and free(x, y, 3.2) and not in_building(x, y, 3.0):
                if put(trees, rng.choice(TREES), x, y, walk_z(x, y) - 0.08, rng.uniform(0, 360), rng.uniform(0.9, 1.3), radius=2.0, force=True):
                    placed += 1
        count["park tree"] = count.get("park tree", 0) + placed
        # benches just inside the lawn's edge, facing in, about one every 25 m of edge (the sector's
        # "park_bench_m": a lawn that is more of a setting than a park takes fewer)
        edge = cv2.distanceTransform(whole, cv2.DIST_L2, 5) * cell              # metres to the lawn's own edge
        ys, xs = np.nonzero((edge >= 1.2) & (edge < 1.8) & (lawn > 0))
        order = list(range(len(xs)))
        rng.shuffle(order)
        for i in order[:max(0, len(xs) // int(float(sector.get("park_bench_m", 25.0)) / cell))]:
            x, y = west + (xs[i] + 0.5) * cell, north - (ys[i] + 0.5) * cell
            gy, gx = np.gradient(edge[max(ys[i] - 2, 0):ys[i] + 3, max(xs[i] - 2, 0):xs[i] + 3])
            ix, iy = float(gx.mean()), -float(gy.mean())                       # towards the lawn's inside (east, north)
            if inside(x, y) and math.hypot(ix, iy) > 1e-3:
                tally("bench", put(props, BENCH, x, y, walk_z(x, y), ue_yaw(iy, -ix), radius=1.2))

    # ---- benches along lines the sector gives ("benches"): the rim of a belvedere, a promenade
    for spec in sector.get("benches", []):
        line = [tuple(p) for p in spec["line"]]
        every, side = float(spec.get("every", 9.0)), (1.0 if spec.get("side", "left") == "left" else -1.0)
        run = every / 2.0
        for (ax, ay), (bx, by) in zip(line[:-1], line[1:]):
            seg = math.hypot(bx - ax, by - ay)
            if seg < 1e-6:
                continue
            ux, uy = (bx - ax) / seg, (by - ay) / seg
            fx, fy = -uy * side, ux * side                      # the way the bench looks
            while run <= seg:
                x, y = ax + ux * run, ay + uy * run
                tally("bench", put(props, BENCH, x, y, walk_z(x, y), ue_yaw(fy, -fx), radius=1.2))
                run += every
            run -= seg

    # ---- fences along lines the sector gives ("fences"): panels of a fence kit end to end, each panel's own
    # length (local +X, from its origin) along the line. A straight piece takes a whole number of panels, each
    # scaled a little so they fill it exactly; "gaps" are stretches left open (a gate): [(x, y), (x, y)] pairs,
    # points on the line. With "post" a post closes each straight piece's far end (the panels carry their own
    # post at the origin end only).
    for spec in sector.get("fences", []):
        line = [tuple(p) for p in spec["line"]]
        panel = float(spec.get("panel_m", 4.03))
        meshes = list(spec["meshes"])
        gaps = [tuple(map(tuple, g)) for g in spec.get("gaps", [])]

        def open_at(x, y):
            for (gx0, gy0), (gx1, gy1) in gaps:
                run = math.hypot(gx1 - gx0, gy1 - gy0)
                t = ((x - gx0) * (gx1 - gx0) + (y - gy0) * (gy1 - gy0)) / (run * run)
                off = abs((x - gx0) * (gy1 - gy0) - (y - gy0) * (gx1 - gx0)) / run
                if -1e-6 <= t <= 1.0 + 1e-6 and off < 0.5:
                    return True
            return False

        for (ax, ay), (bx, by) in zip(line[:-1], line[1:]):
            seg = math.hypot(bx - ax, by - ay)
            if seg < 0.5:
                continue
            ux, uy = (bx - ax) / seg, (by - ay) / seg
            n = max(1, int(round(seg / panel)))
            scale = seg / (n * panel)
            yaw = ue_yaw(ux, uy)
            last_open = True
            for k in range(n):
                x, y = ax + ux * panel * scale * k, ay + uy * panel * scale * k
                mx, my = x + ux * panel * scale * 0.5, y + uy * panel * scale * 0.5
                if open_at(mx, my):
                    if not last_open and spec.get("post"):
                        tally("fence post", put(props, spec["post"], x, y, walk_z(x, y), yaw, scale, radius=0.05, force=True))
                    last_open = True
                    continue
                tally("fence panel", put(props, meshes[rng.randrange(len(meshes))], x, y, walk_z(x, y), yaw, scale, radius=0.05, force=True))
                last_open = False
            if not last_open and spec.get("post"):
                tally("fence post", put(props, spec["post"], bx, by, walk_z(bx, by), yaw, scale, radius=0.05, force=True))

    # ---- single pieces the sector places by hand ("pieces"): (mesh, (x, y), Unreal yaw in degrees, scale): a
    # floodlight mast, a container used as a store, a light tower
    for mesh, (x, y), yaw, scale in sector.get("pieces", []):
        tally("piece", put(props, mesh, x, y, walk_z(x, y), yaw, scale, radius=0.05, force=True))

    # ---- gardens (plan_yards.py): the lawns behind and between the buildings. Trees only, thinly, and none
    # close to a wall: these are back gardens and slopes, not parks
    if os.path.exists(ground_path):
        import cv2
        g = np.load(ground_path)
        names = list(g["kind_names"])
        if "yard" in names:
            cell = 0.5
            gw, gh = int((east - west) / cell) + 1, int((north - south) / cell) + 1
            lawn = np.zeros((gh, gw), np.uint8)
            px = np.stack([(g["pts"][:, 0] - west) / cell, (north - g["pts"][:, 1]) / cell], axis=1)
            for tri in g["tris"][g["kind"] == names.index("yard")]:
                cv2.fillConvexPoly(lawn, px[tri].round().astype(np.int32), 1)
            edge = cv2.distanceTransform(lawn, cv2.DIST_L2, 5) * cell
            ys, xs = np.nonzero(edge >= 2.5)
            order = list(range(len(xs)))
            rng.shuffle(order)
            want = int(lawn.sum() * cell * cell / float(sector.get("yard_tree_m2", YARD_TREE_EVERY_M2)))
            placed = 0
            for i in order:
                if placed >= want:
                    break
                x, y = west + (xs[i] + 0.5) * cell, north - (ys[i] + 0.5) * cell
                if inside(x, y) and free(x, y, 3.5) and not in_building(x, y, 4.0):
                    if put(trees, rng.choice(TREES), x, y, walk_z(x, y) - 0.08, rng.uniform(0, 360), rng.uniform(0.85, 1.25), radius=2.0, force=True):
                        placed += 1
            count["garden tree"] = count.get("garden tree", 0) + placed

    # nothing on or under a viaduct: its deck, its fills and the strip beside its barriers (the ground under a deck's
    # end is level with the deck, and a bench placed on the lawn's edge there stood on the road)
    viaducts = [ring for _, ring in structures.viaduct_rings(net, 2.0)]
    if viaducts:
        def clear(rows):
            return [r for r in rows if not any(sectors.contains(ring, r[0] / 100.0, -r[1] / 100.0) for ring in viaducts)]
        before = sum(len(v) for v in props.values()) + sum(len(v) for v in trees.values())
        props = {k: clear(v) for k, v in props.items()}
        trees = {k: clear(v) for k, v in trees.items()}
        gone = before - sum(len(v) for v in props.values()) - sum(len(v) for v in trees.values())
        if gone:
            count["left off a viaduct"] = gone
    folder = os.path.join(DATA, "sectors", name)
    with open(os.path.join(folder, "props.json"), "w") as f:
        json.dump({"sector": name, "props": props, "trees": trees}, f)
    print("PROPS %s: %s" % (name, ", ".join("%s %d" % kv for kv in sorted(count.items()))))


if __name__ == "__main__":
    main()
