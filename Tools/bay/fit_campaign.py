"""Fits the campaign model's frame to the Bay city's, district by district.

  python -P Tools/bay/fit_campaign.py

The campaign (ASSETS TO USE/bay_city_3d) was written on a simplified model of the city. One scale and shift for the
whole map (x_bay = 0.970 x + 856, y_bay = -0.970 z - 292) leaves the model's roads a median 16 m off the Bay's, and up
to 100 m in places: the Bay was built from the drawn map and straightened and corrected as it went. A marker carried
over like that lands on the wrong street, or on none.
So the fit is finished locally, in two steps. First each neighbourhood's streets (420 m round a centre) are slid over
the Bay's as one piece, and the shift that covers most of them is taken: that settles which street is which. Then
points along the model's roads are matched to the nearest Bay road, the matches' offsets are smoothed into a field
(each point moves with its neighbourhood, not by itself), the field is applied and the matching repeated with a
shorter reach. What comes out is a displacement for every place on the map, stored on a 50 m grid; plan_campaign.py
adds it to the global fit.

Input:  ASSETS TO USE/bay_city_3d/dados/rede_viaria.bin, Saved/Bay/network.json
Output: Saved/Bay/campaign/frame.npz   x0, y0, cell, dx, dy: the displacement (metres, east and north) on a grid whose
                                       first sample is at (x0, y0); bilinear in between, the edge value outside
        Saved/Bay/campaign/frame.png   the model's roads over the Bay's: before (red) and after (blue)
        prints how far the model's roads lie from the Bay's before and after
"""
import os
import struct
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, PROJECT, load_json

CAMPAIGN = os.path.join(PROJECT, "ASSETS TO USE", "bay_city_3d", "dados")
OUT = os.path.join(DATA, "campaign")
SCALE, SHIFT_X, SHIFT_Y = 0.970, 856.0, -292.0
CELL = 50.0
SAMPLE_M = 20.0
HOOD_M = 420.0              # radius of a neighbourhood whose streets are slid over the Bay's as one piece
HOOD_EVERY_M = 240.0        # spacing of the neighbourhoods' centres
SLIDE_M, SLIDE_STEP_M = 132.0, 6.0
COVER_M = 9.0               # a model road sample this close to a Bay road is covered
# after the slide, point by point: (reach of a match, width of the smoothing), tighter each round
ROUNDS = [(45.0, 200.0), (38.0, 160.0), (30.0, 130.0), (25.0, 110.0)]


def model_samples():
    with open(os.path.join(CAMPAIGN, "rede_viaria.bin"), "rb") as f:
        buf = f.read()
    n_nodes, n_edges = struct.unpack_from("<2I", buf, 4)
    pts = np.array([struct.unpack_from("<3f", buf, 20 + 16 * i) for i in range(n_nodes)])[:, [0, 2]]
    pts = np.stack([SCALE * pts[:, 0] + SHIFT_X, -SCALE * pts[:, 1] + SHIFT_Y], axis=1)
    out, segs = [], []
    for i in range(n_edges):
        a, b = struct.unpack_from("<2I", buf, 20 + 16 * n_nodes + 8 * i)
        A, B = pts[a], pts[b]
        segs.append((A, B))
        n = max(1, int(np.hypot(*(B - A)) / SAMPLE_M))
        out.append(A + (B - A) * ((np.arange(n) + 0.5) / n)[:, None])
    return np.vstack(out), segs


