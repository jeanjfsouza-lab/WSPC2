"""Trees and shrubs of the country round the Bay city: the hills, hollows and shores that no sector covers.

  python -P Tools/bay/plan_country.py

Input:  Saved/Bay/landscape.json, landscape.r16, layer_*.raw (build_surface.py: the ground's height and its paint),
        Tools/bay/sectors.py (every sector's outline: inside them the sectors plant their own trees),
        Saved/Bay/sectors/<sector>/ground.npz of the sectors with natural ground ("wild": that ground is country too)
Output: Saved/Bay/country/trees.json   {"tiles": {"<tx>_<ty>": {"trees": {mesh: [[x, y, z, yaw, scale], ...]},
                                                              "bushes": {mesh: [...]}}}, "counts": {...}}
                                       positions in Unreal cm (x east, y south), tiles of TILE_M (build_bay.py stage
                                       "country" places one instanced actor per mesh and tile, so each tile culls on its own)
        Saved/Bay/country/country.png  the paint seen from afar (paint.png) with every tree and shrub as a dot, for checking

How. The paint already says where the ground is green and where it is dry (build_surface.py: green on slopes facing
north and east, in hollows and by the water; golden dry grass on sunny slopes and high ground; bare earth and scree
on steep faces). The vegetation follows it the way it does on the Bay Area's hills: groves of oaks in the hollows and
on the green slopes, a thin savanna of lone oaks over the golden grass, shrubs (coyote brush, chaparral) where green
and dry meet and on bare earth, nothing on scree, sand, water or pavement. A coarse noise gathers trees into groves
and leaves open meadows between them. Every cell of CELL_M gets at most one tree; positions are jittered inside it.
Nothing within EDGE_M of a sector's outline, nothing further than FRAME_PAD_M beyond the map's frame.
A sector's natural ground (its "wild") is planted by the same rule, from the same paint, each plant standing on the
sector's own mesh and WILD_EDGE_M clear of whatever else the sector has (kerbs, gardens, walls).
Every cell has its own random numbers (whether it grows something, where in the cell, which model, turned and sized
how), drawn for the whole grid at once: what grows in one cell does not depend on any other. (Until 2026-11-18 the
plants were drawn one after another from one sequence: repaint one hillside and every tree south of it changed place
and kind.)
"""
import json
import math
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import groundmesh
import sectors
from common import DATA, M_PER_PX, X_LEFT, Y_TOP, data_path, fbm

CELL_M = 8.0
TILE_M = 1000.0
EDGE_M = 6.0                # keep clear of a sector's outline (its kerbs, walls and own trees)
WILD_EDGE_M = 3             # on a sector's natural ground: keep this clear of its kerbs, gardens and walls (whole metres)
FRAME_PAD_M = 600.0         # how far beyond the map's frame the country is planted
SEED = 2026
CP = "/Game/CityPark/Meshes/Flora"
# oaks: the Amur cork trees' broad, low crowns read as coast live oaks; a few elms among them (larger index = larger tree)
TREES = [(CP + "/Trees/SM_AmurCork%02d" % i, 3.0) for i in range(8, 14)] + [(CP + "/Trees/SM_Elm%02d" % i, 1.0) for i in range(8, 12)]
BUSHES = [(CP + "/Bushs/SM_Bush%d_%02d" % (k, i), 1.0) for k, n in ((1, 5), (2, 5), (3, 3), (4, 4), (5, 4)) for i in range(1, n + 1)]
# per square metre, at full weight of the paint (before the grove noise)
TREE_GREEN = 1.0 / 260.0    # oak woodland in the hollows and on green slopes
TREE_DRY = 1.0 / 7000.0     # lone oaks over golden grass
BUSH_EDGE = 1.0 / 500.0     # shrubs where green and dry meet
BUSH_EARTH = 1.0 / 900.0    # chaparral on bare earth
BUSH_DRY = 1.0 / 5000.0
MAX_SLOPE = 0.62            # steeper than this: nothing grows (scree and cut faces)


