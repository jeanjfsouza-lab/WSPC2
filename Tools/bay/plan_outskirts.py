"""Plans the outskirts beyond the Bay's playable frame: far ground, its colours, and the closed roads out of the city.

  python -P Tools/bay/plan_outskirts.py

Until 2026-11-21 the playable landscape (10.2 x 7.65 km) ended at a flat sea on every side, which read as an island
in an ocean. Now the west is open sea (the coast, as Oakland faces the bay) and the other sides are land. The campaign model (bay_city_3d, the reference for the city) has land all round, crossed by two rivers
that leave the city's waters to the west and to the south. The outskirts give the map that land as scenery, at almost
no cost: one low ground mesh round the frame (a vertex every FINE_M out to FINE_PAD_M, every COARSE_M beyond, to
COARSE_PAD_M), one colour texture, no collision, no trees of its own (fog and the colour hide that); and a few roads
that leave the city and go on to the horizon as plain strips, each closed by a police roadblock where the drivable
road ends.

Ground height. At the frame's edge it is the landscape's own edge (build_surface.py), held FLAT_M out so the country
trees planted just beyond the frame (plan_country.py) still stand on it, then it eases over BLEND_M into rolling
country that rises with the distance (Oakland's hills: tens of metres near the city, 300-400 m ridges far off),
flattening towards the rivers. Water: near the frame where the landscape's edge is under water, beyond that where
the model has water (Saved/Bay/outskirts/model_ground.npz, campaign_ground.py).
Colour (Bay Area in the dry season): golden grass, oak groves in the hollows and on north-facing slopes, chaparral
between, rock on the steep faces, farmland in the flats by the rivers, sand on the shores, the exit roads in grey.
Exit roads. Each starts at a road the city already leaves unfinished at its edge (EXITS: the dead end and the side of
the frame it heads for). Inside the frame it is routed over the landscape by least cost (slope, water, built sectors
avoided), smoothed, and laid on the ground; beyond the frame it winds on over the outskirts' ground to the far edge.
Roadblock at its start: concrete barriers across the road, cones in a taper on the city side, a patrol car, a
"stop" sign, and an invisible wall that holds a car.

Input:  Saved/Bay/landscape.json, landscape.r16 (build_surface.py), Saved/Bay/network.json, Tools/bay/sectors.py,
        Saved/Bay/outskirts/model_ground.npz (campaign_ground.py; without it no rivers beyond the frame)
Output: Saved/Bay/outskirts/ground.npz    fine and coarse height grids (h, x0, y0 = north-west corner, step)
        Saved/Bay/outskirts/colour.png    the ground's colour over the whole coarse extent (north up)
        Saved/Bay/outskirts/outskirts.json   extent, frame, exits (centre lines x, y, z every few metres, width) and
                                             the roadblocks' pieces (Unreal cm, yaw)
        Saved/Bay/outskirts/preview.png   colour with the frame and the exits marked, for checking
"""
import heapq
import json
import math
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sectors
from common import DATA, load_json

OUT = os.path.join(DATA, "outskirts")
FINE_M, FINE_PAD_M = 50.0, 8000.0
COARSE_M, COARSE_PAD_M = 400.0, 24000.0
FLAT_M, BLEND_M = 700.0, 2300.0
SHORE_M = 250.0
OCEAN_RAMP_M = (-150.0, 900.0)     # the open sea starts this far west of the frame's west edge (ramp from, to)
TEXTURE_PX = 4096
ROUTE_M = 20.0
ROAD_WIDTH_M = 9.0
SEED = 20261121

# exit roads: (name, the dead end it starts from (x, y), the frame side it heads for)
# (2026-11-21: of the city's dead ends only these two reach open country; the others lie inside built districts, and
# more exits need new streets in network_edits.py)
EXITS = [("North", (-1000.0, 2075.0), "N"), ("East", (2905.0, -915.0), "E")]


