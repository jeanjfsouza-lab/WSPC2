"""Road geometry shared by the sector mesher (runs inside Blender) and the surface rasters. Not run on its own.

Everything is in metres, x east, y north, z up. A road is a smoothed centre line with a height profile and a
cross-section from common.SECTIONS. From the roads of an area this module produces flat polygons, each with
a kind, that together describe the street surface:

  road       carriageway (strips along each road, a disc at each junction, the rounded corner pieces)
  curb       kerb stone, a narrow band on the sidewalk side of every carriageway edge
  sidewalk   between the kerb and the property line
  median     raised divider
  white, yellow   paint

The polygons overlap freely. Whoever triangulates them decides by precedence (paint over median over road
over curb over sidewalk over everything else), which is what makes junctions come out right without any
polygon clipping: a carriageway simply covers whatever sidewalk it crosses.
"""
import math

import numpy as np

from common import CURB_M, SECTIONS

CURB_W = 0.18               # width of the kerb stone seen from above
STEP_M = 6.0                # longest stretch of centre line between two cross-sections
ARC_STEP_M = 2.0            # the same on curves
SIMPLIFY = {"street": 2.6, "alley": 2.6, "arterial": 3.0, "freeway": 2.5, "ramp": 0.5, "bridge": 2.0, "tunnel": 2.5}
BEND_RADIUS = {"street": 14.0, "alley": 9.0, "arterial": 55.0, "freeway": 260.0, "ramp": 45.0, "bridge": 160.0, "tunnel": 70.0}
CORNER_RADIUS = {"street": 5.0, "alley": 3.0, "arterial": 8.0, "freeway": 20.0, "ramp": 14.0, "bridge": 8.0, "tunnel": 8.0}
BULB_RADIUS = 10.0          # turning circle at the end of a dead-end street
CROSSWALK_M = 3.0
PRECEDENCE = ["yellow", "white", "median", "road", "curb", "sidewalk"]


