"""Prepares what the sector mesher cannot work out inside Blender: where the land ends.

  python -P Tools/bay/sector_prep.py <sector>

Input:  Saved/Bay/terrain_base.npz (water), Saved/Bay/network.json, Tools/bay/sectors.py
Output: Saved/Bay/sectors/<sector>/prep.json   {"land": [rings], "ponds": [rings]} in metres; a ring is a
                                               closed list of (x, y). Land rings are the outlines of dry
                                               ground, pond rings the water enclosed by it.
        Saved/Bay/sectors/<sector>/prep.png    picture of the result

The shore comes from the map's water, redrawn finer (0.5 m) and tidied so quays are straight runs with
clean corners. A street is never left hanging over the water: every right-of-way keeps at least
PROMENADE_M of ground beyond its sidewalk.
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roadgeom
import structures
from common import DATA, bilinear, data_path, load_json
from sectors import SECTORS

CELL_M = 0.5
MARGIN_M = 40.0
PROMENADE_M = 9.0
SIMPLIFY_M = 3.2            # coarse on purpose: a quay is built in straight runs


def main():
    name = sys.argv[1]
    west, east, south, north = SECTORS[name]["box"]
    x0, x1, y0, y1 = west - MARGIN_M, east + MARGIN_M, south - MARGIN_M, north + MARGIN_M
    w, h = int((x1 - x0) / CELL_M), int((y1 - y0) / CELL_M)
    xs = x0 + (np.arange(w) + 0.5) * CELL_M
    ys = y1 - (np.arange(h) + 0.5) * CELL_M
    gx, gy = np.meshgrid(xs, ys)
    water = np.load(data_path("terrain_base.npz"))["water"].astype(np.float32)
    wet = bilinear(water, gx.ravel(), gy.ravel()).reshape(h, w)
    wet = cv2.GaussianBlur(wet, (0, 0), 2.0) > 0.5

    def to_px(pts):
        p = np.asarray(pts, dtype=np.float64)
        return np.stack([(p[:, 0] - x0) / CELL_M, (y1 - p[:, 1]) / CELL_M], axis=1).round().astype(np.int32)

    # rights-of-way of the streets around here, with their promenade
    net = load_json("network.json")
    node_xy = {n["id"]: (n["x"], n["y"]) for n in net["nodes"]}
    roads = []
    for e in net["edges"]:
        if e["level"] != 0 or e["cls"] in ("tunnel", "bridge"):
            continue
        ex = [p[0] for p in e["pts"]]
        ey = [p[1] for p in e["pts"]]
        if max(ex) < x0 - 60 or min(ex) > x1 + 60 or max(ey) < y0 - 60 or min(ey) > y1 + 60:
            continue
        roads.append(roadgeom.Road(e))
    row = np.zeros((h, w), np.uint8)
    for kind, pts, _ in roadgeom.street_polygons(roads, node_xy):
        if kind in ("road", "curb", "sidewalk"):
            cv2.fillPoly(row, [to_px(pts)], 1)
    k = int(round(PROMENADE_M / CELL_M)) * 2 + 1
    row = cv2.dilate(row, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    land = (~wet) | (row > 0)
    # crumbs of land or water a few metres across are noise from the map's pixels
    land = cv2.morphologyEx(land.astype(np.uint8), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    land = cv2.morphologyEx(land, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    # the sector's own shore design overrides the map: straight quays, piers
    for ring in SECTORS[name].get("water", []):
        cv2.fillPoly(land, [to_px(ring)], 0)
    for ring in SECTORS[name].get("fill", []):
        cv2.fillPoly(land, [to_px(ring)], 1)
    # a bridge's abutment is ground too: a platform square to the bridge, reaching out past the sea wall
    for _, ring in structures.platform_rings(net):
        if max(p[0] for p in ring) > x0 and min(p[0] for p in ring) < x1 and max(p[1] for p in ring) > y0 and min(p[1] for p in ring) < y1:
            cv2.fillPoly(land, [to_px(ring)], 1)

    contours, hierarchy = cv2.findContours(land, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    rings = {"land": [], "ponds": []}
    for c, hier in zip(contours, hierarchy[0] if hierarchy is not None else []):
        if cv2.contourArea(c) * CELL_M * CELL_M < 40.0:
            continue
        # fine where the sector draws its own shore (those corners are exact), coarse along the map's shore
        designed = bool(SECTORS[name].get("water") or SECTORS[name].get("fill"))
        c = cv2.approxPolyDP(c, (0.6 if designed else SIMPLIFY_M) / CELL_M, True)[:, 0, :]
        if len(c) < 3:
            continue
        ring = [[round(float(x0 + (px + 0.5) * CELL_M), 2), round(float(y1 - (py + 0.5) * CELL_M), 2)] for px, py in c]
        rings["land" if hier[3] < 0 else "ponds"].append(ring)
    folder = os.path.join(DATA, "sectors", name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "prep.json"), "w") as f:
        import json
        json.dump(rings, f)

    vis = np.zeros((h, w, 3), np.uint8)
    vis[:] = (150, 110, 60)
    vis[land > 0] = (150, 185, 160)
    vis[row > 0] = (190, 190, 190)
    for kind, colour in (("land", (0, 0, 220)), ("ponds", (220, 0, 0))):
        for ring in rings[kind]:
            cv2.polylines(vis, [to_px(ring)], True, colour, 2, cv2.LINE_AA)
    cv2.rectangle(vis, tuple(to_px([(west, north)])[0]), tuple(to_px([(east, south)])[0]), (255, 255, 255), 1)
    cv2.imwrite(os.path.join(folder, "prep.png"), cv2.resize(vis, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
    print("PREP %s: %d land rings, %d pond rings; %.0f%% of the window is water" % (
        name, len(rings["land"]), len(rings["ponds"]), 100.0 * (1 - land.mean())))


if __name__ == "__main__":
    main()
