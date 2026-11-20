"""Makes the building collision boxes of WSPC2_Bay invisible in the editor too, and saves the map (full editor).

  UnrealEditor-Cmd.exe D:/Github/WSPC2/WSPC2.uproject -ExecutePythonScript="D:/Github/WSPC2/Tools/bay/hide_collision_boxes.py" -unattended -RenderOffscreen -nosplash -nosound

Each building has an invisible cube as its collision (Tools/bay/build_bay.py, actors "<sector>_BuildingCollision").
They were only hidden in game, so the editor drew them as grey blocks over the real buildings.
UWSPC2CityTools::SpawnInstancedMeshes now makes such boxes invisible everywhere; this script applies the same
to the map already built, without rebuilding it. Collision is unchanged (it does not depend on visibility).

Inputs:  /Game/Bay/Maps/WSPC2_Bay. Outputs: the same map, saved; a HIDEBOXES line with the count in the log.
The editor must be closed (the map is opened and saved here).
"""
import unreal

MAP = "/Game/Bay/Maps/WSPC2_Bay"


def main():
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(MAP)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    changed = 0
    for actor in actors:
        if not actor.get_actor_label().endswith("_BuildingCollision"):
            continue
        for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            if component.get_editor_property("hidden_in_game") and component.get_editor_property("visible"):
                component.set_visibility(False)
                changed += 1
    if changed:
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    unreal.log("HIDEBOXES %d collision box sets made invisible in %s" % (changed, MAP))
    unreal.SystemLibrary.quit_editor()


main()
