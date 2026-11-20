"""Prepares, repairs, optimizes, and normalizes all selected vehicle & wreck assets from
ASSETS TO USE/00_Originais into game-ready GLBs under ASSETS TO USE/01_Preparados/.

Improvements applied automatically per vehicle:
  - Extracts .zip / nested .rar archives cleanly into temp workspace
  - Strips floor/shadow planes (keeps vehicle emblems/logos intact)
  - Splits multi-vehicle packages (Generic Civil Service x10, Lincoln Mark V x2, Burned Cars x2, Burned Police x2)
  - Unrotates diagonal packs (PCA XY minimum bounding box), enforces Blender +X Front / +Y Left / +Z Up
    so UE5 Interchange imports directly as +X Forward / +Y Right / +Z Up without rotation offsets
  - Normalizes real-world scale in metres (fixing mm Beetle, oversized Suburban/CVPI prop, etc.) and grounds at Z = 0
  - Relinks and wires external PBR textures (Albedo, Normal, Roughness, Metallic, Opacity, ARM) + transparent glass
  - Clamps oversized textures (<= 2048 px Playable, <= 1024 px Traffic) and packs inside GLB
  - Separates 4 corner wheels cleanly for Playable / Hero Police cars (<Body>.glb + <Wheel>.glb + layout.json)
    and decimates bloated >300k-tri meshes into target Playable (<= 165k) or Traffic (<= 34k) budgets
  - Stretches a car into a limousine when the recipe has "stretch" (Target_Limousine78 from the silver Lincoln)

Commands:
  blender -b --factory-startup --python Tools/vehicles/prepare_vehicles.py -- --group police
  blender -b --factory-startup --python Tools/vehicles/prepare_vehicles.py -- --only Hero_Suburban89 Hero_BMWE39

Inputs:
  ASSETS TO USE/00_Originais/*

Outputs:
  ASSETS TO USE/01_Preparados/{01_Police,02_Playable,03_Traffic,04_Props_Wrecks,05_Rail}/<Name>/*
  ASSETS TO USE/01_Preparados/manifest.json
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORIG_DIR = PROJECT_ROOT / "ASSETS TO USE" / "00_Originais"
OUT_DIR = PROJECT_ROOT / "ASSETS TO USE" / "01_Preparados"
SEVEN_ZIP = r"C:\Program Files\7-Zip\7z.exe"

WHEEL_KW = ("wheel", "tire", "tyre", "llanta", "rim", "hub", "brake", "caliper", "rotor", "disc")
WHEEL_MAT_KW = ("tire", "tyre", "llanta", "rb1c_tire", "h2tire", "h2protector", "wheelsdually", "wheel_16", "wire_008061138", "wheel", "rim", "rotor", "hub", "sidewall", "tread", "alloy")
BADGE_OBJ_KW = ("logo_plane", "badge", "emblem", "emblema", "ford_badges", "honeycombgrille_badge")
BADGE_MAT_KW = ("crownvic_ford_badges", "crownvic_honeycombgrille_badge", "logo_plane", "emblem", "badge")
FLOOR_OBJ_KW = ("floor", "ground", "shadow", "plinth")
FLOOR_MAT_KW = ("m_ground", "internal_ground_ao", "gt_shadow", "floor")
GLASS_KW = ("glass", "window", "windshield", "windscreen", "vidro", "vitre", "transperent", "transparent", "clearglass", "windowglass", "glass_tex", "citybus_glass")
NO_GLASS_KW = ("headlight", "taillight", "brake", "blinker", "lamp", "reflector", "badge", "plate", "mirror", "black_glass", "trim")

# Specs: id -> configuration
RECIPES = [
    # --- 01_Police ---
    {
        "id": "Police_CVPI01_Patrol",
        "category": "01_Police",
        "source": "01_Police/2001_crown_victoria_police_interceptor_game_prop.glb",
        "role": "traffic",
        "target_length_m": 5.38,
        "target_tris": 34000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "flip_x": True,
        "tint_glass": 0.65,
        "license": "CC-BY-4.0 (2001 CVPI Patrol IA / Prop)",
    },
    {
        "id": "Police_Caprice94_Hero",
        "category": "01_Police",
        "source": "01_Police/chevrolet_caprice_police_car_-94_free_asset.glb",
        "role": "playable",
        "target_length_m": 5.44,
        "target_tris": 170000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": True,
        "tint_glass": 0.24,
        "license": "CC-BY-ND-4.0 (LOCAL PROTOTYPE ONLY - NoDerivatives prevents redistributing modified asset)",
    },
    {
        "id": "Police_Caprice94_Traffic",
        "category": "01_Police",
        "source": "01_Police/chevrolet_caprice_police_car_-94_free_asset.glb",
        "role": "traffic",
        "target_length_m": 5.44,
        "target_tris": 32000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "flip_x": True,
        "tint_glass": 0.48,
        "license": "CC-BY-ND-4.0 (LOCAL PROTOTYPE ONLY - NoDerivatives)",
    },
    {
        "id": "Police_Harley_FLHTP",
        "category": "01_Police",
        "source": "01_Police/harley-davidson_flhtp-electra_glide_police_h.p..glb",
        "role": "playable",
        "target_length_m": 2.45,
        "target_tris": 70000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "flip_x": False,
        "license": "CC-BY-4.0 (Highway Patrol Motorcycle)",
    },
    {
        "id": "Police_Civil_Sedan",
        "category": "01_Police",
        "source": "01_Police/generic-civil-service-vehicles-pack.zip",
        "sub_object": "police_sedan",
        "pbr_prefix": "police",
        "role": "traffic",
        "target_length_m": 5.15,
        "target_tris": 12000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "pca_unrotate": True,
        "tint_glass": 0.35,
        "license": "Generic Civil Service Pack (US Police Sedan)",
    },
    {
        "id": "Traffic_Civil_PostalVan",
        "category": "03_Traffic",
        "source": "01_Police/generic-civil-service-vehicles-pack.zip",
        "sub_object": "postvan",
        "pbr_prefix": "postvan",
        "role": "traffic",
        "target_length_m": 5.45,
        "target_tris": 12000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "pca_unrotate": True,
        "tint_glass": 0.38,
        "license": "Generic Civil Service Pack (Postal Service Van)",
    },
    {
        "id": "Police_Civil_Ambulance",
        "category": "01_Police",
        "source": "01_Police/generic-civil-service-vehicles-pack.zip",
        "sub_object": "ambulance",
        "pbr_prefix": "ambulance",
        "role": "traffic",
        "target_length_m": 6.80,
        "target_tris": 12000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "pca_unrotate": True,
        "tint_glass": 0.35,
        "license": "Generic Civil Service Pack (Emergency Ambulance)",
    },
    {
        "id": "Police_Civil_FireTruck",
        "category": "01_Police",
        "source": "01_Police/generic-civil-service-vehicles-pack.zip",
        "sub_object": "fire_truck",
        "pbr_prefix": "firetruck",
        "role": "traffic",
        "target_length_m": 8.90,
        "target_tris": 15000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "pca_unrotate": True,
        "tint_glass": 0.35,
        "license": "Generic Civil Service Pack (Fire Truck)",
    },
    {
        "id": "Police_Murphy97_Retro",
        "category": "01_Police",
        "source": "01_Police/murphy_97_cruiser_-_low_poly_model.glb",
        "role": "traffic",
        "target_length_m": 5.20,
        "target_tris": 22000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": False,
        "license": "CC-BY-4.0 (Zhabotinsky Low-Poly 97 Caprice)",
    },
    {
        "id": "Police_Thunderbolt96_Retro",
        "category": "01_Police",
        "source": "01_Police/thunderbolt_96_interceptor_-_low_poly_model.glb",
        "role": "traffic",
        "target_length_m": 4.95,
        "target_tris": 22000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": False,
        "license": "CC-BY-4.0 (Zhabotinsky Low-Poly 96 Interceptor)",
    },
    {
        "id": "Police_Fairheaven80_Retro",
        "category": "01_Police",
        "source": "01_Police/fairheaven_lt_80_cop_cruiser_-_low_poly_model.glb",
        "role": "traffic",
        "target_length_m": 5.30,
        "target_tris": 22000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": False,
        "license": "CC-BY-4.0 (Zhabotinsky Low-Poly 80 LTD Cop)",
    },
    {
        "id": "Police_Negotiator80_Retro",
        "category": "01_Police",
        "source": "01_Police/negotiator_80_cop_cruiser_-_low_poly_model.glb",
        "role": "traffic",
        "target_length_m": 5.20,
        "target_tris": 22000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": False,
        "license": "CC-BY-4.0 (Zhabotinsky Low-Poly 80 Diplomat Cop)",
    },

    # --- 02_Playable ---
    {
        "id": "Hero_CrownVic_Undercover",
        "category": "02_Playable",
        "source": "02_Playable_Hero/ford_crown_victoria_lx_2011.glb",
        "role": "playable",
        "target_length_m": 5.38,
        "target_tris": 170000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": True,
        "tint_glass": 0.22,
        "license": "CC-BY-4.0 (+X Forward aligned Panther 98-11 / Undercover)",
    },
    {
        "id": "Hero_Suburban89",
        "category": "02_Playable",
        "source": "02_Playable_Hero/1989-chevrolet-suburban.zip",
        "role": "playable",
        "target_length_m": 5.56,
        "target_tris": 140000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": False,
        "tint_glass": 0.25,
        "license": "Check Sketchfab attribution (1989 Suburban SWAT/Federal/Civil)",
    },
    {
        "id": "Hero_BMWE39",
        "category": "02_Playable",
        "source": "02_Playable_Hero/bmw-e39-free.zip",
        "prefer_blend": True,
        "role": "playable",
        "target_length_m": 4.78,
        "target_tris": 175000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": False,
        "tint_glass": 0.24,
        "license": "Free 3D model (BMW E39 1998-2003)",
    },
    {
        "id": "Hero_BMWE46_Touring01",
        "category": "02_Playable",
        "source": "02_Playable_Hero/bmw_3_series_touring_e46_2001.glb",
        "role": "playable",
        "target_length_m": 4.48,
        "target_tris": 145000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": True,
        "tint_glass": 0.24,
        "license": "CC-BY-4.0 (2001 BMW E46 Touring)",
    },
    {
        "id": "Hero_BMW_E30_Free",
        "category": "02_Playable",
        "source": "02_Playable_Hero/free_bmw_m3_e30.glb",
        "role": "playable",
        "target_length_m": 4.35,
        "target_tris": 125000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": True,
        "tint_glass": 0.22,
        "license": "CC-BY-4.0 (Martin Trafas E30)",
    },
    {
        "id": "Hero_BMW_E34_95",
        "category": "02_Playable",
        "source": "02_Playable_Hero/1995-bmw-m5-e34.zip",
        "role": "playable",
        "target_length_m": 4.72,
        "target_tris": 175000,
        "max_tex_px": 2048,
        "split_wheels": True,
        "flip_x": False,
        "tint_glass": 0.22,
        "license": "WARNING: Possible Forza game-rip (lod0/cockpit) - prototype only",
    },
    {
        "id": "Hero_BMW_E36_97",
        "category": "02_Playable",
        "source": "02_Playable_Hero/1997-bmw-m3-e36.zip",
        "role": "playable",
        "target_length_m": 4.43,
        "target_tris": 175000,
        "max_tex_px": 2048,
        "split_wheels": True,
        "flip_x": False,
        "tint_glass": 0.22,
        "license": "WARNING: Possible Forza game-rip (lod0/cockpit) - prototype only",
    },
    {
        "id": "Hero_BMW_850CSi_95",
        "category": "02_Playable",
        "source": "02_Playable_Hero/1995-bmw-850csi.zip",
        "role": "playable",
        "target_length_m": 4.78,
        "target_tris": 175000,
        "max_tex_px": 2048,
        "split_wheels": True,
        "flip_x": False,
        "tint_glass": 0.22,
        "license": "WARNING: Possible Forza game-rip (lod0/cockpit) - prototype only",
    },
    {
        "id": "Hero_BMW_M635CSi_86",
        "category": "02_Playable",
        "source": "02_Playable_Hero/1986-bmw-m635csi.zip",
        "role": "playable",
        "target_length_m": 4.75,
        "target_tris": 180000,
        "max_tex_px": 2048,
        "split_wheels": True,
        "flip_x": False,
        "tint_glass": 0.22,
        "license": "WARNING: Possible Forza game-rip (lod0/cockpit) - prototype only",
    },
    {
        "id": "Hero_BMW_M1_81",
        "category": "02_Playable",
        "source": "02_Playable_Hero/1981-bmw-m1.zip",
        "role": "playable",
        "target_length_m": 4.36,
        "target_tris": 175000,
        "max_tex_px": 2048,
        "split_wheels": True,
        "flip_x": False,
        "tint_glass": 0.22,
        "license": "WARNING: Possible Forza game-rip (lod0/cockpit) - prototype only",
    },
    {
        "id": "Hero_Supra_94",
        "category": "02_Playable",
        "source": "02_Playable_Hero/toyota_supra_mk_iv_1994.glb",
        "role": "playable",
        "target_length_m": 4.52,
        "target_tris": 155000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": True,
        "tint_glass": 0.22,
        "license": "CC-BY-4.0 (Martin Trafas 94 Supra)",
    },
    {
        "id": "Hero_Porsche_930_75",
        "category": "02_Playable",
        "source": "02_Playable_Hero/free_1975_porsche_911_930_turbo.glb",
        "role": "playable",
        "target_length_m": 4.29,
        "target_tris": 150000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": True,
        "tint_glass": 0.22,
        "license": "CC-BY-4.0 (Lionsharp Studios 930 Turbo)",
    },
    {
        "id": "Hero_Ferrari_F40",
        "category": "02_Playable",
        "source": "02_Playable_Hero/ferrari-f40.zip",
        "role": "playable",
        "target_length_m": 4.36,
        "target_tris": 160000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": True,
        "tint_glass": 0.22,
        "license": "Check author license (Bonus Classic Supercar)",
    },
    {
        "id": "Hero_AE86_Kouki",
        "category": "02_Playable",
        "source": "02_Playable_Hero/toyota-ae86-black-limited-kouki.zip",
        "role": "playable",
        "target_length_m": 4.20,
        "target_tris": 150000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": False,
        "tint_glass": 0.22,
        "license": "Check author license (Bonus Classic AE86)",
    },
    {
        "id": "Hero_FordLTD_Wagon",
        "category": "02_Playable",
        "source": "02_Playable_Hero/ford-ltd-wagon.zip",
        "role": "playable",
        "target_length_m": 5.46,
        "target_tris": 145000,
        "max_tex_px": 2048,
        "split_wheels": True,
        "flip_x": True,
        "tint_glass": 0.25,
        "license": "Check author license (Classic US Station Wagon)",
    },
    {
        "id": "Hero_Beetle_68",
        "category": "02_Playable",
        "source": "02_Playable_Hero/1968-volkswagen-beetle.zip",
        "role": "playable",
        "target_length_m": 4.08,
        "target_tris": 90000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": True,
        "tint_glass": 0.22,
        "license": "Check author license (Bonus Classic 68 Beetle)",
    },
    {
        "id": "Hero_Datsun240K_72",
        "category": "02_Playable",
        "source": "02_Playable_Hero/free_1972_datsun_240k_gt.glb",
        "role": "playable",
        "target_length_m": 4.62,
        "target_tris": 150000,
        "max_tex_px": 2048,
        "split_wheels": True,
        "flip_x": True,
        "tint_glass": 0.22,
        "license": "CC-BY-SA-4.0 (Karol Miklas - ShareAlike applies)",
    },
    {
        "id": "Hero_Alfa155_92",
        "category": "02_Playable",
        "source": "02_Playable_Hero/1992_alfa_romeo_155_q4.glb",
        "role": "playable",
        "target_length_m": 4.44,
        "target_tris": 145000,
        "max_tex_px": 2048,
        "split_wheels": True,
        "flip_x": True,
        "tint_glass": 0.22,
        "license": "CC-BY-NC-SA-4.0 (NON-COMMERCIAL ONLY)",
    },
    {
        "id": "Hero_HondaNR750_94",
        "category": "02_Playable",
        "source": "02_Playable_Hero/honda-nr750-1994.zip",
        "role": "playable",
        "target_length_m": 2.08,
        "target_tris": 55000,
        "max_tex_px": 2048,
        "split_wheels": False,
        "flip_x": True,
        "license": "Check author license (94 Sportbike Bonus)",
    },

    # --- 03_Traffic (optimized <= 35k single-mesh traffic & LOD variants) ---
    {
        "id": "Traffic_Civil_Taxi",
        "category": "03_Traffic",
        "source": "01_Police/generic-civil-service-vehicles-pack.zip",
        "sub_object": "taxi",
        "pbr_prefix": "taxi",
        "role": "traffic",
        "target_length_m": 5.15,
        "target_tris": 10000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "pca_unrotate": True,
        "tint_glass": 0.35,
        "license": "Generic Civil Service Pack (Yellow Cab)",
    },
    {
        "id": "Traffic_Civil_CityBus",
        "category": "03_Traffic",
        "source": "01_Police/generic-civil-service-vehicles-pack.zip",
        "sub_object": "citybus",
        "pbr_prefix": "citybus",
        "role": "traffic",
        "target_length_m": 11.50,
        "target_tris": 12000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "pca_unrotate": True,
        "tint_glass": 0.35,
        "license": "Generic Civil Service Pack (City Transit Bus)",
    },
    {
        "id": "Traffic_Civil_SchoolBus",
        "category": "03_Traffic",
        "source": "01_Police/generic-civil-service-vehicles-pack.zip",
        "sub_object": "school_bus",
        "pbr_prefix": "schoolbus",
        "role": "traffic",
        "target_length_m": 10.50,
        "target_tris": 14000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "pca_unrotate": True,
        "tint_glass": 0.35,
        "license": "Generic Civil Service Pack (US School Bus)",
    },
    {
        "id": "Traffic_Civil_GarbageTruck",
        "category": "03_Traffic",
        "source": "01_Police/generic-civil-service-vehicles-pack.zip",
        "sub_object": "garbage_truck",
        "pbr_prefix": "garbagetruck",
        "role": "traffic",
        "target_length_m": 8.40,
        "target_tris": 15000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "pca_unrotate": True,
        "tint_glass": 0.35,
        "license": "Generic Civil Service Pack (Garbage Truck)",
    },
    {
        "id": "Traffic_Civil_ServiceTruck",
        "category": "03_Traffic",
        "source": "01_Police/generic-civil-service-vehicles-pack.zip",
        "sub_object": "rdservtruck",
        "pbr_prefix": "servicetruck",
        "role": "traffic",
        "target_length_m": 6.00,
        "target_tris": 12000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "pca_unrotate": True,
        "tint_glass": 0.35,
        "license": "Generic Civil Service Pack (Road Utility Truck)",
    },
    {
        "id": "Traffic_Civil_TowTruck",
        "category": "03_Traffic",
        "source": "01_Police/generic-civil-service-vehicles-pack.zip",
        "sub_object": "towtruck",
        "pbr_prefix": "towtruck",
        "role": "traffic",
        "target_length_m": 7.60,
        "target_tris": 12000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "pca_unrotate": True,
        "tint_glass": 0.35,
        "license": "Generic Civil Service Pack (Flatbed Tow Truck)",
    },
    {
        "id": "Traffic_CrownVic01",
        "category": "03_Traffic",
        "source": "02_Playable_Hero/ford_crown_victoria_lx_2011.glb",
        "role": "traffic",
        "target_length_m": 5.38,
        "target_tris": 32000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "flip_x": True,
        "tint_glass": 0.55,
        "license": "CC-BY-4.0 (Optimized Traffic LOD)",
    },
    {
        "id": "Traffic_Suburban89",
        "category": "03_Traffic",
        "source": "02_Playable_Hero/1989-chevrolet-suburban.zip",
        "role": "traffic",
        "target_length_m": 5.56,
        "target_tris": 32000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "flip_x": False,
        "tint_glass": 0.50,
        "license": "Optimized Traffic LOD (89 Suburban)",
    },
    {
        "id": "Traffic_BMWE39",
        "category": "03_Traffic",
        "source": "02_Playable_Hero/bmw-e39-free.zip",
        "prefer_blend": True,
        "role": "traffic",
        "target_length_m": 4.78,
        "target_tris": 32000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "flip_x": False,
        "tint_glass": 0.55,
        "license": "Optimized Traffic LOD (BMW E39)",
    },
    {
        "id": "Traffic_BMWE46_Wagon",
        "category": "03_Traffic",
        "source": "02_Playable_Hero/bmw_3_series_touring_e46_2001.glb",
        "role": "traffic",
        "target_length_m": 4.48,
        "target_tris": 48000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "flip_x": True,
        "tint_glass": 0.55,
        "license": "CC-BY-4.0 (Optimized Traffic LOD)",
    },
    {
        "id": "Traffic_FordLTD_Wagon",
        "category": "03_Traffic",
        "source": "02_Playable_Hero/ford-ltd-wagon.zip",
        "role": "traffic",
        "target_length_m": 5.46,
        "target_tris": 145000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "flip_x": True,
        "tint_glass": 0.55,
        "license": "Optimized Traffic LOD (LTD Wagon - clean CAD threshold 145k)",
    },
    {
        "id": "Traffic_Illinois90",
        "category": "03_Traffic",
        "source": "03_Traffic/illinois_90_-_low_poly_model.glb",
        "role": "traffic",
        "target_length_m": 5.15,
        "target_tris": 22000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": False,
        "license": "CC-BY-4.0 (Zhabotinsky 90 Sedan)",
    },
    {
        "id": "Traffic_Wagon84",
        "category": "03_Traffic",
        "source": "03_Traffic/fairheaven-sw-84-low-poly-model.zip",
        "role": "traffic",
        "target_length_m": 5.05,
        "target_tris": 22000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": False,
        "license": "CC-BY-4.0 (Zhabotinsky 84 Station Wagon)",
    },
    {
        "id": "Traffic_Kiri86",
        "category": "03_Traffic",
        "source": "03_Traffic/kiri-86-low-poly-model.zip",
        "role": "traffic",
        "target_length_m": 4.35,
        "target_tris": 22000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": False,
        "license": "CC-BY-4.0 (Zhabotinsky 86 Compact)",
    },
    {
        "id": "Traffic_LCT3000_95",
        "category": "03_Traffic",
        "source": "03_Traffic/lct-3000-95-low-poly-model.zip",
        "role": "traffic",
        "target_length_m": 6.05,
        "target_tris": 22000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": False,
        "license": "CC-BY-4.0 (Zhabotinsky 95 Box Truck)",
    },
    {
        "id": "Traffic_Phoenix71",
        "category": "03_Traffic",
        "source": "03_Traffic/phoenix_455_71_-_low_poly_model.glb",
        "role": "traffic",
        "target_length_m": 4.89,
        "target_tris": 28000,
        "max_tex_px": 1024,
        "split_wheels": True,
        "flip_x": False,
        "license": "CC-BY-4.0 (Zhabotinsky 71 Muscle)",
    },
    {
        "id": "Traffic_GMC_Motorhome",
        "category": "03_Traffic",
        "source": "03_Traffic/free_gmc_motorhome_reimagined_low_poly.glb",
        "role": "traffic",
        "target_length_m": 7.92,
        "target_tris": 32000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "flip_x": True,
        "tint_glass": 0.30,
        "license": "CC-BY-4.0 (Karol Miklas GMC Motorhome)",
    },
    {
        "id": "Traffic_Cutlass71",
        "category": "03_Traffic",
        "source": "03_Traffic/oldsmobile-cutlass-supreme-sedan-71.zip",
        "role": "traffic",
        "target_length_m": 5.17,
        "target_tris": 30000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "flip_x": False,
        "tint_glass": 0.78,  # Dark glass since hollow interior
        "license": "Check author license (Hollow interior -> tinted for traffic)",
    },
    {
        "id": "Traffic_Lincoln78_A",
        "category": "03_Traffic",
        "source": "03_Traffic/lincoln_continental_mark_v.glb",
        "sub_cluster": "x_gt_-1.5",
        "role": "traffic",
        "target_length_m": 5.85,
        "target_tris": 34000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "flip_x": True,
        "tint_glass": 0.65,
        "license": "CC-BY-4.0 (Split Car A - Gold)",
    },
    {
        "id": "Traffic_Lincoln78_B",
        "category": "03_Traffic",
        "source": "03_Traffic/lincoln_continental_mark_v.glb",
        "sub_cluster": "x_lt_-1.5",
        "role": "traffic",
        "target_length_m": 5.85,
        "target_tris": 34000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "pca_unrotate": True,
        "flip_x": True,
        "tint_glass": 0.65,
        "license": "CC-BY-4.0 (Split Car B - Silver)",
    },
    {
        # Mission target "Limousine Blindada": the silver Lincoln stretched behind the doors (see stretch_body)
        "id": "Target_Limousine78",
        "category": "03_Traffic",
        "source": "03_Traffic/lincoln_continental_mark_v.glb",
        "sub_cluster": "x_lt_-1.5",
        "role": "mission",
        "target_length_m": 5.85,
        "stretch": {"cut_x_m": -0.75, "add_m": 1.2, "slice_m": 0.03},
        "target_tris": 38000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "pca_unrotate": True,
        "flip_x": True,
        "tint_glass": 0.85,
        "license": "CC-BY-4.0 (derivative of Split Car B - Silver, stretched)",
    },
    {
        "id": "Traffic_FiatPunto95",
        "category": "03_Traffic",
        "source": "03_Traffic/free_1995_fiat_punto_gt.glb",
        "role": "traffic",
        "target_length_m": 3.77,
        "target_tris": 28000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "flip_x": True,
        "tint_glass": 0.55,
        "license": "CC-BY-4.0 (Rare import subcompact)",
    },

    # --- 04_Props_Wrecks ---
    {
        "id": "Wreck_BurnedWagon",
        "category": "04_Props_Wrecks",
        "source": "04_Wrecks_Props/burned-out_cars.glb",
        "sub_cluster": "x_gt_0",
        "role": "prop",
        "target_length_m": 4.70,
        "target_tris": 5000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "license": "CC-BY-4.0 (Split Wreck A)",
    },
    {
        "id": "Wreck_BurnedSedan",
        "category": "04_Props_Wrecks",
        "source": "04_Wrecks_Props/burned-out_cars.glb",
        "sub_cluster": "x_lt_0",
        "role": "prop",
        "target_length_m": 4.65,
        "target_tris": 5000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "license": "CC-BY-4.0 (Split Wreck B)",
    },
    {
        "id": "Wreck_BurnedPolice_A",
        "category": "04_Props_Wrecks",
        "source": "04_Wrecks_Props/free-burned-police-cars.zip",
        "sub_object": "Object004",
        "role": "prop",
        "target_length_m": 5.10,
        "target_tris": 15000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "license": "Burned Police Cruiser Wreck A",
    },
    {
        "id": "Wreck_BurnedPolice_B",
        "category": "04_Props_Wrecks",
        "source": "04_Wrecks_Props/free-burned-police-cars.zip",
        "sub_object": "Object005",
        "role": "prop",
        "target_length_m": 5.10,
        "target_tris": 15000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "license": "Burned Police Cruiser Wreck B",
    },
    {
        "id": "Wreck_Caprice_Crashed",
        "category": "04_Props_Wrecks",
        "source": "04_Wrecks_Props/destroyed_car_03__backrooms_car_gameready_ver.glb",
        "role": "prop",
        "target_length_m": 5.10,
        "target_tris": 12000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "license": "CC-BY-4.0",
    },
    {
        "id": "Wreck_TransitBus",
        "category": "04_Props_Wrecks",
        "source": "04_Wrecks_Props/destroyed_bus_01.glb",
        "role": "prop",
        "target_length_m": 11.50,
        "target_tris": 38000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "license": "CC-BY-4.0",
    },
    {
        "id": "Prop_TirePile",
        "category": "04_Props_Wrecks",
        "source": "04_Wrecks_Props/pile_of_old_tires.glb",
        "role": "prop",
        "target_length_m": 2.40,
        "target_tris": 25000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "license": "Prop",
    },

    # --- 05_Rail ---
    {
        "id": "Rail_EMD_GP7",
        "category": "05_Rail",
        "source": "05_Rail/emd-gp7-western-pacific-713.zip",
        "role": "prop",
        "target_length_m": 17.04,
        "target_tris": 140000,
        "max_tex_px": 1024,
        "split_wheels": False,
        "flip_x": False,
        "license": "Check author license (1950s-2000s GP7 Locomotive)",
    },
]


def extract_archive_tree(src_path: Path, tmp_dir: Path, prefer_blend: bool = False) -> Path:
    if src_path.suffix.lower() in (".glb", ".gltf", ".fbx", ".obj"):
        return src_path
    r = subprocess.run([SEVEN_ZIP, "x", str(src_path), f"-o{tmp_dir}", "-y"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
    if r.returncode != 0:
        raise RuntimeError(f"7z failed ({r.returncode}) extracting {src_path.name}: {r.stderr.decode(errors='ignore')[:200]}")
    for nested in list(tmp_dir.rglob("*.zip")) + list(tmp_dir.rglob("*.rar")):
        nd = nested.parent / (nested.stem + "_unp")
        nd.mkdir(exist_ok=True)
        r2 = subprocess.run([SEVEN_ZIP, "x", str(nested), f"-o{nd}", "-y"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
        if r2.returncode != 0:
            raise RuntimeError(f"7z failed ({r2.returncode}) extracting nested {nested.name}")
    models = [p for p in tmp_dir.rglob("*") if p.is_file() and p.suffix.lower() in (".glb", ".fbx", ".obj", ".blend", ".gltf")]
    if prefer_blend:
        prio = {".blend": 0, ".glb": 1, ".fbx": 2, ".obj": 3, ".gltf": 4}
    else:
        prio = {".glb": 0, ".fbx": 1, ".obj": 2, ".blend": 3, ".gltf": 4}
    models.sort(key=lambda x: (prio.get(x.suffix.lower(), 9), -x.stat().st_size))
    return models[0] if models else None


def import_model(model_path: Path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = model_path.suffix.lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(model_path))
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(model_path), automatic_bone_orientation=True)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=str(model_path))
    elif ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(model_path))
    bpy.context.view_layer.update()


def purge_non_mesh_and_bake_transforms():
    # Remove cameras, lights, curves, empties safely while preserving mesh world transforms
    mesh_objs = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons) > 0]
    for o in mesh_objs:
        mw = o.matrix_world.copy()
        o.data = o.data.copy()
        o.data.transform(mw)
        if mw.determinant() < 0:
            o.data.flip_normals()
        o.data.update()
    for o in mesh_objs:
        o.parent = None
        o.matrix_world = Matrix.Identity(4)
    for o in list(bpy.data.objects):
        if o not in mesh_objs:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.update()
    return [o for o in bpy.data.objects if o.type == "MESH"]


def vertex_bounds(objs):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    any_v = False
    for o in objs:
        for v in o.data.vertices:
            any_v = True
            lo.x = min(lo.x, v.co.x); lo.y = min(lo.y, v.co.y); lo.z = min(lo.z, v.co.z)
            hi.x = max(hi.x, v.co.x); hi.y = max(hi.y, v.co.y); hi.z = max(hi.z, v.co.z)
    return (lo, hi) if any_v else (Vector((0, 0, 0)), Vector((0, 0, 0)))


def tri_count(objs) -> int:
    return sum(sum(max(0, len(p.vertices) - 2) for p in o.data.polygons) for o in objs)


def filter_sub_selection(mesh_objs, spec: dict):
    sub_obj = spec.get("sub_object")
    sub_cluster = spec.get("sub_cluster")
    if sub_obj:
        keep = [o for o in mesh_objs if o.name.lower() == sub_obj.lower() or sub_obj.lower() in o.name.lower()]
        for o in list(mesh_objs):
            if o not in keep:
                bpy.data.objects.remove(o, do_unlink=True)
        return keep
    if sub_cluster:
        keep = []
        for o in mesh_objs:
            lo, hi = vertex_bounds([o])
            cx = 0.5 * (lo.x + hi.x)
            cy = 0.5 * (lo.y + hi.y)
            if sub_cluster == "x_gt_-1.5" and cx > -1.5 and cy > 0.6:
                keep.append(o)
            elif sub_cluster == "x_lt_-1.5" and cx <= -1.5 and cy > 0.6:
                keep.append(o)
            elif sub_cluster == "x_gt_0" and cx >= 0.0:
                keep.append(o)
            elif sub_cluster == "x_lt_0" and cx < 0.0:
                keep.append(o)
        for o in list(mesh_objs):
            if o not in keep:
                bpy.data.objects.remove(o, do_unlink=True)
        return keep
    return mesh_objs


def strip_floors_and_badges(mesh_objs):
    # Remove floor/ground/shadow helper planes (preserve vehicle emblems/brands)
    all_lo, all_hi = vertex_bounds(mesh_objs)
    total_dims = all_hi - all_lo
    car_h = max(total_dims.z, 0.01)

    for o in list(mesh_objs):
        nl = o.name.lower()
        mat_names = [ms.material.name.lower() for ms in o.material_slots if ms.material]
        lo, hi = vertex_bounds([o])
        dz = hi.z - lo.z

        is_floor = any(k in nl for k in FLOOR_OBJ_KW) or (mat_names and all(any(k in mn for k in FLOOR_MAT_KW) for mn in mat_names))
        if not is_floor and dz < 0.025 * car_h and (hi.x - lo.x) > 0.65 * total_dims.x and (hi.y - lo.y) > 0.65 * total_dims.y and hi.z < all_lo.z + 0.08 * car_h:
            is_floor = True

        if is_floor:
            bpy.data.objects.remove(o, do_unlink=True)
            continue

        # Also delete faces with explicit floor/shadow materials inside multi-slot meshes
        bad_slots = {
            i for i, ms in enumerate(o.material_slots)
            if ms.material and any(k in ms.material.name.lower() for k in FLOOR_MAT_KW)
        }
        if bad_slots:
            bm = bmesh.new()
            bm.from_mesh(o.data)
            dead = [f for f in bm.faces if f.material_index in bad_slots]
            if dead:
                bmesh.ops.delete(bm, geom=dead, context="FACES")
                bm.to_mesh(o.data)
                o.data.update()
            bm.free()

    return [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons) > 0]


def find_image_files(search_dir: Path) -> list[Path]:
    exts = {".png", ".jpg", ".jpeg", ".tga", ".webp"}
    return [p for p in search_dir.rglob("*") if p.is_file() and p.suffix.lower() in exts]


def relink_and_bind_pbr(mesh_objs, search_dir: Path, spec: dict):
    if not search_dir or not search_dir.is_dir():
        return
    imgs = find_image_files(search_dir)
    by_name = {f.name.lower(): f for f in imgs}
    by_stem = {f.stem.lower(): f for f in imgs}

    # 1. Fix any already-referenced missing images strictly matching image extensions
    for im in bpy.data.images:
        if im.packed_file:
            continue
        pname = Path(bpy.path.abspath(im.filepath)).name.lower() if im.filepath else ""
        cand = by_name.get(pname) or by_stem.get(Path(pname).stem.lower() if pname else "")
        if cand:
            im.filepath = str(cand)
            try:
                im.reload()
            except Exception:
                pass

    def load_img(path: Path, colorspace="sRGB"):
        key = path.name
        for existing in bpy.data.images:
            if Path(bpy.path.abspath(existing.filepath)).resolve() == path.resolve():
                existing.colorspace_settings.name = colorspace
                return existing
        im = bpy.data.images.load(str(path), check_existing=True)
        im.colorspace_settings.name = colorspace
        return im

    def match_tex_by_key(key: str, role_tokens: tuple[str, ...]) -> Path | None:
        key_l = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
        # Direct stem + suffix match
        for tok in role_tokens:
            for cand in imgs:
                cl = re.sub(r"[^a-z0-9]+", "_", cand.stem.lower()).strip("_")
                if cl == f"{key_l}_{tok}" or cl == f"{key_l}{tok}":
                    return cand
        for tok in role_tokens:
            for cand in imgs:
                cl = re.sub(r"[^a-z0-9]+", "_", cand.stem.lower()).strip("_")
                if key_l in cl and cl.endswith(tok):
                    return cand
        return None

    pbr_prefix = spec.get("pbr_prefix", "")
    is_suburban = "suburban" in str(spec.get("source", "")).lower()
    is_honda = "honda-nr750" in str(spec.get("source", "")).lower()
    # 2. Wire materials lacking a valid Base Color image texture
    seen_mats = set()
    for o in mesh_objs:
        for ms in o.material_slots:
            mat = ms.material
            if not mat or mat in seen_mats:
                continue
            seen_mats.add(mat)
            mat.use_nodes = True
            nt = mat.node_tree
            bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if not bsdf:
                bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")

            # Remove broken 0x0 image nodes so Workbench/glTF never render pink
            for n in list(nt.nodes):
                if n.type == "TEX_IMAGE" and (n.image is None or n.image.size[0] == 0):
                    nt.nodes.remove(n)

            base_in = bsdf.inputs.get("Base Color")
            base_tex_node = None
            if base_in and base_in.is_linked:
                src_n = base_in.links[0].from_node
                if src_n.type == "TEX_IMAGE" and src_n.image and src_n.image.size[0] > 0:
                    base_tex_node = src_n
            has_albedo = base_tex_node is not None

            mn_l = mat.name.lower()
            # Generic stripped material names (Suburban 1Mtl, VW Beetle v:MAT_*, Zhabotinsky UCB_*, Oldsmobile M_*, Burned Material #98)
            base_k = re.sub(r"(mtl|\.\d+)$", "", mat.name, flags=re.I)
            base_k = base_k.replace("v:MAT_", "").replace("v:", "")
            base_k = base_k.replace("Material #98", "Material _96").replace("Material #99", "Material _96")
            if pbr_prefix:
                base_k = pbr_prefix
            elif "oldsmobile" in str(spec.get("source", "")).lower():
                if "paint" in mn_l or "body" in mn_l or "dome" in mn_l:
                    base_k = "M_Body"
                elif "wheel" in mn_l:
                    base_k = "M_Wheel"
                    # FBX leaves broken purple BaseColor without texture; force clean rebind to M_Wheel_Diffuse.png
                    if base_in:
                        for lk in list(base_in.links):
                            nt.links.remove(lk)
                        base_in.default_value = (1.0, 1.0, 1.0, 1.0)
                    has_albedo = False
                    base_tex_node = None
                elif "glass" in mn_l:
                    base_k = "M_Glass"
                elif "light" in mn_l:
                    base_k = "M_Lights"
                    if base_in:
                        for lk in list(base_in.links):
                            nt.links.remove(lk)
                        base_in.default_value = (1.0, 1.0, 1.0, 1.0)
                    has_albedo = False
                    base_tex_node = None
                elif "license" in mn_l:
                    base_k = "M_Plate"
                elif "badge" in mn_l:
                    base_k = "M_Badge"
                    if base_in:
                        for lk in list(base_in.links):
                            nt.links.remove(lk)
                        base_in.default_value = (1.0, 1.0, 1.0, 1.0)
                    has_albedo = False
                    base_tex_node = None
                elif "chrome" in mn_l:
                    if base_in:
                        for lk in list(base_in.links):
                            nt.links.remove(lk)
                        base_in.default_value = (0.80, 0.82, 0.85, 1.0)
                    bsdf.inputs["Metallic"].default_value = 0.95
                    bsdf.inputs["Roughness"].default_value = 0.12
                    has_albedo = True
            elif is_suburban:
                if "exterior" in mn_l:
                    base_k = "Driverdoorreardriverdoorreargmc89exterior1"
                elif "interior" in mn_l:
                    base_k = "Reference13refreference13refgmc89interior1"
                elif "gmc89parts" in mn_l:
                    base_k = "Grillechevygrillechevygmc89parts1"
                elif "chrome" in mn_l:
                    bsdf.inputs["Base Color"].default_value = (0.72, 0.74, 0.76, 1.0)
                    bsdf.inputs["Metallic"].default_value = 0.92
                    bsdf.inputs["Roughness"].default_value = 0.14
                elif "blackshiny" in mn_l:
                    bsdf.inputs["Base Color"].default_value = (0.04, 0.04, 0.05, 1.0)
                    bsdf.inputs["Roughness"].default_value = 0.20
            elif is_honda:
                if "bike" in mn_l:
                    base_k = "75_$albedo"
                elif "tyre" in mn_l or "grip" in mn_l:
                    bsdf.inputs["Base Color"].default_value = (0.03, 0.03, 0.03, 1.0)
                    bsdf.inputs["Roughness"].default_value = 0.85
                elif "rim" in mn_l or "exhaust" in mn_l or "chain" in mn_l or "brake" in mn_l:
                    bsdf.inputs["Base Color"].default_value = (0.55, 0.56, 0.58, 1.0)
                    bsdf.inputs["Metallic"].default_value = 0.85
                    bsdf.inputs["Roughness"].default_value = 0.28

            if "bodymat" in mn_l and not match_tex_by_key(base_k, ("dif", "diff", "albedo")):
                base_k = "Generic_bodymat"

            if not has_albedo:
                alb_p = None
                if is_honda and "bike" in mn_l:
                    alb_p = next((c for c in imgs if c.name.lower() == "75_$albedo.png"), None)
                elif pbr_prefix and "decal" in mn_l:
                    for c in imgs:
                        if pbr_prefix in c.stem.lower() and "decal" in c.stem.lower():
                            alb_p = c; break
                elif pbr_prefix and ("glass" in mn_l or "optic" in mn_l):
                    alb_p = match_tex_by_key(pbr_prefix, ("albedo",))
                else:
                    alb_p = match_tex_by_key(base_k, ("albedo", "base_color", "base_color1", "diffuse", "diff", "dif", "d"))
                    if not alb_p and base_k.endswith("_0"):
                        alb_p = match_tex_by_key(base_k[:-2], ("albedo", "diff", "dif", "d"))

                if alb_p:
                    tex_n = nt.nodes.new("ShaderNodeTexImage")
                    tex_n.image = load_img(alb_p, "sRGB")
                    nt.links.new(tex_n.outputs["Color"], bsdf.inputs["Base Color"])
                    base_tex_node = tex_n
                    if pbr_prefix and "decal" in mn_l:
                        nt.links.new(tex_n.outputs["Alpha"], bsdf.inputs["Alpha"])
                        mat.blend_method = "CLIP"

                # PBR auxiliary channels
                key_aux = pbr_prefix if pbr_prefix else base_k
                if not ("decal" in mn_l or "glass" in mn_l):
                    nm_p = match_tex_by_key(key_aux, ("nm", "nmap", "nrm", "normal", "normal_opengl", "n"))
                    if nm_p and not (bsdf.inputs.get("Normal") and bsdf.inputs["Normal"].is_linked):
                        tn = nt.nodes.new("ShaderNodeTexImage")
                        tn.image = load_img(nm_p, "Non-Color")
                        nmap = nt.nodes.new("ShaderNodeNormalMap")
                        nt.links.new(tn.outputs["Color"], nmap.inputs["Color"])
                        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])

                    rg_p = match_tex_by_key(key_aux, ("roughness", "rough"))
                    if rg_p and not (bsdf.inputs.get("Roughness") and bsdf.inputs["Roughness"].is_linked):
                        tr = nt.nodes.new("ShaderNodeTexImage")
                        tr.image = load_img(rg_p, "Non-Color")
                        nt.links.new(tr.outputs["Color"], bsdf.inputs["Roughness"])

                    mt_p = match_tex_by_key(key_aux, ("metall", "metallic", "met"))
                    if mt_p and not (bsdf.inputs.get("Metallic") and bsdf.inputs["Metallic"].is_linked):
                        tm = nt.nodes.new("ShaderNodeTexImage")
                        tm.image = load_img(mt_p, "Non-Color")
                        nt.links.new(tm.outputs["Color"], bsdf.inputs["Metallic"])

                    arm_p = match_tex_by_key(key_aux, ("arm",))
                    if arm_p:
                        ta = nt.nodes.new("ShaderNodeTexImage")
                        ta.image = load_img(arm_p, "Non-Color")
                        sep = nt.nodes.new("ShaderNodeSeparateColor")
                        nt.links.new(ta.outputs["Color"], sep.inputs["Color"])
                        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
                        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])

                op_p = match_tex_by_key(key_aux, ("opacity", "alpha"))
                if ("glass" in mn_l or "window" in mn_l or "badge" in mn_l) and op_p and not (bsdf.inputs.get("Alpha") and bsdf.inputs["Alpha"].is_linked):
                    to = nt.nodes.new("ShaderNodeTexImage")
                    to.image = load_img(op_p, "Non-Color")
                    nt.links.new(to.outputs["Color"], bsdf.inputs["Alpha"])
                    mat.blend_method = "CLIP" if "badge" in mn_l else "BLEND"

            # Ensure active node points cleanly to Base Color texture (or BSDF if solid/procedural) so viewports/Workbench don't show normal maps or magenta!
            if base_tex_node:
                nt.nodes.active = base_tex_node
            else:
                nt.nodes.active = bsdf
            if base_in:
                mat.diffuse_color = tuple(base_in.default_value)


def configure_glass_materials(mesh_objs, tint_alpha: float | None):
    if tint_alpha is None:
        return
    for o in mesh_objs:
        for ms in o.material_slots:
            mat = ms.material
            if not mat:
                continue
            nl = mat.name.lower()
            if any(k in nl for k in NO_GLASS_KW) and not any(k in nl for k in ("windowglass", "windshield", "windscreen", "glass_tex", "citybus_glass")):
                continue
            if any(k in nl for k in GLASS_KW):
                mat.use_nodes = True
                nt = mat.node_tree
                bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
                if bsdf:
                    a_in = bsdf.inputs.get("Alpha")
                    if a_in and not a_in.is_linked:
                        a_in.default_value = tint_alpha
                    r_in = bsdf.inputs.get("Roughness")
                    if r_in and not r_in.is_linked:
                        r_in.default_value = 0.08
                    bc = bsdf.inputs.get("Base Color")
                    if bc and not bc.is_linked and tint_alpha >= 0.45:
                        bc.default_value = (0.04, 0.05, 0.06, 1.0)
                mat.blend_method = "BLEND"


def enforce_clean_materials_and_alpha(mesh_objs):
    """Fixes untextured bright tires and enforces proper glTF alphaMode (OPAQUE, MASK for decals, BLEND only for glass)."""
    GLASS_EXACT = (
        "glass", "window", "windshield", "windscreen", "vidro", "vitre", "transperent",
        "transparent", "clearglass", "windowglass", "glass_tex", "citybus_glass",
        "lights_glass", "light_glass", "red_glass", "orange_glass", "black_glass",
        "glass_ior", "refraction", "lens", "invis", "shadow", "lightbar", "beacon",
    )
    MASK_EXACT = (
        "decal", "sticker", "grille_grid", "grid", "defrost", "stitching",
        "wunderbaum", "numberplates_misk", "m_badge", "grille1",
    )
    TIRE_EXACT = ("tire", "tyre", "llanta", "wire_008061138")

    seen = set()
    for o in mesh_objs:
        for ms in o.material_slots:
            mat = ms.material
            if not mat or mat in seen:
                continue
            seen.add(mat)
            if not mat.use_nodes or not mat.node_tree:
                continue
            nt = mat.node_tree
            bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if not bsdf:
                continue

            nl = mat.name.lower()
            bc = bsdf.inputs.get("Base Color")
            a_in = bsdf.inputs.get("Alpha")

            # 1. Fix untextured bright/white tires -> realistic dark rubber
            if any(k in nl for k in TIRE_EXACT) and bc and not bc.is_linked:
                r, g, b = bc.default_value[0], bc.default_value[1], bc.default_value[2]
                if r > 0.35 or g > 0.35 or b > 0.35 or "wire_008061138" in nl:
                    bc.default_value = (0.03, 0.03, 0.03, 1.0)
                    if bsdf.inputs.get("Roughness") and not bsdf.inputs["Roughness"].is_linked:
                        bsdf.inputs["Roughness"].default_value = 0.85
                    if bsdf.inputs.get("Metallic") and not bsdf.inputs["Metallic"].is_linked:
                        bsdf.inputs["Metallic"].default_value = 0.0

            is_glass = (
                any(k in nl for k in GLASS_EXACT)
                and not (any(k in nl for k in ("headlight_base", "plate", "mirror")) and "glass" not in nl)
            ) or ("optic" in nl and a_in is not None and (a_in.is_linked or a_in.default_value < 0.98))
            is_mask = (not is_glass) and any(k in nl for k in MASK_EXACT)

            if is_glass:
                if hasattr(mat, "blend_method"):
                    mat.blend_method = "BLEND"
                continue

            if is_mask and a_in is not None and a_in.is_linked:
                # Blender 4.2+/5.2 glTF exporter emits alphaMode="MASK" when Alpha passes through GREATER_THAN Math node
                src_link = a_in.links[0]
                if src_link.from_node.type != "MATH" or src_link.from_node.operation != "GREATER_THAN":
                    from_sock = src_link.from_socket
                    nt.links.remove(src_link)
                    math_n = nt.nodes.new("ShaderNodeMath")
                    math_n.operation = "GREATER_THAN"
                    math_n.inputs[1].default_value = 0.5
                    nt.links.new(from_sock, math_n.inputs[0])
                    nt.links.new(math_n.outputs["Value"], a_in)
                if hasattr(mat, "blend_method"):
                    mat.blend_method = "CLIP"
                if hasattr(mat, "alpha_threshold"):
                    mat.alpha_threshold = 0.5
                continue

            # 3. Opaque material: disconnect any accidental PNG alpha link so glTF exports alphaMode="OPAQUE" (Nanite-safe!)
            if a_in is not None:
                for lk in list(a_in.links):
                    nt.links.remove(lk)
                a_in.default_value = 1.0
            if hasattr(mat, "blend_method"):
                mat.blend_method = "OPAQUE"


def strip_whip_antennas(mesh_objs):
    """Strips thin vertical whip antennas (>14 cm above roof p99.5) that inflate collision/bounds Z."""
    all_lo, all_hi = vertex_bounds(mesh_objs)
    dims = all_hi - all_lo
    if dims.x < 3.0 or dims.z > 2.25:
        return mesh_objs

    zs = []
    for o in mesh_objs:
        step = max(1, len(o.data.vertices) // 4000)
        for i in range(0, len(o.data.vertices), step):
            zs.append(o.data.vertices[i].co.z)
    if not zs:
        return mesh_objs
    zs.sort()
    z_p995 = zs[int(len(zs) * 0.995)]
    if (all_hi.z - z_p995) < 0.14:
        return mesh_objs

    for o in list(mesh_objs):
        lo, hi = vertex_bounds([o])
        od = hi - lo
        if hi.z > z_p995 + 0.12 and lo.z > 0.45 and max(od.x, od.y) < 0.30 and len(o.data.polygons) < 2500:
            bpy.data.objects.remove(o, do_unlink=True)
            continue
        if hi.z > z_p995 + 0.12 and len(o.data.polygons) <= 80000:
            bm = bmesh.new()
            bm.from_mesh(o.data)
            islands = bmesh_islands_bounds(bm)
            kill_faces = []
            for comp, ilo, ihi in islands:
                iod = ihi - ilo
                if ihi.z > z_p995 + 0.12 and ilo.z > 0.45 and max(iod.x, iod.y) < 0.30 and len(comp) < 2500:
                    kill_faces.extend(comp)
            if kill_faces:
                bmesh.ops.delete(bm, geom=kill_faces, context="FACES")
                if len(bm.faces) > 0:
                    bm.to_mesh(o.data)
                    o.data.update()
                else:
                    bpy.data.objects.remove(o, do_unlink=True)
            bm.free()

    return [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons) > 0]


def clean_degenerate_geometry(obj):
    """Removes zero-area triangles and loose vertices before export."""
    if not obj or obj.type != "MESH" or not obj.data:
        return
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bad_faces = [f for f in bm.faces if f.calc_area() < 1e-9]
    if bad_faces:
        bmesh.ops.delete(bm, geom=bad_faces, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.validate(clean_customdata=True)
    obj.data.update()


def clamp_and_pack_textures(max_px: int):
    for im in bpy.data.images:
        if im.source not in ("FILE", "GENERATED") or im.size[0] == 0:
            continue
        if not im.packed_file and im.filepath:
            try:
                im.pack()
            except Exception:
                continue
        w, h = im.size[0], im.size[1]
        if max(w, h) > max_px:
            scale = max_px / float(max(w, h))
            nw = max(4, int(round(w * scale)))
            nh = max(4, int(round(h * scale)))
            try:
                im.scale(nw, nh)
                im.pack()
            except Exception:
                pass


def align_and_scale(mesh_objs, spec: dict):
    # 1. Optional PCA unrotate for diagonal vehicles (Civil Service Pack)
    if spec.get("pca_unrotate"):
        pts = []
        for o in mesh_objs:
            step = max(1, len(o.data.vertices) // 2000)
            pts.extend(o.data.vertices[i].co.xy for i in range(0, len(o.data.vertices), step))
        best_ang = 0.0
        best_area = 1e18
        for deg_i in range(180):
            ang = math.radians(deg_i)
            ca, sa = math.cos(ang), math.sin(ang)
            xs = [p.x * ca - p.y * sa for p in pts]
            ys = [p.x * sa + p.y * ca for p in pts]
            area = (max(xs) - min(xs)) * (max(ys) - min(ys))
            if area < best_area:
                best_area = area
                best_ang = ang
        # Fine 0.2 deg refinement around coarse optimum
        base_deg = math.degrees(best_ang)
        for step_i in range(-10, 11):
            ang = math.radians(base_deg + step_i * 0.2)
            ca, sa = math.cos(ang), math.sin(ang)
            xs = [p.x * ca - p.y * sa for p in pts]
            ys = [p.x * sa + p.y * ca for p in pts]
            area = (max(xs) - min(xs)) * (max(ys) - min(ys))
            if area < best_area:
                best_area = area
                best_ang = ang
        rot = Matrix.Rotation(best_ang, 4, "Z")
        for o in mesh_objs:
            o.data.transform(rot)
            o.data.update()

    # 2. Ensure longest horizontal axis lies along X (not Y)
    lo, hi = vertex_bounds(mesh_objs)
    dims = hi - lo
    if dims.y > dims.x * 1.05:
        rot90 = Matrix.Rotation(math.radians(-90.0), 4, "Z")
        for o in mesh_objs:
            o.data.transform(rot90)
            o.data.update()

    # 3. Auto-detect Front vs Rear (+X vs -X) via named objects or silhouette slope if not forced,
    #    then apply spec["flip_x"] if set
    front_sign = 1
    head_xs, tail_xs = [], []
    for o in mesh_objs:
        nl = o.name.lower()
        olo, ohi = vertex_bounds([o])
        cx = 0.5 * (olo.x + ohi.x)
        if any(k in nl for k in ("headlight", "grille", "hood", "bonnet", "steer", "windshield", "_fl", "_fr", "lf", "rf")):
            head_xs.append(cx)
        elif any(k in nl for k in ("taillight", "brakelight", "trunk", "exhaust", "spoiler", "_rl", "_rr", "lr", "rr")):
            tail_xs.append(cx)
    if head_xs and tail_xs and (sum(head_xs) / len(head_xs) < sum(tail_xs) / len(tail_xs)):
        front_sign = -1
    if spec.get("flip_x"):
        front_sign = -front_sign

    if front_sign < 0:
        rot180 = Matrix.Rotation(math.pi, 4, "Z")
        for o in mesh_objs:
            o.data.transform(rot180)
            o.data.update()

    # 4. Normalize real-world length (metres) and place centre XY at (0,0), bottom tyre Z at 0.0
    lo, hi = vertex_bounds(mesh_objs)
    dims = hi - lo
    cur_len = max(dims.x, 1e-5)
    target_len = float(spec["target_length_m"])
    scale_factor = target_len / cur_len

    cx = 0.5 * (lo.x + hi.x)
    cy = 0.5 * (lo.y + hi.y)
    min_z = lo.z
    xform = Matrix.Scale(scale_factor, 4) @ Matrix.Translation(Vector((-cx, -cy, -min_z)))
    for o in mesh_objs:
        o.data.transform(xform)
        o.data.update()


def stretch_body(mesh_objs, spec: dict):
    """Lengthens a car into a stretch limousine (spec["stretch"]; car space after align_and_scale, +X front, metres).
    Cuts at cut_x_m and at cut_x_m - slice_m, spreads that thin slice over slice_m + add_m and moves everything behind it
    back by add_m, so the inserted section repeats the slice's paint, glass and trim; then re-centres the car on X."""
    st = spec.get("stretch")
    if not st:
        return
    cut = float(st["cut_x_m"])
    add = float(st["add_m"])
    sl = float(st.get("slice_m", 0.03))
    rear = cut - sl
    for o in mesh_objs:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        for x in (cut, rear):
            geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
            bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(x, 0.0, 0.0), plane_no=(1.0, 0.0, 0.0))
        for v in bm.verts:
            x = v.co.x
            if x <= rear + 1e-6:
                v.co.x = x - add
            elif x < cut:
                v.co.x = cut - (cut - x) * (sl + add) / sl
        bm.to_mesh(o.data)
        bm.free()
        o.data.update()
    lo, hi = vertex_bounds(mesh_objs)
    shift = Matrix.Translation(Vector((-0.5 * (lo.x + hi.x), 0.0, 0.0)))
    for o in mesh_objs:
        o.data.transform(shift)
        o.data.update()


