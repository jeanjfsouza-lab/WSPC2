"""Imports the vehicle audio into Unreal and builds its data assets (run inside the editor, as a commandlet).

1. Imports every WAV of Saved/Audio/Pipeline/output: the engine banks (loops looping, start/shutdown one-shots),
   the collision set and the mechanical set, all with PlayWhenSilent virtualisation so loops never restart.
2. Creates the mix assets in /Game/Audio/Vehicles/Mix: SA_VehicleEngine (natural 3D, 4-140 m, air absorption),
   SA_VehicleCollision (3-120 m), SC_VehicleCollisions (4 voices, stop quietest), SC_TrafficEngines
   (12 voices, stop farthest then oldest - the engine has no "farthest then quietest" rule) and the master bus
   SMX_WSPC2_Master with the peak limiter SFX_WSPC2_MasterLimiter (-3 dBFS, digital, 10 ms look-ahead) in its effect chain
   (Config/DefaultEngine.ini [/Script/Engine.AudioSettings] MasterSubmix points at it).
3. Creates one UWSPC2EngineSoundBank per archetype (/Game/Audio/Vehicles/Engines/<arch>/EB_<arch>), filled from
   EngineAudioBank.json with the loudness trims of validate_wavs.py, and one UWSPC2VehicleAudioProfile per
   audio_profile tag of Config/WSPC2Vehicles.json (/Game/Audio/Vehicles/Profiles/DA_Audio_<tag>) with its era
   character. No MetaSound is built: the engine grid and the one-shots run on native audio components.

  UnrealEditor-Cmd.exe WSPC2.uproject -run=pythonscript -script="D:/Github/WSPC2/Tools/audio/pipeline/ue_import_and_build_assets.py" -unattended -nosplash

Inputs:  Saved/Audio/Pipeline/output/** (WAVs, EngineAudioBank.json, CollisionAudioManifest.json,
         validation_report.json), Tools/audio/pipeline/engine_archetypes.json, Config/WSPC2Vehicles.json
Outputs: /Game/Audio/Vehicles/{Engines,Collisions,Mechanical,Mix,Profiles}/** and a summary in the log
"""
import json
import os
import re
import statistics

import unreal

ROOT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
OUT = os.path.join(ROOT, "Saved", "Audio", "Pipeline", "output")
ARCHETYPES = os.path.join(ROOT, "Tools", "audio", "pipeline", "engine_archetypes.json")
FLEET = os.path.join(ROOT, "Config", "WSPC2Vehicles.json")
BASE = "/Game/Audio/Vehicles"

ARCH_ENUM = {
    "arch_v8_efi_90s": "V8_EFI_90s", "arch_v8_classic_70s": "V8_Classic_70s", "arch_v8_muscle": "V8_Muscle",
    "arch_v6_american_90s": "V6_American_90s", "arch_v6_mid": "V6_Mid", "arch_i4_econ": "I4_Econ",
    "arch_boxer4_uel_turbo": "Boxer4_UEL_Turbo", "arch_i6_twinturbo": "I6_TwinTurbo",
    "arch_v12_exotic": "V12_Exotic", "arch_diesel_i4_truck": "Diesel_I4_Truck", "arch_diesel_heavy": "Diesel_Heavy",
}

