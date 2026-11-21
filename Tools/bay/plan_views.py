"""Cameras for reviewing one sector of the Bay city, in opposite pairs, and the player start.

  python -P Tools/bay/plan_views.py <sector>

Input:  Saved/Bay/network.json, Tools/bay/sectors.py
Output: Saved/Bay/sectors/<sector>/views.txt   one camera per line: name;x,y,z;lookX,lookY,lookZ (Unreal cm),
                                               the format -WSPC2Views reads
        Saved/Bay/start.json                   player start on a street of the sector

Every aerial and every street camera has a twin looking the opposite way, so nothing in a sector is only
ever seen from its good side. Take the pictures with:
  UnrealEditor.exe D:/Github/WSPC2/WSPC2.uproject /Game/Bay/Maps/WSPC2_Bay -game -RenderOffscreen -windowed
      -ResX=1280 -ResY=720 -unattended -nosound "-WSPC2Views=<views.txt>" "-abslog=<log>"
They land in Saved/Screenshots/Views; move them into the sector's own folder right after.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, load_json, save_json
from sectors import SECTORS


def ue(x, y, z):
    return x * 100.0, -y * 100.0, z * 100.0


def walk(pts, dist):
    """The point `dist` metres along a centre line (x, y, z samples) from its first point, with the street's own
    height there and the direction of travel: (x, y, z, tx, ty)."""
    run = 0.0
    for (ax, ay, az), (bx, by, bz) in zip(pts[:-1], pts[1:]):
        seg = math.hypot(bx - ax, by - ay)
        if seg > 1e-6 and run + seg >= dist:
            t = (dist - run) / seg
            return ax + (bx - ax) * t, ay + (by - ay) * t, az + (bz - az) * t, (bx - ax) / seg, (by - ay) / seg
        run += seg
    (ax, ay, _), (bx, by, bz) = pts[-2], pts[-1]
    seg = math.hypot(bx - ax, by - ay) or 1.0
    return bx, by, bz, (bx - ax) / seg, (by - ay) / seg


def length(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts[:-1], pts[1:]))


def main():
    name = sys.argv[1]
    west, east, south, north = SECTORS[name]["box"]
    cx, cy = (west + east) / 2, (south + north) / 2
    net = load_json("network.json")
    node = {n["id"]: n for n in net["nodes"]}
    inside = [n for n in net["nodes"] if west + 40 < n["x"] < east - 40 and south + 40 < n["y"] < north - 40]
    degree = {}
    for e in net["edges"]:
        degree[e["a"]] = degree.get(e["a"], 0) + 1
        degree[e["b"]] = degree.get(e["b"], 0) + 1
    ground = sum(n["z"] for n in inside) / max(len(inside), 1) if inside else 4.0
    span = max(east - west, north - south)

    views = []
    # aerials: from each corner towards the centre, and straight down
    for label, (dx, dy) in (("air_sw", (-1, -1)), ("air_ne", (1, 1)), ("air_nw", (-1, 1)), ("air_se", (1, -1))):
        cam = (cx + dx * span * 0.62, cy + dy * span * 0.62, ground + span * 0.42)
        views.append(("%s_%s" % (name, label), ue(*cam), ue(cx, cy, ground)))
    views.append(("%s_top" % name, ue(cx, cy - 1.0, ground + span * 1.15), ue(cx, cy, ground)))

    # street level: at the busiest junctions, looking along each pair of opposite arms. Every camera stands on a
    # street's own centre line, walked along it from the junction, at the street's own height there (2026-11-17:
    # they used to be put straight out from the junction at the junction's height, so on a curved street they
    # landed in a courtyard or inside a building, and on a hill under the asphalt)
    junctions = sorted((n for n in inside if degree.get(n["id"], 0) >= 3), key=lambda n: -degree[n["id"]])[:3]
    for k, n in enumerate(junctions):
        arms = []                                       # (centre line from the junction, its first direction)
        for e in net["edges"]:
            if e["level"] != 0 or e["cls"] == "tunnel" or n["id"] not in (e["a"], e["b"]):
                continue
            pts = e["pts"] if e["a"] == n["id"] else e["pts"][::-1]
            if length(pts) < 12.0:
                continue
            _, _, _, tx, ty = walk(pts, 6.0)
            arms.append((pts, (tx, ty)))
        if not arms:
            continue
        pts, d = max(arms, key=lambda a: length(a[0]))    # the longest arm: the most street to look along
        far = min(60.0, length(pts) - 4.0)
        # the same stretch of street from its two ends, eye height, each camera in its own right-hand lane:
        # "a" stands out on the arm and looks at the junction, "b" stands in the junction and looks back
        ax, ay, az, tx, ty = walk(pts, far)
        views.append(("%s_street%da" % (name, k + 1), ue(ax - ty * 2.0, ay + tx * 2.0, az + 1.7), ue(n["x"], n["y"], n["z"] + 1.2)))
        lx, ly, lz, _, _ = walk(pts, min(90.0, length(pts)))
        bx, by = n["x"] + d[0] * 2.0 + d[1] * 2.0, n["y"] + d[1] * 2.0 - d[0] * 2.0
        views.append(("%s_street%db" % (name, k + 1), ue(bx, by, n["z"] + 1.7), ue(lx, ly, lz + 1.2)))
        # and from above the cross street, from both of its sides, each camera over a real arm of the junction (a
        # carriageway: anywhere else it would be inside a building): the arm most across the first one, and the
        # arm opposite that (or else any other arm)
        others = [a for a in arms if a[0] is not pts] or arms
        c_pts, c_d = max(others, key=lambda a: abs(a[1][0] * d[1] - a[1][1] * d[0]))
        rest = [a for a in arms if a[0] is not c_pts]
        d_pts = min(rest, key=lambda a: a[1][0] * c_d[0] + a[1][1] * c_d[1])[0] if rest else c_pts
        for label, arm in (("c", c_pts), ("d", d_pts)):
            ux, uy, uz, _, _ = walk(arm, min(30.0, length(arm) - 3.0))
            views.append(("%s_corner%d%s" % (name, k + 1, label), ue(ux, uy, uz + 13.0), ue(n["x"], n["y"], n["z"])))

    # the sector's own cameras ("views" in sectors.py): places no junction camera shows, a quay or a square,
    # each given as a spot to stand on and a spot to look at; eye height above the ground there
    extra = SECTORS[name].get("views", [])
    if extra:
        import numpy as np
        import roadgeom
        from common import CURB_M
        import sectors
        field = roadgeom.HeightField(roadgeom.sector_roads(net, SECTORS[name]["box"]), levels=sectors.levels(name, net))
        base_ground = np.load(os.path.join(DATA, "terrain_base.npz"))["ground"]
        for label, cam, look in extra:
            zc, zl = roadgeom.ground_heights(field, [cam, look], base_ground) + CURB_M
            views.append(("%s_%s" % (name, label), ue(cam[0], cam[1], float(zc) + 1.7), ue(look[0], look[1], float(zl) + 1.4)))

    folder = os.path.join(DATA, "sectors", name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "views.txt"), "w") as f:
        for label, p, t in views:
            f.write("%s;%.0f,%.0f,%.0f;%.0f,%.0f,%.0f\n" % (label, p[0], p[1], p[2], t[0], t[1], t[2]))

    # the start spot: on a ground road out of the first junction that has one (a junction on a structure, such as
    # the Trevo Sul's elevated ring, has none)
    ground_starts = [(n, e) for n in junctions for e in net["edges"] if e["level"] == 0 and n["id"] in (e["a"], e["b"])]
    if ground_starts:
        n, e = ground_starts[0]
        pts = e["pts"] if e["a"] == n["id"] else e["pts"][::-1]
        p = pts[min(len(pts) - 1, 3)]
        q = pts[min(len(pts) - 1, 5)]
        yaw = math.degrees(math.atan2(-(q[1] - p[1]), q[0] - p[0]))          # Unreal y points south
        save_json("start.json", {"location": [p[0] * 100.0, -p[1] * 100.0, (p[2] + 1.2) * 100.0], "yaw": yaw})
    print("VIEWS %s: %d cameras (%d junctions) -> %s" % (name, len(views), len(junctions), os.path.join(folder, "views.txt")))


if __name__ == "__main__":
    main()
