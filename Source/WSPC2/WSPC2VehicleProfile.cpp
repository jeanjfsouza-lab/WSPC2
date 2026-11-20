// Copyright Epic Games, Inc. All Rights Reserved.

#include "WSPC2VehicleProfile.h"
#include "Engine/StaticMesh.h"

namespace
{
	FWSPC2VehicleProfileSpec MakeCitySamplePreset(
		FName InPresetId,
		const TCHAR* InDisplayName,
		const TCHAR* FolderName,
		const TCHAR* MeshPrefix,
		bool bHasNativeBrakePads)
	{
		FWSPC2VehicleProfileSpec Spec;
		Spec.PresetId = InPresetId;
		Spec.DisplayName = FText::FromString(InDisplayName);
		Spec.WheelLayoutMode = EWSPC2WheelLayoutMode::BakedCarSpace;
		Spec.BodyRelativeRotation = FRotator::ZeroRotator;
		Spec.bAutoComputeCollisionFromBody = true;

		const FString Base = FString::Printf(TEXT("/Game/CitySampleVehicles/%s/Mesh/"), FolderName);
		auto MakeObjPath = [&Base](const FString& AssetName) -> FSoftObjectPath
		{
			return FSoftObjectPath(FString::Printf(TEXT("%s%s.%s"), *Base, *AssetName, *AssetName));
		};

		Spec.BodyMesh = MakeObjPath(FString::Printf(TEXT("SM_%s_No_Wheel"), MeshPrefix));
		Spec.GlassMesh = MakeObjPath(FString::Printf(TEXT("SM_All_Trans_%s"), MeshPrefix));
		Spec.WheelMeshes = {
			MakeObjPath(FString::Printf(TEXT("SM_Wheel_Front_L_%s"), MeshPrefix)),
			MakeObjPath(FString::Printf(TEXT("SM_Wheel_Front_R_%s"), MeshPrefix)),
			MakeObjPath(FString::Printf(TEXT("SM_Wheel_Rear_L_%s"), MeshPrefix)),
			MakeObjPath(FString::Printf(TEXT("SM_Wheel_Rear_R_%s"), MeshPrefix))
		};

		if (bHasNativeBrakePads)
		{
			Spec.FrontBrakeMeshes = {
				MakeObjPath(FString::Printf(TEXT("SM_Brake_Pad_L_%s"), MeshPrefix)),
				MakeObjPath(FString::Printf(TEXT("SM_Brake_Pad_R_%s"), MeshPrefix))
			};
		}

		Spec.OnCarViewNames = { TEXT("Dashboard"), TEXT("Hood"), TEXT("Bumper") };
		return Spec;
	}

