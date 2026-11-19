"""Traces the road ribbons of the drawn map into a graph of centre lines.

  python -P Tools/bay/trace_network.py

Input:  Saved/Bay/masks.npz (from read_map.py)
Output: Saved/Bay/network_raw.json    nodes (id, x, y) and edges (a, b, kind, width, points) in metres
        Saved/Bay/network_raw.png     the graph drawn over the class picture, full map resolution

The ribbons are thinned to one-pixel lines (Zhang-Suen), the lines are walked into a graph, and the graph is
tidied: whiskers pruned, crowded nodes merged, pass-through nodes dissolved, lines simplified. Each edge keeps
the kind of ribbon it was drawn with (street, avenue, bridge, tunnel) and the ribbon's width. This is the map
as drawn; design_network.py turns it into the road network that gets built.
"""
import math
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import M_PER_PX, data_path, save_json, to_world

SPUR_MIN_M = 28.0          # dead ends shorter than this (or than 1.3 road widths) are thinning whiskers
MERGE_M = 13.0             # nodes joined by an edge shorter than this collapse into one
SIMPLIFY_M = 2.2           # Douglas-Peucker tolerance for the centre lines
KINDS = ("street", "avenue", "bridge", "tunnel")

NB = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]   # P2..P9, clockwise from north


def thin(mask):
    """Zhang-Suen thinning of a boolean image; returns a one-pixel-wide skeleton."""
    img = np.pad(mask.astype(np.uint8), 1)
    while True:
        removed = 0
        for step in (0, 1):
            p = [img[1 + dy:img.shape[0] - 1 + dy, 1 + dx:img.shape[1] - 1 + dx] for dy, dx in NB]
            centre = img[1:-1, 1:-1]
            b = sum(p)
            a = sum(((p[i] == 0) & (p[(i + 1) % 8] == 1)).astype(np.uint8) for i in range(8))
            cond = (centre == 1) & (b >= 2) & (b <= 6) & (a == 1)
            if step == 0:
                cond &= (p[0] * p[2] * p[4] == 0) & (p[2] * p[4] * p[6] == 0)
            else:
                cond &= (p[0] * p[2] * p[6] == 0) & (p[0] * p[4] * p[6] == 0)
            n = int(cond.sum())
            if n:
                centre[cond] = 0
                removed += n
        if not removed:
            break
    return img[1:-1, 1:-1].astype(bool)


def simplify(points, tol):
    """Douglas-Peucker on a list of (x, y)."""
    if len(points) < 3:
        return list(points)
    pts = np.asarray(points, dtype=np.float64)
    keep = np.zeros(len(pts), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = pts[i], pts[j]
        ab = b - a
        norm = math.hypot(*ab)
        seg = pts[i + 1:j]
        if norm < 1e-9:
            d = np.hypot(*(seg - a).T)
        else:
            d = np.abs(ab[0] * (seg[:, 1] - a[1]) - ab[1] * (seg[:, 0] - a[0])) / norm
        k = int(np.argmax(d))
        if d[k] > tol:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return [tuple(p) for p in pts[keep]]


def length(points):
    return sum(math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1]) for i in range(len(points) - 1))


