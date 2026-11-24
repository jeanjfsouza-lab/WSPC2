"""Sets the ceiling of the master-bus limiter (SFX_WSPC2_MasterLimiter) without re-running the whole import.

Used to prove the limiter is on the output path (set a low ceiling, record, compare) and to tune it.

  $env:WSPC2_LIMITER_DB = "-12"; $env:WSPC2_LIMITER_LOOKAHEAD_MS = "10"
  UnrealEditor-Cmd.exe WSPC2.uproject -run=pythonscript -script="D:/Github/WSPC2/Tools/audio/pipeline/set_master_limiter.py" -unattended -nosplash

Inputs:  environment variables WSPC2_LIMITER_DB (ceiling, dBFS, default -3) and WSPC2_LIMITER_LOOKAHEAD_MS (default 10)
Outputs: /Game/Audio/Vehicles/Mix/SFX_WSPC2_MasterLimiter saved with the new threshold
"""
import os

import unreal

PATH = "/Game/Audio/Vehicles/Mix/SFX_WSPC2_MasterLimiter"
threshold = float(os.environ.get("WSPC2_LIMITER_DB", "-3"))
look_ahead = float(os.environ.get("WSPC2_LIMITER_LOOKAHEAD_MS", "10"))
preset = unreal.EditorAssetLibrary.load_asset(PATH)
if not preset:
    raise RuntimeError(f"missing {PATH}: run ue_import_and_build_assets.py first")
settings = preset.get_editor_property("settings")
settings.set_editor_property("threshold_db", threshold)
# same response as ue_import_and_build_assets.py: digital envelope, 1 ms attack
settings.set_editor_property("analog_mode", False)
settings.set_editor_property("look_ahead_msec", look_ahead)
settings.set_editor_property("attack_time_msec", 1.0)
preset.set_editor_property("settings", settings)
unreal.EditorAssetLibrary.save_asset(PATH, only_if_is_dirty=False)
unreal.log(f"AUDIOLIMITER threshold {threshold:.1f} dBFS saved")
