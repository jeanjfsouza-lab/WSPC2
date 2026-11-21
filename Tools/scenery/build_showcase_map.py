"""Creates a standalone git-ignored UE 5.8 Lumen/Nanite showcase map at
/Game/Scenery/Imported/Maps/L_SceneryShowcase displaying:
  - Nuclear Power Plant complex (2x CoolingTower, ReactorDome, TurbineHall, 2x RustedTank)
  - Port of Oakland dock (2x SM_Port_STSCrane, SM_Port_ContainerShip, SM_Port_CraneSokol, ATC Tower)
  - Coupled US freight train (TankCar_Graffiti + 7 Intermodal Single/Double Well-Car variants)
  - Oakland Suburban street with all 16 distinct suburban house variants + Date Palms + Chinatown Signboards
and writes Saved/SceneryShowcase/views.txt for automated capture with -WSPC2Views.

Command (editor closed):
  UnrealEditor-Cmd.exe WSPC2.uproject -ExecutePythonScript="Tools/scenery/build_showcase_map.py" -unattended -RenderOffscreen -nosplash -nosound

Inputs:
  /Game/Scenery/Imported/** (built by Tools/scenery/import_and_dress_scenery.py)

Outputs:
  /Game/Scenery/Imported/Maps/L_SceneryShowcase
  Saved/SceneryShowcase/views.txt
"""
import os
import unreal

PROJECT_DIR = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
MAP_PATH = "/Game/Scenery/Imported/Maps/L_SceneryShowcase"
VIEWS_DIR = os.path.join(PROJECT_DIR, "Saved", "SceneryShowcase")
VIEWS_FILE = os.path.join(VIEWS_DIR, "views.txt")

EAL = unreal.EditorAssetLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LES = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
REGISTRY = unreal.AssetRegistryHelpers.get_asset_registry()


def find_mesh(folder_or_path: str):
    if EAL.does_asset_exist(folder_or_path):
        a = EAL.load_asset(folder_or_path)
        if isinstance(a, unreal.StaticMesh):
            return a
    for data in REGISTRY.get_assets_by_path(folder_or_path, recursive=True):
        if str(data.asset_class_path.asset_name) == "StaticMesh":
            return data.get_asset()
    unreal.log_warning("SHOWCASE missing mesh: " + folder_or_path)
    return None


def spawn_sm(mesh_or_path, loc_cm, yaw_deg=0.0, scale=1.0, label=None, mat_override=None):
    mesh = mesh_or_path if isinstance(mesh_or_path, unreal.StaticMesh) else find_mesh(mesh_or_path)
    if not mesh:
        return None
    actor = EAS.spawn_actor_from_class(
        unreal.StaticMeshActor,
        unreal.Vector(loc_cm[0], loc_cm[1], loc_cm[2]),
        unreal.Rotator(roll=0.0, pitch=0.0, yaw=yaw_deg),
    )
    if not actor:
        return None
    smc = actor.static_mesh_component
    smc.set_static_mesh(mesh)
    actor.set_actor_scale3d(
        unreal.Vector(scale, scale, scale) if isinstance(scale, (int, float)) else unreal.Vector(*scale)
    )
    if mat_override:
        m = EAL.load_asset(mat_override)
        if m:
            smc.set_material(0, m)
    if label:
        actor.set_actor_label(label)
    return actor


def setup_environment():
    plane = EAL.load_asset("/Engine/BasicShapes/Plane")
    ground = spawn_sm(
        plane, (0, 0, 0), 0.0, (8000.0, 8000.0, 1.0),
        label="Showcase_Ground",
        mat_override="/Game/Bay/Materials/MI_Bay_AsphaltMS",
    )
    if ground and not ground.static_mesh_component.get_material(0):
        m = EAL.load_asset(
            "/Game/Scene_Warehouse/Assets/MS/Surfaces/Ind_War_Floor_Concrete_Smooth_01/MI_Ind_War_Floor_Concrete_Smooth_01_A"
        )
        if m:
            ground.static_mesh_component.set_material(0, m)

    sun = EAS.spawn_actor_from_class(
        unreal.DirectionalLight,
        unreal.Vector(0, 0, 2000),
        unreal.Rotator(roll=0.0, pitch=-34.0, yaw=-42.0),
    )
    sun.set_actor_label("Sun")
    lc = sun.light_component
    lc.set_intensity(10.0)
    lc.set_light_color(unreal.LinearColor(1.0, 0.95, 0.88, 1.0))
    lc.set_atmosphere_sun_light(True)

    sky_atmo = EAS.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))
    sky_atmo.set_actor_label("SkyAtmosphere")

    sky_light = EAS.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 2500))
    sky_light.set_actor_label("SkyLight")
    sky_light.light_component.set_editor_property("real_time_capture", True)
    sky_light.light_component.set_intensity(1.1)

    fog = EAS.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0))
    fog.set_actor_label("BayFog")
    fog.component.set_fog_density(0.004)
    fog.component.set_fog_height_falloff(0.2)

    clouds = EAS.spawn_actor_from_class(unreal.VolumetricCloud, unreal.Vector(0, 0, 0))
    clouds.set_actor_label("Clouds")

    pp = EAS.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
    pp.set_actor_label("PostProcess")
    pp.unbound = True


