// Copyright Epic Games, Inc. All Rights Reserved.


#include "WSPC2SportsCar.h"
#include "WSPC2PatrolWheels.h"
#include "WSPC2VehicleTuning.h"
#include "WSPC2VehicleDamageComponent.h"
#include "WSPC2VehicleAudioComponent.h"
#include "WSPC2CrewComponent.h"
#include "WSPC2Gunnery.h"
#include "WSPC2.h"
#include "ChaosWheeledVehicleMovementComponent.h"
#include "ChaosVehicleWheel.h"
#include "Components/BoxComponent.h"
#include "PhysicsEngine/BodyInstance.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkinnedAsset.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
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

	// the steering wheel turns with the actual front rack angle (reflecting turn-in slew & countersteer)
	UChaosWheeledVehicleMovementComponent* Movement = GetChaosVehicleMovement();
	float TargetSteerNorm = Movement ? Movement->GetSteeringInput() : 0.0f;
	if (Movement && Movement->Wheels.IsValidIndex(0) && Movement->Wheels[0] && ActiveMaxSteerAngle > 1.0f)
	{
		TargetSteerNorm = FMath::Clamp(Movement->Wheels[0]->GetSteerAngle() / ActiveMaxSteerAngle, -1.0f, 1.0f);
	}
	DrawnSteering = FMath::FInterpTo(DrawnSteering, TargetSteerNorm, Delta, 16.0f);
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
	if (bAllowCliVehicleOverride && !bPresetOverrideActive && FParse::Value(FCommandLine::Get(), TEXT("WSPC2Vehicle="), CliPreset) && !CliPreset.IsEmpty())
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
		ReweldProfileCollision();
		ApplyCenterOfMassOverride();
		ConfigureDamageRig();

		FTimerHandle LogTimer;
		GetWorld()->GetTimerManager().SetTimer(LogTimer, this, &AWSPC2SportsCar::LogWheelLayout, 3.0f, false);
	}
}

float AWSPC2SportsCar::GetActiveBaseRearFriction() const
{
	if (ActiveProfileSpec.bUseRealWorldSpecs)
	{
		return ActiveProfileSpec.RearFriction;
	}
	return GetDefault<UWSPC2VehicleTuning>()->RearFriction;
}