class Graph:
    def __init__(self):
        self.nodes = {}        # id -> [x, y]
        self.edges = {}        # id -> dict(a, b, kind, width, pts)
        self._next_node = 0
        self._next_edge = 0

    def add_node(self, x, y):
        self.nodes[self._next_node] = [float(x), float(y)]
        self._next_node += 1
        return self._next_node - 1

    def add_edge(self, a, b, kind, width, pts):
        self.edges[self._next_edge] = {"a": a, "b": b, "kind": kind, "width": float(width), "pts": [tuple(p) for p in pts]}
        self._next_edge += 1
        return self._next_edge - 1

    def incident(self):
        inc = {n: [] for n in self.nodes}
        for eid, e in self.edges.items():
            inc[e["a"]].append(eid)
            inc[e["b"]].append(eid)
        return inc

    def prune_spurs(self):
        """Drops short dead ends. Returns how many were removed."""
        inc = self.incident()
        gone = 0
        for n, eids in inc.items():
            if len(eids) != 1:
                continue
            e = self.edges.get(eids[0])
            if e is None or e["a"] == e["b"]:
                continue
            other = e["b"] if e["a"] == n else e["a"]
            if len(inc[other]) < 3:
                continue                     # only whiskers hanging off a junction
            if length(e["pts"]) < max(SPUR_MIN_M, 1.3 * e["width"]) and e["kind"] != "tunnel":
                del self.edges[eids[0]]
                gone += 1
        self.drop_orphans()
        return gone

    def drop_orphans(self):
        used = set()
        for e in self.edges.values():
            used.add(e["a"])
            used.add(e["b"])
        for n in list(self.nodes):
            if n not in used:
                del self.nodes[n]

    def merge_close(self):
        """Collapses edges shorter than MERGE_M (crowded junction pixels, offset crossings)."""
        merged = 0
        for eid in sorted(self.edges, key=lambda k: length(self.edges[k]["pts"])):
            e = self.edges.get(eid)
            if e is None or e["a"] == e["b"]:
                continue
            if length(e["pts"]) >= MERGE_M:
                break
            a, b = e["a"], e["b"]
            inc = self.incident()
            if len(inc[a]) == 1 or len(inc[b]) == 1:
                continue                     # a dead end's last stretch is not a junction to merge
            xa, ya = self.nodes[a]
            xb, yb = self.nodes[b]
            # the merged node sits at the heavier junction, or between the two
            wa, wb = len(inc[a]), len(inc[b])
            self.nodes[a] = [(xa * wa + xb * wb) / (wa + wb), (ya * wa + yb * wb) / (wa + wb)]
            del self.edges[eid]
            for other in self.edges.values():
                if other["a"] == b:
                    other["a"] = a
                if other["b"] == b:
                    other["b"] = a
            del self.nodes[b]
            merged += 1
        # edges now start and end at their node's new position
        for e in self.edges.values():
            e["pts"][0] = tuple(self.nodes[e["a"]])
            e["pts"][-1] = tuple(self.nodes[e["b"]])
        # a loop that collapsed onto one node with no extent is noise
        for eid in [k for k, e in self.edges.items() if e["a"] == e["b"] and length(e["pts"]) < 3 * MERGE_M]:
            del self.edges[eid]
        self.drop_orphans()
        return merged

    def bridge_gaps(self, passable):
        """Joins a dead end to the road it visibly continues into. A ribbon's outline, a change of colour
        (street into bridge) or a label can cut the thinned line in two; the link is restored when the
        straight run from the dead end to the other piece stays on drawn road (passable) and roughly
        follows the dead end's heading. Returns how many links were made."""
        from common import to_pixel
        inc = self.incident()
        dead = [n for n, eids in inc.items() if len(eids) == 1]
        dead_set = set(dead)
        # every line vertex, to find the nearest road point: (x, y, edge id, index)
        pool = []
        for eid, e in self.edges.items():
            for i, (x, y) in enumerate(e["pts"]):
                pool.append((x, y, eid, i))
        px = np.array([p[0] for p in pool])
        py = np.array([p[1] for p in pool])

        def on_road(x0, y0, x1, y1):
            n = max(2, int(math.hypot(x1 - x0, y1 - y0) / 0.8))
            xs = np.linspace(x0, x1, n)
            ys = np.linspace(y0, y1, n)
            u, v = to_pixel(xs, ys)
            u = np.clip(u.astype(int), 0, passable.shape[1] - 1)
            v = np.clip(v.astype(int), 0, passable.shape[0] - 1)
            return float(passable[v, u].mean())

        made = 0
        for d in dead:
            if d not in self.nodes:
                continue
            inc = self.incident()
            if len(inc[d]) != 1:
                continue
            eid = inc[d][0]
            e = self.edges[eid]
            pts = e["pts"] if e["b"] == d else e["pts"][::-1]
            x, y = pts[-1]
            back = pts[max(0, len(pts) - 8)]
            hx, hy = x - back[0], y - back[1]
            hn = math.hypot(hx, hy)
            if hn < 1e-6:
                continue
            hx, hy = hx / hn, hy / hn
            dist = np.hypot(px - x, py - y)
            best = None
            for k in np.argsort(dist)[:400]:
                dk = float(dist[k])
                if dk > 70.0:
                    break
                cx, cy, ceid, ci = pool[k]
                if ceid not in self.edges:
                    continue
                if ceid == eid:
                    continue
                if dk < 1.0:
                    continue
                cosang = ((cx - x) * hx + (cy - y) * hy) / dk
                other = self.edges[ceid]
                is_end = ci in (0, len(other["pts"]) - 1)
                end_node = (other["a"] if ci == 0 else other["b"]) if is_end else None
                facing = end_node in dead_set
                limit = 70.0 if facing else 45.0
                if dk > limit or cosang < (0.35 if facing else 0.5):
                    continue
                if on_road(x, y, cx, cy) < 0.9:
                    continue
                score = dk * (0.6 if facing else 1.0) / max(cosang, 0.2)
                if best is None or score < best[0]:
                    best = (score, ceid, ci, end_node)
            if best is None:
                continue
            _, ceid, ci, end_node = best
            other = self.edges[ceid]
            if end_node is None:
                # split the other edge at that vertex
                mid = self.add_node(*other["pts"][ci])
                first, second = other["pts"][:ci + 1], other["pts"][ci:]
                a, b, kind, width = other["a"], other["b"], other["kind"], other["width"]
                del self.edges[ceid]
                self.add_edge(a, mid, kind, width, first)
                self.add_edge(mid, b, kind, width, second)
                end_node = mid
                # the pool's entries for the split edge are stale: later dead ends skip them
            if end_node == d:
                continue
            self.add_edge(d, end_node, e["kind"], e["width"], [tuple(self.nodes[d]), tuple(self.nodes[end_node])])
            made += 1
        return made

    def dissolve_pass_through(self):
        """Joins the two edges at every node that has exactly two, when they are the same kind of road."""
        joined = 0
        while True:
            inc = self.incident()
            target = None
            for n, eids in inc.items():
                if len(eids) == 2 and eids[0] != eids[1]:
                    e1, e2 = self.edges[eids[0]], self.edges[eids[1]]
                    if e1["kind"] == e2["kind"] and e1["a"] != e1["b"] and e2["a"] != e2["b"]:
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
            del self.edges[i1]
            del self.edges[i2]
            del self.nodes[n]
            self.add_edge(start, end, e1["kind"], width, p1 + p2[1:])
            joined += 1


