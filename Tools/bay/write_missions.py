"""Writes the campaign's first four missions into the game's mission data (commandlet).

  UnrealEditor-Cmd.exe D:/Github/WSPC2/WSPC2.uproject -run=pythonscript -script="D:/Github/WSPC2/Tools/bay/write_missions.py"

Input:  Saved/Bay/training/layouts.json   (Tools/bay/plan_training.py: the training yard's layouts Op01 and Op04, with
                                          their markers in Bay metres, the line to drive and the targets)
        Saved/Bay/campaign/operations.json (Tools/bay/plan_campaign.py: operations 02 and 03 placed in the Bay, markers
                                          and the routes of the player and the suspect in Bay metres)
        MISSIONS below: what the scenario documents (ASSETS TO USE/bay_city_3d/cenarios/0N_*.md) ask, with the times
        retuned to what the patrol car can do
Output: /Game/Bay/Missions/DA_Missions    UWSPC2MissionSet (Source/WSPC2/WSPC2Mission.h), read by AWSPC2MissionDirector;
                                          log lines tagged MISSIONS
Bay metres to Unreal: x_ue = 100 x, y_ue = -100 y, z_ue = 100 z (cm). Start yaws point at the first checkpoint or
along the route. Requires the game module built with UWSPC2MissionSet.
Play one: in WSPC2_Bay, console "Mission Op01" (or -WSPC2Mission=Op01 on the command line; add -WSPC2MissionAutopilot
for the test that drives itself).
"""
import json
import math
import os

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
LAYOUTS = os.path.join(PROJECT, "Saved", "Bay", "training", "layouts.json")
OPERATIONS = os.path.join(PROJECT, "Saved", "Bay", "campaign", "operations.json")
FOLDER = "/Game/Bay/Missions"
ASSET = FOLDER + "/DA_Missions"

# What each mission asks (scenario docs 01..04). The docs' times were set for faster cars: Op01's 48 s needs a 78 km/h
# average round 1,034 m of cones, Op04's 70 s a 56 km/h average with a 3 s stop; retuned, and kept here to tune.
MISSIONS = {
    "Op01": {"title": "Op 01 Circuito de Interceptacao", "kind": "CIRCUIT", "layout": "Op01", "laps": 2,
             "time": 100.0, "medal": 80.0, "max_cones": 3, "parked": "SUV",
             "briefing": "Duas voltas pelo tracado de cones (PC 01 a 05) e a chegada. Nao derrube 3 cones, nao bata na viatura "
                         "do instrutor, nao saia da area."},
    "Op02": {"title": "Op 02 Perseguicao Inicial", "kind": "CHASE", "op": "02", "suspect": "Undercover", "speed": 80.0,
             "leash_m": 128.0, "medal_damage": 50.0,
             "briefing": "Pare o Sedan Executivo antes do destino: por dano ou intimidacao (sirene ligada e colado nele). "
                         "Nao fique a mais de 128 m."},
    "Op03": {"title": "Op 03 Interceptacao Tatica", "kind": "INTERCEPTION", "op": "03", "suspect": "Interceptor", "speed": 90.0,
             "leash_m": 128.0, "weapon": "PISTOL", "magazine": 15, "reserve": 10, "reserve_coop": 20,
             "no_fire": 10.0, "evidence_at": 30.0, "boost": 1.5, "window": 70.0, "evidence_radius_m": 4.8,
             "medal_damage": 37.6, "medal_accuracy": 95.0,
             "briefing": "Siga o Cupe Esportivo sem atirar nos primeiros 10 s (pistola 9 mm). Ele vai jogar a evidencia pela "
                         "janela e fugir mais rapido: recupere-a em ate 70 s."},
    "Op04": {"title": "Op 04 Cacada de Elite", "kind": "ELITE", "layout": "Op04", "laps": 1,
             "time": 110.0, "medal": 85.0, "max_cones": 1, "no_collisions": True,
             "weapon": "SHOTGUN", "magazine": 7, "reserve": 5, "reserve_coop": 10,
             "targets_needed": 4, "target_up": 10.0,
             # T1..T5 rise as the car passes PC 08, 09, 11, 12, 13 (two checkpoints before each target)
             "rise": [7, 8, 10, 11, 12],
             "briefing": "Uma volta pelos 16 pontos com parada completa de 3 s na Parada Obrigatoria; acerte pelo menos 4 dos 5 "
                         "alvos com a escopeta (D-pad: arma e trava). Sem cones e sem batidas."},
}

