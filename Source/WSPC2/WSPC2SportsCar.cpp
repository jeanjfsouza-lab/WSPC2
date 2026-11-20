// Copyright Epic Games, Inc. All Rights Reserved.


#include "WSPC2SportsCar.h"
#include "WSPC2PatrolWheels.h"
#include "WSPC2VehicleTuning.h"
#include "WSPC2VehicleDamageComponent.h"
#include "WSPC2CrewComponent.h"
#include "WSPC2Gunnery.h"
#include "WSPC2.h"
#include "ChaosWheeledVehicleMovementComponent.h"
#include "ChaosVehicleWheel.h"
#include "Components/BoxComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkinnedAsset.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "PhysicsEngine/BodyInstance.h"
#include "PhysicsEngine/BodySetup.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "GameFramework/SpringArmComponent.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Net/UnrealNetwork.h"
#include "TimerManager.h"

namespace WSPC2Sedan
{
	const FName WheelBones[4] = { FName("Phys_Wheel_FL"), FName("Phys_Wheel_FR"), FName("Phys_Wheel_BL"), FName("Phys_Wheel_BR") };

	UStaticMesh* LoadOptionalMesh(const FSoftObjectPath& Path)
	{
		if (!Path.IsValid())
		{
			return nullptr;
		}
		return Cast<UStaticMesh>(StaticLoadObject(UStaticMesh::StaticClass(), nullptr, *Path.ToString(), nullptr, LOAD_NoWarn | LOAD_Quiet));
	}
}

AWSPC2SportsCar::AWSPC2SportsCar()
{
	// Set up the chassis
	GetChaosVehicleMovement()->ChassisHeight = 144.0f;

	// Set up the wheels. The bone names belong to the physics skeleton.
	GetChaosVehicleMovement()->bLegacyWheelFrictionPosition = true;
	GetChaosVehicleMovement()->WheelSetups.SetNum(4);

	for (int32 Index = 0; Index < 4; ++Index)
	{
		GetChaosVehicleMovement()->WheelSetups[Index].BoneName = WSPC2Sedan::WheelBones[Index];
	}

	// Vehicle body, transparent glass/lightbar, and 4 wheels
	SedanBody = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Sedan Body"));
	SedanBody->SetupAttachment(GetMesh());
	SedanBody->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	SedanGlass = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Sedan Glass"));
	SedanGlass->SetupAttachment(GetMesh());
	SedanGlass->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	static const TCHAR* WheelNames[4] = { TEXT("Sedan Wheel FL"), TEXT("Sedan Wheel FR"), TEXT("Sedan Wheel RL"), TEXT("Sedan Wheel RR") };

	for (int32 Index = 0; Index < 4; ++Index)
	{
		UStaticMeshComponent* Wheel = CreateDefaultSubobject<UStaticMeshComponent>(WheelNames[Index]);
		Wheel->SetupAttachment(GetMesh());
		Wheel->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		SedanWheels.Add(Wheel);
	}

	static const TCHAR* BrakeNames[2] = { TEXT("Brake FL"), TEXT("Brake FR") };

	for (int32 Index = 0; Index < 2; ++Index)
	{
		UStaticMeshComponent* Brake = CreateDefaultSubobject<UStaticMeshComponent>(BrakeNames[Index]);
		Brake->SetupAttachment(GetMesh());
		Brake->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Brake->SetVisibility(false);
		FrontBrakes.Add(Brake);
	}

	// Collision boxes sized to the patrol cruiser; welded onto GetMesh()'s Chaos rigid body
	BodyCollision = CreateDefaultSubobject<UBoxComponent>(TEXT("Body Collision"));
	BodyCollision->SetupAttachment(GetMesh());
	BodyCollision->SetRelativeLocation(FVector(-8.3f, 0.0f, 63.0f));
	BodyCollision->SetBoxExtent(FVector(274.0f, 96.0f, 33.0f));
	BodyCollision->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	CabinCollision = CreateDefaultSubobject<UBoxComponent>(TEXT("Cabin Collision"));
	CabinCollision->SetupAttachment(GetMesh());
	CabinCollision->SetRelativeLocation(FVector(-32.0f, 0.0f, 126.0f));
	CabinCollision->SetBoxExtent(FVector(122.0f, 82.0f, 32.0f));
	CabinCollision->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	// The officers (built and posed by the crew component from the preset's profile) and the steering wheel
	Crew = CreateDefaultSubobject<UWSPC2CrewComponent>(TEXT("Crew"));
	Crew->SetupAttachment(GetMesh());

	SteeringWheel = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Steering Wheel"));
	SteeringWheel->SetupAttachment(GetMesh());
	SteeringWheel->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	SteeringWheel->SetVisibility(false);

	ApplyTuning();
}

void AWSPC2SportsCar::MountCrew(const FWSPC2VehicleProfileSpec& Spec)
{
	Crew->SetProfile(Spec.CrewProfile);

	UStaticMesh* Wheel = WSPC2Sedan::LoadOptionalMesh(Spec.SteeringWheelMesh);
	SteeringWheel->SetStaticMesh(Wheel);
	SteeringWheel->SetRelativeTransform(FTransform::Identity);
	SteeringWheel->SetVisibility(Wheel != nullptr);
	SteeringWheelCentre = Spec.SteeringWheelCentre;
	SteeringWheelAxis = Spec.SteeringWheelAxis.GetSafeNormal();
	SteeringWheelMaxDeg = Wheel ? Spec.SteeringWheelMaxDeg : 0.0f;
}

void AWSPC2SportsCar::AddCrewToHiddenList(int32 Slot, TSet<FPrimitiveComponentId>& HiddenComponents) const
{
	Crew->AddToHiddenList(Slot, HiddenComponents);
}

