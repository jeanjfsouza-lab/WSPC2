"""Chooses the buildings of one sector of the Bay city and where each one stands.

  python -P Tools/bay/plan_lots.py <sector>

Input:  Saved/Bay/sectors/<sector>/blocks.json   block outlines (sector_mesh.py)
        Saved/Bay/network.json                   roads: which frontage is on an avenue, and the ground's height
        Saved/Bay/tower_units.json               merged tall buildings (merge_towers.py), optional
        Saved/CityMap/building_units.json        merged mid-rise and row buildings of the first city, optional
        Saved/Bay/unit_faces.json                which side of each model is its richest facade (unit_faces.py), optional
        Tools/bay/sectors.py                     the sector's district and open areas
Output: Saved/Bay/sectors/<sector>/lots.json
            buildings   one record per building: unit, centre, size, height, yaw (for review and for props)
            instances   {mesh path: [[x, y, z, yaw, scale], ...]} in Unreal cm and degrees
            collision   [[x, y, z, yaw, sx, sy, sz], ...] one box per building, centre and full size in cm
            plinths     [[x, y, z, yaw, sx, sy, sz], ...] a base under each building whose model's walls stop
                        short of the ground (worked out by plan_plinths.py, which this script calls)
            podiums     [[x, y, z, yaw, sx, sy, sz], ...] a base under each building whose lot falls away
                        behind its front, from under the lowest ground up to the floor
        Saved/Bay/sectors/<sector>/lots.png      plan of the result

How a block is filled. Buildings stand on the street, not in the middle of a block: each straight side of a
block is a frontage, and buildings are set along it wall to wall, front on the property line, as deep into
the block as their footprint goes; now and then the front opens for a service lane. The longest frontages are
filled first, so their buildings take the corners. A building is only placed where its whole footprint lies
inside the block and clear of the buildings already there. What a block's frontages cannot use stays open:
a court behind the buildings, a plaza, or, where a strip is too shallow for any building, nothing.

What is built where follows the district (DISTRICTS): each kind of building has a share on ordinary streets
and another on avenues, and the corners of a frontage take the district's corner kind. Walk-up row buildings
stand with their narrow end on the street, lot beside lot; every building turns its richest facade to its
street; and each one sits on the ground under its own footprint, so none floats where the street climbs.

Two things a sector may set by hand: "landmarks", single buildings with a place of their own, and "ranks",
lines along which buildings of one kind stand wall to wall at one scale (barracks round a parade ground); a
block that holds a rank takes nothing else. Nothing is built through one of the sector's "barriers" (walls).
A sector's "no_auto" are polygons where only its ranks and landmarks are built: a block side whose middle lies in
one is no frontage (a few houses on a country street, not a wall of them from end to end); in such a sector a block
with ranks still takes ordinary fronts along its sides outside those polygons.
"""
import glob
import json
import math
import os
import random
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import groundmesh
import plan_plinths
import plan_yards
import roadgeom
import sectors
import structures
from common import CURB_M, DATA, PROJECT, load_json
from sectors import SECTORS

SEED = 20261112
SETBACK_M = 0.6             # building front behind the property line
GAP_M = (0.15, 0.45)        # buildings stand wall to wall: a street is lined by one continuous front
CLEAR_M = 0.1               # least distance between two buildings (party walls)
PASSAGE_M = (6.0, 9.0)      # now and then a frontage opens for a service lane or a plaza
PASSAGE_AFTER_M = (95.0, 150.0)   # after about this much continuous front
LANE_M = 8.0                # service lane between two rows of buildings inside a block
MAX_DEPTH_M = 64.0          # deepest footprint, measured away from the frontage
FRONTAGE_TOL_M = 5.0        # a gently curved block side counts as one frontage
MIN_FRONTAGE_M = 28.0       # shorter block sides are not built along
SCALE = (0.92, 1.12)        # a building may be built a little smaller or larger than its model
SINK_M = 0.05               # a building's floor below the lowest ground under it
PART_CELL_M = 0.25          # grid used to cut a block's open areas out of it
MAX_STEP_M = 1.2            # most the ground may differ along a building's front (how deep its door may sink)
MAX_BACK_STEP_M = 5.0       # most the ground may stand above the floor behind the front: the back of the building
                            # is cut into the slope, a storey and a half deep (it was 3.2 until the third row
                            # south of downtown, 2026-11-13: half of every hill block stayed empty)
MAX_PODIUM_M = 4.0          # most the ground may fall below the floor behind the front: a podium fills the difference
PODIUM_FROM_M = 0.3         # a smaller fall needs no podium (the model's own base covers it)
PODIUM_INTO_GROUND_M = 0.6
AVENUES = ("arterial", "bridge", "freeway")

TOWERS = ["BPP_NYG_Ref_N1", "BPP_SFD_Ref_N1", "BPP_Bldg_Hero_Tower_CHE_B01_N1", "BPP_CHF_Ref_A1_N1", "BPP_CHE_Ref_A1_N1",
          "BPP_CHA_Ref_N1", "BPP_CHC_Ref_A1_N1", "BPP_CHB_Ref_A1_N1", "BPP_SFD_RoundSplitTower_N1", "BPP_Bldg_Hero_CHH_N1"]
# the downtown towers without the three tallest (257 to 286 m): for the blocks around the financial core
SHOULDER_TOWERS = ["BPP_CHF_Ref_A1_N1", "BPP_CHE_Ref_A1_N1", "BPP_CHA_Ref_N1", "BPP_CHC_Ref_A1_N1", "BPP_CHB_Ref_A1_N1",
                   "BPP_SFD_RoundSplitTower_N1", "BPP_Bldg_Hero_CHH_N1"]
