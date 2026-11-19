"""Draws a window of the user's map with a road graph on top, enlarged, for working on one area.

  python -P Tools/bay/zoom_trace.py <west> <east> <south> <north> <out.png> [--net network_raw.json]
                                    [--zoom 3] [--marks user_marks_1.json] [--ids]

Window limits are in metres (east, north). Input: the map (ASSETS TO USE/city_gps_relief_map_v2.png) and a
graph in Saved/Bay. Output: a PNG with the centre lines coloured by kind, a 100 m grid with coordinates,
optionally node ids (--ids) and the user's correction marks (--marks, drawn green).
"""
import argparse
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import FX, FY, ROAD_COLOURS, SRC_MAP, data_path, load_json, to_pixel

COLOURS = {k: (c[2], c[1], c[0]) for k, c in ROAD_COLOURS.items()}      # OpenCV draws in B, G, R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("west", type=float)
    ap.add_argument("east", type=float)
    ap.add_argument("south", type=float)
    ap.add_argument("north", type=float)
    ap.add_argument("out")
    ap.add_argument("--net", default="network_raw.json")
    ap.add_argument("--zoom", type=float, default=3.0)
    ap.add_argument("--marks", default=None)
    ap.add_argument("--ids", action="store_true")
    a = ap.parse_args()

    page = cv2.imread(SRC_MAP, cv2.IMREAD_COLOR)
    px0, py0 = to_pixel(a.west, a.north)
    px1, py1 = to_pixel(a.east, a.south)
    x0, y0, x1, y1 = int(FX + px0), int(FY + py0), int(FX + px1), int(FY + py1)
    sub = page[max(0, y0):y1, max(0, x0):x1]
    vis = cv2.resize(sub, None, fx=a.zoom, fy=a.zoom, interpolation=cv2.INTER_CUBIC)
    vis = (vis.astype(np.float32) * 0.7 + 255 * 0.3).astype(np.uint8)

    def pt(x, y):
        px, py = to_pixel(x, y)
        return (FX + px - x0) * a.zoom, (FY + py - y0) * a.zoom

    step = 100.0 if (a.east - a.west) <= 1500 else 250.0
    gx = np.arange(np.ceil(a.west / step) * step, a.east, step)
    gy = np.arange(np.ceil(a.south / step) * step, a.north, step)
    for x in gx:
        u, _ = pt(x, a.north)
        cv2.line(vis, (int(u), 0), (int(u), vis.shape[0]), (255, 255, 255), 1)
        cv2.putText(vis, "%d" % x, (int(u) + 3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
    for y in gy:
        _, v = pt(a.west, y)
        cv2.line(vis, (0, int(v)), (vis.shape[1], int(v)), (255, 255, 255), 1)
        cv2.putText(vis, "%d" % y, (3, int(v) - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

    net = load_json(a.net)
    for e in net["edges"]:
        xs = np.array([p[0] for p in e["pts"]])
        ys = np.array([p[1] for p in e["pts"]])
        if xs.max() < a.west or xs.min() > a.east or ys.max() < a.south or ys.min() > a.north:
            continue
        u, v = pt(xs, ys)
        poly = np.stack([u, v], axis=1).round().astype(np.int32)
        kind = e.get("cls") or e.get("kind", "street")
        if e.get("level", 0) > 0:
            cv2.polylines(vis, [poly], False, (255, 255, 255), 9, cv2.LINE_AA)       # passes over other roads
        cv2.polylines(vis, [poly], False, COLOURS.get(kind, (0, 0, 0)), 3, cv2.LINE_AA)
    for n in net["nodes"]:
        if not (a.west <= n["x"] <= a.east and a.south <= n["y"] <= a.north):
            continue
        u, v = pt(n["x"], n["y"])
        c = (int(round(u)), int(round(v)))
        cv2.circle(vis, c, 4, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(vis, c, 4, (0, 0, 0), 1, cv2.LINE_AA)
        if a.ids:
            cv2.putText(vis, str(n["id"]), (c[0] + 5, c[1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 160), 1, cv2.LINE_AA)
    if a.marks:
        for m in load_json(a.marks):
            for x, y in m["pts"]:
                if a.west <= x <= a.east and a.south <= y <= a.north:
                    u, v = pt(x, y)
                    cv2.circle(vis, (int(u), int(v)), 6, (0, 200, 0), 1, cv2.LINE_AA)
    cv2.imwrite(a.out if os.path.isabs(a.out) else data_path(a.out), vis)
    print("ZOOM", a.out, vis.shape)


if __name__ == "__main__":
    main()