# character of each audio_profile tag: forced induction, max boost and the era DSP (pitch, exhaust and cabin
# low-pass, backfire chance, gear whine, diesel knock, hard limiter, idle wander)
PROFILES = {
    "V8_Cruiser":        dict(fi="None", boost=0, dsp=(1.00, 9000, 1600, 0.00, 0.05, 0.0, False, 0.05)),
    "V8_Van":            dict(fi="None", boost=0, dsp=(0.97, 7000, 1400, 0.00, 0.08, 0.0, False, 0.05)),
    "V8_Classic":        dict(fi="None", boost=0, dsp=(0.98, 8000, 1500, 0.08, 0.05, 0.0, False, 0.25)),
    "V8_Muscle":         dict(fi="None", boost=0, dsp=(1.00, 18000, 2200, 0.35, 0.10, 0.0, False, 0.35)),
    "V6_Sedan":          dict(fi="None", boost=0, dsp=(1.00, 8500, 1600, 0.00, 0.05, 0.0, False, 0.05)),
    "V6_MidEngine":      dict(fi="None", boost=0, dsp=(1.00, 16000, 2400, 0.15, 0.10, 0.0, True, 0.05)),
    "I4_Compact":        dict(fi="None", boost=0, dsp=(1.00, 11000, 1800, 0.05, 0.08, 0.0, True, 0.05)),
    "I4_Turbo_Rally":    dict(fi="Turbo_BOV", boost=18, dsp=(1.00, 15000, 2200, 0.45, 0.25, 0.0, True, 0.10)),
    "I6_TwinTurbo":      dict(fi="Turbo_BOV", boost=14, dsp=(1.00, 14000, 2000, 0.15, 0.08, 0.0, True, 0.05)),
    "Flat6_Turbo":       dict(fi="Turbo_Flutter", boost=11, dsp=(0.96, 13000, 2000, 0.20, 0.10, 0.0, False, 0.10)),
    "V12_Exotic":        dict(fi="None", boost=0, dsp=(1.00, 19000, 2600, 0.25, 0.10, 0.0, True, 0.05)),
    "Flat12_Exotic":     dict(fi="None", boost=0, dsp=(0.97, 19000, 2600, 0.20, 0.10, 0.0, True, 0.05)),
    "I4_Diesel_Truck":   dict(fi="None", boost=0, dsp=(1.00, 6000, 1300, 0.00, 0.15, 0.6, False, 0.05)),
    "V8_Diesel_Armored": dict(fi="None", boost=0, dsp=(1.00, 6500, 1200, 0.00, 0.20, 0.5, False, 0.05)),
    "APC_V6_Diesel":     dict(fi="None", boost=0, dsp=(0.94, 6000, 1100, 0.00, 0.35, 0.55, False, 0.05)),
    "Tank_Turbine":      dict(fi="None", boost=0, dsp=(1.00, 20000, 1200, 0.00, 0.40, 0.0, False, 0.0)),
    "GolfCart_Electric": dict(fi="None", boost=0, dsp=(1.00, 20000, 2400, 0.00, 0.30, 0.0, False, 0.0)),
}

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
assets = unreal.EditorAssetLibrary


def log(text):
    unreal.log("AUDIOIMPORT " + text)


def enum_value(enum_cls, name):
    wanted = re.sub(r"[^a-z0-9]", "", name.lower())
    for member in dir(enum_cls):
        if member.startswith("_"):
            continue
        if re.sub(r"[^a-z0-9]", "", member.lower()) == wanted:
            return getattr(enum_cls, member)
    raise ValueError(f"{enum_cls.__name__} has no value {name}")


def set_norm(obj, cpp_name, value):
    """set_editor_property by the C++ name, whatever spelling the Python binding chose (dBAttenuationAtMax...)."""
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", cpp_name[1:] if re.match(r"^b[A-Z]", cpp_name) else cpp_name).lower()
    try:
        obj.set_editor_property(snake, value)  # some editable properties are settable but absent from dir()
        return
    except Exception:
        pass
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    wanted = {norm(cpp_name)}
    if re.match(r"^b[A-Z]", cpp_name):
        wanted.add(norm(cpp_name[1:]))  # the binding drops the b of bools: bAttenuate -> attenuate
    members = [m for m in dir(obj) if not m.startswith("_")]
    for member in members:
        if norm(member) in wanted:
            obj.set_editor_property(member, value)
            return
    close = [m for m in members if norm(cpp_name)[1:6] in norm(m)]
    raise AttributeError(f"{type(obj).__name__} has no property {cpp_name} (close: {close[:8]})")