bool AWSPC2SportsCar::GetGunnerMuzzle(FVector& OutLocation, FVector& OutDirection) const
{
	return Crew->GetMuzzle(OutLocation, OutDirection);
}

void AWSPC2SportsCar::UpdateCrewAndWheel(float Delta)
{
	// test hooks for pictures: -WSPC2CrewSteer=<deg>, -WSPC2CrewWeapon=Pistol|Shotgun|Rifle, -WSPC2CrewAim=<yaw>,<pitch>
	static float ForcedSteer = 0.0f, ForcedYaw = 0.0f, ForcedPitch = 0.0f;
	static bool bForcedSteer = FParse::Value(FCommandLine::Get(), TEXT("WSPC2CrewSteer="), ForcedSteer);
	static FString ForcedWeaponName;
	static bool bForcedWeapon = FParse::Value(FCommandLine::Get(), TEXT("WSPC2CrewWeapon="), ForcedWeaponName);
	static FString ForcedAimText;
	static bool bForcedAim = FParse::Value(FCommandLine::Get(), TEXT("WSPC2CrewAim="), ForcedAimText, false);   // "yaw,pitch": not cut at the comma
	if (bForcedAim && ForcedYaw == 0.0f && ForcedPitch == 0.0f)
	{
		FString YawText, PitchText;
		if (ForcedAimText.Split(TEXT(","), &YawText, &PitchText))
		{
			ForcedYaw = FCString::Atof(*YawText);
			ForcedPitch = FCString::Atof(*PitchText);
		}
	}

	// the steering wheel turns with the steering (as the front wheels do, a touch behind)
	const float Input = GetChaosVehicleMovement() ? GetChaosVehicleMovement()->GetSteeringInput() : 0.0f;
	DrawnSteering = FMath::FInterpTo(DrawnSteering, Input, Delta, 12.0f);
	const float WheelDeg = bForcedSteer ? ForcedSteer : DrawnSteering * SteeringWheelMaxDeg;

	if (SteeringWheel->IsVisible() && !SteeringWheelAxis.IsNearlyZero())
	{
		// clockwise as the driver sees it is a positive turn about the axis that points at him (Unreal's handedness)
		const FQuat Turn(SteeringWheelAxis, FMath::DegreesToRadians(WheelDeg));
		SteeringWheel->SetRelativeLocationAndRotation(SteeringWheelCentre - Turn.RotateVector(SteeringWheelCentre), Turn);
	}

	EWSPC2Weapon Weapon = GetGunnery() ? GetGunnery()->GetWeapon() : EWSPC2Weapon::None;
	if (bForcedWeapon)
	{
		Weapon = ForcedWeaponName == TEXT("Pistol") ? EWSPC2Weapon::Pistol : ForcedWeaponName == TEXT("Shotgun") ? EWSPC2Weapon::Shotgun
			: ForcedWeaponName == TEXT("Rifle") ? EWSPC2Weapon::Rifle : EWSPC2Weapon::None;
	}
	const bool bOut = GetGunnery() ? !GetGunnery()->IsRetracted() : true;
	const FVector2D Aim = bForcedAim ? FVector2D(ForcedYaw, ForcedPitch) : (GetGunnery() ? GetGunnery()->GetDisplayAim() : FVector2D(20.0f, 0.0f));
	Crew->SetDriveState(WheelDeg, Weapon, bOut, Aim);
}

void AWSPC2SportsCar::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AWSPC2SportsCar, ActiveVehiclePresetId);
}

void AWSPC2SportsCar::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);

	if (bUsingSedanBody)
	{
		HideTemplateBodyParts();
	}
}

void AWSPC2SportsCar::PreRegisterAllComponents()
{
	Super::PreRegisterAllComponents();

	// Allow automated tests or launches to pick a hero vehicle via -WSPC2Vehicle=<PresetId>
	FString CliPreset;
	if (!bPresetOverrideActive && FParse::Value(FCommandLine::Get(), TEXT("WSPC2Vehicle="), CliPreset) && !CliPreset.IsEmpty())
	{
		const FName RequestedId(*CliPreset);
		if (UWSPC2VehicleProfile::FindBuiltinPreset(RequestedId))
		{
			ActiveVehiclePresetId = RequestedId;
			bPresetOverrideActive = true;
		}
		else
		{
			UE_LOG(LogWSPC2, Warning, TEXT("Unknown -WSPC2Vehicle=%s; falling back to %s"), *CliPreset, *ActiveVehiclePresetId.ToString());
		}
	}

	// Mount profile first so class mass/torque/height scales are active when ApplyTuning builds the physics setup
	ApplyVehicleProfile(false);
	ApplyTuning();
}

void AWSPC2SportsCar::HideTemplateBodyParts()
{
	TInlineComponentArray<UStaticMeshComponent*> StaticMeshes(this);

	for (UStaticMeshComponent* Component : StaticMeshes)
	{
		// only the template's own parts: the hero chassis, its brakes, the officers and the light bar lenses (named
		// "Siren ...") stay
		const bool bOurs = Component == SedanBody || Component == SedanGlass || SedanWheels.Contains(Component) || FrontBrakes.Contains(Component)
			|| Component == SteeringWheel || Component->ComponentHasTag(TEXT("WSPC2Crew")) || Component->GetName().StartsWith(TEXT("Siren"));

		if (!bOurs)
		{
			Component->SetVisibility(false);
			Component->SetHiddenInGame(true);
		}
	}
}

void AWSPC2SportsCar::BeginPlay()
{
	Super::BeginPlay();

	ApplyWheelTuning();

	if (bUsingSedanBody)
	{
		HideTemplateBodyParts();
		DisableTemplateBodyCollision();
		ApplyCenterOfMassOverride();
		ConfigureDamageRig();

		FTimerHandle LogTimer;
		GetWorld()->GetTimerManager().SetTimer(LogTimer, this, &AWSPC2SportsCar::LogWheelLayout, 3.0f, false);
	}
}

