"""Turns the traced map graph into the road network that gets built.

  python -P Tools/bay/design_network.py

Input:  Saved/Bay/network_raw.json   (trace_network.py: the map as drawn)
        Tools/bay/network_edits.py   (corrections: the user's marks and the designed interchanges)
Output: Saved/Bay/network.json       nodes (id, x, y) and edges (a, b, kind, cls, level, width, pts)
        Saved/Bay/tracado_corrigido.png  the network over the user's map (through preview_trace.py)

Steps: apply the edits, tidy what the drawing leaves untidy (stubs, slivers, crowded junctions), then give
every edge a road class. Classes:
  freeway    divided highway, no sidewalks        ramp       one-lane link of an interchange
  arterial   main avenue                          bridge     deck over water (carries its own class)
  street     ordinary street                      tunnel     below ground
  alley      narrow street or service lane
Edge "level": 0 on the ground, 1 on a structure that passes over other roads, -1 underground.
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import bilinear, data_path, load_json, save_json
from trace_network import Graph, length, simplify
import network_edits

SNAP_M = 14.0              # an added line's end joins an existing node or road within this distance
FROZEN_REACH_M = 7.0       # a frozen junction is recognised up to this far from where it was built
STUB_M = 26.0              # dead ends shorter than this are dropped
SLIVER_M = 85.0            # two roads between the same pair of junctions, both shorter than this, are one road


def point_in_polygon(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def closest_on_polyline(pts, x, y):
    """Returns (distance, segment index, parameter 0..1, point) of the closest point of a polyline."""
    best = (1e18, 0, 0.0, pts[0])
    for i in range(len(pts) - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        dx, dy = bx - ax, by - ay
        den = dx * dx + dy * dy
        t = 0.0 if den < 1e-12 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / den))
        qx, qy = ax + t * dx, ay + t * dy
        d = math.hypot(x - qx, y - qy)
        if d < best[0]:
            best = (d, i, t, (qx, qy))
    return best


# Optional properties an edit may give a road, carried through to network.json:
#   depth   a tunnel's floor below the ground, once it is down (metres). A tunnel with a depth gets the
#           profile of a cut-and-cover underpass: a straight ramp between two short vertical curves at each
#           end, level with the ground at its two mouths, then that depth below the line from mouth to mouth.
#   grade   steepest slope allowed on this road, instead of its class's
#   deck    a designed profile, [(x, y, z), ...]: the road is held at these heights at the samples nearest to
#           those points and at heights interpolated along it in between (an overpass that must clear a road
#           which is itself above the ground, a ramp climbing evenly to a bridge abutment). Its samples, ends
#           included, are pinned like a built road's; the roads around them adapt.
EXTRA_KEYS = ("depth", "grade", "hold", "quay", "deck")
RAMP_CURVE_M = 16.0             # length of the vertical curve at the top and at the foot of a tunnel's ramp


def ramp_depth(run, depth, grade):
    """How far below the ground a tunnel's road is, `run` metres from its nearer mouth."""
    ramp = depth / grade + RAMP_CURVE_M
    run = np.minimum(run, ramp)
    return np.where(run < RAMP_CURVE_M, grade * run * run / (2.0 * RAMP_CURVE_M),
                    np.where(run < ramp - RAMP_CURVE_M, grade * (run - RAMP_CURVE_M / 2.0),
                             depth - grade * (ramp - run) ** 2 / (2.0 * RAMP_CURVE_M)))