def main():
    net = load_json("network.json")
    seg_a = np.vstack([np.asarray(e["pts"], dtype=np.float64)[:-1, :2] for e in net["edges"]])
    seg_b = np.vstack([np.asarray(e["pts"], dtype=np.float64)[1:, :2] for e in net["edges"]])
    ab = seg_b - seg_a
    len2 = np.maximum((ab ** 2).sum(axis=1), 1e-9)
    # a coarse index of the Bay's road segments, so each lookup only tests the segments near the point
    bucket, size = {}, 200.0
    for k in range(len(seg_a)):
        x0, x1 = sorted((seg_a[k][0], seg_b[k][0]))
        y0, y1 = sorted((seg_a[k][1], seg_b[k][1]))
        for gx in range(int(x0 // size), int(x1 // size) + 1):
            for gy in range(int(y0 // size), int(y1 // size) + 1):
                bucket.setdefault((gx, gy), []).append(k)

    def nearest(p):
        gx, gy = int(p[0] // size), int(p[1] // size)
        ids = [k for dx in (-1, 0, 1) for dy in (-1, 0, 1) for k in bucket.get((gx + dx, gy + dy), ())]
        if not ids:
            return None, 1e9
        ids = np.array(ids)
        t = np.clip(((p - seg_a[ids]) * ab[ids]).sum(axis=1) / len2[ids], 0.0, 1.0)
        q = seg_a[ids] + ab[ids] * t[:, None]
        d = np.hypot(q[:, 0] - p[0], q[:, 1] - p[1])
        k = int(np.argmin(d))
        return q[k], float(d[k])

    first, segs = model_samples()
    pts = first.copy()

    def report(label):
        d = np.array([nearest(p)[1] for p in pts])
        print("FRAME %s: the model's roads lie a median %.1f m off the Bay's; %d%% within 10 m, %d%% within 25 m, %d%% beyond 60 m" % (
            label, np.median(d), 100 * np.mean(d < 10), 100 * np.mean(d < 25), 100 * np.mean(d > 60)))
        return d

    report("global fit")

    # ---- first, neighbourhood by neighbourhood, the shift that lays the model's street pattern on the Bay's.
    # Matching each point to the nearest road cannot do this where the model is half a block off: a street that
    # lies midway between two of the Bay's is pulled to neither (the Centro Oeste's south, 55 m off, 2026-11-17:
    # its streets stayed between the Bay's and two missions seemed to lack a street). So each neighbourhood's
    # roads are slid over the Bay's as one piece and the shift that covers most of them is taken.
    grid_m = 2.0
    gx0, gy0 = first[:, 0].min() - 400.0, first[:, 1].min() - 400.0
    gw, gh = int((first[:, 0].max() + 400.0 - gx0) / grid_m), int((first[:, 1].max() + 400.0 - gy0) / grid_m)
    blank = np.full((gh, gw), 255, np.uint8)
    for e in net["edges"]:
        line = np.asarray(e["pts"], dtype=np.float64)[:, :2]
        cv2.polylines(blank, [np.stack([(line[:, 0] - gx0) / grid_m, (line[:, 1] - gy0) / grid_m], axis=1).round().astype(np.int32)], False, 0, 1)
    off_road = cv2.distanceTransform(blank, cv2.DIST_L2, 5) * grid_m

    def covered(p, shift):
        c = ((p[:, 0] + shift[0] - gx0) / grid_m).astype(int)
        r = ((p[:, 1] + shift[1] - gy0) / grid_m).astype(int)
        ok = (c >= 0) & (c < gw) & (r >= 0) & (r < gh)
        out = np.zeros(len(p), bool)
        out[ok] = off_road[r[ok], c[ok]] <= COVER_M
        return out

    shifts = [(dx, dy) for dx in np.arange(-SLIDE_M, SLIDE_M + 0.1, SLIDE_STEP_M) for dy in np.arange(-SLIDE_M, SLIDE_M + 0.1, SLIDE_STEP_M)]
    centres, found = [], []
    for cx in np.arange(first[:, 0].min(), first[:, 0].max() + 1, HOOD_EVERY_M):
        for cy in np.arange(first[:, 1].min(), first[:, 1].max() + 1, HOOD_EVERY_M):
            d2 = (first[:, 0] - cx) ** 2 + (first[:, 1] - cy) ** 2
            near = d2 < HOOD_M ** 2
            if near.sum() < 60:
                continue
            w = np.exp(-d2[near] / (2.0 * (HOOD_M / 2.0) ** 2))
            p = first[near]
            scores = np.array([(covered(p, s) * w).sum() - 0.0006 * np.hypot(*s) * w.sum() for s in shifts])
            k = int(np.argmax(scores))
            centres.append((cx, cy))
            found.append((shifts[k][0], shifts[k][1], scores[k] / w.sum()))
    centres, found = np.array(centres), np.array(found)
    # a neighbourhood whose shift stands apart from its neighbours' (a pattern that fits in two places) takes theirs
    calm = found[:, :2].copy()
    for i, c in enumerate(centres):
        near = np.hypot(centres[:, 0] - c[0], centres[:, 1] - c[1]) < HOOD_EVERY_M * 1.6
        med = np.median(found[near, :2], axis=0)
        if np.hypot(*(found[i, :2] - med)) > 45.0:
            calm[i] = med
    for i, p in enumerate(pts):
        d2 = (centres[:, 0] - p[0]) ** 2 + (centres[:, 1] - p[1]) ** 2
        w = np.exp(-d2 / (2.0 * (HOOD_EVERY_M * 0.8) ** 2)) * found[:, 2]
        pts[i] += (calm * w[:, None]).sum(axis=0) / max(w.sum(), 1e-9)
    print("FRAME neighbourhoods: %d of %d m, shifts median %.0f m, largest %.0f m; %d corrected to their neighbours'" % (
        len(centres), HOOD_M, np.median(np.hypot(calm[:, 0], calm[:, 1])), np.hypot(calm[:, 0], calm[:, 1]).max(),
        int((np.hypot(*(calm - found[:, :2]).T) > 1e-6).sum())))
    report("slid      ")
    for reach, width in ROUNDS:
        hits = [nearest(p) for p in pts]
        ok = np.array([d <= reach for _, d in hits])
        src = pts[ok]
        off = np.array([q - p for (q, d), p in zip(hits, pts) if d <= reach])
        # each point moves by the weighted mean of the offsets round it
        move = np.zeros_like(pts)
        for i, p in enumerate(pts):
            w = np.exp(-((src[:, 0] - p[0]) ** 2 + (src[:, 1] - p[1]) ** 2) / (2.0 * (width / 2.0) ** 2))
            total = w.sum()
            if total > 1e-6:
                move[i] = (off * w[:, None]).sum(axis=0) / total
        pts += 0.8 * move
    after = report("local fit ")

    # ---- the displacement as a grid: from the samples' total moves, smoothed the same way
    total_move = pts - first
    x0, y0 = first[:, 0].min() - 300.0, first[:, 1].min() - 300.0
    nx, ny = int((first[:, 0].max() + 300.0 - x0) / CELL) + 2, int((first[:, 1].max() + 300.0 - y0) / CELL) + 2
    dx, dy = np.zeros((ny, nx), np.float32), np.zeros((ny, nx), np.float32)
    for iy in range(ny):
        for ix in range(nx):
            gx, gy = x0 + ix * CELL, y0 + iy * CELL
            d2 = (first[:, 0] - gx) ** 2 + (first[:, 1] - gy) ** 2
            w = np.exp(-d2 / (2.0 * 70.0 ** 2)) + 1e-4 * np.exp(-d2 / (2.0 * 500.0 ** 2))
            dx[iy, ix], dy[iy, ix] = (total_move[:, 0] * w).sum() / w.sum(), (total_move[:, 1] * w).sum() / w.sum()
    os.makedirs(OUT, exist_ok=True)
    np.savez_compressed(os.path.join(OUT, "frame.npz"), x0=x0, y0=y0, cell=CELL, dx=dx, dy=dy)
    size_m = np.hypot(dx, dy)
    print("FRAME grid %d x %d cells of %.0f m; displacement median %.1f m, largest %.1f m" % (nx, ny, CELL, np.median(size_m), size_m.max()))

    # ---- picture
    def warp(p):
        u, v = (p[:, 0] - x0) / CELL, (p[:, 1] - y0) / CELL
        u, v = np.clip(u, 0, nx - 1.001), np.clip(v, 0, ny - 1.001)
        iu, iv = u.astype(int), v.astype(int)
        fu, fv = u - iu, v - iv
        out = p.copy()
        for k, field in enumerate((dx, dy)):
            out[:, k] += (field[iv, iu] * (1 - fu) * (1 - fv) + field[iv, iu + 1] * fu * (1 - fv)
                          + field[iv + 1, iu] * (1 - fu) * fv + field[iv + 1, iu + 1] * fu * fv)
        return out

    xs = [n["x"] for n in net["nodes"]]
    ys = [n["y"] for n in net["nodes"]]
    bx0, bx1, by0, by1 = min(xs) - 200, max(xs) + 200, min(ys) - 900, max(ys) + 200
    s = 0.3
    img = np.full((int((by1 - by0) * s), int((bx1 - bx0) * s), 3), 250, np.uint8)
    P = lambda x, y: (int(round((x - bx0) * s)), int(round((by1 - y) * s)))
    for e in net["edges"]:
        cv2.polylines(img, [np.array([P(p[0], p[1]) for p in e["pts"]], np.int32)], False, (170, 170, 170), 3, cv2.LINE_AA)
    for A, B in segs:
        cv2.line(img, P(*A), P(*B), (150, 150, 255), 1, cv2.LINE_AA)
        wa, wb = warp(np.array([A])), warp(np.array([B]))
        cv2.line(img, P(*wa[0]), P(*wb[0]), (200, 80, 0), 1, cv2.LINE_AA)
    cv2.imwrite(os.path.join(OUT, "frame.png"), img)
    d = np.array([nearest(p)[1] for p in warp(first)])
    print("FRAME through the grid: median %.1f m off, %d%% within 10 m, %d%% within 25 m, %d%% beyond 60 m" % (
        np.median(d), 100 * np.mean(d < 10), 100 * np.mean(d < 25), 100 * np.mean(d > 60)))


if __name__ == "__main__":
    main()
