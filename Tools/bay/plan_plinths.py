"""Sets a plain plinth under every building of a sector whose model's walls stop short of the ground.

  python -P Tools/bay/plan_plinths.py <sector> [<sector> ...]      (plan_lots.py also calls it at its end)

Input:  Saved/Bay/sectors/<sector>/lots.json   the sector's buildings (plan_lots.py): only "instances" is read
        Saved/Bay/unit_skirts.json             where each model's walls start above the floor (unit_skirts.py)
        Saved/CityMap/building_units.json, Saved/Bay/tower_units.json   the models' sizes and meshes
Output: Saved/Bay/sectors/<sector>/lots.json   the same file with "plinths" added or replaced:
            [[x, y, z, yaw, sx, sy, sz], ...]  one box per building that needs one: centre and full size in
            Unreal cm, yaw in degrees (as "collision"). build_bay.py draws them (stage "buildings").

Why: the walk-up row models stand between neighbours on a sidewalk in the pack they come from. Their long
side walls start about a metre above the floor: at the free end of a row, or along a service lane, you see
under the building to the daylight on the other side. A plinth is what a real building has there anyway.

The box. It fills the model's footprint up to where the wall starts, plus 5 cm of overlap. On a side whose
wall stops short it stands 4 cm behind the wall's own plane (so it never fights with the wall for the same
pixels) and spans only the stretch where the wall is open; on a side whose wall reaches the ground it is
kept 60 cm inside that wall, out of sight. It goes 60 cm into the ground, since a building's floor may
stand a little above a lot that falls away.
Nothing is placed for a model that unit_skirts.py did not measure or found closed on every side.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, PROJECT

OPEN_SHARE = 0.30       # a side counts as open when the wall stops short over this share of its length...
OPEN_GAP_M = 0.45       # ...by at least this much
BEHIND_WALL_M = 0.04    # the plinth's face behind the wall's plane on an open side
HIDDEN_M = 0.60         # ...and inside the building on a side that needs none
INTO_GROUND_M = 0.60
OVERLAP_M = 0.05
SIDES = ("-x", "+x", "-y", "+y")


def load_units():
    units = {}
    for path in (os.path.join(PROJECT, "Saved", "CityMap", "building_units.json"), os.path.join(DATA, "tower_units.json")):
        if os.path.exists(path):
            with open(path) as f:
                for u in json.load(f):
                    units[u["name"]] = u
    return units


def model_box(unit, skirt):
    """The plinth of one model in its own axes (metres): (x0, x1, y0, y1, top), or None when it needs none."""
    open_sides = [s for s in SIDES if skirt[s]["open"] >= OPEN_SHARE and skirt[s]["gap"] >= OPEN_GAP_M]
    if not open_sides:
        return None
    lo, hi = unit["ue_lo"], unit["ue_hi"]
    # each face stands behind its side's wall plane (the wall may be well inside the bounding box: a stoop, a
    # fire escape or a cornice sticks out): just behind it on an open side, well inside on a closed one
    inset = {s: skirt[s].get("wall", 0.0) + (BEHIND_WALL_M if s in open_sides else HIDDEN_M) for s in SIDES}
    x0, x1 = lo[0] + inset["-x"], hi[0] - inset["+x"]
    y0, y1 = lo[1] + inset["-y"], hi[1] - inset["+y"]
    # along a side it only spans the stretch where the wall is open, half a metre more at each end
    spans = {"x": [(skirt[s]["from"], skirt[s]["to"]) for s in open_sides if s.endswith("y")],
             "y": [(skirt[s]["from"], skirt[s]["to"]) for s in open_sides if s.endswith("x")]}
    if spans["x"] and not spans["y"]:
        x0 = max(x0, lo[0] + min(a for a, _ in spans["x"]) - 0.5)
        x1 = min(x1, lo[0] + max(b for _, b in spans["x"]) + 0.5)
    if spans["y"] and not spans["x"]:
        y0 = max(y0, lo[1] + min(a for a, _ in spans["y"]) - 0.5)
        y1 = min(y1, lo[1] + max(b for _, b in spans["y"]) + 0.5)
    if x1 - x0 < 1.0 or y1 - y0 < 1.0:
        return None
    top = max(skirt[s]["gap"] for s in open_sides) + OVERLAP_M
    return x0, x1, y0, y1, top


def add(name, units=None, skirts=None):
    """Works out the plinths of one sector and writes them into its lots.json. Returns how many."""
    path = os.path.join(DATA, "sectors", name, "lots.json")
    skirts_path = os.path.join(DATA, "unit_skirts.json")
    if not os.path.exists(path):
        return 0
    with open(path) as f:
        lots = json.load(f)
    if skirts is None:
        skirts = json.load(open(skirts_path)) if os.path.exists(skirts_path) else {}
    units = units or load_units()
    first_mesh = {u["meshes"][0]: u for u in units.values() if u.get("meshes")}
    plinths = []
    for mesh, rows in lots.get("instances", {}).items():
        unit = first_mesh.get(mesh)                 # a building has one row per mesh: its first mesh counts it
        if unit is None or unit["name"] not in skirts:
            continue
        box = model_box(unit, skirts[unit["name"]])
        if box is None:
            continue
        x0, x1, y0, y1, top = box
        for x, y, z, yaw, scale in rows:            # the model's origin in Unreal cm, its yaw and scale
            r = math.radians(yaw)
            mx, my = (x0 + x1) / 2.0 * scale * 100.0, (y0 + y1) / 2.0 * scale * 100.0
            cx = x + mx * math.cos(r) - my * math.sin(r)
            cy = y + mx * math.sin(r) + my * math.cos(r)
            height = top * scale * 100.0 + INTO_GROUND_M * 100.0
            plinths.append([round(cx, 1), round(cy, 1), round(z - INTO_GROUND_M * 100.0 + height / 2.0, 1), round(yaw, 2),
                            round((x1 - x0) * scale * 100.0, 1), round((y1 - y0) * scale * 100.0, 1), round(height, 1)])
    lots["plinths"] = plinths
    with open(path, "w") as f:
        json.dump(lots, f)
    return len(plinths)


def main():
    units = load_units()
    for name in sys.argv[1:]:
        print("PLINTHS %s: %d" % (name, add(name, units)))


if __name__ == "__main__":
    main()
