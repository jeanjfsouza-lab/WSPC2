"""Imports the synthesised siren as /Game/Audio/Generated/WSPC2_Siren_Wail (commandlet).

  UnrealEditor-Cmd.exe D:/Github/WSPC2/WSPC2.uproject -run=pythonscript -script="D:/Github/WSPC2/Tools/audio/import_siren.py"

The script path must be absolute: a relative one is looked up in the engine's own Binaries folder.

Reads Saved/Audio/WSPC2_Siren_Wail.wav (from Tools/audio/make_siren.py). The sound is set to loop and to keep
playing while silent, so turning the siren on never restarts it from the first sample.
"""
import os

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
SOURCE = os.path.join(PROJECT, "Saved", "Audio", "WSPC2_Siren_Wail.wav")
FOLDER = "/Game/Audio/Generated"
NAME = "WSPC2_Siren_Wail"


def main():
    if not os.path.exists(SOURCE):
        unreal.log_error("SIREN missing %s; run Tools/audio/make_siren.py first" % SOURCE)
        return

    task = unreal.AssetImportTask()
    task.set_editor_property("filename", SOURCE)
    task.set_editor_property("destination_path", FOLDER)
    task.set_editor_property("destination_name", NAME)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", False)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

    path = "%s/%s" % (FOLDER, NAME)
    wave = unreal.EditorAssetLibrary.load_asset(path)
    if not wave:
        unreal.log_error("SIREN import failed for %s" % path)
        return

    wave.set_editor_property("looping", True)
    wave.set_editor_property("virtualization_mode", unreal.VirtualizationMode.PLAY_WHEN_SILENT)
    unreal.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False)
    unreal.log("SIREN imported %s, %.2f s, %d channel(s)" % (path, wave.get_editor_property("duration"),
                                                             wave.get_editor_property("num_channels")))


main()
