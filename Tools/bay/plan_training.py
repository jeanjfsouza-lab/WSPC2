"""The layouts of the training ground (sector PT1): what each campaign operation sets out on the asphalt pad.

  python -P Tools/bay/plan_training.py

The campaign's model (ASSETS TO USE/bay_city_3d) has one copy of the same paved yard for each operation that uses it
(01 "Circuito de Interceptacao", 04 "Cacada de Elite"). The Bay city has one yard; each operation is a layout: a set
of things placed on the same pad, of which the game shows one at a time (AWSPC2LayoutDirector, by the tag
"WSPC2Layout.<name>"; -WSPC2Layout=<name> or ?layout=<name> chooses it).

Input:  ASSETS TO USE/bay_city_3d/dados/cenarios_bay_city.json   the operations' markers, in the model's metres
        Tools/bay/sectors.py                                     the pad (PT_PAD) and its plane (pt_z)
Output: Saved/Bay/training/layouts.json    for each layout: the operation's markers and zones in Bay metres, the line
                                           to drive, and "actors": what build_bay.py (stage "training") places
        Saved/Bay/training/<layout>.png    plan of the layout
        Saved/Bay/structures/TRAIN_<layout>/views.txt   review cameras (tour.ps1 -Structure TRAIN_<layout>
                                                        -Extra "-WSPC2Layout=<layout>")

How a layout is laid out. The operation gives checkpoints in order and circles that fail the run when entered. The
circles the route itself has to enter (the centre of operation 04's arena, where the stop box and the finish are:
the script can only keep them closed for part of the run) are left alone and marked "phased". The others are islands:
the line to drive is the route through the checkpoints with its corners rounded, moved off every island by half a
lane and a metre, and cones stand along both edges of the lane all the way, closer together through the bends and
beside an island. A pair of gate markers stands at each checkpoint.
Operation 04 also has a ramp on its south straight (4.3 m high, as the model's), five targets beside the track, a
stop box and a parked car (the car is the mission's to spawn: only its place is recorded).

Model to Bay: the model's yard spans x = 1834 .. 2090 and z = 1504 .. 1784 (operation 01; operation 04's copy lies
601.6 further south), at 0.97 Bay metres per model metre (the fit of the model's road network to the Bay's,
vault note "Campanha - encaixe no mapa Bay"); its north-west corner is put on the pad's.
"""
import json
import math
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sectors
from common import DATA, PROJECT

CAMPAIGN = os.path.join(PROJECT, "ASSETS TO USE", "bay_city_3d", "dados", "cenarios_bay_city.json")
OUT = os.path.join(DATA, "training")
SCALE = 0.97
MODEL_X0 = 1834.0
MODEL_Z0 = {1: 1504.0, 4: 1504.0 + 601.6}
PAD_W, PAD_E, PAD_S, PAD_N = sectors.PT_PAD
SHIFT_X = (PAD_E - PAD_W - 256.0 * SCALE) / 2.0          # the model's yard is 256 wide: centred on the pad

LANE_HALF_M = 6.0           # half the width kept free along the line to drive
CORNER_M = 14.0             # radius the route's corners are rounded with
CONE_EVERY_M = 4.5          # between cones through a bend or beside an island; twice that on a plain straight
GUARD_STEPS_M = (1.0, 3.5, 6.0, 9.0, 12.0)   # an island this far beyond a lane edge counts as beside it
EDGE_CLEAR_M = 2.0          # nothing this close to the pad's edge line
CELL = 0.5                  # grid of the plan, metres

CONE = "/Game/Construction_VOL1/Meshes/SM_ConstructionPylons_01e"         # 61 cm
GATE_POST = "/Game/Construction_VOL1/Meshes/SM_ConstructionPylons_01a"    # a delineator post, 1.28 m (01d, 93 cm, is a stack of cones)
DRUM = "/Game/Construction_VOL1/Meshes/SM_ConstructionPylons_01c"         # an orange and white traffic drum, 1.09 m
RAMP = "/Game/Bay/Training/SM_Bay_TrainingRamp"         # training_mesh.py: long axis local X, origin at its centre
TARGET = "/Game/Bay/Training/SM_Bay_TrainingTarget"     # training_mesh.py: faces local +X
RAMP_MODEL = (1948.0, 2014.0, 1759.0, 1777.6)           # the ramp in the model, in the frame of operation 01's yard