assets = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()


def log(text):
    unreal.log("MISSIONS " + text)


def ue(x, y, z=0.0):
    return unreal.Vector(x * 100.0, -y * 100.0, z * 100.0)


def ue2(x, y):
    return unreal.Vector2D(x * 100.0, -y * 100.0)


def yaw_to(a, b):
    """Unreal yaw (degrees) from Bay point a to Bay point b."""
    return math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))


def at(x, y, z, yaw):
    return unreal.Transform(location=ue(x, y, z), rotation=unreal.Rotator(roll=0.0, pitch=0.0, yaw=yaw), scale=unreal.Vector(1, 1, 1))


def ahead(line, start, metres=12.0):
    """The first point of a line at least `metres` from start (to aim the start along it)."""
    for p in line:
        if math.hypot(p[0] - start[0], p[1] - start[1]) >= metres:
            return p
    return line[-1]


def course(mission, cfg, layout):
    markers = layout["markers"]
    start = next(m for m in markers if m["role"] == "start_player")
    checkpoints = [m for m in markers if m["role"] == "checkpoint"]
    end = next(m for m in markers if m["role"] == "end")
    first = checkpoints[0]
    mission.set_editor_property("layout", cfg["layout"])
    mission.set_editor_property("player_start", at(start["x"], start["y"], start["z"], yaw_to((start["x"], start["y"]), (first["x"], first["y"]))))
    mission.set_editor_property("checkpoints", [ue(c["x"], c["y"], c["z"]) for c in checkpoints])
    mission.set_editor_property("checkpoint_labels", [c["label"] for c in checkpoints])
    mission.set_editor_property("checkpoint_radius", checkpoints[0]["radius"] * 100.0)
    mission.set_editor_property("laps", cfg["laps"])
    mission.set_editor_property("finish", ue(end["x"], end["y"], end["z"]))
    mission.set_editor_property("finish_radius", end["radius"] * 100.0)
    mission.set_editor_property("time_limit", cfg["time"])
    mission.set_editor_property("medal_time", cfg["medal"])
    mission.set_editor_property("max_cones", cfg["max_cones"])
    mission.set_editor_property("no_collisions", cfg.get("no_collisions", False))
    stops = [i for i, c in enumerate(checkpoints) if "Parada" in c["label"]]
    mission.set_editor_property("stop_checkpoint", stops[0] if stops else -1)
    zones = [unreal.Vector4(z["x"] * 100.0, -z["y"] * 100.0, z["z"] * 100.0, z["radius"] * 100.0)
             for z in markers if z["role"] == "exit_fail" and not z.get("phased")]
    mission.set_editor_property("fail_zones", zones)
    mission.set_editor_property("player_route", [ue2(p[0], p[1]) for p in layout["line"]])
    if cfg.get("parked"):
        parked = next(m for m in markers if m["role"] == "start_suspect")
        mission.set_editor_property("has_parked_car", True)
        mission.set_editor_property("parked_car", at(parked["x"], parked["y"], parked["z"], yaw_to((start["x"], start["y"]), (first["x"], first["y"]))))
        mission.set_editor_property("parked_preset", cfg["parked"])
    targets = layout.get("targets") or []
    if targets:
        mission.set_editor_property("targets", [ue(t["x"], t["y"], t["z"]) for t in targets])
        mission.set_editor_property("target_rise_checkpoint", cfg["rise"][:len(targets)])
        mission.set_editor_property("targets_needed", cfg["targets_needed"])
        mission.set_editor_property("target_up_seconds", cfg["target_up"])
    log("%s: %d checkpoints x %d laps, stop at %s, %d fail zones, %d route points, %d targets"
        % (cfg["title"], len(checkpoints), cfg["laps"], stops[0] if stops else "-", len(zones), len(layout["line"]), len(targets)))


