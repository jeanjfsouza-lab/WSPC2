"""Turns what a sector's buildings leave over inside its blocks into gardens: lawn behind and between them.

  python -P Tools/bay/plan_yards.py <sector> [<sector> ...]
  (plan_lots.py calls it at its end for a district with "yards"; run it on its own to give gardens to a sector
   whose buildings are already planned, without planning them again)

Input:  Saved/Bay/sectors/<sector>/blocks.json   block outlines (sector_mesh.py)
        Saved/Bay/sectors/<sector>/lots.json     the buildings' footprints (plan_lots.py)
        Tools/bay/sectors.py                     open areas, squares and walls: those stay paved
Output: Saved/Bay/sectors/<sector>/yards.json    {"sector": name, "area": m2, "rings": [[[x, y], ...], ...]}
            lawns, in metres (east, north). sector_mesh.py lays them as grass (kind "yard") the next time it
            runs, and plan_props.py plants them. So a sector with gardens is made in this order:
            sector_mesh.py, plan_lots.py (writes this file), sector_mesh.py again, plan_props.py.

Why: walk-up rows stand on the streets and leave the middle of their block open. Paved, that middle is a
slab of concrete 40 to 80 m wide; on a hill, where little can be built, it is most of the block. Real blocks
of this kind are green inside: back gardens, and slopes too steep to build left to grass and trees.

How: the sector's blocks are drawn on a grid of CELL_M. Taken out of them: every building, widened by APRON_M
(the paved strip round a building), the sector's open areas and squares, and a strip beside its walls. What is
left narrower than MIN_WIDTH_M goes too, so a passage between two buildings stays paved. Pieces smaller than
MIN_AREA_M2 are dropped. In a sector with natural ground (its "wild") only what lies within GARDEN_REACH_M of a
building becomes lawn: the rest of the block is the country's. The outlines are then let out by one cell, so that a lawn reaches the back of the
sidewalk: streets, sidewalks and declared lawns have precedence over it in the mesh and trim it exactly.
"""
import json
import math
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import structures
from common import DATA, load_json
from sectors import SECTORS

CELL_M = 0.5
APRON_M = 2.5           # paved strip left round every building
MIN_WIDTH_M = 6.0       # nothing narrower than this becomes lawn
MIN_AREA_M2 = 120.0
MIN_BLOCK_M2 = 900.0    # smaller blocks are traffic islands and corners: plan_lots.py builds nothing on them either
WALL_STRIP_M = 3.0      # paved strip along a wall (the sector's "barriers")
WALK_M = 3.6            # width of the walk from a building's door to the street...
WALK_REACH_M = 24.0     # ...and how far it may run out from the front (the block's edge ends it)
GARDEN_REACH_M = 11.0   # in a sector with natural ground ("wild"), a garden reaches this far from its building


def path_of(name):
    return os.path.join(DATA, "sectors", name, "yards.json")


def clear(name):
    """A sector without gardens must not keep an old file: sector_mesh.py would lay it."""
    if os.path.exists(path_of(name)):
        os.remove(path_of(name))


def add(name):
    """Works out the gardens of one sector and writes yards.json. Returns (number of lawns, their area in m2)."""
    sector = SECTORS[name]
    folder = os.path.join(DATA, "sectors", name)
    with open(os.path.join(folder, "blocks.json")) as f:
        blocks = json.load(f)["blocks"]
    lots_path = os.path.join(folder, "lots.json")
    buildings = json.load(open(lots_path))["buildings"] if os.path.exists(lots_path) else []
    west, east, south, north = sector["box"]
    x0, y0 = west - 4.0, north + 4.0
    w, h = int((east - west + 8.0) / CELL_M) + 1, int((north - south + 8.0) / CELL_M) + 1

    def px(ring):
        p = np.asarray(ring, dtype=np.float64)[:, :2]
        return np.stack([(p[:, 0] - x0) / CELL_M, (y0 - p[:, 1]) / CELL_M], axis=1).round().astype(np.int32)

    def disc(metres):
        k = int(round(metres / CELL_M)) * 2 + 1
        return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))

    block = np.zeros((h, w), np.uint8)
    for b in blocks:
        if b["area"] >= MIN_BLOCK_M2:
            cv2.fillPoly(block, [px(b["outline"])], 1)
    built = np.zeros((h, w), np.uint8)
    for b in buildings:
        cv2.fillPoly(built, [px(b["corners"])], 1)
    built = cv2.dilate(built, disc(APRON_M))
    # a walk from each building's door to its street: where the fronts stand back behind a strip of lawn (a
    # housing estate) the buildings would otherwise be islands in the grass. The front is the footprint's side
    # that looks out of the block (plan_lots.py lays a building's width along its frontage, the block on its left)
    for b in buildings:
        t = math.radians(b["angle"])
        ux, uy = math.cos(t), math.sin(t)
        nx, ny = -uy, ux
        fx, fy = b["x"] - nx * b["d"] / 2.0, b["y"] - ny * b["d"] / 2.0
        half = WALK_M / 2.0
        cv2.fillPoly(built, [px([(fx - ux * half + nx * 1.0, fy - uy * half + ny * 1.0), (fx + ux * half + nx * 1.0, fy + uy * half + ny * 1.0),
                                 (fx + ux * half - nx * WALK_REACH_M, fy + uy * half - ny * WALK_REACH_M),
                                 (fx - ux * half - nx * WALK_REACH_M, fy - uy * half - ny * WALK_REACH_M)])], 1)
    paved = np.zeros((h, w), np.uint8)
    ramps = [ring for _, ring in structures.void_rings(load_json("network.json"), 3.0)]
    for ring in sector.get("open", []) + sector.get("plazas", []) + ramps:
        cv2.fillPoly(paved, [px(ring)], 1)
    for barrier in sector.get("barriers", []):
        if not barrier.get("lift"):
            cv2.polylines(paved, [px(barrier["line"])], False, 1, thickness=max(1, int(round(2.0 * WALL_STRIP_M / CELL_M))))
    paved = cv2.dilate(paved, disc(1.0))

    lawn = block.copy()
    lawn[(built > 0) | (paved > 0)] = 0
    if sector.get("wild"):
        # the country comes up to the gardens: a lawn is what lies round a building, not the whole hillside
        lawn[cv2.dilate(built, disc(GARDEN_REACH_M)) == 0] = 0
    lawn = cv2.morphologyEx(lawn, cv2.MORPH_OPEN, disc(MIN_WIDTH_M / 2.0))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(lawn, connectivity=4)
    rings, total = [], 0.0
    for i in range(1, count):
        area = float(stats[i, cv2.CC_STAT_AREA]) * CELL_M * CELL_M
        if area < MIN_AREA_M2:
            continue
        piece = cv2.dilate((labels == i).astype(np.uint8), np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(piece, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        outline = cv2.approxPolyDP(max(contours, key=cv2.contourArea), 0.8, True).reshape(-1, 2)
        if len(outline) < 3:
            continue
        rings.append([[round(float(x0 + u * CELL_M), 2), round(float(y0 - v * CELL_M), 2)] for u, v in outline])
        total += area
    with open(path_of(name), "w") as f:
        json.dump({"sector": name, "area": round(total, 1), "rings": rings}, f)
    return len(rings), total


def main():
    for name in sys.argv[1:]:
        count, area = add(name)
        print("YARDS %s: %d lawns, %.0f m2" % (name, count, area))


if __name__ == "__main__":
    main()