def bmesh_islands_bounds(bm):
    # Pure bmesh BFS returning [(face_list, vmin, vmax), ...] in O(F) with zero scene object churn
    visited = set()
    islands = []
    for f in bm.faces:
        if f in visited:
            continue
        stack = [f]
        visited.add(f)
        comp = []
        lo = Vector((1e9, 1e9, 1e9))
        hi = Vector((-1e9, -1e9, -1e9))
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for v in cur.verts:
                co = v.co
                if co.x < lo.x: lo.x = co.x
                if co.y < lo.y: lo.y = co.y
                if co.z < lo.z: lo.z = co.z
                if co.x > hi.x: hi.x = co.x
                if co.y > hi.y: hi.y = co.y
                if co.z > hi.z: hi.z = co.z
                for ef in v.link_faces:
                    if ef not in visited:
                        visited.add(ef)
                        stack.append(ef)
        islands.append((comp, lo, hi))
    return islands


def sync_active_base_color_nodes(mesh_objs):
    seen = set()
    for o in mesh_objs:
        for ms in o.material_slots:
            mat = ms.material
            if not mat or mat in seen or not mat.use_nodes or not mat.node_tree:
                continue
            seen.add(mat)
            nt = mat.node_tree
            bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if not bsdf:
                continue
            base_in = bsdf.inputs.get("Base Color")
            base_tex = None
            if base_in and base_in.is_linked and base_in.links[0].from_node.type == "TEX_IMAGE":
                cand = base_in.links[0].from_node
                if cand.image and cand.image.size[0] > 0:
                    base_tex = cand
            nt.nodes.active = base_tex if base_tex else bsdf
            if base_in:
                mat.diffuse_color = tuple(base_in.default_value)