# ---------------------------------------------------------------------------------------------- noise
def _hash(ix, iy, seed):
    h = (ix.astype(np.int64) * 374761393 + iy.astype(np.int64) * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 32767.5 - 1.0


def vnoise(x, y, cell, seed):
    fx, fy = np.asarray(x, np.float64) / cell, np.asarray(y, np.float64) / cell
    ix, iy = np.floor(fx), np.floor(fy)
    tx, ty = fx - ix, fy - iy
    tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
    a, b = _hash(ix, iy, seed), _hash(ix + 1, iy, seed)
    c, d = _hash(ix, iy + 1, seed), _hash(ix + 1, iy + 1, seed)
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def fbm(x, y, cell, seed, octaves=5):
    total, norm, amp = 0.0, 0.0, 1.0
    for k in range(octaves):
        total = total + amp * vnoise(x, y, cell / (2 ** k), seed + 17 * k)
        norm += amp
        amp *= 0.5
    return total / norm


def smoothstep(a, b, v):
    t = np.clip((np.asarray(v) - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------------------------- the world
class World:
    def __init__(self):
        info = load_json("landscape.json")
        self.vx, self.vy = info["vertices"]
        self.q = info["quad_m"]
        self.ox = info["location_cm"][0] / 100.0                 # Unreal x of the landscape's corner = Bay x
        oy_ue = info["location_cm"][1] / 100.0                  # Unreal y (south) of the corner
        raw = np.fromfile(os.path.join(DATA, "landscape.r16"), dtype="<u2").reshape(self.vy, self.vx).astype(np.float32)
        self.H = (raw - 32768.0) / 128.0 * info["scale"][2] / 100.0
        self.X0, self.X1 = self.ox, self.ox + (self.vx - 1) * self.q
        self.Y1, self.Y0 = -oy_ue, -oy_ue - (self.vy - 1) * self.q   # north and south edges, Bay metres
        mg = os.path.join(OUT, "model_ground.npz")
        self.model = dict(np.load(mg)) if os.path.exists(mg) else None
        if self.model:
            w = self.model["water"].astype(np.float32)
            w = cv2.dilate(w, np.ones((3, 3), np.uint8))
            self.model_water = cv2.GaussianBlur(w, (0, 0), 1.2)
            far = (1 - (w > 0.5)).astype(np.uint8)
            self.model_water_dist = cv2.distanceTransform(far, cv2.DIST_L2, 5) * float(self.model["step"])

    def land(self, x, y):
        """Landscape height (bilinear) at points inside the frame; nan outside."""
        u = (np.asarray(x) - self.ox) / self.q
        v = (self.Y1 - np.asarray(y)) / self.q
        ok = (u >= -1e-6) & (v >= -1e-6) & (u <= self.vx - 1 + 1e-6) & (v <= self.vy - 1 + 1e-6)
        u, v = np.clip(u, 0, self.vx - 1.001), np.clip(v, 0, self.vy - 1.001)
        iu, iv = u.astype(np.int64), v.astype(np.int64)
        fu, fv = u - iu, v - iv
        H = self.H
        z = (H[iv, iu] * (1 - fu) * (1 - fv) + H[iv, iu + 1] * fu * (1 - fv) + H[iv + 1, iu] * (1 - fu) * fv
             + H[iv + 1, iu + 1] * fu * fv)
        return np.where(ok, z, np.nan)

    def _model(self, field, x, y, fill):
        if not self.model:
            return np.full(np.shape(x), fill, np.float32)
        m = self.model
        c = ((np.asarray(x) - float(m["x0"])) / float(m["step"])).astype(np.int64)
        r = ((float(m["y0"]) - np.asarray(y)) / float(m["step"])).astype(np.int64)
        n = field.shape[0]
        ok = (c >= 0) & (r >= 0) & (c < n) & (r < n)
        return np.where(ok, field[np.clip(r, 0, n - 1), np.clip(c, 0, n - 1)], fill)

    def height(self, x, y):
        """Ground height of the outskirts (anywhere; inside the frame it is the frame's edge band only)."""
        x, y = np.asarray(x, np.float64), np.asarray(y, np.float64)
        cx, cy = np.clip(x, self.X0, self.X1), np.clip(y, self.Y0, self.Y1)
        d = np.hypot(x - cx, y - cy)
        edge = self.land(cx, cy)
        w = smoothstep(FLAT_M, FLAT_M + BLEND_M, d)
        # water beyond the frame only where the model has it (its two rivers); where the frame's edge is under the
        # sea the ground climbs out of it within SHORE_M, a beach, so the city sits on its bay with land all round
        water = np.clip(self._model(self.model_water if self.model else None, x, y, 0.0) * smoothstep(0.0, 400.0, d), 0.0, 1.0)
        # the coast (user, 2026-11-21: "a cidade pode ser costeira em um dos lados"): open sea west of the frame, as
        # Oakland faces the bay; it reaches round the north-west and south-west corners and fades along the other sides
        ocean = smoothstep(self.X0 - OCEAN_RAMP_M[0], self.X0 - OCEAN_RAMP_M[1], x)
        water = np.maximum(water, ocean)
        shore = smoothstep(0.0, SHORE_M, d) * (1 - ocean)
        edge_land = edge * (1 - shore) + np.maximum(edge, 2.0) * shore
        near_river = smoothstep(300.0, 4000.0, self._model(self.model_water_dist if self.model else None, x, y, 1e5))
        relief = smoothstep(FLAT_M, 9000.0, d) * (0.12 + 0.88 * near_river)
        n1 = fbm(x, y, 6000.0, SEED, 4)
        n2 = 1.0 - np.abs(fbm(x, y, 1800.0, SEED + 5, 5))
        proc = 4.0 + relief * (170.0 * (0.5 + 0.5 * n1) + 210.0 * n2 * n2 * (0.6 + 0.4 * n1))
        land = edge_land * (1 - w) + proc * w
        wet = np.minimum(edge_land, -2.0) * (1 - w) + (-14.0) * w
        return land * (1 - water) + wet * water, water

    def colour(self, x, y, h, water, slope):
        n = 0.6 * fbm(x, y, 2600.0, SEED + 11, 3) + 0.4 * fbm(x, y, 700.0, SEED + 13, 3)
        m = fbm(x, y, 150.0, SEED + 12, 3)
        # albedo (not sRGB brightness of a photo): darker and a little greener than it looks in sunlight, to match
        # the landscape's own grass where the two meet (2026-11-21: the first colours read white through the haze)
        gold = np.stack([150 + 14 * m, 132 + 12 * m, 78 + 8 * m], -1)
        green = np.array([58, 72, 38], np.float32)
        chap = np.array([92, 92, 56], np.float32)
        rock = np.array([118, 110, 96], np.float32)
        sand = np.array([160, 150, 118], np.float32)
        sea = np.array([38, 58, 66], np.float32)
        oak = np.clip((n - 0.05) * 3.0, 0, 1) * np.clip(1.2 - slope * 1.5, 0, 1)
        col = gold * (1 - oak[..., None]) + green * oak[..., None]
        ch = np.clip(1 - np.abs(n - 0.02) * 6.0, 0, 1) * 0.6
        col = col * (1 - ch[..., None]) + chap * ch[..., None]
        rk = smoothstep(0.38, 0.6, slope)
        col = col * (1 - rk[..., None]) + rock * rk[..., None]
        # farmland in the flats: a patchwork of fields
        flat = (h > 1.5) & (h < 40) & (slope < 0.06) & (water < 0.1)
        fid = (_hash(np.floor(x / 320.0), np.floor(y / 260.0), SEED + 3) + 1) / 2
        field = np.stack([108 + 50 * fid, 112 + 36 * fid, 58 + 22 * fid], -1)
        fw = flat[..., None] * 0.85
        col = col * (1 - fw) + field * fw
        shore = smoothstep(4.0, 0.5, h)[..., None] * (water < 0.5)[..., None]
        col = col * (1 - shore) + sand * shore
        wet = smoothstep(0.3, 0.6, water)[..., None]
        col = col * (1 - wet) + sea * wet
        return np.clip(col, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------------------------- exits
def route(world, start, side, built_mask, built_origin):
    """Least-cost path over the landscape from start to the frame's side, on a ROUTE_M grid."""
    nx = int((world.X1 - world.X0) / ROUTE_M) + 1
    ny = int((world.Y1 - world.Y0) / ROUTE_M) + 1
    xs = world.X0 + np.arange(nx) * ROUTE_M
    ys = world.Y1 - np.arange(ny) * ROUTE_M
    gx, gy = np.meshgrid(xs, ys)
    z = world.land(gx, gy)
    wet = z < 0.5
    built = built_mask
    sc = int(round((start[0] - world.X0) / ROUTE_M)), int(round((world.Y1 - start[1]) / ROUTE_M))
    near = np.hypot(gx - start[0], gy - start[1]) < 80.0
    blocked = (built & ~near)
    goal = np.zeros((ny, nx), bool)
    if side == "N":
        goal[0, :] = True
    elif side == "S":
        goal[-1, :] = True
    elif side == "E":
        goal[:, -1] = True
    else:
        goal[:, 0] = True
    dist = np.full((ny, nx), np.inf)
    prev = np.full((ny, nx, 2), -1, np.int64)
    dist[sc[1], sc[0]] = 0.0
    heap = [(0.0, sc[0], sc[1])]
    steps = [(dx, dy, math.hypot(dx, dy)) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
    found = None
    while heap:
        dcur, cx, cy = heapq.heappop(heap)
        if dcur > dist[cy, cx]:
            continue
        if goal[cy, cx]:
            found = (cx, cy)
            break
        for dx, dy, ln in steps:
            px, py = cx + dx, cy + dy
            if px < 0 or py < 0 or px >= nx or py >= ny or blocked[py, px]:
                continue
            run = ln * ROUTE_M
            grade = abs(z[py, px] - z[cy, cx]) / run
            cost = run * (1.0 + 80.0 * grade * grade + (40.0 if grade > 0.12 else 0.0) + (60.0 if wet[py, px] else 0.0))
            nd = dcur + cost
            if nd < dist[py, px]:
                dist[py, px] = nd
                prev[py, px] = (cx, cy)
                heapq.heappush(heap, (nd, px, py))
    if not found:
        return None
    path, c = [], found
    while c[0] >= 0:
        path.append((float(xs[c[0]]), float(ys[c[1]])))
        p = prev[c[1], c[0]]
        c = (int(p[0]), int(p[1])) if p[0] >= 0 else (-1, -1)
    path.reverse()
    path[0] = (float(start[0]), float(start[1]))
    return path


def smooth(pts, passes=4):
    pts = np.asarray(pts, np.float64)
    for _ in range(passes):                                     # Chaikin, ends kept
        q = 0.75 * pts[:-1] + 0.25 * pts[1:]
        r = 0.25 * pts[:-1] + 0.75 * pts[1:]
        mid = np.empty((2 * len(q), 2))
        mid[0::2], mid[1::2] = q, r
        pts = np.vstack([pts[:1], mid, pts[-1:]])
    return pts


def resample(pts, step):
    seg = np.hypot(*np.diff(pts, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.arange(0, s[-1], step).tolist() + [s[-1]]
    return np.stack([np.interp(t, s, pts[:, 0]), np.interp(t, s, pts[:, 1])], -1)


def beyond(world, last, heading, extent):
    """The road on from the frame's edge over the outskirts, winding, to near the far edge."""
    x0, y0, x1, y1 = extent
    pts, (x, y), a = [], last, heading
    for k in range(4000):
        a += 0.18 * float(vnoise(np.array(k * 60.0), np.array(0.0), 900.0, SEED + 21))
        a = heading + max(-0.6, min(0.6, a - heading))
        x, y = x + 25.0 * math.cos(a), y + 25.0 * math.sin(a)
        if x < x0 + 1500 or x > x1 - 1500 or y < y0 + 1500 or y > y1 - 1500:
            break
        pts.append((x, y))
    return pts


def roadblock(start, heading, z, width):
    """Pieces of a police roadblock across a road whose drivable part ends at start, facing back into the city."""
    ux, uy = math.cos(heading), math.sin(heading)                # outwards
    px, py = -uy, ux                                             # across
    yaw_across = math.degrees(math.atan2(py, px))
    pieces = []

    def at(along, across, dz=0.0):
        return start[0] + ux * along + px * across, start[1] + uy * along + py * across, z + dz

    half = width / 2.0 + 2.5
    n = int(half * 2 / 3.0) + 1
    for i in range(n):                                            # concrete barriers, end to end
        x, y, zz = at(2.0, -half + i * (2 * half / max(n - 1, 1)))
        pieces.append({"kind": "barrier", "x": x, "y": y, "z": zz, "yaw": yaw_across})
    for i in range(7):                                            # cones: a taper on the city side
        along = -6.0 - i * 4.0
        across = -half + 1.0 + i * 0.9
        x, y, zz = at(along, across)
        pieces.append({"kind": "cone", "x": x, "y": y, "z": zz, "yaw": 0.0})
    x, y, zz = at(-4.0, half * 0.35)                              # patrol car, angled across the lane
    pieces.append({"kind": "patrol", "x": x, "y": y, "z": zz, "yaw": math.degrees(heading) + 110.0})
    x, y, zz = at(-1.5, -half + 0.8)
    pieces.append({"kind": "sign", "x": x, "y": y, "z": zz, "yaw": math.degrees(heading) + 180.0})
    x, y, zz = at(2.0, 0.0)                                       # the wall that holds a car (invisible)
    pieces.append({"kind": "wall", "x": x, "y": y, "z": zz + 2.0, "yaw": yaw_across, "size_m": [2 * half + 6.0, 1.0, 6.0]})
    return pieces


# ---------------------------------------------------------------------------------------------- main
def main():
    os.makedirs(OUT, exist_ok=True)
    world = World()
    fx0, fx1 = world.X0 - FINE_PAD_M, world.X1 + FINE_PAD_M
    fy0, fy1 = world.Y0 - FINE_PAD_M, world.Y1 + FINE_PAD_M
    cx0, cx1 = world.X0 - COARSE_PAD_M, world.X1 + COARSE_PAD_M
    cy0, cy1 = world.Y0 - COARSE_PAD_M, world.Y1 + COARSE_PAD_M

    grids = {}
    for name, (x0, x1, y0, y1, step) in {"fine": (fx0, fx1, fy0, fy1, FINE_M), "coarse": (cx0, cx1, cy0, cy1, COARSE_M)}.items():
        xs = x0 + np.arange(int(round((x1 - x0) / step)) + 1) * step
        ys = y1 - np.arange(int(round((y1 - y0) / step)) + 1) * step
        gx, gy = np.meshgrid(xs, ys)
        h, _ = world.height(gx, gy)
        grids[name] = {"h": h.astype(np.float32), "x0": x0, "y0": y1, "step": step}
        print("OUTSKIRTS %s grid %d x %d, %.0f m a cell, height %.1f .. %.1f m" % (name, len(xs), len(ys), step, h.min(), h.max()))
    np.savez_compressed(os.path.join(OUT, "ground.npz"),
                        **{"%s_%s" % (g, k): v for g, d in grids.items() for k, v in d.items()})

    # built sectors, rasterised on the routing grid: routes keep out of them
    nx = int((world.X1 - world.X0) / ROUTE_M) + 1
    ny = int((world.Y1 - world.Y0) / ROUTE_M) + 1
    mask = np.zeros((ny, nx), np.uint8)
    for sname, spec in sectors.SECTORS.items():
        if spec.get("status") not in ("built", "done"):
            continue
        ring = np.array(sectors.outline(sname), np.float64)
        pts = np.stack([(ring[:, 0] - world.X0) / ROUTE_M, (world.Y1 - ring[:, 1]) / ROUTE_M], -1)
        cv2.fillPoly(mask, [np.round(pts).astype(np.int32)], 1)
    built = mask.astype(bool)

    net = load_json("network.json")
    exits = []
    for name, start, side in EXITS:
        # the dead end's own road gives the heading and the width
        best = None
        for e in net["edges"]:
            for end, inner in ((e["pts"][0], e["pts"][min(4, len(e["pts"]) - 1)]), (e["pts"][-1], e["pts"][-min(5, len(e["pts"]))])):
                dd = math.hypot(end[0] - start[0], end[1] - start[1])
                if best is None or dd < best[0]:
                    best = (dd, end, inner, e)
        _, end, inner, edge = best
        start = (end[0], end[1])
        heading = math.atan2(end[1] - inner[1], end[0] - inner[0])
        path = route(world, start, side, built, None)
        if not path:
            print("OUTSKIRTS exit %s: no route" % name)
            continue
        inside = resample(smooth(path), 8.0)
        last = inside[-1]
        out_heading = {"N": math.pi / 2, "S": -math.pi / 2, "E": 0.0, "W": math.pi}[side]
        far = np.array(beyond(world, (float(last[0]), float(last[1])), out_heading, (cx0, cy0, cx1, cy1)))
        z_in = world.land(inside[:, 0], inside[:, 1])
        z_in = np.where(np.isnan(z_in), world.height(inside[:, 0], inside[:, 1])[0], z_in)
        z_far, _ = world.height(far[:, 0], far[:, 1]) if len(far) else (np.zeros(0), None)
        line = [[round(float(x), 2), round(float(y), 2), round(float(z) + 0.25, 2)] for (x, y), z in zip(inside, z_in)]
        line += [[round(float(x), 2), round(float(y), 2), round(float(z) + 0.6, 2)] for (x, y), z in zip(far, z_far)]
        width = max(ROAD_WIDTH_M, min(float(edge.get("width", 14.0)) * 0.6, 12.0))
        pieces = roadblock(start, heading, float(end[2]), width)
        exits.append({"name": name, "start": [round(start[0], 2), round(start[1], 2), round(float(end[2]), 2)],
                      "heading_deg": round(math.degrees(heading), 1), "width_m": round(width, 1), "line": line,
                      "inside_points": len(inside), "roadblock": pieces})
        seg = np.hypot(*np.diff(np.array(line)[:, :2], axis=0).T)
        print("OUTSKIRTS exit %s: from (%.0f, %.0f) to the %s edge, %.1f km inside the frame, %.1f km beyond" % (
            name, start[0], start[1], side, seg[:len(inside) - 1].sum() / 1000.0, seg[len(inside) - 1:].sum() / 1000.0))

    # colour over the coarse extent, the exits drawn on it
    px_w = TEXTURE_PX
    px_h = TEXTURE_PX                     # square in pixels (a power of two, so Unreal makes mips); cells a little taller than wide
    xs = cx0 + (np.arange(px_w) + 0.5) * (cx1 - cx0) / px_w
    ys = cy1 - (np.arange(px_h) + 0.5) * (cy1 - cy0) / px_h
    img = np.zeros((px_h, px_w, 3), np.uint8)
    step_y = 256
    for r0 in range(0, px_h, step_y):
        gx, gy = np.meshgrid(xs, ys[r0:r0 + step_y])
        h, water = world.height(gx, gy)
        m = (cx1 - cx0) / px_w
        gyd, gxd = np.gradient(h, m)
        slope = np.hypot(gxd, gyd)
        img[r0:r0 + step_y] = world.colour(gx, gy, h, water, slope)
    for ex in exits:
        p = np.array(ex["line"])[:, :2]
        pix = np.stack([(p[:, 0] - cx0) / (cx1 - cx0) * px_w, (cy1 - p[:, 1]) / (cy1 - cy0) * px_h], -1)
        cv2.polylines(img, [np.round(pix).astype(np.int32)], False, (92, 92, 96), 1, cv2.LINE_AA)
    cv2.imwrite(os.path.join(OUT, "colour.png"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))

    prev = cv2.resize(cv2.cvtColor(img, cv2.COLOR_RGB2BGR), (1024, int(1024 * px_h / px_w)))
    sx, sy = 1024 / (cx1 - cx0), prev.shape[0] / (cy1 - cy0)
    cv2.rectangle(prev, (int((world.X0 - cx0) * sx), int((cy1 - world.Y1) * sy)), (int((world.X1 - cx0) * sx), int((cy1 - world.Y0) * sy)), (0, 0, 255), 1)
    for ex in exits:
        p = np.array(ex["line"])[:, :2]
        cv2.polylines(prev, [np.round(np.stack([(p[:, 0] - cx0) * sx, (cy1 - p[:, 1]) * sy], -1)).astype(np.int32)], False, (255, 255, 255), 1)
    cv2.imwrite(os.path.join(OUT, "preview.png"), prev)

    with open(os.path.join(OUT, "outskirts.json"), "w") as f:
        json.dump({"frame": [world.X0, world.Y0, world.X1, world.Y1], "fine": [fx0, fy0, fx1, fy1, FINE_M],
                   "coarse": [cx0, cy0, cx1, cy1, COARSE_M], "texture": "colour.png", "exits": exits}, f)
    print("OUTSKIRTS %d exits; wrote %s" % (len(exits), OUT))


if __name__ == "__main__":
    main()
