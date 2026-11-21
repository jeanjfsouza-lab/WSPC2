"""Decides which sublevel of the Bay map each sector and each structure belongs to (one sublevel per district).

  python -P Tools/bay/plan_levels.py

The Bay map is split so a build opens and saves only the districts it changes, not all 18 000 actors at once:
  /Game/Bay/Maps/WSPC2_Bay                       the persistent map: landscape, sea, light, player start, training
                                                 ground and the list of sublevels (all always loaded)
  /Game/Bay/Maps/Districts/WSPC2_Bay_<district>  one per district: its sectors' ground, buildings and props, and
                                                 the bridges, tunnels, viaducts and places that stand in it
  /Game/Bay/Maps/Districts/WSPC2_Bay_Country     the trees of the hills round the city
A sector's district is the letters its name starts with (CW12 -> CW, IOX3 -> IOX). A structure goes to the district
of the sector it stands in: the sector whose outline holds its centre (the "at" point in structures.py, the
"centre" of sectors.PLACES, or else the middle of its mesh), the nearest sector box if none does.

Input:  Tools/bay/sectors.py, Tools/bay/structures.py, Saved/Bay/sectors/*/<name>_Ground.glb,
        Saved/Bay/structures/*/<name>.glb
Output: Saved/Bay/levels.json  {"sectors": {name: district}, "structures": {name: district},
                                "levels": {district: map path}, "persistent": map path}
        prints how many sectors and structures each district has
Run by build.ps1 before every build of the Bay map; build_bay.py reads the file.
"""
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA
import sectors
import structures

PERSISTENT = "/Game/Bay/Maps/WSPC2_Bay"
LEVEL = "/Game/Bay/Maps/Districts/WSPC2_Bay_%s"
COUNTRY = "Country"


def district_of_name(name):
    return re.match(r"[A-Z]+", name).group(0)


def glb_centre(path):
    """Middle of the POSITION bounds of a .glb (glTF is y up: x east, z south), in metres (east, north)."""
    with open(path, "rb") as f:
        data = f.read()
    length = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20:20 + length].decode("utf-8"))
    lo, hi = [1e18, 1e18], [-1e18, -1e18]
    for mesh in doc.get("meshes", []):
        for prim in mesh.get("primitives", []):
            acc = doc["accessors"][prim["attributes"]["POSITION"]]
            if "min" in acc and "max" in acc:
                lo = [min(lo[0], acc["min"][0]), min(lo[1], -acc["max"][2])]
                hi = [max(hi[0], acc["max"][0]), max(hi[1], -acc["min"][2])]
    if lo[0] > hi[0]:
        return None
    return ((lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0)


def main():
    built = [n for n, v in sectors.SECTORS.items() if v.get("status") in ("built", "done")]
    on_disk = [n for n in os.listdir(os.path.join(DATA, "sectors"))
               if os.path.exists(os.path.join(DATA, "sectors", n, n + "_Ground.glb"))]
    sector_level = {n: district_of_name(n) for n in sorted(set(built) | set(on_disk))}

    def district_at(x, y):
        inside = [n for n in sector_level if n in sectors.SECTORS and sectors.contains(sectors.outline(n), x, y)]
        if inside:
            return sector_level[inside[0]]
        best, near = 1e18, None
        for n in sector_level:
            if n not in sectors.SECTORS:
                continue
            w, e, s, nn = sectors.SECTORS[n]["box"]
            d = max(w - x, 0.0, x - e) ** 2 + max(s - y, 0.0, y - nn) ** 2
            if d < best:
                best, near = d, sector_level[n]
        return near

    known = {}
    for table in ("STRUCTURES", "TUNNELS", "VIADUCTS"):
        for name, spec in getattr(structures, table, {}).items():
            if "at" in spec:
                at = spec["at"]
                if isinstance(at[0], (list, tuple)):          # a few points (a long bridge): their middle
                    at = (sum(p[0] for p in at) / len(at), sum(p[1] for p in at) / len(at))
                known[name] = (float(at[0]), float(at[1]))
    for name, spec in getattr(sectors, "PLACES", {}).items():
        if spec.get("sector") in sector_level:
            known[name] = ("sector", spec["sector"])
        elif "centre" in spec:
            known[name] = tuple(spec["centre"])

    structure_level = {}
    folder = os.path.join(DATA, "structures")
    for name in sorted(os.listdir(folder)):
        glb = os.path.join(folder, name, name + ".glb")
        if not os.path.exists(glb):
            continue
        where = known.get(name)
        if where and where[0] == "sector":
            structure_level[name] = sector_level[where[1]]
            continue
        if where is None:
            where = glb_centre(glb)
        structure_level[name] = district_at(*where) if where else None

    districts = sorted(set(sector_level.values()) | {d for d in structure_level.values() if d}) + [COUNTRY]
    out = {"persistent": PERSISTENT, "sectors": sector_level, "structures": structure_level,
           "levels": {d: LEVEL % d for d in districts}}
    with open(os.path.join(DATA, "levels.json"), "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    for d in districts:
        ns = sum(1 for v in sector_level.values() if v == d)
        nt = [k for k, v in structure_level.items() if v == d]
        print("LEVELS %-7s %3d sectors, %2d structures %s" % (d, ns, len(nt), " ".join(nt)))
    lost = [k for k, v in structure_level.items() if not v]
    print("LEVELS %d districts (+ Country) -> %s%s" % (len(districts) - 1, os.path.join(DATA, "levels.json"),
                                                     ("; structures with no district: %s" % lost) if lost else ""))


if __name__ == "__main__":
    main()