EXCLUDE_WHEEL_OBJ_KW = (
    "steering", "cockpit", "interior", "headliner", "leather", "carpet", "dash",
    "seat", "mirror", "pedal", "gauge", "undercarriage", "chassis", "suspension",
    "strut", "spring", "caliper", "fender", "arch", "liner", "exhaust", "mudflap",
    "bumper", "door", "hood", "trunk", "roof", "glass", "window", "brake_light",
    "_body_", "body_black",
)
EXCLUDE_WHEEL_MAT_KW = (
    "headliner", "leather", "carpet", "steering", "undercarriage", "chassis", "caliper",
    "paint", "body", "glass", "window", "interior", "crownvic", "fender", "mudflap",
    "bumper", "rubber_trim", "rubbertrim", "weatherstrip", "brake_light", "taillight",
    "headlight", "trim", "plastic",
)
EXPLICIT_WHEEL_MAT_KW = (
    "wheelsdually", "h2tire", "h2protector", "toyota_supra_tire", "toyota_supra_brakes",
    "toyota_supra_rim", "llanta", "rb1c_tire", "tire", "tyre", "rim", "wheel_16",
    "wheel_black", "sidewall", "tread",
    "wire_008061138", "brakedisk", "disc_brake", "brake_disc", "rotor", "alloy",
)