void AWSPC2SportsCar::ApplyCenterOfMassOverride()
{
	if (UChaosWheeledVehicleMovementComponent* Movement = GetChaosVehicleMovement())
	{
		const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
		if (FBodyInstance* BI = GetMesh() ? GetMesh()->GetBodyInstance() : nullptr)
		{
			if (Tuning && Tuning->bOverrideCenterOfMass && BI->IsValidBodyInstance())
			{
				const FVector WorldDesiredCoM = GetActorTransform().TransformPosition(Tuning->CenterOfMassOffset);
				Movement->bEnableCenterOfMassOverride = true;
				Movement->CenterOfMassOverride = BI->GetUnrealWorldTransform().InverseTransformPosition(WorldDesiredCoM);
			}

			// Re-apply Chaos mass and CoM overrides after removing template wheel bodies.
			BI->UpdateMassProperties();
		}
	}
}

void AWSPC2SportsCar::ConfigureDamageRig()
{
	if (UWSPC2VehicleDamageComponent* DamageComp = GetVehicleDamage())
	{
		FVector Hubs[4];
		for (int32 i = 0; i < 4; ++i)
		{
			Hubs[i] = GetSedanWheelPosition(i);
		}
		DamageComp->SetBaselineTorqueScale(ActiveMaxTorqueScale);
		DamageComp->SetupDamageRig(GetMesh(), SedanBody, SedanGlass, SedanWheels, Hubs, WheelRadii, bUsingPoliceCruiserMesh);
	}
}

bool AWSPC2SportsCar::SetVehiclePreset(FName NewPresetId)
{
	if (!HasAuthority())
	{
		return false;
	}

	const FWSPC2VehicleProfileSpec* Spec = UWSPC2VehicleProfile::FindBuiltinPreset(NewPresetId);
	if (!Spec)
	{
		UE_LOG(LogWSPC2, Warning, TEXT("SetVehiclePreset: unknown preset '%s'"), *NewPresetId.ToString());
		return false;
	}

	if (!UWSPC2VehicleProfile::CanLoadPresetAssets(*Spec))
	{
		UE_LOG(LogWSPC2, Warning, TEXT("SetVehiclePreset: assets for preset '%s' are not installed"), *NewPresetId.ToString());
		return false;
	}

	bPresetOverrideActive = true;
	ActiveVehiclePresetId = Spec->PresetId;
	OnRep_ActiveVehiclePresetId();
	ForceNetUpdate();
	return true;
}

FName AWSPC2SportsCar::CycleVehiclePreset()
{
	if (!HasAuthority())
	{
		return ActiveVehiclePresetId;
	}

	const FName NextId = UWSPC2VehicleProfile::GetNextAvailableBuiltinPresetId(ActiveVehiclePresetId);
	if (!NextId.IsNone() && NextId != ActiveVehiclePresetId)
	{
		SetVehiclePreset(NextId);
	}
	return ActiveVehiclePresetId;
}

void AWSPC2SportsCar::OnRep_ActiveVehiclePresetId()
{
	bPresetOverrideActive = true;
	if (HasActorBegunPlay())
	{
		ApplyVehicleProfile(true);
	}
}

FVector AWSPC2SportsCar::GetSedanWheelPosition(int32 Index) const
{
	if (Index >= 0 && Index < 4)
	{
		return WheelMeshOrigins[Index];
	}
	return FVector::ZeroVector;
}