def import_wavs(items):
    """items: (file, destination path, asset name, looping). Returns {asset name: SoundWave}."""
    tasks = []
    for file, path, name, _ in items:
        task = unreal.AssetImportTask()
        task.filename = file
        task.destination_path = path
        task.destination_name = name
        task.replace_existing = True
        task.automated = True
        task.save = False
        tasks.append(task)
    asset_tools.import_asset_tasks(tasks)
    loaded = {}
    play_when_silent = enum_value(unreal.VirtualizationMode, "PlayWhenSilent")
    adpcm = enum_value(unreal.SoundAssetCompressionType, "ADPCM")
    for file, path, name, looping in items:
        wave = assets.load_asset(f"{path}/{name}.{name}")
        if not wave:
            raise RuntimeError(f"import failed: {file}")
        wave.set_editor_property("looping", looping)
        wave.set_editor_property("virtualization_mode", play_when_silent)
        if looping:
            # the project's default codec does not wrap sample-accurately: a 0.9 s idle loop clicked at every repeat
            wave.set_sound_asset_compression_type(adpcm)
        loaded[name] = wave
    return loaded


def create_asset(name, path, cls, factory):
    full = f"{path}/{name}"
    if assets.does_asset_exist(full):
        return assets.load_asset(full)
    return asset_tools.create_asset(name, path, cls, factory)


def data_asset(name, path, cls):
    factory = unreal.DataAssetFactory()
    factory.set_editor_property("data_asset_class", cls)
    return create_asset(name, path, cls, factory)


def mix_assets():
    path = BASE + "/Mix"
    natural = enum_value(unreal.AttenuationDistanceModel, "NaturalSound")
    for name, inner, falloff, absorb in (("SA_VehicleEngine", 400.0, 13600.0, True), ("SA_VehicleCollision", 300.0, 11700.0, True)):
        att = create_asset(name, path, unreal.SoundAttenuation, unreal.SoundAttenuationFactory())
        s = att.get_editor_property("attenuation")
        set_norm(s, "bAttenuate", True)
        set_norm(s, "bSpatialize", True)
        set_norm(s, "DistanceAlgorithm", natural)
        set_norm(s, "AttenuationShapeExtents", unreal.Vector(inner, 0, 0))
        set_norm(s, "FalloffDistance", falloff)
        set_norm(s, "dBAttenuationAtMax", -50.0)
        set_norm(s, "bAttenuateWithLPF", absorb)
        set_norm(s, "LPFRadiusMin", inner * 4)
        set_norm(s, "LPFRadiusMax", inner + falloff)
        set_norm(s, "LPFFrequencyAtMin", 20000.0)
        set_norm(s, "LPFFrequencyAtMax", 4500.0)
        att.set_editor_property("attenuation", s)
    for name, count, rule in (("SC_VehicleCollisions", 4, "StopQuietest"), ("SC_TrafficEngines", 12, "StopFarthestThenOldest")):
        con = create_asset(name, path, unreal.SoundConcurrency, unreal.SoundConcurrencyFactory())
        s = con.get_editor_property("concurrency")
        set_norm(s, "MaxCount", count)
        set_norm(s, "ResolutionRule", enum_value(unreal.MaxConcurrentResolutionRule, rule))
        con.set_editor_property("concurrency", s)

    # master bus: a submix with a peak limiter in its own effect chain, set as MasterSubmix in DefaultEngine.ini.
    # (An effect added at runtime with AddMasterSubmixEffect never reached the recorded output; a submix
    # rebuilds its chain from the asset, so the limiter has to live in the asset.)
    factory = unreal.SoundSubmixEffectFactory()
    set_norm(factory, "SoundEffectSubmixPresetClass", unreal.SubmixEffectDynamicsProcessorPreset)
    limiter = create_asset("SFX_WSPC2_MasterLimiter", path, unreal.SubmixEffectDynamicsProcessorPreset, factory)
    s = limiter.get_editor_property("settings")
    set_norm(s, "DynamicsProcessorType", enum_value(unreal.SubmixEffectDynamicsProcessorType, "Limiter"))
    set_norm(s, "PeakMode", enum_value(unreal.SubmixEffectDynamicsPeakMode, "Peak"))
    set_norm(s, "LinkMode", enum_value(unreal.SubmixEffectDynamicsChannelLinkMode, "Peak"))
    # UE's limiter is not a brick wall: crash transients overshoot the ceiling by up to ~4 dB even with the
    # digital envelope (the default analog one let them through by ~6 dB), so the ceiling sits at -3 dBFS
    set_norm(s, "ThresholdDb", -3.0)
    set_norm(s, "KneeBandwidthDb", 0.0)
    set_norm(s, "bAnalogMode", False)
    set_norm(s, "LookAheadMsec", 10.0)
    set_norm(s, "AttackTimeMsec", 1.0)
    set_norm(s, "ReleaseTimeMsec", 120.0)
    set_norm(s, "InputGainDb", 0.0)
    set_norm(s, "OutputGainDb", 0.0)
    limiter.set_editor_property("settings", s)
    master = create_asset("SMX_WSPC2_Master", path, unreal.SoundSubmix, unreal.SoundSubmixFactory())
    master.set_editor_property("submix_effect_chain", [limiter])
    log("mix assets ready (master submix with limiter at -3 dBFS)")