SLIM_TOWERS = ["BPP_CHF_Ref_A1_N1", "BPP_CHB_Ref_A1_N1", "BPP_CHC_Ref_A1_N1", "BPP_CHA_Ref_N1", "BPP_Bldg_Hero_CHH_N1"]
# Not placed as ordinary buildings: BPP_SFB_Entrance_A1_N1 is a portico that belongs to another building; the two
# "Triangle" models only make sense on a wedge-shaped lot; and the three domed halls are landmarks, each used once,
# where a sector's "landmarks" puts it: BPP_SFB_Dome_A1_N1 is the city hall (Prefeitura, sector PF1);
# BPP_SFB_Ref_N1 and BPP_Bldg_Hero_SFB_N1 (about 100 x 115 m, 103 and 120 m tall) are kept for the central bank
# and one more civic building. A city does not have the same dome three times within a few blocks.
MIDRISES = ["BPP_SFJ_Ref_N1", "BPP_CHI_Ref_A1_N1", "BPP_Bldg_Hero_NYG_Modern_Square_A01_N1", "BPP_NYH_Ref_N1",
            "BPP_SFA_Ref_N1", "BPP_Bldg_Hero_CHA_A01_N1", "BPP_CHD_Ref_A1_N1"]
SMALL_MIDRISES = ["BPP_SFJ_Ref_N1", "BPP_CHI_Ref_A1_N1", "BPP_Bldg_Hero_NYG_Modern_Square_A01_N1", "BPP_NYH_Ref_N1",
                  "BPP_SFA_Ref_N1", "BPP_Bldg_Hero_CHA_A01_N1"]
ROWS = ["BPP_NYAA_Ref_N1", "BPP_NYAB_Ref_N1", "BPP_NYAC_Ref_N1", "BPP_NYAD_Ref_N1", "BPP_NYAE_Ref_N1", "BPP_NYAF_Ref_N1"]
# the mid-rises with a slab's footprint: a point block (42 x 26 m, 49 m tall) and two long slabs (37 x 87 m and
# 38 x 100 m, 38 and 55 m tall). The others are 46 to 64 m square: three of them fill a block
ESTATE_BLOCKS = ["BPP_NYH_Ref_N1", "BPP_Bldg_Hero_CHA_A01_N1", "BPP_SFA_Ref_N1"]

# Distinctive models: one is built only where no other sector has the same within RARE_RADIUS_M. With the
# 60 m cap of the older districts the white hall with two domes was the only mid-rise beside BPP_NYH_Ref_N1 that
# fits an avenue, and it came up in every block along one (three blocks in a row in the port district, 2026-11-16).
RARE_UNITS = ("BPP_Bldg_Hero_CHA_A01_N1",)
RARE_RADIUS_M = 800.0

