"""Imports the synthesised weapon sounds as /Game/Audio/Generated/WSPC2_Gun_<Name> (commandlet).

  UnrealEditor-Cmd.exe D:/Github/WSPC2/WSPC2.uproject -run=pythonscript -script="D:/Github/WSPC2/Tools/audio/import_gunshots.py"

The script path must be absolute: a relative one is looked up in the engine's own Binaries folder.

Reads Saved/Audio/WSPC2_Gun_{Pistol,Shotgun,Rifle,Reload,Draw}.wav (from Tools/audio/make_gunshots.py).
UWSPC2GunneryComponent loads them at runtime; without them the weapons are silent.
"""
import os

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
FOLDER = "/Game/Audio/Generated"
NAMES = ["Pistol", "Shotgun", "Rifle", "Reload", "Draw"]


def main():
    tasks = []
    for name in NAMES:
        source = os.path.join(PROJECT, "Saved", "Audio", "WSPC2_Gun_%s.wav" % name)
        if not os.path.exists(source):
            unreal.log_error("GUNSOUND missing %s; run Tools/audio/make_gunshots.py first" % source)
            return
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", source)
        task.set_editor_property("destination_path", FOLDER)
        task.set_editor_property("destination_name", "WSPC2_Gun_%s" % name)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", False)
        tasks.append(task)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)

    for name in NAMES:
        path = "%s/WSPC2_Gun_%s" % (FOLDER, name)
        sound = unreal.EditorAssetLibrary.load_asset(path)
        if not sound:
            unreal.log_error("GUNSOUND import failed for %s" % path)
            continue
        sound.set_editor_property("looping", False)
        unreal.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False)
        unreal.log("GUNSOUND imported %s, %.2f s" % (path, sound.get_editor_property("duration")))


main()