void AWSPC2SportsCar::ApplyCenterOfMassOverride()
{
	if (UChaosWheeledVehicleMovementComponent* Movement = GetChaosVehicleMovement())
	{
		const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
		if (FBodyInstance* BI = GetMesh() ? GetMesh()->GetBodyInstance() : nullptr)
		{
			const bool bUseReal = ActiveProfileSpec.bUseRealWorldSpecs;
			const bool bDoCoM = bUseReal || (Tuning && Tuning->bOverrideCenterOfMass);
			const FVector DesiredLocalCoM = bUseReal ? ActiveProfileSpec.CenterOfMassOffset : (Tuning ? Tuning->CenterOfMassOffset : FVector(10.0f, 0.0f, 48.0f));
			if (bDoCoM && BI->IsValidBodyInstance())
			{
				const FVector WorldDesiredCoM = GetActorTransform().TransformPosition(DesiredLocalCoM);
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
			if (SedanWheels.IsValidIndex(i) && SedanWheels[i])
			{
				DamageComp->SetDetachedWheelVisualMeshOverride(i, SedanWheels[i]->GetStaticMesh());
			}
		}
		DamageComp->SetBaselineTorqueScale(ActiveMaxTorqueScale);
		DamageComp->ConfigureFromVehicleProfile(ActiveProfileSpec, Hubs, WheelRadii);
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
	return CycleVehiclePresetDirection(1);
}

FName AWSPC2SportsCar::CycleVehiclePresetDirection(int32 Direction)
{
	if (!HasAuthority())
	{
		return ActiveVehiclePresetId;
	}

	const FName NextId = (Direction >= 0)
		? UWSPC2VehicleProfile::GetNextAvailableBuiltinPresetId(ActiveVehiclePresetId)
		: UWSPC2VehicleProfile::GetPreviousAvailableBuiltinPresetId(ActiveVehiclePresetId);
	if (!NextId.IsNone() && NextId != ActiveVehiclePresetId)
	{
		SetVehiclePreset(NextId);
	}
	return ActiveVehiclePresetId;
}

FName AWSPC2SportsCar::CycleVehicleCategory()
{
	if (!HasAuthority())
	{
		return ActiveVehiclePresetId;
	}

	const FName NextId = UWSPC2VehicleProfile::GetNextCategoryPresetId(ActiveVehiclePresetId);
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
	if (!Spec.bBakedRunningGear)
	{
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
		const bool bShowWheel = (Wheels[i] != nullptr);
		SedanWheels[i]->SetVisibility(bShowWheel);
		SedanWheels[i]->SetHiddenInGame(!bShowWheel);

		if (Spec.bBakedRunningGear)
		{
			WheelMeshOrigins[i] = Spec.WheelOffsetsCm.IsValidIndex(i) ? Spec.WheelOffsetsCm[i] : FVector::ZeroVector;
			WheelRadii[i] = (i >= 2 && Spec.RearWheelRadiusCm > 10.0f) ? Spec.RearWheelRadiusCm : FMath::Max(25.0f, Spec.DefaultWheelRadiusCm);
		}
		else
		{
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
				const float ProfileRadius = (i >= 2 && Spec.RearWheelRadiusCm > 10.0f) ? Spec.RearWheelRadiusCm : Spec.DefaultWheelRadiusCm;
				WheelRadii[i] = (ProfileRadius > 10.0f) ? ProfileRadius : FMath::Max(25.0f, MeasuredRadius);
			}
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
	ActiveProfileSpec = Spec;
	ActiveWheelLayoutMode = Spec.WheelLayoutMode;
	ActiveVehiclePresetId = Spec.PresetId;
	ActiveVehicleDisplayName = Spec.DisplayName.IsEmpty() ? Spec.PresetId.ToString() : Spec.DisplayName.ToString();
	ActiveMassScale = FMath::Clamp(Spec.MassScale, 0.4f, 3.0f);
	ActiveMaxTorqueScale = FMath::Clamp(Spec.MaxTorqueScale, 0.4f, 3.0f);
	ActiveChassisHeightCm = FMath::Clamp(Spec.ChassisHeightCm, 80.0f, 320.0f);
	ActiveMaxSteerAngle = Spec.bUseRealWorldSpecs ? FMath::Clamp(Spec.MaxSteerAngle, 15.0f, 48.0f) : GetDefault<UWSPC2VehicleTuning>()->MaxSteerAngle;

	SetCrewLayout(Spec.GunnerSeatLocation, Spec.LightBarCentre, Spec.LightBarHalfSpacing);
	MountCrew(Spec);
	SetRoofLightbarEnabled(Spec.bHasRoofLightbar);

	if (Spec.OnCarViewLocations.Num() > 0)
	{
		SetOnCarViews(Spec.OnCarViewLocations, Spec.OnCarViewNames);
	}

	if (UWSPC2VehicleAudioComponent* Audio = GetVehicleAudio())
	{
		Audio->ConfigureForVehicleProfile(Spec);
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
	BodyCollision->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	BodyCollision->SetNotifyRigidBodyCollision(true);
	BodyCollision->BodyInstance.bAutoWeld = true;
	CabinCollision->SetCollisionProfileName(FName("Vehicle"));
	CabinCollision->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	CabinCollision->SetNotifyRigidBodyCollision(true);
	CabinCollision->BodyInstance.bAutoWeld = true;
	if (GetMesh())
	{
		GetMesh()->SetCollisionProfileName(FName("Vehicle"));
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
		ReweldProfileCollision();
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

void AWSPC2SportsCar::ReweldProfileCollision()
{
	USkeletalMeshComponent* Skel = GetMesh();
	if (!Skel)
	{
		return;
	}

	Skel->SetCollisionProfileName(FName("Vehicle"));
	Skel->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	Skel->SetNotifyRigidBodyCollision(true);
	if (FBodyInstance* RootBI = Skel->GetBodyInstance(NAME_None))
	{
		RootBI->SetInstanceNotifyRBCollision(true);
	}

	auto WeldBox = [Skel](UBoxComponent* Box)
	{
		if (!Box)
		{
			return;
		}
		Box->UnWeldFromParent();
		Box->SetSimulatePhysics(false);
		Box->SetCollisionProfileName(FName("Vehicle"));
		Box->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		Box->SetNotifyRigidBodyCollision(true);
		Box->BodyInstance.bAutoWeld = true;
		Box->AttachToComponent(Skel, FAttachmentTransformRules::KeepRelativeTransform, NAME_None);
		Box->RecreatePhysicsState();
		Box->WeldTo(Skel, NAME_None);
	};

	WeldBox(BodyCollision);
	WeldBox(CabinCollision);

	UE_LOG(LogWSPC2, Log, TEXT("HeroVehicle [%s] ReweldProfileCollision: BodyWelded=%d CabinWelded=%d BodyCol=%d RootNotify=1"),
		*ActiveVehiclePresetId.ToString(),
		BodyCollision && BodyCollision->IsWelded() ? 1 : 0,
		CabinCollision && CabinCollision->IsWelded() ? 1 : 0,
		BodyCollision ? static_cast<int32>(BodyCollision->GetCollisionEnabled()) : -1);
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
		if (ActiveProfileSpec.bBakedRunningGear)
		{
			SedanWheels[Index]->SetVisibility(false);
			if (Index < FrontBrakes.Num())
			{
				FrontBrakes[Index]->SetVisibility(false);
			}
			continue;
		}

		const bool bDetached = DamageComp && DamageComp->IsWheelDetached(Index);
		SedanWheels[Index]->SetVisibility(!bDetached && SedanWheels[Index]->GetStaticMesh() != nullptr);
		SedanWheels[Index]->SetHiddenInGame(bDetached || SedanWheels[Index]->GetStaticMesh() == nullptr);
		if (Index < FrontBrakes.Num() && FrontBrakes[Index]->GetStaticMesh())
		{
			FrontBrakes[Index]->SetVisibility(!bDetached);
			FrontBrakes[Index]->SetHiddenInGame(bDetached);
		}
		if (bDetached)
		{
			continue;
		}

		FVector Position = GetSedanWheelPosition(Index);
		FRotator Motion = FRotator::ZeroRotator;

		if (Movement->Wheels.IsValidIndex(Index) && Movement->Wheels[Index])
		{
			const UChaosVehicleWheel* Wheel = Movement->Wheels[Index];

			// same formula the engine's wheel animation uses
			Position += -Wheel->GetSuspensionAxis() * Wheel->GetSuspensionOffset();
			Motion.Yaw = Wheel->GetSteerAngle();

			const float MaxStep = FMath::Max(GetDefault<UWSPC2VehicleTuning>()->WheelMaxDrawnStepDeg, 1.0f);
			const float Step = FMath::Clamp(Wheel->GetRotationAngularVelocity() * Delta, -MaxStep, MaxStep);

			DrawnWheelAngle[Index] = FMath::Fmod(DrawnWheelAngle[Index] + Step, 360.0f);

			Motion.Pitch = DrawnWheelAngle[Index];

			if (DamageComp)
			{
				const float WobbleDeg = DamageComp->GetWheelWobbleAmplitudeDeg(Index) * FMath::Sin(FMath::DegreesToRadians(DrawnWheelAngle[Index]));
				Motion.Roll = DamageComp->GetWheelCamberDamageDeg(Index) + WobbleDeg;
				Motion.Yaw += DamageComp->GetWheelToeDamageDeg(Index);
				Position.Z -= DamageComp->GetWheelVisualDropCm(Index);
			}
		}

		if (ActiveWheelLayoutMode == EWSPC2WheelLayoutMode::BakedCarSpace)
		{
			const FQuat HubTilt = FRotator(0.0f, Motion.Yaw, Motion.Roll).Quaternion();
			const FQuat Q = HubTilt * FRotator(Motion.Pitch, 0.0f, 0.0f).Quaternion();
			const FVector RelLoc = Position - Q.RotateVector(WheelMeshOrigins[Index]);
			SedanWheels[Index]->SetRelativeLocationAndRotation(RelLoc, Q);

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
			const FQuat HubTilt = FRotator(0.0f, Motion.Yaw, Motion.Roll).Quaternion();
			const FQuat Q = HubTilt * FRotator(Motion.Pitch, 0.0f, 0.0f).Quaternion();
			SedanWheels[Index]->SetRelativeLocationAndRotation(Position, Q * Facing);

			// Hub-centered FL/FR brake calipers steer & ride suspension cleanly without spinning
			if (Index < FrontBrakes.Num() && FrontBrakes[Index]->GetStaticMesh())
			{
				FrontBrakes[Index]->SetRelativeLocationAndRotation(Position, HubTilt);
			}
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

	const bool bUseReal = ActiveProfileSpec.bUseRealWorldSpecs;
	const EWSPC2Drivetrain Drive = bUseReal ? ActiveProfileSpec.Drivetrain : EWSPC2Drivetrain::RWD;

	// chassis
	Movement->ChassisHeight = ActiveChassisHeightCm;
	Movement->Mass = bUseReal ? ActiveProfileSpec.RealMassKg : (Tuning->MassKg * ActiveMassScale);
	Movement->DragCoefficient = bUseReal ? ActiveProfileSpec.DragCoefficient : Tuning->DragCoefficient;
	Movement->DownforceCoefficient = bUseReal ? ActiveProfileSpec.DownforceCoefficient : Tuning->DownforceCoefficient;

	UClass* FrontClass = (Drive == EWSPC2Drivetrain::RWD)
		? UWSPC2PatrolWheelFront::StaticClass()
		: UWSPC2PatrolWheelFrontDriven::StaticClass();
	UClass* RearClass = (Drive == EWSPC2Drivetrain::FWD)
		? UWSPC2PatrolWheelRearFree::StaticClass()
		: UWSPC2PatrolWheelRear::StaticClass();

	if (Movement->WheelSetups.Num() == 4)
	{
		Movement->WheelSetups[0].WheelClass = FrontClass;
		Movement->WheelSetups[1].WheelClass = FrontClass;
		Movement->WheelSetups[2].WheelClass = RearClass;
		Movement->WheelSetups[3].WheelClass = RearClass;
	}

	Movement->DifferentialSetup.DifferentialType =
		(Drive == EWSPC2Drivetrain::FWD) ? EVehicleDifferential::FrontWheelDrive :
		(Drive == EWSPC2Drivetrain::AWD) ? EVehicleDifferential::AllWheelDrive :
		EVehicleDifferential::RearWheelDrive;

	// engine
	const float MaxRPM = bUseReal ? ActiveProfileSpec.MaxRPM : Tuning->MaxRPM;
	const float IdleRPM = bUseReal ? ActiveProfileSpec.IdleRPM : Tuning->IdleRPM;
	const float PeakRPM = bUseReal ? FMath::Clamp(ActiveProfileSpec.PeakTorqueRPM, IdleRPM + 200.0f, MaxRPM - 150.0f) : (MaxRPM * 0.70f);
	const float BaseTorqueNm = bUseReal ? ActiveProfileSpec.RealMaxTorqueNm : (Tuning->MaxTorqueNm * ActiveMaxTorqueScale);
	const float StallRatio = bUseReal ? ActiveProfileSpec.ConverterStallRatio : Tuning->ConverterStallRatio;
	const float FadeRPM = bUseReal ? FMath::Max(PeakRPM * 0.75f, 1600.0f) : Tuning->ConverterFadeRPM;

	Movement->EngineSetup.MaxRPM = MaxRPM;
	Movement->EngineSetup.EngineIdleRPM = IdleRPM;
	Movement->EngineSetup.EngineBrakeEffect = Tuning->EngineBrakeEffect;
	Movement->EngineSetup.EngineRevUpMOI = bUseReal ? FMath::Clamp(ActiveProfileSpec.RealMassKg / 900.0f, 1.2f, 4.5f) : Tuning->EngineRevUpMOI;
	Movement->EngineSetup.EngineRevDownRate = Tuning->EngineRevDownRate;

	Movement->EngineSetup.TorqueCurve.ExternalCurve = nullptr;

	if (FRichCurve* TorqueCurve = Movement->EngineSetup.TorqueCurve.GetRichCurve())
	{
		TorqueCurve->Reset();
		if (bUseReal)
		{
			// Exact real-world torque shape anchored at peak torque (PeakRPM, 1.0) and redline hp (0.96*MaxRPM)
			const float RedlineRPM = FMath::Max(PeakRPM + 250.0f, MaxRPM * 0.96f);
			const float TargetRedlineFrac = FMath::Clamp(
				(ActiveProfileSpec.RealHorsepower * 7127.0f) / FMath::Max(BaseTorqueNm * RedlineRPM, 1000.0f),
				0.52f, 0.97f);
			const float MidRPM = 0.5f * (PeakRPM + RedlineRPM);
			const float MidFrac = FMath::Lerp(1.0f, TargetRedlineFrac, 0.42f);

			const float RpmPts[7] = { 0.0f, IdleRPM, FMath::Lerp(IdleRPM, PeakRPM, 0.48f), PeakRPM, MidRPM, RedlineRPM, MaxRPM + 350.0f };
			const float FracPts[7] = { 0.58f, 0.68f, 0.88f, 1.00f, MidFrac, TargetRedlineFrac, 0.25f };
			float Peak = 0.0f;
			for (int32 Key = 0; Key < 7; ++Key)
			{
				const float Fade = FMath::Clamp(1.0f - RpmPts[Key] / FadeRPM, 0.0f, 1.0f);
				const float Val = FracPts[Key] * (1.0f + (StallRatio - 1.0f) * Fade);
				TorqueCurve->AddKey(RpmPts[Key], Val);
				Peak = FMath::Max(Peak, Val);
			}
			Movement->EngineSetup.MaxTorque = BaseTorqueNm * Peak;
		}
		else
		{
			const float RpmScale = MaxRPM / 5750.0f;
			static const float Rpm[] = { 0.0f, 750.0f, 1500.0f, 2500.0f, 4000.0f, 5000.0f, 5750.0f };
			static const float Fraction[] = { 0.55f, 0.62f, 0.80f, 0.93f, 1.0f, 0.90f, 0.72f };
			float Peak = 0.0f;
			for (int32 Key = 0; Key < UE_ARRAY_COUNT(Rpm); ++Key)
			{
				const float Fade = FMath::Clamp(1.0f - Rpm[Key] / FadeRPM, 0.0f, 1.0f);
				const float Value = Fraction[Key] * (1.0f + (StallRatio - 1.0f) * Fade);
				TorqueCurve->AddKey(Rpm[Key] * RpmScale, Value);
				Peak = FMath::Max(Peak, Value);
			}
			Movement->EngineSetup.MaxTorque = BaseTorqueNm * Peak;
		}
	}

	// transmission
	Movement->TransmissionSetup.bUseAutomaticGears = true;
	Movement->TransmissionSetup.bUseAutoReverse = true;
	Movement->TransmissionSetup.FinalRatio = bUseReal ? ActiveProfileSpec.FinalDriveRatio : Tuning->FinalDriveRatio;
	Movement->TransmissionSetup.ChangeUpRPM = bUseReal ? ActiveProfileSpec.ChangeUpRPM : Tuning->ChangeUpRPM;
	Movement->TransmissionSetup.ChangeDownRPM = bUseReal ? ActiveProfileSpec.ChangeDownRPM : Tuning->ChangeDownRPM;
	Movement->TransmissionSetup.GearChangeTime = bUseReal ? ActiveProfileSpec.GearChangeTime : Tuning->GearChangeTime;
	Movement->TransmissionSetup.TransmissionEfficiency = Tuning->TransmissionEfficiency;
	Movement->TransmissionSetup.ForwardGearRatios = (bUseReal && ActiveProfileSpec.ForwardGearRatios.Num() > 0)
		? ActiveProfileSpec.ForwardGearRatios
		: Tuning->ForwardGearRatios;

	Movement->TransmissionSetup.ReverseGearRatios.SetNum(1);
	Movement->TransmissionSetup.ReverseGearRatios[0] = bUseReal ? ActiveProfileSpec.ReverseGearRatio : Tuning->ReverseGearRatio;

	// steering: full lock at parking speed, less as speed rises so a keyboard tap does not spin the car
	Movement->SteeringSetup.SteeringType = ESteeringType::Ackermann;
	Movement->SteeringSetup.AngleRatio = 0.7f;
	Movement->SteeringSetup.SteeringCurve.ExternalCurve = nullptr;

	if (FRichCurve* SteeringCurve = Movement->SteeringSetup.SteeringCurve.GetRichCurve())
	{
		SteeringCurve->Reset();
		SteeringCurve->AddKey(0.0f, 1.0f);
		SteeringCurve->AddKey(300.0f, 1.0f);
	}

	Movement->InertiaTensorScale = FVector(1.0f, 1.0f, Tuning->YawInertiaScale);
	const bool bOverrideCoM = bUseReal || Tuning->bOverrideCenterOfMass;
	Movement->bEnableCenterOfMassOverride = bOverrideCoM;
	if (bOverrideCoM)
	{
		Movement->CenterOfMassOverride = bUseReal ? ActiveProfileSpec.CenterOfMassOffset : Tuning->CenterOfMassOffset;
	}

	// Wheel CDO properties: always keep DefaultGame.ini baseline in shared CDOs so AI traffic
	// vehicles never contaminate the player vehicle's suspension/rollbar behavior. Per-car values
	// are applied exclusively on runtime wheel instances in ApplyWheelTuning().
	UChaosVehicleWheel* FrontWheelCDO = Cast<UChaosVehicleWheel>(FrontClass->GetDefaultObject());
	UChaosVehicleWheel* RearWheelCDO = Cast<UChaosVehicleWheel>(RearClass->GetDefaultObject());
	if (FrontWheelCDO)
	{
		FrontWheelCDO->SideSlipModifier = Tuning->FrontSlideGrip;
		FrontWheelCDO->CorneringStiffness = Tuning->FrontCorneringStiffness;
		FrontWheelCDO->RollbarScaling = Tuning->FrontRollbarScaling;
		FrontWheelCDO->SpringRate = Tuning->SpringRate;
		FrontWheelCDO->SpringPreload = Tuning->SpringPreload;
		FrontWheelCDO->SuspensionDampingRatio = Tuning->DampingRatio;
		FrontWheelCDO->SuspensionMaxRaise = Tuning->MaxRaise;
		FrontWheelCDO->SuspensionMaxDrop = Tuning->MaxDrop;
	}
	if (RearWheelCDO)
	{
		RearWheelCDO->SideSlipModifier = Tuning->RearSlideGrip;
		RearWheelCDO->CorneringStiffness = Tuning->RearCorneringStiffness;
		RearWheelCDO->RollbarScaling = Tuning->RearRollbarScaling;
		RearWheelCDO->SpringRate = Tuning->SpringRate;
		RearWheelCDO->SpringPreload = Tuning->SpringPreload;
		RearWheelCDO->SuspensionDampingRatio = Tuning->DampingRatio;
		RearWheelCDO->SuspensionMaxRaise = Tuning->MaxRaise;
		RearWheelCDO->SuspensionMaxDrop = Tuning->MaxDrop;
	}

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

	const bool bUseReal = ActiveProfileSpec.bUseRealWorldSpecs;
	const float FFric = bUseReal ? ActiveProfileSpec.FrontFriction : Tuning->FrontFriction;
	const float RFric = bUseReal ? ActiveProfileSpec.RearFriction : Tuning->RearFriction;
	const float FBrake = bUseReal ? ActiveProfileSpec.FrontBrakeTorque : Tuning->FrontBrakeTorque;
	const float RBrake = bUseReal ? ActiveProfileSpec.RearBrakeTorque : Tuning->RearBrakeTorque;
	const float HBrake = bUseReal ? ActiveProfileSpec.HandbrakeTorque : Tuning->HandbrakeTorque;
	const float SteerDeg = bUseReal ? ActiveProfileSpec.MaxSteerAngle : Tuning->MaxSteerAngle;
	const bool bABSFlag = bUseReal ? ActiveProfileSpec.bABS : Tuning->bABS;
	const float FSpring = bUseReal ? ActiveProfileSpec.FrontSpringRate : Tuning->SpringRate;
	const float RSpring = bUseReal ? ActiveProfileSpec.RearSpringRate : Tuning->SpringRate;
	const float Damp = bUseReal ? ActiveProfileSpec.SuspensionDampingRatio : Tuning->DampingRatio;
	const float Preload = bUseReal ? ActiveProfileSpec.SpringPreload : Tuning->SpringPreload;
	const float Raise = bUseReal ? ActiveProfileSpec.SuspensionMaxRaise : Tuning->MaxRaise;
	const float Drop = bUseReal ? ActiveProfileSpec.SuspensionMaxDrop : Tuning->MaxDrop;
	const float FRollbar = bUseReal ? ActiveProfileSpec.FrontRollbarScaling : Tuning->FrontRollbarScaling;
	const float RRollbar = bUseReal ? ActiveProfileSpec.RearRollbarScaling : Tuning->RearRollbarScaling;

	for (int32 WheelIndex = 0; WheelIndex < Movement->WheelSetups.Num(); ++WheelIndex)
	{
		const bool bFront = WheelIndex < 2;

		Movement->SetWheelFrictionMultiplier(WheelIndex, bFront ? FFric : RFric);
		Movement->SetWheelMaxBrakeTorque(WheelIndex, bFront ? FBrake : RBrake);
		Movement->SetWheelHandbrakeTorque(WheelIndex, bFront ? 0.0f : HBrake);
		Movement->SetWheelMaxSteerAngle(WheelIndex, bFront ? SteerDeg : 0.0f);
		Movement->SetABSEnabled(WheelIndex, bABSFlag);
		Movement->SetTractionControlEnabled(WheelIndex, Tuning->bTractionControl);
		Movement->SetSuspensionParams(bFront ? FSpring : RSpring, Damp, Preload, Raise, Drop, WheelIndex);
		if (Movement->Wheels.IsValidIndex(WheelIndex) && Movement->Wheels[WheelIndex])
		{
			Movement->Wheels[WheelIndex]->RollbarScaling = bFront ? FRollbar : RRollbar;
		}

		if (bUsingSedanBody)
		{
			Movement->SetWheelRadius(WheelIndex, WheelRadii[WheelIndex]);
		}
	}
}