def build_graph(skel, kind_of, half_width):
    """Walks the skeleton into a graph. Pixels are joined by links: every straight neighbour, and a diagonal
    neighbour only when no straight neighbour already leads to it. A pixel with two links is part of a line;
    any other pixel is a junction or an end. Each link ends up in exactly one edge."""
    sk = np.pad(skel, 1)
    ys, xs = np.nonzero(skel)
    pix = list(zip(ys.tolist(), xs.tolist()))

    def on(y, x):
        return bool(sk[y + 1, x + 1])

    links = {}
    for y, x in pix:
        out = [(y + dy, x + dx) for dy, dx in ((-1, 0), (0, 1), (1, 0), (0, -1)) if on(y + dy, x + dx)]
        for dy, dx in ((-1, 1), (1, 1), (1, -1), (-1, -1)):
            if on(y + dy, x + dx) and not on(y + dy, x) and not on(y, x + dx):
                out.append((y + dy, x + dx))
        links[(y, x)] = out
    node_px = {p for p, out in links.items() if len(out) != 2}

    # junction pixels linked to each other form one node
    g = Graph()
    node_of = {}
    for p in sorted(node_px):
        if p in node_of:
            continue
        stack, group = [p], [p]
        node_of[p] = -1
        while stack:
            for q in links[stack.pop()]:
                if q in node_px and q not in node_of:
                    node_of[q] = -1
                    stack.append(q)
                    group.append(q)
        cy = sum(q[0] for q in group) / len(group)
        cx = sum(q[1] for q in group) / len(group)
        wx, wy = to_world(cx + 0.5, cy + 0.5)
        nid = g.add_node(wx, wy)
        for q in group:
            node_of[q] = nid

    def finish(path):
        """path: pixels from a node pixel to a node pixel (both included)."""
        a, b = node_of[path[0]], node_of[path[-1]]
        inner = path[1:-1]
        votes = [kind_of[y, x] for y, x in inner]
        counts = np.bincount(votes, minlength=len(KINDS) + 1)
        kind = KINDS[int(np.argmax(counts[1:]))] if counts[1:].sum() else "street"
        widths = [2.0 * half_width[y, x] * M_PER_PX for y, x in inner]
        pts = [tuple(g.nodes[a])]
        for y, x in inner:
            wx, wy = to_world(x + 0.5, y + 0.5)
            pts.append((float(wx), float(wy)))
        pts.append(tuple(g.nodes[b]))
        g.add_edge(a, b, kind, float(np.median(widths)), pts)

    walked = set()        # links already used, as (from, to)
    for p in sorted(node_px):
        for q in links[p]:
            if q in node_px or (p, q) in walked:
                continue
            path = [p, q]
            prev, cur = p, q
            while cur not in node_px:
                nxt = [r for r in links[cur] if r != prev]
                path.append(nxt[0])
                prev, cur = cur, nxt[0]
            walked.add((p, q))
            walked.add((path[-1], path[-2]))
            finish(path)

    # closed rings with no junction on them: give each one a node of its own
    seen = set()
    for p in pix:
        if p in node_px or p in seen:
            continue
        ring, prev, cur = [p], None, p
        closed = False
        while True:
            seen.add(cur)
            nxt = [r for r in links[cur] if r != prev]
            if not nxt or nxt[0] in node_px:
                break
            prev, cur = cur, nxt[0]
            if cur == p:
                closed = True
                break
            ring.append(cur)
        if closed and len(ring) > 20:
            wx, wy = to_world(p[1] + 0.5, p[0] + 0.5)
            node_of[p] = g.add_node(wx, wy)
            finish(ring + [p])
    return g


