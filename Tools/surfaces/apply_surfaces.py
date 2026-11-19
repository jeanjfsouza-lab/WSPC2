"""Gives every drivable surface its own grip: asphalt, concrete, dirt, grass, sand and rock (commandlet).

  UnrealEditor-Cmd.exe D:/Github/WSPC2/WSPC2.uproject -run=pythonscript -script="D:/Github/WSPC2/Tools/surfaces/apply_surfaces.py"

The script path must be absolute: a relative one is looked up in the engine's own Binaries folder.
Run it with the editor closed, and again after rebuilding any map: the map builders assign plain materials.

What it does
  1. Creates the physical materials /Game/Surfaces/PM_<Surface>. The tyres multiply their own grip by the
     friction of whatever they touch, so these numbers are the whole difference between surfaces.
     Asphalt is 1.0, the same as an untagged surface: a surface nobody tagged behaves like asphalt.
  2. Generated ground meshes (test track, both cities): each material slot is named after what it is
     (Road, Sidewalk, Dirt, Grass...). The slot's material is replaced by a child instance in
     /Game/Surfaces/Materials that looks the same and carries the physical material. Pack materials are
     not edited, and two slots sharing one material can still be different surfaces.
  3. WSPC2_Metro's landscape: the paint layers (Saved/CityMap/landscape.json) get the physical material on
     their layer info assets.

Reads   Saved/CityMap/landscape.json (optional), Tools/citymap/build_citymap.py (LAYER_SETUP, for layer numbers)
Writes  /Game/Surfaces/**, the generated static meshes' material slots, the City Park layer info assets
Logs    lines starting with SURFACES
"""
import json
import os
import re

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
ROOT = "/Game/Surfaces"

# Friction of the surface itself (dry), relative to asphalt = 1.0. An untagged surface reports the vehicle
# template's "NonSlippery" material, also 1.0, which is what the handling was measured on (0.82 g of braking).
SURFACES = {
    "Asphalt": (1.00, unreal.PhysicalSurface.SURFACE_TYPE1),
    "Concrete": (0.96, unreal.PhysicalSurface.SURFACE_TYPE2),
    "Rock": (0.85, unreal.PhysicalSurface.SURFACE_TYPE3),
    "Dirt": (0.65, unreal.PhysicalSurface.SURFACE_TYPE4),
    "Sand": (0.54, unreal.PhysicalSurface.SURFACE_TYPE5),
    "Grass": (0.50, unreal.PhysicalSurface.SURFACE_TYPE6),
}

# material slot of a generated mesh -> surface
SLOT_SURFACE = {
    "Road": "Asphalt", "Yard": "Asphalt", "PaintWhite": "Asphalt", "PaintYellow": "Asphalt",
    "Sidewalk": "Concrete", "Curb": "Concrete", "Concrete": "Concrete", "Lot": "Concrete",
    "Dirt": "Dirt", "Grass": "Grass", "Sand": "Sand",
    "Wild": "Grass",        # the Bay city's natural ground inside a sector (dry grass, grass, bare earth)
    "Plaza": "Concrete",    # the Bay city's squares, paved in stone slabs
    "Path": "Dirt",         # ...and the gravel paths of its parks
}

# landscape paint layer (Tools/citymap/build_terrain_data.py) -> surface
LAYER_SURFACE = {
    "Asphalt": "Asphalt", "Pavement": "Concrete", "Rock": "Rock",
    "Dirt": "Dirt", "Soil": "Dirt", "Sand": "Sand", "Grass": "Grass",
}

MESH_FOLDERS = ["/Game/TestTrack/Generated", "/Game/City/Generated", "/Game/CityMap/Generated", "/Game/Bay/Generated"]
LAYER_INFO = "/Game/CityPark/Maps/Showcase_sharedassets/%d_LayerInfo"

assets = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()


def log(text):
    unreal.log("SURFACES " + text)


