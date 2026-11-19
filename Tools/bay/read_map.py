"""Reads the drawn map (second version) into class masks on its pixel grid.

  python -P Tools/bay/read_map.py

Input:  ASSETS TO USE/city_gps_relief_map_v2.png
Output: Saved/Bay/masks.npz      boolean masks (frame only): water, street, avenue, bridge, tunnel, building,
                                 label, land
        Saved/Bay/tint.npy       ground height estimate from the map's tint, metres (float32, NaN where hidden)
        Saved/Bay/buildings.json one box per drawn building: centre and size in metres, shade
        Saved/Bay/read_classes.png  picture of the classes, for checking

Symbols of this version of the map:
  white ribbon, dark grey edge          local street right-of-way
  pale yellow ribbon, orange edge       main avenue or coastal highway
  orange ribbon, brown edge             bridge, viaduct, elevated road
  dark blue dashes (light blue band)    tunnel
  grey box                              building
  blue                                  sea, bay, river
  green .. tan .. brown tint            ground height
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import FH, FW, FX, FY, PX_PER_M, SRC_MAP, X_LEFT, Y_TOP, data_path, save_json, to_world

# legend colour bar of the picture: 0 m at x = 1564, 12.77 px per metre, sampled along y = 3145
LEGEND_Y, LEGEND_X0, LEGEND_PX_PER_M, LEGEND_TOP_M = 3145, 1564, 12.77, 106.0


def ellipse(n):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (n, n))


def keep_big(mask, min_area):
    n, cc, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return keep[cc]


def remove_grid(img):
    """The map has a one-pixel, faint grid line every 0.5 km. Only that pixel line is repainted, from the
    pixels right beside it: a wider repair would wipe out narrow streets that run along a grid line."""
    out = img.copy()
    h, w, _ = img.shape
    for k in range(-6, 10):
        cx = int(round((k * 500.0 - X_LEFT) * PX_PER_M))
        if 2 <= cx < w - 2:
            out[:, cx] = ((img[:, cx - 1].astype(np.int32) + img[:, cx + 1]) // 2).astype(np.uint8)
        cy = int(round((Y_TOP - k * 500.0) * PX_PER_M))
        if 2 <= cy < h - 2:
            out[cy, :] = ((img[cy - 1, :].astype(np.int32) + img[cy + 1, :]) // 2).astype(np.uint8)
    return out


def main():
    page = cv2.imread(SRC_MAP, cv2.IMREAD_COLOR)[:, :, ::-1]
    img = remove_grid(page[FY:FY + FH, FX:FX + FW].copy())
    r, g, b = [img[:, :, i].astype(np.int32) for i in range(3)]
    vmax = np.maximum(np.maximum(r, g), b)
    vmin = np.minimum(np.minimum(r, g), b)
    sat = (vmax - vmin) / np.maximum(vmax, 1)

    # labels: dark navy or brown boxes with white text
    dark = vmax < 95
    label = cv2.morphologyEx(dark.astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (31, 31)))
    label = keep_big(cv2.dilate(label, np.ones((7, 7), np.uint8)) > 0, 900)

    # tunnel centre line: saturated dark blue dashes; joined into a line
    dash = (b > 130) & (r < 70) & (g > 55) & (g < 135) & ~label
    dash = cv2.morphologyEx(dash.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    tunnel = cv2.morphologyEx(dash, cv2.MORPH_CLOSE, ellipse(27)) > 0
    tunnel = keep_big(tunnel, 60)

    # water: clearly blue, large
    blue = ((b - r) > 30) & ~label          # the tunnel labels are navy boxes, not water
    water = cv2.morphologyEx(blue.astype(np.uint8), cv2.MORPH_OPEN, ellipse(9)) > 0
    water = keep_big(water, 4000)

    # streets (white) and avenues (pale yellow), each with its thin edge line
    # The fills are flat colours: avenue (252,240,180), bridge (248,200,104). The hills' tint comes close to
    # both, so the windows are tight and anything not joined to the road network is dropped further down.
    # street fill is white, a little greyer along its centre line and edges, never warmer than neutral
    # (the plain's own tint is a light grey-green with less blue than red, buildings are warm greys)
    white = (vmin >= 212) & (b >= g - 3) & (b >= r - 3) & ((vmax - vmin) <= 14) & ~label
    yellow = (r >= 244) & (g >= 230) & (g <= 247) & (b >= 164) & (b <= 192) & ~label
    # bridge decks come in several brightnesses of one orange: hue about 40 degrees, strongly saturated
    hue = 60.0 * (g - b) / np.maximum(r - b, 1)
    orange = (r >= g) & (g > b) & (hue >= 30) & (hue <= 48) & (sat >= 0.47) & (vmax >= 150) & ~label
    orange = cv2.morphologyEx(orange.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0   # deck lines
    orange = cv2.morphologyEx(orange.astype(np.uint8), cv2.MORPH_OPEN, ellipse(5)) > 0     # drop avenue edge lines
    orange = cv2.dilate(orange.astype(np.uint8), ellipse(5)) > 0
    yellow = cv2.morphologyEx((yellow & ~orange).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    yellow = cv2.morphologyEx(yellow, cv2.MORPH_CLOSE, ellipse(7)) > 0                     # lane lines inside
    yellow &= ~orange
    white = cv2.morphologyEx(white.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
    white &= ~yellow & ~orange

    # labels hide what is under them: carry straight roads and water across each label box
    n, cc, stats, _ = cv2.connectedComponentsWithStats(label.astype(np.uint8))
    hh, ww = label.shape
    for m in (water, white, yellow, orange):
        for k in range(1, n):
            x, y, bw, bh, _ = stats[k]
            x0, y0, x1, y1 = max(0, x - 2), max(0, y - 2), min(ww - 1, x + bw + 2), min(hh - 1, y + bh + 2)
            if x0 < 5 or x1 > ww - 6 or y0 < 5 or y1 > hh - 6:
                continue
            for row in range(y0, y1 + 1):
                if m[row, x0 - 4:x0 - 1].any() and m[row, x1 + 1:x1 + 4].any():
                    m[row, x0:x1 + 1] = True
            for col in range(x0, x1 + 1):
                if m[y0 - 4:y0 - 1, col].any() and m[y1 + 1:y1 + 4, col].any():
                    m[y0:y1 + 1, col] = True

    # one road network: keep what touches its largest piece (the map's network is a single component)
    net = cv2.dilate((white | yellow | orange | tunnel).astype(np.uint8), ellipse(9))
    n, cc, stats, _ = cv2.connectedComponentsWithStats(net)
    main = cc == (1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA])))
    dropped = [(int(stats[k, cv2.CC_STAT_AREA]), int(stats[k, 0]), int(stats[k, 1])) for k in range(1, n)
               if stats[k, cv2.CC_STAT_AREA] > 1500 and not main[stats[k, 1] + stats[k, 3] // 2, stats[k, 0] + stats[k, 2] // 2]]
    print("READ pieces not joined to the network (area px, x, y):", sorted(dropped, reverse=True)[:12])
    white &= main
    yellow &= main
    orange &= main
    tunnel &= main

    # buildings: near-neutral grey boxes
    paved = white | yellow | orange
    fill = (r >= g - 2) & (sat <= 0.14) & (vmax >= 150) & (vmax <= 222) & ~label & ~water & ~paved
    fill = cv2.morphologyEx(fill.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, cc, stats, _ = cv2.connectedComponentsWithStats(fill)
    building = np.zeros_like(white)
    boxes = []
    for k in range(1, n):
        x, y, w, h, area = stats[k]
        if area < 12 or w < 4 or h < 4 or area < 0.5 * w * h:
            continue
        building[y:y + h, x:x + w] |= cc[y:y + h, x:x + w] == k
        cx, cy = to_world(x + w / 2.0, y + h / 2.0)
        boxes.append({"centre": [round(float(cx), 1), round(float(cy), 1)],
                      "size": [round(w / PX_PER_M, 1), round(h / PX_PER_M, 1)],
                      "shade": round(float(vmax[cc == k].mean()), 1)})
    building = cv2.dilate(building.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0

    # ground height from the tint (colour direction against the legend bar)
    xs = np.arange(LEGEND_X0, LEGEND_X0 + int(LEGEND_TOP_M * LEGEND_PX_PER_M))
    lut_rgb = page[LEGEND_Y - 2:LEGEND_Y + 3, xs].astype(np.float32).mean(axis=0)
    lut_h = (xs - LEGEND_X0) / LEGEND_PX_PER_M
    hidden = water | paved | tunnel | building | label
    land = cv2.erode((~hidden).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    packed = (r << 16) | (g << 8) | b
    colours, inverse = np.unique(packed[land], return_inverse=True)
    crgb = np.stack([(colours >> 16) & 255, (colours >> 8) & 255, colours & 255], axis=1).astype(np.float32)
    lut = lut_rgb / np.linalg.norm(lut_rgb, axis=1, keepdims=True)
    best = np.empty(len(crgb), np.float32)
    for start in range(0, len(crgb), 20000):
        part = crgb[start:start + 20000]
        unit = part / np.maximum(np.linalg.norm(part, axis=1, keepdims=True), 1e-3)
        best[start:start + 20000] = lut_h[np.argmax(unit @ lut.T, axis=1)]
    tint = np.full(land.shape, np.nan, np.float32)
    tint[land] = best[inverse]
    tint[water] = 0.0

    np.savez_compressed(data_path("masks.npz"), water=water, street=white, avenue=yellow, bridge=orange,
                        tunnel=tunnel, building=building, label=label, land=land)
    np.save(data_path("tint.npy"), tint)
    save_json("buildings.json", {"buildings": boxes})

    vis = np.zeros(img.shape, np.uint8)
    vis[:] = (200, 220, 190)
    for mask, colour in ((water, (120, 170, 215)), (building, (150, 150, 150)), (white, (255, 255, 255)),
                         (yellow, (250, 225, 90)), (orange, (240, 130, 20)), (tunnel, (20, 60, 200)),
                         (label, (160, 0, 60))):
        vis[mask] = colour
    cv2.imwrite(data_path("read_classes.png"), cv2.resize(vis[:, :, ::-1], (FW // 2, FH // 2), interpolation=cv2.INTER_AREA))
    cv2.imwrite(data_path("read_classes_full.png"), vis[:, :, ::-1])

    total = float(land.size)
    for name, mask in (("water", water), ("street", white), ("avenue", yellow), ("bridge", orange),
                       ("tunnel", tunnel), ("building", building), ("label", label)):
        print("READ %-9s %6.2f%% of the frame (%.2f km2)" % (name, 100 * mask.sum() / total, mask.sum() / PX_PER_M ** 2 / 1e6))
    print("READ buildings: %d boxes" % len(boxes))


if __name__ == "__main__":
    main()
