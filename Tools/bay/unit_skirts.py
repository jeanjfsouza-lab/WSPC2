"""Measures, for each walk-up row model, where its walls stop short of the ground (commandlet).

  .\\Tools\\bay\\build.ps1 -Script unit_skirts.py -Commandlet
  (or: UnrealEditor-Cmd.exe D:/Github/WSPC2/WSPC2.uproject -run=pythonscript
       -script="D:/Github/WSPC2/Tools/bay/unit_skirts.py"   -- the path must be absolute)

Input:  Saved/CityMap/building_units.json, Saved/Bay/tower_units.json   the merged buildings and their meshes
        environment BAY_SKIRT_UNITS (optional): names of other models to measure too, comma separated
Output: Saved/Bay/unit_skirts.json   {unit name: {side: {"open": share, "gap": m, "wall": m, "from": m, "to": m}}}
            side   "+x", "-x", "+y", "-y" (model axes)
            open   share of that side's length (where it has a wall at all) where the wall starts above GROUND_M
            gap    how high above the floor the wall starts there (90th percentile of the open stretches)
            wall   how far behind the bounding box's side the wall's own plane lies
            from, to   where the open stretch lies along the side, in metres from the side's low end
        A model already in the file is not measured again: delete the file to start over.

Why: the walk-up row models of the City Sample are made to stand between neighbours on a sidewalk. Their
long side walls start about 1.3 m above the floor over nine tenths of their length: at the free end of a
row, or along a service lane, you see under the building to the daylight on the other side.
plan_plinths.py reads this file and sets a plain plinth under every building that needs one.

How. Every polygon of the model that faces a side (its normal within 45 degrees of that side's axis) and lies
within BAND_M of the bounding box's side is laid over that side's length in bins of BIN_M: each bin keeps the
lowest height any such polygon reaches. Polygons, not vertices: a plain wall is one large polygon with a
vertex only at each corner. A bin no polygon covers has no wall (a passage, a deep porch) and is not counted.
Only walk-up shaped models are measured (narrow and deep, the test plan_lots.py uses): reading every polygon
of the large models takes minutes each, and their walls have been seen to reach the ground.
"""
import json
import os

import unreal

PROJECT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(PROJECT, "Saved", "Bay", "unit_skirts.json")
BAND_M = 1.6            # how far in from the bounding box a wall may stand (cornices and stoops overhang)
STOREY_M = 6.0          # only the ground storey is looked at
BIN_M = 2.0
GROUND_M = 0.35         # a wall that starts higher than this does not reach the ground
SIDES = {"-x": (0, 0, 1), "+x": (0, 1, 1), "-y": (1, 0, 0), "+y": (1, 1, 0)}      # axis, low or high end, axis along


def log(text):
    unreal.log("SKIRTS " + text)


def walk_up(u):
    w, d = u["ue_hi"][0] - u["ue_lo"][0], u["ue_hi"][1] - u["ue_lo"][1]
    return min(w, d) < 14.0 and max(w, d) > 2.5 * min(w, d)


def measure(u):
    lo, hi = u["ue_lo"], u["ue_hi"]                     # metres, model axes
    lowest = {s: {} for s in SIDES}                     # side -> {bin: lowest height reached (m)}
    depth = {s: {} for s in SIDES}                      # side -> {distance behind the side in 5 cm steps: area}
    polygons = 0
    for mesh_path in u["meshes"]:
        mesh = unreal.load_asset(mesh_path)
        desc = mesh.get_static_mesh_description(0) if mesh else None
        if desc is None:
            log("no mesh description for %s" % mesh_path)
            continue
        for i in range(desc.get_polygon_count()):
            pid = unreal.PolygonID(i)
            if not desc.is_polygon_valid(pid):
                continue
            corners = desc.get_polygon_vertices(pid)
            if len(corners) < 3:
                continue
            pts = [desc.get_vertex_position(v) for v in corners]
            z_low = min(p.z for p in pts) / 100.0
            if z_low > STOREY_M:
                continue
            n = (pts[1] - pts[0]).cross(pts[2] - pts[0])
            size = n.length()
            if size < 1e-6:
                continue
            if abs(n.x) > 0.7 * size:
                axis = 0
            elif abs(n.y) > 0.7 * size:
                axis = 1
            else:
                continue
            polygons += 1
            xy = [(p.x / 100.0, p.y / 100.0) for p in pts]
            where = sum(q[axis] for q in xy) / len(xy)
            z_high = max(p.z for p in pts) / 100.0
            for side, (side_axis, high, along) in SIDES.items():
                plane = hi[side_axis] if high else lo[side_axis]
                if side_axis != axis or abs(where - plane) > BAND_M:
                    continue
                first = int((min(q[along] for q in xy) - lo[along]) // BIN_M)
                last = int((max(q[along] for q in xy) - lo[along]) // BIN_M)
                for b in range(first, last + 1):
                    if z_low < lowest[side].get(b, 1e9):
                        lowest[side][b] = z_low
                if z_high >= 1.5 and z_low <= 4.5:      # the ground storey's wall, above any plinth line
                    step = int(abs(where - plane) / 0.05)
                    depth[side][step] = depth[side].get(step, 0.0) + size
    entry = {}
    for side, (side_axis, high, along) in SIDES.items():
        bins = int((hi[along] - lo[along]) // BIN_M) + 1
        walled = [b for b in range(bins) if b in lowest[side]]
        open_bins = [b for b in walled if GROUND_M < lowest[side][b] < 4.0]
        gaps = sorted(lowest[side][b] for b in open_bins)
        wall = max(depth[side].items(), key=lambda kv: kv[1])[0] * 0.05 if depth[side] else 0.0
        entry[side] = {"open": round(len(open_bins) / max(1, len(walled)), 2),
                       "gap": round(gaps[int(len(gaps) * 0.9)] if gaps else 0.0, 2), "wall": round(wall, 2),
                       "from": round(min(open_bins) * BIN_M, 1) if open_bins else 0.0,
                       "to": round((max(open_bins) + 1) * BIN_M, 1) if open_bins else 0.0}
    return entry, polygons


def main():
    units = []
    for path in (os.path.join(PROJECT, "Saved", "CityMap", "building_units.json"), os.path.join(PROJECT, "Saved", "Bay", "tower_units.json")):
        if os.path.exists(path):
            with open(path) as f:
                units += json.load(f)
    extra = [n.strip() for n in os.environ.get("BAY_SKIRT_UNITS", "").split(",") if n.strip()]
    result = {}
    if os.path.exists(OUT):
        with open(OUT) as f:
            result = json.load(f)
    for u in units:
        if u["name"] in result or not (walk_up(u) or u["name"] in extra):
            continue
        entry, polygons = measure(u)
        result[u["name"]] = entry
        log("%-28s %s  (%d wall polygons)" % (u["name"], "  ".join(
            "%s open %3.0f%% gap %.2f wall %.2f [%.0f..%.0f]" % (s, e["open"] * 100, e["gap"], e["wall"], e["from"], e["to"])
            for s, e in entry.items()), polygons))
        with open(OUT, "w") as f:
            json.dump(result, f, indent=1)
    log("DONE %d units -> %s" % (len(result), OUT))


main()