	TArray<FWSPC2VehicleProfileSpec> BuildBuiltinPresets()
	{
		TArray<FWSPC2VehicleProfileSpec> Presets;

		// 1. Patrol Cruiser (CitySampleVehicles vehicle13_Car — baseline default)
		{
			FWSPC2VehicleProfileSpec Patrol = MakeCitySamplePreset(
				FName("Patrol"), TEXT("Patrol Cruiser"), TEXT("vehicle13_Car"), TEXT("vehCar_vehicle13"), false);
			Patrol.bIsPoliceCruiser = true;
			Patrol.bHasRoofLightbar = true;
			Patrol.SplitBodyNoFrontBrakesMesh = FSoftObjectPath(TEXT("/Game/CitySampleVehicles/vehicle13_Car/WSPC2/SM_Body_NoFrontBrakes.SM_Body_NoFrontBrakes"));
			Patrol.FrontBrakeMeshes = {
				FSoftObjectPath(TEXT("/Game/CitySampleVehicles/vehicle13_Car/WSPC2/SM_Brake_FL.SM_Brake_FL")),
				FSoftObjectPath(TEXT("/Game/CitySampleVehicles/vehicle13_Car/WSPC2/SM_Brake_FR.SM_Brake_FR"))
			};
			Patrol.bAutoComputeCollisionFromBody = false;
			Patrol.BodyCollisionCenter = FVector(-8.3f, 0.0f, 63.0f);
			Patrol.BodyCollisionExtent = FVector(274.0f, 96.0f, 33.0f);
			Patrol.CabinCollisionCenter = FVector(-32.0f, 0.0f, 126.0f);
			Patrol.CabinCollisionExtent = FVector(122.0f, 82.0f, 32.0f);
			Patrol.GunnerSeatLocation = FVector(5.0f, 78.0f, 120.0f);
			Patrol.LightBarCentre = FVector(-43.8f, 0.0f, 168.0f);
			Patrol.LightBarHalfSpacing = 38.4f;
			// driver and gunner posed for this body by Tools/crew (needs the CitySampleCrowd pack; absent: empty seats)
			Patrol.CrewProfile = FSoftObjectPath(TEXT("/Game/Crew/DA_Crew_Patrol.DA_Crew_Patrol"));
			// the steering wheel cut out of the body by Tools/patrolcar/split_brakes.py; centre and axis as measured
			// there (pose_crew.py SEAT: centre (0.355, 0.415, 0.90) m Blender, face 18 degrees up from upright)
			Patrol.SteeringWheelMesh = FSoftObjectPath(TEXT("/Game/CitySampleVehicles/vehicle13_Car/WSPC2/SM_SteeringWheel.SM_SteeringWheel"));
			Patrol.SteeringWheelCentre = FVector(35.5f, -41.5f, 90.0f);
			Patrol.SteeringWheelAxis = FVector(-0.9511f, 0.0f, 0.3090f);
			Patrol.SteeringWheelMaxDeg = 200.0f;
			Patrol.OnCarViewLocations = { FVector(2.0f, -38.0f, 121.0f), FVector(110.0f, 0.0f, 114.0f), FVector(276.0f, 0.0f, 54.0f) };
			Patrol.MassScale = 1.0f;
			Patrol.MaxTorqueScale = 1.0f;
			Patrol.ChassisHeightCm = 144.0f;
			Presets.Add(MoveTemp(Patrol));
		}

		// 2. Undercover Sedan (CitySampleVehicles vehicle03_Car — full-size detective sedan, 16 fractured mats, native brake pads)
		{
			FWSPC2VehicleProfileSpec Undercover = MakeCitySamplePreset(
				FName("Undercover"), TEXT("Undercover Sedan"), TEXT("vehicle03_Car"), TEXT("vehCar_vehicle03"), true);
			Undercover.bIsPoliceCruiser = false;
			Undercover.bHasRoofLightbar = false;
			Undercover.bAutoComputeCollisionFromBody = false;
			Undercover.BodyCollisionCenter = FVector(-8.0f, 0.0f, 63.0f);
			Undercover.BodyCollisionExtent = FVector(270.0f, 96.0f, 33.0f);
			Undercover.CabinCollisionCenter = FVector(-30.0f, 0.0f, 122.0f);
			Undercover.CabinCollisionExtent = FVector(120.0f, 82.0f, 28.0f);
			Undercover.GunnerSeatLocation = FVector(5.0f, 78.0f, 118.0f);
			Undercover.LightBarCentre = FVector(95.0f, 0.0f, 116.0f);
			Undercover.LightBarHalfSpacing = 24.0f;
			Undercover.OnCarViewLocations = { FVector(2.0f, -38.0f, 119.0f), FVector(110.0f, 0.0f, 112.0f), FVector(274.0f, 0.0f, 54.0f) };
			Undercover.MassScale = 0.98f;
			Undercover.MaxTorqueScale = 1.03f;
			Undercover.ChassisHeightCm = 140.0f;
			Presets.Add(MoveTemp(Undercover));
		}

		// 3. Sports Interceptor (CitySampleVehicles vehicle07_Car — fast low coupe, native brake pads)
		{
			FWSPC2VehicleProfileSpec Interceptor = MakeCitySamplePreset(
				FName("Interceptor"), TEXT("Sports Interceptor"), TEXT("vehicle07_Car"), TEXT("vehCar_vehicle07"), true);
			Interceptor.bIsPoliceCruiser = false;
			Interceptor.bHasRoofLightbar = false;
			Interceptor.GunnerSeatLocation = FVector(-8.0f, 72.0f, 102.0f);
			Interceptor.LightBarCentre = FVector(68.0f, 0.0f, 102.0f);
			Interceptor.LightBarHalfSpacing = 20.0f;
			Interceptor.OnCarViewLocations = { FVector(-8.0f, -36.0f, 104.0f), FVector(95.0f, 0.0f, 95.0f), FVector(224.0f, 0.0f, 44.0f) };
			Interceptor.MassScale = 0.86f;
			Interceptor.MaxTorqueScale = 1.18f;
			Interceptor.ChassisHeightCm = 126.0f;
			Presets.Add(MoveTemp(Interceptor));
		}

		// 4. Federal SUV (CitySampleVehicles vehicle02_Car — heavy utility SUV, native brake pads)
		{
			FWSPC2VehicleProfileSpec SUV = MakeCitySamplePreset(
				FName("SUV"), TEXT("Federal SUV"), TEXT("vehicle02_Car"), TEXT("vehCar_vehicle02"), true);
			SUV.bIsPoliceCruiser = false;
			SUV.bHasRoofLightbar = false;
			SUV.GunnerSeatLocation = FVector(6.0f, 78.0f, 134.0f);
			SUV.LightBarCentre = FVector(82.0f, 0.0f, 136.0f);
			SUV.LightBarHalfSpacing = 24.0f;
			SUV.OnCarViewLocations = { FVector(4.0f, -38.0f, 136.0f), FVector(108.0f, 0.0f, 126.0f), FVector(244.0f, 0.0f, 58.0f) };
			SUV.MassScale = 1.18f;
			SUV.MaxTorqueScale = 1.12f;
			SUV.ChassisHeightCm = 162.0f;
			Presets.Add(MoveTemp(SUV));
		}

		// 5. Tactical Pickup (CitySampleVehicles vehicle04_Truck — heavy full-size pickup)
		{
			FWSPC2VehicleProfileSpec Pickup = MakeCitySamplePreset(
				FName("Pickup"), TEXT("Tactical Pickup"), TEXT("vehicle04_Truck"), TEXT("vehTruck_vehicle04"), false);
			Pickup.bIsPoliceCruiser = false;
			Pickup.bHasRoofLightbar = false;
			Pickup.GunnerSeatLocation = FVector(25.0f, 82.0f, 146.0f);
			Pickup.LightBarCentre = FVector(96.0f, 0.0f, 146.0f);
			Pickup.LightBarHalfSpacing = 26.0f;
			Pickup.OnCarViewLocations = { FVector(24.0f, -40.0f, 148.0f), FVector(130.0f, 0.0f, 136.0f), FVector(282.0f, 0.0f, 62.0f) };
			Pickup.MassScale = 1.24f;
			Pickup.MaxTorqueScale = 1.16f;
			Pickup.ChassisHeightCm = 172.0f;
			Presets.Add(MoveTemp(Pickup));
		}

		// 6. SWAT Van (CitySampleVehicles vehicle09_Van — heavy tactical transport van)
		{
			FWSPC2VehicleProfileSpec SWATVan = MakeCitySamplePreset(
				FName("SWATVan"), TEXT("SWAT Van"), TEXT("vehicle09_Van"), TEXT("vehVan_vehicle09"), false);
			SWATVan.bIsPoliceCruiser = false;
			SWATVan.bHasRoofLightbar = true;
			SWATVan.GunnerSeatLocation = FVector(95.0f, 88.0f, 168.0f);
			SWATVan.LightBarCentre = FVector(80.0f, 0.0f, 246.0f);
			SWATVan.LightBarHalfSpacing = 42.0f;
			SWATVan.OnCarViewLocations = { FVector(100.0f, -44.0f, 174.0f), FVector(225.0f, 0.0f, 145.0f), FVector(322.0f, 0.0f, 68.0f) };
			SWATVan.MassScale = 1.45f;
			SWATVan.MaxTorqueScale = 1.24f;
			SWATVan.ChassisHeightCm = 225.0f;
			Presets.Add(MoveTemp(SWATVan));
		}

		// 7. Undercover Taxi (CitySampleVehicles vehicle12_Car — the vehicle03 sedan body with taxi livery and roof sign,
		//    same wheels and glass; manual collision so the roof sign stays out of the cabin box)
		{
			FWSPC2VehicleProfileSpec UndercoverTaxi = MakeCitySamplePreset(
				FName("UndercoverTaxi"), TEXT("Undercover Taxi"), TEXT("vehicle12_Car"), TEXT("vehCar_vehicle12"), true);
			UndercoverTaxi.bIsPoliceCruiser = false;
			UndercoverTaxi.bHasRoofLightbar = false;
			UndercoverTaxi.bAutoComputeCollisionFromBody = false;
			UndercoverTaxi.BodyCollisionCenter = FVector(-8.0f, 0.0f, 63.0f);
			UndercoverTaxi.BodyCollisionExtent = FVector(270.0f, 96.0f, 33.0f);
			UndercoverTaxi.CabinCollisionCenter = FVector(-30.0f, 0.0f, 122.0f);
			UndercoverTaxi.CabinCollisionExtent = FVector(120.0f, 82.0f, 28.0f);
			UndercoverTaxi.GunnerSeatLocation = FVector(5.0f, 78.0f, 118.0f);
			UndercoverTaxi.LightBarCentre = FVector(95.0f, 0.0f, 116.0f);
			UndercoverTaxi.LightBarHalfSpacing = 24.0f;
			UndercoverTaxi.OnCarViewLocations = { FVector(2.0f, -38.0f, 119.0f), FVector(110.0f, 0.0f, 112.0f), FVector(274.0f, 0.0f, 54.0f) };
			UndercoverTaxi.MassScale = 0.98f;
			UndercoverTaxi.MaxTorqueScale = 1.0f;
			UndercoverTaxi.ChassisHeightCm = 140.0f;
			Presets.Add(MoveTemp(UndercoverTaxi));
		}

		// 8. Delivery Hatch (CitySampleVehicles vehicle06_Car — compact 4.37 m car, 2.39 m wheelbase, native brake pads;
		//    light and slow, the campaign's "Carro de Entregas" unit. Crew and camera points from the mesh bounds)
		{
			FWSPC2VehicleProfileSpec Delivery = MakeCitySamplePreset(
				FName("Delivery"), TEXT("Delivery Hatch"), TEXT("vehicle06_Car"), TEXT("vehCar_vehicle06"), true);
			Delivery.bIsPoliceCruiser = false;
			Delivery.bHasRoofLightbar = false;
			Delivery.GunnerSeatLocation = FVector(-15.0f, 68.0f, 100.0f);
			Delivery.LightBarCentre = FVector(55.0f, 0.0f, 98.0f);
			Delivery.LightBarHalfSpacing = 20.0f;
			Delivery.OnCarViewLocations = { FVector(-15.0f, -35.0f, 104.0f), FVector(85.0f, 0.0f, 98.0f), FVector(226.0f, 0.0f, 44.0f) };
			Delivery.MassScale = 0.82f;
			Delivery.MaxTorqueScale = 0.75f;
			Delivery.ChassisHeightCm = 124.0f;
			Presets.Add(MoveTemp(Delivery));
		}

		// 9. CrownVic Legacy Fallback (/Game/CrownVic)
		{
			FWSPC2VehicleProfileSpec CrownVic;
			CrownVic.PresetId = FName("CrownVic");
			CrownVic.DisplayName = FText::FromString(TEXT("Crown Vic Legacy"));
			CrownVic.bIsPoliceCruiser = false;
			CrownVic.bHasRoofLightbar = true;
			CrownVic.WheelLayoutMode = EWSPC2WheelLayoutMode::CenteredOriginCrownVicLegacy;
			CrownVic.BodyMesh = FSoftObjectPath(TEXT("/Game/CrownVic/CrownVic_Body/StaticMeshes/CrownVic_Body.CrownVic_Body"));
			CrownVic.WheelMeshes = {
				FSoftObjectPath(TEXT("/Game/CrownVic/CrownVic_Wheel/StaticMeshes/CrownVic_Wheel.CrownVic_Wheel"))
			};
			CrownVic.BodyRelativeRotation = FRotator(0.0f, -90.0f, 0.0f);
			CrownVic.WheelOffsetsCm = {
				FVector(153.0f, -80.4f, 35.2f),
				FVector(153.0f, 80.4f, 35.2f),
				FVector(-140.6f, -83.3f, 35.2f),
				FVector(-140.6f, 83.3f, 35.2f)
			};
			CrownVic.DefaultWheelRadiusCm = 35.1f;
			CrownVic.bAutoComputeCollisionFromBody = false;
			CrownVic.BodyCollisionCenter = FVector(-8.3f, 0.0f, 63.0f);
			CrownVic.BodyCollisionExtent = FVector(274.0f, 96.0f, 33.0f);
			CrownVic.CabinCollisionCenter = FVector(-32.0f, 0.0f, 126.0f);
			CrownVic.CabinCollisionExtent = FVector(122.0f, 82.0f, 32.0f);
			CrownVic.GunnerSeatLocation = FVector(0.0f, 78.0f, 118.0f);
			CrownVic.LightBarCentre = FVector(-40.0f, 0.0f, 158.0f);
			CrownVic.LightBarHalfSpacing = 40.0f;
			CrownVic.OnCarViewLocations = { FVector(-5.0f, -38.0f, 118.0f), FVector(105.0f, 0.0f, 112.0f), FVector(268.0f, 0.0f, 52.0f) };
			CrownVic.OnCarViewNames = { TEXT("Dashboard"), TEXT("Hood"), TEXT("Bumper") };
			CrownVic.MassScale = 1.0f;
			CrownVic.MaxTorqueScale = 1.0f;
			CrownVic.ChassisHeightCm = 144.0f;
			Presets.Add(MoveTemp(CrownVic));
		}

		return Presets;
	}
}