def rdp(points, tol):
    """Douglas-Peucker on (x, y, ...) tuples, judged in plan."""
    if len(points) < 3:
        return list(points)
    pts = np.asarray([p[:2] for p in points], dtype=np.float64)
    keep = np.zeros(len(pts), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = pts[i], pts[j]
        ab = b - a
        norm = math.hypot(ab[0], ab[1])
        seg = pts[i + 1:j]
        d = np.hypot(seg[:, 0] - a[0], seg[:, 1] - a[1]) if norm < 1e-9 else \
            np.abs(ab[0] * (seg[:, 1] - a[1]) - ab[1] * (seg[:, 0] - a[0])) / norm
        k = int(np.argmax(d))
        if d[k] > tol:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return [points[i] for i in range(len(points)) if keep[i]]


def smooth_centre(pts, cls, curve=False):
    """Straightens a traced centre line and rounds its bends. Returns (x, y) points, densely spaced.

    The trace follows pixels, so a straight street arrives as a slightly crooked line: it is reduced to its
    real corners first. Each corner then becomes an arc as large as the road class wants and the neighbouring
    straights allow.
    curve=True (a road an edit drew as a curve): every point is a point of the curve. None is dropped, and each
    corner's arc takes all the room its two neighbours leave, so the arcs run into one another: a smooth curve."""
    if curve:
        # (the height samples the network adds between two given points lie on the straight between them: dropped)
        raw = [(p[0], p[1]) for p in pts]
        corners = [raw[0]]
        for i in range(1, len(raw) - 1):
            ax, ay = raw[i][0] - corners[-1][0], raw[i][1] - corners[-1][1]
            bx, by = raw[i + 1][0] - raw[i][0], raw[i + 1][1] - raw[i][1]
            if math.hypot(ax, ay) < 0.5:
                continue
            if abs(math.atan2(ax * by - ay * bx, ax * bx + ay * by)) > math.radians(0.6):
                corners.append(raw[i])
        corners.append(raw[-1])
    else:
        corners = [(p[0], p[1]) for p in rdp(pts, SIMPLIFY[cls])]
    if len(corners) < 3:
        out = corners
    else:
        radius = 1e4 if curve else BEND_RADIUS[cls]
        out = [corners[0]]
        n = len(corners)
        # how much of each straight a corner may use: half of it, all of it at the line's two ends
        seg = [math.hypot(corners[i + 1][0] - corners[i][0], corners[i + 1][1] - corners[i][1]) for i in range(n - 1)]
        for i in range(1, n - 1):
            p0, p1, p2 = corners[i - 1], corners[i], corners[i + 1]
            ux, uy = p1[0] - p0[0], p1[1] - p0[1]
            vx, vy = p2[0] - p1[0], p2[1] - p1[1]
            lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
            if lu < 1e-6 or lv < 1e-6:
                continue
            ux, uy, vx, vy = ux / lu, uy / lu, vx / lv, vy / lv
            turn = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
            if abs(turn) < math.radians(2.0):
                out.append(p1)
                continue
            room_in = seg[i - 1] * (1.0 if i == 1 else 0.5)
            room_out = seg[i] * (1.0 if i == n - 2 else 0.5)
            tangent = min(radius * math.tan(abs(turn) / 2.0), room_in * 0.98, room_out * 0.98)
            r = tangent / math.tan(abs(turn) / 2.0)
            start = (p1[0] - ux * tangent, p1[1] - uy * tangent)
            side = 1.0 if turn > 0 else -1.0
            cx, cy = start[0] - uy * side * r, start[1] + ux * side * r
            a0 = math.atan2(start[1] - cy, start[0] - cx)
            steps = max(2, int(math.ceil(abs(turn) * r / ARC_STEP_M)))
            for k in range(steps + 1):
                a = a0 + turn * k / steps
                out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        out.append(corners[-1])
    dense = [out[0]]
    for i in range(len(out) - 1):
        ax, ay = out[i]
        bx, by = out[i + 1]
        d = math.hypot(bx - ax, by - ay)
        if d < 0.05:
            continue
        k = max(1, int(math.ceil(d / STEP_M)))
        for j in range(1, k + 1):
            dense.append((ax + (bx - ax) * j / k, ay + (by - ay) * j / k))
    return dense


class Road:
    """One edge of the network, ready to be built: smoothed centre line, heights, section."""

    def __init__(self, edge):
        self.id = edge["id"]
        self.cls = edge["cls"]
        self.level = edge.get("level", 0)
        self.name = edge.get("name")
        self.a, self.b = edge["a"], edge["b"]
        self.section = SECTIONS[self.cls]
        self.half = self.section["carriage"] / 2.0
        self.sidewalk = self.section["sidewalk"]
        src = np.asarray(edge["pts"], dtype=np.float64)
        xy = np.asarray(smooth_centre(edge["pts"], self.cls, bool(edge.get("curve"))), dtype=np.float64)
        # heights: carried over from the profile by distance along the line
        src_s = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(src[:, 0]), np.diff(src[:, 1])))])
        seg = np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1]))
        self.s = np.concatenate([[0.0], np.cumsum(seg)])
        self.length = float(self.s[-1])
        z = np.interp(self.s / max(self.length, 1e-6) * src_s[-1], src_s, src[:, 2])
        self.xy = xy
        self.z = z
        # unit tangent at each point (average of the two segments), and its left normal
        d = np.diff(xy, axis=0) / np.maximum(seg, 1e-9)[:, None]
        t = np.vstack([d[0], d[:-1] + d[1:], d[-1]])
        t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-9)[:, None]
        self.tangent = t
        self.normal = np.stack([-t[:, 1], t[:, 0]], axis=1)
        # mitre: an offset line keeps its distance on both sides of a bend
        cos_half = np.ones(len(xy))
        cos_half[1:-1] = np.clip((d[:-1] * t[1:-1]).sum(axis=1), 0.5, 1.0)
        self.mitre = 1.0 / cos_half
        self.trim = [0.0, 0.0]          # how far each end lies inside its junction, set by Junction

    def offset(self, d):
        """Points of the line d metres to the left of the centre (negative: right)."""
        return self.xy + self.normal * (d * self.mitre)[:, None]

    def at(self, s):
        """Position, tangent and left normal at distance s along the road."""
        s = min(max(s, 0.0), self.length)
        i = int(np.searchsorted(self.s, s, side="right")) - 1
        i = min(max(i, 0), len(self.s) - 2)
        f = (s - self.s[i]) / max(self.s[i + 1] - self.s[i], 1e-9)
        p = self.xy[i] + (self.xy[i + 1] - self.xy[i]) * f
        t = self.xy[i + 1] - self.xy[i]
        t = t / max(math.hypot(t[0], t[1]), 1e-9)
        return p, t, np.array([-t[1], t[0]])

    def heading(self, at_start, reach=9.0):
        """Unit direction leaving the given end, judged a few metres along so a wobble at the node is ignored."""
        if at_start:
            p, _, _ = self.at(min(reach, self.length))
            v = p - self.xy[0]
        else:
            p, _, _ = self.at(max(self.length - reach, 0.0))
            v = p - self.xy[-1]
        return v / max(math.hypot(v[0], v[1]), 1e-9)