LAYOUTS = {"Op01": {"operation": 1, "closed": True},
           "Op04": {"operation": 4, "closed": False, "ramp": True,
                    # the five targets and the parked car of the operation's script (cenarios/04_cacada_de_elite.md)
                    "targets": [(2079.61, 2200.91), (2066.30, 2156.37), (2002.30, 2152.53), (1949.30, 2132.56), (1856.63, 2133.59)],
                    "parked_car": (1956.98, 2199.89)}}


def to_bay(op, x, z):
    return PAD_W + SHIFT_X + SCALE * (x - MODEL_X0), PAD_N - SCALE * (z - MODEL_Z0[op])


def ue_yaw(vx, vy):
    return math.degrees(math.atan2(-vy, vx)) % 360.0


def rounded(points, radius, closed):
    """The polyline with each corner replaced by an arc (as large as its two sides allow), sampled every metre."""
    n = len(points)
    out = []
    idx = range(n) if closed else range(1, n - 1)
    if not closed:
        out.append(points[0])
    for i in idx:
        p0, p1, p2 = points[(i - 1) % n], points[i], points[(i + 1) % n]
        ux, uy = p1[0] - p0[0], p1[1] - p0[1]
        vx, vy = p2[0] - p1[0], p2[1] - p1[1]
        lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
        ux, uy, vx, vy = ux / lu, uy / lu, vx / lv, vy / lv
        turn = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        if abs(turn) < math.radians(3.0) or abs(turn) > math.radians(165.0):
            out.append(p1)                              # straight on, or a turn back on itself: the point itself
            continue
        tangent = min(radius * math.tan(abs(turn) / 2.0), lu * 0.45, lv * 0.45)
        r = tangent / math.tan(abs(turn) / 2.0)
        start = (p1[0] - ux * tangent, p1[1] - uy * tangent)
        side = 1.0 if turn > 0 else -1.0
        cx, cy = start[0] - uy * side * r, start[1] + ux * side * r
        a0 = math.atan2(start[1] - cy, start[0] - cx)
        steps = max(2, int(math.ceil(abs(turn) * r / 1.0)))
        out += [(cx + r * math.cos(a0 + turn * k / steps), cy + r * math.sin(a0 + turn * k / steps)) for k in range(steps + 1)]
    if not closed:
        out.append(points[-1])
    else:
        out.append(out[0])
    dense = [out[0]]
    for a, b in zip(out[:-1], out[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        k = max(1, int(math.ceil(d / 1.0)))
        dense += [(a[0] + (b[0] - a[0]) * j / k, a[1] + (b[1] - a[1]) * j / k) for j in range(1, k + 1)]
    return np.array(dense, dtype=np.float64)


def keep_clear(line, islands, closed):
    """Moves the line off every island by half a lane and a metre, keeps it that far inside the pad, and smooths
    what was moved. Returns the line and the largest move."""
    first = line.copy()
    lo = np.array([PAD_W + LANE_HALF_M + EDGE_CLEAR_M, PAD_S + LANE_HALF_M + EDGE_CLEAR_M])
    hi = np.array([PAD_E - LANE_HALF_M - EDGE_CLEAR_M, PAD_N - LANE_HALF_M - EDGE_CLEAR_M])

    def push(pts):
        for cx, cy, r in islands:
            need = r + LANE_HALF_M + 1.0
            d = np.hypot(pts[:, 0] - cx, pts[:, 1] - cy)
            inside = d < need
            if inside.any():
                scale = need / np.maximum(d[inside], 1e-6)
                pts[inside, 0] = cx + (pts[inside, 0] - cx) * scale
                pts[inside, 1] = cy + (pts[inside, 1] - cy) * scale
        return np.clip(pts, lo, hi)

    for _ in range(80):
        line = push(line)
        smooth = line.copy()
        smooth[1:-1] = 0.25 * line[:-2] + 0.5 * line[1:-1] + 0.25 * line[2:]
        if closed:
            smooth[0] = smooth[-1] = 0.25 * line[-2] + 0.5 * line[0] + 0.25 * line[1]
        line = smooth
    line = push(line)
    return line, float(np.hypot(*(line - first).T).max())


def depth_into(points, zone):
    """How far the polyline goes into a circle, metres (0: it stays out)."""
    cx, cy, r = zone
    deepest = 0.0
    for a, b in zip(points[:-1], points[1:]):
        ab = (b[0] - a[0], b[1] - a[1])
        t = min(1.0, max(0.0, ((cx - a[0]) * ab[0] + (cy - a[1]) * ab[1]) / max(ab[0] ** 2 + ab[1] ** 2, 1e-9)))
        deepest = max(deepest, r - math.hypot(a[0] + ab[0] * t - cx, a[1] + ab[1] * t - cy))
    return deepest


def plan(name, spec, operation):
    op = spec["operation"]
    z_of = lambda x: float(sectors.pt_z(x))
    markers = []
    for m in operation["markers"]:
        x, y = to_bay(op, m["pos"][0], m["pos"][2])
        markers.append({"role": m["role"], "label": m["label"], "x": round(x, 2), "y": round(y, 2), "z": round(z_of(x), 2),
                        "radius": round(m["radius"] * SCALE, 2)})
    route = [to_bay(op, p[0], p[2]) for p in operation["paths"]["player"]]
    checkpoints = [m for m in markers if m["role"] in ("checkpoint", "end", "start_player")]
    if spec["closed"]:
        # a circuit: the laps run through the checkpoints and the finish and round again (the start is on the way)
        route = [(m["x"], m["y"]) for m in markers if m["role"] in ("checkpoint", "end")]
    zones = [m for m in markers if m["role"] == "exit_fail"]
    # the model's yard has its gate in the north-west corner and the Bay's in the middle of the north side: the
    # circle that closes the gate (it lies north of every checkpoint, on the way out) moves with it
    north_most = max(m["y"] for m in checkpoints)
    for zone in zones:
        if zone["y"] - zone["radius"] > north_most:
            zone["x"], zone["y"] = round(sectors.PT_ROAD_X, 2), round(PAD_N - 8.0, 2)
            zone["label"] += " (no portao)"
    chord = route + [route[0]] if spec["closed"] else route
    islands = []
    for zone in zones:
        deep = depth_into(chord, (zone["x"], zone["y"], zone["radius"]))
        zone["phased"] = bool(deep > 0.4 * zone["radius"])
        if not zone["phased"]:
            islands.append((zone["x"], zone["y"], zone["radius"]))
    line, moved = keep_clear(rounded(route, CORNER_M, spec["closed"]), islands, spec["closed"])

    # ---- the plan as a grid: islands, the lane kept free along the line, the ramp
    gw, gh = int(round((PAD_E - PAD_W) / CELL)), int(round((PAD_N - PAD_S) / CELL))
    px = lambda x, y: (int(round((x - PAD_W) / CELL)), int(round((PAD_N - y) / CELL)))
    island = np.zeros((gh, gw), np.uint8)
    for cx, cy, r in islands:
        cv2.circle(island, px(cx, cy), int(round(r / CELL)), 1, -1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(10.0 / CELL) + 1, int(10.0 / CELL) + 1))
    island = cv2.morphologyEx(island, cv2.MORPH_CLOSE, kernel)
    lane = np.zeros((gh, gw), np.uint8)
    cv2.polylines(lane, [np.array([px(x, y) for x, y in line], np.int32)], False, 1, int(round(2 * LANE_HALF_M / CELL)))
    island[lane > 0] = 0
    from_line = cv2.distanceTransform((1 - cv2.polylines(np.zeros((gh, gw), np.uint8), [np.array([px(x, y) for x, y in line], np.int32)],
                                                          False, 1, 1)).astype(np.uint8), cv2.DIST_L2, 5) * CELL

    actors, cones = [], []

    def put(mesh, x, y, yaw, label, physics=False, scale=1.0, lift=0.0, pitch=0.0, tags=()):
        actors.append({"mesh": mesh, "x": round(x * 100.0, 1), "y": round(-y * 100.0, 1), "z": round((z_of(x) + lift) * 100.0, 1),
                       "yaw": round(yaw % 360.0, 1), "pitch": round(pitch, 4), "scale": scale, "physics": physics, "label": label,
                       "tags": list(tags)})

    ramp = None
    if spec.get("ramp"):
        x0, y0 = to_bay(1, RAMP_MODEL[0], RAMP_MODEL[2])
        x1, y1 = to_bay(1, RAMP_MODEL[1], RAMP_MODEL[3])
        ramp = {"x": round((x0 + x1) / 2.0, 2), "y": round((y0 + y1) / 2.0, 2), "length": round(abs(x1 - x0), 2),
                "width": round(abs(y1 - y0), 2), "height": round(4.4 * SCALE, 2)}
        # the pad is a plane that rises to the east: the ramp, 64 m long, is tipped with it (set level, one foot would
        # stand 38 cm above the asphalt and the other as far under it), and lifted a finger so its feet do not flicker
        slope = float(sectors.pt_z(ramp["x"] + 50.0) - sectors.pt_z(ramp["x"] - 50.0)) / 100.0
        put(RAMP, ramp["x"], ramp["y"], 0.0, "%s_Ramp" % name, pitch=math.degrees(math.atan(slope)), lift=0.015)
        cv2.rectangle(island, px(min(x0, x1) - 3.0, max(y0, y1) + 3.0), px(max(x0, x1) + 3.0, min(y0, y1) - 3.0), 0, -1)

    # ---- gates: a pair of delineator posts at each checkpoint, across the line where it passes nearest
    def across(x, y):
        k = int(np.argmin(np.hypot(line[:, 0] - x, line[:, 1] - y)))
        a, b = line[max(k - 2, 0)], line[min(k + 2, len(line) - 1)]
        t = (b - a) / max(np.hypot(*(b - a)), 1e-9)
        return line[k], t, float(np.hypot(line[k][0] - x, line[k][1] - y))

    gates, drums, off_line = [], [], 0.0
    for m in markers:
        if m["role"] not in ("checkpoint", "end", "start_player"):
            continue
        p, t, d = across(m["x"], m["y"])
        off_line = max(off_line, d)
        if ramp and abs(p[0] - ramp["x"]) < ramp["length"] / 2.0 + 2.0 and abs(p[1] - ramp["y"]) < ramp["width"] / 2.0 + 2.0:
            continue                                    # on the ramp: its own kerbs are the gate
        for side in (1.0, -1.0):
            gx, gy = p[0] - t[1] * side * (LANE_HALF_M + 0.4), p[1] + t[0] * side * (LANE_HALF_M + 0.4)
            gates.append((gx, gy))
            if m["role"] == "end":                      # the finish: two cones a side
                gates.append((gx - t[1] * side * 0.9, gy + t[0] * side * 0.9))
    # the stop box of an operation that asks for a full stop: a traffic drum at each corner of a bay round the spot
    for m in markers:
        if "Parada" in m["label"]:
            p, t, _ = across(m["x"], m["y"])
            for along, side in ((4.5, 1.0), (4.5, -1.0), (-4.5, 1.0), (-4.5, -1.0)):
                drums.append((m["x"] + t[0] * along - t[1] * side * 3.2, m["y"] + t[1] * along + t[0] * side * 3.2))
    gates = [g for g in gates if PAD_W + EDGE_CLEAR_M < g[0] < PAD_E - EDGE_CLEAR_M and PAD_S + EDGE_CLEAR_M < g[1] < PAD_N - EDGE_CLEAR_M]

    # ---- cones along both edges of the lane. (A first version ringed every island with cones: seven rings of dots
    # in operation 01, and nothing that read as a track.)
    def is_island(x, y):
        c, r = px(x, y)
        return 0 <= c < gw and 0 <= r < gh and island[r, c] > 0

    step = np.hypot(*np.diff(line, axis=0).T)
    tangent = np.zeros_like(line)
    tangent[1:-1] = line[2:] - line[:-2]
    tangent[0], tangent[-1] = line[1] - line[0], line[-1] - line[-2]
    tangent /= np.maximum(np.hypot(tangent[:, 0], tangent[:, 1]), 1e-9)[:, None]
    normal = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1)
    # how sharply the line turns at each point (radians per metre, over 6 m): cones stand closer through a bend
    heading = np.unwrap(np.arctan2(tangent[:, 1], tangent[:, 0]))
    bend = np.abs(np.concatenate([[0.0] * 3, heading[6:] - heading[:-6], [0.0] * 3])) / 6.0
    for side in (1.0, -1.0):
        edge = line + normal * side * (LANE_HALF_M + 0.3)
        guarded = np.array([any(is_island(e[0] + n[0] * side * d, e[1] + n[1] * side * d) for d in GUARD_STEPS_M)
                            for e, n in zip(edge, normal)])
        run = 1e9
        for k in range(len(edge)):
            if k:
                run += float(step[k - 1])
            x, y = float(edge[k][0]), float(edge[k][1])
            # both edges of the lane are coned all the way (a first version coned an edge only where an island lay
            # beside it: from the driver's seat a few scattered cones, and no track to read): every 9 m on a
            # straight, every 4.5 m through a bend or beside an island
            every = CONE_EVERY_M if (guarded[k] or bend[k] > 1.0 / 60.0) else 2.0 * CONE_EVERY_M
            if run < every:
                continue
            c, r = px(x, y)
            if min(x - PAD_W, PAD_E - x, y - PAD_S, PAD_N - y) < EDGE_CLEAR_M or not (0 <= c < gw and 0 <= r < gh):
                continue
            if from_line[r, c] < LANE_HALF_M - 0.2:
                continue                                # in the lane of another stretch of the line
            if ramp and abs(x - ramp["x"]) < ramp["length"] / 2.0 + 1.0 and abs(y - ramp["y"]) < ramp["width"] / 2.0 + 1.0:
                continue
            if all(math.hypot(x - cx_, y - cy_) >= CONE_EVERY_M * 0.6 for cx_, cy_ in cones) and \
                    all(math.hypot(x - g[0], y - g[1]) >= 2.5 for g in gates + drums):
                cones.append((x, y))
                run = 0.0

    rng = np.random.default_rng(100 + op)
    for i, (x, y) in enumerate(cones):
        put(CONE, x, y, float(rng.uniform(0, 360)), "%s_Cone_%03d" % (name, i), physics=True)
    for i, (x, y) in enumerate(gates):
        put(GATE_POST, x, y, float(rng.uniform(0, 360)), "%s_Gate_%03d" % (name, i), physics=True)
    for i, (x, y) in enumerate(drums):
        put(DRUM, x, y, float(rng.uniform(0, 360)), "%s_Drum_%03d" % (name, i), physics=True)
    targets = []
    for i, (tx, tz) in enumerate(spec.get("targets", [])):
        x, y = to_bay(op, tx, tz)
        p, _, _ = across(x, y)
        targets.append({"name": "T%d" % (i + 1), "x": round(x, 2), "y": round(y, 2), "z": round(z_of(x), 2)})
        put(TARGET, x, y, ue_yaw(p[0] - x, p[1] - y), "%s_Target_T%d" % (name, i + 1), tags=["WSPC2Target.T%d" % (i + 1)])
    parked = None
    if spec.get("parked_car"):
        x, y = to_bay(op, *spec["parked_car"])
        parked = {"x": round(x, 2), "y": round(y, 2), "z": round(z_of(x), 2)}

    # ---- picture
    k = 4
    img = np.full((gh * k // 2, gw * k // 2, 3), (78, 78, 84), np.uint8)
    s = k / 2.0 / CELL
    P = lambda x, y: (int(round((x - PAD_W) * s)), int(round((PAD_N - y) * s)))
    big = cv2.resize(island, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    img[big > 0] = (70, 70, 120)
    for zone in zones:
        cv2.circle(img, P(zone["x"], zone["y"]), int(zone["radius"] * s), (60, 200, 255) if zone["phased"] else (60, 60, 230), 1, cv2.LINE_AA)
    cv2.polylines(img, [np.array([P(x, y) for x, y in line], np.int32)], False, (90, 220, 90), 2, cv2.LINE_AA)
    if ramp:
        cv2.rectangle(img, P(ramp["x"] - ramp["length"] / 2, ramp["y"] + ramp["width"] / 2),
                      P(ramp["x"] + ramp["length"] / 2, ramp["y"] - ramp["width"] / 2), (200, 200, 200), 2)
    for m in markers:
        if m["role"] in ("checkpoint", "end", "start_player", "start_suspect"):
            colour = {"checkpoint": (0, 220, 255), "end": (255, 255, 255), "start_player": (0, 255, 0), "start_suspect": (255, 120, 0)}[m["role"]]
            cv2.circle(img, P(m["x"], m["y"]), 4, colour, -1, cv2.LINE_AA)
            cv2.putText(img, m["label"].replace("Ponto de Controle ", "PC")[:14], (P(m["x"], m["y"])[0] + 6, P(m["x"], m["y"])[1] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, colour, 1, cv2.LINE_AA)
    for x, y in cones:
        cv2.circle(img, P(x, y), 2, (0, 140, 255), -1, cv2.LINE_AA)
    for x, y in gates + drums:
        cv2.circle(img, P(x, y), 3, (0, 90, 255), -1, cv2.LINE_AA)
    for t in targets:
        cv2.drawMarker(img, P(t["x"], t["y"]), (255, 255, 0), cv2.MARKER_TILTED_CROSS, 10, 2, cv2.LINE_AA)
    if parked:
        cv2.rectangle(img, P(parked["x"] - 2.5, parked["y"] + 1.0), P(parked["x"] + 2.5, parked["y"] - 1.0), (255, 120, 0), 2)
    os.makedirs(OUT, exist_ok=True)
    cv2.imwrite(os.path.join(OUT, "%s.png" % name), img)

    # ---- review cameras
    ue = lambda x, y, z: (x * 100.0, -y * 100.0, z * 100.0)
    cx, cy, cz = (PAD_W + PAD_E) / 2.0, (PAD_S + PAD_N) / 2.0, z_of((PAD_W + PAD_E) / 2.0)
    tag = "TRAIN_%s" % name
    views = [("%s_top" % tag, ue(cx, cy - 1.0, cz + 250.0), ue(cx, cy, cz))]
    for label, dx, dy in (("air_sw", -1, -1), ("air_ne", 1, 1), ("air_nw", -1, 1), ("air_se", 1, -1)):
        views.append(("%s_%s" % (tag, label), ue(cx + dx * 150.0, cy + dy * 160.0, cz + 70.0), ue(cx, cy, cz)))
    def top(x, y):
        """Height of what a car stands on at a point: the pad, or the ramp's deck where the ramp is (its ramps taken
        as straight slopes of 20 m)."""
        z = z_of(x)
        if ramp and abs(y - ramp["y"]) < ramp["width"] / 2.0:
            s = x - (ramp["x"] - ramp["length"] / 2.0)
            if 0.0 < s < ramp["length"]:
                z += ramp["height"] * min(1.0, min(s, ramp["length"] - s) / 20.0)
        return z

    length = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(line, axis=0).T))])
    stops = np.arange(10.0, length[-1] - 40.0, max(60.0, length[-1] / 9.0))
    for i, at in enumerate(stops):
        a = int(np.searchsorted(length, at))
        b = int(np.searchsorted(length, at + 35.0))
        views.append(("%s_drive%02d" % (tag, i + 1), ue(line[a][0], line[a][1], top(line[a][0], line[a][1]) + 1.3),
                      ue(line[b][0], line[b][1], top(line[b][0], line[b][1]) + 0.8)))
    if gates:
        gx, gy = gates[0]
        views.append(("%s_gate_close" % tag, ue(gx + 4.0, gy + 3.0, z_of(gx) + 1.2), ue(gx, gy, z_of(gx) + 0.4)))
    if cones:
        gx, gy = cones[len(cones) // 2]
        views.append(("%s_cone_close" % tag, ue(gx + 3.0, gy + 2.0, z_of(gx) + 1.0), ue(gx, gy, z_of(gx) + 0.3)))
    if ramp:
        views.append(("%s_ramp_w" % tag, ue(ramp["x"] - ramp["length"] / 2 - 30.0, ramp["y"] + 4.0, z_of(ramp["x"]) + 2.0),
                      ue(ramp["x"], ramp["y"], z_of(ramp["x"]) + 3.0)))
        views.append(("%s_ramp_e" % tag, ue(ramp["x"] + ramp["length"] / 2 + 30.0, ramp["y"] - 4.0, z_of(ramp["x"]) + 2.0),
                      ue(ramp["x"], ramp["y"], z_of(ramp["x"]) + 3.0)))
        views.append(("%s_ramp_side" % tag, ue(ramp["x"] + 10.0, ramp["y"] + 32.0, z_of(ramp["x"]) + 6.0),
                      ue(ramp["x"], ramp["y"], z_of(ramp["x"]) + 2.0)))
        views.append(("%s_ramp_top" % tag, ue(ramp["x"] - 8.0, ramp["y"], z_of(ramp["x"]) + ramp["height"] + 1.3),
                      ue(ramp["x"] + 40.0, ramp["y"], z_of(ramp["x"]) + 1.0)))
    for t in targets[:2]:
        p, _, _ = across(t["x"], t["y"])
        views.append(("%s_target_%s" % (tag, t["name"]), ue(p[0], p[1], t["z"] + 1.3), ue(t["x"], t["y"], t["z"] + 1.0)))
    folder = os.path.join(DATA, "structures", tag)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "views.txt"), "w") as f:
        for label, p, t in views:
            f.write("%s;%.0f,%.0f,%.0f;%.0f,%.0f,%.0f\n" % (label, p[0], p[1], p[2], t[0], t[1], t[2]))

    print("TRAINING %s (operation %02d): %d checkpoints, %d zones (%d phased), line %.0f m moved up to %.1f m off the islands, "
          "checkpoints up to %.1f m off the line; %d cones, %d gate posts, %d drums%s%s; %d cameras" % (
              name, op, sum(1 for m in markers if m["role"] == "checkpoint"), len(zones), sum(1 for z in zones if z["phased"]),
              length[-1], moved, off_line, len(cones), len(gates), len(drums), ", a ramp" if ramp else "",
              (", %d targets" % len(targets)) if targets else "", len(views)))
    return {"operation": op, "title": operation["title"], "closed": spec["closed"], "markers": markers,
            "line": [[round(float(x), 2), round(float(y), 2)] for x, y in line[::3]], "ramp": ramp, "targets": targets,
            "parked_car": parked, "actors": actors}