def street(mission, cfg, op):
    markers = op["markers"]
    start = next(m for m in markers if m["role"] == "start_player")
    suspect = next(m for m in markers if m["role"] == "start_suspect")
    target_line = op["routes"]["target"]["line"]
    player_line = op["routes"]["player"]["line"]
    s, p = (start["x"], start["y"]), (suspect["x"], suspect["y"])
    mission.set_editor_property("player_start", at(start["x"], start["y"], start["z"], yaw_to(s, ahead(player_line, s))))
    mission.set_editor_property("suspect_start", at(suspect["x"], suspect["y"], suspect["z"], yaw_to(p, ahead(target_line, p))))
    mission.set_editor_property("suspect_preset", cfg["suspect"])
    mission.set_editor_property("suspect_route", [ue2(q[0], q[1]) for q in target_line])
    mission.set_editor_property("suspect_speed_kmh", cfg["speed"])
    mission.set_editor_property("leash_cm", cfg["leash_m"] * 100.0)
    # the autopilot of the test chases along the suspect's own route (the player's route of Op02 is only its opening)
    route = target_line if cfg["kind"] == "CHASE" else player_line
    mission.set_editor_property("player_route", [ue2(q[0], q[1]) for q in route])
    mission.set_editor_property("medal_max_damage", cfg.get("medal_damage", 0.0))
    mission.set_editor_property("medal_accuracy", cfg.get("medal_accuracy", 0.0))
    if cfg["kind"] == "INTERCEPTION":
        mission.set_editor_property("no_fire_seconds", cfg["no_fire"])
        mission.set_editor_property("evidence_at", cfg["evidence_at"])
        mission.set_editor_property("evidence_boost", cfg["boost"])
        mission.set_editor_property("evidence_window", cfg["window"])
        mission.set_editor_property("evidence_radius", cfg["evidence_radius_m"] * 100.0)
    log("%s: start (%.0f, %.0f, %.1f), suspect %s at (%.0f, %.0f, %.1f), route %d points (%.0f m)" % (
        cfg["title"], start["x"], start["y"], start["z"], cfg["suspect"], suspect["x"], suspect["y"], suspect["z"],
        len(target_line), op["routes"]["target"].get("bay_m", 0)))


def main():
    cls_set = getattr(unreal, "WSPC2MissionSet", None)
    if cls_set is None:
        log("SKIPPED: the game module has no UWSPC2MissionSet yet (build it first)")
        return
    layouts = json.load(open(LAYOUTS, encoding="utf-8"))["layouts"]
    operations = json.load(open(OPERATIONS, encoding="utf-8"))["operations"]
    missions = []
    for mission_id, cfg in MISSIONS.items():
        mission = unreal.WSPC2MissionSpec()
        mission.set_editor_property("id", mission_id)
        mission.set_editor_property("title", cfg["title"])
        mission.set_editor_property("briefing", cfg["briefing"])
        mission.set_editor_property("kind", getattr(unreal.WSPC2MissionKind, cfg["kind"]))
        if cfg.get("weapon"):
            mission.set_editor_property("weapon", getattr(unreal.WSPC2Weapon, cfg["weapon"]))
            mission.set_editor_property("magazine", cfg["magazine"])
            mission.set_editor_property("reserve", cfg["reserve"])
            mission.set_editor_property("reserve_coop", cfg["reserve_coop"])
        if cfg.get("layout"):
            course(mission, cfg, layouts[cfg["layout"]])
        else:
            street(mission, cfg, operations[cfg["op"]])
        missions.append(mission)

    if not assets.does_directory_exist(FOLDER):
        assets.make_directory(FOLDER)
    if assets.does_asset_exist(ASSET):
        data = assets.load_asset(ASSET)
    else:
        factory = unreal.DataAssetFactory()
        factory.set_editor_property("data_asset_class", cls_set)
        data = tools.create_asset(ASSET.rsplit("/", 1)[1], FOLDER, cls_set, factory)
    data.set_editor_property("missions", missions)
    assets.save_loaded_asset(data)
    log("wrote %s: %s" % (ASSET, ", ".join(MISSIONS)))


main()