def physical_material(surface):
    friction, surface_type = SURFACES[surface]
    name = "PM_" + surface
    path = "%s/%s" % (ROOT, name)
    material = assets.load_asset(path) if assets.does_asset_exist(path) else \
        tools.create_asset(name, ROOT, unreal.PhysicalMaterial, unreal.PhysicalMaterialFactoryNew())
    material.set_editor_property("friction", friction)
    material.set_editor_property("static_friction", friction)
    material.set_editor_property("surface_type", surface_type)
    assets.save_asset(path, only_if_is_dirty=False)
    return material


def tagged_instance(material, surface, physical):
    """A child of `material` that renders the same and reports `physical` to whatever drives over it."""
    # a material already tagged by an earlier run: go back to the original it was made from
    while isinstance(material, unreal.MaterialInstanceConstant) and material.get_path_name().startswith(ROOT + "/Materials/"):
        material = material.get_editor_property("parent")

    name = "MI_%s__%s" % (surface, material.get_name())
    folder = ROOT + "/Materials"
    path = "%s/%s" % (folder, name)
    if assets.does_asset_exist(path):
        instance = assets.load_asset(path)
    else:
        instance = tools.create_asset(name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    unreal.MaterialEditingLibrary.set_material_instance_parent(instance, material)
    instance.set_editor_property("phys_material", physical)
    assets.save_asset(path, only_if_is_dirty=False)
    return instance


def tag_meshes(physicals):
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.scan_paths_synchronous(MESH_FOLDERS, True)
    counts = {}
    unknown = set()

    for folder in MESH_FOLDERS:
        for data in registry.get_assets_by_path(folder, recursive=True):
            if str(data.asset_class_path.asset_name) != "StaticMesh":
                continue
            mesh = data.get_asset()
            changed = False
            for index, slot in enumerate(mesh.static_materials):
                slot_name = str(slot.material_slot_name)
                surface = SLOT_SURFACE.get(slot_name)
                if not surface:
                    unknown.add(slot_name)
                    continue
                if not slot.material_interface:
                    continue
                mesh.set_material(index, tagged_instance(slot.material_interface, surface, physicals[surface]))
                counts[surface] = counts.get(surface, 0) + 1
                changed = True
            if changed:
                assets.save_asset(str(data.package_name), only_if_is_dirty=False)

    log("mesh slots tagged: %s" % ", ".join("%s %d" % item for item in sorted(counts.items())))
    if unknown:
        log("slots left as they were (no surface assigned): %s" % ", ".join(sorted(unknown)))


def landscape_layer_numbers():
    """Our layer name -> the City Park material's layer number, read from the map builder so the two cannot drift."""
    source = open(os.path.join(PROJECT, "Tools", "citymap", "build_citymap.py"), encoding="utf-8").read()
    block = re.search(r"LAYER_SETUP\s*=\s*\{(.*?)\n\}", source, re.S)
    return {name: int(number) for name, number in re.findall(r'"(\w+)"\s*:\s*\(\s*(\d+)\s*,', block.group(1))} if block else {}


def tag_landscape(physicals):
    info_path = os.path.join(PROJECT, "Saved", "CityMap", "landscape.json")
    if not os.path.exists(info_path):
        log("no Saved/CityMap/landscape.json: landscape layers skipped")
        return

    numbers = landscape_layer_numbers()
    for layer in json.load(open(info_path))["layers"]:
        surface = LAYER_SURFACE.get(layer)
        number = numbers.get(layer)
        if not surface or not number:
            log("landscape layer %s skipped (surface %s, material layer %s)" % (layer, surface, number))
            continue
        path = LAYER_INFO % number
        info = assets.load_asset(path)
        if not info:
            log("landscape layer %s: missing %s" % (layer, path))
            continue
        info.set_editor_property("phys_material", physicals[surface])
        assets.save_asset(path, only_if_is_dirty=False)
        log("landscape layer %s (material layer %d) -> %s" % (layer, number, surface))


def main():
    physicals = {surface: physical_material(surface) for surface in SURFACES}
    log("physical materials: %s" % ", ".join("%s %.2f" % (name, values[0]) for name, values in SURFACES.items()))
    tag_meshes(physicals)
    tag_landscape(physicals)
    log("done")


main()