bool AWSPC2SportsCar::TryMountProfileSpec(const FWSPC2VehicleProfileSpec& Spec)
{
	UStaticMesh* PrimaryBody = WSPC2Sedan::LoadOptionalMesh(Spec.BodyMesh);
	if (!PrimaryBody)
	{
		return false;
	}

	UStaticMesh* Wheels[4] = { nullptr, nullptr, nullptr, nullptr };
	if (Spec.WheelLayoutMode == EWSPC2WheelLayoutMode::BakedCarSpace)
	{
		if (Spec.WheelMeshes.Num() < 4)
		{
			return false;
		}
		for (int32 i = 0; i < 4; ++i)
		{
			Wheels[i] = WSPC2Sedan::LoadOptionalMesh(Spec.WheelMeshes[i]);
			if (!Wheels[i])
			{
				return false;
			}
		}
	}
	else
	{
		UStaticMesh* BaseWheel = Spec.WheelMeshes.IsValidIndex(0) ? WSPC2Sedan::LoadOptionalMesh(Spec.WheelMeshes[0]) : nullptr;
		if (!BaseWheel)
		{
			return false;
		}
		for (int32 i = 0; i < 4; ++i)
		{
			UStaticMesh* OverrideWheel = (i > 0 && Spec.WheelMeshes.IsValidIndex(i)) ? WSPC2Sedan::LoadOptionalMesh(Spec.WheelMeshes[i]) : nullptr;
			Wheels[i] = OverrideWheel ? OverrideWheel : BaseWheel;
		}
	}

	// Optional split body + steering front brake discs/calipers
	UStaticMesh* SplitBody = WSPC2Sedan::LoadOptionalMesh(Spec.SplitBodyNoFrontBrakesMesh);
	UStaticMesh* LoadedBrakes[2] = {
		Spec.FrontBrakeMeshes.IsValidIndex(0) ? WSPC2Sedan::LoadOptionalMesh(Spec.FrontBrakeMeshes[0]) : nullptr,
		Spec.FrontBrakeMeshes.IsValidIndex(1) ? WSPC2Sedan::LoadOptionalMesh(Spec.FrontBrakeMeshes[1]) : nullptr
	};
	const bool bHaveBothBrakes = LoadedBrakes[0] && LoadedBrakes[1];
	const bool bUseSplitBody = (SplitBody != nullptr) && bHaveBothBrakes;
	const bool bMountBrakes = bHaveBothBrakes && (!Spec.SplitBodyNoFrontBrakesMesh.IsValid() || bUseSplitBody);

	UStaticMesh* MountedBodyMesh = bUseSplitBody ? SplitBody : PrimaryBody;
	UStaticMesh* MountedGlassMesh = WSPC2Sedan::LoadOptionalMesh(Spec.GlassMesh);

	// Reset relative transforms before setting meshes so previous damage deformations never leak across profiles
	SedanBody->SetRelativeTransform(FTransform(Spec.BodyRelativeRotation, FVector::ZeroVector, FVector::OneVector));
	SedanBody->SetStaticMesh(MountedBodyMesh);
	SedanBody->EmptyOverrideMaterials();
	SedanBody->SetVisibility(true);
	SedanBody->SetHiddenInGame(false);

	SedanGlass->SetRelativeTransform(FTransform(Spec.BodyRelativeRotation, FVector::ZeroVector, FVector::OneVector));
	SedanGlass->SetStaticMesh(MountedGlassMesh);
	SedanGlass->EmptyOverrideMaterials();
	SedanGlass->SetVisibility(MountedGlassMesh != nullptr);
	SedanGlass->SetHiddenInGame(MountedGlassMesh == nullptr);

	for (int32 i = 0; i < 4; ++i)
	{
		SedanWheels[i]->SetStaticMesh(Wheels[i]);
		SedanWheels[i]->EmptyOverrideMaterials();
		SedanWheels[i]->SetVisibility(true);
		SedanWheels[i]->SetHiddenInGame(false);

		const FBoxSphereBounds WheelBounds = Wheels[i]->GetBounds();
		if (Spec.WheelLayoutMode == EWSPC2WheelLayoutMode::BakedCarSpace)
		{
			WheelMeshOrigins[i] = WheelBounds.Origin;
			WheelRadii[i] = FMath::Max(25.0f, static_cast<float>(WheelBounds.BoxExtent.Z));
			SedanWheels[i]->SetRelativeLocationAndRotation(FVector::ZeroVector, FRotator::ZeroRotator);
		}
		else
		{
			WheelMeshOrigins[i] = Spec.WheelOffsetsCm.IsValidIndex(i) ? Spec.WheelOffsetsCm[i] : FVector::ZeroVector;
			const float MeasuredRadius = static_cast<float>(WheelBounds.BoxExtent.Z);
			WheelRadii[i] = (Spec.DefaultWheelRadiusCm > 10.0f) ? Spec.DefaultWheelRadiusCm : FMath::Max(25.0f, MeasuredRadius);
		}
		DrawnWheelAngle[i] = 0.0f;
	}

	for (int32 i = 0; i < 2; ++i)
	{
		if (bMountBrakes && LoadedBrakes[i])
		{
			FrontBrakes[i]->SetStaticMesh(LoadedBrakes[i]);
			FrontBrakes[i]->SetVisibility(true);
			FrontBrakes[i]->SetHiddenInGame(false);
			bFrontBrakeBakedCarSpace[i] = LoadedBrakes[i]->GetBounds().Origin.Size() > 25.0f;
		}
		else
		{
			FrontBrakes[i]->SetStaticMesh(nullptr);
			FrontBrakes[i]->SetVisibility(false);
			FrontBrakes[i]->SetHiddenInGame(true);
			bFrontBrakeBakedCarSpace[i] = true;
		}
	}

	if (Spec.bAutoComputeCollisionFromBody)
	{
		const FBox BodyBox = MountedBodyMesh->GetBounds().GetBox().TransformBy(FTransform(Spec.BodyRelativeRotation, FVector::ZeroVector));
		const FVector Size = BodyBox.GetSize();
		const FVector Center = BodyBox.GetCenter();

		// Lower body box: keep bottom >= 28 cm so kerbs never snag the chassis collider
		const float LowerMinZ = FMath::Max(static_cast<float>(BodyBox.Min.Z) + 6.0f, 28.0f);
		const float LowerMaxZ = FMath::Min(LowerMinZ + FMath::Max(Size.Z * 0.44f, 54.0f), static_cast<float>(BodyBox.Max.Z) - 18.0f);
		const float LowerCenterZ = 0.5f * (LowerMinZ + LowerMaxZ);
		const float LowerHalfZ = FMath::Max(16.0f, 0.5f * (LowerMaxZ - LowerMinZ));

		BodyCollision->SetRelativeLocation(FVector(Center.X, Center.Y, LowerCenterZ));
		BodyCollision->SetBoxExtent(FVector(FMath::Max(120.0f, Size.X * 0.49f), FMath::Max(65.0f, Size.Y * 0.44f), LowerHalfZ));

		// Cabin box: upper greenhouse centered slightly rear of midpoint
		const float CabinMinZ = LowerMaxZ - 4.0f;
		const float CabinMaxZ = FMath::Max(CabinMinZ + 32.0f, static_cast<float>(BodyBox.Max.Z) - 4.0f);
		CabinCollision->SetRelativeLocation(FVector(Center.X - Size.X * 0.04f, Center.Y, 0.5f * (CabinMinZ + CabinMaxZ)));
		CabinCollision->SetBoxExtent(FVector(FMath::Max(85.0f, Size.X * 0.28f), FMath::Max(55.0f, Size.Y * 0.38f), 0.5f * (CabinMaxZ - CabinMinZ)));
	}
	else
	{
		BodyCollision->SetRelativeLocation(Spec.BodyCollisionCenter);
		BodyCollision->SetBoxExtent(Spec.BodyCollisionExtent);
		CabinCollision->SetRelativeLocation(Spec.CabinCollisionCenter);
		CabinCollision->SetBoxExtent(Spec.CabinCollisionExtent);
	}

	bUsingSedanBody = true;
	bUsingPoliceCruiserMesh = Spec.bIsPoliceCruiser;
	ActiveWheelLayoutMode = Spec.WheelLayoutMode;
	ActiveVehiclePresetId = Spec.PresetId;
	ActiveVehicleDisplayName = Spec.DisplayName.IsEmpty() ? Spec.PresetId.ToString() : Spec.DisplayName.ToString();
	ActiveMassScale = FMath::Clamp(Spec.MassScale, 0.4f, 3.0f);
	ActiveMaxTorqueScale = FMath::Clamp(Spec.MaxTorqueScale, 0.4f, 3.0f);
	ActiveChassisHeightCm = FMath::Clamp(Spec.ChassisHeightCm, 80.0f, 320.0f);

	SetCrewLayout(Spec.GunnerSeatLocation, Spec.LightBarCentre, Spec.LightBarHalfSpacing);
	MountCrew(Spec);
	SetRoofLightbarEnabled(Spec.bHasRoofLightbar);

	if (Spec.OnCarViewLocations.Num() > 0)
	{
		SetOnCarViews(Spec.OnCarViewLocations, Spec.OnCarViewNames);
	}

	return true;
}