def main():
    EAL.make_directory("/Game/Scenery/Imported/Maps")
    LES.new_level(MAP_PATH)
    setup_environment()

    # =========================================================================
    # ZONE 1: NUCLEAR POWER PLANT COMPLEX (around X=0, Y=0)
    # =========================================================================
    spawn_sm("/Game/Scenery/Imported/02_Usina_Nuclear/SM_Nuclear_CoolingTower", (-5500, -5200, 0), 15.0, 1.0, "CoolingTower_1")
    spawn_sm("/Game/Scenery/Imported/02_Usina_Nuclear/SM_Nuclear_CoolingTower", (4800, -5200, 0), -25.0, 1.0, "CoolingTower_2")
    spawn_sm("/Game/Scenery/Imported/02_Usina_Nuclear/SM_Nuclear_ReactorDome", (-1800, 3200, 0), 90.0, 1.0, "ReactorDome")
    spawn_sm("/Game/Scenery/Imported/02_Usina_Nuclear/SM_Nuclear_TurbineHall", (5800, 3400, 0), 0.0, 1.0, "TurbineHall")
    spawn_sm("/Game/Scenery/Imported/02_Usina_Nuclear/SM_Nuclear_RustedTank", (-7200, 3400, 0), 0.0, 1.0, "RustedTank_1")
    spawn_sm("/Game/Scenery/Imported/02_Usina_Nuclear/SM_Nuclear_RustedTank", (-7200, 4800, 0), 40.0, 1.0, "RustedTank_2")

    # =========================================================================
    # ZONE 2: PORT OF OAKLAND DOCK & AIRPORT TOWER (around X=30000, Y=0)
    # =========================================================================
    spawn_sm("/Game/Scenery/Imported/03_Porto/SM_Port_STSCrane", (30000, -3200, 0), 180.0, 1.0, "STSCrane_1")
    spawn_sm("/Game/Scenery/Imported/03_Porto/SM_Port_STSCrane", (30000, 3200, 0), 180.0, 1.0, "STSCrane_2")
    spawn_sm("/Game/Scenery/Imported/03_Porto/SM_Port_ContainerShip", (34500, 0, -250), 90.0, 1.0, "ContainerShip")
    spawn_sm("/Game/Scenery/Imported/03_Porto/SM_Port_CraneSokol", (28500, 9500, 0), -20.0, 1.0, "CraneSokol")
    spawn_sm("/Game/Scenery/Imported/04_Aeroporto/SM_Airport_ATCTower", (26000, -11000, 0), 0.0, 1.0, "ATCTower")

    # =========================================================================
    # ZONE 3: COUPLED FREIGHT TRAIN (along X at Y=16000)
    # =========================================================================
    rail_lineup = [
        ("/Game/Scenery/Imported/06_Ferrovia_Vagoes/SM_Rail_TankCar_Graffiti", 0),
        ("/Game/Scenery/Imported/06_Ferrovia_Vagoes/SM_Rail_WellCar_Double", 1740),
        ("/Game/Scenery/Imported/06_Ferrovia_Vagoes/Variants/SM_Rail_WellCar_Double_VarGreenOchre", 3480),
        ("/Game/Scenery/Imported/06_Ferrovia_Vagoes/Variants/SM_Rail_WellCar_Double_VarNavyGrey", 5220),
        ("/Game/Scenery/Imported/06_Ferrovia_Vagoes/Variants/SM_Rail_WellCar_Double_VarOchreRed", 6960),
        ("/Game/Scenery/Imported/06_Ferrovia_Vagoes/SM_Rail_WellCar_Single", 8700),
        ("/Game/Scenery/Imported/06_Ferrovia_Vagoes/Variants/SM_Rail_WellCar_Single_VarNavy", 10440),
        ("/Game/Scenery/Imported/06_Ferrovia_Vagoes/Variants/SM_Rail_WellCar_Single_VarGreen", 12180),
    ]
    for idx, (rpath, dx) in enumerate(rail_lineup):
        spawn_sm(rpath, (-4000 + dx, 16000, 0), 0.0, 1.0, f"RailCar_{idx}")

    # =========================================================================
    # ZONE 4: OAKLAND SUBURBAN STREET (all 16 house variants along Y=26000 & Y=31500)
    # =========================================================================
    row1 = [
        "/Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_HouseA_Var1_QuixelCream_Slate",
        "/Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_HouseB_Var1_QuixelBlue_Slate",
        "/Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_HouseC_Var1_QuixelWhite_Slate",
        "/Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_HouseD_Victorian_Var1_OaklandBlue_Slate",
        "/Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_HouseA_Var2_QuixelSage_BrownRoof",
        "/Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_HouseB_Var2_QuixelCream_Brown",
        "/Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_HouseC_Var2_QuixelCream_Terra",
        "/Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_HouseD_Victorian_Var2_OaklandCream_Brown",
    ]
    row2 = [
        "/Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_HouseA_Var3_QuixelBlue_GreyRoof",
        "/Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_HouseB_Var3_CityParkWall_Terra",
        "/Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_HouseC_Var3_DWPlaster_BrownRoof",
        "/Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_HouseD_Victorian_Var3_OaklandSage_Grey",
        "/Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_HouseA_Var4_Terracotta_TerraRoof",
        "/Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_HouseB_Var4_QuixelSage_GreyRoof",
        "/Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_HouseC_Var4_QuixelSage_GreyRoof",
        "/Game/Scenery/Imported/01_Suburbios_Casas/Variants/SM_Suburb_HouseD_Victorian_Var4_OaklandTerra_RedRoof",
    ]
    for i, hp in enumerate(row1):
        spawn_sm(hp, (-9000 + i * 2400, 26000, 0), 0.0, 1.0, f"SuburbRow1_{i}")
    for i, hp in enumerate(row2):
        spawn_sm(hp, (-9000 + i * 2400, 31500, 0), 180.0, 1.0, f"SuburbRow2_{i}")
    for i in range(6):
        spawn_sm("/Game/Scenery/Imported/07_Palmeiras/SM_Flora_DatePalm", (-8200 + i * 3200, 28600, 0), i * 57.0, 1.0, f"DatePalm_{i}")
    spawn_sm("/Game/Scenery/Imported/05_Chinatown/SM_Chinatown_Signboards", (-11500, 28600, 0), 90.0, 1.0, "Chinatown_Signs")

    LES.save_current_level()

    os.makedirs(VIEWS_DIR, exist_ok=True)
    views = [
        "SC_warmup;-14000,15000,7500;0,-1000,2500",
        "SC_01_Nuclear_Wide;-13500,15500,7200;400,-1200,2400",
        "SC_02_Nuclear_CoolingClose;200,-1400,1200;-5500,-5200,3200",
        "SC_03_Nuclear_ReactorTurbine;2500,10800,2400;1800,3200,1700",
        "SC_04_Port_STSCrane_Ship;18500,-9200,4800;31800,500,2000",
        "SC_05_Port_STSCrane_Close;23500,-7600,1800;30500,-2400,2200",
        "SC_06_Rail_Train_Wide;-6500,12600,900;3500,16000,320",
        "SC_07_Rail_DoubleStack_Close;400,14100,480;2500,16000,310",
        "SC_08_Suburbs_Street_Wide;-11800,28750,820;5000,28750,350",
        "SC_09_Suburbs_Row1_Close;-10500,29200,520;-3500,26000,360",
        "SC_10_Suburbs_Row2_Victorian;6200,29400,560;4200,31500,420",
    ]
    with open(VIEWS_FILE, "w", encoding="ascii") as f:
        f.write("\n".join(views) + "\n")
    unreal.log(f"SHOWCASE READY: {MAP_PATH} + {len(views)} views -> {VIEWS_FILE}")


if __name__ == "__main__":
    main()