def main():
    info = json.load(open(data_path("landscape.json")))
    vx, vy = info["vertices"]
    q = info["quad_m"]
    ox, oy = info["location_cm"][0] / 100.0, -info["location_cm"][1] / 100.0       # metres, north up
    z = (np.fromfile(data_path("landscape.r16"), np.uint16).reshape(vy, vx).astype(np.float32) - 32768.0) / 128.0
    paint = {n: np.fromfile(data_path("layer_%s.raw" % n), np.uint8).reshape(vy, vx).astype(np.float32) / 255.0
             for n in info["layers"]}
    k = int(round(CELL_M / q))                                     # landscape vertices per cell side
    ch, cw = (vy - 1) // k, (vx - 1) // k

    def cells(a):
        return a[:ch * k, :cw * k].reshape(ch, k, cw, k).mean(axis=(1, 3))

    zc = cells(z)
    green, dry = cells(paint["Grass"]), cells(paint["DryGrass"])
    earth, rock, sand = cells(paint["Dirt"]), cells(paint["Rock"]), cells(paint["Sand"])
    paved = cells(paint["Asphalt"] + paint["Pavement"])
    gy, gx = np.gradient(zc, CELL_M)
    slope = np.sqrt(gx * gx + gy * gy)
    # cell centres in metres
    cx = ox + (np.arange(cw) * k + k / 2.0) * q
    cy = oy - (np.arange(ch) * k + k / 2.0) * q

    # where nothing is planted: inside (or right beside) any sector, beyond the frame's pad
    blocked = np.zeros((ch, cw), np.uint8)
    for name, spec in sectors.SECTORS.items():
        # every sector, also those given only a box (CC1, CC5, CC17: 2026-11-17, skipping them planted 351 trees in
        # the middle of downtown)
        ring = np.array(sectors.outline(name), np.float64)
        pts = np.stack([(ring[:, 0] - ox) / CELL_M - 0.5, (oy - ring[:, 1]) / CELL_M - 0.5], axis=1)
        cv2.fillPoly(blocked, [np.round(pts).astype(np.int32)], 1)
    grow = max(1, int(math.ceil(EDGE_M / CELL_M)))
    blocked = cv2.dilate(blocked, np.ones((2 * grow + 1, 2 * grow + 1), np.uint8))
    # a sector's natural ground is country: its cells are free again, and each plant is checked on a 1 m picture of
    # that ground (the mesh's "wild" triangles, WILD_EDGE_M in from their edge)
    wild = []
    wild_cell = np.zeros((ch, cw), bool)
    for name, spec in sectors.SECTORS.items():
        path = os.path.join(DATA, "sectors", name, "ground.npz")
        if not spec.get("wild") or not os.path.exists(path):
            continue
        g = np.load(path)
        kinds = [str(n) for n in g["kind_names"]]
        if "wild" not in kinds:
            continue
        west, east, south, north = [float(v) for v in g["box"]]
        fine = np.zeros((int(north - south) + 2, int(east - west) + 2), np.uint8)
        px = np.stack([g["pts"][:, 0] - west, north - g["pts"][:, 1]], axis=1)
        for tri in g["tris"][g["kind"] == kinds.index("wild")]:
            cv2.fillConvexPoly(fine, np.round(px[tri]).astype(np.int32), 1)
        fine = cv2.erode(fine, np.ones((2 * WILD_EDGE_M + 1, 2 * WILD_EDGE_M + 1), np.uint8))
        wild.append((west, north, fine, groundmesh.GroundMesh(name)))
        for i in np.nonzero((cy > south) & (cy < north))[0]:
            for j in np.nonzero((cx > west) & (cx < east))[0]:
                if fine[int(north - cy[i]), int(cx[j] - west)]:
                    wild_cell[i, j] = True
    blocked[wild_cell] = 0

    def on_wild(x, y):
        """The mesh of the sector whose natural ground the point stands on, or None."""
        for west, north, fine, mesh in wild:
            u, v = int(x - west), int(north - y)
            if 0 <= v < fine.shape[0] and 0 <= u < fine.shape[1] and fine[v, u]:
                return mesh
        return None

    terrain = np.load(data_path("terrain_base.npz"))
    h_map, w_map = terrain["water"].shape
    x_right, y_bottom = X_LEFT + w_map * M_PER_PX, Y_TOP - h_map * M_PER_PX
    in_frame = ((cx[None, :] > X_LEFT - FRAME_PAD_M) & (cx[None, :] < x_right + FRAME_PAD_M) &
                (cy[:, None] < Y_TOP + FRAME_PAD_M) & (cy[:, None] > y_bottom - FRAME_PAD_M))
    ok = (blocked == 0) & in_frame & (zc > 1.0) & (sand < 0.3) & (paved < 0.2) & (rock < 0.3) & (slope < MAX_SLOPE)

    groves = fbm((ch, cw), 70.0 / CELL_M, seed=61)                  # groves and open meadows
    grove = np.clip(0.30 + 1.25 * groves, 0.0, 1.7)
    lone = np.clip(0.55 + 0.9 * fbm((ch, cw), 160.0 / CELL_M, seed=63), 0.0, 1.4)
    area = CELL_M * CELL_M
    p_tree = (TREE_GREEN * green ** 1.4 * grove + TREE_DRY * dry * lone) * area
    edge = np.clip(4.0 * green * dry, 0, 1)
    p_bush = (BUSH_EDGE * edge * (0.4 + 0.6 * grove) + BUSH_EARTH * earth + BUSH_DRY * dry) * area
    p_tree = np.where(ok, np.clip(p_tree, 0, 0.92), 0.0)
    p_bush = np.where(ok, np.clip(p_bush, 0, 0.9), 0.0)

    rng = np.random.default_rng(SEED)
    tiles, counts = {}, {"trees": 0, "bushes": 0, "on sectors' natural ground": 0}
    tree_meshes, tree_w = zip(*TREES)
    bush_meshes, bush_w = zip(*BUSHES)
    tree_w = np.array(tree_w) / sum(tree_w)
    bush_w = np.array(bush_w) / sum(bush_w)

    def height_at(x, y):
        fx, fy = (x - ox) / q, (oy - y) / q
        j0, i0 = int(fx), int(fy)
        tx, ty = fx - j0, fy - i0
        return float(z[i0, j0] * (1 - tx) * (1 - ty) + z[i0, j0 + 1] * tx * (1 - ty) + z[i0 + 1, j0] * (1 - tx) * ty +
                     z[i0 + 1, j0 + 1] * tx * ty)

    dots = []
    for group, prob, meshes, weights, sink, scale in (("trees", p_tree, tree_meshes, tree_w, 0.15, (0.8, 1.25)),
                                                      ("bushes", p_bush, bush_meshes, bush_w, 0.05, (0.7, 1.35))):
        hit = rng.random(prob.shape) < prob
        # each cell's own numbers: where in the cell, which model, turned how, how large
        east, north, which, turn, size = (rng.random(prob.shape) for _ in range(5))
        steps = np.cumsum(weights)
        ii, jj = np.nonzero(hit)
        for i, j in zip(ii, jj):
            x = cx[j] + (east[i, j] - 0.5) * 0.9 * CELL_M
            y = cy[i] + (north[i, j] - 0.5) * 0.9 * CELL_M
            if wild_cell[i, j]:
                ground = on_wild(x, y)
                top = ground.at(x, y) if ground is not None else None
                if top is None:
                    continue                    # off the natural ground: on a kerb, in a garden
                zz = float(top) - sink
                counts["on sectors' natural ground"] += 1
            else:
                zz = height_at(x, y) - sink
            mesh = meshes[min(int(np.searchsorted(steps, which[i, j])), len(meshes) - 1)]
            key = "%d_%d" % (math.floor(x / TILE_M), math.floor(y / TILE_M))
            rows = tiles.setdefault(key, {"trees": {}, "bushes": {}})[group].setdefault(mesh, [])
            rows.append([round(x * 100.0, 1), round(-y * 100.0, 1), round(zz * 100.0, 1), round(float(turn[i, j]) * 360.0, 1),
                         round(scale[0] + float(size[i, j]) * (scale[1] - scale[0]), 3)])
            counts[group] += 1
            dots.append((x, y, group))

    out = os.path.join(DATA, "country")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "trees.json"), "w") as f:
        json.dump({"tiles": tiles, "counts": counts, "cell_m": CELL_M, "tile_m": TILE_M}, f)

    # preview over paint.png (a quarter of the landscape's vertices per side)
    img = cv2.imread(data_path("paint.png"))
    if img is not None:
        s = img.shape[1] / float(vx)
        for x, y, group in dots:
            u, v = int((x - ox) / q * s), int((oy - y) / q * s)
            if 0 <= u < img.shape[1] and 0 <= v < img.shape[0]:
                img[v, u] = (30, 70, 25) if group == "trees" else (60, 110, 80)
        cv2.imwrite(os.path.join(out, "country.png"), img)
    print("COUNTRY %d trees and %d shrubs in %d tiles of %.0f m (cells of %.0f m outside every sector, up to %.0f m "
          "beyond the frame); %d of them on the natural ground of %d sectors" % (
              counts["trees"], counts["bushes"], len(tiles), TILE_M, CELL_M, FRAME_PAD_M,
              counts["on sectors' natural ground"], len(wild)))


main()
