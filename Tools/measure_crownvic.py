"""Prints the bounds of the imported sedan meshes, to check scale and orientation."""
import unreal

for path in ("/Game/CrownVic/CrownVic_Body/StaticMeshes/CrownVic_Body",
             "/Game/CrownVic/CrownVic_Wheel/StaticMeshes/CrownVic_Wheel"):
    mesh = unreal.EditorAssetLibrary.load_asset(path)
    if not mesh:
        unreal.log_error("WSPC2MEASURE missing %s" % path)
        continue
    bounds = mesh.get_bounds()
    o, e = bounds.origin, bounds.box_extent
    unreal.log("WSPC2MEASURE %s min (%.1f, %.1f, %.1f) max (%.1f, %.1f, %.1f) tris %d" % (
        path.split("/")[-1],
        o.x - e.x, o.y - e.y, o.z - e.z,
        o.x + e.x, o.y + e.y, o.z + e.z,
        mesh.get_num_triangles(0)))