def draw(g, base, path):
    colours = {"street": (40, 40, 40), "avenue": (0, 120, 220), "bridge": (0, 0, 230), "tunnel": (200, 40, 160)}
    vis = (base.astype(np.float32) * 0.45 + 140).astype(np.uint8)
    S = 2
    vis = cv2.resize(vis, None, fx=S, fy=S, interpolation=cv2.INTER_NEAREST)
    from common import to_pixel
    for e in g.edges.values():
        px, py = to_pixel([p[0] for p in e["pts"]], [p[1] for p in e["pts"]])
        poly = np.stack([px * S, py * S], axis=1).round().astype(np.int32)
        cv2.polylines(vis, [poly], False, colours[e["kind"]], 2, cv2.LINE_AA)
    for n, (x, y) in g.nodes.items():
        px, py = to_pixel(x, y)
        cv2.circle(vis, (int(round(px * S)), int(round(py * S))), 4, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(vis, (int(round(px * S)), int(round(py * S))), 4, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.imwrite(path, vis)


def main():
    m = np.load(data_path("masks.npz"))
    net = m["street"] | m["avenue"] | m["bridge"] | m["tunnel"]
    net = cv2.morphologyEx(net.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    # small holes (lane lines, islands a few metres across) would become loops
    n, cc, stats, _ = cv2.connectedComponentsWithStats((1 - net).astype(np.uint8), connectivity=4)
    small = np.zeros(n, bool)
    small[1:] = stats[1:, cv2.CC_STAT_AREA] < 90
    net = (net > 0) | small[cc]
    half_width = cv2.distanceTransform(net.astype(np.uint8), cv2.DIST_L2, 5)

    kind_of = np.zeros(net.shape, np.uint8)
    for i, name in enumerate(KINDS):
        kind_of[m[name] & (kind_of == 0)] = i + 1
    kind_of[m["tunnel"]] = KINDS.index("tunnel") + 1

    skel = thin(net)
    print("TRACE skeleton: %d pixels" % int(skel.sum()))
    g = build_graph(skel, kind_of, half_width)
    print("TRACE raw graph: %d nodes, %d edges" % (len(g.nodes), len(g.edges)))

    for _ in range(6):
        a = g.prune_spurs()
        b = g.merge_close()
        c = g.dissolve_pass_through()
        print("TRACE tidy pass: %d whiskers, %d merges, %d joins" % (a, b, c))
        if a + b + c == 0:
            break
    passable = cv2.dilate(net.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))) > 0
    passable |= m["label"]
    for _ in range(3):
        made = g.bridge_gaps(passable)
        joins = g.dissolve_pass_through()
        print("TRACE gaps bridged: %d (then %d joins)" % (made, joins))
        if not made:
            break
    for e in g.edges.values():
        e["pts"] = simplify(e["pts"], SIMPLIFY_M)

    ids = {n: i for i, n in enumerate(sorted(g.nodes))}
    out = {"nodes": [{"id": ids[n], "x": round(g.nodes[n][0], 2), "y": round(g.nodes[n][1], 2)} for n in sorted(g.nodes)],
           "edges": [{"id": i, "a": ids[e["a"]], "b": ids[e["b"]], "kind": e["kind"], "width": round(e["width"], 1),
                      "length": round(length(e["pts"]), 1),
                      "pts": [[round(p[0], 2), round(p[1], 2)] for p in e["pts"]]}
                     for i, e in enumerate(g.edges.values())]}
    save_json("network_raw.json", out)

    base = cv2.imread(data_path("read_classes_full.png"))
    draw(g, base, data_path("network_raw.png"))
    total = {k: 0.0 for k in KINDS}
    for e in out["edges"]:
        total[e["kind"]] += e["length"]
    print("TRACE network: %d nodes, %d edges; km by kind: %s" % (
        len(out["nodes"]), len(out["edges"]), ", ".join("%s %.1f" % (k, v / 1000) for k, v in total.items())))
    inc = g.incident()
    print("TRACE node degrees:", np.bincount([len(v) for v in inc.values()]).tolist())


if __name__ == "__main__":
    main()
