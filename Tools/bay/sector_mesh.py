"""Builds the ground of one sector of the Bay city: carriageways, kerbs, sidewalks, paint and block ground,
as one mesh with no gaps (Blender).

  blender -b --factory-startup --python Tools/bay/sector_mesh.py -- <sector>
  blender -b --factory-startup --python Tools/bay/sector_mesh.py -- <sector> --check
      (--check writes nothing: it works the mesh out again and compares it with Saved/Bay/sectors/<sector>/
       ground.npz, the mesh the sector was built from. Prints "CHECK <sector>: unchanged" or what changed.
       Run it for every built sector after the road network, the terrain or sectors.py were edited.)

Input:  Saved/Bay/network.json (design_network.py), Saved/Bay/terrain_base.npz, Tools/bay/sectors.py
Output: Saved/Bay/sectors/<sector>/<sector>_Ground.glb   mesh in metres, x east, y north, z up
        Saved/Bay/sectors/<sector>/ground.npz            the triangles, their kinds and heights, for preview_sector.py
                                                         and for whatever is set on the ground (groundmesh.py)
        Saved/Bay/sectors/<sector>/blocks.json           outline of every block (ground enclosed by streets)
Material slots: Road, PaintWhite, PaintYellow, Curb, Sidewalk, Concrete (medians), Lot (block ground), Grass (parks
and the gardens of Saved/Bay/sectors/<sector>/yards.json, when plan_yards.py has written that file), Wild (a sector's
"wild": natural ground, painted like the landscape round the city). A sector's "aprons" are block ground in the slot
Road, level with the carriageway, and take the sector's "paint".

How: every road contributes overlapping flat polygons (roadgeom.py). They are triangulated together
(constrained Delaunay) and each triangle takes the kind that takes precedence among the polygons covering
it. Heights come from the roads' profiles; sidewalks and blocks stand a kerb's height above the carriageway
and a vertical face closes every step. The sector rectangle cuts the result, so neighbouring sectors meet
along a straight line.
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import roadgeom
import structures
import sectors
from common import CURB_M, DATA, load_json
from sectors import SECTORS

MARGIN_M = 80.0             # roads this far outside the sector still shape its edge
UV_M = 4.0
MEDIAN_M = 0.20
SEAWALL_FOOT_M = -3.0       # the sea wall's face reaches this height (the sea is at 0)
SNAP_M = 0.05               # a polygon point this close to one of the sector's sides is put on it
GRID_M = 0.002              # all polygon points are rounded to this grid before triangulating
# Nearness for the triangulator: points closer than this are one point, and a point this close to a side is on
# it. It must be larger than what rounding to GRID_M moves a point off a slanting line (up to 1.4 mm): with 0.1 mm
# (until 2026-11-14) the corners of a crossing's stripes, rounded off the line they stood on, were joined to the
# far kerb by triangles of almost no area standing almost upright, 12 m long: seen as a band across the road.
CDT_EPS_M = 0.003
REFINE_TOL_M = {True: 0.03, False: 0.08}    # how far a flat triangle may depart from the true ground: on the
                                            # street (carriageway, paint, kerb, sidewalk) / elsewhere
REFINE_ROUNDS = 10          # (4 until 2026-11-18: on a crest beside a junction the fourth round still left folds of 0.2 m)
FOLD_TOL_M = 0.08           # --check: a built road surface that departs from the ground by more than this is a fold
REFINE_CLEAR_M = 0.3        # no point is added this close to the sector's own sides (the neighbour has none there)
PARAPET_W, PARAPET_H = 0.30, 0.95       # the low wall along the top of a terrace's walls
SLOT = {"road": "Road", "white": "PaintWhite", "yellow": "PaintYellow", "curb": "Curb", "sidewalk": "Sidewalk",
        "median": "Concrete", "ground": "Lot", "park": "Grass", "yard": "Grass", "apron": "Road", "wild": "Wild",
        "plaza": "Plaza", "path": "Path"}
SLOTS = ["Road", "PaintWhite", "PaintYellow", "Curb", "Sidewalk", "Concrete", "Lot", "Grass", "Wild", "Plaza", "Path"]
LEVEL = {"road": 0, "white": 0, "yellow": 0, "curb": 1, "sidewalk": 1, "ground": 1, "park": 1, "yard": 1, "median": 2,
         "apron": 0, "wild": 1, "plaza": 1, "path": 1}
WILD_SKIRT_M = (2.5, 1.5)   # natural ground that reaches the sector's own side runs on beyond it as an apron: this far
                            # out, falling this far (see below)
RISE = {0: 0.0, 1: CURB_M, 2: MEDIAN_M}
PAVED = {"road", "apron"}   # what paint may lie on


def painted(specs):
    """Quads of the paint a sector lays on its aprons (its "paint"): for each {"colour": "white" or "yellow",
    "line": [points], "width": metres (default 0.12), "dash": (on, off) metres or nothing for a solid line}, one
    quad per straight piece. Returns [(kind, four points)]."""
    out = []
    for spec in specs:
        half = float(spec.get("width", 0.12)) / 2.0
        dash = spec.get("dash")
        line = [tuple(p) for p in spec["line"]]
        for (ax, ay), (bx, by) in zip(line[:-1], line[1:]):
            run = math.hypot(bx - ax, by - ay)
            if run < 0.05:
                continue
            ux, uy = (bx - ax) / run, (by - ay) / run
            nx, ny = -uy * half, ux * half
            pieces = [(0.0, run)]
            if dash:
                on, off = dash
                pieces, s = [], 0.0
                while s + on <= run + 1e-6:
                    pieces.append((s, s + on))
                    s += on + off
            for s0, s1 in pieces:
                p0, p1 = (ax + ux * s0, ay + uy * s0), (ax + ux * s1, ay + uy * s1)
                out.append((spec.get("colour", "white"), [(p0[0] + nx, p0[1] + ny), (p0[0] - nx, p0[1] - ny),
                                                           (p1[0] - nx, p1[1] - ny), (p1[0] + nx, p1[1] + ny)]))
    return out


def crossed(quad):
    """True when a four-point polygon's opposite sides cross (a bow-tie)."""
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def cut(p1, p2, p3, p4):
        return side(p1, p2, p3) * side(p1, p2, p4) < 0 and side(p3, p4, p1) * side(p3, p4, p2) < 0

    a, b, c, d = quad
    return cut(a, b, c, d) or cut(b, c, d, a)


