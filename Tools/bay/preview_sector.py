"""Draws a sector's ground mesh from above, coloured by surface kind, to check it before going into Unreal.

  python -P Tools/bay/preview_sector.py <sector> [pixels per metre, default 3]

Input:  Saved/Bay/sectors/<sector>/ground.npz and blocks.json (sector_mesh.py)
Output: Saved/Bay/sectors/<sector>/ground.png
"""
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA

COLOUR = {"road": (70, 70, 74), "white": (245, 245, 245), "yellow": (40, 200, 240), "curb": (150, 150, 150),
          "sidewalk": (196, 190, 180), "median": (120, 135, 120), "ground": (150, 185, 160), "park": (70, 150, 80), "yard": (95, 170, 95),
          "apron": (84, 84, 90), "wild": (110, 170, 195)}


def main():
    name = sys.argv[1]
    scale = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    folder = os.path.join(DATA, "sectors", name)
    d = np.load(os.path.join(folder, "ground.npz"))
    west, east, south, north = d["box"]
    pts, tris, kind, names = d["pts"], d["tris"], d["kind"], [str(n) for n in d["kind_names"]]
    S = 4                                    # supersampling, for clean thin lines
    w, h = int((east - west) * scale * S), int((north - south) * scale * S)
    img = np.zeros((h, w, 3), np.uint8)
    px = np.stack([(pts[:, 0] - west) * scale * S, (north - pts[:, 1]) * scale * S], axis=1)
    for k, kname in enumerate(names):
        sel = tris[kind == k]
        if len(sel):
            cv2.fillPoly(img, [px[t].round().astype(np.int32) for t in sel], COLOUR.get(kname, (200, 205, 215)))
    img = cv2.resize(img, (w // S, h // S), interpolation=cv2.INTER_AREA)
    blocks_path = os.path.join(folder, "blocks.json")
    if os.path.exists(blocks_path):
        for i, b in enumerate(json.load(open(blocks_path))["blocks"]):
            o = np.array(b["outline"])
            c = (int((o[:, 0].mean() - west) * scale), int((north - o[:, 1].mean()) * scale))
            cv2.putText(img, "B%d %.0f m2" % (i, b["area"]), (c[0] - 40, c[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 60, 20), 1, cv2.LINE_AA)
    cv2.imwrite(os.path.join(folder, "ground.png"), img)
    print("PREVIEW sector %s: %d triangles -> %s" % (name, len(tris), os.path.join(folder, "ground.png")))


if __name__ == "__main__":
    main()
