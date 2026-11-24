// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "UObject/SoftObjectPath.h"
#include "WSPC2VehicleProfile.generated.h"

/**
 * Driven wheel layout for Chaos simulation and drive-assist tuning.
 */
UENUM(BlueprintType)
enum class EWSPC2Drivetrain : uint8
{
	RWD = 0,
	FWD = 1,
	AWD = 2
};

/**
 * Engine bay placement used for the >30% engine block intrusion disable rule.
 */
UENUM(BlueprintType)
enum class EWSPC2EngineLayout : uint8
{
	Front = 0,
	Mid = 1,
	Rear = 2
};

/**
 * How a vehicle's wheel meshes are authored and oriented relative to the car chassis.
 */
UENUM(BlueprintType)
enum class EWSPC2WheelLayoutMode : uint8
{
	/** CitySampleVehicles convention: 4 separate wheel meshes baked in +X car space; Bounds.Origin is the hub. */
	BakedCarSpace = 0,

	/** Prepared GLB convention (Tools/vehicles/prepare_vehicles.py): +X forward body and origin-centered wheel (L=Yaw 0, R=Yaw 180). */
	CenteredOriginPlusX = 1,

	/** Legacy /Game/CrownVic convention: body rotated Yaw -90, origin-centered wheel (L=Yaw -90, R=Yaw +90). */
	CenteredOriginCrownVicLegacy = 2
};

/**
 * Full visual, collision, crew and handling-scale definition for a playable hero vehicle.
 * All mesh paths are optional soft references so git-ignored asset packs are never hard-required.
 */
USTRUCT(BlueprintType)
struct FWSPC2VehicleProfileSpec
{
	GENERATED_BODY()

	/** Short identifier used by CLI (-WSPC2Vehicle=<Id>), RPCs and console commands (e.g. Patrol, Undercover, Interceptor). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Identity")
	FName PresetId = FName("Patrol");

	/** Human-readable label shown in HUD and logs. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Identity")
	FText DisplayName = FText::FromString(TEXT("Patrol Cruiser"));

	/** Enables vehicle13_Car specific multi-stage windshield crack and police roof lightbar fracture slots. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Police")
	bool bIsPoliceCruiser = false;

	/** True when the chassis has a visible external roof lightbar; false hides external roof lens blocks (undercover/grille lights). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Police")
	bool bHasRoofLightbar = false;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Meshes")
	EWSPC2WheelLayoutMode WheelLayoutMode = EWSPC2WheelLayoutMode::BakedCarSpace;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Meshes")
	FSoftObjectPath BodyMesh;

	/** Optional body mesh with front brakes cut out (e.g. Tools/patrolcar/split_brakes.py output). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Meshes")
	FSoftObjectPath SplitBodyNoFrontBrakesMesh;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Meshes")
	FSoftObjectPath GlassMesh;

	/** Wheel meshes in FL, FR, RL, RR order. CenteredOrigin modes reuse index 0 if only 1 entry is provided. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Meshes")
	TArray<FSoftObjectPath> WheelMeshes;

	/** Optional front brake disc/caliper meshes in FL, FR order that steer with the front wheels without spinning. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Meshes")
	TArray<FSoftObjectPath> FrontBrakeMeshes;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Meshes")
	FRotator BodyRelativeRotation = FRotator::ZeroRotator;

	/** Car-space hub offsets (cm) in FL, FR, RL, RR order for CenteredOrigin modes. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Wheels")
	TArray<FVector> WheelOffsetsCm = {
		FVector(153.0f, -80.4f, 35.2f),
		FVector(153.0f, 80.4f, 35.2f),
		FVector(-140.6f, -83.3f, 35.2f),
		FVector(-140.6f, 83.3f, 35.2f)
	};

	/** Fallback wheel radius (cm) for CenteredOrigin modes when > 0; BakedCarSpace measures Bounds.BoxExtent.Z. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Wheels")
	float DefaultWheelRadiusCm = 35.1f;

	/** Optional staggered rear wheel radius (cm) when > 0; 0 reuses DefaultWheelRadiusCm. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Wheels")
	float RearWheelRadiusCm = 0.0f;

	/** True for tracked/armored military hulls whose tracks/wheels are baked into BodyMesh while Chaos simulates invisible corner hubs. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Wheels")
	bool bBakedRunningGear = false;

	/** When true, BodyCollision and CabinCollision are derived automatically from the loaded BodyMesh bounds. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Collision")
	bool bAutoComputeCollisionFromBody = true;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Collision")
	FVector BodyCollisionCenter = FVector(-8.3f, 0.0f, 63.0f);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Collision")
	FVector BodyCollisionExtent = FVector(274.0f, 96.0f, 33.0f);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Collision")
	FVector CabinCollisionCenter = FVector(-32.0f, 0.0f, 126.0f);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Collision")
	FVector CabinCollisionExtent = FVector(122.0f, 82.0f, 32.0f);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	FVector GunnerSeatLocation = FVector(5.0f, 78.0f, 120.0f);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	FVector LightBarCentre = FVector(-43.8f, 0.0f, 168.0f);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	float LightBarHalfSpacing = 38.4f;

	/** Optional UWSPC2CrewProfile with the officers posed for this body (Tools/crew); empty or missing: no one drawn. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	FSoftObjectPath CrewProfile;

	/** Optional steering wheel cut out of the body (car space, like the body); turned with the steering */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	FSoftObjectPath SteeringWheelMesh;

