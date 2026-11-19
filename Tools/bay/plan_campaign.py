"""Puts the campaign's twenty operations on the Bay city's own streets and says where the city does not serve them.

  python -P Tools/bay/plan_campaign.py [operation numbers, e.g. 6 9 15]

The campaign (ASSETS TO USE/bay_city_3d) was written on a simplified model of the same city, in a frame of its own
(x east, z south, model metres). The Bay city was built from the drawn map and corrected as it went, so the model's
streets and the Bay's do not coincide: a marker carried over by the frame's fit alone lands up to tens of metres off
its street. This script carries each operation over and seats it on the built network:

  frame      x_bay = 0.970 x + 856, y_bay = -0.970 z - 292 (fit of the model's road graph to the Bay's, median 16 m off),
             plus the local displacement worked out by fit_campaign.py (median 4 m off; run that first)
  on a road  every marker and route point that stands on a road in the model (it lies within 12 m of the model's road
             graph) is moved to the nearest Bay road within SNAP_M; others (a spot in a yard, a target beside the track)
             keep the fitted position
  routes     consecutive seated points of a route are joined along the Bay network (shortest way); a leg much longer
             than in the model, or with no way at all, is a gap: a street the campaign drives that the city lacks or
             has elsewhere
The training ground's operations (01, 04) are laid out by plan_training.py on the pad and only listed here.

Input:  ASSETS TO USE/bay_city_3d/dados/cenarios_bay_city.json, rede_viaria.bin; Saved/Bay/network.json
Output: Saved/Bay/campaign/operations.json   every operation in Bay metres: markers (with how far each was moved and
                                             whether it is seated), routes as drivable lines along the network, gaps
        Saved/Bay/campaign/op_NN.png         plan of each operation over the network: route green, gaps red
        Saved/Bay/campaign/overview.png      all routes on the whole network
        prints one line per operation and the list of gaps
"""
import heapq
import json
import math
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
ON_MODEL_ROAD_M = 12.0      # a model point this close to the model's road graph stands on a road
SNAP_M = 70.0               # furthest a point is moved to reach a Bay road
DETOUR = 1.6                # a leg this many times longer along the Bay's streets than in the model is a gap...
DETOUR_MIN_M = 120.0        # ...when it is also this much longer in metres
TRAINING_OPS = (1, 4)
ROAD_ROLES = ("start_player", "start_suspect", "start_ally", "checkpoint", "end", "suspect_route", "blockade", "ambush")


_FRAME = None


def to_bay(x, z):
    """Model (x east, z south) to Bay metres (east, north): the global fit plus the local displacement of
    fit_campaign.py (Saved/Bay/campaign/frame.npz), when that file exists."""
    global _FRAME
    bx, by = SCALE * x + SHIFT_X, -SCALE * z + SHIFT_Y
    path = os.path.join(OUT, "frame.npz")
    if _FRAME is None:
        _FRAME = dict(np.load(path)) if os.path.exists(path) else {}
    if _FRAME:
        f = _FRAME
        ny, nx = f["dx"].shape
        u = min(max((bx - float(f["x0"])) / float(f["cell"]), 0.0), nx - 1.001)
        v = min(max((by - float(f["y0"])) / float(f["cell"]), 0.0), ny - 1.001)
        iu, iv = int(u), int(v)
        fu, fv = u - iu, v - iv
        for k, field in enumerate((f["dx"], f["dy"])):
            d = (field[iv, iu] * (1 - fu) * (1 - fv) + field[iv, iu + 1] * fu * (1 - fv)
                 + field[iv + 1, iu] * (1 - fu) * fv + field[iv + 1, iu + 1] * fu * fv)
            if k == 0:
                bx += float(d)
            else:
                by += float(d)
    return bx, by


