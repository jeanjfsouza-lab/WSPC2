"""Organizes raw third-party downloads inside ASSETS TO USE into categorized 00_Originais subfolders
while keeping city_gps_relief_map*.png, processed/, VehicleVarietyPackVolume2/, and CityParkEnvironmentCollec/
in their exact expected root paths.

Command:
  python Tools/vehicles/organize_assets.py

Inputs:
  ASSETS TO USE/* raw .glb/.zip downloads

Outputs:
  ASSETS TO USE/00_Originais/{01_Police,02_Playable_Hero,03_Traffic,04_Wrecks_Props,05_Rail,06_Archive_Descartados}/
"""
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "ASSETS TO USE"
ORIG_DIR = ASSETS_DIR / "00_Originais"

KEEP_IN_ROOT = {
    "city_gps_relief_map.png",
    "city_gps_relief_map_v2.png",
}

CATEGORY_MAP = {
    "01_Police": [
        "2001_crown_victoria_police_interceptor_game_prop.glb",
        "chevrolet_caprice_police_car_-94_free_asset.glb",
        "harley-davidson_flhtp-electra_glide_police_h.p..glb",
        "murphy_97_cruiser_-_low_poly_model.glb",
        "thunderbolt_96_interceptor_-_low_poly_model.glb",
        "fairheaven_lt_80_cop_cruiser_-_low_poly_model.glb",
        "negotiator_80_cop_cruiser_-_low_poly_model.glb",
        "generic-civil-service-vehicles-pack.zip",
    ],
    "02_Playable_Hero": [
        "1989-chevrolet-suburban.zip",
        "bmw-e39-free.zip",
        "ford_crown_victoria_lx_2011.glb",
        "ford-crown-victoria-lx-2011.zip",
        "bmw_3_series_touring_e46_2001.glb",
        "1997-bmw-m3-e36.zip",
        "1995-bmw-m5-e34.zip",
        "1995-bmw-850csi.zip",
        "1991-bmw-m3-e30.zip",
        "free_bmw_m3_e30.glb",
        "1986-bmw-m635csi.zip",
        "1981-bmw-m1.zip",
        "toyota_supra_mk_iv_1994.glb",
        "toyota-ae86-black-limited-kouki.zip",
        "ferrari-f40.zip",
        "free_1975_porsche_911_930_turbo.glb",
        "1968-volkswagen-beetle.zip",
        "ford-ltd-wagon.zip",
        "free_1972_datsun_240k_gt.glb",
        "1992_alfa_romeo_155_q4.glb",
        "alfa_romeo_sz_1990.glb",
        "honda-nr750-1994.zip",
    ],
    "03_Traffic": [
        "illinois_90_-_low_poly_model.glb",
        "fairheaven-sw-84-low-poly-model.zip",
        "kiri-86-low-poly-model.zip",
        "lct-3000-95-low-poly-model.zip",
        "phoenix_455_71_-_low_poly_model.glb",
        "free_gmc_motorhome_reimagined_low_poly.glb",
        "oldsmobile-cutlass-supreme-sedan-71.zip",
        "lincoln_continental_mark_v.glb",
        "free_1995_fiat_punto_gt.glb",
    ],
    "04_Wrecks_Props": [
        "burned-out_cars.glb",
        "free-burned-police-cars.zip",
        "destroyed_car_03__backrooms_car_gameready_ver.glb",
        "destroyed_bus_01.glb",
        "pile_of_old_tires.glb",
    ],
    "05_Rail": [
        "emd-gp7-western-pacific-713.zip",
    ],
    "06_Archive_Descartados": [
        "mitsubishi_lancer_evo_ix__www.vecarz.com.glb",
        "dirty_lada_lowpoly_from_scan.glb",
        "free_zuk_3d_model.glb",
        "destroyed_cars.glb",
        "destroyed-car-03-raw-scan.zip",
        "destroyed-car-07-raw-scan.zip",
        "wall-of-cars-free-raw-scan.zip",
        "hk-416-a7-free-download.zip",
    ],
}


def main():
    moved = 0
    for cat, files in CATEGORY_MAP.items():
        dst_dir = ORIG_DIR / cat
        dst_dir.mkdir(parents=True, exist_ok=True)
        for fname in files:
            src = ASSETS_DIR / fname
            dst = dst_dir / fname
            if src.exists() and src.is_file():
                shutil.move(str(src), str(dst))
                moved += 1
                print(f"Moved {fname} -> 00_Originais/{cat}/")

    remaining = [
        p.name for p in sorted(ASSETS_DIR.iterdir())
        if p.is_file() and p.name not in KEEP_IN_ROOT
    ]
    print(f"Done. Moved {moved} raw files into 00_Originais/. Remaining root files: {remaining}")


if __name__ == "__main__":
    main()
