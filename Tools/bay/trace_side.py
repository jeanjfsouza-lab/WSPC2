"""Prints a line that follows roads of the Bay network from junction to junction, for writing a sector's outline.

  python -P Tools/bay/trace_side.py "x,y x,y x,y ..." [--offset D] [--far]

Each "x,y" (metres, east/north) is taken as the junction nearest to it; consecutive junctions must be joined by
one road. Prints the points of the roads' built centre lines (the same smoothing the meshes use), as a Python
list ready to paste into Tools/bay/sectors.py.
  --offset D   the line D metres to the left of the direction of travel (negative: to the right)
  --far        instead of a number: half a metre behind the far (right-hand) property line of each road, the
               offset for a sector that builds a street whole (carriageway, both kerbs, both sidewalks)
Input: Saved/Bay/network.json. Output: text only.
"""
import argparse
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roadgeom
from common import load_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("points")
    ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--far", action="store_true")
    a = ap.parse_args()
    net = load_json("network.json")
    stops = []
    for token in a.points.split():
        x, y = (float(v) for v in token.split(","))
        node = min(net["nodes"], key=lambda n: math.hypot(n["x"] - x, n["y"] - y))
        stops.append(node)
    out = []
    for p, q in zip(stops[:-1], stops[1:]):
        edges = [e for e in net["edges"] if {e["a"], e["b"]} == {p["id"], q["id"]} and e["level"] == 0]
        if not edges:
            raise SystemExit("no road joins n%d (%.1f, %.1f) and n%d (%.1f, %.1f)" % (p["id"], p["x"], p["y"], q["id"], q["x"], q["y"]))
        edge = min(edges, key=lambda e: e["length"])
        road = roadgeom.Road(edge)
        d = a.offset
        if a.far:
            d = -(road.half + road.sidewalk + 0.5)
        forward = edge["a"] == p["id"]
        line = road.offset(d if forward else -d)
        line = line if forward else line[::-1]
        out += [(float(x), float(y)) for x, y in line]
        print("# n%d -> n%d: %s, %.1f m, offset %.2f" % (p["id"], q["id"], road.cls, road.length, d))
    keep = roadgeom.rdp(out, 0.12)
    tidy = [keep[0]]
    for pt in keep[1:]:
        if math.hypot(pt[0] - tidy[-1][0], pt[1] - tidy[-1][1]) > 0.05:
            tidy.append(pt)
    print("[" + ", ".join("(%.2f, %.2f)" % pt for pt in tidy) + "]")


if __name__ == "__main__":
    main()
