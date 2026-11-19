"""Measures the Bay city's built ground against what it should be, over the whole map: where a road's surface leaves
the road's own profile, where a road has no ground under it, where a sector's open side stands off the landscape,
where a building stands on ground that falls or climbs steeply under it. A list of work for a geometry pass.

  python -P Tools/bay/audit_geometry.py [roads] [sides] [buildings] [nodes]      (no word: all four)

Input:  Saved/Bay/network.json, Tools/bay/sectors.py, Saved/Bay/sectors/<sector>/ground.npz and lots.json (the meshes
        and buildings as made), Saved/Bay/surface_height.npy (build_surface.py: the landscape, in the drawing's pixels)
Output: Saved/Bay/geometry.json   {"roads": [...], "holes": [...], "sides": [...], "buildings": [...], "nodes": [...]}
        prints a summary and the worst of each kind

roads      every metre along every street on the ground (not a bridge, a tunnel or a tunnel's open ramp), on the centre
           line and 2.5 m to each side, the mesh's height. A kink: the surface's grade changes by more than KINK_M
           from one metre to the next, beyond what the road's own profile does (a crest cut by a long triangle, a
           seam where two sectors hold different heights: what a car feels). A departure: away from the street's two
           ends the centre line is more than DEPART_M off the road's profile. A hole: no mesh under the centre line
           nor 25 cm to either side of it.
sides      every 4 m along every side of a sector that has no sector beyond it and no water: the mesh's edge against
           the landscape 3 m and 6 m out. The landscape lower than the edge by more than SIDE_TOL_M shows the mesh's
           underside as a dark line; higher, it stands as a bank against the sector. (build_surface.py carries the
           landscape on from every open side, except along a sector's retaining "walls", which are left out here too.)
buildings  ground under each building's footprint (its corners, the middles of its sides, its centre): how far it
           climbs above the floor (the back wall buried) and how far it falls below it (a podium).
nodes      junctions where exactly two streets of one class meet end to end: roadgeom.markings() starts each
           street's lines half a metre from its end, which leaves a metre without paint there.
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import groundmesh
import sectors
import structures
from common import DATA, bilinear, data_path, load_json

ROAD_STEP_M = 1.0
ROAD_SIDE_M = 2.5
KINK_M = 0.06               # a change of grade of 6 % from one metre to the next
CARRIAGEWAY = ("road", "white", "yellow", "apron")
END_M = 5.0                 # kinks are not counted this close to a street's two ends (the junction's own surface)
DEPART_M = 0.15
SIDE_STEP_M = 4.0
SIDE_TOL_M = 0.4
HALF_MIN_M = 6.0            # a street with a mesh under one half only counts from this length on
BURIED_M, PODIUM_M = 2.5, 4.0


class Ground:
    """Every built sector's mesh, found by position."""

    def __init__(self):
        self.names = [n for n in sectors.SECTORS if os.path.exists(os.path.join(DATA, "sectors", n, "ground.npz"))]
        self.rings = {n: sectors.outline(n) for n in self.names}
        self.boxes = {n: sectors.SECTORS[n]["box"] for n in self.names}
        self.meshes = {}
        # a coarse grid of which sectors' boxes reach each cell, so a point is tested against few outlines
        self.cell = 100.0
        self.grid = {}
        for n in self.names:
            w, e, s, no = self.boxes[n]
            for i in range(int(math.floor((w - 2) / self.cell)), int(math.floor((e + 2) / self.cell)) + 1):
                for j in range(int(math.floor((s - 2) / self.cell)), int(math.floor((no + 2) / self.cell)) + 1):
                    self.grid.setdefault((i, j), []).append(n)

    def mesh(self, n):
        if n not in self.meshes:
            self.meshes[n] = groundmesh.GroundMesh(n)
        return self.meshes[n]

    def surface(self, x, y):
        """(height, sector, kind of ground) of the mesh under the point; (None, None, None)."""
        for n in self.sectors_at(x, y, margin=1.0):
            m = self.mesh(n)
            if not hasattr(m, "kind"):
                d = np.load(os.path.join(DATA, "sectors", n, "ground.npz"))
                m.kind, m.kind_names = d["kind"], [str(k) for k in d["kind_names"]]
            cell = m.cells.get((int((x - m.x0) // groundmesh.CELL_M), int((y - m.y0) // groundmesh.CELL_M)))
            for t in cell or []:
                (ax, ay), (bx, by), (cx, cy) = m.pts[m.tris[t]]
                det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
                if abs(det) < 1e-12:
                    continue
                u = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / det
                v = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / det
                w = 1.0 - u - v
                if u >= -1e-6 and v >= -1e-6 and w >= -1e-6:
                    ha, hb, hc = m.h[t]
                    return float(u * ha + v * hb + w * hc), n, m.kind_names[m.kind[t]]
        return None, None, None

    def sectors_at(self, x, y, margin=0.0):
        out = []
        for n in self.grid.get((int(math.floor(x / self.cell)), int(math.floor(y / self.cell))), []):
            w, e, s, no = self.boxes[n]
            if w - margin <= x <= e + margin and s - margin <= y <= no + margin and (margin > 0.0 or sectors.contains(self.rings[n], x, y)):
                out.append(n)
        return out

    def at(self, x, y):
        """(height, sector) of the mesh under the point, trying every sector whose box reaches it; (None, None)."""
        for n in self.sectors_at(x, y, margin=1.0):
            z = self.mesh(n).at(x, y)
            if z is not None:
                return z, n
        return None, None


def audit_roads(net, ground):
    voids = [np.array(ring) for _, ring in structures.void_rings(net, 3.0)]

    def in_void(x, y):
        return any(sectors.contains([tuple(p) for p in ring], x, y) for ring in voids
                   if ring[:, 0].min() - 1 < x < ring[:, 0].max() + 1 and ring[:, 1].min() - 1 < y < ring[:, 1].max() + 1)

    ends = set()
    for e in net["edges"]:
        if e["level"] != 0 or e["cls"] in ("tunnel", "bridge"):
            ends.update((e["a"], e["b"]))
    node_xy = {n["id"]: (n["x"], n["y"]) for n in net["nodes"]}

    def surface(x, y, nx, ny):
        """The mesh under the point; a point that falls exactly between two sectors' meshes (a centre line that is
        their shared side) is tried a few centimetres to each side. Only the carriageway counts: on a median, a
        kerb or a sidewalk (a track 2.5 m off the centre clips the corner of a side street's sidewalk) the answer
        is "not carriageway", which is neither a height nor a hole."""
        for off in (0.0, 0.03, -0.03, 0.25, -0.25):
            z, n, kind = ground.surface(x + nx * off, y + ny * off)
            if z is not None:
                return (z, n) if kind in CARRIAGEWAY else (float("nan"), n)
        return None, None

    kinks, departs, holes, halves, measured = [], [], [], [], 0
    for e in net["edges"]:
        if e["level"] != 0 or e["cls"] in ("tunnel", "bridge"):
            continue
        pts = np.array(e["pts"], dtype=np.float64)
        seg = np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1]))
        s = np.concatenate([[0.0], np.cumsum(seg)])
        if s[-1] < 8.0:
            continue
        stations = np.arange(ROAD_STEP_M, s[-1] - ROAD_STEP_M + 1e-6, ROAD_STEP_M)
        xs, ys, zs = np.interp(stations, s, pts[:, 0]), np.interp(stations, s, pts[:, 1]), np.interp(stations, s, pts[:, 2])
        ax = np.interp(np.minimum(stations + 1.0, s[-1]), s, pts[:, 0]) - np.interp(np.maximum(stations - 1.0, 0.0), s, pts[:, 0])
        ay = np.interp(np.minimum(stations + 1.0, s[-1]), s, pts[:, 1]) - np.interp(np.maximum(stations - 1.0, 0.0), s, pts[:, 1])
        size = np.maximum(np.hypot(ax, ay), 1e-9)
        nx, ny = -ay / size, ax / size
        carried = np.array([any(math.hypot(xs[k] - node_xy[n][0], ys[k] - node_xy[n][1]) < 14.0 for n in (e["a"], e["b"]) if n in ends)
                            for k in range(len(stations))])
        worst_kink, worst_depart, hole_run = None, None, None
        there = {}                                  # per track: is there a mesh under each station
        for off in (0.0, ROAD_SIDE_M, -ROAD_SIDE_M):
            z = np.full(len(stations), np.nan)
            who = [None] * len(stations)
            there[off] = np.ones(len(stations), bool)
            for k in range(len(stations)):
                x, y = float(xs[k] + nx[k] * off), float(ys[k] + ny[k] * off)
                if carried[k] or in_void(x, y):
                    continue
                zz, n = surface(x, y, float(nx[k]), float(ny[k]))
                measured += 1
                if zz is None:
                    there[off][k] = False
                    if off == 0.0:
                        if hole_run and stations[k] - hole_run[7] <= 2.0 * ROAD_STEP_M:
                            hole_run[7], hole_run[3], hole_run[4] = float(stations[k]), round(x, 1), round(y, 1)
                        else:
                            if hole_run:
                                holes.append(hole_run)
                            hole_run = [e["id"], round(x, 1), round(y, 1), round(x, 1), round(y, 1), e["cls"], float(stations[k]), float(stations[k])]
                    continue
                z[k], who[k] = zz, n
            # a kink: the surface's grade changes by more than KINK_M over one step each way, beyond what the road's
            # own profile does there (a vertical curve changes a hundredth of that)
            bend = (z[2:] - 2.0 * z[1:-1] + z[:-2]) - (zs[2:] - 2.0 * zs[1:-1] + zs[:-2])
            bend[(stations[1:-1] < END_M) | (stations[1:-1] > s[-1] - END_M)] = np.nan
            for k in np.nonzero(np.abs(np.nan_to_num(bend)) > KINK_M)[0]:
                c = k + 1
                if worst_kink is None or abs(bend[k]) > abs(worst_kink[0]):
                    worst_kink = (float(bend[k]), float(xs[c] + nx[c] * off), float(ys[c] + ny[c] * off), who[c], off)
            if off == 0.0:
                # away from its two ends (where the crossing street has a say) the surface is the road's own profile
                far = (stations > 15.0) & (stations < s[-1] - 15.0)
                dz = np.where(far, z - zs, np.nan)
                if np.isfinite(dz).any():
                    k = int(np.nanargmax(np.abs(dz)))
                    if abs(dz[k]) > DEPART_M:
                        worst_depart = (float(dz[k]), float(xs[k]), float(ys[k]), who[k])
        if hole_run:
            holes.append(hole_run)
        # half a street: a mesh under one side of the centre line and none under the other (the landscape, painted
        # as asphalt, is the other half: no kerb, no markings, another texture)
        lone = there[ROAD_SIDE_M] != there[-ROAD_SIDE_M]
        k = 0
        while k < len(stations):
            if not lone[k]:
                k += 1
                continue
            j = k
            while j + 1 < len(stations) and lone[j + 1]:
                j += 1
            if stations[j] - stations[k] >= HALF_MIN_M:
                side = ROAD_SIDE_M if not there[ROAD_SIDE_M][k] else -ROAD_SIDE_M
                halves.append({"edge": e["id"], "cls": e["cls"], "length_m": round(float(stations[j] - stations[k] + ROAD_STEP_M), 1),
                               "from": [round(float(xs[k] + nx[k] * side), 1), round(float(ys[k] + ny[k] * side), 1)],
                               "to": [round(float(xs[j] + nx[j] * side), 1), round(float(ys[j] + ny[j] * side), 1)]})
            k = j + 1
        if worst_kink:
            kinks.append({"edge": e["id"], "cls": e["cls"], "bend_m": round(worst_kink[0], 2), "at": [round(worst_kink[1], 1), round(worst_kink[2], 1)],
                          "sector": worst_kink[3], "off_m": worst_kink[4]})
        if worst_depart:
            departs.append({"edge": e["id"], "cls": e["cls"], "dz_m": round(worst_depart[0], 2), "at": [round(worst_depart[1], 1), round(worst_depart[2], 1)],
                            "sector": worst_depart[3]})
    kinks.sort(key=lambda r: -abs(r["bend_m"]))
    departs.sort(key=lambda r: -abs(r["dz_m"]))
    holes = [{"edge": h[0], "cls": h[5], "from": [h[1], h[2]], "to": [h[3], h[4]], "length_m": round(h[7] - h[6] + ROAD_STEP_M, 1)} for h in holes]
    holes.sort(key=lambda r: -r["length_m"])
    halves.sort(key=lambda r: -r["length_m"])
    return kinks, departs, holes, halves, measured