SAMPLES = ["/Game/Construction_VOL1/Meshes/SM_ConstructionPylons_01%s" % c for c in "abcdefg"] + [
    "/Game/VehicleTemplate/Meshes/SM_Cone", "/Game/Construction_VOL1/Meshes/SM_Trafficbarrier_01",
    "/Game/Construction_VOL1/Meshes/SM_PlasticBarrel_01a", "/Game/Construction_VOL1/Meshes/SM_Barrel_01",
    "/Game/Construction_VOL1/Meshes/SM_Roadblock_01a", "/Game/Construction_VOL1/Meshes/SM_Roadblock_02a",
    "/Game/Construction_VOL1/Meshes/SM_Roadblock_03a", "/Game/Construction_VOL1/Meshes/SM_Roadblock_04a",
    "/Game/Prop/CONSTRUCTION/Kit_Fence/Mesh/SM_ChainLinkFence_D01_N1", "/Game/Prop/CONSTRUCTION/Kit_Fence/Mesh/SM_ChainLinkFence_D02_N1",
    "/Game/Prop/CONSTRUCTION/Kit_Fence/Mesh/SM_ChainLinkFence_D03_N1", "/Game/Prop/CONSTRUCTION/Kit_Fence/Mesh/SM_Fence_ChainLink_A01_N1",
    "/Game/Prop/CONSTRUCTION/Kit_Fence/Mesh/SM_Fence_ChainLink_B01_N1", "/Game/Construction_VOL1/Meshes/SM_construction_fence_01a",
    "/Game/Construction_VOL1/Meshes/SM_LightGenerator_01a"]