def band(road, d0, d1, s0=None, s1=None):
    """Quads covering the band between two offsets of a road, optionally only between two distances."""
    left, right = road.offset(d0), road.offset(d1)
    quads = []
    if s0 is None and s1 is None:
        for i in range(len(left) - 1):
            quads.append([tuple(left[i]), tuple(right[i]), tuple(right[i + 1]), tuple(left[i + 1])])
        return quads
    s0 = 0.0 if s0 is None else s0
    s1 = road.length if s1 is None else s1
    if s1 - s0 < 0.05:
        return quads
    stops = [s0] + [float(s) for s in road.s if s0 < s < s1] + [s1]
    rows = []
    for s in stops:
        p, _, n = road.at(s)
        i = min(int(np.searchsorted(road.s, s)), len(road.s) - 1)
        m = road.mitre[i] if abs(road.s[i] - s) < 1e-6 else 1.0
        rows.append((p + n * d0 * m, p + n * d1 * m))
    for (a0, a1), (b0, b1) in zip(rows[:-1], rows[1:]):
        quads.append([tuple(a0), tuple(a1), tuple(b1), tuple(b0)])
    return quads


def disc(centre, radius, steps=28):
    return [(centre[0] + radius * math.cos(2 * math.pi * k / steps), centre[1] + radius * math.sin(2 * math.pi * k / steps))
            for k in range(steps)]


def ring(centre, r0, r1, steps=28):
    """An annulus as quads."""
    quads = []
    for k in range(steps):
        a0, a1 = 2 * math.pi * k / steps, 2 * math.pi * (k + 1) / steps
        quads.append([(centre[0] + r0 * math.cos(a0), centre[1] + r0 * math.sin(a0)),
                      (centre[0] + r1 * math.cos(a0), centre[1] + r1 * math.sin(a0)),
                      (centre[0] + r1 * math.cos(a1), centre[1] + r1 * math.sin(a1)),
                      (centre[0] + r0 * math.cos(a1), centre[1] + r0 * math.sin(a1))])
    return quads


