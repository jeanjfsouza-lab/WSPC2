"""Gives the Bay city's generated ground meshes their grip per surface, and only those (commandlet).

  .\\Tools\\bay\\build.ps1 -Script apply_bay_surfaces.py -Commandlet
  (or: UnrealEditor-Cmd.exe D:/Github/WSPC2/WSPC2.uproject -run=pythonscript
       -script="D:/Github/WSPC2/Tools/bay/apply_bay_surfaces.py"   -- the path must be absolute)

Why this exists. Tools/surfaces/apply_surfaces.py goes through the generated meshes of every map, oldest map
first, and saves each one again. On 2026-11-13 one mesh of the first city
(/Game/CityMap/Generated/City_Sidewalks/StaticMeshes/Sidewalk_-3_-2) turned out to be damaged on disk: its
compressed mesh data no longer decompresses, and saving it brings the editor down before the pass reaches
/Game/Bay/Generated. A Bay build only re-imports Bay meshes, so the Bay only needs its own folder done; that
is also quicker (one folder instead of four).

It runs the very code of apply_surfaces.py: that file's source is loaded as it is, without its closing call
to main(), and its folder list is cut down to the Bay's. The two cannot drift apart; if that file stops ending
with main(), this script says so and stops.

Inputs   Tools/surfaces/apply_surfaces.py, /Game/Bay/Generated/** (static meshes with named material slots)
Outputs  /Game/Surfaces/PM_<Surface>, /Game/Surfaces/Materials/MI_<Surface>__<material>, and the Bay meshes'
         material slots pointing at them
Logs     lines starting with SURFACES; the last one is "SURFACES done (Bay only)"
"""
import os

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
SOURCE = os.path.join(PROJECT, "Tools", "surfaces", "apply_surfaces.py")
BAY_FOLDERS = ["/Game/Bay/Generated", "/Game/Bay/Training"]      # the training ground's ramp is driven on too


def run():
    with open(SOURCE, encoding="utf-8") as f:
        source = f.read()
    body, call, rest = source.rstrip().rpartition("\nmain()")
    if not call or rest.strip():
        raise RuntimeError("Tools/surfaces/apply_surfaces.py no longer ends with a call to main(): "
                           "Tools/bay/apply_bay_surfaces.py has to be brought up to date with it")
    scope = {"__name__": "apply_surfaces", "__file__": SOURCE}
    exec(compile(body, SOURCE, "exec"), scope)
    scope["MESH_FOLDERS"][:] = BAY_FOLDERS            # the functions read this list from their own module
    # that file makes and saves the tagged material again for every slot of every mesh: 340 saves of the same
    # dozen assets, four minutes of a five-minute pass (2026-11-13). Once per material and surface is enough.
    make, made = scope["tagged_instance"], {}

    def once(material, surface, physical):
        key = (material.get_path_name(), surface)
        if key not in made:
            made[key] = make(material, surface, physical)
        return made[key]

    scope["tagged_instance"] = once
    physicals = {surface: scope["physical_material"](surface) for surface in scope["SURFACES"]}
    scope["log"]("Bay only: physical materials %s" % ", ".join(
        "%s %.2f" % (name, values[0]) for name, values in scope["SURFACES"].items()))
    scope["tag_meshes"](physicals)
    scope["log"]("done (Bay only)")


run()
