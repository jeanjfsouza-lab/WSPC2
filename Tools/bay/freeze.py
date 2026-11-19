"""Freezes the junctions of the sectors already built, so later changes to the road network cannot move them.

  python -P Tools/bay/freeze.py [network file in Saved/Bay, default network.json]

Input:  Saved/Bay/<network file>, Tools/bay/sectors.py (sectors whose status is "built" or "done")
Output: Saved/Bay/frozen_nodes.json   [[x, y], ...]: every junction inside or within REACH_M of a built sector,
                                      and both ends of every built bridge and tunnel (structures.py), at the
                                      position they were built with. Earlier entries are kept.
        Saved/Bay/frozen_heights.json [[x, y, z], ...]: every height sample of every road that runs between two
                                      frozen junctions and of every built bridge and tunnel, as built.
                                      Earlier entries are kept.

Why: design_network.py straightens streets by fitting a line through a whole run of junctions. Add or remove a
road at one end of a street and the fitted line shifts by a few decimetres along its whole length, also inside
sectors whose meshes are already in the map. design_network.py reads this file and, after the straightening,
puts every frozen junction back where it was. Run this right after a sector passes its review, before the
network is edited again; pass the network file the sector was built from if network.json has moved on.

Heights: a road's height answers to the ground under it and to the roads it meets, and the limit on slopes
passes a change on from street to street. Mend the terrain beside a built district (terrain_base.py) or lay a
steep new street against it, and streets inside it would move by decimetres to metres. design_network.py
holds every sample listed here at its height: what is built stays as built, and the change stops at the first
junction of a built sector. (A road leaving a frozen junction for unbuilt land is not held: it is still to be
designed. The built sector it leaves keeps a few metres of it, so that sector is made again: make_sector.ps1
-Check names it.)
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sectors
import structures
from common import data_path, load_json, save_json

REACH_M = 45.0              # junctions this far outside a built sector shape its edge, so they are frozen too


def distance_to_ring(ring, x, y):
    best = 1e18
    for i in range(len(ring)):
        (ax, ay), (bx, by) = ring[i], ring[(i + 1) % len(ring)]
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / max(dx * dx + dy * dy, 1e-9)))
        best = min(best, math.hypot(x - ax - t * dx, y - ay - t * dy))
    return best


def main():
    net = load_json(sys.argv[1] if len(sys.argv) > 1 else "network.json")
    built = [name for name, spec in sectors.SECTORS.items() if spec.get("status") in ("built", "done")]
    rings = [sectors.outline(name) for name in built]
    frozen = load_json("frozen_nodes.json") if os.path.exists(data_path("frozen_nodes.json")) else []
    # the road of a bridge or tunnel already built is held from end to end, also where it reaches into land
    # no sector has been built on yet: its mesh was made from that road
    spans = set()
    span_ends = set()
    for specs, cls in ((structures.STRUCTURES, "bridge"), (structures.TUNNELS, "tunnel")):
        for spec in specs.values():
            if spec.get("status") in ("built", "done"):
                # (a bridge the network carries in pieces names a point on each: all of them are held)
                points = spec["at"] if isinstance(spec["at"][0], (list, tuple)) else [spec["at"]]
                for p in points:
                    edge = structures.find_edge(net, p, cls)
                    if edge is not None:
                        spans.add(edge["id"])
                        span_ends.update((edge["a"], edge["b"]))
    # the viaducts' edges too (level 1, any class)
    for name, spec in structures.VIADUCTS.items():
        if spec.get("status") in ("built", "done"):
            edge = structures.viaduct_edge(net, name)
            spans.add(edge["id"])
            span_ends.update((edge["a"], edge["b"]))
    added = 0
    for n in net["nodes"]:
        x, y = n["x"], n["y"]
        if n["id"] not in span_ends and not any(
                sectors.contains(ring, x, y) or distance_to_ring(ring, x, y) <= REACH_M for ring in rings):
            continue
        if any(math.hypot(x - fx, y - fy) < 3.0 for fx, fy in frozen):
            continue                                    # already frozen (at the position it was first built with)
        frozen.append([round(x, 3), round(y, 3)])
        added += 1
    save_json("frozen_nodes.json", frozen)

    # ...and the heights of the roads between frozen junctions, sample by sample
    def is_frozen(n):
        return any(math.hypot(n["x"] - fx, n["y"] - fy) < 3.0 for fx, fy in frozen)

    held = {n["id"] for n in net["nodes"] if is_frozen(n)}
    heights = load_json("frozen_heights.json") if os.path.exists(data_path("frozen_heights.json")) else []
    known = {(round(x, 2), round(y, 2)) for x, y, _ in heights}
    new = 0
    for e in net["edges"]:
        if e["id"] not in spans and (e["a"] not in held or e["b"] not in held):
            continue
        for x, y, z in e["pts"]:
            key = (round(x, 2), round(y, 2))
            if key not in known:
                known.add(key)
                heights.append([key[0], key[1], round(z, 2)])
                new += 1
    save_json("frozen_heights.json", heights)
    print("FREEZE %d junctions frozen (%d new) for built sectors: %s" % (len(frozen), added, ", ".join(built)))
    print("FREEZE %d road heights held (%d new), with the roads of %d built bridges and tunnels" % (len(heights), new, len(spans)))


if __name__ == "__main__":
    main()