	/** Centre of the steering wheel and its axis (towards the driver), car space */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	FVector SteeringWheelCentre = FVector::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	FVector SteeringWheelAxis = FVector(-1.0f, 0.0f, 0.0f);

	/** How far the steering wheel turns at full lock, degrees each way */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	float SteeringWheelMaxDeg = 200.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Cameras")
	TArray<FVector> OnCarViewLocations;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Cameras")
	TArray<FString> OnCarViewNames;

	/** Multiplier applied on top of UWSPC2VehicleTuning::MassKg (1.0 preserves baseline patrol car mass). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Handling")
	float MassScale = 1.0f;

	/** Multiplier applied on top of UWSPC2VehicleTuning::MaxTorqueNm (1.0 preserves baseline patrol car torque). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Handling")
	float MaxTorqueScale = 1.0f;

	/** Chaos chassis height (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Handling")
	float ChassisHeightCm = 144.0f;

	/** Optional metadata & authentic real-world powertrain/suspension overrides (loaded from Config/WSPC2Vehicles.json). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	FString RealWorldCounterpart;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	FString RoleGroup;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	FString AudioProfile = TEXT("V8_Cruiser");

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	bool bUseRealWorldSpecs = false;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	EWSPC2Drivetrain Drivetrain = EWSPC2Drivetrain::RWD;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	EWSPC2EngineLayout EngineLayout = EWSPC2EngineLayout::Front;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld", meta = (Units = "kg"))
	float RealMassKg = 1850.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float RealHorsepower = 235.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld", meta = (Units = "Nm"))
	float RealMaxTorqueNm = 386.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float PeakTorqueRPM = 4000.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float IdleRPM = 720.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float MaxRPM = 5750.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float ChangeUpRPM = 5200.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float ChangeDownRPM = 1800.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	TArray<float> ForwardGearRatios;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float ReverseGearRatio = 2.95f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float FinalDriveRatio = 3.55f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float GearChangeTime = 0.25f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float ConverterStallRatio = 1.55f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float DragCoefficient = 0.35f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float DownforceCoefficient = 0.12f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	FVector CenterOfMassOffset = FVector(10.0f, 0.0f, 48.0f);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float FrontSpringRate = 225.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float RearSpringRate = 225.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float SuspensionDampingRatio = 0.54f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float SpringPreload = 50.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float SuspensionMaxRaise = 13.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float SuspensionMaxDrop = 14.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float FrontRollbarScaling = 0.30f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float RearRollbarScaling = 0.22f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float FrontFriction = 2.35f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float RearFriction = 2.42f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float FrontBrakeTorque = 4200.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float RearBrakeTorque = 2200.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float HandbrakeTorque = 10000.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	float MaxSteerAngle = 36.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "RealWorld")
	bool bABS = true;

	/** Damage resistance multiplier (<1 stronger frame/armor, 1.0 standard street metal, -1 auto from police flag). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Damage")
	float ArmorDamageScale = -1.0f;

	/** Underbody ride clearance (cm) used to compute critical chassis twist degrees where floorpan hits ground. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Damage", meta = (Units = "cm"))
	float GroundClearanceCm = 17.5f;

	/** Estimated local-space engine block AABB min/max (cm) for the >30% engine intrusion disable rule. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Damage")
	FVector EngineBlockMinCm = FVector(105.0f, -42.0f, 30.0f);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Damage")
	FVector EngineBlockMaxCm = FVector(220.0f, 42.0f, 88.0f);
};

/**
 * Reusable DataAsset describing a playable hero vehicle (native CitySampleVehicles or prepared GLB).
 * Also exposes built-in runtime presets for zero-asset-setup vehicle switching.
 */
UCLASS(BlueprintType)
class UWSPC2VehicleProfile : public UDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Vehicle")
	FWSPC2VehicleProfileSpec Profile;