def _mat_is_explicit_wheel(mat_name: str) -> bool:
    nl = mat_name.lower()
    if any(k in nl for k in ("steering", "spare", "caliper", "chassis", "body", "paint", "interior", "glass", "window", "brake_light", "taillight", "headlight", "rubber_trim", "rubbertrim", "weatherstrip", "trim", "crownvic")):
        return False
    return any(k in nl for k in EXPLICIT_WHEEL_MAT_KW)


def _split_mesh_by_face_groups(o, groups: dict):
    """Creates one new mesh object per non-empty corner face-set and deletes extracted faces from o."""
    created = []
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.faces.ensure_lookup_table()
    all_moved = set()
    for tag, f_indices in groups.items():
        if not f_indices:
            continue
        all_moved.update(f_indices)
        w_bm = bm.copy()
        w_bm.faces.ensure_lookup_table()
        del_f = [wf for wf in w_bm.faces if wf.index not in f_indices]
        if del_f:
            bmesh.ops.delete(w_bm, geom=del_f, context="FACES")
        if len(w_bm.faces) == 0:
            w_bm.free()
            continue
        w_mesh = bpy.data.meshes.new(f"{o.name}_{tag}")
        w_bm.to_mesh(w_mesh)
        w_bm.free()
        for ms in o.material_slots:
            w_mesh.materials.append(ms.material)
        # Drop unused material slots on extracted wheel piece cleanly
        used_idx = {p.material_index for p in w_mesh.polygons}
        if len(used_idx) < len(w_mesh.materials):
            remap = {}
            new_mats = []
            for old_i in sorted(used_idx):
                if old_i < len(w_mesh.materials):
                    remap[old_i] = len(new_mats)
                    new_mats.append(w_mesh.materials[old_i])
            for p in w_mesh.polygons:
                p.material_index = remap.get(p.material_index, 0)
            w_mesh.materials.clear()
            for nm in new_mats:
                w_mesh.materials.append(nm)
        w_mesh.update()
        w_obj = bpy.data.objects.new(f"{o.name}_{tag}", w_mesh)
        bpy.context.collection.objects.link(w_obj)
        created.append(w_obj)

    if all_moved:
        dead = [f for f in bm.faces if f.index in all_moved]
        if dead:
            bmesh.ops.delete(bm, geom=dead, context="FACES")
        if len(bm.faces) > 0:
            bm.to_mesh(o.data)
            o.data.update()
        else:
            bpy.data.objects.remove(o, do_unlink=True)
    bm.free()
    return created