def junction_polygons(node_xy, arms):
    """Corner pieces of one junction and how far each arm reaches into it.

    arms: list of (road, at_start). Sorted counter-clockwise by heading. Between two neighbouring arms lies a
    corner of a block: the left kerb line of one arm meets the right kerb line of the next. The corner is
    rounded: the piece between the arc and the sharp corner becomes carriageway, and a kerb band follows
    the arc. Returns (polygons as (kind, points), {arm index: trim distance})."""
    polys = []
    px, py = node_xy
    heads = [r.heading(at_start) for r, at_start in arms]
    order = sorted(range(len(arms)), key=lambda k: math.atan2(heads[k][1], heads[k][0]))
    trims = {k: 0.0 for k in range(len(arms))}
    if len(arms) < 2:
        return polys, trims
    for idx in range(len(order)):
        i, j = order[idx], order[(idx + 1) % len(order)]
        if i == j:
            continue
        di, dj = heads[i], heads[j]
        ri, rj = arms[i][0], arms[j][0]
        phi = math.atan2(di[0] * dj[1] - di[1] * dj[0], di[0] * dj[0] + di[1] * dj[1])
        if phi <= 0:
            phi += 2 * math.pi
        if phi > math.pi - 0.25 or phi < 0.12:
            continue                                   # the two arms run on as one line, or lie on each other
        ni = np.array([-di[1], di[0]])                 # left of arm i
        nj = np.array([-dj[1], dj[0]])
        a0 = np.array([px, py]) + ni * ri.half         # left kerb line of arm i
        b0 = np.array([px, py]) - nj * rj.half         # right kerb line of arm j
        den = di[0] * dj[1] - di[1] * dj[0]
        ta = ((b0[0] - a0[0]) * dj[1] - (b0[1] - a0[1]) * dj[0]) / den
        tb = ((b0[0] - a0[0]) * di[1] - (b0[1] - a0[1]) * di[0]) / den
        corner = a0 + di * ta
        radius = min(CORNER_RADIUS[ri.cls], CORNER_RADIUS[rj.cls])
        tangent = radius / math.tan(phi / 2.0)
        room = min(ri.length * 0.45 - ta, rj.length * 0.45 - tb, 30.0)
        if room < 0.5:
            trims[i] = max(trims[i], max(ta, 0.0))
            trims[j] = max(trims[j], max(tb, 0.0))
            continue
        if tangent > room:
            tangent = room
            radius = tangent * math.tan(phi / 2.0)
        pa, pb = corner + di * tangent, corner + dj * tangent
        bis = di + dj
        bis /= max(math.hypot(bis[0], bis[1]), 1e-9)
        centre = corner + bis * (radius / math.sin(phi / 2.0))
        ang_a = math.atan2(pa[1] - centre[1], pa[0] - centre[0])
        sweep = math.pi - phi                          # from arm i's tangent point to arm j's, clockwise
        steps = max(3, int(math.ceil(sweep * radius / 0.7)))
        arc = [(centre[0] + radius * math.cos(ang_a - sweep * k / steps), centre[1] + radius * math.sin(ang_a - sweep * k / steps))
               for k in range(steps + 1)]
        polys.append(("road", [tuple(corner)] + arc))
        inner = max(radius - CURB_W, 0.05)
        for k in range(steps):
            a_0, a_1 = ang_a - sweep * k / steps, ang_a - sweep * (k + 1) / steps
            polys.append(("curb", [(centre[0] + radius * math.cos(a_0), centre[1] + radius * math.sin(a_0)),
                                   (centre[0] + radius * math.cos(a_1), centre[1] + radius * math.sin(a_1)),
                                   (centre[0] + inner * math.cos(a_1), centre[1] + inner * math.sin(a_1)),
                                   (centre[0] + inner * math.cos(a_0), centre[1] + inner * math.sin(a_0))]))
        trims[i] = max(trims[i], ta + tangent)
        trims[j] = max(trims[j], tb + tangent)
    return polys, trims


def stripe(road, s0, s1, d0, d1):
    """One rectangle of paint between two distances along the road and two offsets."""
    p0, _, n0 = road.at(s0)
    p1, _, n1 = road.at(s1)
    return [tuple(p0 + n0 * d0), tuple(p0 + n0 * d1), tuple(p1 + n1 * d1), tuple(p1 + n1 * d0)]


def line(road, s0, s1, offset, width=0.12, dash=None):
    """A painted line at an offset from the centre; dash = (on, off) lengths, or None for a solid line."""
    out = []
    if s1 - s0 < 0.5:
        return out
    if dash is None:
        stops = [s0] + [float(s) for s in road.s if s0 + 0.2 < s < s1 - 0.2] + [s1]
        for a, b in zip(stops[:-1], stops[1:]):
            out.append(stripe(road, a, b, offset - width / 2, offset + width / 2))
        return out
    on, off = dash
    # dashes are counted from the road's own start, not from where this stretch of line begins: two pieces of
    # one road built separately (a sector's part and a bridge's deck) then carry the same rhythm
    period, first = on + off, off / 2 + 0.5
    s = math.ceil((s0 - first) / period) * period + first
    while s + on <= s1:
        out.append(stripe(road, s, s + on, offset - width / 2, offset + width / 2))
        s += on + off
    return out