void AWSPC2SportsCar::ApplyVehicleProfile(bool bRuntimeSwitch)
{
	bool bMounted = false;

	// 1. Custom DataAsset assigned in Blueprint/Details (unless overridden by CLI or runtime cycling)
	if (!bPresetOverrideActive && VehicleProfileAsset)
	{
		bMounted = TryMountProfileSpec(VehicleProfileAsset->Profile);
	}

	// 2. Requested built-in preset (default: Patrol)
	if (!bMounted)
	{
		if (const FWSPC2VehicleProfileSpec* RequestedSpec = UWSPC2VehicleProfile::FindBuiltinPreset(ActiveVehiclePresetId))
		{
			bMounted = TryMountProfileSpec(*RequestedSpec);
		}
	}

	// 3. Fallback chain: Patrol -> CrownVic -> template mesh
	if (!bMounted)
	{
		static const FName FallbackOrder[] = { FName("Patrol"), FName("CrownVic") };
		for (const FName FallbackId : FallbackOrder)
		{
			if (const FWSPC2VehicleProfileSpec* FallbackSpec = UWSPC2VehicleProfile::FindBuiltinPreset(FallbackId))
			{
				if (TryMountProfileSpec(*FallbackSpec))
				{
					bMounted = true;
					break;
				}
			}
		}
	}

	if (!bMounted)
	{
		bUsingSedanBody = false;
		bUsingPoliceCruiserMesh = false;
		return;
	}

	// Enable welded Chaos vehicle collision & rigid-body hit notifications
	BodyCollision->SetCollisionProfileName(FName("Vehicle"));
	BodyCollision->SetNotifyRigidBodyCollision(true);
	CabinCollision->SetCollisionProfileName(FName("Vehicle"));
	CabinCollision->SetNotifyRigidBodyCollision(true);
	if (GetMesh())
	{
		GetMesh()->SetNotifyRigidBodyCollision(true);
	}

	// Shift each simulated Chaos wheel from the template skeleton bone to the loaded vehicle's exact hub
	UChaosWheeledVehicleMovementComponent* Movement = GetChaosVehicleMovement();
	const USkinnedAsset* Skeleton = GetMesh() ? GetMesh()->GetSkinnedAsset() : nullptr;

	if (Movement && Skeleton && Movement->WheelSetups.Num() == 4)
	{
		for (int32 Index = 0; Index < 4; ++Index)
		{
			const FVector BonePosition = Skeleton->GetComposedRefPoseMatrix(Movement->WheelSetups[Index].BoneName).GetOrigin();
			Movement->WheelSetups[Index].AdditionalOffset = GetSedanWheelPosition(Index) - BonePosition;
		}
	}

	if (bRuntimeSwitch)
	{
		ApplyTuning();

		if (Movement)
		{
			Movement->RecreatePhysicsState();
			// Reset GT/PT transmission state so RecreatePhysicsState never leaves PT stuck in Neutral while GT thinks TargetGear==1
			Movement->ResetVehicleState();
			Movement->SetTargetGear(0, true);
			Movement->SetTargetGear(1, true);
		}

		HideTemplateBodyParts();
		DisableTemplateBodyCollision();
		ApplyWheelTuning();
		ApplyCenterOfMassOverride();
		ConfigureDamageRig();

		if (HasAuthority())
		{
			if (UWSPC2VehicleDamageComponent* DamageComp = GetVehicleDamage())
			{
				DamageComp->RepairAll();
			}

			// Lift slightly so taller wheels or deeper bumpers settle cleanly onto the ground
			const FVector LiftLoc = GetActorLocation() + FVector(0.0f, 0.0f, 18.0f);
			FRotator UprightRot = GetActorRotation();
			UprightRot.Pitch = 0.0f;
			UprightRot.Roll = 0.0f;
			SetActorTransform(FTransform(UprightRot, LiftLoc, FVector::OneVector), false, nullptr, ETeleportType::TeleportPhysics);
			if (GetMesh())
			{
				GetMesh()->SetPhysicsAngularVelocityInDegrees(FVector::ZeroVector);
			}
		}

		UE_LOG(LogWSPC2, Log, TEXT("Switched hero vehicle to %s (%s), massScale=%.2f torqueScale=%.2f wheels=(R %.1f/%.1f cm)"),
			*ActiveVehicleDisplayName, *ActiveVehiclePresetId.ToString(), ActiveMassScale, ActiveMaxTorqueScale, WheelRadii[0], WheelRadii[2]);
	}
}