def extract_wheel_islands_to_objects(mesh_objs, dims: Vector, all_lo: Vector):
    # Step 0: Extract material-tagged wheel faces from monolithic/spanning meshes (Suburban89 OBJ, Supra 4-wheel tire/brake, Beetle llanta, Forza axles)
    for o in list(mesh_objs):
        if o.name not in bpy.data.objects:
            continue
        nl = o.name.lower()
        if any(k in nl for k in EXCLUDE_WHEEL_OBJ_KW):
            continue
        olo, ohi = vertex_bounds([o])
        od = ohi - olo
        if not (od.y > dims.y * 0.45 or od.x > dims.x * 0.45):
            continue
        wheel_slots = {
            idx for idx, ms in enumerate(o.material_slots)
            if ms.material and _mat_is_explicit_wheel(ms.material.name)
        }
        if not wheel_slots:
            continue
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.faces.ensure_lookup_table()
        groups = {"W_FL": set(), "W_FR": set(), "W_RL": set(), "W_RR": set()}
        for f in bm.faces:
            if f.material_index not in wheel_slots:
                continue
            fc = f.calc_center_median()
            if abs(fc.y) >= dims.y * 0.16 and abs(fc.x) >= dims.x * 0.14 and fc.z <= all_lo.z + dims.z * 0.54:
                key = ("W_F" if fc.x >= 0.0 else "W_R") + ("L" if fc.y >= 0.0 else "R")
                groups[key].add(f.index)
        bm.free()
        if all(len(v) > 0 for v in groups.values()) or sum(1 for v in groups.values() if v) >= 2:
            _split_mesh_by_face_groups(o, groups)

    mesh_objs = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons) > 0]

    # Step 1: Island-based extraction for remaining spanning wheel/axle meshes without explicit wheel material tags
    cand_objs = []
    for o in list(mesh_objs):
        nl = o.name.lower()
        mats = " ".join(ms.material.name.lower() for ms in o.material_slots if ms.material)
        if any(k in nl for k in EXCLUDE_WHEEL_OBJ_KW) or any(k in mats for k in ("headliner", "leather", "carpet", "steering", "undercarriage", "caliper")):
            continue
        olo, ohi = vertex_bounds([o])
        od = ohi - olo
        is_w = any(k in nl for k in WHEEL_KW) or any(k in mats for k in WHEEL_MAT_KW)
        spans = od.y > dims.y * 0.45 or od.x > dims.x * 0.45
        if (is_w and spans) or (len(o.data.polygons) <= 120000 and olo.z <= all_lo.z + dims.z * 0.20 and od.y > dims.y * 0.55 and not any(k in nl for k in ("bumper", "skirt", "frame", "floor"))):
            cand_objs.append(o)

    if not cand_objs:
        return mesh_objs

    # Pre-split spanning axle meshes across Y=0 (and X=0 if spanning both axles)
    split_cands = []
    for o in cand_objs:
        olo, ohi = vertex_bounds([o])
        od = ohi - olo
        if od.y > dims.y * 0.50:
            bm = bmesh.new()
            bm.from_mesh(o.data)
            bm.faces.ensure_lookup_table()
            if od.x > dims.x * 0.45:
                groups = {"FL": set(), "FR": set(), "RL": set(), "RR": set()}
                for f in bm.faces:
                    fc = f.calc_center_median()
                    k = ("F" if fc.x >= 0.0 else "R") + ("L" if fc.y >= 0.0 else "R")
                    groups[k].add(f.index)
            else:
                groups = {"L": set(), "R": set()}
                for f in bm.faces:
                    groups["L" if f.calc_center_median().y >= 0.0 else "R"].add(f.index)
            bm.free()
            if sum(1 for v in groups.values() if v) >= 2:
                split_cands.extend(_split_mesh_by_face_groups(o, groups))
                continue
        split_cands.append(o)
    cand_objs = split_cands

    anchors = {}
    cached_islands = []
    for o in cand_objs:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        islands = bmesh_islands_bounds(bm)
        cached_islands.append((o, bm, islands))
        for comp, lo, hi in islands:
            od = hi - lo
            ctr = 0.5 * (lo + hi)
            if (0.35 <= od.x <= 1.05 and 0.35 <= od.z <= 1.05 and 0.10 <= od.y <= 0.55 and
                0.72 <= (od.x / max(od.z, 0.01)) <= 1.38 and
                lo.z <= all_lo.z + dims.z * 0.16 and abs(ctr.y) >= dims.y * 0.24 and abs(ctr.x) >= dims.x * 0.16):
                key = ("F" if ctr.x >= 0 else "R") + ("L" if ctr.y >= 0 else "R")
                ground_bonus = 5.0 if lo.z <= all_lo.z + 0.04 else 0.0
                score = ground_bonus + od.x * od.z * max(od.y, 0.15)
                if key not in anchors or score > anchors[key][0]:
                    anchors[key] = (score, ctr.copy(), lo.copy(), hi.copy())

    if len(anchors) < 4:
        for _, bm, _ in cached_islands:
            bm.free()
        return [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons) > 0]

    for o, bm, islands in cached_islands:
        bm.faces.ensure_lookup_table()
        bad_slots = {
            idx for idx, ms in enumerate(o.material_slots)
            if ms.material and any(k in ms.material.name.lower() for k in EXCLUDE_WHEEL_MAT_KW)
        }
        corner_faces = {"W_FL": set(), "W_FR": set(), "W_RL": set(), "W_RR": set()}
        for comp, lo, hi in islands:
            if any(f.material_index in bad_slots for f in comp):
                continue
            od = hi - lo
            if od.x > 1.05 or od.y > 0.55 or od.z > 1.05:
                continue
            ctr = 0.5 * (lo + hi)
            for k, (_, ac, alo, ahi) in anchors.items():
                if (od.x <= max(1.05, (ahi.x - alo.x) * 1.08) and
                    od.z <= max(1.05, (ahi.z - alo.z) * 1.08) and
                    od.y <= max(0.32, (ahi.y - alo.y) * 1.18) and
                    lo.x >= alo.x - 0.05 and hi.x <= ahi.x + 0.05 and
                    lo.y >= alo.y - 0.08 and hi.y <= ahi.y + 0.08 and
                    lo.z >= alo.z - 0.05 and hi.z <= ahi.z + 0.06 and
                    (ctr - ac).length < 0.25 and abs(ctr.y) >= abs(ac.y) - 0.22):
                    corner_faces[f"W_{k}"].update(f.index for f in comp)
                    break
        bm.free()
        if any(corner_faces.values()):
            _split_mesh_by_face_groups(o, corner_faces)

    return [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons) > 0]