def markings(road, degree_a, degree_b, through=(False, False)):
    """Paint for one road: centre line, lane lines, edge lines, and at real junctions a crosswalk and a
    stop bar. Returns [(kind, polygon)]. through: at that end the road runs on as another road of its own
    class (a junction of two): its lines start at the end itself, so they meet the next road's (they used to
    start half a metre in, a metre without paint at every such junction)."""
    out = []
    cls, half = road.cls, road.half
    if cls in ("alley", "tunnel") or road.length < 12.0:
        return out
    junction_a, junction_b = degree_a >= 3, degree_b >= 3
    urban = cls in ("street", "arterial", "bridge")
    start = road.trim[0] + (CROSSWALK_M + 3.0 if junction_a and urban else (0.0 if through[0] else 0.5))
    end = road.length - road.trim[1] - (CROSSWALK_M + 3.0 if junction_b and urban else (0.0 if through[1] else 0.5))
    if end - start < 4.0:
        return out
    lanes = road.section["lanes"]
    median = road.section["median"]
    if cls == "freeway":
        inner = median / 2 + 0.6
        lane_w = 3.65
        for side in (1.0, -1.0):
            out += [("yellow", q) for q in line(road, start, end, side * inner, 0.15)]
            for k in range(1, lanes // 2):
                out += [("white", q) for q in line(road, start, end, side * (inner + k * lane_w), 0.12, (3.0, 9.0))]
            out += [("white", q) for q in line(road, start, end, side * (inner + (lanes // 2) * lane_w), 0.15)]
        return out
    if cls == "ramp":
        out += [("yellow", q) for q in line(road, start, end, half - 1.2, 0.12)]
        out += [("white", q) for q in line(road, start, end, -(half - 1.2), 0.12)]
        return out
    # two-way urban road: double yellow in the middle
    for off in (-0.13, 0.13):
        out += [("yellow", q) for q in line(road, start, end, off, 0.11)]
    if lanes >= 4:
        lane_w = 3.4
        for side in (1.0, -1.0):
            out += [("white", q) for q in line(road, start, end, side * lane_w, 0.11, (3.0, 9.0))]
    if cls == "street":
        # parking lane line on both sides
        for side in (1.0, -1.0):
            out += [("white", q) for q in line(road, start + 2.0, end - 2.0, side * (half - 2.5), 0.10)]
    # crosswalks (bars along the road) and stop bars, where the road meets a junction
    for at_start, is_junction in ((True, junction_a), (False, junction_b)):
        if not is_junction:
            continue
        t = road.trim[0] if at_start else road.trim[1]
        near = t + 0.4
        far = near + CROSSWALK_M
        if far + 2.0 > road.length / 2:
            continue
        to_s = (lambda v: v) if at_start else (lambda v: road.length - v)
        r = -half + 0.5
        while r + 0.6 <= half - 0.5:
            a, b = sorted((to_s(near), to_s(far)))
            out.append(("white", stripe(road, a, b, r, r + 0.6)))
            r += 1.2
        a, b = sorted((to_s(far + 1.2), to_s(far + 1.8)))
        # the stop bar spans the lanes that arrive at the junction: right of their own direction of travel
        lo, hi = (0.3, half - 0.3) if at_start else (-(half - 0.3), -0.3)
        out.append(("white", stripe(road, a, b, lo, hi)))
    return out


def street_polygons(roads, node_xy):
    """All flat polygons of the streets among `roads` (level 0). Returns [(kind, points, road id or None)].
    Also sets each road's trim distances."""
    polys = []
    arms_at = {}
    for r in roads:
        arms_at.setdefault(r.a, []).append((r, True))
        arms_at.setdefault(r.b, []).append((r, False))
    # junction corners first: they tell every road where its junctions begin
    for node, arms in arms_at.items():
        if node not in node_xy:
            continue
        corner, trims = junction_polygons(node_xy[node], arms)
        polys += [(kind, pts, None) for kind, pts in corner]
        for k, (road, at_start) in enumerate(arms):
            road.trim[0 if at_start else 1] = max(road.trim[0 if at_start else 1], trims[k])
        if len(arms) >= 2:
            # the arms' strips already cover the crossing; the disc rounds the outside of a bend and fills the
            # sliver where a wide road changes direction at the junction. It takes the second widest arm: wide
            # enough for that bend, yet not bulging past the kerb when a wide road ends at a narrower street
            halves = sorted((r.half for r, _ in arms), reverse=True)
            polys.append(("road", disc(node_xy[node], halves[1] * 0.98), None))      # second widest arm
        elif arms[0][0].cls == "street" and arms[0][0].length > 30.0 and node not in STRUCTURE_ENDS:
            # dead end: a turning circle with its own kerb and sidewalk
            centre = node_xy[node]
            polys.append(("road", disc(centre, BULB_RADIUS, 36), None))
            polys += [("curb", q, None) for q in ring(centre, BULB_RADIUS, BULB_RADIUS + CURB_W, 36)]
            polys += [("sidewalk", q, None) for q in ring(centre, BULB_RADIUS + CURB_W, BULB_RADIUS + 2.6, 36)]
    for r in roads:
        polys += [("road", q, r.id) for q in band(r, r.half, -r.half)]
        # a bend tighter than the carriageway is wide folds the strip's inner edge over itself, and whoever
        # triangulates throws folded pieces away: discs along such a bend keep the carriageway whole
        step = np.diff(r.xy, axis=0)
        run = np.hypot(step[:, 0], step[:, 1])
        for i in range(1, len(r.xy) - 1):
            turn = abs(math.atan2(step[i - 1][0] * step[i][1] - step[i - 1][1] * step[i][0],
                                  step[i - 1][0] * step[i][0] + step[i - 1][1] * step[i][1]))
            if turn > 1e-3 and (run[i - 1] + run[i]) / 2.0 / turn < r.half * 1.7:
                polys.append(("road", disc((float(r.xy[i][0]), float(r.xy[i][1])), r.half * 0.995, 20), r.id))
        if r.sidewalk > 0:
            for side in (1.0, -1.0):
                polys += [("curb", q, r.id) for q in band(r, side * r.half, side * (r.half + CURB_W))]
                polys += [("sidewalk", q, r.id) for q in band(r, side * (r.half + CURB_W), side * (r.half + r.sidewalk))]
    degree = {n: len(a) for n, a in arms_at.items()}
    # where exactly two roads of one class meet end to end the road simply runs on: no gap in its median or paint
    runs_on = {n for n, a in arms_at.items() if len(a) == 2 and a[0][0].cls == a[1][0].cls and n not in STRUCTURE_ENDS}
    for r in roads:
        if r.section["median"] > 0:
            m = r.section["median"] / 2
            s0 = r.trim[0] + (0.0 if r.a in runs_on else 8.0)
            s1 = r.length - r.trim[1] - (0.0 if r.b in runs_on else 8.0)
            polys += [("median", q, r.id) for q in band(r, m, -m, s0, s1)]
    for r in roads:
        polys += [(kind, q, r.id) for kind, q in markings(r, degree.get(r.a, 1), degree.get(r.b, 1), (r.a in runs_on, r.b in runs_on))]
    return polys


STRUCTURE_ENDS = set()      # nodes where a road runs on into a tunnel or onto a viaduct (sector_roads fills it):
                            # a street that only seems to end there gets no turning circle


def sector_roads(net, box, margin=80.0):
    """The roads that shape a sector's ground: every road on the ground within `margin` metres of its box.
    The mesher and the planners must all use this one list, so they agree on every height."""
    west, east, south, north = box
    STRUCTURE_ENDS.update(n for e in net["edges"] if e["level"] != 0 or e["cls"] == "tunnel" for n in (e["a"], e["b"]))
    roads = []
    for e in net["edges"]:
        if e["level"] != 0 or e["cls"] == "tunnel":
            continue
        xs = [p[0] for p in e["pts"]]
        ys = [p[1] for p in e["pts"]]
        if max(xs) < west - margin or min(xs) > east + margin or max(ys) < south - margin or min(ys) > north + margin:
            continue
        roads.append(Road(e))
    return roads


def ground_heights(field, pts, base_ground):
    """Height of the street surface at each point (HeightField), or of the natural ground (the terrain
    base's "ground" raster) where no road is near. Sidewalks and block ground stand CURB_M above this."""
    from common import bilinear
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    z, _ = field.at(pts)
    if np.isnan(z).any():
        z = np.where(np.isnan(z), bilinear(base_ground, pts[:, 0], pts[:, 1]), z)
    return z


ROAD_OWN_M = 4.0            # beyond a kerb the held lines (levels, relief, seams) come in over this distance
PIN_M = 2.0                 # ...except within this distance of a piece of a line marked "pin" (a seam) that lies on
PIN_NEAR_M = 0.6            # a carriageway: both ends on it, or one end on it and the other, beyond the kerb, no
                            # further than PIN_NEAR_M from the height the roads give there. That piece holds


class HeightField:
    """Height of the street surface anywhere near the given roads: at a point, the roads around it are
    weighted by how close their centre lines pass, so a point on a road takes that road's profile and a
    point inside a block is carried by the streets around the block.

    On a carriageway the roads alone decide; a sector's held lines (its levels, relief, seams) come in over
    ROAD_OWN_M beyond the kerb. (Until 2026-11-18 they counted everywhere: a held line a metre from a kerb
    outweighs the road itself 2.5 m away, so a level kept along a sector's side bent the lane where the side
    crosses a street, 0.4 m on the shore road between NH1 and NH3, and one stray sample on a freeway's
    carriageway stood as a bump 0.8 m high. And two sectors that meet across a street now take the street's
    surface from the same roads, whatever each holds beside it.) A level marked "pin" (the seams along the
    sector's outline) holds on a carriageway too, within PIN_M of each piece of its lines that lies on a carriageway
    (see PIN_NEAR_M): both sectors along a seam have the seam's heights there, and the roads each of them sees may give
    a few decimetres' difference on the outer lanes of a freeway with a hill street beside it (FN1 and FN2 stood
    0.35 m apart across one). A piece with one end beyond the kerb and far from the roads' height does not hold: it is a
    ramp from the road up the bank behind it, and held, it stood as a spike 1.5 m high in the alley between NH2 and FN0.)"""

    def __init__(self, roads, power=3.0, reach=260.0, levels=None):
        """levels: a sector's "levels", ground held at one height along given lines (a walled yard, a
        terrace): [{"z": street-surface height, "lines": [[(x, y), ...], ...]}], or at a height of its own at
        every point of a line: {"profile": [[(x, y, z), ...], ...]} (what sectors.levels() makes of a sector's
        "relief" and "over_tunnels"). They pull the ground as roads do."""
        self.power, self.reach = power, reach
        self.lines = [(r.xy, r.z) for r in roads]
        self.halves = [float(r.half) for r in roads]            # the first len(roads) lines are the roads
        self.pins = []                                          # pieces (a, b) of pinned lines, both ends on a carriageway
        for level in levels or []:
            for line in level.get("profile", []):
                xyz = np.asarray(line, dtype=np.float64)
                if level.get("pin") and roads:
                    on = [min(self._off(r, q) for r in roads) < 0.0 for q in xyz[:, :2]]
                    if any(on):
                        base = HeightField(roads, power, reach).at(xyz[:, :2])[0]
                        near = [on[k] or abs(xyz[k, 2] - base[k]) < PIN_NEAR_M for k in range(len(xyz))]
                        self.pins += [(xyz[k, :2].copy(), xyz[k + 1, :2].copy()) for k in range(len(xyz) - 1)
                                      if (on[k] or on[k + 1]) and near[k] and near[k + 1]]
                self.lines.append((xyz[:, :2].copy(), xyz[:, 2].copy()))
            for line in level.get("lines", []):
                xy = np.asarray(line, dtype=np.float64)
                self.lines.append((xy, np.full(len(xy), float(level["z"]))))

    @staticmethod
    def _off(road, q):
        """Metres from the point to the road's kerb (negative on its carriageway)."""
        a, b = road.xy[:-1], road.xy[1:]
        ab = b - a
        t = np.clip(((q - a) * ab).sum(axis=1) / np.maximum((ab ** 2).sum(axis=1), 1e-9), 0.0, 1.0)
        return float(np.sqrt((((a + ab * t[:, None]) - q) ** 2).sum(axis=1)).min()) - float(road.half)

    def at(self, pts):
        """pts: (n, 2) array. Returns heights (n,) and distance to the nearest centre line (n,)."""
        pts = np.asarray(pts, dtype=np.float64)
        num = np.zeros(len(pts))
        den = np.zeros(len(pts))
        num_road = np.zeros(len(pts))
        den_road = np.zeros(len(pts))
        gap = np.full(len(pts), 1e9)                            # metres to the nearest kerb; negative on a carriageway
        pin = np.full(len(pts), 1e9)                            # metres to the nearest pinned piece
        for a, b in self.pins:
            ab = b - a
            t = np.clip(((pts - a) * ab).sum(axis=1) / max(float((ab ** 2).sum()), 1e-9), 0.0, 1.0)
            pin = np.minimum(pin, np.sqrt((((a + ab * t[:, None]) - pts) ** 2).sum(axis=1)))
        held = len(self.lines) > len(self.halves)
        nearest = np.full(len(pts), 1e9)
        for index, (xy, z) in enumerate(self.lines):
            lo, hi = xy.min(axis=0) - self.reach, xy.max(axis=0) + self.reach
            sel = np.nonzero((pts[:, 0] >= lo[0]) & (pts[:, 0] <= hi[0]) & (pts[:, 1] >= lo[1]) & (pts[:, 1] <= hi[1]))[0]
            if not len(sel):
                continue
            p = pts[sel]
            a, b = xy[:-1], xy[1:]
            ab = b - a
            den_seg = np.maximum((ab ** 2).sum(axis=1), 1e-9)
            best_d = np.full(len(sel), 1e18)
            best_z = np.zeros(len(sel))
            for k in range(len(a)):                      # one segment at a time keeps memory flat
                t = np.clip(((p - a[k]) * ab[k]).sum(axis=1) / den_seg[k], 0.0, 1.0)
                q = a[k] + ab[k] * t[:, None]
                d = ((p - q) ** 2).sum(axis=1)
                better = d < best_d
                best_d[better] = d[better]
                best_z[better] = (z[k] + (z[k + 1] - z[k]) * t)[better]
            d = np.sqrt(best_d)
            w = np.where(d < self.reach, 1.0 / (d + 0.5) ** self.power, 0.0)
            num[sel] += w * best_z
            den[sel] += w
            nearest[sel] = np.minimum(nearest[sel], d)
            if held and index < len(self.halves):
                num_road[sel] += w * best_z
                den_road[sel] += w
                gap[sel] = np.minimum(gap[sel], d - self.halves[index])
        out = np.where(den > 0, num / np.maximum(den, 1e-30), np.nan)
        if held:
            own = (den_road > 0) & (gap < ROAD_OWN_M)
            t = np.clip(gap / ROAD_OWN_M, 0.0, 1.0)
            t = t * t * (3.0 - 2.0 * t)
            t = np.maximum(t, np.clip(1.0 - pin / PIN_M, 0.0, 1.0))
            road = num_road / np.maximum(den_road, 1e-30)
            out = np.where(own, road + (out - road) * t, out)
        return out, nearest
