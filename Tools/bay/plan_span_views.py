"""Cameras for reviewing one bridge of the Bay city, in opposite pairs.

  python -P Tools/bay/plan_span_views.py <structure>

Input:  Saved/Bay/structures/<name>/span.json (span_mesh.py)
Output: Saved/Bay/structures/<name>/views.txt   one camera per line: name;x,y,z;lookX,lookY,lookZ (Unreal cm),
                                                the format -WSPC2Views reads (see tour.ps1 -Structure)

Pairs: the whole bridge from the water on each side; from above each end looking along it; a driver's eye at
each abutment looking onto the deck, and at the crest looking each way; under the main span from each side;
and each abutment from the water, where the deck meets the land.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA


def ue(x, y, z):
    return x * 100.0, -y * 100.0, z * 100.0


def main():
    name = sys.argv[1]
    folder = os.path.join(DATA, "structures", name)
    with open(os.path.join(folder, "span.json")) as f:
        span = json.load(f)
    line = span["line"]                                   # points along the deck's axis, first to last
    first, last, mid = line[0], line[-1], line[len(line) // 2]
    ax, ay = last[0] - first[0], last[1] - first[1]
    run = math.hypot(ax, ay)
    ax, ay = ax / run, ay / run                           # along the bridge
    nx, ny = span["normal"]                               # left of that direction
    crest = max(line, key=lambda p: p[2])

    def along(p, d):
        return p[0] + ax * d, p[1] + ay * d

    views = []

    def add(label, cam, look):
        views.append(("%s_%s" % (name, label), ue(*cam), ue(*look)))

    # the whole bridge from the water, from each side
    for label, side in (("side_left", 1.0), ("side_right", -1.0)):
        add(label, (mid[0] + nx * side * run * 0.62, mid[1] + ny * side * run * 0.62, 38.0), (mid[0], mid[1], 12.0))
    # from above each end, looking along the bridge
    for label, p, d in (("air_first", first, -1.0), ("air_last", last, 1.0)):
        x, y = along(p, d * 150.0)
        add(label, (x + nx * 60.0 * d, y + ny * 60.0 * d, 95.0), (mid[0], mid[1], 10.0))
    # a driver's eye at each abutment, in the right-hand lane, looking onto the deck
    for label, p, d in (("drive_first", first, 1.0), ("drive_last", last, -1.0)):
        x, y = along(p, -d * 22.0)
        tx, ty = along(p, d * 120.0)
        add(label, (x - nx * 2.6 * d, y - ny * 2.6 * d, p[2] + 1.5), (tx - nx * 2.6 * d, ty - ny * 2.6 * d, p[2] + 6.0))
    # at the crest, looking each way
    for label, d in (("crest_to_last", 1.0), ("crest_to_first", -1.0)):
        tx, ty = along(crest, d * 150.0)
        add(label, (crest[0] - nx * 2.6 * d, crest[1] - ny * 2.6 * d, crest[2] + 1.5), (tx - nx * 2.6 * d, ty - ny * 2.6 * d, crest[2] - 6.0))
    # under the main span, from each side, low over the water
    for label, side in (("under_left", 1.0), ("under_right", -1.0)):
        add(label, (crest[0] + nx * side * 95.0 + ax * 70.0, crest[1] + ny * side * 95.0 + ay * 70.0, 5.0), (crest[0], crest[1], 14.0))
    # each abutment from the water: where the deck meets the land
    for label, p, d in (("abutment_first", first, 1.0), ("abutment_last", last, -1.0)):
        fx, fy = along(p, d * 30.0)
        add(label + "_a", (fx + nx * 70.0 + ax * d * 55.0, fy + ny * 70.0 + ay * d * 55.0, 14.0), (fx, fy, p[2] - 2.0))
        add(label + "_b", (fx - nx * 70.0 + ax * d * 55.0, fy - ny * 70.0 + ay * d * 55.0, 14.0), (fx, fy, p[2] - 2.0))

    with open(os.path.join(folder, "views.txt"), "w") as f:
        for label, p, t in views:
            f.write("%s;%.0f,%.0f,%.0f;%.0f,%.0f,%.0f\n" % (label, p[0], p[1], p[2], t[0], t[1], t[2]))
    print("VIEWS %s: %d cameras -> %s" % (name, len(views), os.path.join(folder, "views.txt")))


if __name__ == "__main__":
    main()