def detect_wheel_clusters(mesh_objs):
    # Returns (fl_objs, fr_objs, rl_objs, rr_objs) if 4 clean corner clusters exist
    all_lo, all_hi = vertex_bounds(mesh_objs)
    dims = all_hi - all_lo

    # ALWAYS split spanning wheel/tire objects (e.g. Supra 4-wheel tire mesh, Beetle llanta, Suburban OBJ) BEFORE finding anchors!
    mesh_objs = extract_wheel_islands_to_objects(mesh_objs, dims, all_lo)
    all_lo, all_hi = vertex_bounds(mesh_objs)
    dims = all_hi - all_lo

    def is_excluded(o):
        nl = o.name.lower()
        if any(k in nl for k in EXCLUDE_WHEEL_OBJ_KW):
            return True
        mat_names = [ms.material.name.lower() for ms in o.material_slots if ms.material]
        if mat_names and any(
            any(bk in mn for bk in EXCLUDE_WHEEL_MAT_KW) and not _mat_is_explicit_wheel(mn)
            for mn in mat_names
        ):
            return True
        return False

    def find_tyre_anchors(objs):
        anchors = {}
        for o in objs:
            if is_excluded(o):
                continue
            olo, ohi = vertex_bounds([o])
            od = ohi - olo
            ctr = 0.5 * (olo + ohi)
            if (0.35 <= od.x <= 1.05 and 0.35 <= od.z <= 1.05 and 0.10 <= od.y <= 0.55 and
                0.72 <= (od.x / max(od.z, 0.01)) <= 1.38 and
                olo.z <= all_lo.z + dims.z * 0.16 and abs(ctr.y) >= dims.y * 0.24 and abs(ctr.x) >= dims.x * 0.16):
                key = ("F" if ctr.x >= 0 else "R") + ("L" if ctr.y >= 0 else "R")
                # Prefer full ground-touching tires over thin outer lettering/sidewalls or smaller rims
                ground_bonus = 5.0 if olo.z <= all_lo.z + 0.04 else 0.0
                score = ground_bonus + od.x * od.z * max(od.y, 0.15)
                prev = anchors.get(key)
                if not prev or score > prev[0]:
                    anchors[key] = (score, ctr, o, olo, ohi)
        return anchors

    anchors = find_tyre_anchors(mesh_objs)

    if len(anchors) == 4:
        corners = {"FL": [], "FR": [], "RL": [], "RR": []}
        for o in mesh_objs:
            nl = o.name.lower()
            if any(k in nl for k in EXCLUDE_WHEEL_OBJ_KW):
                continue
            olo, ohi = vertex_bounds([o])
            od = ohi - olo
            ctr = 0.5 * (olo + ohi)
            if od.x > 1.05 or od.y > 0.55 or od.z > 1.05:
                continue
            mat_excluded = is_excluded(o)
            for k, (_, ac, _, alo, ahi) in anchors.items():
                # Allow compact painted center-hub caps / lug nuts centered strictly inside the wheel hub
                # (e.g. Datsun 240K Cylinder.*_black_paint_0), while still excluding body panels.
                if mat_excluded:
                    is_hub_cap = (
                        od.x <= 0.35 and od.z <= 0.35 and od.y <= 0.16
                        and abs(ctr.x - ac.x) <= 0.06 and abs(ctr.z - ac.z) <= 0.06
                        and olo.y >= alo.y - 0.02 and ohi.y <= ahi.y + 0.02
                    )
                    if not is_hub_cap:
                        continue
                # Skip off-center stationary brake calipers nestled beside the rotor (e.g. CrownVic Object_457)
                if od.x < 0.20 and od.z < 0.26 and abs(ctr.x - ac.x) > 0.07:
                    continue
                if (od.x <= max(1.05, (ahi.x - alo.x) * 1.08) and
                    od.z <= max(1.05, (ahi.z - alo.z) * 1.08) and
                    od.y <= max(0.32, (ahi.y - alo.y) * 1.18) and
                    olo.x >= alo.x - 0.05 and ohi.x <= ahi.x + 0.05 and
                    olo.y >= alo.y - 0.08 and ohi.y <= ahi.y + 0.08 and
                    olo.z >= alo.z - 0.05 and ohi.z <= ahi.z + 0.06 and
                    (ctr - ac).length < 0.25 and abs(ctr.y) >= abs(ac.y) - 0.22):
                    corners[k].append(o)
                    break
        if all(len(v) > 0 for v in corners.values()):
            return corners

    # Secondary fallback by explicit wheel keyword names (never matching steering/interior!)
    corners = {"FL": [], "FR": [], "RL": [], "RR": []}
    for o in mesh_objs:
        if is_excluded(o):
            continue
        nl = o.name.lower()
        mats = " ".join(ms.material.name.lower() for ms in o.material_slots if ms.material)
        is_w = any(k in nl for k in WHEEL_KW) or any(k in mats for k in WHEEL_MAT_KW)
        if not is_w:
            continue
        olo, ohi = vertex_bounds([o])
        od = ohi - olo
        ctr = 0.5 * (olo + ohi)
        if od.y > dims.y * 0.45 or od.x > dims.x * 0.35 or ctr.z > dims.z * 0.55 or abs(ctr.y) < dims.y * 0.24:
            continue
        key = ("F" if ctr.x >= 0 else "R") + ("L" if ctr.y >= 0 else "R")
        corners[key].append(o)

    if all(len(v) > 0 for v in corners.values()):
        return corners
    return None


