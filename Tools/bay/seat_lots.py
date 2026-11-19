"""Sets a sector's buildings on its ground again, where they stand, after the ground mesh has changed.

  python -P Tools/bay/seat_lots.py <sector> [<sector> ...]

Input:  Saved/Bay/sectors/<sector>/lots.json    the buildings as planned (plan_lots.py)
        Saved/Bay/sectors/<sector>/ground.npz   the sector's mesh as it is now (sector_mesh.py)
        Saved/Bay/unit_skirts.json and the unit lists, for the plinths (plan_plinths.py)
Output: Saved/Bay/sectors/<sector>/lots.json    the same buildings at the same places, with new heights:
            buildings (z, slope, podium), instances (z), collision, podiums, plinths
            ...less the buildings the new ground no longer lets stand (see below)
        prints how far the floors moved, and what was taken out

Why: a block's ground is a triangulated surface, level only at its vertices' heights. Lay gardens in it
(plan_yards.py) and the mesh gains vertices inside the block, each at the height the terrain has there:
on a slope the surface under a building moves by up to some decimetres, and a building planned on the old
surface would float or stand buried. So a sector with gardens is made in this order: sector_mesh.py,
plan_lots.py, sector_mesh.py again, this script, plan_props.py. Run it too whenever a built sector's ground
is regenerated without planning its buildings again.

The rule is plan_lots.py's own: a building's floor is 5 cm under the lowest ground along its front (the side
between its first two corners); where the ground falls more than 30 cm below that behind the front it gets a
podium; a landmark stands on the lowest ground under it. A building with a probe off the mesh is left alone.

A building is taken out when the new ground stands more than MAX_BURIED_M above its floor somewhere under it, or
falls more than MAX_PODIUM_M below it: plan_lots.py would not have put it there (its limits are 5 m and 4 m; these
are a little wider, so that a garden's lawn moving the ground by a few decimetres removes nothing). It happens where
a sector's ground was redrawn after its buildings were planned: a seam along its side, a level pad for a campaign
place (57 buildings on 2026-11-18, one of them 19 m deep in a hillside). Landmarks are never taken out.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import groundmesh
import plan_plinths
from common import DATA

SINK_M = 0.05                   # as plan_lots.py
PODIUM_FROM_M = 0.3
PODIUM_INTO_GROUND_M = 0.6
MAX_BURIED_M = 5.5              # ground this far above the floor somewhere under a building: it is taken out
MAX_PODIUM_M = 6.0              # ground this far below the floor: likewise


def seat(name, units=None):
    """Reseats one sector. Returns (buildings, how many moved more than 2 cm, largest move in m, left alone)."""
    path = os.path.join(DATA, "sectors", name, "lots.json")
    with open(path) as f:
        lots = json.load(f)
    units = units or plan_plinths.load_units()
    mesh = groundmesh.GroundMesh(name)
    seen = {}                                   # unit -> how many of its buildings so far (its row in each mesh's list)
    podiums = []
    moved, worst, skipped = 0, 0.0, 0
    out = []                                    # (index, unit, row) of the buildings the ground no longer lets stand
    for i, b in enumerate(lots["buildings"]):
        row = seen.get(b["unit"], 0)
        seen[b["unit"]] = row + 1
        c = [tuple(p) for p in b["corners"]]
        spots = c + [(b["x"], b["y"])] + [((c[k][0] + c[(k + 1) % 4][0]) / 2, (c[k][1] + c[(k + 1) % 4][1]) / 2) for k in range(4)]
        under = [mesh.at(x, y) for x, y in spots]
        box = lots["collision"][i]
        height = b["h"]
        if any(h is None for h in under):
            skipped += 1
            if b.get("podium", 0.0) > 0.0:      # keep its podium as it was
                tall = b["podium"] + PODIUM_INTO_GROUND_M
                podiums.append([box[0], box[1], round((b["z"] - tall / 2) * 100, 1), box[3], box[4] - 10.0, box[5] - 10.0, round(tall * 100, 1)])
            continue
        low, high = min(under), max(under)
        if b.get("landmark"):
            z, base = low - SINK_M, 0.0
        else:
            front_low = min(under[0], under[1], under[5])
            z = front_low - SINK_M
            drop = front_low - low
            base = drop if drop > PODIUM_FROM_M else 0.0
            if high - z > MAX_BURIED_M or drop > MAX_PODIUM_M:
                out.append((i, b["unit"], row))
                continue
        shift = abs(z - b["z"])
        worst = max(worst, shift)
        moved += shift > 0.02
        b["z"], b["slope"] = round(z, 2), round(high - low, 2)
        if not b.get("landmark"):
            b["podium"] = round(base, 2)
        for mesh_path in units[b["unit"]]["meshes"]:
            lots["instances"][mesh_path][row][2] = round(z * 100, 1)
        box[2], box[6] = round((z + (height - base) / 2) * 100, 1), round((height + base) * 100, 1)
        if base > 0.0:
            tall = base + PODIUM_INTO_GROUND_M
            podiums.append([box[0], box[1], round((z - tall / 2) * 100, 1), box[3], box[4] - 10.0, box[5] - 10.0, round(tall * 100, 1)])
    if out:
        gone = {i for i, _, _ in out}
        lots["buildings"] = [b for i, b in enumerate(lots["buildings"]) if i not in gone]
        lots["collision"] = [c for i, c in enumerate(lots["collision"]) if i not in gone]
        rows_out = {}
        for _, unit, row in out:
            rows_out.setdefault(unit, set()).add(row)
        for unit, rows in rows_out.items():
            for mesh_path in units[unit]["meshes"]:
                kept = [t for k, t in enumerate(lots["instances"][mesh_path]) if k not in rows]
                if kept:
                    lots["instances"][mesh_path] = kept
                else:
                    del lots["instances"][mesh_path]
    lots["podiums"] = podiums
    with open(path, "w") as f:
        json.dump(lots, f)
    plan_plinths.add(name, units)               # the plinths follow their buildings
    return len(lots["buildings"]), moved, worst, skipped, len(out)


def main():
    units = plan_plinths.load_units()
    for name in sys.argv[1:]:
        count, moved, worst, skipped, out = seat(name, units)
        print("SEAT %s: %d buildings, %d moved (largest %.2f m), %d left alone (a probe off the mesh)%s" % (
            name, count, moved, worst, skipped, ", %d taken out (the ground too far above or below the floor)" % out if out else ""))


if __name__ == "__main__":
    main()