def engine_banks(trims):
    archetypes = json.load(open(ARCHETYPES, encoding="utf-8"))["archetypes"]
    banks = {}
    for arch in archetypes:
        arch_id = arch["id"]
        bank_dir = os.path.join(OUT, "engines", arch_id)
        meta = json.load(open(os.path.join(bank_dir, "EngineAudioBank.json"), encoding="utf-8"))
        path = f"{BASE}/Engines/{arch_id}"
        items = []
        for state in meta["states"]:
            name = f"{arch_id}_r{int(round(state['rpm'])):05d}_l{int(round(state['load'] * 100)):03d}"
            items.append((os.path.join(bank_dir, state["clip"]), path, name, True))
        items.append((os.path.join(bank_dir, meta["startClip"]), path, f"{arch_id}_Start", False))
        items.append((os.path.join(bank_dir, meta["shutdownClip"]), path, f"{arch_id}_Shutdown", False))
        waves = import_wavs(items)

        rpms = sorted({s["rpm"] for s in meta["states"]})
        loads = sorted({s["load"] for s in meta["states"]})
        by_key = {(s["rpm"], s["load"]): s for s in meta["states"]}
        grid = []
        for rpm in rpms:
            for load in loads:
                state = by_key[(rpm, load)]
                point = unreal.WSPC2EngineSamplePoint()
                point.set_editor_property("measured_rpm", float(state["measuredRpm"]))
                point.set_editor_property("load", float(load))
                point.set_editor_property("normalization_gain", 1.0)
                name = f"{arch_id}_r{int(round(rpm)):05d}_l{int(round(load * 100)):03d}"
                point.set_editor_property("wave_asset", waves[name])
                grid.append(point)

        bank = data_asset(f"EB_{arch_id}", path, unreal.WSPC2EngineSoundBank)
        bank.set_editor_property("archetype_id", arch_id)
        bank.set_editor_property("archetype", enum_value(unreal.WSPC2EngineArchetype, ARCH_ENUM[arch_id]))
        bank.set_editor_property("display_name", arch["displayName"])
        bank.set_editor_property("idle_rpm", float(meta["idleRpm"]))
        bank.set_editor_property("loudness_trim_db", float(trims.get(arch_id, 0.0)))
        bank.set_editor_property("rpms", [float(by_key[(r, loads[0])]["measuredRpm"]) for r in rpms])
        bank.set_editor_property("loads", [float(x) for x in loads])
        bank.set_editor_property("grid", grid)
        bank.set_editor_property("start_sound", waves[f"{arch_id}_Start"])
        bank.set_editor_property("shutdown_sound", waves[f"{arch_id}_Shutdown"])
        banks[arch_id] = bank
        log(f"bank {arch_id}: {len(rpms)} rpm x {len(loads)} loads, trim {trims.get(arch_id, 0.0):+.2f} dB")
    return banks, archetypes


def effects():
    manifest = json.load(open(os.path.join(OUT, "CollisionAudioManifest.json"), encoding="utf-8"))
    folders = {"impact": "Collisions/Impacts", "crunch": "Collisions/Crunch", "glass": "Collisions/Glass", "scrape": "Collisions/Scrape"}
    items = []
    for entry in manifest["files"]:
        group = entry["category"].split("_")[0]
        folder = folders.get(group, "Mechanical")
        items.append((os.path.join(OUT, entry["file"]), f"{BASE}/{folder}", entry["name"], bool(entry["loop"])))
    import_wavs(items)
    log(f"effects: {len(items)} sounds")
    return len(items)