def decimate_objects(objs, target_tris: int):
    cur = tri_count(objs)
    if cur <= target_tris:
        return
    # Triangulate, weld split vertices, clean degenerates & validate giant monolithic exports (>500k in 1 object)
    is_giant_mono = len(objs) == 1 and cur > 500000
    if is_giant_mono:
        o = objs[0]
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.002)
        bmesh.ops.dissolve_degenerate(bm, dist=0.001, edges=bm.edges)
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
        bm.to_mesh(o.data)
        o.data.update()
        bm.free()
        o.data.validate(clean_customdata=True)
        cur = tri_count(objs)

    def run_collapse(o, ratio_val: float) -> bool:
        pre_lo, pre_hi = vertex_bounds([o])
        pre_z = max(0.05, pre_hi.z - pre_lo.z)
        backup = o.data.copy()
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        mod = o.modifiers.new("WSPC2_Decimate", "DECIMATE")
        mod.decimate_type = "COLLAPSE"
        mod.ratio = max(0.01, min(1.0, ratio_val))
        mod.use_collapse_triangulate = True
        try:
            bpy.ops.object.modifier_apply(modifier=mod.name)
            o.data.validate(clean_customdata=True)
            post_lo, post_hi = vertex_bounds([o])
            if (post_hi.z - post_lo.z) > pre_z * 1.18:
                print(f"WARNING: {o.name} decimate z-spike {pre_z:.3f} -> {post_hi.z - post_lo.z:.3f} (reverted)")
                old = o.data
                o.data = backup
                bpy.data.meshes.remove(old, do_unlink=True)
                return False
            bpy.data.meshes.remove(backup, do_unlink=True)
            return True
        except Exception:
            if mod.name in o.modifiers:
                o.modifiers.remove(mod)
            bpy.data.meshes.remove(backup, do_unlink=True)
            return False

    if is_giant_mono:
        # Iterative gentle collapse steps preserve flat door/roof panels and revert if Z spikes
        cur_after = cur
        for _ in range(5):
            if cur_after <= target_tris * 1.15:
                break
            step_r = max(0.35, target_tris / max(1.0, cur_after))
            if not run_collapse(objs[0], step_r):
                break
            nxt = tri_count(objs)
            if nxt >= cur_after * 0.96:
                break
            cur_after = nxt
        return

    ratio = max(0.008, target_tris / float(cur))
    passes = [0.18, max(0.03, target_tris / max(1.0, cur * 0.18))] if ratio < 0.08 else [ratio]
    for r in passes:
        for o in objs:
            t = sum(max(0, len(p.vertices) - 2) for p in o.data.polygons)
            if t < 150:
                continue
            run_collapse(o, r)