def strip(line, width):
    """The outline of a band `width` metres wide along a line (gentle bends only): its left side, then its right
    side backwards."""
    left, right = [], []
    for k, (x, y) in enumerate(line):
        ax, ay = line[max(k - 1, 0)]
        bx, by = line[min(k + 1, len(line) - 1)]
        d = math.hypot(bx - ax, by - ay) or 1.0
        nx, ny = -(by - ay) / d, (bx - ax) / d
        left.append((x + nx * width / 2.0, y + ny * width / 2.0))
        right.append((x - nx * width / 2.0, y - ny * width / 2.0))
    return left + right[::-1]


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    name = args[0]
    check = "--check" in args           # compare with the mesh the sector was built from; write nothing
    west, east, south, north = SECTORS[name]["box"]
    cut = sectors.outline(name)                     # the sector's own sides
    out_dir = os.path.join(DATA, "sectors", name)
    os.makedirs(out_dir, exist_ok=True)

    net = load_json("network.json")
    node_xy = {n["id"]: (n["x"], n["y"]) for n in net["nodes"]}
    roads = roadgeom.sector_roads(net, (west, east, south, north), MARGIN_M)
    print("SECTOR %s: %d roads within reach" % (name, len(roads)))
    polys = roadgeom.street_polygons(roads, node_xy)
    # where the land ends (sector_prep.py); without the file the whole sector is dry
    prep_path = os.path.join(out_dir, "prep.json")
    has_shore = os.path.exists(prep_path)
    if has_shore:
        with open(prep_path) as f:
            prep = json.load(f)
        # a straight quay is one side of the land's outline, hundreds of metres long. A side only has a height
        # at its two ends, so the top of the sea wall would run straight from one corner's height to the
        # other's whatever the ground does in between: long sides get a point about every 30 m
        def with_points(ring, step=30.0):
            out = []
            for i in range(len(ring)):
                (ax, ay), (bx, by) = ring[i], ring[(i + 1) % len(ring)]
                pieces = max(1, int(round(math.hypot(bx - ax, by - ay) / step)))
                out += [(ax + (bx - ax) * k / pieces, ay + (by - ay) * k / pieces) for k in range(pieces)]
            return out

        polys += [("land", with_points([tuple(p) for p in ring]), None) for ring in prep["land"]]
        polys += [("pond", [tuple(p) for p in ring], None) for ring in prep["ponds"]]
    # lawns (the sector's "parks"): block ground that is grass instead of paving; streets and sidewalks cut them
    polys += [("park", [tuple(p) for p in ring], None) for ring in SECTORS[name].get("parks", [])]
    # paths through the lawns (the sector's "paths": {"line": [...], "width": m}): a band of fine gravel along
    # each line, level with the grass; streets and sidewalks cut them, they cut the lawns
    polys += [("path", strip([tuple(p) for p in path["line"]], float(path.get("width", 3.0))), None)
              for path in SECTORS[name].get("paths", [])]
    # asphalt aprons (the sector's "aprons"): block ground paved like a carriageway and level with it, so a drive
    # without kerbs runs straight on to it (a training ground, a car park); streets and sidewalks cut them. And the
    # paint the sector lays on them (its "paint")
    polys += [("apron", [tuple(p) for p in ring], None) for ring in SECTORS[name].get("aprons", [])]
    polys += [(kind, quad, None) for kind, quad in painted(SECTORS[name].get("paint", []))]
    # squares (the sector's "plazas"): block ground paved in stone slabs instead of the blocks' plain concrete (until
    # 2026-11-19 a square was told from a yard only by its trees). Streets, sidewalks, lawns and gardens cut them
    polys += [("plaza", [tuple(p) for p in ring], None) for ring in SECTORS[name].get("plazas", [])]
    # natural ground (the sector's "wild"): block ground left as the country is, in a material painted like the
    # landscape. Streets, sidewalks, lawns and gardens cut it; True means the whole sector
    wild = SECTORS[name].get("wild", [])
    polys += [("wild", [tuple(p) for p in ring], None) for ring in ([list(cut)] if wild is True else wild)]
    # gardens (plan_yards.py): what the buildings leave over inside the blocks, as lawn. They are block ground
    # all the same: a block's outline, which plan_lots.py builds along, takes them in. The file only exists
    # once the buildings are planned, so a sector with gardens is meshed twice (see plan_yards.py)
    yards_path = os.path.join(out_dir, "yards.json")
    if os.path.exists(yards_path) and SECTORS[name].get("yards", True):
        with open(yards_path) as f:
            polys += [("yard", [tuple(p) for p in ring], None) for ring in json.load(f)["rings"]]
    # the open ramps of the tunnels: the ground has a hole there, and the tunnel's own walls stand in it
    polys += [("void", [tuple(p) for p in ring], None) for _, ring in structures.void_rings(net)]
    polys.append(("ground", list(cut), None))

    # A point that lies a hair off one of the sector's sides (a junction disc's point 1 cm from a side that runs
    # through that junction) makes the triangulator lose track of which polygon covers what. Such points are
    # put exactly on the side.
    def on_side(p):
        for i in range(len(cut)):
            (ax, ay), (bx, by) = cut[i], cut[(i + 1) % len(cut)]
            dx, dy = bx - ax, by - ay
            side = math.hypot(dx, dy)
            t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / (side * side)
            off = ((p[0] - ax) * dy - (p[1] - ay) * dx) / side
            if abs(off) < SNAP_M and -0.001 <= t <= 1.001:
                return (ax + dx * t, ay + dy * t)
        return p

    polys = [(kind, pts if kind == "ground" else [on_side(p) for p in pts], rid) for kind, pts, rid in polys]

    # ---- triangulate everything together, in coordinates local to the sector
    ox, oy = west, south
    verts, faces, kinds, own_area = [], [], [], []
    for kind, pts, _ in polys:
        # anything wholly outside the sector cannot matter
        if max(p[0] for p in pts) < west - 1 or min(p[0] for p in pts) > east + 1 or \
                max(p[1] for p in pts) < south - 1 or min(p[1] for p in pts) > north + 1:
            continue
        # the triangulator reads a clockwise polygon as "everything but its inside": make all counter-clockwise
        area = 0.0
        for i in range(len(pts)):
            area += pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
        if abs(area) < 0.008 or (len(pts) == 4 and crossed(pts)):
            continue                                    # a sliver or a bow-tie has no usable inside
        if area < 0:
            pts = pts[::-1]
        base = len(verts)
        # on a 2 mm grid: points of different polygons that should coincide (two roads' ends at one junction)
        # then do coincide exactly, instead of lying a fraction of a millimetre apart
        verts += [Vector((round((p[0] - ox) / GRID_M) * GRID_M, round((p[1] - oy) / GRID_M) * GRID_M)) for p in pts]
        faces.append(list(range(base, base + len(pts))))
        kinds.append(kind)
        own_area.append(abs(area) / 2.0)
    print("SECTOR %s: %d polygons, %d points in" % (name, len(faces), len(verts)))
    ground_id = len(faces) - 1
    field = roadgeom.HeightField(roads, levels=sectors.levels(name, net))
    base_ground = np.load(os.path.join(DATA, "terrain_base.npz"))["ground"]
    # The ground is flat between its points. Where the streets round a place climb at different rates (a steep
    # street leaving a junction whose other arms are level or fall) the true surface is curved, and a triangle
    # 12 m long across a carriageway, with points only at its corners, cuts a chord under or over it. Where it
    # meets the fine triangles of a crossing the road has a fold: 0.6 m at (1082, -811) on 2026-11-13, and up to
    # 0.35 m in the hill sectors built before. So the triangulation is refined: wherever the flat height in a
    # triangle (at its middle or at the middle of a side) departs from the true height by more than REFINE_TOL_M,
    # a point is added there and the whole is triangulated again.
    extra, added = [], set()
    street_kinds = set(roadgeom.PRECEDENCE) | {"apron"}
    cut_a = np.array(cut, dtype=np.float64)
    cut_b = np.roll(cut_a, -1, axis=0)
    for rnd in range(REFINE_ROUNDS + 1):
        v2, _, tris, _, _, orig = delaunay_2d_cdt(verts + extra, [], faces, 1, CDT_EPS_M, True)
        if rnd == REFINE_ROUNDS:
            break
        P = np.array([(v.x + ox, v.y + oy) for v in v2])
        Zv = roadgeom.ground_heights(field, P, base_ground)
        inside, fine = [], []
        for tri, src in zip(tris, orig):
            if len(tri) != 3 or ground_id not in src:
                continue
            present = {kinds[i] for i in src}
            if "void" in present or (has_shore and ("land" not in present or "pond" in present)):
                continue
            inside.append(tri)
            fine.append(bool(present & street_kinds))
        if not inside:
            break
        T = np.array(inside)
        tol = np.where(np.array(fine), REFINE_TOL_M[True], REFINE_TOL_M[False])
        worst_err = np.zeros(len(T))
        worst_xy = np.zeros((len(T), 2))
        for w in ((1 / 3, 1 / 3, 1 / 3), (0.5, 0.5, 0.0), (0.0, 0.5, 0.5), (0.5, 0.0, 0.5)):
            w = np.array(w)
            xy = (P[T] * w[None, :, None]).sum(axis=1)
            flat = (Zv[T] * w[None, :]).sum(axis=1)
            err = np.abs(roadgeom.ground_heights(field, xy, base_ground) - flat)
            better = err > worst_err
            worst_err[better], worst_xy[better] = err[better], xy[better]
        new = 0
        for k in np.nonzero(worst_err > tol)[0]:
            x, y = worst_xy[k]
            ab = cut_b - cut_a
            s = np.clip(((x - cut_a[:, 0]) * ab[:, 0] + (y - cut_a[:, 1]) * ab[:, 1]) / np.maximum((ab ** 2).sum(axis=1), 1e-12), 0.0, 1.0)
            if np.hypot(cut_a[:, 0] + ab[:, 0] * s - x, cut_a[:, 1] + ab[:, 1] * s - y).min() < REFINE_CLEAR_M:
                continue
            key = (round((x - ox) / GRID_M) * GRID_M, round((y - oy) / GRID_M) * GRID_M)
            if key in added:
                continue
            added.add(key)
            extra.append(Vector(key))
            new += 1
        if not new:
            break
    print("SECTOR %s: %d points added where the ground curves" % (name, len(extra)))
    # a polygon that folds over itself can be read as covering everything: any polygon credited with clearly
    # more area than it has is left out
    claimed = [0.0] * len(faces)
    for tri, src in zip(tris, orig):
        a, b, c = (v2[i] for i in tri[:3])
        t_area = abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)) / 2.0
        for i in set(src):
            claimed[i] += t_area
    # (the sector's own outline, the last polygon, too: read as covering everything it made the whole window, box
    # and margin, into ground, as in CW72 on 2026-11-15 and CW109 on 2026-11-16)
    rogue = {i for i in range(len(faces)) if claimed[i] > 1.3 * own_area[i] + 0.3}
    for i in sorted(rogue)[:10]:
        print("SECTOR %s: ignoring a folded %s polygon near (%.1f, %.1f): area %.2f, credited %.1f" % (
            name, kinds[i], verts[faces[i][0]].x + ox, verts[faces[i][0]].y + oy, own_area[i], claimed[i]))

    # ...and given back what is really theirs: every triangle whose middle lies inside such a polygon's own
    # outline, whatever the triangulator said (it may also have read the polygon inside out). Dropped
    # altogether, a plain strip of road whose corner lies 2 mm off another polygon's edge (the junction of S1
    # and S2 in CW107) left a hole of lawn in the carriageway
    def inside_face(i, x, y):
        ring = faces[i]
        hit = False
        for k in range(len(ring)):
            p, q = verts[ring[k]], verts[ring[(k + 1) % len(ring)]]
            if (p.y > y) != (q.y > y) and x < (q.x - p.x) * (y - p.y) / (q.y - p.y) + p.x:
                hit = not hit
        return hit

    boxes = {i: (min(verts[j].x for j in faces[i]), max(verts[j].x for j in faces[i]),
                 min(verts[j].y for j in faces[i]), max(verts[j].y for j in faces[i])) for i in rogue}
    given = 0
    fixed = []
    for tri, src in zip(tris, orig):
        own = [i for i in src if i not in rogue]
        if rogue:
            cx = sum(v2[i].x for i in tri[:3]) / 3.0
            cy = sum(v2[i].y for i in tri[:3]) / 3.0
            for i, (x0, x1, y0, y1) in boxes.items():
                if x0 <= cx <= x1 and y0 <= cy <= y1 and inside_face(i, cx, cy):
                    own.append(i)
                    given += 1
        fixed.append(own)
    orig = fixed
    if rogue:
        print("SECTOR %s: %d triangles given back to the folded polygons, inside their own outlines" % (name, given))
    rank = {k: i for i, k in enumerate(roadgeom.PRECEDENCE + ["apron", "path", "park", "yard", "plaza", "wild", "ground"])}
    pts = np.array([(v.x + ox, v.y + oy) for v in v2])
    tri_list, tri_kind = [], []
    flat_sides = set()
    void_sides = set()
    for tri, src in zip(tris, orig):
        if ground_id not in src or len(tri) != 3:
            continue
        present = {kinds[i] for i in src}
        if "void" in present:
            # a tunnel's open ramp: no ground, and no sea wall along its sides (the tunnel brings its own walls)
            void_sides.update((min(p, q), max(p, q)) for p, q in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])))
            continue
        if has_shore and ("land" not in present or "pond" in present):
            continue                                    # open water: the sea, not this mesh
        present -= {"land", "pond"}
        if not (present & PAVED) or "median" in present:
            present -= {"white", "yellow"}              # paint only exists on carriageway (and on an apron)
        kind = min(present, key=lambda k: rank[k])
        a, b, c = tri
        # every triangle faces up
        cross = (pts[b][0] - pts[a][0]) * (pts[c][1] - pts[a][1]) - (pts[b][1] - pts[a][1]) * (pts[c][0] - pts[a][0])
        if abs(cross) < 1e-9:
            # a triangle with no area is left out; its sides are remembered, so that the gap it leaves (which
            # has no width) is not taken for a shore and given a sea wall
            flat_sides.update(((min(p, q), max(p, q)) for p, q in ((a, b), (b, c), (c, a))))
            continue
        tri_list.append((a, b, c) if cross > 0 else (a, c, b))
        tri_kind.append(kind)
    tri_arr = np.array(tri_list)
    print("SECTOR %s: %d triangles, %d points out" % (name, len(tri_arr), len(pts)))

    # ---- heights
    z = roadgeom.ground_heights(field, pts, base_ground)

    if check:
        # Is the sector as built still what the network, the terrain and sectors.py give? The road network is
        # edited all the time, and an edit near a built sector can move a kerb, a crossing or a height in it
        # without anyone noticing: then its mesh in the map no longer matches its neighbours'.
        old = np.load(os.path.join(out_dir, "ground.npz"))
        old_names = [str(n) for n in old["kind_names"]]

        def faces(p, t, kinds):
            """The mesh as a set of triangles, each as its three corners (to the millimetre) and its kind:
            the same whatever order the triangulator hands points and triangles back in."""
            return {(tuple(sorted((round(float(p[v][0]), 3), round(float(p[v][1]), 3)) for v in tri)), kind)
                    for tri, kind in zip(t, kinds)}

        def area(key):
            (ax, ay), (bx, by), (cx, cy) = key[0]
            return abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / 2.0

        was = faces(old["pts"], old["tris"], [old_names[k] for k in old["kind"]])
        now = faces(pts, tri_list, tri_kind)
        gone, new = sorted(was - now), sorted(now - was)
        # heights, at every corner the two meshes share
        old_z = {}
        for tri in old["tris"]:
            for v in tri:
                old_z[(round(float(old["pts"][v][0]), 3), round(float(old["pts"][v][1]), 3))] = float(old["z"][v])
        lifted, at = 0.0, None
        for tri in tri_list:
            for v in tri:
                key = (round(float(pts[v][0]), 3), round(float(pts[v][1]), 3))
                if key in old_z and abs(old_z[key] - float(z[v])) > lifted:
                    lifted, at = abs(old_z[key] - float(z[v])), key
        # how much of the surface changed kind: the centre of every triangle that is new is looked up in the
        # old mesh. A junction that moved a millimetre gives thousands of new triangles and no change of kind;
        # a crossing that moved a metre, or a kerb that moved, gives square metres of it
        op, ot = old["pts"], old["tris"]
        ok = [old_names[k] for k in old["kind"]]
        cell, grid = 6.0, {}
        for i, tri in enumerate(ot):
            xs, ys = op[tri, 0], op[tri, 1]
            for gx in range(int(xs.min() // cell), int(xs.max() // cell) + 1):
                for gy in range(int(ys.min() // cell), int(ys.max() // cell) + 1):
                    grid.setdefault((gx, gy), []).append(i)

        def old_kind(x, y):
            for i in grid.get((int(x // cell), int(y // cell)), ()):
                (ax, ay), (bx, by), (cx, cy) = op[ot[i][0]], op[ot[i][1]], op[ot[i][2]]
                d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
                if abs(d) < 1e-12:
                    continue
                u = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / d
                v = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / d
                if u >= -1e-9 and v >= -1e-9 and u + v <= 1 + 1e-9:
                    return ok[i]
            return None

        swapped, spots = {}, []
        for k in new:
            mx, my = sum(c[0] for c in k[0]) / 3.0, sum(c[1] for c in k[0]) / 3.0
            before = old_kind(mx, my)
            if before != k[1]:
                swap = "%s to %s" % (before or "nothing", k[1])
                swapped[swap] = swapped.get(swap, 0.0) + area(k)
                spots.append((mx, my))
        changed = sum(swapped.values())
        # ...and between the corners: how far the old mesh's flat triangles depart from the true ground on the
        # street (at each triangle's middle and the middle of each side). Corners can all agree while a long
        # triangle between them cuts a chord through a curved street: that is a fold in the road, and a mesh
        # made before the refinement (2026-11-14) has them wherever the ground curves
        street_ids = [i for i, n in enumerate(old_names) if n in roadgeom.PRECEDENCE]
        st = ot[np.isin(old["kind"], street_ids)]
        fold, fold_at = 0.0, None
        if len(st):
            for w in ((1 / 3, 1 / 3, 1 / 3), (0.5, 0.5, 0.0), (0.0, 0.5, 0.5), (0.5, 0.0, 0.5)):
                w = np.array(w)
                xy = (op[st][:, :, :2] * w[None, :, None]).sum(axis=1)
                flat = (old["z"][st] * w[None, :]).sum(axis=1)
                err = np.abs(roadgeom.ground_heights(field, xy, base_ground) - flat)
                k = int(np.argmax(err))
                if err[k] > fold:
                    fold, fold_at = float(err[k]), (float(xy[k, 0]), float(xy[k, 1]))
        if fold > FOLD_TOL_M:
            lifted, at = max(lifted, fold), (at if lifted >= fold else fold_at)
        if not gone and not new and lifted < 0.005:
            print("CHECK %s: unchanged" % name)
        elif changed < 0.5 and lifted < 0.02:
            print("CHECK %s: same surface (%d triangles cut differently, %.2f m2 changed kind, heights within %.3f m)" % (
                name, len(new), changed, lifted))
        else:
            parts = []
            if changed >= 0.5:
                parts.append("%.1f m2 changed kind (%s) within x %.0f..%.0f y %.0f..%.0f" % (
                    changed, ", ".join("%s %.1f" % kv for kv in sorted(swapped.items(), key=lambda kv: -kv[1])[:5]),
                    min(s[0] for s in spots), max(s[0] for s in spots), min(s[1] for s in spots), max(s[1] for s in spots)))
            if fold > FOLD_TOL_M:
                parts.append("the built road surface departs from the ground by up to %.2f m near (%.0f, %.0f)" % (
                    fold, fold_at[0], fold_at[1]))
            if lifted >= 0.02 and lifted > fold:
                parts.append("heights differ by up to %.2f m, most near (%.0f, %.0f)" % (lifted, at[0], at[1]))
            if not parts:
                # (2026-11-17: this case printed an empty reason) heights moved by more than 2 cm, but no more than the
                # built surface's own departure from the ground, which is within the fold tolerance
                parts.append("heights differ by up to %.2f m near (%.0f, %.0f), within the fold tolerance (%.2f m)" % (
                    lifted, at[0], at[1], FOLD_TOL_M))
            print("CHECK %s: CHANGED: %s" % (name, "; ".join(parts)))
        return

    # a block's ground stays level with the carriageway where it touches one directly (no kerb there)
    low = np.zeros(len(pts), bool)
    for tri, kind in zip(tri_list, tri_kind):
        if LEVEL[kind] == 0:
            low[list(tri)] = True

    def level_at(kind, v):
        if kind in ("ground", "plaza") and low[v]:
            return 0
        return LEVEL[kind]

    # ---- mesh arrays
    mesh_verts, mesh_faces, mesh_slot, mesh_uv, smooth = [], [], [], [], []
    index = {}

    def vert(v, level):
        key = (v, level)
        if key not in index:
            index[key] = len(mesh_verts)
            mesh_verts.append((pts[v][0], pts[v][1], z[v] + RISE[level]))
        return index[key]

    u0, v0 = math.floor(ox / UV_M) * UV_M, math.floor(oy / UV_M) * UV_M
    for tri, kind in zip(tri_list, tri_kind):
        mesh_faces.append(tuple(vert(v, level_at(kind, v)) for v in tri))
        mesh_slot.append(SLOTS.index(SLOT[kind]))
        mesh_uv.append([((pts[v][0] - u0) / UV_M, (pts[v][1] - v0) / UV_M) for v in tri])
        smooth.append(True)

    # vertical faces wherever two neighbouring triangles stand at different heights along their shared edge
    edge_tris = {}
    for t, tri in enumerate(tri_list):
        for k in range(3):
            a, b = tri[k], tri[(k + 1) % 3]
            edge_tris.setdefault((min(a, b), max(a, b)), []).append(t)
    steps = 0
    for (a, b), ts in edge_tris.items():
        if len(ts) != 2:
            continue
        k1, k2 = tri_kind[ts[0]], tri_kind[ts[1]]
        la = (level_at(k1, a), level_at(k2, a))
        lb = (level_at(k1, b), level_at(k2, b))
        if la[0] == la[1] and lb[0] == lb[1]:
            continue
        lo_t, hi_t = (ts[0], ts[1]) if (la[0] + lb[0]) < (la[1] + lb[1]) else (ts[1], ts[0])
        klo, khi = tri_kind[lo_t], tri_kind[hi_t]
        za0, za1 = z[a] + RISE[level_at(klo, a)], z[a] + RISE[level_at(khi, a)]
        zb0, zb1 = z[b] + RISE[level_at(klo, b)], z[b] + RISE[level_at(khi, b)]
        quad = [(pts[a][0], pts[a][1], za0), (pts[b][0], pts[b][1], zb0), (pts[b][0], pts[b][1], zb1), (pts[a][0], pts[a][1], za1)]
        quad = [q for i, q in enumerate(quad) if i == 0 or q != quad[i - 1]]
        if len(quad) > 2 and quad[0] == quad[-1]:
            quad = quad[:-1]
        if len(quad) < 3:
            continue
        # face it towards the lower side
        centre = pts[list(tri_list[lo_t])].mean(axis=0)
        ex, ey = pts[b][0] - pts[a][0], pts[b][1] - pts[a][1]
        side = ex * (centre[1] - pts[a][1]) - ey * (centre[0] - pts[a][0])       # > 0: lower side is on the left of a->b
        if side > 0:
            quad = quad[::-1]
        base = len(mesh_verts)
        mesh_verts.extend(quad)
        mesh_faces.append(tuple(range(base, base + len(quad))))
        mesh_slot.append(SLOTS.index("Concrete" if "median" in (klo, khi) else "Curb"))
        run = math.hypot(ex, ey)
        mesh_uv.append([(0.0, 0.0), (run / UV_M, 0.0), (run / UV_M, 0.1), (0.0, 0.1)][:len(quad)])
        smooth.append(False)
        steps += 1

    # sea wall: where the ground ends at open water, a concrete face down past the low-tide line. The same
    # face holds the ground back along the outline's "walls" (the sector stands above natural ground there).
    # With "parapet", a low wall runs along the top wherever block ground or lawn reaches the edge.
    walls = 0
    retaining = SECTORS[name].get("walls", [])
    parapet = bool(SECTORS[name].get("parapet"))
    if has_shore or retaining:
        eps = 0.02
        for (a, b), ts in edge_tris.items():
            if len(ts) != 1 or (a, b) in flat_sides or (a, b) in void_sides:
                continue
            xa, ya, xb, yb = pts[a][0], pts[a][1], pts[b][0], pts[b][1]
            if sectors.on_outline(cut, xa, ya, xb, yb, eps) and not any(sectors.on_outline(seg, xa, ya, xb, yb, eps) for seg in retaining):
                continue                                # the sector's own edge: the next sector carries on
            kind = tri_kind[ts[0]]
            top_a, top_b = z[a] + RISE[level_at(kind, a)], z[b] + RISE[level_at(kind, b)]
            quad = [(xa, ya, SEAWALL_FOOT_M), (xb, yb, SEAWALL_FOOT_M), (xb, yb, top_b), (xa, ya, top_a)]
            centre = pts[list(tri_list[ts[0]])].mean(axis=0)
            land_side = (xb - xa) * (centre[1] - ya) - (yb - ya) * (centre[0] - xa)    # > 0: land on the left of a->b
            if land_side < 0:
                quad = quad[::-1]
            base = len(mesh_verts)
            mesh_verts.extend(quad)
            mesh_faces.append(tuple(range(base, base + 4)))
            mesh_slot.append(SLOTS.index("Concrete"))
            run = math.hypot(xb - xa, yb - ya)
            depth = (top_a - SEAWALL_FOOT_M) / UV_M
            uvs = [(0.0, 0.0), (run / UV_M, 0.0), (run / UV_M, depth), (0.0, depth)]
            mesh_uv.append(uvs if land_side >= 0 else uvs[::-1])
            smooth.append(False)
            walls += 1
            if parapet and kind in ("ground", "park", "yard", "wild", "plaza", "path") and run > 0.05:
                # seen with the land on the left of p -> q: outer face flush with the wall, top, face to the land, ends
                (px_, py_, pt), (qx, qy, qt) = ((xa, ya, top_a), (xb, yb, top_b)) if land_side >= 0 else ((xb, yb, top_b), (xa, ya, top_a))
                nx, ny = -(qy - py_) / run * PARAPET_W, (qx - px_) / run * PARAPET_W
                p0, p1, q0, q1 = pt - 0.02, pt + PARAPET_H, qt - 0.02, qt + PARAPET_H
                for quad in ([(px_, py_, p0), (qx, qy, q0), (qx, qy, q1), (px_, py_, p1)],
                             [(px_, py_, p1), (qx, qy, q1), (qx + nx, qy + ny, q1), (px_ + nx, py_ + ny, p1)],
                             [(qx + nx, qy + ny, q0), (px_ + nx, py_ + ny, p0), (px_ + nx, py_ + ny, p1), (qx + nx, qy + ny, q1)],
                             [(px_ + nx, py_ + ny, p0), (px_, py_, p0), (px_, py_, p1), (px_ + nx, py_ + ny, p1)],
                             [(qx, qy, q0), (qx + nx, qy + ny, q0), (qx + nx, qy + ny, q1), (qx, qy, q1)]):
                    base = len(mesh_verts)
                    mesh_verts.extend(quad)
                    mesh_faces.append(tuple(range(base, base + 4)))
                    mesh_slot.append(SLOTS.index("Concrete"))
                    span = math.hypot(quad[1][0] - quad[0][0], quad[1][1] - quad[0][1])
                    mesh_uv.append([(0.0, 0.0), (span / UV_M, 0.0), (span / UV_M, PARAPET_H / UV_M), (0.0, PARAPET_H / UV_M)])
                    smooth.append(False)

    # natural ground at the sector's own side: beyond it lies the landscape, which build_surface.py brings up to this
    # mesh's edge from a hand below. An apron in the same material runs on from the edge, outwards and down under the
    # landscape, so nothing shows through the slit between the two (a side shared with another sector's mesh has it
    # too, unseen). An apron, not a skirt hanging straight down: the material lays its textures from above, and an
    # upright face takes one line of them and smears it into stripes (seen on the beach side of CN2, 2026-11-18)
    skirts = 0
    for (a, b), ts in edge_tris.items():
        if len(ts) != 1 or tri_kind[ts[0]] != "wild" or (a, b) in flat_sides or (a, b) in void_sides:
            continue
        xa, ya, xb, yb = pts[a][0], pts[a][1], pts[b][0], pts[b][1]
        if not sectors.on_outline(cut, xa, ya, xb, yb, 0.02) or any(sectors.on_outline(seg, xa, ya, xb, yb, 0.02) for seg in retaining):
            continue
        top_a, top_b = z[a] + RISE[1], z[b] + RISE[1]
        centre = pts[list(tri_list[ts[0]])].mean(axis=0)
        span = math.hypot(xb - xa, yb - ya)
        if span < 1e-6:
            continue
        land_left = (xb - xa) * (centre[1] - ya) - (yb - ya) * (centre[0] - xa) > 0      # the ground lies left of a -> b
        ox_, oy_ = ((yb - ya) / span, -(xb - xa) / span) if land_left else (-(yb - ya) / span, (xb - xa) / span)
        out, fall = WILD_SKIRT_M
        quad = [(xa, ya, top_a), (xa + ox_ * out, ya + oy_ * out, top_a - fall), (xb + ox_ * out, yb + oy_ * out, top_b - fall),
                (xb, yb, top_b)]
        # seen from above it must run counter-clockwise to face up: a, a's outer point, b's, b does when the ground
        # lies left of a -> b (the apron then goes out to the right). (The first aprons were turned the other way:
        # facing down, they showed as a black band along the sector's side, 2026-11-18.)
        if not land_left:
            quad = quad[::-1]
        turn = (quad[1][0] - quad[0][0]) * (quad[2][1] - quad[1][1]) - (quad[1][1] - quad[0][1]) * (quad[2][0] - quad[1][0])
        if turn < 0.0:
            quad = quad[::-1]
        base = len(mesh_verts)
        mesh_verts.extend(quad)
        mesh_faces.append(tuple(range(base, base + 4)))
        mesh_slot.append(SLOTS.index("Wild"))
        mesh_uv.append([((q[0] - u0) / UV_M, (q[1] - v0) / UV_M) for q in quad])
        smooth.append(False)
        skirts += 1
    if skirts:
        print("SECTOR %s: %d apron faces where natural ground reaches the sector's side" % (name, skirts))

    # walls that stand on the ground (the sector's "barriers"): the perimeter wall of a garrison, a yard wall.
    # Each follows its line in short pieces, so it follows sloping ground; its foot is sunk 30 cm.
    # With "lift" the piece starts that far above the ground instead (a coping on a wall, the lintel of a
    # gate) and gets an underside; with "level" it is one height from end to end (a lintel is a beam).
    barrier_faces = 0
    base_ground = np.load(os.path.join(DATA, "terrain_base.npz"))["ground"]
    for barrier in SECTORS[name].get("barriers", []):
        height, half_w = float(barrier.get("height", 3.0)), float(barrier.get("width", 0.5)) / 2.0
        lift = float(barrier.get("lift", 0.0))
        sink = 0.0 if lift > 0.0 else 0.3
        line = [tuple(p) for p in barrier["line"]]
        for (ax, ay), (bx, by) in zip(line[:-1], line[1:]):
            run = math.hypot(bx - ax, by - ay)
            if run < 0.05:
                continue
            pieces = max(1, int(math.ceil(run / 6.0)))
            nx, ny = -(by - ay) / run * half_w, (bx - ax) / run * half_w
            stops = [(ax + (bx - ax) * k / pieces, ay + (by - ay) * k / pieces) for k in range(pieces + 1)]
            foot = roadgeom.ground_heights(field, stops, base_ground) + CURB_M + lift - sink
            if barrier.get("level"):
                foot = np.full(len(stops), float(np.mean(foot)))
            for k in range(pieces):
                (px_, py_), (qx, qy) = stops[k], stops[k + 1]
                p0, q0 = float(foot[k]), float(foot[k + 1])
                p1, q1 = p0 + height + sink, q0 + height + sink
                quads = [[(px_ - nx, py_ - ny, p0), (qx - nx, qy - ny, q0), (qx - nx, qy - ny, q1), (px_ - nx, py_ - ny, p1)],
                         [(qx + nx, qy + ny, q0), (px_ + nx, py_ + ny, p0), (px_ + nx, py_ + ny, p1), (qx + nx, qy + ny, q1)],
                         [(px_ - nx, py_ - ny, p1), (qx - nx, qy - ny, q1), (qx + nx, qy + ny, q1), (px_ + nx, py_ + ny, p1)]]
                if k == 0:
                    quads.append([(px_ + nx, py_ + ny, p0), (px_ - nx, py_ - ny, p0), (px_ - nx, py_ - ny, p1), (px_ + nx, py_ + ny, p1)])
                if k == pieces - 1:
                    quads.append([(qx - nx, qy - ny, q0), (qx + nx, qy + ny, q0), (qx + nx, qy + ny, q1), (qx - nx, qy - ny, q1)])
                if lift > 0.0:
                    quads.append([(px_ + nx, py_ + ny, p0), (qx + nx, qy + ny, q0), (qx - nx, qy - ny, q0), (px_ - nx, py_ - ny, p0)])
                for quad in quads:
                    base = len(mesh_verts)
                    mesh_verts.extend(quad)
                    mesh_faces.append(tuple(range(base, base + 4)))
                    mesh_slot.append(SLOTS.index("Concrete"))
                    span = math.hypot(quad[1][0] - quad[0][0], quad[1][1] - quad[0][1])
                    mesh_uv.append([(0.0, 0.0), (span / UV_M, 0.0), (span / UV_M, (height + sink) / UV_M), (0.0, (height + sink) / UV_M)])
                    smooth.append(False)
                    barrier_faces += 1

    # ---- Blender mesh and export
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mesh = bpy.data.meshes.new("Bay_%s_Ground" % name)
    mesh.from_pydata(mesh_verts, [], mesh_faces)
    for slot in SLOTS:
        mesh.materials.append(bpy.data.materials.new(slot))
    uv = mesh.uv_layers.new(name="UVMap")
    for poly, slot, uvs, is_smooth in zip(mesh.polygons, mesh_slot, mesh_uv, smooth):
        poly.material_index = slot
        poly.use_smooth = is_smooth
        for li, (u, v) in zip(poly.loop_indices, uvs):
            uv.data[li].uv = (u, v)
    mesh.validate()
    obj = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    glb = os.path.join(out_dir, "%s_Ground.glb" % name)
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_apply=True,
                              export_materials="EXPORT")

    # ---- data for the preview and for the lots stage
    kind_names = sorted(set(tri_kind))
    tri_rise = np.array([[RISE[level_at(kind, v)] for v in tri] for tri, kind in zip(tri_list, tri_kind)], dtype=np.float32)
    np.savez_compressed(os.path.join(out_dir, "ground.npz"), pts=pts, z=z, tris=tri_arr, tri_rise=tri_rise,
                        kind=np.array([kind_names.index(k) for k in tri_kind]), kind_names=np.array(kind_names),
                        box=np.array([west, east, south, north]), outline=np.array(cut))

    # blocks: connected groups of ground triangles, each with its outline
    ground_tris = [t for t, k in enumerate(tri_kind) if k in ("ground", "yard", "wild", "plaza")]
    parent = {t: t for t in ground_tris}

    def find(t):
        while parent[t] != t:
            parent[t] = parent[parent[t]]
            t = parent[t]
        return t

    is_ground = set(ground_tris)
    for ts in edge_tris.values():
        if len(ts) == 2 and ts[0] in is_ground and ts[1] in is_ground:
            parent[find(ts[0])] = find(ts[1])
    groups = {}
    for t in ground_tris:
        groups.setdefault(find(t), []).append(t)
    blocks = []
    for members in groups.values():
        area = 0.0
        boundary = {}
        inside = set(members)
        for t in members:
            a, b, c = tri_list[t]
            area += 0.5 * abs((pts[b][0] - pts[a][0]) * (pts[c][1] - pts[a][1]) - (pts[b][1] - pts[a][1]) * (pts[c][0] - pts[a][0]))
            for k in range(3):
                u, v = tri_list[t][k], tri_list[t][(k + 1) % 3]
                other = [x for x in edge_tris[(min(u, v), max(u, v))] if x != t]
                if not other or other[0] not in inside:
                    boundary[u] = v                    # outline runs counter-clockwise
        if area < 60.0 or not boundary:
            continue
        # a lawn inside a block leaves a hole in it: the block's outline is its outer ring, the largest loop
        loops, seen = [], set()
        for start in boundary:
            if start in seen:
                continue
            ring, cur = [start], boundary[start]
            seen.add(start)
            while cur != start and cur not in seen and len(ring) <= len(boundary):
                ring.append(cur)
                seen.add(cur)
                cur = boundary.get(cur, start)
            loops.append(ring)

        def ring_area(ring):
            return abs(sum(pts[ring[i]][0] * pts[ring[(i + 1) % len(ring)]][1] - pts[ring[(i + 1) % len(ring)]][0] * pts[ring[i]][1]
                           for i in range(len(ring)))) / 2.0

        loop = max(loops, key=ring_area)
        blocks.append({"area": round(area, 1),
                       "outline": [[round(float(pts[v][0]), 2), round(float(pts[v][1]), 2), round(float(z[v] + CURB_M), 2)] for v in loop]})
    blocks.sort(key=lambda b: -b["area"])
    with open(os.path.join(out_dir, "blocks.json"), "w") as f:
        json.dump({"sector": name, "blocks": blocks}, f)

    count = {}
    for k in tri_kind:
        count[k] = count.get(k, 0) + 1
    print("SECTOR %s: %s; %d kerb faces, %d sea wall faces; %d blocks; z %.2f .. %.2f m" % (
        name, ", ".join("%s %d" % kv for kv in sorted(count.items())), steps, walls, len(blocks), float(z.min()), float(z.max())))
    print("SECTOR %s: wrote %s" % (name, glb))


main()