class Design(Graph):
    @classmethod
    def from_json(cls, net):
        g = cls()
        for n in net["nodes"]:
            g.nodes[n["id"]] = [n["x"], n["y"]]
        g._next_node = max(g.nodes) + 1
        for e in net["edges"]:
            eid = g.add_edge(e["a"], e["b"], e["kind"], e["width"], e["pts"])
            g.edges[eid]["cls"] = None
            g.edges[eid]["level"] = 0
        return g

    def add_edge(self, a, b, kind, width, pts, cls=None, level=0, name=None, curve=False):
        eid = Graph.add_edge(self, a, b, kind, width, pts)
        self.edges[eid].update({"cls": cls, "level": level, "name": name, "curve": curve})
        return eid

    # ---- finding things by position
    def nearest_node(self, x, y):
        best = (1e18, None)
        for n, (nx, ny) in self.nodes.items():
            d = math.hypot(nx - x, ny - y)
            if d < best[0]:
                best = (d, n)
        return best

    def nearest_edge(self, x, y, skip=()):
        best = (1e18, None, 0, 0.0, None)
        for eid, e in self.edges.items():
            if eid in skip:
                continue
            xs = [p[0] for p in e["pts"]]
            ys = [p[1] for p in e["pts"]]
            if x < min(xs) - 80 or x > max(xs) + 80 or y < min(ys) - 80 or y > max(ys) + 80:
                continue
            d, i, t, q = closest_on_polyline(e["pts"], x, y)
            if d < best[0]:
                best = (d, eid, i, t, q)
        return best

    def split_edge(self, eid, seg, t, q):
        """Puts a node on an edge at point q (on segment seg) and returns it."""
        e = self.edges[eid]
        pts = e["pts"]
        if seg == 0 and t < 1e-6:
            return e["a"]
        if seg == len(pts) - 2 and t > 1 - 1e-6:
            return e["b"]
        mid = self.add_node(*q)
        first = pts[:seg + 1] + [tuple(q)]
        second = [tuple(q)] + pts[seg + 1:]
        keep = {k: e[k] for k in ("kind", "width", "cls", "level", "name")}
        extra = {k: e[k] for k in EXTRA_KEYS if k in e}
        # a road drawn as a curve stays a curve on both sides of the new node (before 2026-11-14 the flag was
        # dropped, and a split curve was simplified and rounded like a traced street)
        curve = bool(e.get("curve", False))
        a, b = e["a"], e["b"]
        del self.edges[eid]
        for x, y, part in ((a, mid, first), (mid, b, second)):
            new = self.add_edge(x, y, keep["kind"], keep["width"], part, keep["cls"], keep["level"], keep["name"], curve)
            self.edges[new].update(extra)
        return mid

    def anchor(self, x, y, snap=SNAP_M, skip=()):
        """Node for the end of an added line: an existing node, a point on an existing road, or a new node."""
        d, n = self.nearest_node(x, y)
        if n is not None and d <= snap:
            return n
        d, eid, seg, t, q = self.nearest_edge(x, y, skip)
        if eid is not None and d <= snap:
            return self.split_edge(eid, seg, t, q)
        return self.add_node(x, y)

    # ---- edits
    def apply(self, edit):
        op = edit["op"]
        if op == "clear":
            poly = edit["polygon"]
            gone = []
            for eid, e in self.edges.items():
                pts = np.asarray(e["pts"])
                # resample so a long straight edge is judged along its whole run
                inside = 0
                total = 0
                for i in range(len(pts) - 1):
                    steps = max(1, int(math.hypot(*(pts[i + 1] - pts[i])) / 5.0))
                    for s in range(steps):
                        p = pts[i] + (pts[i + 1] - pts[i]) * (s + 0.5) / steps
                        total += 1
                        inside += point_in_polygon(p[0], p[1], poly)
                if total and inside / total >= edit.get("share", 0.5):
                    gone.append(eid)
            for eid in gone:
                del self.edges[eid]
            self.drop_orphans()
            return "cleared %d edges" % len(gone)
        if op == "remove":
            d, eid, _, _, _ = self.nearest_edge(*edit["at"])
            if eid is None or d > edit.get("within", 12.0):
                return "remove at %s: nothing within reach (nearest %.0f m)" % (edit["at"], d)
            del self.edges[eid]
            self.drop_orphans()
            return "removed 1 edge"
        if op == "set":
            d, eid, _, _, _ = self.nearest_edge(*edit["at"])
            if eid is None or d > edit.get("within", 12.0):
                return "set at %s: nothing within reach (nearest %.0f m)" % (edit["at"], d)
            for k in ("kind", "cls", "level", "name", "width"):
                if k in edit:
                    self.edges[eid][k] = edit[k]
            return "set 1 edge"
        if op == "along":
            # every road that runs along the given line (judged every few metres) takes the properties
            path = [tuple(p) for p in edit["pts"]]
            within, share = edit.get("within", 12.0), edit.get("share", 0.75)
            hit = 0
            for e in self.edges.values():
                if e["width"] < edit.get("min_width", 0.0):
                    continue
                near = total = 0
                pts = e["pts"]
                for i in range(len(pts) - 1):
                    steps = max(1, int(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) / 5.0))
                    for s in range(steps):
                        f = (s + 0.5) / steps
                        x, y = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f
                        total += 1
                        near += closest_on_polyline(path, x, y)[0] <= within
                if total and near / total >= share:
                    for k in ("kind", "cls", "level", "name", "width") + EXTRA_KEYS:
                        if k in edit:
                            e[k] = edit[k]
                    hit += 1
            return "set %d edges" % hit
        if op == "add":
            pts = [tuple(p) for p in edit["pts"]]
            snap = edit.get("snap", SNAP_M)
            a = self.anchor(*pts[0], snap=snap)
            b = self.anchor(*pts[-1], snap=snap)
            pts[0] = tuple(self.nodes[a])
            pts[-1] = tuple(self.nodes[b])
            eid = self.add_edge(a, b, edit.get("kind", "street"), edit.get("width", 20.0), pts,
                                edit.get("cls"), edit.get("level", 0), edit.get("name"), edit.get("curve", False))
            self.edges[eid].update({k: edit[k] for k in EXTRA_KEYS if k in edit})
            return "added 1 edge"
        if op == "move":
            d, n = self.nearest_node(*edit["at"])
            if n is None or d > edit.get("within", 15.0):
                return "move at %s: no node within reach" % (edit["at"],)
            self.nodes[n] = list(edit["to"])
            for e in self.edges.values():
                if e["a"] == n:
                    e["pts"][0] = tuple(edit["to"])
                if e["b"] == n:
                    e["pts"][-1] = tuple(edit["to"])
            return "moved 1 node"
        raise ValueError("unknown edit op %r" % op)

    # ---- tidying
    def drop_stubs(self):
        inc = self.incident()
        gone = 0
        for n, eids in inc.items():
            if len(eids) != 1:
                continue
            e = self.edges.get(eids[0])
            if e is None or e["kind"] == "tunnel" or e.get("cls") or e.get("name"):
                continue
            if length(e["pts"]) < STUB_M:
                del self.edges[eids[0]]
                gone += 1
        self.drop_orphans()
        return gone

    def drop_slivers(self):
        """Two short roads joining the same two junctions enclose nothing worth a block: keep the shorter."""
        pairs = {}
        for eid, e in self.edges.items():
            if e["a"] != e["b"]:
                pairs.setdefault((min(e["a"], e["b"]), max(e["a"], e["b"])), []).append(eid)
        gone = 0
        for eids in pairs.values():
            if len(eids) < 2:
                continue
            eids.sort(key=lambda k: length(self.edges[k]["pts"]))
            for eid in eids[1:]:
                e = self.edges[eid]
                if length(e["pts"]) < SLIVER_M and not e.get("cls") and not e.get("name"):
                    del self.edges[eid]
                    gone += 1
        # a short loop back onto its own junction is the same thing
        for eid in [k for k, e in self.edges.items() if e["a"] == e["b"] and length(e["pts"]) < 2 * SLIVER_M
                    and not e.get("cls")]:
            del self.edges[eid]
            gone += 1
        self.drop_orphans()
        return gone

    def dissolve_same(self):
        """Joins the two edges at a node with exactly two, when kind, class and level agree."""
        joined = 0
        while True:
            inc = self.incident()
            target = None
            for n, eids in inc.items():
                if len(eids) == 2 and eids[0] != eids[1]:
                    e1, e2 = self.edges[eids[0]], self.edges[eids[1]]
                    same = all(e1.get(k) == e2.get(k) for k in ("kind", "cls", "level", "name")) and \
                        not e1.get("curve") and not e2.get("curve")
                    if same and e1["a"] != e1["b"] and e2["a"] != e2["b"]:
                        target = (n, eids[0], eids[1])
                        break
            if target is None:
                return joined
            n, i1, i2 = target
            e1, e2 = self.edges[i1], self.edges[i2]
            p1 = e1["pts"] if e1["b"] == n else e1["pts"][::-1]
            start = e1["a"] if e1["b"] == n else e1["b"]
            p2 = e2["pts"] if e2["a"] == n else e2["pts"][::-1]
            end = e2["b"] if e2["a"] == n else e2["a"]
            l1, l2 = length(p1), length(p2)
            width = (e1["width"] * l1 + e2["width"] * l2) / max(l1 + l2, 1e-6)
            keep = (e1["kind"], width, p1 + p2[1:], e1.get("cls"), e1.get("level", 0), e1.get("name"))
            del self.edges[i1]
            del self.edges[i2]
            del self.nodes[n]
            self.add_edge(start, end, *keep)
            joined += 1