# What each district builds. A tier is a kind of building: its models, its share of the picks on an ordinary
# street and on an avenue, and how many copies of one model a sector may hold. "corner" names the tier tried
# first at the two ends of a frontage. "interior" builds further rows behind the street fronts of a big block.
DISTRICTS = {
    # financial district: towers on every corner and along the long fronts, mid-rises between them
    "downtown": {"tiers": [{"units": TOWERS, "street": 0.55, "avenue": 0.60, "max": 2},
                           {"units": MIDRISES, "street": 0.45, "avenue": 0.40, "max": 7}],
                 "corner": {"street": 0, "avenue": 0}, "corner_m": 80.0, "street_depth": 200.0, "interior": True},
    # the blocks around the financial core: the same fabric, towers up to 170 m, more mid-rises
    "shoulder": {"tiers": [{"units": SHOULDER_TOWERS, "street": 0.35, "avenue": 0.50, "max": 2},
                           {"units": MIDRISES, "street": 0.65, "avenue": 0.50, "max": 7}],
                 "corner": {"street": 0, "avenue": 0}, "corner_m": 60.0, "street_depth": 200.0, "interior": True},
    # the first blocks beyond the towers: mid-rises on every corner and along most of the fronts, walk-up rows
    # between them and behind them, a slim tower only where an avenue passes. The skyline steps down here
    "midtown": {"tiers": [{"units": SLIM_TOWERS, "street": 0.0, "avenue": 0.25, "max": 1},
                          {"units": MIDRISES, "street": 0.60, "avenue": 0.75, "max": 7},
                          {"units": ROWS, "street": 0.40, "avenue": 0.0, "max": 40}],
                "corner": {"street": 1, "avenue": 1}, "corner_m": 45.0, "street_depth": 200.0, "interior": True},
    # a hilltop neighbourhood: mid-rises on the corners and along a third of the fronts, walk-up rows between
    # them, nothing behind the street fronts but gardens. (On a hill the rows that "midtown" sets inside a
    # block come out scattered, wherever the slope lets one stand.)
    "hilltop": {"tiers": [{"units": SLIM_TOWERS, "street": 0.0, "avenue": 0.20, "max": 1},
                          {"units": SMALL_MIDRISES, "street": 0.35, "avenue": 0.80, "max": 5},
                          {"units": ROWS, "street": 0.65, "avenue": 0.0, "max": 40}],
                "corner": {"street": 1, "avenue": 1}, "corner_m": 45.0, "street_depth": 64.0, "interior": False,
                "yards": True},
    # older, lower neighbourhood at the edge of downtown: walk-up rows on the side streets, mid-rises on the
    # avenue and at the corners, a few slim residential towers where the avenue meets a cross street
    "midrise": {"tiers": [{"units": SLIM_TOWERS, "street": 0.0, "avenue": 0.20, "max": 1},
                          {"units": SMALL_MIDRISES, "street": 0.10, "avenue": 0.80, "max": 5},
                          {"units": ROWS, "street": 0.90, "avenue": 0.0, "max": 40}],
                "corner": {"street": 2, "avenue": 0}, "corner_m": 30.0, "street_depth": 40.0, "interior": False,
                # what its buildings leave over inside a block is garden, not paving (plan_yards.py)
                "yards": True},
    # an old port district: walk-up rows on every front, the avenues too, with a couple of mid-rises a block
    # where an avenue passes (with the 60 m cap only two models fit an avenue, and as the district's whole avenue
    # front they made one repeated wall, 2026-11-16)
    "port": {"tiers": [{"units": SMALL_MIDRISES, "street": 0.10, "avenue": 0.40, "max": 2},
                       {"units": ROWS, "street": 0.90, "avenue": 0.60, "max": 40}],
             "corner": {"street": 1, "avenue": 1}, "corner_m": 30.0, "street_depth": 40.0, "interior": False,
             "yards": True},
    # a housing estate: mid-rise blocks standing apart in lawn, set back from the street behind a strip of
    # grass; no rows, nothing wall to wall. "gap_m" is the distance left between two buildings of a front
    # (default GAP_M: wall to wall), "setback_m" how far the fronts stand behind the property line (default
    # SETBACK_M). plan_yards.py turns everything else into lawn and lays a walk from each door to the street.
    "estate": {"tiers": [{"units": ESTATE_BLOCKS, "street": 1.0, "avenue": 1.0, "max": 10}],
               "corner": {"street": 0, "avenue": 0}, "corner_m": 0.0, "street_depth": 64.0, "interior": False,
               "gap_m": (18.0, 30.0), "setback_m": 9.0, "yards": True},
    # The districts of the zoning after the campaign model (plan_zones.py, 2026-11-21). Their models come from
    # extra_units.json (extra_units.py): "@kind" in a tier stands for every unit of that kind. The houses are
    # optional (a git-ignored folder): a district left with no models of its own builds as its "fallback".
    # suburb: detached houses on their own lots, set back behind a front lawn, a side yard between neighbours;
    # a corner shop or a garage where an avenue passes
    "suburb": {"tiers": [{"units": ["@house"], "street": 1.0, "avenue": 0.75, "max": 8},
                         {"units": ["SM_BayWarehouse_Shop", "SM_BayWarehouse_Shop_B"], "street": 0.0, "avenue": 0.25, "max": 2}],
               "corner": {"street": 0, "avenue": 1}, "corner_m": 0.0, "street_depth": 30.0, "interior": False,
               "gap_m": (4.0, 9.0), "setback_m": 6.0, "yards": True, "fallback": "estate"},
    # victorian: the old residential flats near the centre (West Oakland): narrow Victorian houses close together,
    # cottages among them, walk-up rows on the avenues
    "victorian": {"tiers": [{"units": ["@victorian"], "street": 0.60, "avenue": 0.15, "max": 30},
                            {"units": ["@house_narrow"], "street": 0.25, "avenue": 0.0, "max": 8},
                            {"units": ROWS, "street": 0.15, "avenue": 0.60, "max": 40},
                            {"units": SMALL_MIDRISES, "street": 0.0, "avenue": 0.25, "max": 2}],
                  "corner": {"street": 0, "avenue": 2}, "corner_m": 20.0, "street_depth": 30.0, "interior": False,
                  "gap_m": (0.8, 2.2), "setback_m": 3.0, "yards": True, "fallback": "port"},
    # industrial: warehouses, sheds and old factory halls with a yard or a driveway between them; the inside of a
    # big block is built too (a second row reached by its own lane), what is left is paved yard
    "industrial": {"tiers": [{"units": ["@warehouse"], "street": 0.9, "avenue": 0.75, "max": 6},
                             {"units": ROWS, "street": 0.1, "avenue": 0.25, "max": 6}],
                   "corner": {"street": 0, "avenue": 0}, "corner_m": 0.0, "street_depth": 80.0, "interior": True,
                   "gap_m": (2.5, 7.0), "setback_m": 2.0, "fallback": "port"},
    # chinatown: the Oriental quarter of the campaign (Op 09): walk-up rows wall to wall on every front, more
    # mid-rises than the old port district, mid-rises on the corners, paved courts behind
    "chinatown": {"tiers": [{"units": SMALL_MIDRISES, "street": 0.25, "avenue": 0.5, "max": 3},
                            {"units": ROWS, "street": 0.75, "avenue": 0.5, "max": 40}],
                  "corner": {"street": 0, "avenue": 0}, "corner_m": 30.0, "street_depth": 40.0, "interior": False},
}
NARROW_HOUSE_M = 10.0       # "@house_narrow": a house whose frontage is at most this wide (a cottage)


def expand(names, units):
    """A tier's model names with "@kind" turned into every unit of that kind (extra_units.json)."""
    out = []
    for n in names:
        if n == "@house_narrow":
            out += [u for u in units if units[u].get("kind") == "house"
                    and min(units[u]["ue_hi"][0] - units[u]["ue_lo"][0], units[u]["ue_hi"][1] - units[u]["ue_lo"][1]) <= NARROW_HOUSE_M]
        elif n.startswith("@"):
            out += sorted(u for u in units if units[u].get("kind") == n[1:])
        else:
            out.append(n)
    return out


def load_units():
    units = {}
    for path in (os.path.join(PROJECT, "Saved", "CityMap", "building_units.json"), os.path.join(DATA, "tower_units.json"),
                 os.path.join(DATA, "extra_units.json")):
        if os.path.exists(path):
            with open(path) as f:
                for u in json.load(f):
                    units[u["name"]] = u
    return units


