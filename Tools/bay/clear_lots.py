"""Takes out of a sector's plan the buildings that stand on the site of a campaign place (sectors.PLACES), leaving
every other building where it is.

  python -P Tools/bay/clear_lots.py <sector> [<sector> ...]      (no names: every sector that has a place)
  then:  python -P Tools/bay/plan_yards.py <sector>              (a sector with gardens: the gardens follow)
         .\\Tools\\bay\\make_sector.ps1 -Sectors <sector> -KeepLots

Input:  Tools/bay/sectors.py                    PLACES: each place's site
        Saved/Bay/sectors/<sector>/lots.json    the buildings as planned (plan_lots.py)
        the unit lists (plan_plinths.load_units): which meshes make up each building
Output: Saved/Bay/sectors/<sector>/lots.json    the plan as it was before any place (lots_before_places.json, once it
                                                exists) without the buildings whose footprint comes within CLEAR_M of a
                                                site: their entry, their collision box and their row in each of
                                                their meshes' instance lists (seat_lots.py then makes the podiums
                                                and plinths again)
        Saved/Bay/sectors/<sector>/lots_before_places.json   the plan as it was, kept the first time only
        prints what went

Why not plan the sector again: plan_lots.py would lay out every block of the sector anew, and a sector that was
reviewed building by building would come back different everywhere. A place only needs its own lot.
"""
import json
import os
import shutil
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_plinths
import sectors
from common import DATA

CLEAR_M = 0.3               # a building this close to a place's site goes (the sites are drawn to their lots: a wider
                            # margin took the neighbours on both sides of the bank and the two houses behind the fire
                            # station)


def clear(name, units):
    path = os.path.join(DATA, "sectors", name, "lots.json")
    backup = os.path.join(DATA, "sectors", name, "lots_before_places.json")
    # always from the plan as it was before any place: run again after a site has moved, the buildings an earlier
    # run took out for the old site are back
    with open(backup if os.path.exists(backup) else path) as f:
        lots = json.load(f)
    sites = [(place, np.array(sectors.place_ring(place, CLEAR_M), dtype=np.float32).reshape(-1, 1, 2))
             for place, p in sectors.PLACES.items() if p["sector"] == name]
    seen, keep, keep_boxes, gone = {}, [], [], []
    drop_rows = {}                                      # mesh path -> rows of its instance list to drop
    for i, b in enumerate(lots["buildings"]):
        row = seen.get(b["unit"], 0)
        seen[b["unit"]] = row + 1
        corners = np.array(b["corners"], dtype=np.float32)
        hit = None
        for place, ring in sites:
            inside = any(cv2.pointPolygonTest(ring, (float(x), float(y)), False) >= 0 for x, y in corners) or \
                cv2.pointPolygonTest(ring, (float(b["x"]), float(b["y"])), False) >= 0
            # ...or the site's own corners inside the building (a site smaller than the building)
            inside = inside or any(cv2.pointPolygonTest(corners.reshape(-1, 1, 2), (float(x), float(y)), False) >= 0 for x, y in ring.reshape(-1, 2))
            if inside:
                hit = place
                break
        if hit is None:
            keep.append(b)
            keep_boxes.append(lots["collision"][i])
            continue
        gone.append((hit, b))
        for mesh_path in units[b["unit"]]["meshes"]:
            drop_rows.setdefault(mesh_path, set()).add(row)
    if not gone and not os.path.exists(backup):
        return 0, len(keep), []
    if not os.path.exists(backup):
        shutil.copyfile(path, backup)
    for mesh_path, rows in drop_rows.items():
        lots["instances"][mesh_path] = [t for k, t in enumerate(lots["instances"][mesh_path]) if k not in rows]
        if not lots["instances"][mesh_path]:
            del lots["instances"][mesh_path]
    lots["buildings"], lots["collision"] = keep, keep_boxes
    with open(path, "w") as f:
        json.dump(lots, f)
    return len(gone), len(keep), gone


def main():
    units = plan_plinths.load_units()
    names = sys.argv[1:] or sorted({p["sector"] for p in sectors.PLACES.values()})
    for name in names:
        count, left, gone = clear(name, units)
        what = ", ".join("%s %s at (%.0f, %.0f)" % (place, b["unit"].replace("BPP_", "").replace("_N1", ""), b["x"], b["y"]) for place, b in gone)
        print("CLEAR %s: %d buildings taken out, %d left%s" % (name, count, left, (": " + what) if what else ""))


if __name__ == "__main__":
    main()