def profiles(banks, archetypes):
    fleet = json.load(open(FLEET, encoding="utf-8"))
    fleet = fleet["vehicles"] if isinstance(fleet, dict) and "vehicles" in fleet else fleet
    groups = {}
    for entry in fleet:
        specs = entry["real_specs"]
        groups.setdefault(specs["audio_profile"], []).append(specs)
    tag_to_arch = {tag: a["id"] for a in archetypes for tag in a["audioProfiles"]}
    synthetic = {"Tank_Turbine": "SyntheticTurbine", "GolfCart_Electric": "SyntheticElectric"}
    path = BASE + "/Profiles"
    made = 0
    for tag, specs in sorted(groups.items()):
        cfg = PROFILES[tag]
        years = [int(m.group(0)) for s in specs for m in [re.search(r"(19|20)\d\d", s.get("real_world_counterpart", ""))] if m]
        year = int(statistics.median(years)) if years else 1990
        era = "Era_1970s" if year < 1980 else "Era_1980s" if year < 1990 else "Era_1990s" if year < 2000 else "Era_2000s"

        profile = data_asset(f"DA_Audio_{tag}", path, unreal.WSPC2VehicleAudioProfile)
        profile.set_editor_property("audio_profile_tag", tag)
        arch_id = tag_to_arch.get(tag)
        profile.set_editor_property("archetype", enum_value(unreal.WSPC2EngineArchetype, ARCH_ENUM[arch_id] if arch_id else synthetic[tag]))
        profile.set_editor_property("vehicle_display_name", unreal.Text(tag.replace("_", " ")))
        if arch_id:
            profile.set_editor_property("engine_bank", banks[arch_id])
        profile.set_editor_property("era", enum_value(unreal.WSPC2VehicleEra, era))
        profile.set_editor_property("forced_induction", enum_value(unreal.WSPC2ForcedInduction, cfg["fi"]))
        profile.set_editor_property("idle_rpm", float(statistics.median(s["idle_rpm"] for s in specs)))
        profile.set_editor_property("redline_rpm", float(statistics.median(s["max_rpm"] for s in specs)))
        profile.set_editor_property("max_boost_psi", float(cfg["boost"]))
        profile.set_editor_property("gain_db", 0.0)
        pitch, exhaust, cabin, backfire, whine, diesel, limiter, wander = cfg["dsp"]
        dsp = unreal.WSPC2EraDSPConfig()
        dsp.set_editor_property("pitch_multiplier", pitch)
        dsp.set_editor_property("exhaust_low_pass_hz", float(exhaust))
        dsp.set_editor_property("cabin_low_pass_hz", float(cabin))
        dsp.set_editor_property("backfire_chance", backfire)
        dsp.set_editor_property("gear_whine_gain", whine)
        dsp.set_editor_property("diesel_clatter_gain", diesel)
        dsp.set_editor_property("hard_rev_limiter", limiter)
        dsp.set_editor_property("idle_instability_amount", wander)
        profile.set_editor_property("era_dsp", dsp)
        made += 1
        log(f"profile {tag}: {arch_id or synthetic[tag]}, {era}, FI {cfg['fi']}")
    return made


def main():
    report = json.load(open(os.path.join(OUT, "validation_report.json"), encoding="utf-8"))
    if report["failures"]:
        raise RuntimeError(f"validate_wavs.py reported failures: {report['failures'][:3]}")
    mix_assets()
    banks, archetypes = engine_banks(report["engineTrimsDb"])
    count = effects()
    made = profiles(banks, archetypes)
    saved = 0
    for folder in ("Engines", "Collisions", "Mechanical", "Mix", "Profiles"):
        if assets.save_directory(f"{BASE}/{folder}", only_if_is_dirty=True, recursive=True):
            saved += 1
    log(f"done: {len(banks)} banks, {count} effects, {made} profiles, {saved}/5 folders saved")


main()