def inside(poly, x, y):
    return cv2.pointPolygonTest(poly, (float(x), float(y)), True)


def rect_corners(cx, cy, w, d, ux, uy):
    """Corners of a w x d rectangle centred at (cx, cy) whose w runs along the unit vector (ux, uy)."""
    vx, vy = -uy, ux
    return [(cx + sx * w / 2 * ux + sy * d / 2 * vx, cy + sx * w / 2 * uy + sy * d / 2 * vy)
            for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def rects_clear(a, b, gap):
    """True when two rectangles (corner lists) are at least `gap` apart: separating-axis test on padded boxes."""
    for poly in (a, b):
        for i in range(4):
            ex, ey = poly[(i + 1) % 4][0] - poly[i][0], poly[(i + 1) % 4][1] - poly[i][1]
            n = math.hypot(ex, ey) or 1.0
            ax, ay = -ey / n, ex / n
            pa = [p[0] * ax + p[1] * ay for p in a]
            pb = [p[0] * ax + p[1] * ay for p in b]
            if max(pa) + gap <= min(pb) or max(pb) + gap <= min(pa):
                return True
    return False


def rare_taken(name, cx, cy):
    """The distinctive models (RARE_UNITS) another sector already has within RARE_RADIUS_M of (cx, cy)."""
    taken = set()
    for path in glob.glob(os.path.join(DATA, "sectors", "*", "lots.json")):
        if os.path.basename(os.path.dirname(path)) == name:
            continue
        with open(path) as f:
            for b in json.load(f).get("buildings", []):
                if b.get("unit") in RARE_UNITS and math.hypot(b["x"] - cx, b["y"] - cy) <= RARE_RADIUS_M:
                    taken.add(b["unit"])
    return taken


def main():
    name = sys.argv[1]
    sector = SECTORS[name]
    max_height = float(sector.get("max_height_m", 1e9))
    folder = os.path.join(DATA, "sectors", name)
    with open(os.path.join(folder, "blocks.json")) as f:
        blocks = json.load(f)["blocks"]
    units = load_units()
    faces_path = os.path.join(DATA, "unit_faces.json")
    faces = load_json("unit_faces.json") if os.path.exists(faces_path) else {}
    rng = random.Random(SEED + sum(ord(c) for c in name))
    district = DISTRICTS[sector["district"]]
    first_tier = expand(district["tiers"][0]["units"], units)
    if district.get("fallback") and not any(n in units for n in first_tier):
        print("LOTS %s: no %s models in the project; building it as %s" % (name, sector["district"], district["fallback"]))
        district = DISTRICTS[district["fallback"]]
    tiers = []
    for t in district["tiers"]:
        tiers.append(dict(t, units=[units[n] for n in expand(t["units"], units) if n in units]))
    if not any(t["units"] for t in tiers):
        print("LOTS %s: no merged building units found" % name)
        return
    cap = {u["name"]: t["max"] for t in reversed(tiers) for u in t["units"]}      # a model in two tiers takes the first's
    west, east, south, north = sector["box"]
    for unit in rare_taken(name, (west + east) / 2.0, (south + north) / 2.0):
        cap[unit] = 0                                                  # one is built nearby already
    cut = sectors.outline(name)
    open_zones = [np.array(ring, dtype=np.float32).reshape(-1, 1, 2)
                  for ring in sector.get("open", []) + sector.get("plazas", [])]

    # the ground under each building, and which frontages are on an avenue
    net = load_json("network.json")
    roads = roadgeom.sector_roads(net, sector["box"])
    field = roadgeom.HeightField(roads, levels=sectors.levels(name, net))
    base_ground = np.load(os.path.join(DATA, "terrain_base.npz"))["ground"]
    mesh_ground = groundmesh.GroundMesh(name)

    def pick_side(u, swap):
        """0 or 180: the turn that shows the model's richer facade to the street, when one clearly is."""
        f = faces.get(u["name"])
        if not f:
            return rng.choice((0.0, 180.0))
        front, back = (f["+x"], f["-x"]) if swap else (f["+y"], f["-y"])       # the side facing the street at flip 0, 180
        if abs(front - back) < 0.08 * max(front, back, 1):
            return rng.choice((0.0, 180.0))
        return 0.0 if front > back else 180.0

    def facing(mx, my):
        """What a block side looks onto: "avenue", "street", "alley", or "walk" (a promenade or a square)."""
        best, cls = 1e9, None
        for r in roads:
            d = float(np.min(np.hypot(r.xy[:, 0] - mx, r.xy[:, 1] - my))) - r.half - r.sidewalk
            if d < best:
                best, cls = d, r.cls
        if best > 6.0:
            return "walk"
        return "avenue" if cls in AVENUES else "alley" if cls == "alley" else "street"

    def ccw(ring):
        area = sum(ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1] for i in range(len(ring)))
        return ring if area > 0 else ring[::-1]

    def buildable_parts(outline):
        """The block without its open areas, as one or more polygons (metres). A side left by an open area is
        a frontage like any other: buildings line a promenade or a square as they line a street."""
        if not open_rings:
            return [outline]
        x0, y0 = float(outline[:, 0].min()) - 2.0, float(outline[:, 1].max()) + 2.0
        w = int((float(outline[:, 0].max()) + 2.0 - x0) / PART_CELL_M) + 1
        h = int((y0 - float(outline[:, 1].min()) + 2.0) / PART_CELL_M) + 1

        def to_px(ring):
            p = np.asarray(ring, dtype=np.float64)
            return np.stack([(p[:, 0] - x0) / PART_CELL_M, (y0 - p[:, 1]) / PART_CELL_M], axis=1).round().astype(np.int32)

        mask = np.zeros((h, w), np.uint8)
        cv2.fillPoly(mask, [to_px(outline)], 1)
        gone = np.zeros((h, w), np.uint8)
        for ring in open_rings:
            cv2.fillPoly(gone, [to_px(ring)], 1)
        if not (gone & mask).any():
            return [outline]
        k = int(round(0.5 / PART_CELL_M)) * 2 + 1
        mask[cv2.dilate(gone, np.ones((k, k), np.uint8)) > 0] = 0
        parts = []
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        for c in contours:
            if len(c) < 3 or cv2.contourArea(c) * PART_CELL_M * PART_CELL_M < 300.0:
                continue
            ring = np.array([(x0 + px * PART_CELL_M, y0 - py * PART_CELL_M) for px, py in c[:, 0, :]], dtype=np.float32)
            parts.append(ring)
        return parts

    # (the open ramps of the tunnels, with 4 m of walk beside their parapets, are kept clear like any open area; so
    # is the footprint of every viaduct, with 4 m beside its barriers)
    ramps = [ring for _, ring in structures.void_rings(net, 4.0) + structures.viaduct_rings(net, 4.0)
             if max(p[0] for p in ring) > west and min(p[0] for p in ring) < east and max(p[1] for p in ring) > south and min(p[1] for p in ring) < north]
    open_rings = sector.get("open", []) + sector.get("plazas", []) + ramps
    open_zones += [np.array(ring, dtype=np.float32).reshape(-1, 1, 2) for ring in ramps]
    buildings, instances, collision, podiums = [], {}, [], []
    used_count = {}

    def floor_under(corners, cx, cy):
        """Where a building's floor goes and what the ground does under its footprint (the sector's mesh, probed
        at the corners, the edge middles and the centre). The front is the side between the first two corners.
        Returns (floor, drop, rise, front_step), in metres:
          floor       5 cm under the lowest ground along the front: the door is on its street
          drop        how far the ground falls below that behind the front (a podium fills the difference)
          rise        how far it stands above it behind the front (the building is cut into the hill)
          front_step  how much the ground differs along the front (how deep the door sinks at its high end)"""
        spots = corners + [(cx, cy)] + [((corners[i][0] + corners[(i + 1) % 4][0]) / 2, (corners[i][1] + corners[(i + 1) % 4][1]) / 2)
                                        for i in range(4)]
        field_z = roadgeom.ground_heights(field, spots, base_ground) + CURB_M
        under = np.array([h if h is not None else float(f) for h, f in ((mesh_ground.at(px, py), f) for (px, py), f in zip(spots, field_z))])
        front_low, front_high = float(min(under[0], under[1], under[5])), float(max(under[0], under[1], under[5]))
        return front_low - SINK_M, front_low - float(under.min()), float(under.max()) - front_low, front_high - front_low

    # landmarks first: buildings with a place of their own (a city hall), which everything else keeps clear of
    fixed = []
    for unit_name, (lx, ly), yaw, scale in sector.get("landmarks", []):
        u = units.get(unit_name)
        if not u:
            print("LOTS %s: landmark %s is not merged yet" % (name, unit_name))
            continue
        fw, fd = (u["ue_hi"][0] - u["ue_lo"][0]) * scale, (u["ue_hi"][1] - u["ue_lo"][1]) * scale
        r = math.radians(yaw)
        ux, uy = math.cos(r), -math.sin(r)              # where the model's own x points (east, north) at this Unreal yaw
        corners = rect_corners(lx, ly, fw, fd, ux, uy)
        mx, my = (u["ue_lo"][0] + u["ue_hi"][0]) / 2, (u["ue_lo"][1] + u["ue_hi"][1]) / 2
        ox = (mx * math.cos(r) - my * math.sin(r)) * scale
        oy = (mx * math.sin(r) + my * math.cos(r)) * scale
        height = u["ue_hi"][2] * scale
        # (a landmark has no front here: it stands on the lowest ground under it, as its sector levelled it)
        floor, drop, rise, _ = floor_under(corners, lx, ly)
        z, slope = floor - drop, drop + rise
        for mesh in u["meshes"]:
            instances.setdefault(mesh, []).append([round(lx * 100 - ox * 100, 1), round(-ly * 100 - oy * 100, 1), round(z * 100, 1),
                                                   round(yaw % 360.0, 2), round(scale, 3)])
        collision.append([round(lx * 100, 1), round(-ly * 100, 1), round((z + height / 2) * 100, 1), round(yaw, 2),
                          round(fw * 100, 1), round(fd * 100, 1), round(height * 100, 1)])
        buildings.append({"unit": u["name"], "block": -1, "landmark": True, "x": round(float(lx), 2), "y": round(float(ly), 2), "z": round(z, 2),
                          "w": round(fw, 1), "d": round(fd, 1), "h": round(height, 1), "angle": round(-yaw, 2), "slope": round(slope, 2),
                          "corners": [[round(float(px), 2), round(float(py), 2)] for px, py in corners]})
        used_count[u["name"]] = used_count.get(u["name"], 0) + 1
        fixed.append(corners)
    # walls standing in the sector (its "barriers"): nothing is built through one
    for barrier in sector.get("barriers", []):
        if barrier.get("lift"):
            continue                        # a coping or a lintel: nothing of it stands on the ground
        half = float(barrier.get("width", 0.5)) / 2.0 + 0.5
        line = barrier["line"]
        for (ax, ay), (bx, by) in zip(line[:-1], line[1:]):
            run = math.hypot(bx - ax, by - ay)
            if run > 0.05:
                fixed.append(rect_corners((ax + bx) / 2.0, (ay + by) / 2.0, run + 2.0 * half, 2.0 * half, (bx - ax) / run, (by - ay) / run))
    cut_a = np.array(cut, dtype=np.float64)
    cut_b = np.roll(cut_a, -1, axis=0)

    def along_cut(a, b):
        """True when the stretch a-b runs along the sector's own cut. (It may span several of the cut's sides: an
        outline with a point every 16 m, so that its edge follows the ground, has 40 sides in a row on one line. Tested
        against one side at a time, 2026-11-18, such a stretch was a frontage: houses all along the sector's edge.)"""
        ab = cut_b - cut_a
        for k in range(7):
            p = np.array([a[0] + (b[0] - a[0]) * k / 6.0, a[1] + (b[1] - a[1]) * k / 6.0], dtype=np.float64)
            t = np.clip(((p - cut_a) * ab).sum(axis=1) / np.maximum((ab ** 2).sum(axis=1), 1e-12), 0.0, 1.0)
            if np.hypot(*(cut_a + ab * t[:, None] - p).T).min() > 0.8:
                return False
        return True

    order = {"avenue": 0, "street": 1, "walk": 2, "alley": 3}
    no_auto = [np.array(ring, dtype=np.float32).reshape(-1, 1, 2) for ring in sector.get("no_auto", [])]
    work = [(bi, part) for bi, block in enumerate(blocks) if block["area"] >= 900.0
            for part in buildable_parts(np.array([p[:2] for p in block["outline"]], dtype=np.float32))]
    for bi, outline in work:
        poly = np.array(ccw([tuple(p) for p in cv2.approxPolyDP(outline.reshape(-1, 1, 2), 1.0, True).reshape(-1, 2)]), dtype=np.float32)
        if len(poly) < 3:
            continue
        # frontages: straight sides long enough to build along, not on the sector's own cut
        sides = []
        front = ccw([tuple(p) for p in cv2.approxPolyDP(outline.reshape(-1, 1, 2), FRONTAGE_TOL_M, True).reshape(-1, 2)])
        for i in range(len(front)):
            a, b = np.array(front[i]), np.array(front[(i + 1) % len(front)])
            length = float(np.hypot(*(b - a)))
            looks_on = facing(float(a[0] + b[0]) / 2, float(a[1] + b[1]) / 2)
            # a side on the sector's own cut is no frontage, unless the cut runs along a street's property line
            # there (the street itself then belongs to the neighbouring sector)
            if length >= MIN_FRONTAGE_M and not (looks_on == "walk" and along_cut(a, b)):
                sides.append((length, a, b, looks_on))
        # no ordinary front where the sector builds by hand only (its "no_auto")
        sides = [s for s in sides if not any(inside(zone, float(s[1][0] + s[2][0]) / 2.0, float(s[1][1] + s[2][1]) / 2.0) >= 0.0
                                             for zone in no_auto)]
        # avenues first, so their buildings hold the corners; alleys last: a block turns its back on them
        sides.sort(key=lambda s: (order[s[3]], -s[0]))
        placed = []
        poly_cv = poly.reshape(-1, 1, 2).astype(np.float32)

        def fill_row(a, ux, uy, length, offset, street_row, kind, only=None, fixed_scale=None):
            """Sets buildings wall to wall along the line that starts at `a` and runs along (ux, uy), their
            fronts `offset` metres inside it. Returns how deep the row came out (0 when nothing fitted).
            `only`: the models of a rank, used in turn whatever the district's shares and caps say;
            `fixed_scale`: every building at this scale (a rank is uniform)."""
            nx, ny = -uy, ux                # the block's inside is on the left of a counter-clockwise outline
            s = 0.5
            first = True
            since_gap, next_gap = 0.0, rng.uniform(*PASSAGE_AFTER_M)
            deepest = 0.0
            shares = [t[kind] for t in tiers]
            while s < length - 6.0:
                pick = rng.random() * sum(shares)
                acc = 0.0
                tier = tiers[-1]
                for t, sh in zip(tiers, shares):
                    acc += sh
                    if pick <= acc and sh > 0:
                        tier = t
                        break
                # the two ends of a street front take the district's corner kind
                if street_row and (first or s > length - district["corner_m"]):
                    tier = tiers[district["corner"][kind]]
                pool = list(tier["units"])
                rng.shuffle(pool)
                pool.sort(key=lambda u: used_count.get(u["name"], 0))       # variety: least used first
                # when nothing of the chosen kind fits, fall back on the kinds allowed on this frontage, smallest last
                fallback = [u for t, sh in zip(tiers, shares) if sh > 0 for u in t["units"] if u not in pool]
                rng.shuffle(fallback)
                fallback.sort(key=lambda u: -(u["ue_hi"][0] - u["ue_lo"][0]) * (u["ue_hi"][1] - u["ue_lo"][1]))
                # a sector's "max_height_m": nothing taller (at the largest scale it may be built at), so that a
                # landmark keeps its place in the skyline (the Delegacia Central, sector CW1)
                candidates = [u for u in pool + fallback if used_count.get(u["name"], 0) < cap[u["name"]]
                              and u["ue_hi"][2] * SCALE[1] <= max_height]
                if only is not None:
                    candidates = sorted(only, key=lambda u: used_count.get(u["name"], 0))
                done = False
                # how deep the block is behind this spot (to its far side or to an open area), buildings aside
                room = 0.0
                while room < 60.0:
                    qx, qy = a[0] + ux * (s + 4.0) + nx * (offset + room + 2.0), a[1] + uy * (s + 4.0) + ny * (offset + room + 2.0)
                    if inside(poly_cv, qx, qy) < 0.3 or any(inside(zone, qx, qy) > -1.0 for zone in open_zones):
                        break
                    room += 2.0
                for u in candidates:
                    w0, d0 = u["ue_hi"][0] - u["ue_lo"][0], u["ue_hi"][1] - u["ue_lo"][1]
                    walkup = min(w0, d0) < 14.0 and max(w0, d0) > 2.5 * min(w0, d0)
                    if walkup:
                        # a walk-up on its own narrow lot: narrow end on the street. It lies along the street
                        # only where the block itself is too shallow for a lot (a strip by a quay) or the
                        # ground too steep for one (see below), never just because another building stands behind
                        narrow = w0 > d0
                        swaps = [narrow] if room >= max(w0, d0) * SCALE[0] else [narrow, not narrow]
                    else:
                        swaps = rng.sample((False, True), 2)
                    for swap in swaps:
                        fw, fd = (d0, w0) if swap else (w0, d0)
                        scale = rng.uniform(*SCALE) if fixed_scale is None else fixed_scale
                        fw, fd = fw * scale, fd * scale
                        if s + fw > length - 1.0 or (fd > MAX_DEPTH_M and fw <= MAX_DEPTH_M):
                            continue                    # a long building lies along its street, not across the block
                        if kind == "street" and fd > district["street_depth"]:
                            continue                    # on a side street lots are shallow: the block's middle stays yards
                        # the frontage is a straight line laid over a block side that may step or bow a little
                        # (a street that widens half way along): the front goes back to the real property line
                        push = 0.0
                        steps = max(2, int(fw / 3.0) + 1)
                        for i in range(steps):
                            t = 0.0
                            while t <= 7.0:
                                qx = a[0] + ux * (s + fw * i / (steps - 1)) + nx * (offset + t)
                                qy = a[1] + uy * (s + fw * i / (steps - 1)) + ny * (offset + t)
                                if inside(poly_cv, qx, qy) >= 0.3:
                                    break
                                t += 0.3
                            push = max(push, t)
                        if push > 7.0:
                            continue
                        cx = a[0] + ux * (s + fw / 2) + nx * (offset + push + fd / 2)
                        cy = a[1] + uy * (s + fw / 2) + ny * (offset + push + fd / 2)
                        corners = rect_corners(cx, cy, fw, fd, ux, uy)
                        # the whole footprint must lie in the block: probe it every few metres, so a street
                        # that cuts a notch into the block (a cul-de-sac) is never built over
                        na, nb = max(2, int(fw / 4.0) + 1), max(2, int(fd / 4.0) + 1)
                        probes = [(cx + (i / (na - 1) - 0.5) * fw * ux + (j / (nb - 1) - 0.5) * fd * nx,
                                   cy + (i / (na - 1) - 0.5) * fw * uy + (j / (nb - 1) - 0.5) * fd * ny)
                                  for i in range(na) for j in range(nb)]
                        if min(inside(poly_cv, px, py) for px, py in probes) < 0.3:
                            continue
                        if any(inside(zone, px, py) > -1.0 for zone in open_zones for px, py in probes + [(cx, cy)]):
                            continue                    # promenade, square or park: kept open
                        if not all(rects_clear(corners, other, CLEAR_M) for other in placed + fixed):
                            continue
                        # a building's floor is at its street: on the lowest ground along its front. Where the
                        # street climbs, a long front would be buried to its windows at the high end: only what
                        # has a nearly level front is placed, so smaller buildings step up the slope. Behind
                        # the front the ground may rise a storey (the back of the building is cut into the
                        # hill) or fall away, up to a storey and a bit: the building then stands on a podium,
                        # as houses on the downhill side of a hill street do
                        z, drop, rise, front_step = floor_under(corners, cx, cy)
                        slope = drop + rise
                        if front_step > MAX_STEP_M or rise > MAX_BACK_STEP_M or drop > MAX_PODIUM_M:
                            # a walk-up whose deep lot does not suit the slope may lie along the street instead
                            if walkup and only is None and swap == narrow and (not narrow) not in swaps:
                                swaps.append(not narrow)
                            continue
                        placed.append(corners)
                        used_count[u["name"]] = used_count.get(u["name"], 0) + 1
                        # Unreal yaw that lays the model's own x (or y, when swapped) along the frontage
                        theta = math.degrees(math.atan2(uy, ux))
                        flip = pick_side(u, swap)
                        yaw = (-theta + (90.0 if swap else 0.0) + flip) % 360.0
                        mx, my = (u["ue_lo"][0] + u["ue_hi"][0]) / 2, (u["ue_lo"][1] + u["ue_hi"][1]) / 2
                        r = math.radians(yaw)
                        ox = (mx * math.cos(r) - my * math.sin(r)) * scale
                        oy = (mx * math.sin(r) + my * math.cos(r)) * scale
                        height = u["ue_hi"][2] * scale
                        for mesh in u["meshes"]:
                            instances.setdefault(mesh, []).append([round(cx * 100 - ox * 100, 1), round(-cy * 100 - oy * 100, 1),
                                                                   round(z * 100, 1), round(yaw, 2), round(scale, 3)])
                        # the podium: a plain base under the whole footprint, from under the lowest ground up
                        # to the floor; the collision box reaches down with it
                        base = drop if drop > PODIUM_FROM_M else 0.0
                        if base > 0.0:
                            tall = base + PODIUM_INTO_GROUND_M
                            podiums.append([round(cx * 100, 1), round(-cy * 100, 1), round((z - tall / 2) * 100, 1), round(-theta, 2),
                                            round((fw - 0.1) * 100, 1), round((fd - 0.1) * 100, 1), round(tall * 100, 1)])
                        collision.append([round(cx * 100, 1), round(-cy * 100, 1), round((z + (height - base) / 2) * 100, 1), round(-theta, 2),
                                          round(fw * 100, 1), round(fd * 100, 1), round((height + base) * 100, 1)])
                        buildings.append({"unit": u["name"], "block": bi, "x": round(float(cx), 2), "y": round(float(cy), 2), "z": round(z, 2),
                                          "w": round(fw, 1), "d": round(fd, 1), "h": round(height, 1), "angle": round(theta, 2),
                                          "slope": round(slope, 2), "podium": round(base, 2),
                                          "corners": [[round(float(px), 2), round(float(py), 2)] for px, py in corners]})
                        deepest = max(deepest, fd)
                        since_gap += fw
                        if since_gap >= next_gap and only is None:      # (a rank is one unbroken front)
                            s += fw + rng.uniform(*PASSAGE_M)
                            since_gap, next_gap = 0.0, rng.uniform(*PASSAGE_AFTER_M)
                        else:
                            s += fw + rng.uniform(*district.get("gap_m", GAP_M))
                        done = True
                        break
                    if done:
                        break
                if not done:
                    s += 1.5            # creep along until a building fits snugly against what is already there
                first = False
            return deepest

        # ranks: where the sector sets buildings of one kind along a line of its own (barracks round a parade
        # ground: fronts on the line, bodies on its left), the block takes those and nothing else
        ranks_here = False
        for rank in sector.get("ranks", []):
            (ax, ay), (bx, by) = rank["line"]
            length = math.hypot(bx - ax, by - ay)
            ux, uy = (bx - ax) / length, (by - ay) / length
            steps = max(2, int(length / 2.0))
            if not any(inside(poly_cv, ax + ux * length * k / steps - uy * 2.0, ay + uy * length * k / steps + ux * 2.0) >= 0.3
                       for k in range(steps + 1)):
                continue
            ranks_here = True
            fill_row((float(ax), float(ay)), ux, uy, length, 0.0, False, "street",
                     only=[units[n] for n in rank["units"] if n in units], fixed_scale=float(rank.get("scale", 1.0)))
        if ranks_here and not no_auto:
            continue

        # first every street gets its front
        rows = []
        setback = float(district.get("setback_m", SETBACK_M))
        for length, a, b, looks_on in sides:
            kind = "avenue" if looks_on == "avenue" else "street"
            a = (float(a[0]), float(a[1]))
            ux, uy = (float(b[0]) - a[0]) / length, (float(b[1]) - a[1]) / length
            depth = fill_row(a, ux, uy, length, setback, True, kind)
            rows.append((length, a, ux, uy, setback + depth, kind))
        # ...then, downtown, the inside of a big block is built too: more rows behind its two longest frontages,
        # with a service lane between one row and the next. A downtown block is not a ring around an empty yard.
        if district["interior"]:
            built = [r for r in rows if r[4] > setback + 1.0]        # frontages that took buildings (not a promenade)
            for length, a, ux, uy, used, kind in sorted(built, key=lambda r: -r[0])[:2]:
                offset = used + LANE_M
                for _ in range(4):
                    depth = fill_row(a, ux, uy, length, offset, False, kind)
                    if depth <= 0.0:
                        break
                    offset += depth + LANE_M

    with open(os.path.join(folder, "lots.json"), "w") as f:
        json.dump({"sector": name, "buildings": buildings, "instances": instances, "collision": collision, "podiums": podiums}, f)
    # a plinth under every building whose model's walls stop short of the ground (added to the same file)
    plinths = plan_plinths.add(name, units)
    # gardens: in a district of walk-ups, what the buildings leave over inside the blocks (plan_yards.py writes
    # yards.json; sector_mesh.py has to run again to lay them)
    if district.get("yards") and sector.get("yards", True):
        lawns, lawn_area = plan_yards.add(name)
    else:
        plan_yards.clear(name)
        lawns, lawn_area = 0, 0.0

    # plan picture
    scale = 2.4
    w, h = int((east - west) * scale), int((north - south) * scale)
    img = np.full((h, w, 3), (235, 235, 235), np.uint8)

    def px(p):
        return [int(round((p[0] - west) * scale)), int(round((north - p[1]) * scale))]

    for block in blocks:
        cv2.fillPoly(img, [np.array([px(p) for p in block["outline"]], np.int32)], (190, 215, 195))
    for bld in buildings:
        shade = int(np.clip(230 - bld["h"] * 0.6, 40, 230))
        cv2.fillPoly(img, [np.array([px(p) for p in bld["corners"]], np.int32)], (shade, shade, min(255, shade + 25)))
        cv2.polylines(img, [np.array([px(p) for p in bld["corners"]], np.int32)], True, (40, 40, 40), 1, cv2.LINE_AA)
        c = px((bld["x"], bld["y"]))
        if min(bld["w"], bld["d"]) > 14.0:
            cv2.putText(img, "%.0f" % bld["h"], (c[0] - 10, c[1] + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 120), 1, cv2.LINE_AA)
    cv2.imwrite(os.path.join(folder, "lots.png"), img)
    heights = sorted(b["h"] for b in buildings)
    slopes = [b["slope"] for b in buildings]
    print("LOTS %s: %d buildings of %d models on %d blocks; heights %.0f .. %.0f m, median %.0f m; %d instanced meshes; "
          "ground under a building differs by up to %.2f m; %d plinths, %d podiums; %d gardens, %.0f m2" % (
              name, len(buildings), len(used_count), len(blocks), heights[0] if heights else 0, heights[-1] if heights else 0,
              heights[len(heights) // 2] if heights else 0, len(instances), max(slopes) if slopes else 0.0, plinths, len(podiums),
              lawns, lawn_area))


if __name__ == "__main__":
    main()
