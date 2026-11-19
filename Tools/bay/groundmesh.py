"""Height of a built sector's ground mesh at any point. Not run on its own.

A sector's ground (sector_mesh.py) is made of triangles that can be tens of metres across inside a block. On
sloping ground such a triangle lies a few centimetres above or below the smooth height field it was sampled
from, so whatever stands on the ground (a building, a tree grate, a bench) must be set on the triangle
itself, not on the field. GroundMesh reads Saved/Bay/sectors/<sector>/ground.npz and answers exactly that.
"""
import os

import numpy as np

from common import DATA

CELL_M = 6.0


class GroundMesh:
    def __init__(self, sector):
        d = np.load(os.path.join(DATA, "sectors", sector, "ground.npz"))
        self.pts, self.tris = d["pts"], d["tris"]
        # height of every corner of every triangle: the street surface plus that surface's rise (kerb, median)
        rise = d["tri_rise"] if "tri_rise" in d.files else np.zeros(self.tris.shape, np.float32)
        self.h = d["z"][self.tris] + rise
        lo = self.pts.min(axis=0)
        self.x0, self.y0 = float(lo[0]), float(lo[1])
        self.cells = {}
        tri_xy = self.pts[self.tris]                                  # (n, 3, 2)
        ix0 = ((tri_xy[:, :, 0].min(axis=1) - self.x0) // CELL_M).astype(int)
        ix1 = ((tri_xy[:, :, 0].max(axis=1) - self.x0) // CELL_M).astype(int)
        iy0 = ((tri_xy[:, :, 1].min(axis=1) - self.y0) // CELL_M).astype(int)
        iy1 = ((tri_xy[:, :, 1].max(axis=1) - self.y0) // CELL_M).astype(int)
        for t in range(len(self.tris)):
            for i in range(ix0[t], ix1[t] + 1):
                for j in range(iy0[t], iy1[t] + 1):
                    self.cells.setdefault((i, j), []).append(t)

    def at(self, x, y):
        """Height of the mesh's surface at (x, y), or None where the sector has no ground (water, outside)."""
        cell = self.cells.get((int((x - self.x0) // CELL_M), int((y - self.y0) // CELL_M)))
        if not cell:
            return None
        for t in cell:
            (ax, ay), (bx, by), (cx, cy) = self.pts[self.tris[t]]
            det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(det) < 1e-12:
                continue
            u = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / det
            v = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / det
            w = 1.0 - u - v
            if u >= -1e-6 and v >= -1e-6 and w >= -1e-6:
                ha, hb, hc = self.h[t]
                return float(u * ha + v * hb + w * hc)
        return None
