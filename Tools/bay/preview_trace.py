"""Draws a road graph over the user's map, for the user to check and correct.

  python -P Tools/bay/preview_trace.py [network json] [output png]

Input:  ASSETS TO USE/city_gps_relief_map_v2.png and a graph in Saved/Bay: network_raw.json (default, the map
        as traced) or network.json (after design_network.py).
Output: Saved/Bay/tracado_lido.png (default): the whole page at 1.5x, lightened, with the centre lines on top,
        coloured by traced kind or, when the graph has them, by road class. A road on a structure that passes
        over others (level 1) is drawn with a white casing. Yellow dot = dead end, white dot = junction.
        The page's own km ticks stay readable around the frame.
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import FX, FY, ROAD_COLOURS, ROAD_NAMES_PT, SRC_MAP, data_path, load_json, to_pixel

SCALE = 1.5
ORDER = ["alley", "street", "avenue", "arterial", "freeway", "tunnel", "bridge", "ramp"]


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "network_raw.json"
    out = sys.argv[2] if len(sys.argv) > 2 else data_path("tracado_lido.png")
    net = load_json(src)
    page = cv2.imread(SRC_MAP, cv2.IMREAD_COLOR)[:, :, ::-1]
    page = cv2.resize(page, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)
    vis = (page.astype(np.float32) * 0.62 + 255 * 0.38).astype(np.uint8)

    def pt(x, y):
        px, py = to_pixel(x, y)
        return (FX + px) * SCALE, (FY + py) * SCALE

    def poly(e):
        xs, ys = pt(np.array([p[0] for p in e["pts"]]), np.array([p[1] for p in e["pts"]]))
        return np.stack([xs, ys], axis=1).round().astype(np.int32)

    kind_of = lambda e: e.get("cls") or e["kind"]
    used = []
    degree = {}
    for e in net["edges"]:
        degree[e["a"]] = degree.get(e["a"], 0) + 1
        degree[e["b"]] = degree.get(e["b"], 0) + 1
    for kind in ORDER:
        some = [e for e in net["edges"] if kind_of(e) == kind and e.get("level", 0) <= 0]
        if some or any(kind_of(e) == kind for e in net["edges"]):
            used.append(kind)
        for e in some:
            cv2.polylines(vis, [poly(e)], False, ROAD_COLOURS[kind], 3, cv2.LINE_AA)
    for e in net["edges"]:                       # structures over other roads go on top, with a casing
        if e.get("level", 0) > 0:
            cv2.polylines(vis, [poly(e)], False, (255, 255, 255), 9, cv2.LINE_AA)
            cv2.polylines(vis, [poly(e)], False, ROAD_COLOURS[kind_of(e)], 4, cv2.LINE_AA)
    for n in net["nodes"]:
        x, y = pt(n["x"], n["y"])
        c = (int(round(x)), int(round(y)))
        if degree.get(n["id"], 0) == 1:
            cv2.circle(vis, c, 6, (255, 220, 0), -1, cv2.LINE_AA)
            cv2.circle(vis, c, 6, (0, 0, 0), 1, cv2.LINE_AA)
        else:
            cv2.circle(vis, c, 4, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(vis, c, 4, (0, 0, 0), 1, cv2.LINE_AA)

    img = Image.fromarray(vis)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arialbd.ttf", int(20 * SCALE))
    except OSError:
        font = ImageFont.load_default()
    x, y = int(2150 * SCALE), int(16 * SCALE)
    d.rectangle([x - 14, y - 8, int(4700 * SCALE), y + int(44 * SCALE)], fill=(255, 255, 255), outline=(0, 0, 0))
    for kind in used:
        label = ROAD_NAMES_PT[kind]
        d.line([x, y + int(15 * SCALE), x + int(46 * SCALE), y + int(15 * SCALE)], fill=ROAD_COLOURS[kind], width=6)
        d.text((x + int(54 * SCALE), y), label, fill=(0, 0, 0), font=font)
        x += int((82 + 12.5 * len(label)) * SCALE)
    if any(e.get("level", 0) > 0 for e in net["edges"]):
        d.line([x, y + int(15 * SCALE), x + int(46 * SCALE), y + int(15 * SCALE)], fill=(160, 160, 160), width=12)
        d.line([x, y + int(15 * SCALE), x + int(46 * SCALE), y + int(15 * SCALE)], fill=(255, 255, 255), width=8)
        d.line([x, y + int(15 * SCALE), x + int(46 * SCALE), y + int(15 * SCALE)], fill=(0, 0, 0), width=3)
        d.text((x + int(54 * SCALE), y), "passa por cima", fill=(0, 0, 0), font=font)
        x += int(260 * SCALE)
    d.ellipse([x, y + int(5 * SCALE), x + int(20 * SCALE), y + int(25 * SCALE)], fill=(255, 220, 0), outline=(0, 0, 0))
    d.text((x + int(28 * SCALE), y), "fim de rua", fill=(0, 0, 0), font=font)
    img.save(out)
    print("PREVIEW %s: %d nodes, %d edges, %d dead ends -> %s" % (
        src, len(net["nodes"]), len(net["edges"]), sum(1 for v in degree.values() if v == 1), out))


if __name__ == "__main__":
    main()