def audit_sides(ground):
    from common import to_pixel
    surface = np.load(data_path("surface_height.npy"))
    h, w = surface.shape

    def land(x, y):
        u, v = to_pixel(np.array([x]), np.array([y]))
        u0, v0 = float(u[0]) - 0.5, float(v[0]) - 0.5
        i, j = int(math.floor(u0)), int(math.floor(v0))
        if i < 0 or j < 0 or i >= w - 1 or j >= h - 1:
            return None
        fu, fv = u0 - i, v0 - j
        return float(surface[j, i] * (1 - fu) * (1 - fv) + surface[j, i + 1] * fu * (1 - fv) + surface[j + 1, i] * (1 - fu) * fv + surface[j + 1, i + 1] * fu * fv)

    def off_segment(x, y, seg):
        (px, py), (qx, qy) = seg[0], seg[-1]
        dx, dy = qx - px, qy - py
        t = max(0.0, min(1.0, ((x - px) * dx + (y - py) * dy) / max(dx * dx + dy * dy, 1e-9)))
        return math.hypot(x - px - dx * t, y - py - dy * t)

    rows = {}
    for a in ground.names:
        ring = ground.rings[a]
        walls = sectors.SECTORS[a].get("walls", [])
        kinds = None
        for i in range(len(ring)):
            (ax, ay), (bx, by) = ring[i], ring[(i + 1) % len(ring)]
            side = math.hypot(bx - ax, by - ay)
            if side < 1e-6:
                continue
            ux, uy = (bx - ax) / side, (by - ay) / side
            nx, ny = uy, -ux
            count = max(1, int(round(side / SIDE_STEP_M)))
            for k in range(count):
                t = (k + 0.5) / count
                x, y = ax + (bx - ax) * t, ay + (by - ay) * t
                if [n for n in ground.sectors_at(x + nx * 0.6, y + ny * 0.6) if n != a]:
                    continue                                        # another sector beyond: a shared side
                if any(off_segment(x, y, seg) < 3.0 for seg in walls):
                    continue                                        # a retaining wall: the step is built
                edge = ground.mesh(a).at(x - nx * 0.3, y - ny * 0.3)
                if edge is None:
                    continue
                out = [land(x + nx * d, y + ny * d) for d in (3.0, 6.0)]
                if any(v is None or v < 0.2 for v in out):
                    continue                                        # water beyond (a sea wall), or the map's frame
                step = edge - out[0]
                rows.setdefault(a, []).append((step, edge - out[1], x, y, side / count))
    out = []
    for a, items in rows.items():
        steps = np.array([r[0] for r in items])
        bad = [r for r in items if abs(r[0]) > SIDE_TOL_M]
        if not bad:
            continue
        worst = max(bad, key=lambda r: abs(r[0]))
        out.append({"sector": a, "wild": bool(sectors.SECTORS[a].get("wild")), "open_m": round(sum(r[4] for r in items), 1),
                    "bad_m": round(sum(r[4] for r in bad), 1), "above_m": round(float(steps.max()), 2), "below_m": round(float(steps.min()), 2),
                    "worst_m": round(worst[0], 2), "at": [round(worst[2], 1), round(worst[3], 1)]})
    out.sort(key=lambda r: -r["bad_m"])
    total = sum(sum(r[4] for r in items) for items in rows.values())
    return out, total