STRAIGHT_KINDS = ("street", "avenue")
STRAIGHT_TOL_M = 7.5        # a run of street that strays less than this from a straight line is a straight street
THROUGH_DEG = 20.0          # two arms of a junction this close to opposite are one street passing through
NODE_SHIFT_M = 14.0         # a junction never moves further than this when its streets are straightened


def regularize(g):
    """Makes streets that were drawn roughly straight exactly straight, and puts each junction where its
    straight streets cross. The trace follows the drawing's pixels, so a street arrives with small wobbles and
    its junctions a few metres off line; no real street grid is built that way. Streets that really curve
    (they stray further than STRAIGHT_TOL_M) are left as drawn. Only surface streets and avenues take part;
    ramps, bridges, tunnels and anything set by an edit keep their shape."""
    def eligible(e):
        return e["kind"] in STRAIGHT_KINDS and not e.get("cls") and e.get("level", 0) == 0 and e["a"] != e["b"]

    def arm_dir(eid, node):
        e = g.edges[eid]
        pts = e["pts"] if e["a"] == node else e["pts"][::-1]
        acc, target = 0.0, min(30.0, length(pts) * 0.6)
        for i in range(len(pts) - 1):
            seg = math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
            if acc + seg >= target:
                f = (target - acc) / max(seg, 1e-9)
                q = (pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f)
                break
            acc += seg
        else:
            q = pts[-1]
        v = (q[0] - pts[0][0], q[1] - pts[0][1])
        n = math.hypot(*v) or 1.0
        return v[0] / n, v[1] / n

    inc = g.incident()
    # which arm continues which, at every node
    through = {}
    for node, eids in inc.items():
        arms = [eid for eid in eids if eligible(g.edges[eid])]
        dirs = {eid: arm_dir(eid, node) for eid in arms}
        options = []
        for i in range(len(arms)):
            for j in range(i + 1, len(arms)):
                a, b = dirs[arms[i]], dirs[arms[j]]
                dev = math.degrees(math.acos(max(-1.0, min(1.0, -(a[0] * b[0] + a[1] * b[1])))))
                if dev < THROUGH_DEG:
                    options.append((dev, arms[i], arms[j]))
        used = set()
        for dev, e1, e2 in sorted(options):
            if e1 in used or e2 in used:
                continue
            used.update((e1, e2))
            through[(node, e1)] = e2
            through[(node, e2)] = e1

    # chains of edges that pass straight through their junctions
    chains, seen = [], set()
    for eid, e in g.edges.items():
        if eid in seen or not eligible(e):
            continue
        seq = [eid]
        seen.add(eid)
        ends = []
        for start in (e["a"], e["b"]):
            node, cur, path = start, eid, []
            while (node, cur) in through:
                nxt = through[(node, cur)]
                if nxt in seen:
                    break
                seen.add(nxt)
                path.append(nxt)
                en = g.edges[nxt]
                node = en["b"] if en["a"] == node else en["a"]
                cur = nxt
            ends.append(path)
        chains.append(ends[0][::-1] + seq + ends[1])

    def ordered_nodes(chain):
        """Nodes of a chain in order (first edge oriented by the second)."""
        if len(chain) == 1:
            e = g.edges[chain[0]]
            return [e["a"], e["b"]]
        e0, e1 = g.edges[chain[0]], g.edges[chain[1]]
        shared = e0["a"] if e0["a"] in (e1["a"], e1["b"]) else e0["b"]
        nodes = [e0["b"] if shared == e0["a"] else e0["a"], shared]
        for eid in chain[1:]:
            e = g.edges[eid]
            nodes.append(e["b"] if e["a"] == nodes[-1] else e["a"])
        return nodes

    def fit(points):
        p = np.asarray(points, dtype=np.float64)
        centre = p.mean(axis=0)
        _, _, vt = np.linalg.svd(p - centre)
        d = vt[0]
        dev = np.abs((p[:, 0] - centre[0]) * d[1] - (p[:, 1] - centre[1]) * d[0])
        return centre, d, dev

    lines_at = {}                  # node -> [(centre, direction)]
    straight_edges = set()
    runs = 0

    def settle(chain):
        """Fits one line to a chain; if it strays, cuts the chain at the junction that strays most."""
        nonlocal runs
        nodes = ordered_nodes(chain)
        pts, owner = [], []
        for k, eid in enumerate(chain):
            for q in g.edges[eid]["pts"]:
                pts.append(q[:2])
                owner.append(k)
        centre, d, dev = fit(pts)
        if dev.max() <= STRAIGHT_TOL_M:
            for n in nodes:
                lines_at.setdefault(n, []).append((centre, d))
            straight_edges.update(chain)
            runs += 1
            return
        if len(chain) == 1:
            return
        node_dev = [abs((g.nodes[n][0] - centre[0]) * d[1] - (g.nodes[n][1] - centre[1]) * d[0]) for n in nodes[1:-1]]
        cut = 1 + int(np.argmax(node_dev)) if node_dev else len(chain) // 2
        settle(chain[:cut])
        settle(chain[cut:])

    for chain in chains:
        settle(chain)

    moved, far = 0, 0
    for node, lines in lines_at.items():
        x, y = g.nodes[node]
        target = None
        if len(lines) >= 2:
            # the two lines that cross most squarely decide the junction
            best = None
            for i in range(len(lines)):
                for j in range(i + 1, len(lines)):
                    (c1, d1), (c2, d2) = lines[i], lines[j]
                    cross = d1[0] * d2[1] - d1[1] * d2[0]
                    if abs(cross) > 0.42 and (best is None or abs(cross) > abs(best[0])):
                        best = (cross, c1, d1, c2, d2)
            if best:
                cross, c1, d1, c2, d2 = best
                t = ((c2[0] - c1[0]) * d2[1] - (c2[1] - c1[1]) * d2[0]) / cross
                target = (c1[0] + d1[0] * t, c1[1] + d1[1] * t)
        if target is None:
            c, d = lines[0]
            t = (x - c[0]) * d[0] + (y - c[1]) * d[1]
            target = (c[0] + d[0] * t, c[1] + d[1] * t)
        shift = math.hypot(target[0] - x, target[1] - y)
        if shift > NODE_SHIFT_M:
            far += 1
            continue
        if shift > 0.01:
            moved += 1
        g.nodes[node] = [float(target[0]), float(target[1])]
    for eid, e in g.edges.items():
        a, b = tuple(g.nodes[e["a"]]), tuple(g.nodes[e["b"]])
        if eid in straight_edges:
            e["pts"] = [a, b]
        else:
            # a curved road keeps its shape; its ends follow their junctions, the shift fading along the road
            pts = [tuple(p[:2]) for p in e["pts"]]
            da = (a[0] - pts[0][0], a[1] - pts[0][1])
            db = (b[0] - pts[-1][0], b[1] - pts[-1][1])
            if abs(da[0]) + abs(da[1]) + abs(db[0]) + abs(db[1]) > 0.01:
                total = length(pts) or 1.0
                run, out = 0.0, []
                for i, p in enumerate(pts):
                    if i:
                        run += math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1])
                    wa = max(0.0, 1.0 - run / min(60.0, total))
                    wb = max(0.0, 1.0 - (total - run) / min(60.0, total))
                    out.append((p[0] + da[0] * wa + db[0] * wb, p[1] + da[1] * wa + db[1] * wb))
                out[0], out[-1] = a, b
                e["pts"] = out
    print("DESIGN straightened: %d straight runs covering %d edges; %d junctions moved, %d left alone (too far)" % (
        runs, len(straight_edges), moved, far))


