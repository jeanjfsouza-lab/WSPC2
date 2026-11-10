"""Imports the processed sedan model into /Game/CrownVic.

Run with the editor closed:
  UnrealEditor-Cmd.exe WSPC2.uproject -run=pythonscript -script=Tools/import_crownvic.py

The source files live in 'ASSETS TO USE/processed' and, like the imported
assets, are kept out of git.
"""
import os

import unreal

PROJECT_DIR = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
SOURCE_DIR = os.path.join(PROJECT_DIR, "ASSETS TO USE", "processed")
DEST = "/Game/CrownVic"


def import_file(filename):
    task = unreal.AssetImportTask()
    task.filename = os.path.join(SOURCE_DIR, filename)
    task.destination_path = DEST
    task.automated = True
    task.replace_existing = True
    task.save = True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    unreal.log("WSPC2IMPORT imported %s -> %s" % (filename, list(task.imported_object_paths)))


import_file("CrownVic_Body.glb")
import_file("CrownVic_Wheel.glb")

registry = unreal.AssetRegistryHelpers.get_asset_registry()

# Nanite cannot draw translucent materials, and the body has glass: use plain meshes.
# (Set through the property: editor subsystems do not exist in a commandlet.)
for data in registry.get_assets_by_path(DEST, recursive=True):
    if str(data.asset_class_path.asset_name) == "StaticMesh":
        mesh = data.get_asset()
        settings = mesh.get_editor_property("nanite_settings")
        unreal.log("WSPC2IMPORT %s nanite was %s, triangles %d" % (data.asset_name, settings.enabled, mesh.get_num_triangles(0)))
        settings.enabled = False
        mesh.set_editor_property("nanite_settings", settings)
        unreal.log("WSPC2IMPORT %s triangles now %d" % (data.asset_name, mesh.get_num_triangles(0)))

unreal.EditorAssetLibrary.save_directory(DEST, only_if_is_dirty=False, recursive=True)

for data in registry.get_assets_by_path(DEST, recursive=True):
    if str(data.asset_class_path.asset_name) == "StaticMesh":
        mesh = data.get_asset()
        box = mesh.get_bounding_box()
        unreal.log("WSPC2IMPORT mesh %s min %s max %s materials %d" % (
            data.package_name, box.min, box.max, len(mesh.static_materials)))

counts = {}
for data in registry.get_assets_by_path(DEST, recursive=True):
    name = str(data.asset_class_path.asset_name)
    counts[name] = counts.get(name, 0) + 1
unreal.log("WSPC2IMPORT asset counts %s" % counts)