def audit_buildings(ground):
    out, count = [], 0
    for n in ground.names:
        path = os.path.join(DATA, "sectors", n, "lots.json")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            rows = json.load(f)["buildings"]
        mesh = ground.mesh(n)
        for b in rows:
            c = [tuple(p) for p in b["corners"]]
            spots = c + [(b["x"], b["y"])] + [((c[k][0] + c[(k + 1) % 4][0]) / 2, (c[k][1] + c[(k + 1) % 4][1]) / 2) for k in range(4)]
            under = [mesh.at(x, y) for x, y in spots]
            if any(v is None for v in under):
                continue
            count += 1
            up, down = max(under) - b["z"], b["z"] - min(under)
            if up > BURIED_M or down > PODIUM_M:
                out.append({"sector": n, "unit": b["unit"], "at": [round(b["x"], 1), round(b["y"], 1)], "buried_m": round(up, 2), "podium_m": round(down, 2)})
    out.sort(key=lambda r: -max(r["buried_m"], r["podium_m"]))
    return out, count


def audit_nodes(net, ground):
    arms = {}
    for e in net["edges"]:
        if e["level"] != 0 or e["cls"] in ("tunnel", "bridge"):
            arms.setdefault(e["a"], []).append(None)
            arms.setdefault(e["b"], []).append(None)
            continue
        arms.setdefault(e["a"], []).append(e["cls"])
        arms.setdefault(e["b"], []).append(e["cls"])
    out = []
    for node in net["nodes"]:
        a = arms.get(node["id"], [])
        if len(a) == 2 and a[0] is not None and a[0] == a[1]:
            here = ground.sectors_at(node["x"], node["y"], margin=2.0)
            out.append({"node": node["id"], "cls": a[0], "at": [round(node["x"], 1), round(node["y"], 1)], "sectors": sorted(here)})
    return out


