"""Natural ground and water of the Bay city, before any road is laid on it.

  python -P Tools/bay/terrain_base.py

Input:  Saved/Bay/masks.npz, tint.npy (from read_map.py)
Output: Saved/Bay/terrain_base.npz   on the map's pixel grid (1.667 m):
            ground  float32  natural ground height in metres (land only; meaningless under water)
            water   bool     sea, bay, river and ponds, with the shore cleaned up
            quay    bool     shore pixels that face built-up land (they get a sea wall, not a beach)
        Saved/Bay/terrain_base.png   shaded relief for checking

How the height is found
  The map's tint gives the shape of the land; its brightness is distorted by the map's own hill shading and
  by the soft shadows around everything drawn on it. So the tint is only read well away from roads, buildings,
  labels and markers, spikes are filtered out, and the result is scaled hill by hill so that each named summit
  reaches the height the map lists for it.
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import PX_PER_M, data_path, fbm, fill_holes, gauss, to_pixel, world_grid

PLAIN_M = 4.0               # the coastal plain the city stands on
# name, listed height (m), marker dot (east, north in m), area it governs in km (west, east, south, north)
SPOTS = [
    ("Falesia Norte", 107.4, (-850, 1768), (-1.35, -0.25, 1.50, 2.15)),     # the bluff over the bay, not the range behind
    ("Encosta Sinuosa Norte", 44.4, (733, 2113), (0.30, 1.25, 1.75, 2.65)),
    ("Colina Oeste", 49.0, (-1393, -597), (-1.85, -0.85, -1.05, -0.15)),
    ("Plato Sudeste", 34.1, (1232, -973), (0.65, 2.00, -1.05, -0.40)),
    ("Crista Sul e Represa", 58.6, (1403, -1148), (0.60, 2.05, -1.60, -1.05)),
    ("Mirante Leste", 60.8, (3542, -478), (2.65, 4.45, -1.05, -0.15)),
]
# Built platforms: ground levelled at a height the map lists for a place, whatever the tint says there.
# name, height (m), outline (east, north in m), distance over which it eases back into the natural ground (m)
PADS = [
    # the city hall's terrace at the north end of the Ponte Central da Baia: "Prefeitura (+7,7 m ASL)"
    ("Prefeitura", 7.7, [(1698, 1482), (1834, 1482), (1834, 1650), (1698, 1650)], 45.0),
    # the old garrison (sector CC12): the ground inside its wall is one level yard; the natural ground climbs
    # 3.5 m across it towards the knoll on its east side, so outside the east wall a grass bank rises to the
    # street, as the glacis of a fort does. The ease is short: no street around the garrison is touched.
    ("Quartel Velho", 4.5, [(1974.0, 583.0), (2147.2, 583.0), (2147.2, 752.0), (1974.0, 752.0)], 14.0),
    # the north-east corner of the downtown quays (sectors CC14 and CC15): the drawing's shore steps in by 30 m
    # there and the quay is built square, on fill. Without this the river drive, laid over what the map has
    # as water, dips to 2.9 m at the corner
    ("Cais nordeste", 4.0, [(2283.0, 842.0), (2330.0, 842.0), (2330.0, 916.0), (2283.0, 916.0)], 12.0),
]
# Repairs: places where the tint cannot be read and the reading falls to the plain in the middle of high ground.
# The city blocks on top of the Plato Sudeste are drawn pale, with no relief tint at all, right where the map
# puts the plateau's own height marker (+34,1 m, on the street): read as drawn they are a pit 30 m deep and
# 350 m across, and every street around them dives into it. Inside each outline, ground lower than `floor` is
# thrown away and stretched again, like a membrane, between the ground left around it and the spot heights given.
# Only ground inside the outline changes.
# name, outline (east, north in m), floor (m), spot heights [(east, north, height in m), ...]
REPAIRS = [
    ("Plato Sudeste, topo", [(905.0, -858.0), (1365.0, -858.0), (1365.0, -1150.0), (905.0, -1150.0)], 31.0,
     [(1232.0, -973.0, 34.1)]),
]
REPAIR_SPOT_M = 12.0        # a spot height holds over this radius
BACKDROP_MAX_M = 140.0      # hills beyond the city keep the tint's shape up to this height
CLEAR_PX = 6                # the tint is trusted only this far from anything drawn over it


def ellipse(n):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (n, n))


def main():
    m = np.load(data_path("masks.npz"))
    tint = np.load(data_path("tint.npy"))
    h, w = tint.shape
    wx, wy = world_grid(h, w)

    # ---- water: roads drawn across it hide it; the stair-stepped shore is rounded off
    paved = m["street"] | m["avenue"] | m["bridge"]
    water = m["water"].copy()
    spans = cv2.morphologyEx(water.astype(np.uint8), cv2.MORPH_CLOSE, ellipse(61)).astype(bool)
    water |= spans & (paved | m["tunnel"]) & ~water
    built = (m["building"] | (paved & ~spans)).astype(np.float32)
    city_coast = np.clip(gauss(built, 25.0) * 6.0, 0.0, 1.0)
    natural = gauss(water, 14.0) + 0.16 * fbm((h, w), 150 * PX_PER_M, seed=7)
    straight = gauss(water, 5.0)
    shaped = (city_coast * straight + (1 - city_coast) * natural) > 0.5
    # never flood what is built, never dry out a bridge span
    on_land = cv2.dilate((m["building"] | (paved & ~spans)).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    water = (shaped & ~on_land) | (water & spans & paved)
    water = cv2.morphologyEx(water.astype(np.uint8), cv2.MORPH_OPEN, ellipse(5)).astype(bool)
    shore = water & ~cv2.erode(water.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    quay = shore & (city_coast > 0.5)

    # ---- tint: only where nothing is drawn nearby
    drawn = paved | m["tunnel"] | m["building"] | m["label"] | m["water"]
    for _, _, (dx, dy), _ in SPOTS:
        px, py = to_pixel(dx, dy)
        cv2.circle(drawn.view(np.uint8), (int(px), int(py)), 16, 1, -1)
    clear = cv2.distanceTransform((~drawn).astype(np.uint8), cv2.DIST_L2, 5) > CLEAR_PX
    known = clear & ~np.isnan(tint)
    t = fill_holes(np.nan_to_num(tint), known).astype(np.float32)
    # symbols and shadows leave pimples and pits a few pixels across: grey opening and closing remove them
    spot = ellipse(25)
    t = cv2.morphologyEx(cv2.morphologyEx(t, cv2.MORPH_OPEN, spot), cv2.MORPH_CLOSE, spot)
    t = gauss(t, 10.0)
    relief = np.maximum(t - PLAIN_M, 0.0)

    # ---- heights. Open country is read as drawn. A named hill is mostly hidden under streets and buildings,
    # so its reading comes out low: there the relief is scaled until the summit reaches the listed height.
    num = 0.06 * relief
    den = np.full_like(relief, 0.06)
    for name, top, (dx, dy), (x0, x1, y0, y1) in SPOTS:
        inside = (wx >= x0 * 1000) & (wx <= x1 * 1000) & (wy >= y0 * 1000) & (wy <= y1 * 1000)
        around = ((wx - dx) ** 2 + (wy - dy) ** 2 < 130.0 ** 2) & ~m["water"]
        summit = max(float(np.percentile(relief[around], 92)), 3.0)
        ratio = relief / summit
        ratio = np.where(ratio > 0.8, 0.8 + 0.2 * np.tanh((ratio - 0.8) / 0.2), ratio)   # rounded top, no mesa
        hill = (top - PLAIN_M) * ratio
        weight = gauss(inside, 60.0)
        num += weight * hill
        den += weight
        print("TERRAIN %-22s tint near marker %5.1f m -> %5.1f m (x%.2f)" % (name, summit + PLAIN_M, top, (top - PLAIN_M) / summit))
    ground = PLAIN_M + num / den
    ground = np.where(ground > 110.0, 110.0 + (BACKDROP_MAX_M - 110.0) * np.tanh((ground - 110.0) / (BACKDROP_MAX_M - 110.0)), ground)
    # the land meets the water as a bluff at most, never a wall
    shore_dist = cv2.distanceTransform((~water).astype(np.uint8), cv2.DIST_L2, 5) / PX_PER_M
    ground = np.minimum(ground, 1.2 + 0.8 * shore_dist)
    ground = gauss(ground, 4.0)
    # repairs: pits left by pale, unreadable ground on top of a hill are stretched over from their rims
    for name, outline, floor, spots in REPAIRS:
        mask = np.zeros((h, w), np.uint8)
        u, v = to_pixel(np.array([p[0] for p in outline]), np.array([p[1] for p in outline]))
        cv2.fillPoly(mask, [np.stack([u, v], axis=1).round().astype(np.int32)], 1)
        inside = cv2.erode(mask, np.ones((3, 3), np.uint8)) > 0
        low = (mask > 0) & (ground < floor) & ~water
        bad = cv2.dilate(low.astype(np.uint8), ellipse(9)).astype(bool) & inside        # the pit and the top of its sides
        at_rim = int((low & ~inside).sum())
        fixed, keep = ground.copy(), ~bad
        for x, y, z in spots:
            px, py = to_pixel(x, y)
            disc = np.zeros((h, w), np.uint8)
            cv2.circle(disc, (int(round(float(px))), int(round(float(py)))), int(round(REPAIR_SPOT_M * PX_PER_M)), 1, -1)
            fixed[disc > 0] = z
            keep |= disc > 0
        rows, cols = np.nonzero(mask)
        r0, r1, c0, c1 = max(rows.min() - 60, 0), min(rows.max() + 60, h), max(cols.min() - 60, 0), min(cols.max() + 60, w)
        window = (slice(r0, r1), slice(c0, c1))
        patch = fill_holes(fixed[window], keep[window])
        for _ in range(300):
            patch = np.where(keep[window], fixed[window], gauss(patch, 3.0))
        before = ground[window][bad[window]]
        ground[window] = patch
        print("TERRAIN repair %-22s %.0f m2 lifted from %.1f..%.1f m to %.1f..%.1f m%s" % (
            name, bad.sum() / PX_PER_M ** 2, before.min(), before.max(), patch[bad[window]].min(), patch[bad[window]].max(),
            ("; %d LOW PIXELS ON THE OUTLINE: the pit is wider than the outline" % at_rim) if at_rim else ""))
    # built platforms: level at their listed height, easing back into the natural ground around them. Put in
    # after the shore rule on purpose: a platform stands on its own walls right up to the water
    for name, top, outline, ease in PADS:
        mask = np.zeros((h, w), np.uint8)
        u, v = to_pixel(np.array([p[0] for p in outline]), np.array([p[1] for p in outline]))
        cv2.fillPoly(mask, [np.stack([u, v], axis=1).round().astype(np.int32)], 1)
        away = cv2.distanceTransform(1 - mask, cv2.DIST_L2, 5) / PX_PER_M
        t = np.clip(1.0 - away / ease, 0.0, 1.0)
        weight = t * t * (3 - 2 * t)
        ground = ground * (1 - weight) + top * weight
        # ...but only the platform itself stands on walls: around it the land still comes down to the water
        ground = np.where(mask > 0, ground, np.minimum(ground, 1.2 + 0.8 * shore_dist))
        print("TERRAIN pad %-18s %.1f m over %.0f m2" % (name, top, mask.sum() / PX_PER_M ** 2))

    np.savez_compressed(data_path("terrain_base.npz"), ground=ground.astype(np.float32), water=water, quay=quay)

    small = cv2.resize(np.where(water, -6.0, ground).astype(np.float32), (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    gy, gx = np.gradient(small, 2 / PX_PER_M)
    shade = np.clip(0.8 + (gx * -0.7 + gy * 0.7) * 1.6, 0.3, 1.35)
    norm = np.clip((small + 8) / 120.0, 0, 1)
    rgb = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_TURBO).astype(np.float32) * shade[:, :, None]
    cv2.imwrite(data_path("terrain_base.png"), np.clip(rgb, 0, 255).astype(np.uint8))
    land = ~water
    print("TERRAIN ground: p50 %.1f  p90 %.1f  p99 %.1f  max %.1f m; water %.2f km2; quay shore %.1f km" % (
        np.percentile(ground[land], 50), np.percentile(ground[land], 90), np.percentile(ground[land], 99),
        ground[land].max(), water.sum() / PX_PER_M ** 2 / 1e6, quay.sum() / PX_PER_M / 1000))


if __name__ == "__main__":
    main()