void AWSPC2SportsCar::DisableTemplateBodyCollision()
{
	// The skeletal mesh underneath is still the template's low sports car, and its physics asset was still
	// colliding: an invisible body a hand's width off the ground that grounded on kerbs and crests.
	// The two boxes sized to the sedan stay as the car's collision; the template shapes stop touching the world.
	USkeletalMeshComponent* Skeleton = GetMesh();
	int32 Disabled = 0;

	for (FBodyInstance* Body : Skeleton->Bodies)
	{
		const UBodySetup* Setup = (Body && Body->IsValidBodyInstance()) ? Body->GetBodySetup() : nullptr;
		if (!Setup)
		{
			continue;
		}

		const FBox Bounds = Setup->AggGeom.CalcAABB(FTransform::Identity);
		const int32 ShapeCount = Setup->AggGeom.GetElementCount();

		UE_LOG(LogWSPC2, Log, TEXT("Template body '%s': %d shape(s), lowest point %.1f cm, highest %.1f cm (bone space)"),
			*Setup->BoneName.ToString(), ShapeCount, Bounds.Min.Z, Bounds.Max.Z);

		for (int32 Shape = 0; Shape < ShapeCount; ++Shape)
		{
			// the index addresses this body's own shapes only, never the boxes welded onto it
			Body->SetShapeCollisionEnabled(Shape, ECollisionEnabled::NoCollision, Shape == ShapeCount - 1);
			++Disabled;
		}
	}

	UE_LOG(LogWSPC2, Log, TEXT("HeroVehicle [%s]: %d template collision shape(s) switched off; profile boxes carry the collision"), *ActiveVehiclePresetId.ToString(), Disabled);
}

void AWSPC2SportsCar::Tick(float Delta)
{
	Super::Tick(Delta);

	if (!bUsingSedanBody)
	{
		return;
	}

	UpdateCrewAndWheel(Delta);

	const UChaosWheeledVehicleMovementComponent* Movement = GetChaosVehicleMovement();
	const UWSPC2VehicleDamageComponent* DamageComp = GetVehicleDamage();

	for (int32 Index = 0; Index < SedanWheels.Num(); ++Index)
	{
		FVector Position = GetSedanWheelPosition(Index);
		FRotator Motion = FRotator::ZeroRotator;

		if (Movement->Wheels.IsValidIndex(Index) && Movement->Wheels[Index])
		{
			const UChaosVehicleWheel* Wheel = Movement->Wheels[Index];

			// same formula the engine's wheel animation uses
			Position += -Wheel->GetSuspensionAxis() * Wheel->GetSuspensionOffset();
			Motion.Yaw = Wheel->GetSteerAngle();

			// The step comes from the wheel's spin rate, not from the difference of two angles: the simulation wraps
			// the angle at every full turn, and the plain difference then jumped ~350 degrees the wrong way once per
			// revolution. Each jump turned the wheel backwards for a frame, and motion blur and the upscaler smeared
			// it; at 90 km/h that happened about twelve times a second.
			const float MaxStep = FMath::Max(GetDefault<UWSPC2VehicleTuning>()->WheelMaxDrawnStepDeg, 1.0f);
			const float Step = FMath::Clamp(Wheel->GetRotationAngularVelocity() * Delta, -MaxStep, MaxStep);

			DrawnWheelAngle[Index] = FMath::Fmod(DrawnWheelAngle[Index] + Step, 360.0f);

			Motion.Pitch = DrawnWheelAngle[Index];

			if (DamageComp)
			{
				Motion.Roll = DamageComp->GetWheelCamberDamageDeg(Index);
				Position.Z -= DamageComp->GetWheelVisualDropCm(Index);
			}
		}

		if (ActiveWheelLayoutMode == EWSPC2WheelLayoutMode::BakedCarSpace)
		{
			// CitySampleVehicles wheel vertices are baked around car origin (0,0,0) with hub at WheelMeshOrigins[Index].
			// Apply steering yaw and damaged camber roll before spinning around the tilted local axle.
			const FQuat HubTilt = FRotator(0.0f, Motion.Yaw, Motion.Roll).Quaternion();
			const FQuat Q = HubTilt * FRotator(Motion.Pitch, 0.0f, 0.0f).Quaternion();
			const FVector RelLoc = Position - Q.RotateVector(WheelMeshOrigins[Index]);
			SedanWheels[Index]->SetRelativeLocationAndRotation(RelLoc, Q);

			// Front brakes follow the same hub, steered and cambered on the spring, without spinning
			if (Index < FrontBrakes.Num() && FrontBrakes[Index]->GetStaticMesh())
			{
				const FVector BrakeLoc = bFrontBrakeBakedCarSpace[Index]
					? (Position - HubTilt.RotateVector(WheelMeshOrigins[Index]))
					: Position;
				FrontBrakes[Index]->SetRelativeLocationAndRotation(BrakeLoc, HubTilt);
			}
		}
		else if (ActiveWheelLayoutMode == EWSPC2WheelLayoutMode::CenteredOriginPlusX)
		{
			// Prepared GLBs: +X forward, origin at wheel hub; Left=Yaw 0, Right=Yaw 180
			const bool bRight = (Index % 2) == 1;
			const FQuat Facing = FRotator(0.0f, bRight ? 180.0f : 0.0f, 0.0f).Quaternion();
			const FQuat Q = FRotator(0.0f, Motion.Yaw, Motion.Roll).Quaternion() * FRotator(Motion.Pitch, 0.0f, 0.0f).Quaternion();
			SedanWheels[Index]->SetRelativeLocationAndRotation(Position, Q * Facing);
		}
		else
		{
			// Legacy /Game/CrownVic: body Yaw -90, wheel L=Yaw -90, R=Yaw +90
			const bool bRight = (Index % 2) == 1;
			const FQuat Facing = FRotator(0.0f, bRight ? 90.0f : -90.0f, 0.0f).Quaternion();
			const FQuat Q = FRotator(0.0f, Motion.Yaw, Motion.Roll).Quaternion() * FRotator(Motion.Pitch, 0.0f, 0.0f).Quaternion();
			SedanWheels[Index]->SetRelativeLocationAndRotation(Position, Q * Facing);
		}
	}
}