def classify(e, over_water):
    """Road class from the ribbon's kind and drawn width, unless an edit already set one."""
    if e.get("cls"):
        return e["cls"]
    kind, width = e["kind"], e["width"]
    if kind == "tunnel":
        return "tunnel"
    if kind == "avenue":
        if width >= 40.0:
            return "freeway"
        return "arterial" if width >= 17.0 else "street"
    if kind == "bridge":
        if over_water:
            return "bridge"
        if width >= 36.0:
            return "freeway"
        return "arterial" if width >= 26.0 else "street"
    return "alley" if width < 11.0 else "street"


def resample(pts, step):
    """Points along a polyline no further apart than step, corners kept."""
    out = [tuple(pts[0])]
    for i in range(len(pts) - 1):
        ax, ay = pts[i]
        bx, by = pts[i + 1]
        n = max(1, int(math.ceil(math.hypot(bx - ax, by - ay) / step)))
        for k in range(1, n + 1):
            out.append((ax + (bx - ax) * k / n, ay + (by - ay) * k / n))
    return out


def solve_heights(edges, node_xy, ground, water, held=None):
    """Gives every edge a height profile.

    Each edge is sampled every few metres. A sample wants to sit on the ground (or at its deck or tunnel
    height) and wants to be level with its neighbours along the road; how strongly it holds to the ground
    depends on the road class. The result is then limited to each class's steepest grade. Junction samples
    are shared, so roads always meet at one height.
    held: {(x, y) rounded to cm: z} of samples that keep the height they were built with (freeze.py): they
    are not moved by the ground, by their neighbours or by the limit on slopes; the roads around them adapt.
    """
    from common import ROAD_MIN_Z, SECTIONS
    STEP = 8.0
    index = {}                      # node id -> sample index
    xs, ys, target, hold, grade = [], [], [], [], []

    def new_sample(x, y):
        xs.append(x)
        ys.append(y)
        target.append(0.0)
        hold.append(0.0)
        grade.append(1.0)
        return len(xs) - 1

    for n, (x, y) in node_xy.items():
        index[n] = new_sample(x, y)
    chains = []
    for e in edges:
        pts = resample(e["pts"], STEP)
        ids = [index[e["a"]]] + [new_sample(x, y) for x, y in pts[1:-1]] + [index[e["b"]]]
        chains.append(ids)
    xs, ys = np.array(xs), np.array(ys)
    target, hold, grade = np.array(target), np.array(hold), np.array(grade)
    gz = np.maximum(bilinear(ground, xs, ys), ROAD_MIN_Z)
    wet = bilinear(water.astype(np.float32), xs, ys) > 0.5

    # what each sample is asked for; where several edges share a junction the firmest request wins
    for e, ids in zip(edges, chains):
        sec = SECTIONS[e["cls"]]
        n = len(ids)
        t = np.linspace(0.0, 1.0, n)
        ids = np.array(ids)
        if e["cls"] == "tunnel" and e.get("depth"):
            # an underpass with a designed profile: held firmly, so it comes out as designed. Its depth is
            # counted from the straight line between the ground at its two mouths, not from the natural
            # ground above each point: what stands over an underpass is built ground (a promenade, a
            # square), level from mouth to mouth, whatever the terrain used to do there
            run = np.minimum(t, 1 - t) * e["length"]
            # a mouth held at the height it was built with counts at that height, not at the ground's; and a
            # long tunnel that runs under a valley between two higher mouths keeps its depth under the valley
            # floor, not under the line between the mouths (the Tunel do Vale, 2026-11-16: its south mouth stands
            # 12 m up a hillside, and measured from that line it came out above the valley floor)
            ends = []
            for k in (ids[0], ids[-1]):
                was = (held or {}).get((round(float(xs[k]), 2), round(float(ys[k]), 2)))
                ends.append(float(gz[k]) if was is None else float(was))
            line = np.minimum(ends[0] + (ends[1] - ends[0]) * t, np.maximum(gz[ids], min(ends)))
            want = line - ramp_depth(run, float(e["depth"]), float(e.get("grade", sec["grade"])))
            w = np.full(n, 8.0)
            w[[0, -1]] = 0.0                                   # the mouths take the street's height
        elif e["cls"] == "tunnel":
            run = np.minimum(t, 1 - t) * e["length"]
            depth = 13.0 * np.clip(run / 110.0, 0.0, 1.0) ** 2 * (3 - 2 * np.clip(run / 110.0, 0.0, 1.0))
            want, w = gz[ids] - depth, np.full(n, 1.0)
            w[[0, -1]] = 0.0                                   # the mouths take the street's height
        elif e.get("quay") is not None:
            # a street on a pier or a quay built out over the water on fill (an edit's quay=): held level at
            # that height. Over water the ground under it means nothing, and as a deck it would arch like a bridge
            want, w = np.full(n, float(e["quay"])), np.full(n, 1.0)
        elif e["level"] > 0:
            want, w = gz[ids] + 7.0, np.full(n, 0.6)
            w[[0, -1]] = 0.0
        elif wet[ids].mean() > 0.5:
            span = e["length"]
            rise = 3.0 if span < 120 else 9.0 if span < 320 else 22.0 if span < 650 else 38.0
            want, w = ROAD_MIN_Z + 1.0 + rise * np.sin(np.pi * t) ** 2, np.full(n, 0.5)
            w[[0, -1]] = 0.0
        else:
            # "hold" on an edge (an edit's hold=): how closely this road follows the ground, in place of its
            # class's value. Near 0 it is graded evenly from junction to junction, cutting through a shoulder
            # or filling a dip, as a street laid out across the flank of a hill is
            want, w = gz[ids], np.full(n, float(e.get("hold", sec["hold"])))
        better = w > hold[ids]
        target[ids[better]] = want[better]
        hold[ids[better]] = w[better]
        grade[ids] = np.minimum(grade[ids], float(e.get("grade", sec["grade"])))
    free = hold <= 0.0                 # only an end of a structure with nothing else there
    target[free] = gz[free]
    hold[free] = 0.05
    pin = np.zeros(len(xs), bool)
    pin_z = np.zeros(len(xs))
    for i in range(len(xs)) if held else ():
        was = held.get((round(float(xs[i]), 2), round(float(ys[i]), 2)))
        if was is not None:
            pin[i], pin_z[i] = True, was
    # an edit's deck= (a designed profile): the road's samples held at the heights given at a few points along it,
    # interpolated by distance along the road in between. Samples already held as built keep their height.
    for e, ids in zip(edges, chains):
        if not e.get("deck"):
            continue
        ids = np.array(ids)
        run = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(xs[ids]), np.diff(ys[ids])))])
        px, py = xs[ids], ys[ids]

        def run_of(cx, cy):
            """Distance along the road of the point of its line nearest to (cx, cy). (Until 2026-11-17 a given point
            was moved to the nearest sample: with points given closer together than the samples, a smooth curve came
            out in steps, 8 % of grade from one sample to the next on the training ground's access street.)"""
            ax, ay = px[:-1], py[:-1]
            dx, dy = px[1:] - ax, py[1:] - ay
            t = np.clip(((cx - ax) * dx + (cy - ay) * dy) / np.maximum(dx * dx + dy * dy, 1e-12), 0.0, 1.0)
            k = int(np.argmin(np.hypot(ax + dx * t - cx, ay + dy * t - cy)))
            return float(run[k] + t[k] * (run[k + 1] - run[k]))

        ctrl = sorted((run_of(cx, cy), float(cz)) for cx, cy, cz in e["deck"])
        zs = np.interp(run, [c[0] for c in ctrl], [c[1] for c in ctrl])
        free_ids = ~pin[ids]
        pin[ids[free_ids]], pin_z[ids[free_ids]] = True, zs[free_ids]
    # a built street that a new street now joins halfway is cut in two at the new junction, and its two pieces are
    # sampled afresh from there: their samples fall between the ones it was built with. Such a sample lies on the
    # straight piece between two held samples of that street (within 5 cm) and takes the height in between, so
    # the built street keeps its profile exactly
    if held:
        cells = {}
        for (hx, hy), hz in held.items():
            cells.setdefault((int(hx // 10.0), int(hy // 10.0)), []).append((hx, hy, hz))
        for i in np.nonzero(~pin)[0]:
            x, y = float(xs[i]), float(ys[i])
            cx, cy = int(x // 10.0), int(y // 10.0)
            near = [p for dx in (-1, 0, 1) for dy in (-1, 0, 1) for p in cells.get((cx + dx, cy + dy), ())
                    if (p[0] - x) ** 2 + (p[1] - y) ** 2 <= 81.0]
            best = None
            for j in range(len(near)):
                for k in range(j + 1, len(near)):
                    (px, py, pz), (qx, qy, qz) = near[j], near[k]
                    seg = math.hypot(qx - px, qy - py)
                    if seg < 0.5 or seg > 9.0:
                        continue
                    t = ((x - px) * (qx - px) + (y - py) * (qy - py)) / (seg * seg)
                    off = abs((x - px) * (qy - py) - (y - py) * (qx - px)) / seg
                    if 0.0 < t < 1.0 and off <= 0.05 and (best is None or seg < best[0]):
                        best = (seg, pz + (qz - pz) * t)
            if best is not None:
                pin[i], pin_z[i] = True, best[1]
    target[pin] = pin_z[pin]
    hold[pin] = 1e6

    # neighbours along the roads
    a = np.concatenate([np.array(c[:-1]) for c in chains])
    b = np.concatenate([np.array(c[1:]) for c in chains])
    dist = np.maximum(np.hypot(xs[a] - xs[b], ys[a] - ys[b]), 0.5)
    count = np.bincount(a, minlength=len(xs)) + np.bincount(b, minlength=len(xs))
    z = target.copy()
    for _ in range(600):
        total = np.bincount(a, weights=z[b], minlength=len(xs)) + np.bincount(b, weights=z[a], minlength=len(xs))
        z = (hold * target + total) / (hold + count)
    z[pin] = pin_z[pin]

    # steepest grade: the highest and the lowest surfaces within the limit of z, averaged
    limit = np.minimum(grade[a], grade[b]) * dist
    if pin.any():
        # a held sample does not give way, so the averaging below must find nothing to settle between it and
        # its neighbours: every free sample is first brought within reach of the held ones (no higher and no
        # lower than the slope limit allows, counted along the roads from each of them). Left out, the free
        # road keeps half of the disagreement and meets the held junction with a step of metres.
        hi = np.where(pin, pin_z, np.inf)
        lo = np.where(pin, pin_z, -np.inf)
        for _ in range(4000):
            was_hi, was_lo = hi.copy(), lo.copy()
            np.minimum.at(hi, a, hi[b] + limit)
            np.minimum.at(hi, b, hi[a] + limit)
            np.maximum.at(lo, a, lo[b] - limit)
            np.maximum.at(lo, b, lo[a] - limit)
            if np.array_equal(hi, was_hi) and np.array_equal(lo, was_lo):
                break
        both = np.isfinite(lo) & np.isfinite(hi) & (lo > hi)          # two held samples that disagree: split it
        z = np.where(pin, pin_z, np.where(both, (np.where(both, lo, 0.0) + np.where(both, hi, 0.0)) * 0.5, np.clip(z, lo, hi)))
    upper, lower = z.copy(), -z.copy()
    for it in range(4000):
        before = upper.sum() + lower.sum()
        for env in (upper, lower):
            np.minimum.at(env, a, env[b] + limit)
            np.minimum.at(env, b, env[a] + limit)
        if before - (upper.sum() + lower.sum()) < 1e-3:
            break
    z = (upper - lower) * 0.5
    z[pin] = pin_z[pin]
    steep = np.abs(z[a] - z[b]) / dist
    print("DESIGN heights: %d samples (%d held as built), %.1f .. %.1f m; grade p50 %.1f%% p95 %.1f%% max %.1f%% (%d limit passes)" % (
        len(z), int(pin.sum()), z.min(), z.max(), 100 * np.percentile(steep, 50), 100 * np.percentile(steep, 95), 100 * steep.max(), it + 1))
    profiles = [[(float(xs[i]), float(ys[i]), float(z[i])) for i in ids] for ids in chains]
    return profiles, {n: float(z[i]) for n, i in index.items()}


def main():
    g = Design.from_json(load_json("network_raw.json"))
    print("DESIGN raw: %d nodes, %d edges" % (len(g.nodes), len(g.edges)))
    for edit in network_edits.EDITS:
        if edit.get("when") == "after":
            continue
        note = g.apply(edit)
        print("DESIGN edit %-7s %-34s %s" % (edit["op"], edit.get("why", "")[:34], note))
    for _ in range(4):
        a, b, c = g.drop_stubs(), g.drop_slivers(), g.dissolve_same()
        print("DESIGN tidy: %d stubs, %d slivers, %d joins" % (a, b, c))
        if a + b + c == 0:
            break
    regularize(g)
    # edits that only say what a road is (its class) come after the straightening: a road whose class was set
    # by an edit keeps its traced shape, and these roads are part of the street grid like any other
    for edit in network_edits.EDITS:
        if edit.get("when") == "after":
            note = g.apply(edit)
            print("DESIGN edit %-7s %-34s %s" % (edit["op"], edit.get("why", "")[:34], note))
    # junctions of sectors already built go back to where those sectors were built (freeze.py): the
    # straightening refits a street's whole line whenever a road is added or removed at one of its ends
    frozen_path = data_path("frozen_nodes.json")
    if os.path.exists(frozen_path):
        back, worst = 0, 0.0
        for fx, fy in load_json("frozen_nodes.json"):
            d, n = g.nearest_node(fx, fy)
            if n is None or d > FROZEN_REACH_M or d < 1e-4:
                continue
            g.nodes[n] = [fx, fy]
            for e in g.edges.values():
                if e["a"] == n:
                    e["pts"][0] = (fx, fy)
                if e["b"] == n:
                    e["pts"][-1] = (fx, fy)
            back += 1
            worst = max(worst, d)
        print("DESIGN frozen: %d junctions of built sectors put back (furthest had moved %.2f m)" % (back, worst))

    base = np.load(data_path("terrain_base.npz"))
    water = base["water"]
    from common import to_pixel
    out_edges = []
    for eid, e in g.edges.items():
        # a road drawn as a curve by an edit (an oval, a loop ramp) keeps every point it was given
        pts = [tuple(p) for p in e["pts"]] if e.get("curve") else simplify(e["pts"], 1.5)
        xs = np.array([p[0] for p in e["pts"]])
        ys = np.array([p[1] for p in e["pts"]])
        # share of the edge that runs over water, sampled every few metres
        wet = []
        for i in range(len(xs) - 1):
            steps = max(1, int(math.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i]) / 4.0))
            for s in range(steps):
                u, v = to_pixel(xs[i] + (xs[i + 1] - xs[i]) * (s + 0.5) / steps, ys[i] + (ys[i + 1] - ys[i]) * (s + 0.5) / steps)
                u = min(max(int(u), 0), water.shape[1] - 1)
                v = min(max(int(v), 0), water.shape[0] - 1)
                wet.append(bool(water[v, u]))
        over = float(np.mean(wet)) if wet else 0.0
        cls = classify(e, over > 0.5)
        out_edges.append({"a": e["a"], "b": e["b"], "kind": e["kind"], "cls": cls, "level": e.get("level", 0),
                          "name": e.get("name"), "curve": bool(e.get("curve")), "width": round(e["width"], 1), "wet": round(over, 2),
                          "length": round(length(pts), 1), "pts": [[round(p[0], 2), round(p[1], 2)] for p in pts]})
        out_edges[-1].update({k: e[k] for k in EXTRA_KEYS if k in e})
    ids = {n: i for i, n in enumerate(sorted(g.nodes))}
    for i, e in enumerate(out_edges):
        e["id"] = i
        e["a"], e["b"] = ids[e["a"]], ids[e["b"]]
    node_xy = {ids[n]: tuple(g.nodes[n]) for n in g.nodes}
    held = {}
    if os.path.exists(data_path("frozen_heights.json")):
        held = {(round(x, 2), round(y, 2)): z for x, y, z in load_json("frozen_heights.json")}
    profiles, node_z = solve_heights(out_edges, node_xy, base["ground"], water, held)
    for e, prof in zip(out_edges, profiles):
        e["pts"] = [[round(x, 2), round(y, 2), round(z, 2)] for x, y, z in prof]
    net = {"nodes": [{"id": i, "x": round(node_xy[i][0], 2), "y": round(node_xy[i][1], 2), "z": round(node_z[i], 2)}
                     for i in sorted(node_xy)],
           "edges": out_edges}
    save_json("network.json", net)

    km = {}
    for e in out_edges:
        km[e["cls"]] = km.get(e["cls"], 0.0) + e["length"] / 1000.0
    deg = {}
    for e in out_edges:
        deg[e["a"]] = deg.get(e["a"], 0) + 1
        deg[e["b"]] = deg.get(e["b"], 0) + 1
    print("DESIGN network: %d nodes, %d edges, %d dead ends; km by class: %s" % (
        len(net["nodes"]), len(out_edges), sum(1 for v in deg.values() if v == 1),
        ", ".join("%s %.1f" % kv for kv in sorted(km.items()))))


if __name__ == "__main__":
    main()