def join_objs(objs, new_name: str):
    if not objs:
        return None
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    res = bpy.context.view_layer.objects.active
    res.name = new_name
    res.data.name = new_name
    return res


def export_glb(obj, out_path: Path):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=str(out_path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
    )


def prepare_single(spec: dict) -> dict:
    src = ORIG_DIR / spec["source"]
    dest_dir = OUT_DIR / spec["category"] / spec["id"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Remove any stale GLBs from previous runs (e.g. if split_wheels changed)
    for stale in dest_dir.glob("*.glb"):
        stale.unlink(missing_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"wspc2_prep_{spec['id']}_"))
    try:
        model_path = extract_archive_tree(src, tmp_dir, prefer_blend=spec.get("prefer_blend", False))
        if not model_path or not model_path.exists():
            return {"id": spec["id"], "error": f"model not found in {src}"}

        import_model(model_path)
        objs = purge_non_mesh_and_bake_transforms()
        objs = filter_sub_selection(objs, spec)
        objs = strip_floors_and_badges(objs)
        if not objs:
            return {"id": spec["id"], "error": "empty after filter"}

        if src.suffix.lower() == ".zip":
            relink_and_bind_pbr(objs, tmp_dir, spec)
        configure_glass_materials(objs, spec.get("tint_glass"))
        enforce_clean_materials_and_alpha(objs)
        sync_active_base_color_nodes(objs)
        align_and_scale(objs, spec)
        stretch_body(objs, spec)
        objs = strip_whip_antennas(objs)

        layout = {
            "id": spec["id"],
            "category": spec["category"],
            "role": spec["role"],
            "axes": "Blender: +X front, +Y left, +Z up -> imports directly as UE5 +X forward, +Y right, +Z up",
            "license": spec.get("license", ""),
            "files": [],
        }

        wheel_clusters = detect_wheel_clusters(objs) if spec.get("split_wheels") else None
        if wheel_clusters:
            # Prefer FL unless artist posed front wheels steered (wider Y or less circular than RL -> export straight RL instead!)
            centres = {}
            sizes = {}
            for k in ("FL", "FR", "RL", "RR"):
                wlo, whi = vertex_bounds(wheel_clusters[k])
                centres[k] = [round(v, 4) for v in (0.5 * (wlo + whi))]
                sizes[k] = whi - wlo

            fl_size, rl_size = sizes["FL"], sizes["RL"]
            fl_steered = (fl_size.y > rl_size.y * 1.15) or (abs(fl_size.x - fl_size.z) > abs(rl_size.x - rl_size.z) + 0.015)
            chosen_key = "RL" if fl_steered else "FL"

            # If front wheels were posed steered asymmetrically in X, symmetrize front axle X & Y cleanly
            if abs(centres["FL"][0] - centres["FR"][0]) > 0.015 and abs(centres["RL"][0] - centres["RR"][0]) < 0.015:
                avg_fx = round(0.5 * (centres["FL"][0] + centres["FR"][0]), 4)
                avg_fy = round(0.5 * (abs(centres["FL"][1]) + abs(centres["FR"][1])), 4)
                centres["FL"][0] = avg_fx
                centres["FR"][0] = avg_fx
                centres["FL"][1] = avg_fy
                centres["FR"][1] = -avg_fy

            chosen_objs = wheel_clusters[chosen_key]
            other_wheels = [o for k, lst in wheel_clusters.items() if k != chosen_key for o in lst]
            ch_lo, ch_hi = vertex_bounds(chosen_objs)
            ch_ctr = 0.5 * (ch_lo + ch_hi)
            ch_size = ch_hi - ch_lo

            for o in other_wheels:
                if o.name in bpy.data.objects:
                    bpy.data.objects.remove(o, do_unlink=True)
            body_objs = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons) > 0 and o not in chosen_objs]

            decimate_objects(chosen_objs, 7500)
            body_budget = max(12000, int(spec["target_tris"]) - 4 * tri_count(chosen_objs))
            decimate_objects(body_objs, body_budget)

            for o in chosen_objs:
                o.data.transform(Matrix.Translation(-ch_ctr))
                o.data.update()

            clamp_and_pack_textures(spec.get("max_tex_px", 1024))
            body = join_objs(body_objs, f"{spec['id']}_Body")
            wheel = join_objs(chosen_objs, f"{spec['id']}_Wheel")
            clean_degenerate_geometry(body)
            clean_degenerate_geometry(wheel)
            enforce_clean_materials_and_alpha([body, wheel])

            body_glb = dest_dir / f"{spec['id']}_Body.glb"
            wheel_glb = dest_dir / f"{spec['id']}_Wheel.glb"
            export_glb(body, body_glb)
            export_glb(wheel, wheel_glb)

            blo, bhi = vertex_bounds([body])
            wlo_f, whi_f = vertex_bounds([wheel])
            wsize_f = whi_f - wlo_f
            layout.update({
                "split_wheels": True,
                "wheel_source_corner": chosen_key,
                "wheel_centres_m": centres,
                "ue_wheel_offsets_cm": {k: [round(c[0]*100, 1), round(-c[1]*100, 1), round(c[2]*100, 1)] for k, c in centres.items()},
                "wheel_radius_m": round(0.5 * max(wsize_f.x, wsize_f.z), 4),
                "body_tris": tri_count([body]),
                "wheel_tris": tri_count([wheel]),
                "mats": len(body.data.materials),
                "dims_m": [round(bhi.x - blo.x, 3), round(bhi.y - blo.y, 3), round(bhi.z - blo.z, 3)],
                "files": [body_glb.name, wheel_glb.name],
            })
        else:
            objs = [o for o in bpy.data.objects if o.type == "MESH" and len(o.data.polygons) > 0]
            decimate_objects(objs, int(spec["target_tris"]))
            clamp_and_pack_textures(spec.get("max_tex_px", 1024))
            full = join_objs(objs, spec["id"])
            clean_degenerate_geometry(full)
            enforce_clean_materials_and_alpha([full])
            flo, fhi = vertex_bounds([full])
            if abs(flo.z) > 1e-4:
                full.data.transform(Matrix.Translation((0.0, 0.0, -flo.z)))
                full.data.update()
                flo, fhi = vertex_bounds([full])
            full_glb = dest_dir / f"{spec['id']}.glb"
            export_glb(full, full_glb)
            layout.update({
                "split_wheels": False,
                "tris": tri_count([full]),
                "mats": len(full.data.materials),
                "dims_m": [round(fhi.x - flo.x, 3), round(fhi.y - flo.y, 3), round(fhi.z - flo.z, 3)],
                "files": [full_glb.name],
            })

        (dest_dir / "layout.json").write_text(json.dumps(layout, indent=2, ensure_ascii=False), encoding="utf-8")
        if "CC-BY-ND" in spec.get("license", "") or "Forza" in spec.get("license", "") or "NON-COMMERCIAL" in spec.get("license", ""):
            (dest_dir / "LICENSE_WARNING.txt").write_text(spec["license"] + "\n", encoding="utf-8")

        print(f"PREPARED {spec['id']:28s} -> {layout.get('body_tris', layout.get('tris', 0)):6d} tris | dims={layout['dims_m']} | wheels={layout['split_wheels']}")
        return layout
    except Exception as exc:
        print(f"ERROR {spec['id']}: {exc}")
        return {"id": spec["id"], "error": str(exc)}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


GROUP_ALIASES = {
    "police": "01_Police",
    "01_police": "01_Police",
    "playable": "02_Playable",
    "hero": "02_Playable",
    "02_playable": "02_Playable",
    "traffic": "03_Traffic",
    "03_traffic": "03_Traffic",
    "wrecks": "04_Props_Wrecks",
    "props": "04_Props_Wrecks",
    "04_props_wrecks": "04_Props_Wrecks",
    "rail": "05_Rail",
    "05_rail": "05_Rail",
}


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", help="Category folder or alias (police, playable, traffic, wrecks, rail, all)")
    parser.add_argument("--only", nargs="+", help="Specific recipe IDs")
    args = parser.parse_args(argv)

    targets = RECIPES
    if args.only:
        want = set(args.only)
        targets = [r for r in RECIPES if r["id"] in want]
    elif args.group and args.group.lower() != "all":
        resolved = GROUP_ALIASES.get(args.group.lower(), args.group)
        targets = [r for r in RECIPES if r["category"].lower() == resolved.lower()]

    manifest_path = OUT_DIR / "manifest.json"
    existing = {}
    if manifest_path.exists():
        for entry in json.loads(manifest_path.read_text(encoding="utf-8")):
            existing[entry["id"]] = entry

    valid_ids = {r["id"] for r in RECIPES}
    for obsolete_id in list(existing.keys()):
        if obsolete_id not in valid_ids:
            del existing[obsolete_id]

    for spec in targets:
        res = prepare_single(spec)
        existing[spec["id"]] = res
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(list(existing.values()), indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