def samples():
    """A row of the pieces a layout could use, to choose among them by eye (BAY_TRAINING_SAMPLES=1 adds it as the
    layout "Samples"; tour.ps1 -Structure TRAIN_Samples -Extra "-WSPC2Layout=Samples"). Not part of the game."""
    actors, views = [], []
    ue = lambda x, y, z: (x * 100.0, -y * 100.0, z * 100.0)
    y = PAD_S + 60.0
    for i, mesh in enumerate(SAMPLES):
        x = PAD_W + 40.0 + 7.0 * i
        z = float(sectors.pt_z(x))
        actors.append({"mesh": mesh, "x": round(x * 100.0, 1), "y": round(-y * 100.0, 1), "z": round(z * 100.0, 1), "yaw": 0.0, "pitch": 0.0,
                       "scale": 1.0, "physics": False, "label": "Sample_%02d_%s" % (i, mesh.rsplit("/", 1)[-1]), "tags": []})
        if i % 2 == 0:
            views.append(("TRAIN_Samples_%02d" % i, ue(x + 3.5, y - 7.0, z + 1.6), ue(x + 3.5, y, z + 0.8)))
    folder = os.path.join(DATA, "structures", "TRAIN_Samples")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "views.txt"), "w") as f:
        for label, p, t in views:
            f.write("%s;%.0f,%.0f,%.0f;%.0f,%.0f,%.0f\n" % (label, p[0], p[1], p[2], t[0], t[1], t[2]))
    print("TRAINING Samples: %d pieces in a row, %d cameras" % (len(actors), len(views)))
    return {"operation": 0, "title": "samples", "closed": False, "markers": [], "line": [], "ramp": None, "targets": [], "parked_car": None,
            "actors": actors}


def main():
    with open(CAMPAIGN, encoding="utf-8") as f:
        operations = {o["id"]: o for o in json.load(f)["operations"]}
    layouts = {name: plan(name, spec, operations[spec["operation"]]) for name, spec in LAYOUTS.items()}
    if os.environ.get("BAY_TRAINING_SAMPLES"):
        layouts["Samples"] = samples()
    cx = (PAD_W + PAD_E) / 2.0
    out = {"pad": {"west": PAD_W, "east": PAD_E, "south": PAD_S, "north": PAD_N},
           "director": {"x": round(cx * 100.0, 1), "y": round(-(PAD_S + PAD_N) / 2.0 * 100.0, 1),
                        "z": round((float(sectors.pt_z(cx)) + 0.5) * 100.0, 1)},
           "tag_prefix": "WSPC2Layout.", "physics_tag": "WSPC2Physics", "layouts": layouts}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "layouts.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print("TRAINING -> %s" % os.path.join(OUT, "layouts.json"))


if __name__ == "__main__":
    main()
