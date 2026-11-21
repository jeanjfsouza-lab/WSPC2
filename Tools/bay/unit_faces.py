"""Measures which sides of each merged building carry a facade and which are blank party walls.

  UnrealEditor-Cmd.exe D:/Github/WSPC2/WSPC2.uproject -run=pythonscript -script="D:/Github/WSPC2/Tools/bay/unit_faces.py"
  (or: .\\Tools\\bay\\build.ps1 -Script unit_faces.py -Commandlet)

Input:  Saved/CityMap/building_units.json, Saved/Bay/tower_units.json   the merged buildings and their meshes
        Saved/Bay/extra_units.json   the houses and warehouses of the newer districts (extra_units.py), optional
Output: Saved/Bay/unit_faces.json   {unit name: {"+x": n, "-x": n, "+y": n, "-y": n, "up": n, "polygons": n}}
        n = how many of the model's polygons face that way (model axes, Unreal units: +y is the model's "south").

Why: a row building shows windows on its street side and a blank wall to its neighbours. A facade is made of
thousands of small polygons (window frames, sills, cornices), a blank wall of a handful, so the count per
side tells the two apart. plan_lots.py reads the result to turn every building's facade to its street.
At most SAMPLE polygons per mesh are read (evenly spread), which is plenty for a ratio.
"""
import json
import os

import unreal

PROJECT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(PROJECT, "Saved", "Bay", "unit_faces.json")
SAMPLE = 40000


def log(text):
    unreal.log("FACES " + text)


def main():
    units = []
    for path in (os.path.join(PROJECT, "Saved", "CityMap", "building_units.json"), os.path.join(PROJECT, "Saved", "Bay", "tower_units.json"),
                 os.path.join(PROJECT, "Saved", "Bay", "extra_units.json")):
        if os.path.exists(path):
            with open(path) as f:
                units += json.load(f)
    result = {}
    if os.path.exists(OUT):
        with open(OUT) as f:
            result = json.load(f)
    shown = False
    for u in units:
        if u["name"] in result:
            continue
        if not shown:
            probe = unreal.load_asset(u["meshes"][0]).get_static_mesh_description(0)
            log("mesh description offers: %s" % ", ".join(m for m in dir(probe) if "polygon" in m or "triangle" in m or "normal" in m))
            shown = True
        tally = {"+x": 0, "-x": 0, "+y": 0, "-y": 0, "up": 0, "polygons": 0}
        for mesh_path in u["meshes"]:
            mesh = unreal.load_asset(mesh_path)
            if mesh is None:
                log("missing mesh %s" % mesh_path)
                continue
            desc = mesh.get_static_mesh_description(0)
            if desc is None:
                log("no mesh description for %s" % mesh_path)
                continue
            count = desc.get_polygon_count()
            step = max(1, count // SAMPLE)
            weight = float(step)
            for i in range(0, count, step):
                pid = unreal.PolygonID(i)
                if not desc.is_polygon_valid(pid):
                    continue
                # the polygon's normal from its first three corners
                corners = desc.get_polygon_vertices(pid)
                if len(corners) < 3:
                    continue
                a, b, c = (desc.get_vertex_position(v) for v in corners[:3])
                n = (b - a).cross(c - a)
                size = n.length()
                if size < 1e-9:
                    continue
                n = n / size
                tally["polygons"] += weight
                if n.x > 0.7:
                    tally["+x"] += weight
                elif n.x < -0.7:
                    tally["-x"] += weight
                elif n.y > 0.7:
                    tally["+y"] += weight
                elif n.y < -0.7:
                    tally["-y"] += weight
                elif n.z > 0.7:
                    tally["up"] += weight
        result[u["name"]] = {k: int(v) for k, v in tally.items()}
        log("%-42s +x %7d  -x %7d  +y %7d  -y %7d  up %7d  of %d" % (
            u["name"], tally["+x"], tally["-x"], tally["+y"], tally["-y"], tally["up"], tally["polygons"]))
        with open(OUT, "w") as f:
            json.dump(result, f, indent=1)
    log("DONE %d units -> %s" % (len(result), OUT))


main()
