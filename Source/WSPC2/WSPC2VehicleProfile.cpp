// Copyright Epic Games, Inc. All Rights Reserved.

#include "WSPC2VehicleProfile.h"
#include "WSPC2.h"
#include "Engine/StaticMesh.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	FVector ParseJsonVec3(const TArray<TSharedPtr<FJsonValue>>* Arr, const FVector& DefaultVal)
	{
		if (!Arr || Arr->Num() < 3)
		{
			return DefaultVal;
		}
		return FVector(
			static_cast<float>((*Arr)[0]->AsNumber()),
			static_cast<float>((*Arr)[1]->AsNumber()),
			static_cast<float>((*Arr)[2]->AsNumber()));
	}

	void AppendCatalogPresetsFromJson(TArray<FWSPC2VehicleProfileSpec>& Presets)
	{
		const FString JsonPath = FPaths::ProjectConfigDir() / TEXT("WSPC2Vehicles.json");
		FString JsonText;
		if (!FFileHelper::LoadFileToString(JsonText, *JsonPath))
		{
			return;
		}

		TSharedPtr<FJsonObject> RootObj;
		TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonText);
		if (!FJsonSerializer::Deserialize(Reader, RootObj) || !RootObj.IsValid())
		{
			UE_LOG(LogWSPC2, Warning, TEXT("VehicleProfile: failed to parse %s"), *JsonPath);
			return;
		}

		const TArray<TSharedPtr<FJsonValue>>* VehiclesArr = nullptr;
		if (!RootObj->TryGetArrayField(TEXT("vehicles"), VehiclesArr) || !VehiclesArr)
		{
			return;
		}

		int32 Added = 0;
		for (const TSharedPtr<FJsonValue>& Val : *VehiclesArr)
		{
			const TSharedPtr<FJsonObject> Obj = Val.IsValid() ? Val->AsObject() : nullptr;
			if (!Obj.IsValid())
			{
				continue;
			}

			FString IdStr;
			if (!Obj->TryGetStringField(TEXT("id"), IdStr) || IdStr.IsEmpty())
			{
				continue;
			}

			FWSPC2VehicleProfileSpec Spec;
			Spec.PresetId = FName(*IdStr);
			FString DispName;
			Obj->TryGetStringField(TEXT("display_name"), DispName);
			Spec.DisplayName = FText::FromString(DispName.IsEmpty() ? IdStr : DispName);
			Obj->TryGetStringField(TEXT("role_group"), Spec.RoleGroup);

			Spec.WheelLayoutMode = EWSPC2WheelLayoutMode::CenteredOriginPlusX;
			Spec.BodyRelativeRotation = FRotator::ZeroRotator;
			Spec.bAutoComputeCollisionFromBody = true;

			FString MeshPath;
			if (Obj->TryGetStringField(TEXT("body_mesh"), MeshPath) && !MeshPath.IsEmpty())
			{
				Spec.BodyMesh = FSoftObjectPath(MeshPath);
			}
			if (Obj->TryGetStringField(TEXT("glass_mesh"), MeshPath) && !MeshPath.IsEmpty())
			{
				Spec.GlassMesh = FSoftObjectPath(MeshPath);
			}
			if (Obj->TryGetStringField(TEXT("steering_wheel_mesh"), MeshPath) && !MeshPath.IsEmpty())
			{
				Spec.SteeringWheelMesh = FSoftObjectPath(MeshPath);
			}

			const TArray<TSharedPtr<FJsonValue>>* StrArr = nullptr;
			if (Obj->TryGetArrayField(TEXT("wheel_meshes"), StrArr) && StrArr)
			{
				for (const TSharedPtr<FJsonValue>& WVal : *StrArr)
				{
					const FString WPath = WVal->AsString();
					if (!WPath.IsEmpty())
					{
						Spec.WheelMeshes.Add(FSoftObjectPath(WPath));
					}
				}
			}
			if (Obj->TryGetArrayField(TEXT("front_brake_meshes"), StrArr) && StrArr)
			{
				for (const TSharedPtr<FJsonValue>& BVal : *StrArr)
				{
					const FString BPath = BVal->AsString();
					if (!BPath.IsEmpty())
					{
						Spec.FrontBrakeMeshes.Add(FSoftObjectPath(BPath));
					}
				}
			}

			const TArray<TSharedPtr<FJsonValue>>* VecArr = nullptr;
			if (Obj->TryGetArrayField(TEXT("steering_wheel_centre_cm"), VecArr))
			{
				Spec.SteeringWheelCentre = ParseJsonVec3(VecArr, FVector::ZeroVector);
			}
			if (Obj->TryGetArrayField(TEXT("steering_wheel_axis"), VecArr))
			{
				Spec.SteeringWheelAxis = ParseJsonVec3(VecArr, FVector(-0.94f, 0.0f, 0.34f)).GetSafeNormal();
			}
			double Num = 0.0;
			if (Obj->TryGetNumberField(TEXT("steering_wheel_max_deg"), Num))
			{
				Spec.SteeringWheelMaxDeg = static_cast<float>(Num);
			}

			if (Obj->TryGetArrayField(TEXT("wheel_offsets_cm"), StrArr) && StrArr && StrArr->Num() >= 4)
			{
				Spec.WheelOffsetsCm.SetNum(4);
				for (int32 w = 0; w < 4; ++w)
				{
					const TArray<TSharedPtr<FJsonValue>>& WCoords = (*StrArr)[w]->AsArray();
					Spec.WheelOffsetsCm[w] = ParseJsonVec3(&WCoords, Spec.WheelOffsetsCm[w]);
				}
			}

			if (Obj->TryGetNumberField(TEXT("wheel_radius_cm"), Num))
			{
				Spec.DefaultWheelRadiusCm = static_cast<float>(Num);
			}
			if (Obj->TryGetNumberField(TEXT("rear_wheel_radius_cm"), Num))
			{
				Spec.RearWheelRadiusCm = static_cast<float>(Num);
			}
			bool BoolVal = false;
			if (Obj->TryGetBoolField(TEXT("baked_running_gear"), BoolVal))
			{
				Spec.bBakedRunningGear = BoolVal;
			}
			if (Obj->TryGetNumberField(TEXT("chassis_height_cm"), Num))
			{
				Spec.ChassisHeightCm = static_cast<float>(Num);
			}
			if (Obj->TryGetNumberField(TEXT("ground_clearance_cm"), Num))
			{
				Spec.GroundClearanceCm = static_cast<float>(Num);
			}
			if (Obj->TryGetArrayField(TEXT("engine_block_min_cm"), VecArr))
			{
				Spec.EngineBlockMinCm = ParseJsonVec3(VecArr, Spec.EngineBlockMinCm);
			}
			if (Obj->TryGetArrayField(TEXT("engine_block_max_cm"), VecArr))
			{
				Spec.EngineBlockMaxCm = ParseJsonVec3(VecArr, Spec.EngineBlockMaxCm);
			}
			if (Obj->TryGetArrayField(TEXT("lightbar_centre_cm"), VecArr))
			{
				Spec.LightBarCentre = ParseJsonVec3(VecArr, Spec.LightBarCentre);
			}
			if (Obj->TryGetArrayField(TEXT("on_car_views_cm"), StrArr) && StrArr)
			{
				Spec.OnCarViewLocations.Reset();
				for (const TSharedPtr<FJsonValue>& VVal : *StrArr)
				{
					const TArray<TSharedPtr<FJsonValue>>& Coords = VVal->AsArray();
					Spec.OnCarViewLocations.Add(ParseJsonVec3(&Coords, FVector::ZeroVector));
				}
				Spec.OnCarViewNames = { TEXT("Dashboard"), TEXT("Hood"), TEXT("Bumper") };
			}

			const TSharedPtr<FJsonObject>* RealObjPtr = nullptr;
			if (Obj->TryGetObjectField(TEXT("real_specs"), RealObjPtr) && RealObjPtr && RealObjPtr->IsValid())
			{
				const TSharedPtr<FJsonObject>& RS = *RealObjPtr;
				Spec.bUseRealWorldSpecs = true;
				RS->TryGetStringField(TEXT("real_world_counterpart"), Spec.RealWorldCounterpart);
				RS->TryGetStringField(TEXT("audio_profile"), Spec.AudioProfile);

				FString DriveStr;
				if (RS->TryGetStringField(TEXT("drivetrain"), DriveStr))
				{
					Spec.Drivetrain = DriveStr.Equals(TEXT("FWD"), ESearchCase::IgnoreCase) ? EWSPC2Drivetrain::FWD
						: DriveStr.Equals(TEXT("AWD"), ESearchCase::IgnoreCase) ? EWSPC2Drivetrain::AWD
						: EWSPC2Drivetrain::RWD;
				}
				FString LayoutStr;
				if (RS->TryGetStringField(TEXT("engine_layout"), LayoutStr))
				{
					Spec.EngineLayout = LayoutStr.Equals(TEXT("Mid"), ESearchCase::IgnoreCase) ? EWSPC2EngineLayout::Mid
						: LayoutStr.Equals(TEXT("Rear"), ESearchCase::IgnoreCase) ? EWSPC2EngineLayout::Rear
						: EWSPC2EngineLayout::Front;
				}

				if (RS->TryGetBoolField(TEXT("is_police"), BoolVal)) { Spec.bIsPoliceCruiser = false; } // citysample-specific mesh slot flag stays false
				if (RS->TryGetBoolField(TEXT("has_roof_lightbar"), BoolVal)) { Spec.bHasRoofLightbar = BoolVal; }
				if (RS->TryGetNumberField(TEXT("mass_kg"), Num)) { Spec.RealMassKg = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("horsepower"), Num)) { Spec.RealHorsepower = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("max_torque_nm"), Num)) { Spec.RealMaxTorqueNm = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("peak_torque_rpm"), Num)) { Spec.PeakTorqueRPM = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("idle_rpm"), Num)) { Spec.IdleRPM = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("max_rpm"), Num)) { Spec.MaxRPM = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("change_up_rpm"), Num)) { Spec.ChangeUpRPM = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("change_down_rpm"), Num)) { Spec.ChangeDownRPM = static_cast<float>(Num); }
				if (RS->TryGetArrayField(TEXT("gear_ratios"), StrArr) && StrArr)
				{
					Spec.ForwardGearRatios.Reset();
					for (const TSharedPtr<FJsonValue>& GVal : *StrArr)
					{
						Spec.ForwardGearRatios.Add(static_cast<float>(GVal->AsNumber()));
					}
				}
				if (RS->TryGetNumberField(TEXT("reverse_gear_ratio"), Num)) { Spec.ReverseGearRatio = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("final_drive_ratio"), Num)) { Spec.FinalDriveRatio = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("gear_change_time"), Num)) { Spec.GearChangeTime = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("converter_stall_ratio"), Num)) { Spec.ConverterStallRatio = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("drag_cd"), Num)) { Spec.DragCoefficient = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("downforce_coef"), Num)) { Spec.DownforceCoefficient = static_cast<float>(Num); }
				if (RS->TryGetArrayField(TEXT("com_offset_cm"), VecArr)) { Spec.CenterOfMassOffset = ParseJsonVec3(VecArr, Spec.CenterOfMassOffset); }
				if (RS->TryGetNumberField(TEXT("front_spring_rate"), Num)) { Spec.FrontSpringRate = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("rear_spring_rate"), Num)) { Spec.RearSpringRate = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("damping_ratio"), Num)) { Spec.SuspensionDampingRatio = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("spring_preload"), Num)) { Spec.SpringPreload = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("max_raise_cm"), Num)) { Spec.SuspensionMaxRaise = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("max_drop_cm"), Num)) { Spec.SuspensionMaxDrop = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("front_rollbar"), Num)) { Spec.FrontRollbarScaling = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("rear_rollbar"), Num)) { Spec.RearRollbarScaling = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("front_friction"), Num)) { Spec.FrontFriction = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("rear_friction"), Num)) { Spec.RearFriction = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("front_brake_torque"), Num)) { Spec.FrontBrakeTorque = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("rear_brake_torque"), Num)) { Spec.RearBrakeTorque = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("handbrake_torque"), Num)) { Spec.HandbrakeTorque = static_cast<float>(Num); }
				if (RS->TryGetNumberField(TEXT("max_steer_angle"), Num)) { Spec.MaxSteerAngle = static_cast<float>(Num); }
				if (RS->TryGetBoolField(TEXT("abs"), BoolVal)) { Spec.bABS = BoolVal; }
				if (RS->TryGetNumberField(TEXT("armor_damage_scale"), Num)) { Spec.ArmorDamageScale = static_cast<float>(Num); }
			}

			int32 ExistingIdx = INDEX_NONE;
			for (int32 i = 0; i < Presets.Num(); ++i)
			{
				if (Presets[i].PresetId == Spec.PresetId)
				{
					ExistingIdx = i;
					break;
				}
			}
			if (ExistingIdx != INDEX_NONE)
			{
				Presets[ExistingIdx] = MoveTemp(Spec);
			}
			else
			{
				Presets.Add(MoveTemp(Spec));
			}
			++Added;
		}
		UE_LOG(LogWSPC2, Log, TEXT("VehicleProfile: loaded %d catalog presets from %s (total=%d)"), Added, *JsonPath, Presets.Num());
	}
}

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

		AppendCatalogPresetsFromJson(Presets);
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

	if (Spec.bBakedRunningGear)
	{
		return true;
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

FString UWSPC2VehicleProfile::GetNormalizedRoleGroup(const FWSPC2VehicleProfileSpec& Spec)
{
	return Spec.RoleGroup.IsEmpty() ? FString(TEXT("Builtin")) : Spec.RoleGroup;
}

static FName FindAvailablePresetDirectional(const TArray<FWSPC2VehicleProfileSpec>& Presets, FName CurrentId, int32 StepDir)
{
	if (Presets.IsEmpty())
	{
		return NAME_None;
	}

	const int32 Num = Presets.Num();
	int32 StartIndex = 0;
	for (int32 i = 0; i < Num; ++i)
	{
		if (Presets[i].PresetId == CurrentId)
		{
			StartIndex = i;
			break;
		}
	}

	const int32 Dir = (StepDir >= 0) ? 1 : -1;
	for (int32 Step = 1; Step <= Num; ++Step)
	{
		const int32 Idx = ((StartIndex + Dir * Step) % Num + Num) % Num;
		const FWSPC2VehicleProfileSpec& Candidate = Presets[Idx];
		if (UWSPC2VehicleProfile::CanLoadPresetAssets(Candidate))
		{
			return Candidate.PresetId;
		}
	}
	return CurrentId;
}

FName UWSPC2VehicleProfile::GetNextAvailableBuiltinPresetId(FName CurrentId)
{
	return FindAvailablePresetDirectional(GetBuiltinPresets(), CurrentId, 1);
}

FName UWSPC2VehicleProfile::GetPreviousAvailableBuiltinPresetId(FName CurrentId)
{
	return FindAvailablePresetDirectional(GetBuiltinPresets(), CurrentId, -1);
}

FName UWSPC2VehicleProfile::GetNextCategoryPresetId(FName CurrentId)
{
	static const TCHAR* CategoryOrder[] = {
		TEXT("Builtin"),
		TEXT("Fleet_Playable"),
		TEXT("Fleet_Bonus"),
		TEXT("Military"),
		TEXT("Mission"),
		TEXT("Traffic")
	};
	constexpr int32 NumCats = UE_ARRAY_COUNT(CategoryOrder);

	const FWSPC2VehicleProfileSpec* CurSpec = FindBuiltinPreset(CurrentId);
	const FString CurCat = CurSpec ? GetNormalizedRoleGroup(*CurSpec) : FString(TEXT("Builtin"));
	int32 StartCat = 0;
	for (int32 c = 0; c < NumCats; ++c)
	{
		if (CurCat.Equals(CategoryOrder[c], ESearchCase::IgnoreCase))
		{
			StartCat = c;
			break;
		}
	}

	const TArray<FWSPC2VehicleProfileSpec>& Presets = GetBuiltinPresets();
	for (int32 Step = 1; Step <= NumCats; ++Step)
	{
		const FString TargetCat(CategoryOrder[(StartCat + Step) % NumCats]);
		for (const FWSPC2VehicleProfileSpec& Candidate : Presets)
		{
			if (GetNormalizedRoleGroup(Candidate).Equals(TargetCat, ESearchCase::IgnoreCase) && CanLoadPresetAssets(Candidate))
			{
				return Candidate.PresetId;
			}
		}
	}
	return CurrentId;
}

void UWSPC2VehicleProfile::GetPresetsByRoleGroup(const FString& RoleGroup, TArray<FName>& OutIds)
{
	OutIds.Reset();
	for (const FWSPC2VehicleProfileSpec& Spec : GetBuiltinPresets())
	{
		if (GetNormalizedRoleGroup(Spec).Equals(RoleGroup, ESearchCase::IgnoreCase) && CanLoadPresetAssets(Spec))
		{
			OutIds.Add(Spec.PresetId);
		}
	}
}