class Roads:
    """The Bay network as something to seat points on and to route along."""

    def __init__(self, net):
        self.edges = net["edges"]
        self.lines = [np.asarray(e["pts"], dtype=np.float64)[:, :2] for e in self.edges]
        self.run = [np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(line, axis=0).T))]) for line in self.lines]
        seg_a, seg_b, seg_edge, seg_s = [], [], [], []
        for k, line in enumerate(self.lines):
            seg_a.append(line[:-1])
            seg_b.append(line[1:])
            seg_edge.append(np.full(len(line) - 1, k))
            seg_s.append(self.run[k][:-1])
        self.a, self.b = np.vstack(seg_a), np.vstack(seg_b)
        self.seg_edge, self.seg_s = np.concatenate(seg_edge), np.concatenate(seg_s)
        self.ab = self.b - self.a
        self.len2 = np.maximum((self.ab ** 2).sum(axis=1), 1e-9)
        self.adjacent = {}
        for k, e in enumerate(self.edges):
            self.adjacent.setdefault(e["a"], []).append(k)
            self.adjacent.setdefault(e["b"], []).append(k)

    def nearest(self, x, y):
        """(distance, edge index, distance along that edge, point) of the road point nearest to (x, y)."""
        p = np.array([x, y])
        t = np.clip(((p - self.a) * self.ab).sum(axis=1) / self.len2, 0.0, 1.0)
        q = self.a + self.ab * t[:, None]
        d = np.hypot(q[:, 0] - x, q[:, 1] - y)
        k = int(np.argmin(d))
        return float(d[k]), int(self.seg_edge[k]), float(self.seg_s[k] + t[k] * math.sqrt(self.len2[k])), (float(q[k][0]), float(q[k][1]))

    def piece(self, edge, s0, s1):
        """The edge's line between two distances along it (reversed when s1 < s0)."""
        line, run = self.lines[edge], self.run[edge]
        lo, hi = min(s0, s1), max(s0, s1)
        pts = [tuple(np.array([np.interp(lo, run, line[:, 0]), np.interp(lo, run, line[:, 1])]))]
        pts += [tuple(p) for p, s in zip(line, run) if lo < s < hi]
        pts.append((float(np.interp(hi, run, line[:, 0])), float(np.interp(hi, run, line[:, 1]))))
        return pts if s1 >= s0 else pts[::-1]

    def candidates(self, x, y, reach, slack=35.0, most=5):
        """The roads a point may stand on: for each road within `reach`, and no more than `slack` further than the
        nearest one, (distance, edge index, distance along it, point); nearest first, `most` at most. Where a street
        passes under a viaduct or over a tunnel the nearest road is not always the one meant: the route decides."""
        p = np.array([x, y])
        t = np.clip(((p - self.a) * self.ab).sum(axis=1) / self.len2, 0.0, 1.0)
        q = self.a + self.ab * t[:, None]
        d = np.hypot(q[:, 0] - x, q[:, 1] - y)
        best = {}
        for k in np.nonzero(d <= reach)[0]:
            e = int(self.seg_edge[k])
            if e not in best or d[k] < best[e][0]:
                best[e] = (float(d[k]), e, float(self.seg_s[k] + t[k] * math.sqrt(self.len2[k])), (float(q[k][0]), float(q[k][1])))
        out = sorted(best.values())
        return [c for c in out if c[0] <= out[0][0] + slack][:most] if out else []

    def tree(self, edge, s):
        """Shortest distances from a seated point to every junction: (dist, came, edge, s)."""
        length = self.run[edge][-1]
        dist, came = {}, {}
        heap = [(s, 0, self.edges[edge]["a"], None, None), (length - s, 1, self.edges[edge]["b"], None, None)]
        order = 2                                       # ties are broken by the order of arrival, never by the rest
        while heap:
            d, _, node, prev, via = heapq.heappop(heap)
            if node in dist:
                continue
            dist[node] = d
            came[node] = (prev, via)
            for k in self.adjacent.get(node, ()):
                e = self.edges[k]
                other = e["b"] if e["a"] == node else e["a"]
                if other not in dist:
                    heapq.heappush(heap, (d + self.run[k][-1], order, other, node, k))
                    order += 1
        return dist, came, edge, s

    def way(self, tree, goal):
        """Length of the shortest way from a tree's root to a seated point, and the junction it arrives by
        (None, None: no way; a junction of None: both on the same road)."""
        dist, _, e0, s0 = tree
        e1, s1 = goal
        e = self.edges[e1]
        ends = []
        if e["a"] in dist:
            ends.append((dist[e["a"]] + s1, e["a"]))
        if e["b"] in dist:
            ends.append((dist[e["b"]] + self.run[e1][-1] - s1, e["b"]))
        best = min(ends) if ends else (None, None)
        if e0 == e1 and (best[0] is None or abs(s1 - s0) <= best[0]):
            return abs(s1 - s0), None
        return best

    def line(self, tree, goal):
        """The shortest way itself, as a line."""
        _, came, e0, s0 = tree
        e1, s1 = goal
        total, node = self.way(tree, goal)
        if total is None:
            return None
        if node is None:
            return self.piece(e0, s0, s1)
        tail = self.piece(e1, 0.0 if node == self.edges[e1]["a"] else self.run[e1][-1], s1)
        chain = []
        while came[node][0] is not None:
            prev, via = came[node]
            e = self.edges[via]
            chain.append(self.piece(via, 0.0, self.run[via][-1]) if e["a"] == prev else self.piece(via, self.run[via][-1], 0.0))
            node = prev
        out = self.piece(e0, s0, 0.0 if node == self.edges[e0]["a"] else self.run[e0][-1])
        for part in reversed(chain):
            out += part[1:]
        return out + tail[1:]

    def match(self, fitted, reach):
        """Seats a route's points on the network together: for each point one of its candidate roads, chosen so
        that the whole route stays near its points and each leg is as long along the streets as it is in the
        model. Returns the seats (distance moved, edge, distance along, point), None where no road is in reach."""
        cands = [self.candidates(x, y, reach) for x, y in fitted]
        seats = [None] * len(fitted)
        i = 0
        while i < len(fitted):
            if not cands[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(fitted) and cands[j + 1]:
                j += 1
            # dynamic programme over the stretch i..j
            cost = [[c[0] for c in cands[i]]]
            back = []
            for k in range(i + 1, j + 1):
                leg = math.hypot(fitted[k][0] - fitted[k - 1][0], fitted[k][1] - fitted[k - 1][1])
                trees = [self.tree(c[1], c[2]) for c in cands[k - 1]]
                row, choice = [], []
                for c in cands[k]:
                    options = []
                    for m, tree in enumerate(trees):
                        length, _ = self.way(tree, (c[1], c[2]))
                        step = 3000.0 if length is None else min(abs(length - leg), 3000.0)
                        options.append((cost[-1][m] + step, m))
                    best = min(options)
                    row.append(best[0] + c[0])
                    choice.append(best[1])
                cost.append(row)
                back.append(choice)
            pick = int(np.argmin(cost[-1]))
            for k in range(j, i - 1, -1):
                seats[k] = cands[k][pick]
                if k > i:
                    pick = back[k - i - 1][pick]
            i = j + 1
        return seats


SPUR_M = 60.0               # a route never runs out and straight back along the same road for less than this


def without_spurs(line, most=SPUR_M):
    """The line without its short out-and-back stretches, and the metres taken out. A waypoint that the model has a few
    metres up a side road (at a tunnel's mouth, 20 m past the junction the route turns at) is seated there, and the
    way to it and back is the same road twice: nobody drives to it and turns round on the spot."""
    pts = [list(p) for p in line]
    cut, i = 0.0, 1
    while i < len(pts) - 1:
        k = 0
        while i - k - 1 >= 0 and i + k + 1 < len(pts) and math.hypot(pts[i - k - 1][0] - pts[i + k + 1][0],
                                                                      pts[i - k - 1][1] - pts[i + k + 1][1]) < 0.02:
            k += 1
        run = sum(math.hypot(pts[j + 1][0] - pts[j][0], pts[j + 1][1] - pts[j][1]) for j in range(i - k, i))
        if k and run <= most:
            del pts[i - k + 1:i + k + 1]
            cut += 2.0 * run
            i = max(i - k, 1)
        else:
            i += 1
    return pts, cut


def model_roads():
    with open(os.path.join(CAMPAIGN, "rede_viaria.bin"), "rb") as f:
        buf = f.read()
    n_nodes, n_edges = struct.unpack_from("<2I", buf, 4)
    pts = np.array([struct.unpack_from("<3f", buf, 20 + 16 * i) for i in range(n_nodes)])[:, [0, 2]]
    edges = np.array([struct.unpack_from("<2I", buf, 20 + 16 * n_nodes + 8 * i) for i in range(n_edges)])
    return pts[edges[:, 0]], pts[edges[:, 1]]


def main():
    wanted = [int(a) for a in sys.argv[1:]]
    with open(os.path.join(CAMPAIGN, "cenarios_bay_city.json"), encoding="utf-8") as f:
        operations = json.load(f)["operations"]
    net = load_json("network.json")
    roads = Roads(net)
    ma, mb = model_roads()
    mab = mb - ma
    mlen2 = np.maximum((mab ** 2).sum(axis=1), 1e-9)

    def off_model_road(x, z):
        p = np.array([x, z])
        t = np.clip(((p - ma) * mab).sum(axis=1) / mlen2, 0.0, 1.0)
        q = ma + mab * t[:, None]
        return float(np.hypot(q[:, 0] - x, q[:, 1] - z).min())

    os.makedirs(OUT, exist_ok=True)
    xs = [n["x"] for n in net["nodes"]]
    ys = [n["y"] for n in net["nodes"]]
    frame = (min(xs) - 150.0, max(xs) + 150.0, min(ys) - 900.0, max(ys) + 150.0)

    def canvas(box, scale):
        w, h = int((box[1] - box[0]) * scale), int((box[3] - box[2]) * scale)
        img = np.full((h, w, 3), 245, np.uint8)
        P = lambda x, y: (int(round((x - box[0]) * scale)), int(round((box[3] - y) * scale)))
        for line, e in zip(roads.lines, roads.edges):
            if line[:, 0].max() < box[0] or line[:, 0].min() > box[1] or line[:, 1].max() < box[2] or line[:, 1].min() > box[3]:
                continue
            colour = (150, 110, 60) if e["cls"] == "tunnel" else (60, 60, 200) if e["cls"] == "bridge" else (165, 165, 165)
            cv2.polylines(img, [np.array([P(x, y) for x, y in line], np.int32)], False, colour,
                          max(1, int({"freeway": 5, "arterial": 4}.get(e["cls"], 2) * scale / 0.5)), cv2.LINE_AA)
        return img, P

    overview, PO = canvas(frame, 0.25)
    palette = [(40, 40, 220), (0, 130, 240), (40, 160, 40), (190, 60, 150), (200, 120, 0), (0, 170, 170)]
    out, all_gaps = {}, []
    for op in operations:
        number = op["id"]
        if wanted and number not in wanted:
            continue
        record = {"title": op["title"], "district": op["district"], "time": op["time"], "weather": op["weather"],
                  "unit": op["unit"], "target": op["target"], "doc": op.get("docFile")}
        if number in TRAINING_OPS:
            record["layout"] = "Op%02d" % number
            record["note"] = "on the training ground: Saved/Bay/training/layouts.json (plan_training.py)"
            out["%02d" % number] = record
            print("CAMPAIGN %02d %-30s on the training ground (layout Op%02d)" % (number, op["title"][:30], number))
            continue
        # ---- the routes first: each one seated as a whole (Roads.match), so its points agree on which street they
        # follow; the markers that are points of a route then take the route's seat
        routes, gaps, seat_of = {}, [], {}
        for who, path in (op.get("paths") or {}).items():
            if len(path) < 2:
                continue
            fitted = [to_bay(p[0], p[2]) for p in path]
            seats = roads.match(fitted, SNAP_M)
            for p, seat in zip(path, seats):
                if seat is not None:
                    seat_of.setdefault((round(p[0], 1), round(p[2], 1)), seat)
            line, length, model_length = [], 0.0, 0.0
            for i in range(len(path) - 1):
                leg_model = math.hypot(fitted[i + 1][0] - fitted[i][0], fitted[i + 1][1] - fitted[i][1])
                model_length += leg_model
                a, b = seats[i], seats[i + 1]
                if a is None or b is None:
                    where = fitted[i] if a is None else fitted[i + 1]
                    gaps.append({"route": who, "leg": i, "kind": "no road", "at": [round(where[0], 1), round(where[1], 1)],
                                 "model_m": round(leg_model, 1),
                                 "note": "no Bay road within %.0f m of the route point" % SNAP_M})
                    continue
                tree = roads.tree(a[1], a[2])
                way, _ = roads.way(tree, (b[1], b[2]))
                if way is None:
                    gaps.append({"route": who, "leg": i, "kind": "no way", "at": [round(a[3][0], 1), round(a[3][1], 1)],
                                 "to": [round(b[3][0], 1), round(b[3][1], 1)], "model_m": round(leg_model, 1)})
                    continue
                if way > DETOUR * leg_model and way - leg_model > DETOUR_MIN_M:
                    gaps.append({"route": who, "leg": i, "kind": "detour", "at": [round(a[3][0], 1), round(a[3][1], 1)],
                                 "to": [round(b[3][0], 1), round(b[3][1], 1)], "model_m": round(leg_model, 1), "bay_m": round(way, 1)})
                    continue
                piece = roads.line(tree, (b[1], b[2]))
                length += way
                line += [[round(float(q[0]), 2), round(float(q[1]), 2)] for q in (piece if not line else piece[1:])]
            line, spurs = without_spurs(line)
            length -= spurs
            routes[who] = {"line": line, "bay_m": round(length, 1), "model_m": round(model_length, 1),
                           "points": [[round(x, 2), round(y, 2)] for x, y in fitted]}
        markers, moved, loose = [], [], 0
        for m in op["markers"]:
            x, y = to_bay(m["pos"][0], m["pos"][2])
            entry = {"role": m["role"], "label": m["label"], "radius": round(m["radius"] * SCALE, 2), "model": [round(v, 2) for v in m["pos"]]}
            on_road = m["role"] in ROAD_ROLES and off_model_road(m["pos"][0], m["pos"][2]) <= ON_MODEL_ROAD_M
            seat = seat_of.get((round(m["pos"][0], 1), round(m["pos"][2], 1)))
            if seat is None:
                d, edge, s, q = roads.nearest(x, y)
            else:
                d, edge, s, q = seat
            if (on_road or seat is not None) and d <= SNAP_M:
                z = float(np.interp(s, roads.run[edge], np.asarray(roads.edges[edge]["pts"])[:, 2]))
                entry.update({"x": round(q[0], 2), "y": round(q[1], 2), "z": round(z, 2), "seated": True, "moved": round(d, 1),
                              "edge": edge, "road": roads.edges[edge]["cls"]})
                moved.append(d)
            else:
                entry.update({"x": round(x, 2), "y": round(y, 2), "z": None, "seated": False, "off_road": round(d, 1)})
                if on_road:
                    entry["note"] = "stands on a road in the model; the nearest Bay road is %.0f m away" % d
                    loose += 1
            markers.append(entry)
        record.update({"markers": markers, "routes": routes, "gaps": gaps})
        out["%02d" % number] = record
        all_gaps += [(number, g) for g in gaps]
        print("CAMPAIGN %02d %-30s %2d markers: %2d seated (moved median %.0f m, most %.0f m), %d road markers left off a road; "
              "routes %s; %d gaps" % (number, op["title"][:30], len(markers), len(moved), float(np.median(moved)) if moved else 0.0,
                                      max(moved) if moved else 0.0, loose,
                                      ", ".join("%s %.0f m (model %.0f)" % (k, v["bay_m"], v["model_m"]) for k, v in routes.items()), len(gaps)))

        # ---- the operation's own picture
        px = [m["x"] for m in markers] + [p[0] for r in routes.values() for p in r["points"]]
        py = [m["y"] for m in markers] + [p[1] for r in routes.values() for p in r["points"]]
        span = max(max(px) - min(px), max(py) - min(py), 300.0) + 240.0
        cx, cy = (max(px) + min(px)) / 2.0, (max(py) + min(py)) / 2.0
        scale = min(2.0, 1500.0 / span)
        img, P = canvas((cx - span / 2, cx + span / 2, cy - span / 2, cy + span / 2), scale)
        for who, r in routes.items():
            colour = (40, 170, 40) if who == "player" else (200, 120, 0)
            if len(r["points"]) > 1:
                cv2.polylines(img, [np.array([P(x, y) for x, y in r["points"]], np.int32)], False, (200, 200, 255) if who == "player" else (255, 225, 190), 1, cv2.LINE_AA)
            if len(r["line"]) > 1:
                cv2.polylines(img, [np.array([P(x, y) for x, y in r["line"]], np.int32)], False, colour, 3, cv2.LINE_AA)
                cv2.polylines(overview, [np.array([PO(x, y) for x, y in r["line"]], np.int32)], False, palette[number % len(palette)], 2, cv2.LINE_AA)
        for g in gaps:
            cv2.circle(img, P(*g["at"]), 14, (0, 0, 255), 2, cv2.LINE_AA)
            if "to" in g:
                cv2.line(img, P(*g["at"]), P(*g["to"]), (0, 0, 255), 2, cv2.LINE_AA)
            cv2.circle(overview, PO(*g["at"]), 9, (0, 0, 255), 2, cv2.LINE_AA)
        role_colour = {"start_player": (0, 160, 0), "start_suspect": (0, 0, 200), "start_ally": (160, 100, 0), "checkpoint": (0, 150, 220),
                       "end": (0, 0, 0), "objective": (170, 0, 170), "blockade": (0, 90, 255), "ambush": (60, 60, 60), "effect": (0, 200, 255),
                       "exit_fail": (200, 200, 0), "suspect_route": (220, 130, 0)}
        for m in markers:
            c = role_colour.get(m["role"], (90, 90, 90))
            cv2.circle(img, P(m["x"], m["y"]), 5 if m.get("seated") else 4, c, -1 if m.get("seated") else 2, cv2.LINE_AA)
            if m["role"] in ("start_player", "end", "objective", "start_suspect"):
                cv2.putText(img, m["label"][:26], (P(m["x"], m["y"])[0] + 7, P(m["x"], m["y"])[1] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.42, c, 1, cv2.LINE_AA)
        cv2.putText(img, "Op %02d  %s" % (number, op["district"].encode("ascii", "ignore").decode()), (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2, cv2.LINE_AA)
        cv2.imwrite(os.path.join(OUT, "op_%02d.png" % number), img)
        start = next((m for m in markers if m["role"] == "start_player"), None)
        if start:
            cv2.putText(overview, "%02d" % number, (PO(start["x"], start["y"])[0] + 5, PO(start["x"], start["y"])[1] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, palette[number % len(palette)], 2, cv2.LINE_AA)
    if not wanted:
        cv2.imwrite(os.path.join(OUT, "overview.png"), overview)
        with open(os.path.join(OUT, "operations.json"), "w", encoding="utf-8") as f:
            json.dump({"frame": {"scale": SCALE, "shift_x": SHIFT_X, "shift_y": SHIFT_Y, "note": "x_bay = scale * x + shift_x, y_bay = -scale * z + shift_y; metres, x east, y north"},
                       "operations": out}, f, ensure_ascii=False)
    print("CAMPAIGN gaps: %d" % len(all_gaps))
    for number, g in all_gaps:
        print("   %02d %-7s %-8s leg %2d at (%.0f, %.0f)%s  model %.0f m%s" % (
            number, g["route"], g["kind"], g["leg"], g["at"][0], g["at"][1], (" -> (%.0f, %.0f)" % tuple(g["to"])) if "to" in g else "",
            g["model_m"], (", Bay %.0f m" % g["bay_m"]) if "bay_m" in g else ""))


if __name__ == "__main__":
    main()