def main():
    what = set(sys.argv[1:]) or {"roads", "sides", "buildings", "nodes"}
    net = load_json("network.json")
    ground = Ground()
    path = data_path("geometry.json")
    result = json.load(open(path)) if os.path.exists(path) else {}
    if "roads" in what:
        kinks, departs, holes, halves, measured = audit_roads(net, ground)
        result["halves"] = halves
        print("ROADS %d stretches (%.0f m) with a mesh under one half of the street only" % (len(halves), sum(r["length_m"] for r in halves)))
        for r in halves[:40]:
            print("ROADS half  %5.0f m from (%.0f, %.0f) to (%.0f, %.0f), %s edge %d" % (
                r["length_m"], r["from"][0], r["from"][1], r["to"][0], r["to"][1], r["cls"], r["edge"]))
        result["kinks"], result["departs"], result["holes"] = kinks, departs, holes
        by_sector = {}
        for r in kinks:
            by_sector[r["sector"]] = by_sector.get(r["sector"], 0) + 1
        print("ROADS %d points measured; %d streets have a kink of more than %.2f m somewhere (in %d sectors); %d leave their profile by more "
              "than %.2f m; %d stretches with no ground (%.0f m)" % (measured, len(kinks), KINK_M, len(by_sector), len(departs), DEPART_M, len(holes),
                                                                     sum(r["length_m"] for r in holes)))
        for r in kinks[:40]:
            print("ROADS kink %+5.2f m at (%.0f, %.0f) in %s, %s edge %d%s" % (r["bend_m"], r["at"][0], r["at"][1], r["sector"], r["cls"], r["edge"],
                                                                                 "" if r["off_m"] == 0.0 else " (%.1f m off the centre)" % r["off_m"]))
        for r in departs[:25]:
            print("ROADS departs %+5.2f m at (%.0f, %.0f) in %s, %s edge %d" % (r["dz_m"], r["at"][0], r["at"][1], r["sector"], r["cls"], r["edge"]))
        print("ROADS kinks by sector: " + ", ".join("%s %d" % kv for kv in sorted(by_sector.items(), key=lambda kv: -kv[1])[:40]))
        for r in holes[:25]:
            print("ROADS hole %5.1f m from (%.0f, %.0f) to (%.0f, %.0f), %s edge %d" % (r["length_m"], r["from"][0], r["from"][1], r["to"][0], r["to"][1], r["cls"], r["edge"]))
    if "sides" in what:
        sides, total = audit_sides(ground)
        result["sides"] = sides
        print("SIDES %.0f m of open side measured; %d sectors stand more than %.1f m off the landscape somewhere (%.0f m of side)" % (
            total, len(sides), SIDE_TOL_M, sum(r["bad_m"] for r in sides)))
        for r in sides[:30]:
            print("SIDES %-6s %s %5.0f m of %5.0f m off; mesh above by up to %5.2f m, below by up to %5.2f m; worst at (%.0f, %.0f)" % (
                r["sector"], "natural" if r["wild"] else "       ", r["bad_m"], r["open_m"], max(r["above_m"], 0.0), max(-r["below_m"], 0.0), r["at"][0], r["at"][1]))
    if "buildings" in what:
        rows, count = audit_buildings(ground)
        result["buildings"] = rows
        print("BUILDINGS %d measured; %d with the ground more than %.1f m above the floor or %.1f m below it" % (count, len(rows), BURIED_M, PODIUM_M))
        for r in rows[:20]:
            print("BUILDINGS %-6s %-28s at (%.0f, %.0f): ground up to %.1f m above the floor, %.1f m below" % (
                r["sector"], r["unit"].replace("BPP_", ""), r["at"][0], r["at"][1], r["buried_m"], r["podium_m"]))
    if "nodes" in what:
        nodes = audit_nodes(net, ground)
        result["nodes"] = nodes
        touched = sorted({s for r in nodes for s in r["sectors"]})
        print("NODES %d junctions of two streets of one class, end to end; in %d sectors: %s" % (len(nodes), len(touched), " ".join(touched)))
    with open(path, "w") as f:
        json.dump(result, f, indent=1)


if __name__ == "__main__":
    main()
