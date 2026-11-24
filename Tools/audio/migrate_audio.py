"""Copies the City Sample sounds the vehicles use (engine loops, tyres, wind, crashes, siren, city air).

  python Tools/audio/migrate_audio.py [--copy]
Reuses the dependency-following copier of Tools/city/migrate_assets.py with its own seed list.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "city"))
import migrate_assets  # noqa: E402

A = "Audio\\"
migrate_assets.SEEDS = [
    A + r"Vehicles\Metasounds\Sedan\wav\sfx_Veh_Sedan_Engine_Idle_lp",
    A + r"Vehicles\Veh_Shared\wav\sfx_Veh_Shared_RPM_Pinned_Sedan_lp_01",
    # steady engine recordings (idle, low and high revs) per vehicle class from CitySample
    A + r"SoundWaves\NPC\Sedan\sfx_LeaveBehind_Veh_Npc_Sedan_Drive_Idle_lp_01",
    A + r"SoundWaves\NPC\Sedan\sfx_LeaveBehind_Veh_Npc_Sedan_Drive_Low_lp_01",
    A + r"SoundWaves\NPC\Sedan\sfx_LeaveBehind_Veh_Npc_Sedan_Drive_High_lp_01",
    A + r"SoundWaves\NPC\Sports\sfx_LeaveBehind_Veh_Npc_Sports_Drive_Idle_lp_01",
    A + r"SoundWaves\NPC\Sports\sfx_LeaveBehind_Veh_Npc_Sports_Drive_Low_lp_01",
    A + r"SoundWaves\NPC\Sports\sfx_LeaveBehind_Veh_Npc_Sports_Drive_High_lp_01",
    A + r"SoundWaves\NPC\SUV\sfx_LeaveBehind_Veh_Npc_SUV_Drive_Idle_lp_01",
    A + r"SoundWaves\NPC\SUV\sfx_LeaveBehind_Veh_Npc_SUV_Drive_High_lp_01",
    A + r"SoundWaves\NPC\Hatchback\sfx_LeaveBehind_Veh_Npc_Hatchback_Drive_Idle_lp_01",
    A + r"SoundWaves\NPC\Hatchback\sfx_LeaveBehind_Veh_Npc_Hatchback_Drive_Low_lp_01",
    A + r"SoundWaves\NPC\Hatchback\sfx_LeaveBehind_Veh_Npc_Hatchback_Drive_High_lp_01",
    A + r"SoundWaves\NPC\Minivan\sfx_LeaveBehind_Veh_Npc_Minivan_Drive_Idle_lp_01",
    A + r"SoundWaves\NPC\Minivan\sfx_LeaveBehind_Veh_Npc_Minivan_Drive_Low_01",
    A + r"SoundWaves\NPC\Minivan\sfx_LeaveBehind_Veh_Npc_Minivan_Drive_High_lp_01",
    A + r"SoundWaves\NPC\Semi\sfx_LeaveBehind_Veh_Npc_Semi_Drive_Idle_lp_01",
    A + r"SoundWaves\NPC\Semi\sfx_LeaveBehind_Veh_Npc_Semi_Drive_Low_lp_01",
    A + r"SoundWaves\NPC\Semi\sfx_LeaveBehind_Veh_Npc_Semi_Drive_High_lp_01",
    A + r"SoundWaves\NPC\Bus\sfx_LeaveBehind_Veh_Npc_Bus_Drive_Idle_lp_01",
    A + r"SoundWaves\NPC\Bus\sfx_LeaveBehind_Veh_Npc_Bus_Drive_Low_lp_01",
    A + r"SoundWaves\NPC\Bus\sfx_LeaveBehind_Veh_Npc_Bus_Drive_High_lp_01",
    A + r"SoundWaves\NPC\GarbageTruck\sfx_LeaveBehind_Veh_Npc_GarbageTruck_Drive_Idle_lp_01",
    A + r"SoundWaves\NPC\GarbageTruck\sfx_LeaveBehind_Veh_Npc_GarbageTruck_Drive_Low_lp_01",
    A + r"SoundWaves\NPC\GarbageTruck\sfx_LeaveBehind_Veh_Npc_GarbageTruck_Drive_High_lp_01",
    A + r"Vehicles\Metasounds\SUV\wav\sfx_Veh_SUV_Idle_lp_01",
    A + r"Vehicles\Metasounds\SUV\wav\sfx_Veh_SUV_Pinned_RPM_lp_01",
    A + r"Vehicles\Metasounds\SportsCar\wavs\sfx_veh_Sport_Engine_Idle_lp_01",
    A + r"Vehicles\Metasounds\SportsCar\wavs\sfx_Veh_Sport_RPM_Pinned_lp_01",
    A + r"Vehicles\Metasounds\SportsCar\wavs\sfx_Veh_Sport_Backfire_nl_01",
    A + r"Vehicles\Metasounds\SportsCar\wavs\sfx_Veh_Sport_Backfire_nl_02",
    A + r"Vehicles\Metasounds\SportsCar\wavs\sfx_Veh_Sport_Backfire_nl_03",
    A + r"Vehicles\Metasounds\SportsCar\wavs\sfx_Veh_Sport_Backfire_nl_04",
    A + r"Vehicles\Metasounds\SportsCar\wavs\sfx_Veh_Sport_Backfire_nl_05",
    A + r"Vehicles\Metasounds\SportsCar\wavs\sfx_Veh_Sport_Backfire_nl_06",
    A + r"Vehicles\Veh_Shared\wav\sfx_Veh_Shared_RoadNoiseAndWind_lp",
    A + r"Vehicles\Veh_Shared\wav\sfx_veh_Shared_Tire_Drifting_lp_01",
    A + r"Vehicles\Veh_Shared\wav\sfx_veh_Shared_Tire_Drift_Heavy_lp_01",
    A + r"SoundWaves\SFX\Vehicles\Destruction\Crash",
    A + r"SoundWaves\Ambient\Horns\VEH_SEDAN_Horn_A_001",
    A + r"SoundWaves\Ambient\Horns\VEH_SEDAN_Horn_A_002",
    A + r"SoundWaves\Ambient\Horns\VEH_SEDAN_Horn_A_003",
    A + r"SoundWaves\Ambient\Horns\VEH_SEDAN_Horn_A_004",
    A + r"SoundWaves\Ambient\Siren_Horn\Horns\sfx_LeaveBehind_amb_Swt_GarbageTruck_Horn_nl_01",
    A + r"SoundWaves\Ambient\Siren_Horn\Siren\sfx_LeaveBehind_amb_Swt_Siren_nl_01",
    A + r"SoundWaves\Ambient\Siren_Horn\Siren\sfx_LeaveBehind_amb_Swt_Siren_nl_02",
    A + r"SoundWaves\Ambient\Siren_Horn\Siren\sfx_LeaveBehind_amb_Swt_Siren_nl_03",
    A + r"SoundWaves\Ambient\VariousCity\VEH_SIREN_001",
    A + r"SoundWaves\Ambient\Air_Traffic\sfx_LeaveBehind_amb_Urban_Air_Mid_lp_01",
]

if __name__ == "__main__":
    migrate_assets.main()