void AWSPC2SportsCar::LogWheelLayout()
{
	const UChaosWheeledVehicleMovementComponent* Movement = GetChaosVehicleMovement();
	UE_LOG(LogWSPC2, Log, TEXT("HeroVehicle preset=%s name='%s' body=%s brakes=%d"),
		*ActiveVehiclePresetId.ToString(),
		*ActiveVehicleDisplayName,
		*GetNameSafe(SedanBody ? SedanBody->GetStaticMesh() : nullptr),
		(FrontBrakes.Num() >= 2 && FrontBrakes[0]->GetStaticMesh() && FrontBrakes[1]->GetStaticMesh()) ? 1 : 0);

	for (int32 Index = 0; Index < Movement->Wheels.Num(); ++Index)
	{
		if (const UChaosVehicleWheel* Wheel = Movement->Wheels[Index])
		{
			const UPhysicalMaterial* Surface = Movement->GetWheelState(Index).PhysMaterial.Get();

			UE_LOG(LogWSPC2, Log, TEXT("Wheel %d: axle at (%s), radius %.1f, suspension offset %.1f, on %s (friction %.2f)"),
				Index, *GetSedanWheelPosition(Index).ToCompactString(), Wheel->GetWheelRadius(), Wheel->GetSuspensionOffset(),
				*GetNameSafe(Surface), Surface ? Surface->Friction : 0.0f);
		}
	}

	// inertia in kg m^2 (Unreal reports kg cm^2), centre of mass relative to the car
	const FVector Inertia = GetMesh()->GetInertiaTensor() * 0.0001f;
	const FVector CentreOfMass = GetActorTransform().InverseTransformPosition(GetMesh()->GetCenterOfMass());
	UE_LOG(LogWSPC2, Log, TEXT("Mass properties: %.0f kg, inertia roll %.0f pitch %.0f yaw %.0f kg m2, centre of mass (%.0f, %.0f, %.0f) cm"),
		GetMesh()->GetMass(), Inertia.X, Inertia.Y, Inertia.Z, CentreOfMass.X, CentreOfMass.Y, CentreOfMass.Z);

	UE_LOG(LogWSPC2, Log, TEXT("Car at height %.1f, roll %.1f, pitch %.1f, speed %.1f km/h"),
		GetActorLocation().Z, GetActorRotation().Roll, GetActorRotation().Pitch, GetSpeedKmh());
}