const TArray<FWSPC2VehicleProfileSpec>& UWSPC2VehicleProfile::GetBuiltinPresets()
{
	static const TArray<FWSPC2VehicleProfileSpec> Presets = BuildBuiltinPresets();
	return Presets;
}

const FWSPC2VehicleProfileSpec* UWSPC2VehicleProfile::FindBuiltinPreset(FName PresetId)
{
	if (PresetId.IsNone())
	{
		return nullptr;
	}

	const TArray<FWSPC2VehicleProfileSpec>& Presets = GetBuiltinPresets();
	for (const FWSPC2VehicleProfileSpec& Spec : Presets)
	{
		if (Spec.PresetId == PresetId)
		{
			return &Spec;
		}
	}
	return nullptr;
}

bool UWSPC2VehicleProfile::CanLoadPresetAssets(const FWSPC2VehicleProfileSpec& Spec)
{
	if (!Spec.BodyMesh.IsValid())
	{
		return false;
	}

	UStaticMesh* Body = Cast<UStaticMesh>(StaticLoadObject(
		UStaticMesh::StaticClass(), nullptr, *Spec.BodyMesh.ToString(), nullptr, LOAD_NoWarn | LOAD_Quiet));
	if (!Body)
	{
		return false;
	}

	if (Spec.WheelLayoutMode == EWSPC2WheelLayoutMode::BakedCarSpace)
	{
		if (Spec.WheelMeshes.Num() < 4)
		{
			return false;
		}
		for (int32 i = 0; i < 4; ++i)
		{
			if (!Spec.WheelMeshes[i].IsValid())
			{
				return false;
			}
			if (!StaticLoadObject(UStaticMesh::StaticClass(), nullptr, *Spec.WheelMeshes[i].ToString(), nullptr, LOAD_NoWarn | LOAD_Quiet))
			{
				return false;
			}
		}
		return true;
	}

	if (Spec.WheelMeshes.IsEmpty() || !Spec.WheelMeshes[0].IsValid())
	{
		return false;
	}
	return StaticLoadObject(UStaticMesh::StaticClass(), nullptr, *Spec.WheelMeshes[0].ToString(), nullptr, LOAD_NoWarn | LOAD_Quiet) != nullptr;
}

FName UWSPC2VehicleProfile::GetNextAvailableBuiltinPresetId(FName CurrentId)
{
	const TArray<FWSPC2VehicleProfileSpec>& Presets = GetBuiltinPresets();
	if (Presets.IsEmpty())
	{
		return NAME_None;
	}

	int32 StartIndex = 0;
	for (int32 i = 0; i < Presets.Num(); ++i)
	{
		if (Presets[i].PresetId == CurrentId)
		{
			StartIndex = i;
			break;
		}
	}

	for (int32 Step = 1; Step <= Presets.Num(); ++Step)
	{
		const FWSPC2VehicleProfileSpec& Candidate = Presets[(StartIndex + Step) % Presets.Num()];
		if (CanLoadPresetAssets(Candidate))
		{
			return Candidate.PresetId;
		}
	}

	return CurrentId;
}
