"""Lets go of the held heights of built roads inside a polygon, for a change made on purpose to a road a sector has
already been built with (freeze.py holds every height sample between frozen junctions as built).

  python -P Tools/bay/unfreeze.py "x1,y1 x2,y2 x3,y3 ..." [why]

Input:  Saved/Bay/frozen_heights.json
Output: the same file without the samples inside the polygon (a copy of the old one is kept as
        frozen_heights.before_unfreeze.json). The junctions stay frozen where they are.
Then: design_network.py (the road is designed afresh there), make_sector.ps1 -Sectors <the sector> -KeepLots, a
build of that sector, a review, and freeze.py again, which holds the new heights.
Use: 2026-11-17, the Ponte Pensil's north head (NH1): its east arm had been built dipping to 7.4 m between the
roundabout's platform (10.5 m) and a junction held at 12.9 m by the coastal road's old arch; the coastal road became
a causeway at 4.5 m, and the arm had to come down to it.
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import data_path, load_json, save_json


def inside(poly, x, y):
    hit = False
    j = len(poly) - 1
    for i in range(len(poly)):
        (xi, yi), (xj, yj) = poly[i], poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            hit = not hit
        j = i
    return hit


def main():
    poly = [tuple(float(v) for v in p.split(",")) for p in sys.argv[1].split()]
    why = sys.argv[2] if len(sys.argv) > 2 else ""
    path = data_path("frozen_heights.json")
    heights = load_json("frozen_heights.json")
    shutil.copyfile(path, data_path("frozen_heights.before_unfreeze.json"))
    kept = [h for h in heights if not inside(poly, h[0], h[1])]
    save_json("frozen_heights.json", kept)
    print("UNFREEZE %d of %d held heights let go inside %s %s" % (len(heights) - len(kept), len(heights), poly, why))


main()
