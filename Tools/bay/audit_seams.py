"""Measures how well the ground meshes of neighbouring sectors of the Bay city meet along their shared sides.

  python -P Tools/bay/audit_seams.py [sector ...]        (no names: every sector that has a mesh)

Input:  Tools/bay/sectors.py (outlines, retaining walls), Saved/Bay/sectors/<sector>/ground.npz (the meshes as made)
Output: Saved/Bay/seams.json   [{"a": sector, "b": neighbour, "length_m", "gap_m": worst height difference between the
                               two meshes at the side, "gap_at": [x, y], "crease_m": worst fold of either mesh at the
                               side, "crease_at": [x, y], "bad_m": metres of the side where either is over STEP_M,
                               "runs": [[x0, y0, x1, y1], ...] the stretches of the side that are over}, ...],
                               worst first (written only when no sector is named)
        prints the pairs that are over STEP_M somewhere

How. Along every side of every sector's outline, a point every SAMPLE_M, and there:
  gap     the sector's mesh EDGE_M inside the side against the neighbour's mesh EDGE_M outside it: what stands open
          between the two (a slit one looks into from the side);
  crease  for each of the two meshes, how far its height at the side departs from the line through its heights IN_M
          and twice IN_M further in: a mesh that follows its ground has none, a mesh whose side is a straight rail
          over a hill has a fold of metres along it.
A side with no sector beyond it (an open side: sea or landscape) is listed with "-" for the neighbour and only its
own crease.
Why either happens: a side with only its two end points is a straight rail from one end's height to the other's,
whatever the ground does in between (CN1 and CN2 stood 4.5 m apart on a hillside, 2026-11-18; the cliff sides of the
Falesia Norte dived 30 m); or the two sectors hold different heights along the side. The cure is a seam (sectors.py,
SEAMS): the same points and the same heights in both. Stretches along a sector's retaining "walls" are steps by
design and are left out.
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import groundmesh
import sectors
from common import DATA, data_path

SAMPLE_M = 4.0
EDGE_M = 0.05
IN_M = 1.5
STEP_M = 0.5                # a difference worth reporting


def main():
    wanted = set(sys.argv[1:])
    names = [n for n in sectors.SECTORS if os.path.exists(os.path.join(DATA, "sectors", n, "ground.npz"))]
    rings = {n: sectors.outline(n) for n in names}
    boxes = {n: sectors.SECTORS[n]["box"] for n in names}
    walls = {n: [[tuple(p) for p in seg] for seg in sectors.SECTORS[n].get("walls", [])] for n in names}
    meshes = {}

    def mesh(n):
        if n not in meshes:
            meshes[n] = groundmesh.GroundMesh(n)
        return meshes[n]

    def other_at(name, x, y):
        for n in names:
            if n == name:
                continue
            w, e, s, north = boxes[n]
            if w - 1.0 <= x <= e + 1.0 and s - 1.0 <= y <= north + 1.0 and sectors.contains(rings[n], x, y):
                return n
        return None

    def walled(n, x, y, ux, uy):
        """True when the point of n's side lies on one of n's retaining walls."""
        ax, ay, bx, by = x - ux * 0.5, y - uy * 0.5, x + ux * 0.5, y + uy * 0.5
        for seg in walls[n]:
            for p, q in zip(seg[:-1], seg[1:]):
                if sectors.on_outline([p, q], ax, ay, bx, by, 0.05):
                    return True
        return False

    def crease(m, x, y, nx, ny):
        """How far the mesh's height at the side departs from the line through its heights further in (None: no
        mesh there). (nx, ny) points into the mesh."""
        z0 = m.at(x + nx * EDGE_M, y + ny * EDGE_M)
        z1 = m.at(x + nx * IN_M, y + ny * IN_M)
        z2 = m.at(x + nx * 2.0 * IN_M, y + ny * 2.0 * IN_M)
        if z0 is None or z1 is None or z2 is None:
            return None
        return abs(z0 - (2.0 * z1 - z2))

    pairs = {}
    for a in names:
        if wanted and a not in wanted:
            continue
        ring = rings[a]
        for i in range(len(ring)):
            (ax, ay), (bx, by) = ring[i], ring[(i + 1) % len(ring)]
            side = math.hypot(bx - ax, by - ay)
            if side < 1e-6:
                continue
            ux, uy = (bx - ax) / side, (by - ay) / side
            nx, ny = uy, -ux                                        # outward of a counter-clockwise outline
            count = max(1, int(round(side / SAMPLE_M)))
            for k in range(count):
                t = (k + 0.5) / count
                x, y = ax + (bx - ax) * t, ay + (by - ay) * t
                b = other_at(a, x + nx * 0.3, y + ny * 0.3)
                if b is None:
                    # an open side (the landscape carries on from it): only the sector's own fold can be measured
                    ca = None if walled(a, x, y, ux, uy) else crease(mesh(a), x, y, -nx, -ny)
                    if ca is not None:
                        pairs.setdefault((a, "-"), []).append((0.0, ca, x, y, side / count))
                    continue
                if not wanted and b < a:                             # each pair once, from its first sector
                    continue
                if walled(a, x, y, ux, uy) or walled(b, x, y, ux, uy):
                    continue
                za = mesh(a).at(x - nx * EDGE_M, y - ny * EDGE_M)
                zb = mesh(b).at(x + nx * EDGE_M, y + ny * EDGE_M)
                if za is None or zb is None:
                    continue
                ca, cb = crease(mesh(a), x, y, -nx, -ny), crease(mesh(b), x, y, nx, ny)
                fold = max(c for c in (ca, cb, 0.0) if c is not None)
                pairs.setdefault((a, b), []).append((abs(za - zb), fold, x, y, side / count))
    out = []
    for (a, b), rows in pairs.items():
        gap = np.array([r[0] for r in rows])
        fold = np.array([r[1] for r in rows])
        g, c = rows[int(np.argmax(gap))], rows[int(np.argmax(fold))]
        runs, last = [], None
        for r in rows:
            if max(r[0], r[1]) > STEP_M:
                if last is not None and math.hypot(r[2] - last[2], r[3] - last[3]) < 3.0 * SAMPLE_M:
                    runs[-1][2:] = [round(r[2], 1), round(r[3], 1)]
                else:
                    runs.append([round(r[2], 1), round(r[3], 1), round(r[2], 1), round(r[3], 1)])
                last = r
        out.append({"a": a, "b": b, "length_m": round(float(sum(r[4] for r in rows)), 1),
                    "gap_m": round(float(gap.max()), 2), "gap_at": [round(g[2], 1), round(g[3], 1)],
                    "crease_m": round(float(fold.max()), 2), "crease_at": [round(c[2], 1), round(c[3], 1)],
                    "bad_m": round(float(sum(r[4] for r in rows if max(r[0], r[1]) > STEP_M)), 1), "runs": runs})
    out.sort(key=lambda r: -max(r["gap_m"], r["crease_m"]))
    if not wanted:
        with open(data_path("seams.json"), "w") as f:
            json.dump(out, f, indent=1)
    bad = [r for r in out if r["bad_m"] > 0.0]
    print("SEAMS %d shared sides measured; %d are more than %.1f m out somewhere (%.0f m of side in all)" % (
        len(out), len(bad), STEP_M, sum(r["bad_m"] for r in bad)))
    for r in bad:
        print("SEAMS %-6s %-6s gap %5.2f m at (%.0f, %.0f); crease %5.2f m at (%.0f, %.0f); %4.0f m of %4.0f m over" % (
            r["a"], r["b"], r["gap_m"], r["gap_at"][0], r["gap_at"][1], r["crease_m"], r["crease_at"][0], r["crease_at"][1],
            r["bad_m"], r["length_m"]))


if __name__ == "__main__":
    main()