void AWSPC2SportsCar::ApplyTuning()
{
	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
	UChaosWheeledVehicleMovementComponent* Movement = GetChaosVehicleMovement();

	if (!Tuning || !Movement)
	{
		return;
	}

	// chassis
	Movement->ChassisHeight = ActiveChassisHeightCm;
	Movement->Mass = Tuning->MassKg * ActiveMassScale;
	Movement->DragCoefficient = Tuning->DragCoefficient;
	Movement->DownforceCoefficient = Tuning->DownforceCoefficient;

	// wheels: steer at the front, drive and handbrake at the rear
	if (Movement->WheelSetups.Num() == 4)
	{
		Movement->WheelSetups[0].WheelClass = UWSPC2PatrolWheelFront::StaticClass();
		Movement->WheelSetups[1].WheelClass = UWSPC2PatrolWheelFront::StaticClass();
		Movement->WheelSetups[2].WheelClass = UWSPC2PatrolWheelRear::StaticClass();
		Movement->WheelSetups[3].WheelClass = UWSPC2PatrolWheelRear::StaticClass();
	}

	Movement->DifferentialSetup.DifferentialType = EVehicleDifferential::RearWheelDrive;

	// engine: a lazy V8, strong in the midrange and fading towards the redline
	Movement->EngineSetup.MaxRPM = Tuning->MaxRPM;
	Movement->EngineSetup.EngineIdleRPM = Tuning->IdleRPM;
	Movement->EngineSetup.EngineBrakeEffect = Tuning->EngineBrakeEffect;
	Movement->EngineSetup.EngineRevUpMOI = Tuning->EngineRevUpMOI;
	Movement->EngineSetup.EngineRevDownRate = Tuning->EngineRevDownRate;

	// drop any curve asset the Blueprint points at, so we never edit a shared asset
	Movement->EngineSetup.TorqueCurve.ExternalCurve = nullptr;

	if (FRichCurve* TorqueCurve = Movement->EngineSetup.TorqueCurve.GetRichCurve())
	{
		const float RpmScale = Tuning->MaxRPM / 5750.0f;

		// engine torque as a fraction of its peak
		static const float Rpm[] = { 0.0f, 750.0f, 1500.0f, 2500.0f, 4000.0f, 5000.0f, 5750.0f };
		static const float Fraction[] = { 0.55f, 0.62f, 0.80f, 0.93f, 1.0f, 0.90f, 0.72f };

		float Peak = 0.0f;

		TorqueCurve->Reset();

		for (int32 Key = 0; Key < UE_ARRAY_COUNT(Rpm); ++Key)
		{
			const float Fade = FMath::Clamp(1.0f - Rpm[Key] / Tuning->ConverterFadeRPM, 0.0f, 1.0f);
			const float Value = Fraction[Key] * (1.0f + (Tuning->ConverterStallRatio - 1.0f) * Fade);

			TorqueCurve->AddKey(Rpm[Key] * RpmScale, Value);
			Peak = FMath::Max(Peak, Value);
		}

		// the simulation rescales the curve so its highest point equals MaxTorque
		Movement->EngineSetup.MaxTorque = Tuning->MaxTorqueNm * ActiveMaxTorqueScale * Peak;
	}

	// transmission
	Movement->TransmissionSetup.bUseAutomaticGears = true;
	Movement->TransmissionSetup.bUseAutoReverse = true;
	Movement->TransmissionSetup.FinalRatio = Tuning->FinalDriveRatio;
	Movement->TransmissionSetup.ChangeUpRPM = Tuning->ChangeUpRPM;
	Movement->TransmissionSetup.ChangeDownRPM = Tuning->ChangeDownRPM;
	Movement->TransmissionSetup.GearChangeTime = Tuning->GearChangeTime;
	Movement->TransmissionSetup.TransmissionEfficiency = Tuning->TransmissionEfficiency;
	Movement->TransmissionSetup.ForwardGearRatios = Tuning->ForwardGearRatios;

	Movement->TransmissionSetup.ReverseGearRatios.SetNum(1);
	Movement->TransmissionSetup.ReverseGearRatios[0] = Tuning->ReverseGearRatio;

	// steering: full lock at parking speed, less as speed rises so a keyboard tap does not spin the car
	Movement->SteeringSetup.SteeringType = ESteeringType::Ackermann;
	Movement->SteeringSetup.AngleRatio = 0.7f;
	Movement->SteeringSetup.SteeringCurve.ExternalCurve = nullptr;

	if (FRichCurve* SteeringCurve = Movement->SteeringSetup.SteeringCurve.GetRichCurve())
	{
		// Flat: the speed limit on steering is applied to the driver's input instead (AWSPC2Pawn::GetSteeringAllowance),
		// where it can tell turning in from countersteering. Here it would cut both.
		// Two keys, never one: the engine samples the curve in steps of (last key time / 20), and a single key at
		// zero made that step zero, an endless loop that tried to allocate 30 GB.
		SteeringCurve->Reset();
		SteeringCurve->AddKey(0.0f, 1.0f);
		SteeringCurve->AddKey(300.0f, 1.0f);
	}

	// how hard the body resists starting and stopping a spin; the template's small physics shapes give a light car
	Movement->InertiaTensorScale = FVector(1.0f, 1.0f, Tuning->YawInertiaScale);
	Movement->bEnableCenterOfMassOverride = Tuning->bOverrideCenterOfMass;
	if (Tuning->bOverrideCenterOfMass)
	{
		Movement->CenterOfMassOverride = Tuning->CenterOfMassOffset;
	}

	// wheel properties with no runtime setter: configure CDOs before Chaos creates the physics wheels
	UWSPC2PatrolWheelFront* FrontWheelCDO = GetMutableDefault<UWSPC2PatrolWheelFront>();
	UWSPC2PatrolWheelRear* RearWheelCDO = GetMutableDefault<UWSPC2PatrolWheelRear>();
	FrontWheelCDO->SideSlipModifier = Tuning->FrontSlideGrip;
	RearWheelCDO->SideSlipModifier = Tuning->RearSlideGrip;
	FrontWheelCDO->CorneringStiffness = Tuning->FrontCorneringStiffness;
	RearWheelCDO->CorneringStiffness = Tuning->RearCorneringStiffness;
	FrontWheelCDO->RollbarScaling = Tuning->FrontRollbarScaling;
	RearWheelCDO->RollbarScaling = Tuning->RearRollbarScaling;

	// input smoothing
	Movement->SteeringInputRate.RiseRate = Tuning->SteeringRiseRate;
	Movement->SteeringInputRate.FallRate = Tuning->SteeringFallRate;
	Movement->ThrottleInputRate.RiseRate = Tuning->ThrottleRiseRate;
	Movement->BrakeInputRate.RiseRate = Tuning->BrakeRiseRate;
}

void AWSPC2SportsCar::ApplyWheelTuning()
{
	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
	UChaosWheeledVehicleMovementComponent* Movement = GetChaosVehicleMovement();

	if (!Tuning || !Movement)
	{
		return;
	}

	for (int32 WheelIndex = 0; WheelIndex < Movement->WheelSetups.Num(); ++WheelIndex)
	{
		const bool bFront = WheelIndex < 2;

		Movement->SetWheelFrictionMultiplier(WheelIndex, bFront ? Tuning->FrontFriction : Tuning->RearFriction);
		Movement->SetWheelMaxBrakeTorque(WheelIndex, bFront ? Tuning->FrontBrakeTorque : Tuning->RearBrakeTorque);
		Movement->SetWheelHandbrakeTorque(WheelIndex, bFront ? 0.0f : Tuning->HandbrakeTorque);
		Movement->SetWheelMaxSteerAngle(WheelIndex, bFront ? Tuning->MaxSteerAngle : 0.0f);
		Movement->SetABSEnabled(WheelIndex, Tuning->bABS);
		Movement->SetTractionControlEnabled(WheelIndex, Tuning->bTractionControl);
		Movement->SetSuspensionParams(Tuning->SpringRate, Tuning->DampingRatio, Tuning->SpringPreload, Tuning->MaxRaise, Tuning->MaxDrop, WheelIndex);

		if (bUsingSedanBody)
		{
			Movement->SetWheelRadius(WheelIndex, WheelRadii[WheelIndex]);
		}
	}
}