	/** Returns all built-in hero presets (Patrol, Undercover, Interceptor, SUV, Pickup, SWATVan, CrownVic). */
	static const TArray<FWSPC2VehicleProfileSpec>& GetBuiltinPresets();

	/** Looks up a built-in preset by PresetId (case-insensitive). Returns nullptr if not found. */
	static const FWSPC2VehicleProfileSpec* FindBuiltinPreset(FName PresetId);

	/** Returns the next loadable built-in PresetId after CurrentId, cycling smoothly over installed packs. */
	static FName GetNextAvailableBuiltinPresetId(FName CurrentId);

	/** Returns the previous loadable built-in PresetId before CurrentId. */
	static FName GetPreviousAvailableBuiltinPresetId(FName CurrentId);

	/** Returns the first loadable PresetId of the next vehicle role category (Builtin/Fleet_Playable/Fleet_Bonus/Military/Mission/Traffic). */
	static FName GetNextCategoryPresetId(FName CurrentId);

	/** Collects all loadable PresetIds belonging to a RoleGroup ("Fleet_Playable", "Fleet_Bonus", "Military", "Mission", "Traffic", or "Builtin"). */
	static void GetPresetsByRoleGroup(const FString& RoleGroup, TArray<FName>& OutIds);

	/** Returns normalized category name ("Builtin" when RoleGroup is empty). */
	static FString GetNormalizedRoleGroup(const FWSPC2VehicleProfileSpec& Spec);

	/** Returns true if the spec's primary body mesh exists and loads cleanly without warnings. */
	static bool CanLoadPresetAssets(const FWSPC2VehicleProfileSpec& Spec);
};

/**
 * One key pose of an officer (Tools/crew/pose_crew.py --keys). For every bone of the body, in FWSPC2CrewMember::Bones
 * order: the move that carries the bone from its rest place in the character's own space to its posed place in the
 * car's space (posed = rest * move). The game blends neighbouring keys.
 */
USTRUCT(BlueprintType)
struct FWSPC2CrewPose
{
	GENERATED_BODY()

	/** Steer (driver), Seated, Handgun or Longgun (gunner) */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	FName Name;

	/** Steering wheel degrees (Steer, + = clockwise as the driver sees it) or aim yaw degrees (Handgun, Longgun) */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	float Param = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	TArray<FTransform> Moves;

	/** Where the weapon's grip is (weapon space: x along the barrel, z up), car space; Handgun and Longgun only */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	FTransform Grip;
};

/**
 * One officer drawn in the car, posed at run time: the crowd's skeletal body and outfit parts (the first part leads,
 * the others follow its pose), a face and hair carried rigidly by the head. Cosmetic only; built by
 * Tools/crew/build_crew_preview.py.
 */
USTRUCT(BlueprintType)
struct FWSPC2CrewMember
{
	GENERATED_BODY()

	/** Driver or Gunner */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	FName Role;

	/** Static mesh of the posed body and uniform, in car space (cm, +X forward): the preview map's still officer */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	FSoftObjectPath BodyMesh;

	/** Skeletal meshes of the body (first) and the outfit (shirt, trousers, shoes) sharing its skeleton */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	TArray<FSoftObjectPath> BodyParts;

	/** Skeletal face mesh, drawn in its rest pose */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	FSoftObjectPath FaceMesh;

	/** Hair cards (static mesh) and their material */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	FSoftObjectPath HairMesh;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	FSoftObjectPath HairMaterial;

	/** Where the face and the hair go in the still pose, car space (preview map) */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	FTransform HeadTransform;

	/** Bone names, in the order of every pose's Moves */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	TArray<FName> Bones;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	TArray<FWSPC2CrewPose> Poses;
};

/** The officers posed for one car body. Lives with the crew assets (git-ignored, optional). */
UCLASS(BlueprintType)
class UWSPC2CrewProfile : public UDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	TArray<FWSPC2CrewMember> Members;

	/** Uniform colours: a material whose name is in SwapFrom is drawn with the SwapTo at the same index */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	TArray<FName> SwapFrom;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crew")
	TArray<FSoftObjectPath> SwapTo;
};
