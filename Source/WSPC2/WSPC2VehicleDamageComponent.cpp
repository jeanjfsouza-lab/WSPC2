// Copyright Epic Games, Inc. All Rights Reserved.

#include "WSPC2VehicleDamageComponent.h"
#include "WSPC2.h"
#include "WSPC2VehicleProfile.h"
#include "WSPC2VehicleTuning.h"
#include "ChaosWheeledVehicleMovementComponent.h"
#include "ChaosVehicleWheel.h"
#include "Components/BoxComponent.h"
#include "Components/DecalComponent.h"
#include "Components/LightComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SpotLightComponent.h"
#include "Components/PrimitiveComponent.h"
#include "GameFramework/Pawn.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Net/UnrealNetwork.h"
#include "Particles/ParticleSystem.h"
#include "Particles/ParticleSystemComponent.h"

namespace
{
	const TCHAR* PathWindshieldCrack1 = TEXT("/Game/CitySampleVehicles/vehicle13_Car/Material/MI/MI_vehCar_vehicle13_19_Windshield_2.MI_vehCar_vehicle13_19_Windshield_2");
	const TCHAR* PathWindshieldCrack2 = TEXT("/Game/CitySampleVehicles/vehicle13_Car/Material/MI/MI_vehCar_vehicle13_19_windshield_3.MI_vehCar_vehicle13_19_windshield_3");
	const TCHAR* PathLightbarFractured = TEXT("/Game/CitySampleVehicles/vehicle13_Car/Material/MI/MI_vehCar_vehicle13_23_Fractured.MI_vehCar_vehicle13_23_Fractured");
	const TCHAR* PathLightHousingFractured = TEXT("/Game/CitySampleVehicles/vehicle13_Car/Material/M_vehCar_vehicle13_3_Fractured.M_vehCar_vehicle13_3_Fractured");
	const TCHAR* PathGenericGlassFractured = TEXT("/Game/CitySampleVehicles/Material/MI/MI_Veh_Glass_Clear_Fractured.MI_Veh_Glass_Clear_Fractured");

	// Optional Cascade VFX from ProceduralBuildingGenerator (loaded silently; gracefully skipped if pack is absent)
	const TCHAR* PathSteamVFX = TEXT("/Game/ProceduralBuildingGenerator/Effects/Steam/Particle/P_Steam_Jet_Emissive_Subtle.P_Steam_Jet_Emissive_Subtle");
	const TCHAR* PathSmokeVFX = TEXT("/Game/ProceduralBuildingGenerator/Effects/Steam/Particle/P_ChimneySMoke.P_ChimneySMoke");
	const TCHAR* PathWreckSmokeVFX = TEXT("/Game/ProceduralBuildingGenerator/Effects/Smoke/Particle/P_smokeColumn.P_smokeColumn");
	const TCHAR* PathSparkVFX = TEXT("/Game/ProceduralBuildingGenerator/Effects/Sparks/Particle/P_WeldSparks.P_WeldSparks");

	template <typename T>
	T* LoadOptionalAsset(const TCHAR* Path)
	{
		return Cast<T>(StaticLoadObject(T::StaticClass(), nullptr, Path, nullptr, LOAD_NoWarn | LOAD_Quiet));
	}

	UParticleSystemComponent* CreateVehicleParticleComp(AActor* Owner, USceneComponent* Parent, const TCHAR* Name, UParticleSystem* Template, const FVector& RelLoc, const FRotator& RelRot, const FVector& RelScale)
	{
		if (!Owner || !Parent || !Template)
		{
			return nullptr;
		}

		UParticleSystemComponent* PSC = NewObject<UParticleSystemComponent>(Owner, Name);
		if (!PSC)
		{
			return nullptr;
		}

		PSC->SetupAttachment(Parent);
		PSC->SetTemplate(Template);
		PSC->SetRelativeLocation(RelLoc);
		PSC->SetRelativeRotation(RelRot);
		PSC->SetRelativeScale3D(RelScale);
		PSC->bAutoActivate = false;
		PSC->RegisterComponent();
		PSC->DeactivateImmediate();
		return PSC;
	}
}

UWSPC2VehicleDamageComponent::UWSPC2VehicleDamageComponent()
{
	SetIsReplicatedByDefault(true);
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickInterval = 0.033f;

	for (int32 i = 0; i < 4; ++i)
	{
		WheelHubPositions[i] = FVector::ZeroVector;
	}
}

void UWSPC2VehicleDamageComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(UWSPC2VehicleDamageComponent, ZoneDamage);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, WheelHealth);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, PuncturedWheelMask);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, DetachedWheelMask);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, WheelBentAmount);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, EngineBlockIntrusionPct);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, ChassisTwistDeg);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, DisableReason);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, DeformSlots);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, HealthPercent);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, bIsWrecked);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, PropertyDamageDollars);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, CollisionCount);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, LastImpact);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, PanelStates);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, BrokenLightsMask);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, ShatteredGlassMask);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, ImpactHistory);
}

void UWSPC2VehicleDamageComponent::BeginPlay()
{
	Super::BeginPlay();

	AActor* Owner = GetOwner();
	if (!Owner)
	{
		return;
	}

	if (Owner->HasAuthority())
	{
		Owner->OnActorHit.AddUniqueDynamic(this, &UWSPC2VehicleDamageComponent::HandleActorHit);
	}

	// Ensure all collision primitives on the vehicle generate Chaos hit events
	TInlineComponentArray<UPrimitiveComponent*> Primitives(Owner);
	for (UPrimitiveComponent* Prim : Primitives)
	{
		if (Prim && Prim->GetCollisionEnabled() != ECollisionEnabled::NoCollision)
		{
			Prim->SetNotifyRigidBodyCollision(true);
			if (Owner->HasAuthority())
			{
				Prim->OnComponentHit.AddUniqueDynamic(this, &UWSPC2VehicleDamageComponent::HandleComponentHit);
			}
		}
	}

	CaptureBaselineTuning();

	if (GetNetMode() != NM_DedicatedServer)
	{
		SteamParticleTemplate = LoadOptionalAsset<UParticleSystem>(PathSteamVFX);
		SmokeParticleTemplate = LoadOptionalAsset<UParticleSystem>(PathSmokeVFX);
		WreckSmokeParticleTemplate = LoadOptionalAsset<UParticleSystem>(PathWreckSmokeVFX);
		SparkParticleTemplate = LoadOptionalAsset<UParticleSystem>(PathSparkVFX);
		DebrisCubeMesh = LoadOptionalAsset<UStaticMesh>(TEXT("/Engine/BasicShapes/Cube.Cube"));
		LocalizedDamageDecalMat = LoadOptionalAsset<UMaterialInterface>(TEXT("/Game/Vehicles/Imported/Materials/M_WSPC2_DamageDecal.M_WSPC2_DamageDecal"));

		if (USceneComponent* RootComp = Owner->GetRootComponent())
		{
			ImpactSparkLight = NewObject<UPointLightComponent>(Owner, TEXT("DamageImpactSparkLight"));
			if (ImpactSparkLight)
			{
				ImpactSparkLight->SetupAttachment(RootComp);
				ImpactSparkLight->SetLightColor(FLinearColor(1.0f, 0.58f, 0.14f));
				ImpactSparkLight->SetIntensity(75000.0f);
				ImpactSparkLight->SetAttenuationRadius(750.0f);
				ImpactSparkLight->SetCastShadows(false);
				ImpactSparkLight->SetVisibility(false);
				ImpactSparkLight->RegisterComponent();
			}

			EngineHazardLight = NewObject<UPointLightComponent>(Owner, TEXT("DamageEngineHazardLight"));
			if (EngineHazardLight)
			{
				EngineHazardLight->SetupAttachment(RootComp);
				EngineHazardLight->SetRelativeLocation(FVector(185.0f, 0.0f, 88.0f));
				EngineHazardLight->SetLightColor(FLinearColor(1.0f, 0.28f, 0.04f));
				EngineHazardLight->SetIntensity(28000.0f);
				EngineHazardLight->SetAttenuationRadius(580.0f);
				EngineHazardLight->SetCastShadows(false);
				EngineHazardLight->SetVisibility(false);
				EngineHazardLight->RegisterComponent();
			}

			// Jet points along +X in local emitter space; rotate +76 deg pitch so steam/smoke vents upward from hood
			HoodSteamComp = CreateVehicleParticleComp(
				Owner, RootComp, TEXT("DamageHoodSteamVFX"), SteamParticleTemplate,
				FVector(182.0f, 0.0f, 102.0f), FRotator(76.0f, 0.0f, 0.0f), FVector(0.55f));

			HoodSmokeComp = CreateVehicleParticleComp(
				Owner, RootComp, TEXT("DamageHoodSmokeVFX"), SmokeParticleTemplate,
				FVector(176.0f, 0.0f, 98.0f), FRotator(85.0f, 0.0f, 0.0f), FVector(0.38f));

			RimSparkComp = CreateVehicleParticleComp(
				Owner, RootComp, TEXT("DamageRimSparkVFX"), SparkParticleTemplate,
				FVector::ZeroVector, FRotator(15.0f, 180.0f, 0.0f), FVector(0.28f));

			HeadlightSpots.Reset();
			for (int32 i = 0; i < 2; ++i)
			{
				const FString Name = (i == 0) ? TEXT("DamageHeadlightSpotL") : TEXT("DamageHeadlightSpotR");
				USpotLightComponent* Spot = NewObject<USpotLightComponent>(Owner, *Name);
				if (Spot)
				{
					Spot->SetupAttachment(RootComp);
					Spot->SetRelativeLocation(FVector(230.0f, (i == 0) ? -68.0f : 68.0f, 64.0f));
					Spot->SetRelativeRotation(FRotator(-5.0f, 0.0f, 0.0f));
					Spot->SetLightColor(FLinearColor(1.0f, 0.96f, 0.86f));
					Spot->SetIntensity(28000.0f);
					Spot->SetAttenuationRadius(3800.0f);
					Spot->SetInnerConeAngle(16.0f);
					Spot->SetOuterConeAngle(36.0f);
					Spot->SetCastShadows(false);
					Spot->SetVisibility(false);
					Spot->RegisterComponent();
				}
				HeadlightSpots.Add(Spot);
			}

			TaillightGlows.Reset();
			for (int32 i = 0; i < 2; ++i)
			{
				const FString Name = (i == 0) ? TEXT("DamageTaillightGlowL") : TEXT("DamageTaillightGlowR");
				UPointLightComponent* Glow = NewObject<UPointLightComponent>(Owner, *Name);
				if (Glow)
				{
					Glow->SetupAttachment(RootComp);
					Glow->SetRelativeLocation(FVector(-245.0f, (i == 0) ? -68.0f : 68.0f, 70.0f));
					Glow->SetLightColor(FLinearColor(1.0f, 0.12f, 0.06f));
					Glow->SetIntensity(6500.0f);
					Glow->SetAttenuationRadius(420.0f);
					Glow->SetCastShadows(false);
					Glow->SetVisibility(false);
					Glow->RegisterComponent();
				}
				TaillightGlows.Add(Glow);
			}
		}
	}
}

void UWSPC2VehicleDamageComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	ClearContactDamageDecals();
	if (DeformableChassis)
	{
		DeformableChassis->ResetAndDestroy(BodyMesh, GlassMesh);
		DeformableChassis.Reset();
	}
	Super::EndPlay(EndPlayReason);
}

void UWSPC2VehicleDamageComponent::CaptureBaselineTuning()
{
	AActor* Owner = GetOwner();
	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
	const UChaosWheeledVehicleMovementComponent* VehMove = Owner ? Owner->FindComponentByClass<UChaosWheeledVehicleMovementComponent>() : nullptr;

	// Prefer live Chaos movement & wheel instance baselines once AWSPC2SportsCar has applied profile specs
	if (VehMove && VehMove->Wheels.Num() >= 4)
	{
		BaseMaxTorque = FMath::Max(VehMove->EngineSetup.MaxTorque, 80.0f);
		BaseDragCoefficient = VehMove->DragCoefficient;
		BaseDownforceCoefficient = VehMove->DownforceCoefficient;
		for (int32 w = 0; w < 4; ++w)
		{
			if (const UChaosVehicleWheel* W = VehMove->Wheels[w])
			{
				WheelBaseFriction[w] = W->FrictionForceMultiplier;
				WheelBaseBrakeTorque[w] = W->MaxBrakeTorque;
				WheelBaseSteerAngle[w] = W->MaxSteerAngle;
				WheelBaseABS[w] = W->bABSEnabled;
			}
		}
		bBaselinesCaptured = true;
		return;
	}

	if (Tuning)
	{
		BaseMaxTorque = FMath::Max(Tuning->MaxTorqueNm * BaselineTorqueScale, 100.0f);
		BaseDragCoefficient = Tuning->DragCoefficient;
		BaseDownforceCoefficient = Tuning->DownforceCoefficient;

		for (int32 w = 0; w < 4; ++w)
		{
			const bool bFront = (w < 2);
			WheelBaseFriction[w] = bFront ? Tuning->FrontFriction : Tuning->RearFriction;
			WheelBaseBrakeTorque[w] = bFront ? Tuning->FrontBrakeTorque : Tuning->RearBrakeTorque;
			WheelBaseSteerAngle[w] = bFront ? Tuning->MaxSteerAngle : 0.0f;
			WheelBaseABS[w] = Tuning->bABS;
		}
		bBaselinesCaptured = true;
	}
}

void UWSPC2VehicleDamageComponent::ConfigureFromVehicleProfile(
	const FWSPC2VehicleProfileSpec& Spec,
	const FVector InWheelHubPositions[4],
	const float InWheelRadii[4])
{
	ArmorDamageScaleOverride = Spec.ArmorDamageScale;
	GroundClearanceCm = FMath::Clamp(Spec.GroundClearanceCm, 10.0f, 52.0f);

	const FVector SafeMin(
		FMath::Min(Spec.EngineBlockMinCm.X, Spec.EngineBlockMaxCm.X),
		FMath::Min(Spec.EngineBlockMinCm.Y, Spec.EngineBlockMaxCm.Y),
		FMath::Min(Spec.EngineBlockMinCm.Z, Spec.EngineBlockMaxCm.Z));
	const FVector SafeMax(
		FMath::Max(Spec.EngineBlockMinCm.X, Spec.EngineBlockMaxCm.X),
		FMath::Max(Spec.EngineBlockMinCm.Y, Spec.EngineBlockMaxCm.Y),
		FMath::Max(Spec.EngineBlockMinCm.Z, Spec.EngineBlockMaxCm.Z));
	EngineBlockBox = FBox(SafeMin, SafeMax);

	for (int32 i = 0; i < 4; ++i)
	{
		WheelHubPositions[i] = InWheelHubPositions[i];
		WheelBaseRadii[i] = InWheelRadii[i] > 5.0f ? InWheelRadii[i] : 35.2f;
	}

	const float HalfTrackCm = FMath::Max(0.5f * FMath::Abs(InWheelHubPositions[1].Y - InWheelHubPositions[0].Y), 55.0f);
	const float HalfWheelbaseCm = FMath::Max(0.5f * FMath::Abs(InWheelHubPositions[0].X - InWheelHubPositions[2].X), 85.0f);
	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
	if (Tuning && Tuning->DamageFloorTouchTwistOverrideDeg > 0.5f)
	{
		FloorTouchTwistDeg = Tuning->DamageFloorTouchTwistOverrideDeg;
	}
	else
	{
		const float EffectiveSpan = FMath::Lerp(HalfTrackCm, HalfWheelbaseCm, 0.35f);
		FloorTouchTwistDeg = FMath::Clamp(FMath::RadiansToDegrees(FMath::Atan2(GroundClearanceCm, EffectiveSpan)), 6.0f, 18.0f);
	}

	if (EngineHazardLight)
	{
		EngineHazardLight->SetRelativeLocation(EngineBlockBox.GetCenter() + FVector(0.0f, 0.0f, 18.0f));
	}
	if (HoodSteamComp)
	{
		HoodSteamComp->SetRelativeLocation(EngineBlockBox.GetCenter() + FVector(0.0f, 0.0f, 28.0f));
	}
	if (HoodSmokeComp)
	{
		HoodSmokeComp->SetRelativeLocation(EngineBlockBox.GetCenter() + FVector(0.0f, 0.0f, 24.0f));
	}

	UE_LOG(LogWSPC2, Log, TEXT("VehicleDamage [%s]: EngineBox=(%s..%s), GC=%.1f cm, FloorTouchTwistDeg=%.1f deg, Armor=%.2f"),
		*GetNameSafe(GetOwner()), *SafeMin.ToCompactString(), *SafeMax.ToCompactString(), GroundClearanceCm, FloorTouchTwistDeg,
		ArmorDamageScaleOverride > 0.01f ? ArmorDamageScaleOverride : (Spec.bIsPoliceCruiser ? (Tuning ? Tuning->PoliceArmorDamageScale : 0.58f) : 1.0f));
}

void UWSPC2VehicleDamageComponent::SetDetachedWheelVisualMeshOverride(int32 WheelIndex, UStaticMesh* Mesh)
{
	if (WheelIndex >= 0 && WheelIndex < 4)
	{
		WheelVisualOverrides[WheelIndex] = Mesh;
	}
}

void UWSPC2VehicleDamageComponent::SetupDamageRig(
	UPrimitiveComponent* InRootPhysicsBody,
	UStaticMeshComponent* InBodyMesh,
	UStaticMeshComponent* InGlassMesh,
	const TArray<TObjectPtr<UStaticMeshComponent>>& InWheelMeshes,
	const FVector InWheelHubPositions[4],
	const float InWheelRadii[4],
	bool bInIsPoliceCruiser)
{
	RootPhysicsBody = InRootPhysicsBody;
	BodyMesh = InBodyMesh;
	GlassMesh = InGlassMesh;
	WheelMeshes = InWheelMeshes;
	bIsPoliceCruiser = bInIsPoliceCruiser;

	for (int32 i = 0; i < 4; ++i)
	{
		WheelHubPositions[i] = InWheelHubPositions[i];
		WheelBaseRadii[i] = InWheelRadii[i] > 5.0f ? InWheelRadii[i] : 35.2f;
	}

	CaptureBaselineTuning();

	if (RootPhysicsBody)
	{
		RootPhysicsBody->SetNotifyRigidBodyCollision(true);
	}

	if (AActor* Owner = GetOwner())
	{
		TInlineComponentArray<UPrimitiveComponent*> Primitives(Owner);
		for (UPrimitiveComponent* Prim : Primitives)
		{
			if (Prim && Prim->GetCollisionEnabled() != ECollisionEnabled::NoCollision)
			{
				Prim->SetNotifyRigidBodyCollision(true);
				if (Owner->HasAuthority())
				{
					Prim->OnComponentHit.AddUniqueDynamic(this, &UWSPC2VehicleDamageComponent::HandleComponentHit);
				}
			}
		}
	}

	ClearContactDamageDecals();
	if (DeformableChassis)
	{
		DeformableChassis->ResetAndDestroy(BodyMesh, GlassMesh);
		DeformableChassis.Reset();
	}
	for (int32 i = 0; i < 9; ++i)
	{
		PanelStates[i] = 0;
		AppliedPanelStates[i] = 0;
	}
	BrokenLightsMask = 0;
	ShatteredGlassMask = 0;
	AppliedShatteredGlassMask = 0;
	ImpactHistory.Reset();
	AppliedImpactCount = 0;
	for (int32 i = 0; i < 5; ++i)
	{
		LightFlickerTimer[i] = 0.0f;
	}

	GlassCrackStage = 0;
	bSideGlassFractured = false;
	bLightbarFractured = false;
	bHeadlightHousingFractured = false;

	if (BodyMesh)
	{
		InitialBodyRelativeTransform = BodyMesh->GetRelativeTransform();
		BodyMIDs.Reset();
		OriginalBodyMaterials.Reset();
		const int32 NumMats = BodyMesh->GetNumMaterials();
		for (int32 Slot = 0; Slot < NumMats; ++Slot)
		{
			UMaterialInterface* BaseMat = BodyMesh->GetMaterial(Slot);
			OriginalBodyMaterials.Add(BaseMat);
			if (BaseMat)
			{
				UMaterialInstanceDynamic* MID = BodyMesh->CreateDynamicMaterialInstance(Slot, BaseMat);
				BodyMIDs.Add(MID);
			}
			else
			{
				BodyMIDs.Add(nullptr);
			}
		}

		// Reposition hood VFX to match the active vehicle's front hood geometry
		if (UStaticMesh* StaticMesh = BodyMesh->GetStaticMesh())
		{
			const FBoxSphereBounds LocalBounds = StaticMesh->GetBounds();
			const FBox BodyBox = LocalBounds.GetBox().TransformBy(InitialBodyRelativeTransform);
			const float HoodX = FMath::Lerp(BodyBox.GetCenter().X, BodyBox.Max.X, 0.72f);
			const float HoodZ = FMath::Lerp(BodyBox.Min.Z, BodyBox.Max.Z, 0.58f);

			if (EngineHazardLight)
			{
				EngineHazardLight->SetRelativeLocation(FVector(HoodX, 0.0f, HoodZ - 6.0f));
			}
			if (HoodSteamComp)
			{
				HoodSteamComp->SetRelativeLocation(FVector(HoodX, 0.0f, HoodZ + 8.0f));
			}
			if (HoodSmokeComp)
			{
				HoodSmokeComp->SetRelativeLocation(FVector(HoodX - 6.0f, 0.0f, HoodZ + 4.0f));
			}

			const float HeadlightZ = FMath::Lerp(BodyBox.Min.Z, BodyBox.Max.Z, 0.42f);
			const float TaillightZ = FMath::Lerp(BodyBox.Min.Z, BodyBox.Max.Z, 0.48f);
			const float SideY = FMath::Max(45.0f, BodyBox.GetExtent().Y * 0.72f);
			if (HeadlightSpots.IsValidIndex(0) && HeadlightSpots[0])
			{
				HeadlightSpots[0]->SetRelativeLocation(FVector(BodyBox.Max.X - 6.0f, -SideY, HeadlightZ));
			}
			if (HeadlightSpots.IsValidIndex(1) && HeadlightSpots[1])
			{
				HeadlightSpots[1]->SetRelativeLocation(FVector(BodyBox.Max.X - 6.0f, SideY, HeadlightZ));
			}
			if (TaillightGlows.IsValidIndex(0) && TaillightGlows[0])
			{
				TaillightGlows[0]->SetRelativeLocation(FVector(BodyBox.Min.X + 6.0f, -SideY, TaillightZ));
			}
			if (TaillightGlows.IsValidIndex(1) && TaillightGlows[1])
			{
				TaillightGlows[1]->SetRelativeLocation(FVector(BodyBox.Min.X + 6.0f, SideY, TaillightZ));
			}
		}
	}

	if (GlassMesh)
	{
		InitialGlassRelativeTransform = GlassMesh->GetRelativeTransform();
		OriginalGlassMaterials.Reset();
		GlassMIDs.Reset();
		const int32 NumGlassMats = GlassMesh->GetNumMaterials();
		for (int32 Slot = 0; Slot < NumGlassMats; ++Slot)
		{
			UMaterialInterface* GMat = GlassMesh->GetMaterial(Slot);
			OriginalGlassMaterials.Add(GMat);
			GlassMIDs.Add(GMat ? GlassMesh->CreateDynamicMaterialInstance(Slot, GMat) : nullptr);
		}
	}

	if (bIsPoliceCruiser)
	{
		PoliceWindshieldCrack1 = LoadOptionalAsset<UMaterialInterface>(PathWindshieldCrack1);
		PoliceWindshieldCrack2 = LoadOptionalAsset<UMaterialInterface>(PathWindshieldCrack2);
		PoliceLightbarFractured = LoadOptionalAsset<UMaterialInterface>(PathLightbarFractured);
		PoliceLightHousingFractured = LoadOptionalAsset<UMaterialInterface>(PathLightHousingFractured);
	}
	else
	{
		PoliceWindshieldCrack1 = nullptr;
		PoliceWindshieldCrack2 = nullptr;
		PoliceLightbarFractured = nullptr;
		PoliceLightHousingFractured = nullptr;
	}

	GenericGlassFractured = LoadOptionalAsset<UMaterialInterface>(PathGenericGlassFractured);

	bRigConfigured = true;
	RefreshAllDamageSystems();
}

void UWSPC2VehicleDamageComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	AActor* Owner = GetOwner();
	if (!Owner)
	{
		return;
	}

	// Update roof lightbar electrical reliability & flickering
	const float RoofDmg = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Roof)];
	if (bIsWrecked || RoofDmg >= 0.72f)
	{
		CurrentSirenHealthFactor = 0.0f;
	}
	else if (RoofDmg >= 0.25f || bLightbarFractured)
	{
		const float Integrity = FMath::Clamp(1.0f - (RoofDmg - 0.20f) / 0.52f, 0.15f, 1.0f);
		const float Pulse = 0.5f + 0.5f * FMath::Sin(HazardFlickerPhase * 1.7f + 0.8f);
		CurrentSirenHealthFactor = (Pulse > (0.65f - Integrity * 0.5f)) ? Integrity : 0.08f;
	}
	else
	{
		CurrentSirenHealthFactor = 1.0f;
	}

	// Engine misfire / sputter cycles once radiator/engine block has moderate-to-heavy damage or >12% intrusion
	const float EngineStress = FMath::Max3(
		ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Front)],
		(100.0f - HealthPercent) * 0.0085f,
		EngineBlockIntrusionPct / 30.0f);
	if (!bIsWrecked && EngineStress >= 0.36f)
	{
		if (MisfireCutRemaining > 0.0f)
		{
			MisfireCutRemaining -= DeltaTime;
		}
		else
		{
			MisfireTimer -= DeltaTime;
			if (MisfireTimer <= 0.0f)
			{
				const float StressAlpha = FMath::Clamp((EngineStress - 0.36f) / 0.64f, 0.0f, 1.0f);
				MisfireCutRemaining = FMath::Lerp(0.14f, 0.34f, StressAlpha);
				MisfireTimer = FMath::Lerp(3.2f, 0.95f, StressAlpha) + FMath::FRandRange(0.0f, 0.7f);
			}
		}
	}
	else
	{
		MisfireCutRemaining = 0.0f;
	}

	// High-speed suspension wobble phase when front hubs or tyres are battered
	const float SpeedKmh = Owner->GetVelocity().Size() * 0.036f;
	if (SpeedKmh > 12.0f)
	{
		ShimmyPhase += DeltaTime * FMath::Clamp(SpeedKmh * 0.32f, 4.0f, 32.0f);
	}

	if (GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	if (DeformableChassis && DeformableChassis->IsActive())
	{
		DeformableChassis->TickLoosePanels(DeltaTime, SpeedKmh);
	}
	UpdateDynamicCornerLights(DeltaTime);

	HazardFlickerPhase += DeltaTime * 19.0f;

	if (ImpactSparkLight && SparkFlashRemaining > 0.0f)
	{
		SparkFlashRemaining -= DeltaTime;
		if (SparkFlashRemaining <= 0.0f)
		{
			ImpactSparkLight->SetVisibility(false);
		}
		else
		{
			ImpactSparkLight->SetIntensity(85000.0f * FMath::Clamp(SparkFlashRemaining / 0.12f, 0.0f, 1.0f));
		}
	}

	if (EngineHazardLight)
	{
		const bool bShowEngineFire = bIsWrecked || EngineBlockIntrusionPct >= 14.0f || ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Front)] > 0.62f;
		EngineHazardLight->SetVisibility(bShowEngineFire);
		if (bShowEngineFire)
		{
			const float Flicker = 0.60f + 0.40f * FMath::Sin(HazardFlickerPhase) * FMath::Cos(HazardFlickerPhase * 2.3f);
			EngineHazardLight->SetIntensity((bIsWrecked ? 52000.0f : 24000.0f) * Flicker);
		}
	}

	// Continuous rim, detached hub, or twisted underbody scraping sparks while moving
	if (RimSparkComp)
	{
		int32 ActiveSparkWheel = -1;
		for (int32 w = 0; w < 4; ++w)
		{
			if (IsWheelDetached(w) || bWheelPunctured[w])
			{
				ActiveSparkWheel = w;
				break;
			}
		}

		const bool bFloorScrape = (GetMaxChassisTwistDeg() >= FloorTouchTwistDeg * 0.80f);
		const bool bBumperDrag = (DeformableChassis && DeformableChassis->IsAnyBumperDragging());
		const bool bEmitSparks = ((ActiveSparkWheel >= 0 || bFloorScrape || bBumperDrag) && SpeedKmh > 12.0f);
		if (bEmitSparks)
		{
			const FVector SparkLoc = (ActiveSparkWheel >= 0)
				? FVector(WheelHubPositions[ActiveSparkWheel].X, WheelHubPositions[ActiveSparkWheel].Y,
					IsWheelDetached(ActiveSparkWheel) ? 6.0f : FMath::Max(6.0f, WheelHubPositions[ActiveSparkWheel].Z - WheelBaseRadii[ActiveSparkWheel] + 7.0f))
				: (bBumperDrag ? FVector((DeformableChassis->GetPanelState(EWSPC2DetachablePanel::FrontBumper) == EWSPC2PanelDamageState::Loose) ? 235.0f : -235.0f, 0.0f, 8.0f)
					: FVector(0.0f, (ChassisTwistDeg.X >= 0.0f ? 62.0f : -62.0f), 6.0f));
			RimSparkComp->SetRelativeLocation(SparkLoc);
			if (!RimSparkComp->IsActive())
			{
				RimSparkComp->Activate(true);
			}
		}
		else if (RimSparkComp->IsActive())
		{
			RimSparkComp->Deactivate();
		}
	}
}

void UWSPC2VehicleDamageComponent::HandleComponentHit(UPrimitiveComponent* HitComp, AActor* OtherActor, UPrimitiveComponent* OtherComp, FVector NormalImpulse, const FHitResult& Hit)
{
	HandleActorHit(GetOwner(), OtherActor, NormalImpulse, Hit);
}

void UWSPC2VehicleDamageComponent::HandleActorHit(AActor* SelfActor, AActor* OtherActor, FVector NormalImpulse, const FHitResult& Hit)
{
	if (!SelfActor || !SelfActor->HasAuthority() || !GetWorld())
	{
		return;
	}

	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
	if (Tuning && !Tuning->bEnableVehicleDamage)
	{
		return;
	}

	// Only ignore upward road/curb contact normals when the vehicle is upright; if rolled or upside-down, hitting ground crushes the roof/sides
	const float UpDot = FVector::DotProduct(FVector::UpVector, SelfActor->GetActorUpVector());
	if (UpDot > 0.40f && Hit.ImpactNormal.Z > 0.78f)
	{
		return;
	}

	const double Now = GetWorld()->GetTimeSeconds();
	const double Cooldown = Tuning ? Tuning->DamageScrapeCooldown : 0.085;
	if (Now - LastHitTimeSeconds < Cooldown)
	{
		return;
	}

	const FVector OtherVel = OtherActor ? OtherActor->GetVelocity() : FVector::ZeroVector;
	const FVector RelVel = SelfActor->GetVelocity() - OtherVel;
	const FVector HitNormal = Hit.ImpactNormal.IsNearlyZero() ? FVector::UpVector : FVector(Hit.ImpactNormal).GetSafeNormal();

	const float NormalSpeedKmh = FMath::Abs(FVector::DotProduct(RelVel, HitNormal)) * 0.036f;
	const float TangentSpeedKmh = (RelVel - HitNormal * FVector::DotProduct(RelVel, HitNormal)).Size() * 0.036f;
	const float EffectiveSpeedKmh = FMath::Max(NormalSpeedKmh, TangentSpeedKmh * 0.42f);
	const float ImpulseMag = NormalImpulse.Size();

	const float MinSpeed = Tuning ? Tuning->DamageMinSpeedKmh : 6.5f;
	const float MinImpulse = Tuning ? Tuning->DamageMinImpulse : 95000.0f;

	// Filter out stationary resting contacts while preserving light scrapes and bumper taps
	if (EffectiveSpeedKmh < MinSpeed && ImpulseMag < MinImpulse)
	{
		return;
	}
	if (EffectiveSpeedKmh < 3.5f && ImpulseMag < MinImpulse * 2.2f)
	{
		return;
	}

	LastHitTimeSeconds = Now;
	const FVector HitPoint = Hit.ImpactPoint.IsNearlyZero() ? SelfActor->GetActorLocation() : FVector(Hit.ImpactPoint);

	ApplyDirectImpact(HitPoint, HitNormal, EffectiveSpeedKmh, ImpulseMag);
}

void UWSPC2VehicleDamageComponent::ApplyDirectImpact(const FVector& WorldImpactPoint, const FVector& WorldImpactNormal, float ImpactSpeedKmh, float ImpulseMagnitude)
{
	AActor* Owner = GetOwner();
	if (!Owner || !Owner->HasAuthority())
	{
		return;
	}

	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
	if (Tuning && !Tuning->bEnableVehicleDamage)
	{
		return;
	}

	const float MinSpeed = Tuning ? Tuning->DamageMinSpeedKmh : 6.5f;
	const float SevereSpeed = Tuning ? Tuning->DamageSevereSpeedKmh : 105.0f;
	const float SevereImpulse = Tuning ? Tuning->DamageSevereImpulse : 3800000.0f;
	const float ArmorScale = (ArmorDamageScaleOverride > 0.01f)
		? ArmorDamageScaleOverride
		: (bIsPoliceCruiser ? (Tuning ? Tuning->PoliceArmorDamageScale : 0.58f) : 1.0f);
	const float HealthMult = Tuning ? Tuning->DamageZoneToHealthScale : 27.5f;
	const float BlowoutSev = Tuning ? Tuning->DamageWheelBlowoutSeverity : 0.60f;
	const float BendSev = Tuning ? Tuning->DamageWheelBendSeverity : 0.35f;
	const float DetachSev = Tuning ? Tuning->DamageWheelDetachSeverity : 0.80f;

	const float SpeedFactor = FMath::Max(0.0f, (ImpactSpeedKmh - (MinSpeed * 0.65f)) / FMath::Max(SevereSpeed - MinSpeed, 20.0f));
	const float ImpulseFactor = ImpulseMagnitude / FMath::Max(SevereImpulse, 100000.0f);
	const float Severity = FMath::Clamp(FMath::Max(SpeedFactor, ImpulseFactor), 0.04f, 1.45f);

	const FVector LocalHit = Owner->GetActorTransform().InverseTransformPosition(WorldImpactPoint);
	FVector LocalNormal = Owner->GetActorTransform().InverseTransformVectorNoScale(WorldImpactNormal).GetSafeNormal();
	if (LocalNormal.IsNearlyZero())
	{
		LocalNormal = -LocalHit.GetSafeNormal();
	}
	// Resolve reliable inward crush vector pointing toward vehicle interior regardless of caller normal sign convention
	FVector InwardDir = LocalNormal;
	if (FVector::DotProduct(InwardDir, -LocalHit.GetSafeNormal()) < -0.15f)
	{
		InwardDir = -LocalNormal;
	}
	InwardDir = InwardDir.GetSafeNormal();
	const float UpDot = FVector::DotProduct(FVector::UpVector, Owner->GetActorUpVector());

	EWSPC2DamageZone Zone = EWSPC2DamageZone::Front;
	if (UpDot < 0.25f || LocalHit.Z > 125.0f)
	{
		Zone = EWSPC2DamageZone::Roof;
	}
	else if (FMath::Abs(LocalHit.X) >= FMath::Abs(LocalHit.Y) * 1.12f)
	{
		Zone = (LocalHit.X >= 0.0f) ? EWSPC2DamageZone::Front : EWSPC2DamageZone::Rear;
	}
	else
	{
		Zone = (LocalHit.Y >= 0.0f) ? EWSPC2DamageZone::Right : EWSPC2DamageZone::Left;
	}

	const int32 ZoneIdx = static_cast<int32>(Zone);
	ZoneDamage[ZoneIdx] = FMath::Clamp(ZoneDamage[ZoneIdx] + Severity * 0.44f * ArmorScale, 0.0f, 1.0f);

	HealthPercent = FMath::Clamp(HealthPercent - Severity * HealthMult * ArmorScale, 0.0f, 100.0f);
	if (HealthPercent <= 0.0f && !bIsWrecked)
	{
		TriggerVehicleDisabled(EWSPC2VehicleDisableReason::HealthDepleted);
	}
	++CollisionCount;
	PropertyDamageDollars += FMath::Max(55, FMath::RoundToInt(Severity * 1750.0f));

	// Rule 1: Engine block intrusion (> 30% estimated penetration disables the vehicle immediately)
	EvaluateEngineBlockIntrusion(LocalHit, InwardDir, Severity, ArmorScale);

	// Rule 3: Structural chassis torsion/twist (> X deg where floorpan contacts ground disables the vehicle)
	EvaluateChassisTwist(LocalHit, InwardDir, Severity, ArmorScale);

	// Localized dent & scratch slot for M_WSPC2_VehicleDamage
	RecordImpactDeformSlot(LocalHit, InwardDir, Severity);

	// Burnout / Wreckfest real-time 3D sheet-metal crumpling, detachable panels & shattering lights
	EnsureDeformableChassis();
	// Outer sheet metal crumples visibly even on armored police cruisers, while engine/chassis integrity retains ArmorScale
	const float VisualArmorScale = FMath::Lerp(ArmorScale, 1.0f, 0.65f);
	FWSPC2MeshImpactRecord MeshRec;
	MeshRec.LocalPos = LocalHit;
	MeshRec.InwardDir = InwardDir;
	MeshRec.Severity = Severity;
	MeshRec.RadiusCm = FMath::Clamp(58.0f + Severity * 62.0f, 52.0f, 136.0f);
	MeshRec.DepthCm = FMath::Clamp(Severity * 52.0f * VisualArmorScale, 10.0f, 62.0f);
	if (ImpactHistory.Num() >= 16)
	{
		ImpactHistory.RemoveAt(0);
	}
	ImpactHistory.Add(MeshRec);
	if (DeformableChassis && DeformableChassis->IsActive())
	{
		DeformableChassis->ApplyPlasticImpact(MeshRec, ChassisTwistDeg, FloorTouchTwistDeg);
		AppliedImpactCount = ImpactHistory.Num();
		SpawnLocalizedContactDecal(LocalHit, InwardDir, Severity);
	}
	EvaluatePanelsAndLightsFromImpact(LocalHit, WorldImpactNormal, Severity, ImpactSpeedKmh, Zone);

	// Corner wheel damage: progressive bend/camber/toe/wobble, blowout, and detachment (Rule 2: >=2 wheels disables)
	if (Zone != EWSPC2DamageZone::Roof && Severity >= 0.16f)
	{
		int32 BestWheel = -1;
		float BestDist = 145.0f;
		for (int32 w = 0; w < 4; ++w)
		{
			if (!WheelHubPositions[w].IsNearlyZero())
			{
				const float Dist = FVector::Dist(LocalHit, WheelHubPositions[w]);
				if (Dist < BestDist)
				{
					BestDist = Dist;
					BestWheel = w;
				}
			}
		}

		if (BestWheel >= 0)
		{
			const float ProxAlpha = FMath::Clamp(1.0f - (BestDist / 145.0f) * 0.45f, 0.55f, 1.0f);
			// Wheels and suspension hubs are exposed outside the armored body shell
			const float WheelArmorScale = FMath::Lerp(ArmorScale, 1.0f, 0.45f);
			const float CornerSev = Severity * ProxAlpha * WheelArmorScale;
			WheelHealth[BestWheel] = FMath::Clamp(WheelHealth[BestWheel] - CornerSev * 0.90f, 0.0f, 1.0f);

			if (CornerSev >= BendSev || WheelHealth[BestWheel] < 0.72f)
			{
				WheelBentAmount[BestWheel] = FMath::Clamp(WheelBentAmount[BestWheel] + CornerSev * 0.70f, 0.0f, 1.0f);
			}

			const float Threshold = bIsPoliceCruiser ? BlowoutSev : BlowoutSev * 0.72f;
			if (WheelHealth[BestWheel] <= 0.0f || Severity >= Threshold)
			{
				PunctureWheel(BestWheel);
			}

			if (!IsWheelDetached(BestWheel) && (CornerSev >= DetachSev || (IsWheelPunctured(BestWheel) && WheelHealth[BestWheel] <= 0.14f)))
			{
				DetachWheel(BestWheel, WorldImpactNormal, ImpactSpeedKmh);
			}
		}
	}

	// Catastrophic health wreck can burst a weakened wheel on the hardest-hit corner
	if (bIsWrecked && GetPuncturedWheelCount() == 0 && GetDetachedWheelCount() == 0)
	{
		const int32 WorstCornerWheel = (ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Front)] >= ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Rear)])
			? ((ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Right)] >= ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Left)]) ? 1 : 0)
			: ((ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Right)] >= ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Left)]) ? 3 : 2);
		PunctureWheel(WorstCornerWheel);
	}

	RecalculateWheelCamberAndFlags();

	LastImpact.WorldPoint = WorldImpactPoint;
	LastImpact.WorldNormal = WorldImpactNormal;
	LastImpact.Severity = Severity;
	LastImpact.Zone = static_cast<uint8>(ZoneIdx);
	++LastImpact.Sequence;

	TriggerImpactBurstFX(WorldImpactPoint, WorldImpactNormal, Severity);
	RefreshAllDamageSystems();

	UE_LOG(LogWSPC2, Log, TEXT("ChaosDamage [%s]: tier=%s reason=%s zone=%d sev=%.2f speed=%.1f -> hull=%.1f%% eng=%.0f%% engIntrus=%.1f%% twist=%.1f/%.1f deg flat=%d det=%d"),
		*GetNameSafe(Owner), GetDamageStageName(), GetDisableReasonName(), ZoneIdx, Severity, ImpactSpeedKmh,
		HealthPercent, GetEngineHealthTorqueFactor() * 100.0f, EngineBlockIntrusionPct,
		GetMaxChassisTwistDeg(), FloorTouchTwistDeg, GetPuncturedWheelCount(), GetDetachedWheelCount());

	OnVehicleDamaged.Broadcast(Zone, Severity, HealthPercent);
}

void UWSPC2VehicleDamageComponent::EvaluateEngineBlockIntrusion(const FVector& LocalHit, const FVector& InwardDir, float Severity, float ArmorScale)
{
	if (!EngineBlockBox.IsValid)
	{
		return;
	}

	// Project wide Chaos bumper/corner contacts toward the engine bay on axial impacts
	FVector EvalHit = LocalHit;
	const FVector BoxCenter = EngineBlockBox.GetCenter();
	const float AxialAlign = FMath::Abs(InwardDir.X);
	const bool bSameEndAsEngine = (BoxCenter.X >= 0.0f && LocalHit.X > 30.0f) || (BoxCenter.X < 0.0f && LocalHit.X < -30.0f);
	if (AxialAlign > 0.55f && bSameEndAsEngine)
	{
		const float PullAlpha = FMath::GetMappedRangeValueClamped(FVector2f(0.55f, 0.90f), FVector2f(0.45f, 0.85f), AxialAlign);
		const float ClampedY = FMath::Clamp(EvalHit.Y, EngineBlockBox.Min.Y + 8.0f, EngineBlockBox.Max.Y - 8.0f);
		const float ClampedZ = FMath::Clamp(EvalHit.Z, EngineBlockBox.Min.Z + 10.0f, EngineBlockBox.Max.Z - 10.0f);
		EvalHit.Y = FMath::Lerp(EvalHit.Y, ClampedY, PullAlpha);
		EvalHit.Z = FMath::Lerp(EvalHit.Z, ClampedZ, PullAlpha);
	}

	const float RadiusCm = 28.0f + Severity * 30.0f;
	const float ReachArmor = (ArmorScale >= 0.40f) ? FMath::Max(ArmorScale, 0.65f) : ArmorScale;
	const float ReachCm = FMath::Clamp(Severity * ReachArmor * 102.0f, 12.0f, 125.0f);
	const FBox ExpandedBox = EngineBlockBox.ExpandBy(RadiusCm * 0.55f);

	// Sample along the inward crush path from impact point to max crush reach
	float MaxPenRatio = 0.0f;
	const FVector BoxExtent = EngineBlockBox.GetExtent().ComponentMax(FVector(18.0f));
	for (int32 Step = 1; Step <= 6; ++Step)
	{
		const FVector Sample = EvalHit + InwardDir * (ReachCm * (static_cast<float>(Step) / 6.0f));
		if (ExpandedBox.IsInside(Sample))
		{
			const FVector Closest = EngineBlockBox.GetClosestPointTo(Sample);
			const float DistOutside = FVector::Dist(Sample, Closest);
			if (DistOutside <= RadiusCm * 0.55f)
			{
				// Measure inward penetration depth relative to the engine box size along InwardDir
				const float PenDepth = EngineBlockBox.IsInside(Sample)
					? FMath::Min3(
						FMath::Min(Sample.X - EngineBlockBox.Min.X, EngineBlockBox.Max.X - Sample.X),
						FMath::Min(Sample.Y - EngineBlockBox.Min.Y, EngineBlockBox.Max.Y - Sample.Y),
						FMath::Min(Sample.Z - EngineBlockBox.Min.Z, EngineBlockBox.Max.Z - Sample.Z)) + ReachCm * 0.25f
					: FMath::Max(0.0f, RadiusCm * 0.55f - DistOutside);
				const float RefSpan = FMath::Max(25.0f, 2.0f * FVector::DotProduct(BoxExtent, InwardDir.GetAbs()));
				MaxPenRatio = FMath::Max(MaxPenRatio, PenDepth / RefSpan);
			}
		}
	}

	if (MaxPenRatio <= 0.001f)
	{
		return;
	}

	const float DeltaPct = FMath::Clamp(MaxPenRatio * 95.0f * Severity * FMath::Max(ArmorScale, 0.35f), 2.0f, 45.0f);
	EngineBlockIntrusionPct = FMath::Clamp(EngineBlockIntrusionPct + DeltaPct, 0.0f, 100.0f);

	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
	const float DisablePct = Tuning ? Tuning->DamageEngineIntrusionDisablePct : 30.0f;
	if (EngineBlockIntrusionPct > DisablePct)
	{
		TriggerVehicleDisabled(EWSPC2VehicleDisableReason::EngineBlockCrushed);
	}
}

void UWSPC2VehicleDamageComponent::EvaluateChassisTwist(const FVector& LocalHit, const FVector& InwardDir, float Severity, float ArmorScale)
{
	if (Severity < 0.24f)
	{
		return;
	}

	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
	const float DegPerSev = Tuning ? Tuning->DamageChassisTwistPerSeverityDeg : 4.2f;

	const FVector NormHit = LocalHit.GetSafeNormal();
	const FVector TorqueLever = FVector::CrossProduct(NormHit, InwardDir);
	// Side/corner/roll hits twist Roll (X); high front/rear or roof crush buckle Pitch (Y); off-center corner hits skew Yaw (Z)
	const float RollDelta = (TorqueLever.X * 1.15f + InwardDir.Y * (LocalHit.Z > 65.0f ? 0.55f : -0.45f) + (LocalHit.Z > 110.0f ? 0.60f : 0.0f)) * Severity * ArmorScale * DegPerSev;
	const float PitchDelta = (TorqueLever.Y * 0.95f + (LocalHit.Z > 110.0f ? -0.95f : (InwardDir.X * (LocalHit.Z > 70.0f ? -0.5f : 0.45f)))) * Severity * ArmorScale * DegPerSev;
	const float YawDelta = TorqueLever.Z * 1.10f * Severity * ArmorScale * DegPerSev;

	ChassisTwistDeg.X = FMath::Clamp(ChassisTwistDeg.X + RollDelta, -25.0f, 25.0f);
	ChassisTwistDeg.Y = FMath::Clamp(ChassisTwistDeg.Y + PitchDelta, -25.0f, 25.0f);
	ChassisTwistDeg.Z = FMath::Clamp(ChassisTwistDeg.Z + YawDelta, -25.0f, 25.0f);

	if (GetMaxChassisTwistDeg() > FloorTouchTwistDeg)
	{
		TriggerVehicleDisabled(EWSPC2VehicleDisableReason::ChassisTwisted);
	}
}

void UWSPC2VehicleDamageComponent::RecordImpactDeformSlot(const FVector& LocalHit, const FVector& InwardDir, float Severity)
{
	if (Severity < 0.14f)
	{
		return;
	}

	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
	const float MaxDepth = Tuning ? Tuning->DamageMaxDeformDepthCm : 26.0f;
	const float NewDepth = FMath::Clamp(Severity * 22.0f, 2.5f, MaxDepth);
	const float NewRadius = FMath::Clamp(32.0f + Severity * 34.0f, 28.0f, 76.0f);

	// Merge into closest existing slot within 38 cm so repeated hits deepen the dent cleanly
	for (int32 i = 0; i < 4; ++i)
	{
		if (DeformSlots[i].DepthCm > 0.1f && FVector::Dist(FVector(DeformSlots[i].LocalPos), LocalHit) < 38.0f)
		{
			DeformSlots[i].DepthCm = FMath::Clamp(DeformSlots[i].DepthCm + NewDepth * 0.6f, 2.5f, MaxDepth);
			DeformSlots[i].RadiusCm = FMath::Max(DeformSlots[i].RadiusCm, NewRadius);
			return;
		}
	}

	DeformSlots[NextDeformSlot].LocalPos = LocalHit;
	DeformSlots[NextDeformSlot].InwardDir = InwardDir;
	DeformSlots[NextDeformSlot].RadiusCm = NewRadius;
	DeformSlots[NextDeformSlot].DepthCm = NewDepth;
	NextDeformSlot = (NextDeformSlot + 1) % 4;
}

void UWSPC2VehicleDamageComponent::TriggerVehicleDisabled(EWSPC2VehicleDisableReason Reason)
{
	bIsWrecked = true;
	if (DisableReason == EWSPC2VehicleDisableReason::None || Reason == EWSPC2VehicleDisableReason::EngineBlockCrushed
		|| Reason == EWSPC2VehicleDisableReason::TwoWheelsLost || Reason == EWSPC2VehicleDisableReason::ChassisTwisted)
	{
		DisableReason = Reason;
	}
	UE_LOG(LogWSPC2, Log, TEXT("ChaosDamage [%s]: VEHICLE DISABLED -> reason=%s (engineIntrusion=%.1f%%, detachedWheels=%d, maxTwist=%.1f/%.1f deg)"),
		*GetNameSafe(GetOwner()), GetDisableReasonName(), EngineBlockIntrusionPct, GetDetachedWheelCount(), GetMaxChassisTwistDeg(), FloorTouchTwistDeg);
}

void UWSPC2VehicleDamageComponent::DetachWheel(int32 WheelIndex, const FVector& ImpulseDir, float SpeedKmh)
{
	AActor* Owner = GetOwner();
	if (!Owner || !Owner->HasAuthority() || WheelIndex < 0 || WheelIndex >= 4)
	{
		return;
	}

	const uint8 Bit = static_cast<uint8>(1u << WheelIndex);
	const bool bAlreadyDetached = (DetachedWheelMask & Bit) != 0;
	DetachedWheelMask |= Bit;
	PuncturedWheelMask |= Bit;
	WheelHealth[WheelIndex] = 0.0f;
	WheelBentAmount[WheelIndex] = 1.0f;
	RecalculateWheelCamberAndFlags();

	if (!bAlreadyDetached)
	{
		SpawnDetachedWheelActor(WheelIndex, ImpulseDir, SpeedKmh);

		const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
		const int32 NeededToDisable = Tuning ? Tuning->DamageDetachedWheelsToDisable : 2;
		if (GetDetachedWheelCount() >= NeededToDisable)
		{
			TriggerVehicleDisabled(EWSPC2VehicleDisableReason::TwoWheelsLost);
		}
		RefreshAllDamageSystems();
		UE_LOG(LogWSPC2, Log, TEXT("ChaosDamage [%s]: Wheel %d DETACHED! Detached count=%d/%d."),
			*GetNameSafe(Owner), WheelIndex, GetDetachedWheelCount(), NeededToDisable);
	}
}

void UWSPC2VehicleDamageComponent::SpawnDetachedWheelActor(int32 WheelIndex, const FVector& ImpulseDir, float SpeedKmh)
{
	AActor* Owner = GetOwner();
	UWorld* World = GetWorld();
	if (!Owner || !World || GetNetMode() == NM_DedicatedServer || WheelIndex < 0 || WheelIndex >= 4)
	{
		return;
	}

	UStaticMesh* WheelMeshAsset = WheelVisualOverrides[WheelIndex].Get();
	if (!WheelMeshAsset && WheelMeshes.IsValidIndex(WheelIndex) && WheelMeshes[WheelIndex])
	{
		WheelMeshAsset = WheelMeshes[WheelIndex]->GetStaticMesh();
	}
	if (!WheelMeshAsset)
	{
		return;
	}

	const FVector HubWorld = Owner->GetActorTransform().TransformPosition(WheelHubPositions[WheelIndex]);
	const FVector OutwardSide = ((WheelIndex % 2) == 1 ? 1.0f : -1.0f) * Owner->GetActorRightVector();
	const FVector SpawnPos = HubWorld + OutwardSide * 28.0f + FVector(0.0f, 0.0f, 12.0f);
	const FRotator SpawnRot = Owner->GetActorRotation() + FRotator(0.0f, (WheelIndex % 2) == 1 ? 180.0f : 0.0f, 0.0f);

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AStaticMeshActor* LooseWheel = World->SpawnActor<AStaticMeshActor>(SpawnPos, SpawnRot, Params);
	if (!LooseWheel)
	{
		return;
	}

	UStaticMeshComponent* MeshComp = LooseWheel->GetStaticMeshComponent();
	LooseWheel->SetMobility(EComponentMobility::Movable);
	MeshComp->SetStaticMesh(WheelMeshAsset);
	MeshComp->SetCollisionProfileName(TEXT("PhysicsActor"));
	MeshComp->SetCollisionResponseToAllChannels(ECR_Ignore);
	MeshComp->SetCollisionResponseToChannel(ECC_WorldStatic, ECR_Block);
	MeshComp->SetSimulatePhysics(true);
	MeshComp->SetMassOverrideInKg(NAME_None, 24.0f, true);

	const FVector EjectVec = (OutwardSide * 0.75f + FVector(0.0f, 0.0f, 0.45f) + ImpulseDir.GetSafeNormal() * 0.35f).GetSafeNormal();
	const float EjectSpeed = FMath::Clamp(SpeedKmh * 14.0f + 420.0f, 420.0f, 1450.0f);
	MeshComp->SetPhysicsLinearVelocity(Owner->GetVelocity() * 0.55f + EjectVec * EjectSpeed);
	MeshComp->SetPhysicsAngularVelocityInDegrees(FVector(
		FMath::FRandRange(-420.0f, 420.0f),
		FMath::FRandRange(-680.0f, 680.0f),
		FMath::FRandRange(-360.0f, 360.0f)));
	LooseWheel->SetLifeSpan(25.0f);
	SpawnedDetachedWheels.Add(LooseWheel);
}

void UWSPC2VehicleDamageComponent::PunctureWheel(int32 WheelIndex)
{
	AActor* Owner = GetOwner();
	if (!Owner || !Owner->HasAuthority() || WheelIndex < 0 || WheelIndex >= 4)
	{
		return;
	}

	const uint8 Bit = static_cast<uint8>(1u << WheelIndex);
	const bool bAlreadyPunctured = (PuncturedWheelMask & Bit) != 0;
	PuncturedWheelMask |= Bit;
	WheelHealth[WheelIndex] = 0.0f;
	RecalculateWheelCamberAndFlags();

	if (!bAlreadyPunctured)
	{
		RefreshAllDamageSystems();
		UE_LOG(LogWSPC2, Log, TEXT("ChaosDamage [%s]: Wheel %d punctured! Riding on damaged rim (health=%.1f%%)."),
			*GetNameSafe(Owner), WheelIndex, HealthPercent);
	}
}

void UWSPC2VehicleDamageComponent::RepairAll()
{
	AActor* Owner = GetOwner();
	if (Owner && !Owner->HasAuthority())
	{
		return;
	}

	for (int32 z = 0; z < 5; ++z)
	{
		ZoneDamage[z] = 0.0f;
	}

	for (int32 w = 0; w < 4; ++w)
	{
		WheelHealth[w] = 1.0f;
		WheelBentAmount[w] = 0.0f;
		bWheelPunctured[w] = false;
		WheelCamberTiltDeg[w] = 0.0f;
		WheelToeTiltDeg[w] = 0.0f;
		WheelFrictionScale[w] = 1.0f;
	}

	PuncturedWheelMask = 0;
	DetachedWheelMask = 0;
	EngineBlockIntrusionPct = 0.0f;
	ChassisTwistDeg = FVector::ZeroVector;
	DisableReason = EWSPC2VehicleDisableReason::None;
	NextDeformSlot = 0;
	LastVisualDetachedMask = 0;
	for (int32 s = 0; s < 4; ++s)
	{
		DeformSlots[s] = FWSPC2ImpactDeformSlot();
	}
	for (int32 p = 0; p < 9; ++p)
	{
		PanelStates[p] = 0;
		AppliedPanelStates[p] = 0;
	}
	BrokenLightsMask = 0;
	ShatteredGlassMask = 0;
	AppliedShatteredGlassMask = 0;
	ImpactHistory.Reset();
	AppliedImpactCount = 0;
	for (int32 i = 0; i < 5; ++i)
	{
		LightFlickerTimer[i] = 0.0f;
	}
	ClearContactDamageDecals();
	if (DeformableChassis)
	{
		DeformableChassis->ResetAndDestroy(BodyMesh, GlassMesh);
		DeformableChassis.Reset();
	}
	for (AStaticMeshActor* LooseWheel : SpawnedDetachedWheels)
	{
		if (IsValid(LooseWheel))
		{
			LooseWheel->Destroy();
		}
	}
	SpawnedDetachedWheels.Reset();

	HealthPercent = 100.0f;
	bIsWrecked = false;

	GlassCrackStage = 0;
	bSideGlassFractured = false;
	bLightbarFractured = false;
	bHeadlightHousingFractured = false;
	MisfireCutRemaining = 0.0f;
	MisfireTimer = 0.0f;
	CurrentSirenHealthFactor = 1.0f;

	if (BodyMesh && bRigConfigured)
	{
		BodyMesh->SetRelativeTransform(InitialBodyRelativeTransform);
		for (int32 Slot = 0; Slot < OriginalBodyMaterials.Num(); ++Slot)
		{
			if (OriginalBodyMaterials[Slot])
			{
				UMaterialInstanceDynamic* MID = BodyMesh->CreateDynamicMaterialInstance(Slot, OriginalBodyMaterials[Slot]);
				if (BodyMIDs.IsValidIndex(Slot))
				{
					BodyMIDs[Slot] = MID;
				}
			}
		}
	}

	if (GlassMesh && bRigConfigured)
	{
		GlassMesh->SetRelativeTransform(InitialGlassRelativeTransform);
		GlassMIDs.Reset();
		for (int32 Slot = 0; Slot < OriginalGlassMaterials.Num(); ++Slot)
		{
			if (OriginalGlassMaterials[Slot])
			{
				UMaterialInstanceDynamic* GMID = GlassMesh->CreateDynamicMaterialInstance(Slot, OriginalGlassMaterials[Slot]);
				GlassMIDs.Add(GMID);
			}
			else
			{
				GlassMIDs.Add(nullptr);
			}
		}
	}

	if (HoodSteamComp)
	{
		HoodSteamComp->DeactivateImmediate();
	}
	if (HoodSmokeComp)
	{
		HoodSmokeComp->DeactivateImmediate();
		if (bWreckSmokeTemplateActive && SmokeParticleTemplate)
		{
			HoodSmokeComp->SetTemplate(SmokeParticleTemplate);
			HoodSmokeComp->SetRelativeScale3D(FVector(0.38f));
		}
	}
	bWreckSmokeTemplateActive = false;
	if (RimSparkComp)
	{
		RimSparkComp->DeactivateImmediate();
	}
	if (EngineHazardLight)
	{
		EngineHazardLight->SetVisibility(false);
	}
	if (ImpactSparkLight)
	{
		ImpactSparkLight->SetVisibility(false);
	}

	RefreshAllDamageSystems();
}

void UWSPC2VehicleDamageComponent::OnRep_DamageState()
{
	RecalculateWheelCamberAndFlags();
	RefreshAllDamageSystems();
}

void UWSPC2VehicleDamageComponent::OnRep_LastImpact()
{
	if (LastImpact.Severity > 0.0f)
	{
		TriggerImpactBurstFX(LastImpact.WorldPoint, LastImpact.WorldNormal, LastImpact.Severity);
	}
}

void UWSPC2VehicleDamageComponent::OnRep_MeshDeformState()
{
	SyncDeformableChassisFromState();
}

void UWSPC2VehicleDamageComponent::EnsureDeformableChassis()
{
	if (DeformableChassis && DeformableChassis->IsActive())
	{
		return;
	}
	AActor* Owner = GetOwner();
	if (!Owner || !BodyMesh)
	{
		return;
	}
	USceneComponent* AttachParent = BodyMesh->GetAttachParent() ? BodyMesh->GetAttachParent() : Owner->GetRootComponent();
	if (!AttachParent)
	{
		return;
	}
	if (!DeformableChassis)
	{
		DeformableChassis = MakeUnique<FWSPC2DeformableChassis>();
	}
	DeformableChassis->BuildFromStaticMeshes(Owner, AttachParent, BodyMesh, GlassMesh, EngineBlockBox, BodyMIDs, GlassMIDs);
}

void UWSPC2VehicleDamageComponent::SyncDeformableChassisFromState()
{
	if (ImpactHistory.Num() == 0 && BrokenLightsMask == 0 && ShatteredGlassMask == 0)
	{
		ClearContactDamageDecals();
		if (DeformableChassis)
		{
			DeformableChassis->ResetAndDestroy(BodyMesh, GlassMesh);
			DeformableChassis.Reset();
		}
		AppliedImpactCount = 0;
		AppliedShatteredGlassMask = 0;
		for (int32 p = 0; p < 9; ++p)
		{
			AppliedPanelStates[p] = 0;
		}
		return;
	}

	EnsureDeformableChassis();
	if (!DeformableChassis || !DeformableChassis->IsActive())
	{
		return;
	}

	while (AppliedImpactCount < ImpactHistory.Num())
	{
		const FWSPC2MeshImpactRecord& Rec = ImpactHistory[AppliedImpactCount];
		DeformableChassis->ApplyPlasticImpact(Rec, ChassisTwistDeg, FloorTouchTwistDeg);
		SpawnLocalizedContactDecal(Rec.LocalPos, Rec.InwardDir, Rec.Severity);
		++AppliedImpactCount;
	}

	const FVector ImpulseDir = LastImpact.WorldNormal.IsNearlyZero() ? FVector::UpVector : FVector(LastImpact.WorldNormal);
	const float SpeedKmh = GetOwner() ? (GetOwner()->GetVelocity().Size() * 0.036f) : 45.0f;

	for (int32 p = 0; p < 9; ++p)
	{
		if (PanelStates[p] > AppliedPanelStates[p])
		{
			DeformableChassis->SetPanelState(
				static_cast<EWSPC2DetachablePanel>(p),
				static_cast<EWSPC2PanelDamageState>(PanelStates[p]),
				ImpulseDir,
				SpeedKmh);
			AppliedPanelStates[p] = PanelStates[p];
		}
	}

	for (int32 g = 0; g < 9; ++g)
	{
		const uint8 Bit = static_cast<uint8>(1u << g);
		if ((ShatteredGlassMask & Bit) != 0 && (AppliedShatteredGlassMask & Bit) == 0)
		{
			DeformableChassis->ShatterGlassZone(static_cast<EWSPC2GlassZone>(g), ImpulseDir, SpeedKmh, GenericGlassFractured);
			AppliedShatteredGlassMask |= Bit;
		}
	}
}

void UWSPC2VehicleDamageComponent::BreakCornerLight(int32 LightIndex, EWSPC2GlassZone GlassZone, const FVector& ImpulseDir, float ImpactSpeedKmh)
{
	if (LightIndex >= 0 && LightIndex < 5)
	{
		const uint8 LightBit = static_cast<uint8>(1u << LightIndex);
		if ((BrokenLightsMask & LightBit) == 0)
		{
			BrokenLightsMask |= LightBit;
			LightFlickerTimer[LightIndex] = 0.65f;
		}
	}
	const int32 GIdx = static_cast<int32>(GlassZone);
	if (GIdx >= 0 && GIdx < 9)
	{
		const uint8 GBit = static_cast<uint8>(1u << GIdx);
		if ((ShatteredGlassMask & GBit) == 0)
		{
			ShatteredGlassMask |= GBit;
			if (DeformableChassis && DeformableChassis->IsActive())
			{
				DeformableChassis->ShatterGlassZone(GlassZone, ImpulseDir, ImpactSpeedKmh, GenericGlassFractured);
				AppliedShatteredGlassMask |= GBit;
			}
		}
	}
}

void UWSPC2VehicleDamageComponent::EvaluatePanelsAndLightsFromImpact(
	const FVector& LocalHit,
	const FVector& WorldImpactNormal,
	float Severity,
	float ImpactSpeedKmh,
	EWSPC2DamageZone Zone)
{
	const float Front = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Front)];
	const float Rear = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Rear)];
	const float Left = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Left)];
	const float Right = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Right)];
	const float Roof = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Roof)];

	auto PromotePanel = [&](EWSPC2DetachablePanel Panel, EWSPC2PanelDamageState TargetState)
	{
		const int32 PIdx = static_cast<int32>(Panel);
		const uint8 TargetU8 = static_cast<uint8>(TargetState);
		if (PanelStates[PIdx] < TargetU8)
		{
			PanelStates[PIdx] = TargetU8;
			if (DeformableChassis && DeformableChassis->IsActive())
			{
				DeformableChassis->SetPanelState(Panel, TargetState, WorldImpactNormal, ImpactSpeedKmh);
				AppliedPanelStates[PIdx] = TargetU8;
			}
		}
	};

	// Front bumper & pushbar + Hood latch failure
	if (Zone == EWSPC2DamageZone::Front || LocalHit.X > 90.0f)
	{
		if (Front >= 0.36f || Severity >= 0.70f)
		{
			PromotePanel(EWSPC2DetachablePanel::FrontBumper, EWSPC2PanelDamageState::Detached);
		}
		else if (Front >= 0.14f || Severity >= 0.32f)
		{
			PromotePanel(EWSPC2DetachablePanel::FrontBumper, EWSPC2PanelDamageState::Loose);
		}

		if (Front >= 0.68f || EngineBlockIntrusionPct >= 24.0f || Severity >= 1.22f)
		{
			PromotePanel(EWSPC2DetachablePanel::Hood, EWSPC2PanelDamageState::Detached);
		}
		else if (Front >= 0.24f || Severity >= 0.52f || EngineBlockIntrusionPct >= 6.0f)
		{
			PromotePanel(EWSPC2DetachablePanel::Hood, EWSPC2PanelDamageState::Loose);
		}

		// Headlights shatter per impacted corner (broad barrier impacts break both)
		if (Severity >= 0.22f || Front >= 0.16f)
		{
			const bool bBroadFront = FMath::Abs(WorldImpactNormal.X) > 0.45f || Severity >= 0.52f;
			if (bBroadFront || LocalHit.Y <= 25.0f)
			{
				BreakCornerLight(0, EWSPC2GlassZone::Headlight_FL, WorldImpactNormal, ImpactSpeedKmh);
			}
			if (bBroadFront || LocalHit.Y >= -25.0f)
			{
				BreakCornerLight(1, EWSPC2GlassZone::Headlight_FR, WorldImpactNormal, ImpactSpeedKmh);
			}
		}

		if (Front >= 0.65f || Severity >= 1.05f)
		{
			BreakCornerLight(-1, EWSPC2GlassZone::Windshield, WorldImpactNormal, ImpactSpeedKmh);
		}
	}

	// Rear bumper & trunk decklid + Taillights
	if (Zone == EWSPC2DamageZone::Rear || LocalHit.X < -90.0f)
	{
		if (Rear >= 0.36f || Severity >= 0.70f)
		{
			PromotePanel(EWSPC2DetachablePanel::RearBumper, EWSPC2PanelDamageState::Detached);
		}
		else if (Rear >= 0.14f || Severity >= 0.32f)
		{
			PromotePanel(EWSPC2DetachablePanel::RearBumper, EWSPC2PanelDamageState::Loose);
		}

		if (Rear >= 0.66f)
		{
			PromotePanel(EWSPC2DetachablePanel::Trunk, EWSPC2PanelDamageState::Detached);
		}
		else if (Rear >= 0.26f || Severity >= 0.55f)
		{
			PromotePanel(EWSPC2DetachablePanel::Trunk, EWSPC2PanelDamageState::Loose);
		}

		if (Severity >= 0.22f || Rear >= 0.16f)
		{
			const bool bBroadRear = Severity >= 0.52f;
			if (bBroadRear || LocalHit.Y <= 25.0f)
			{
				BreakCornerLight(2, EWSPC2GlassZone::Taillight_RL, WorldImpactNormal, ImpactSpeedKmh);
			}
			if (bBroadRear || LocalHit.Y >= -25.0f)
			{
				BreakCornerLight(3, EWSPC2GlassZone::Taillight_RR, WorldImpactNormal, ImpactSpeedKmh);
			}
		}

		if (Rear >= 0.52f)
		{
			BreakCornerLight(-1, EWSPC2GlassZone::RearWindow, WorldImpactNormal, ImpactSpeedKmh);
		}
	}

	// Side doors, mirrors & side glass
	if (Zone == EWSPC2DamageZone::Left || Left >= 0.18f)
	{
		if (Left >= 0.12f || Severity >= 0.26f) PromotePanel(EWSPC2DetachablePanel::LeftMirror, EWSPC2PanelDamageState::Detached);
		if (Left >= 0.72f) PromotePanel(EWSPC2DetachablePanel::LeftDoor, EWSPC2PanelDamageState::Detached);
		else if (Left >= 0.32f) PromotePanel(EWSPC2DetachablePanel::LeftDoor, EWSPC2PanelDamageState::Loose);
		if (Left >= 0.36f) BreakCornerLight(-1, EWSPC2GlassZone::SideWindow_L, WorldImpactNormal, ImpactSpeedKmh);
	}
	if (Zone == EWSPC2DamageZone::Right || Right >= 0.18f)
	{
		if (Right >= 0.12f || Severity >= 0.26f) PromotePanel(EWSPC2DetachablePanel::RightMirror, EWSPC2PanelDamageState::Detached);
		if (Right >= 0.72f) PromotePanel(EWSPC2DetachablePanel::RightDoor, EWSPC2PanelDamageState::Detached);
		else if (Right >= 0.32f) PromotePanel(EWSPC2DetachablePanel::RightDoor, EWSPC2PanelDamageState::Loose);
		if (Right >= 0.36f) BreakCornerLight(-1, EWSPC2GlassZone::SideWindow_R, WorldImpactNormal, ImpactSpeedKmh);
	}

	// Roof / Rollover lightbar & windshield shatter
	if (Zone == EWSPC2DamageZone::Roof || Roof >= 0.20f || bIsWrecked)
	{
		if (Roof >= 0.42f || bIsWrecked)
		{
			PromotePanel(EWSPC2DetachablePanel::RoofLightbar, EWSPC2PanelDamageState::Detached);
			BreakCornerLight(4, EWSPC2GlassZone::Lightbar_Glass, WorldImpactNormal, ImpactSpeedKmh);
		}
		else if (Roof >= 0.18f)
		{
			PromotePanel(EWSPC2DetachablePanel::RoofLightbar, EWSPC2PanelDamageState::Loose);
		}
		if (Roof >= 0.45f)
		{
			BreakCornerLight(-1, EWSPC2GlassZone::Windshield, WorldImpactNormal, ImpactSpeedKmh);
		}
	}
}

void UWSPC2VehicleDamageComponent::UpdateDynamicCornerLights(float DeltaTime)
{
	AActor* Owner = GetOwner();
	const APawn* Pawn = Cast<APawn>(Owner);
	const bool bShowLights = IsValid(Pawn) && Pawn->IsPlayerControlled() && !bIsWrecked;

	auto EvalCorner = [&](int32 Idx, ULightComponent* Comp, float NominalIntensity)
	{
		if (!Comp)
		{
			return;
		}
		const bool bBroken = (BrokenLightsMask & static_cast<uint8>(1u << Idx)) != 0;
		if (!bShowLights)
		{
			Comp->SetVisibility(false);
			return;
		}
		if (!bBroken)
		{
			Comp->SetVisibility(true);
			Comp->SetIntensity(NominalIntensity);
			return;
		}
		if (LightFlickerTimer[Idx] > 0.0f)
		{
			LightFlickerTimer[Idx] = FMath::Max(0.0f, LightFlickerTimer[Idx] - DeltaTime);
			const bool bFlash = FMath::Sin(HazardFlickerPhase * 2.4f + Idx * 1.7f) > 0.25f;
			Comp->SetVisibility(bFlash);
			Comp->SetIntensity(bFlash ? NominalIntensity * 0.75f : 0.0f);
		}
		else
		{
			Comp->SetVisibility(false);
		}
	};

	if (HeadlightSpots.IsValidIndex(0)) EvalCorner(0, HeadlightSpots[0], 26000.0f);
	if (HeadlightSpots.IsValidIndex(1)) EvalCorner(1, HeadlightSpots[1], 26000.0f);
	if (TaillightGlows.IsValidIndex(0)) EvalCorner(2, TaillightGlows[0], 5500.0f);
	if (TaillightGlows.IsValidIndex(1)) EvalCorner(3, TaillightGlows[1], 5500.0f);
}

int32 UWSPC2VehicleDamageComponent::GetLoosePanelCount() const
{
	int32 C = 0;
	for (int32 i = 0; i < 9; ++i)
	{
		if (PanelStates[i] == static_cast<uint8>(EWSPC2PanelDamageState::Loose)) ++C;
	}
	return C;
}

int32 UWSPC2VehicleDamageComponent::GetDetachedPanelCount() const
{
	int32 C = 0;
	for (int32 i = 0; i < 9; ++i)
	{
		if (PanelStates[i] == static_cast<uint8>(EWSPC2PanelDamageState::Detached)) ++C;
	}
	return C;
}

int32 UWSPC2VehicleDamageComponent::GetBrokenLightCount() const
{
	int32 C = 0;
	for (int32 i = 0; i < 4; ++i)
	{
		if ((BrokenLightsMask & static_cast<uint8>(1u << i)) != 0) ++C;
	}
	return C;
}

int32 UWSPC2VehicleDamageComponent::GetShatteredGlassCount() const
{
	int32 C = 0;
	for (int32 i = 0; i < 9; ++i)
	{
		if ((ShatteredGlassMask & static_cast<uint8>(1u << i)) != 0) ++C;
	}
	return C;
}

void UWSPC2VehicleDamageComponent::RecalculateWheelCamberAndFlags()
{
	for (int32 w = 0; w < 4; ++w)
	{
		const uint8 Bit = static_cast<uint8>(1u << w);
		bWheelPunctured[w] = (PuncturedWheelMask & Bit) != 0;

		const bool bRightSide = (w % 2) == 1;
		const float Sign = bRightSide ? -1.0f : 1.0f;
		const float Bent = FMath::Clamp(WheelBentAmount[w], 0.0f, 1.0f);
		if (bWheelPunctured[w])
		{
			WheelCamberTiltDeg[w] = Sign * (8.5f + Bent * 9.5f);
			WheelToeTiltDeg[w] = Sign * (2.5f + Bent * 8.5f);
		}
		else
		{
			const float HubWear = FMath::Max(Bent, FMath::Clamp(1.0f - WheelHealth[w], 0.0f, 1.0f));
			WheelCamberTiltDeg[w] = (HubWear > 0.18f) ? Sign * FMath::Lerp(0.0f, 12.0f, (HubWear - 0.18f) / 0.82f) : 0.0f;
			WheelToeTiltDeg[w] = (Bent > 0.10f) ? Sign * (Bent * 9.0f) : 0.0f;
		}
	}
}

int32 UWSPC2VehicleDamageComponent::GetDetachedWheelCount() const
{
	int32 Count = 0;
	for (int32 w = 0; w < 4; ++w)
	{
		if (IsWheelDetached(w))
		{
			++Count;
		}
	}
	return Count;
}

const TCHAR* UWSPC2VehicleDamageComponent::GetDisableReasonName() const
{
	switch (DisableReason)
	{
	case EWSPC2VehicleDisableReason::None:               return TEXT("None");
	case EWSPC2VehicleDisableReason::HealthDepleted:     return TEXT("HealthDepleted");
	case EWSPC2VehicleDisableReason::EngineBlockCrushed: return TEXT("EngineBlockCrushed");
	case EWSPC2VehicleDisableReason::TwoWheelsLost:      return TEXT("TwoWheelsLost");
	case EWSPC2VehicleDisableReason::ChassisTwisted:     return TEXT("ChassisTwisted");
	default:                                             return TEXT("Unknown");
	}
}

EWSPC2DamageStage UWSPC2VehicleDamageComponent::GetDamageStage() const
{
	if (bIsWrecked || HealthPercent <= 0.0f)
	{
		return EWSPC2DamageStage::Wrecked;
	}
	if (HealthPercent >= 95.0f)
	{
		return EWSPC2DamageStage::Pristine;
	}
	if (HealthPercent >= 70.0f)
	{
		return EWSPC2DamageStage::Light;
	}
	if (HealthPercent >= 40.0f)
	{
		return EWSPC2DamageStage::Moderate;
	}
	return EWSPC2DamageStage::Heavy;
}

const TCHAR* UWSPC2VehicleDamageComponent::GetDamageStageName() const
{
	switch (GetDamageStage())
	{
	case EWSPC2DamageStage::Pristine: return TEXT("Pristine");
	case EWSPC2DamageStage::Light:    return TEXT("Light");
	case EWSPC2DamageStage::Moderate: return TEXT("Moderate");
	case EWSPC2DamageStage::Heavy:    return TEXT("Heavy");
	case EWSPC2DamageStage::Wrecked:  return TEXT("Wrecked");
	default:                          return TEXT("Unknown");
	}
}

int32 UWSPC2VehicleDamageComponent::GetPuncturedWheelCount() const
{
	int32 Count = 0;
	for (int32 w = 0; w < 4; ++w)
	{
		if (bWheelPunctured[w])
		{
			++Count;
		}
	}
	return Count;
}

float UWSPC2VehicleDamageComponent::GetWheelVisualDropCm(int32 WheelIndex) const
{
	if (WheelIndex < 0 || WheelIndex >= 4)
	{
		return 0.0f;
	}
	if (IsWheelDetached(WheelIndex))
	{
		const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
		const float HubR = Tuning ? Tuning->DamageDetachedHubRadiusCm : 11.0f;
		return FMath::Max(0.0f, WheelBaseRadii[WheelIndex] - HubR);
	}
	if (bWheelPunctured[WheelIndex])
	{
		const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
		return (Tuning ? Tuning->DamageFlatTyreRadiusDropCm : 6.0f) * 0.55f;
	}
	const float Wear = 1.0f - WheelHealth[WheelIndex];
	return Wear > 0.35f ? Wear * 1.1f : 0.0f;
}

float UWSPC2VehicleDamageComponent::GetEngineHealthTorqueFactor() const
{
	if (bIsWrecked)
	{
		return 0.0f;
	}

	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
	const float MinTorqueScale = Tuning ? Tuning->DamageHeavyMinTorqueScale : 0.34f;
	const float FrontDamage = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Front)];
	const float RearDamage = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Rear)];
	const float OverallDamage = FMath::Clamp((100.0f - HealthPercent) * 0.01f, 0.0f, 1.0f);
	const float IntrusionFrac = FMath::Clamp(EngineBlockIntrusionPct / FMath::Max(Tuning ? Tuning->DamageEngineIntrusionDisablePct : 30.0f, 1.0f), 0.0f, 1.0f);

	// Light front bumps shave off a touch of response; engine intrusion toward 30% saps severe power
	const float EngineWear = FMath::Clamp(FMath::Max(FrontDamage * 0.78f + RearDamage * 0.14f + OverallDamage * 0.28f, IntrusionFrac * 0.92f), 0.0f, 1.0f);
	if (EngineWear <= 0.08f)
	{
		return 1.0f;
	}

	const float Alpha = (EngineWear - 0.08f) / 0.92f;
	return FMath::Lerp(1.0f, MinTorqueScale, FMath::Pow(Alpha, 1.15f));
}

float UWSPC2VehicleDamageComponent::GetThrottleDamageMultiplier() const
{
	if (bIsWrecked)
	{
		return 0.0f;
	}
	if (MisfireCutRemaining > 0.0f)
	{
		return 0.25f;
	}
	return 1.0f;
}

float UWSPC2VehicleDamageComponent::GetSteeringPullBias() const
{
	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
	const float MaxPull = Tuning ? Tuning->DamageMaxSteeringPull : 0.24f;

	const float SideDiff = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Right)] - ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Left)];
	const float FrontWearDiff = (1.0f - WheelHealth[0]) - (1.0f - WheelHealth[1]);
	const float FlatFrontDiff = (bWheelPunctured[1] ? 0.14f : 0.0f) - (bWheelPunctured[0] ? 0.14f : 0.0f);
	const float Pull = SideDiff * 0.16f - FrontWearDiff * 0.08f + FlatFrontDiff;

	// Subtle wheel shimmy oscillation when front suspension/rims are bent and car is moving
	float Shimmy = 0.0f;
	if (const AActor* Owner = GetOwner())
	{
		const float SpeedKmh = Owner->GetVelocity().Size() * 0.036f;
		const float FrontBend = FMath::Max(bWheelPunctured[0] ? 1.0f : (1.0f - WheelHealth[0]), bWheelPunctured[1] ? 1.0f : (1.0f - WheelHealth[1]));
		if (SpeedKmh > 20.0f && FrontBend > 0.25f)
		{
			const float SpeedAlpha = FMath::Clamp((SpeedKmh - 20.0f) / 90.0f, 0.0f, 1.0f);
			Shimmy = FMath::Sin(ShimmyPhase) * 0.055f * FrontBend * SpeedAlpha;
		}
	}

	return FMath::Clamp(Pull + Shimmy, -MaxPull, MaxPull);
}

void UWSPC2VehicleDamageComponent::RefreshAllDamageSystems()
{
	ApplyVisualDeformation();
	UpdateGlassFractureMaterials();
	UpdateLightMaterials();
	UpdateDamageVFX();
	ApplyMechanicalPenalties();
}

void UWSPC2VehicleDamageComponent::ApplyVisualDeformation()
{
	const float Front = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Front)];
	const float Rear = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Rear)];
	const float Left = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Left)];
	const float Right = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Right)];
	const float Roof = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Roof)];
	const float TotalSeverity = FMath::Clamp((100.0f - HealthPercent) * 0.01f, 0.0f, 1.0f);
	const float MaxZoneDmg = FMath::Max3(Front, Rear, FMath::Max3(Left, Right, Roof));

	// Compute real CitySample shader wear curves (0% -> clean glossy cruiser, 100% -> dented, primer-scratched, bare metal & soot)
	CurrentPrimerThreshold = FMath::Lerp(0.80f, 0.18f, FMath::Clamp(TotalSeverity * 1.15f + MaxZoneDmg * 0.25f, 0.0f, 1.0f));
	CurrentMetalThreshold = FMath::Lerp(0.95f, 0.34f, FMath::Clamp(TotalSeverity * 1.10f + MaxZoneDmg * 0.20f, 0.0f, 1.0f));
	CurrentDentStrength = FMath::Lerp(0.15f, 1.50f, FMath::Clamp(TotalSeverity * 0.85f + MaxZoneDmg * 0.45f, 0.0f, 1.0f));

	if (!bRigConfigured || !BodyMesh)
	{
		return;
	}

	const float TwistFloorFrac = FMath::Clamp(GetMaxChassisTwistDeg() / FMath::Max(FloorTouchTwistDeg, 1.0f), 0.0f, 1.25f);
	const float LeftSag = (bWheelPunctured[0] ? 1.8f : 0.0f) + (bWheelPunctured[2] ? 1.8f : 0.0f) + (IsWheelDetached(0) ? 5.5f : 0.0f) + (IsWheelDetached(2) ? 5.5f : 0.0f);
	const float RightSag = (bWheelPunctured[1] ? 1.8f : 0.0f) + (bWheelPunctured[3] ? 1.8f : 0.0f) + (IsWheelDetached(1) ? 5.5f : 0.0f) + (IsWheelDetached(3) ? 5.5f : 0.0f);
	const float FrontSag = (bWheelPunctured[0] ? 1.6f : 0.0f) + (bWheelPunctured[1] ? 1.6f : 0.0f) + (IsWheelDetached(0) ? 5.5f : 0.0f) + (IsWheelDetached(1) ? 5.5f : 0.0f);
	const float RearSag = (bWheelPunctured[2] ? 1.6f : 0.0f) + (bWheelPunctured[3] ? 1.6f : 0.0f) + (IsWheelDetached(2) ? 5.5f : 0.0f) + (IsWheelDetached(3) ? 5.5f : 0.0f);

	const FVector CrushScale(
		1.0f - 0.055f * (Front + Rear) - 0.045f * FMath::Clamp(EngineBlockIntrusionPct / 30.0f, 0.0f, 1.2f),
		1.0f - 0.042f * (Left + Right),
		1.0f - 0.062f * Roof - 0.035f * TwistFloorFrac);

	const FVector CrushShift(
		(Rear - Front) * 6.5f,
		(Left - Right) * 3.5f,
		-Roof * 4.8f - 0.5f * (LeftSag + RightSag) - TwistFloorFrac * 4.5f);

	const FRotator CrushTilt(
		(Rear - Front) * 1.9f + (RearSag - FrontSag) * 0.65f + ChassisTwistDeg.Y * 0.85f,
		ChassisTwistDeg.Z * 0.85f + (Left - Right) * 1.1f,
		ChassisTwistDeg.X * 0.85f + (Right - Left) * 2.8f + (LeftSag - RightSag) * 0.95f);

	FTransform DeformedBody = InitialBodyRelativeTransform;
	const bool bHasDeformMesh = DeformableChassis && DeformableChassis->IsActive();
	if (!bHasDeformMesh)
	{
		DeformedBody.SetScale3D(InitialBodyRelativeTransform.GetScale3D() * CrushScale);
		DeformedBody.AddToTranslation(CrushShift);
		DeformedBody.SetRotation(InitialBodyRelativeTransform.GetRotation() * CrushTilt.Quaternion());
		BodyMesh->SetRelativeTransform(DeformedBody);
	}

	if (GlassMesh && !bHasDeformMesh)
	{
		FTransform DeformedGlass = InitialGlassRelativeTransform;
		DeformedGlass.SetScale3D(InitialGlassRelativeTransform.GetScale3D() * CrushScale);
		DeformedGlass.AddToTranslation(CrushShift);
		DeformedGlass.SetRotation(InitialGlassRelativeTransform.GetRotation() * CrushTilt.Quaternion());
		GlassMesh->SetRelativeTransform(DeformedGlass);
	}

	const float SootLevel = FMath::Clamp(TotalSeverity * 0.7f + (EngineBlockIntrusionPct / 35.0f) * 0.45f, 0.0f, 1.0f);
	static const FName HitPosNames[4] = { TEXT("HitPos0"), TEXT("HitPos1"), TEXT("HitPos2"), TEXT("HitPos3") };
	static const FName HitDirNames[4] = { TEXT("HitDir0"), TEXT("HitDir1"), TEXT("HitDir2"), TEXT("HitDir3") };

	for (UMaterialInstanceDynamic* MID : BodyMIDs)
	{
		if (!MID)
		{
			continue;
		}

		// Only M_WSPC2_VehicleDamage carries localized impact wear; never mutate global CitySample Paint/Dirt/CPD across untouched panels
		const UMaterial* BaseMat = MID->GetMaterial();
		if (!BaseMat || !BaseMat->GetName().Contains(TEXT("M_WSPC2_VehicleDamage")))
		{
			continue;
		}

		if (bHasDeformMesh)
		{
			// CPU-deformed meshes drive strictly localized scratches/primer/steel/soot via VertexColor in contact area
			MID->SetScalarParameterValue(TEXT("UseWPO"), 0.0f);
			MID->SetScalarParameterValue(TEXT("DamageAmount"), TotalSeverity);
			MID->SetScalarParameterValue(TEXT("ScratchAmount"), 0.0f);
			MID->SetScalarParameterValue(TEXT("SootAmount"), 0.0f);
		}
		else
		{
			MID->SetScalarParameterValue(TEXT("UseWPO"), 1.0f);
			for (int32 s = 0; s < 4; ++s)
			{
				const FWSPC2ImpactDeformSlot& Slot = DeformSlots[s];
				MID->SetVectorParameterValue(HitPosNames[s], FLinearColor(Slot.LocalPos.X, Slot.LocalPos.Y, Slot.LocalPos.Z, FMath::Max(1.0f, Slot.RadiusCm)));
				MID->SetVectorParameterValue(HitDirNames[s], FLinearColor(Slot.InwardDir.X, Slot.InwardDir.Y, Slot.InwardDir.Z, Slot.DepthCm));
			}
			MID->SetScalarParameterValue(TEXT("DamageAmount"), TotalSeverity);
			MID->SetScalarParameterValue(TEXT("ScratchAmount"), FMath::Clamp(TotalSeverity * 1.15f + MaxZoneDmg * 0.35f, 0.0f, 1.0f));
			MID->SetScalarParameterValue(TEXT("SootAmount"), SootLevel);
		}
	}
}

void UWSPC2VehicleDamageComponent::UpdateGlassFractureMaterials()
{
	if (!GlassMesh)
	{
		return;
	}

	const float Front = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Front)];
	const float Roof = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Roof)];
	const float Side = 0.5f * (ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Left)] + ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Right)]);
	const float GlassStrain = Front + Roof + Side;

	if (bIsPoliceCruiser)
	{
		// Slot 4 on SM_All_Trans_vehCar_vehicle13 is MI_vehCar_vehicle13_19 (windshield)
		if ((GlassStrain >= 0.54f || bIsWrecked) && GlassCrackStage < 2 && PoliceWindshieldCrack2 && GlassMesh->GetNumMaterials() > 4)
		{
			GlassMesh->SetMaterial(4, PoliceWindshieldCrack2);
			GlassCrackStage = 2;
		}
		else if (GlassStrain >= 0.18f && GlassCrackStage < 1 && PoliceWindshieldCrack1 && GlassMesh->GetNumMaterials() > 4)
		{
			GlassMesh->SetMaterial(4, PoliceWindshieldCrack1);
			GlassCrackStage = 1;
		}

		// Slot 5 ('veh_window') & Slot 8 ('veh_glass_inner') fracture on heavy side/roll impacts
		if (!bSideGlassFractured && (Side >= 0.42f || Roof >= 0.45f || bIsWrecked) && GenericGlassFractured)
		{
			if (GlassMesh->GetNumMaterials() > 5)
			{
				GlassMesh->SetMaterial(5, GenericGlassFractured);
			}
			if (GlassMesh->GetNumMaterials() > 8)
			{
				GlassMesh->SetMaterial(8, GenericGlassFractured);
			}
			bSideGlassFractured = true;
		}

		// Slot 3 on SM_All_Trans_vehCar_vehicle13 is MI_vehCar_vehicle13_23 (police roof lightbar)
		if (!bLightbarFractured && (Roof >= 0.22f || HealthPercent < 45.0f || bIsWrecked) && PoliceLightbarFractured && GlassMesh->GetNumMaterials() > 3)
		{
			GlassMesh->SetMaterial(3, PoliceLightbarFractured);
			bLightbarFractured = true;
		}
	}
	else
	{
		// Procedural M_WSPC2_VehicleGlass crack stage
		const float NormalizedCrack = bIsWrecked ? 1.0f : FMath::Clamp((GlassStrain - 0.12f) / 0.65f, 0.0f, 1.0f);
		for (UMaterialInstanceDynamic* GMID : GlassMIDs)
		{
			if (GMID)
			{
				GMID->SetScalarParameterValue(TEXT("CrackStage"), NormalizedCrack);
			}
		}

		// Legacy CitySample non-police glass fracture swap fallback (skip if slot already uses M_WSPC2_VehicleGlass)
		if (GenericGlassFractured)
		{
			const int32 NumMats = GlassMesh->GetNumMaterials();
			const TArray<FName> SlotNames = GlassMesh->GetMaterialSlotNames();
			auto ShouldSwapSlot = [this](int32 Slot) -> bool
			{
				if (!OriginalGlassMaterials.IsValidIndex(Slot) || !OriginalGlassMaterials[Slot])
				{
					return false;
				}
				const FString ParentName = OriginalGlassMaterials[Slot]->GetMaterial() ? OriginalGlassMaterials[Slot]->GetMaterial()->GetName() : OriginalGlassMaterials[Slot]->GetName();
				return !ParentName.Contains(TEXT("M_WSPC2_VehicleGlass"), ESearchCase::IgnoreCase);
			};

			if (GlassCrackStage < 1 && (GlassStrain >= 0.20f || bIsWrecked))
			{
				bool bMatchedWindshield = false;
				for (int32 Slot = 0; Slot < NumMats; ++Slot)
				{
					if (!ShouldSwapSlot(Slot)) continue;
					const FString SlotStr = SlotNames.IsValidIndex(Slot) ? SlotNames[Slot].ToString() : FString();
					const FString MatStr = OriginalGlassMaterials[Slot]->GetName();
					if (SlotStr.Contains(TEXT("windshield"), ESearchCase::IgnoreCase)
						|| MatStr.Contains(TEXT("windshield"), ESearchCase::IgnoreCase)
						|| MatStr.Contains(TEXT("_19")))
					{
						GlassMesh->SetMaterial(Slot, GenericGlassFractured);
						bMatchedWindshield = true;
					}
				}
				if (!bMatchedWindshield)
				{
					for (int32 Slot = 0; Slot < NumMats; ++Slot)
					{
						if (!ShouldSwapSlot(Slot)) continue;
						const FString SlotStr = SlotNames.IsValidIndex(Slot) ? SlotNames[Slot].ToString() : FString();
						const FString MatStr = OriginalGlassMaterials[Slot]->GetName();
						if (SlotStr.Contains(TEXT("glass"), ESearchCase::IgnoreCase)
							|| SlotStr.Contains(TEXT("window"), ESearchCase::IgnoreCase)
							|| MatStr.Contains(TEXT("glass"), ESearchCase::IgnoreCase)
							|| MatStr.Contains(TEXT("window"), ESearchCase::IgnoreCase))
						{
							GlassMesh->SetMaterial(Slot, GenericGlassFractured);
						}
					}
				}
				GlassCrackStage = 1;
			}

			if (!bSideGlassFractured && (Side >= 0.42f || Roof >= 0.45f || bIsWrecked))
			{
				for (int32 Slot = 0; Slot < NumMats; ++Slot)
				{
					if (!ShouldSwapSlot(Slot)) continue;
					const FString SlotStr = SlotNames.IsValidIndex(Slot) ? SlotNames[Slot].ToString() : FString();
					const FString MatStr = OriginalGlassMaterials[Slot]->GetName();
					if (SlotStr.Contains(TEXT("window"), ESearchCase::IgnoreCase)
						|| SlotStr.Contains(TEXT("glass"), ESearchCase::IgnoreCase)
						|| MatStr.Contains(TEXT("window"), ESearchCase::IgnoreCase)
						|| MatStr.Contains(TEXT("glass"), ESearchCase::IgnoreCase))
					{
						GlassMesh->SetMaterial(Slot, GenericGlassFractured);
					}
				}
				bSideGlassFractured = true;
				GlassCrackStage = FMath::Max(GlassCrackStage, 2);
			}
		}
		else
		{
			if (GlassCrackStage < 1 && (GlassStrain >= 0.20f || bIsWrecked))
			{
				GlassCrackStage = 1;
			}
			if (!bSideGlassFractured && (Side >= 0.42f || Roof >= 0.45f || bIsWrecked))
			{
				bSideGlassFractured = true;
				GlassCrackStage = FMath::Max(GlassCrackStage, 2);
			}
		}
	}
}

void UWSPC2VehicleDamageComponent::UpdateLightMaterials()
{
	if (!BodyMesh)
	{
		return;
	}

	const float Front = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Front)];
	const float Rear = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Rear)];
	const bool bFrontLightsDead = (BrokenLightsMask & 0x03) == 0x03;
	const bool bRearLightsDead = (BrokenLightsMask & 0x0C) == 0x0C;
	const float HeadlightHealth = (bIsWrecked || bFrontLightsDead) ? 0.0f : FMath::Clamp(1.0f - (Front - 0.18f) / 0.62f, 0.0f, 1.0f);
	const float TaillightHealth = (bIsWrecked || bRearLightsDead) ? 0.0f : FMath::Clamp(1.0f - (Rear - 0.22f) / 0.65f, 0.0f, 1.0f);

	const TArray<FName> SlotNames = BodyMesh->GetMaterialSlotNames();
	for (int32 Slot = 0; Slot < BodyMIDs.Num(); ++Slot)
	{
		if (!BodyMIDs[Slot])
		{
			continue;
		}
		const FString SlotStr = SlotNames.IsValidIndex(Slot) ? SlotNames[Slot].ToString() : FString();
		const FString MatStr = OriginalBodyMaterials.IsValidIndex(Slot) && OriginalBodyMaterials[Slot] ? OriginalBodyMaterials[Slot]->GetName() : FString();
		const bool bIsLightSlot = SlotStr.Contains(TEXT("light"), ESearchCase::IgnoreCase)
			|| MatStr.Contains(TEXT("light"), ESearchCase::IgnoreCase)
			|| SlotStr.Contains(TEXT("veh_light"), ESearchCase::IgnoreCase);
		if (!bIsLightSlot)
		{
			continue;
		}

		if (bIsPoliceCruiser && !bHeadlightHousingFractured && SlotStr.Contains(TEXT("veh_light"), ESearchCase::IgnoreCase)
			&& (Front >= 0.65f || Rear >= 0.72f || bIsWrecked) && PoliceLightHousingFractured)
		{
			BodyMesh->SetMaterial(Slot, PoliceLightHousingFractured);
			UMaterialInstanceDynamic* FracturedMID = BodyMesh->CreateDynamicMaterialInstance(Slot, PoliceLightHousingFractured);
			BodyMIDs[Slot] = FracturedMID;
			bHeadlightHousingFractured = true;
			if (DeformableChassis && DeformableChassis->IsActive())
			{
				for (const TWeakObjectPtr<UProceduralMeshComponent>& WeakPMC : DeformableChassis->GetActiveBodyPMCs())
				{
					if (UProceduralMeshComponent* PMC = WeakPMC.Get())
					{
						if (PMC->GetNumMaterials() > Slot)
						{
							PMC->SetMaterial(Slot, FracturedMID);
						}
					}
				}
			}
		}

		if (BodyMIDs[Slot])
		{
			BodyMIDs[Slot]->SetScalarParameterValue(TEXT("Headlight Amt LE"), HeadlightHealth);
			BodyMIDs[Slot]->SetScalarParameterValue(TEXT("Run Amt LE"), TaillightHealth);
			BodyMIDs[Slot]->SetScalarParameterValue(TEXT("Brake Amt LE"), TaillightHealth);
			BodyMIDs[Slot]->SetScalarParameterValue(TEXT("PoliceLight Amt"), CurrentSirenHealthFactor);
		}
	}
}

void UWSPC2VehicleDamageComponent::UpdateDamageVFX()
{
	if (GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	const float Front = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Front)];
	const bool bShowSteam = !bIsWrecked && (Front >= 0.28f || HealthPercent < 66.0f) && Front < 0.65f && HealthPercent > 30.0f;
	const bool bShowSmoke = bIsWrecked || Front >= 0.52f || HealthPercent < 42.0f;

	if (HoodSteamComp)
	{
		if (bShowSteam && !HoodSteamComp->IsActive())
		{
			HoodSteamComp->Activate(true);
		}
		else if (!bShowSteam && HoodSteamComp->IsActive())
		{
			HoodSteamComp->Deactivate();
		}
	}

	if (HoodSmokeComp)
	{
		if (bShowSmoke)
		{
			const bool bUseWreckPlume = bIsWrecked && (WreckSmokeParticleTemplate != nullptr);
			if (bUseWreckPlume != bWreckSmokeTemplateActive)
			{
				UParticleSystem* DesiredTemplate = bUseWreckPlume ? WreckSmokeParticleTemplate.Get() : SmokeParticleTemplate.Get();
				if (DesiredTemplate)
				{
					HoodSmokeComp->SetTemplate(DesiredTemplate);
					HoodSmokeComp->SetRelativeScale3D(bUseWreckPlume ? FVector(0.26f) : FVector(0.38f));
					bWreckSmokeTemplateActive = bUseWreckPlume;
					HoodSmokeComp->Activate(true);
				}
			}
			else if (!HoodSmokeComp->IsActive())
			{
				HoodSmokeComp->Activate(true);
			}
		}
		else if (HoodSmokeComp->IsActive())
		{
			HoodSmokeComp->Deactivate();
		}
	}
}

void UWSPC2VehicleDamageComponent::ApplyMechanicalPenalties()
{
	AActor* Owner = GetOwner();
	if (!Owner)
	{
		return;
	}

	if (!bBaselinesCaptured)
	{
		CaptureBaselineTuning();
	}

	if (UChaosWheeledVehicleMovementComponent* VehMove = Owner->FindComponentByClass<UChaosWheeledVehicleMovementComponent>())
	{
		const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
		const float FlatRadiusDrop = Tuning ? Tuning->DamageFlatTyreRadiusDropCm : 6.0f;
		const float FlatFrictionScale = Tuning ? Tuning->DamageFlatTyreFrictionScale : 0.52f;

		const float Front = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Front)];
		const float Rear = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Rear)];
		const float Left = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Left)];
		const float Right = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Right)];
		const float TotalSeverity = FMath::Clamp((100.0f - HealthPercent) * 0.01f, 0.0f, 1.0f);

		// 1. Engine max torque updated via Chaos SetMaxEngineTorque (engine stops generating drive when wrecked)
		const float TorqueFactor = GetEngineHealthTorqueFactor();
		const float TargetTorque = BaseMaxTorque * TorqueFactor;
		VehMove->EngineSetup.MaxTorque = TargetTorque;
		VehMove->SetMaxEngineTorque(TargetTorque);

		// 2. Crushed bodywork, detached hubs, and floorpan ground contact add heavy drag while reducing downforce
		const float FloorDrag = (GetMaxChassisTwistDeg() > FloorTouchTwistDeg) ? 0.95f : 0.0f;
		const float ExtraDrag = TotalSeverity * 0.42f + GetPuncturedWheelCount() * 0.06f + GetDetachedWheelCount() * 0.22f + FloorDrag + (bIsWrecked ? 0.35f : 0.0f);
		VehMove->SetDragCoefficient(BaseDragCoefficient + ExtraDrag);
		const float AeroLoss = FMath::Clamp(1.0f - (Front * 0.35f + Rear * 0.25f + TotalSeverity * 0.15f), 0.45f, 1.0f);
		VehMove->SetDownforceCoefficient(BaseDownforceCoefficient * AeroLoss);

		// 3. Per-wheel radius, friction, slip grip, brake torque fade, steering travel limit, and ABS failures
		const float DetachedHubR = Tuning ? Tuning->DamageDetachedHubRadiusCm : 11.0f;
		const int32 NumWheels = FMath::Min(4, VehMove->WheelSetups.Num());
		for (int32 w = 0; w < NumWheels; ++w)
		{
			const bool bFront = (w < 2);
			const bool bRight = (w % 2) == 1;
			const float EndDmg = bFront ? Front : Rear;
			const float SideDmg = bRight ? Right : Left;
			const float CornerDmg = FMath::Clamp(0.65f * EndDmg + 0.55f * SideDmg, 0.0f, 1.0f);
			const float WheelDmg = FMath::Clamp(1.0f - WheelHealth[w], 0.0f, 1.0f);
			const bool bDetached = IsWheelDetached(w);
			const bool bFlat = bWheelPunctured[w];

			const float TargetRadius = bDetached
				? DetachedHubR
				: FMath::Max(16.0f, WheelBaseRadii[w] - (bFlat ? FlatRadiusDrop : (WheelDmg * 1.2f)));
			VehMove->SetWheelRadius(w, TargetRadius);

			const float FricScale = bDetached ? 0.18f : (bFlat ? FlatFrictionScale : FMath::Lerp(1.0f, 0.78f, FMath::Max(WheelDmg, WheelBentAmount[w])));
			WheelFrictionScale[w] = FricScale;
			VehMove->SetWheelFrictionMultiplier(w, WheelBaseFriction[w] * FricScale);
			VehMove->SetWheelSlipGraphMultiplier(w, bDetached ? 0.35f : (bFlat ? 0.70f : FMath::Lerp(1.0f, 0.86f, WheelDmg)));

			const float BrakeScale = bDetached ? 0.0f : (bIsWrecked ? 0.35f : FMath::Clamp(1.0f - CornerDmg * 0.38f - (bFlat ? 0.25f : 0.0f), 0.35f, 1.0f));
			VehMove->SetWheelMaxBrakeTorque(w, WheelBaseBrakeTorque[w] * BrakeScale);

			if (bFront)
			{
				const float SteerScale = bDetached ? 0.10f : (bIsWrecked ? 0.55f : FMath::Clamp(1.0f - CornerDmg * 0.22f - WheelBentAmount[w] * 0.18f - (bFlat ? 0.12f : 0.0f), 0.45f, 1.0f));
				VehMove->SetWheelMaxSteerAngle(w, WheelBaseSteerAngle[w] * SteerScale);

				const bool bABSOk = WheelBaseABS[w] && !bIsWrecked && !bDetached && !bFlat && CornerDmg < 0.65f;
				VehMove->SetABSEnabled(w, bABSOk);
			}
		}
	}
}

void UWSPC2VehicleDamageComponent::TriggerImpactBurstFX(const FVector& WorldPoint, const FVector& WorldNormal, float Severity)
{
	if (GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	if (ImpactSparkLight)
	{
		ImpactSparkLight->SetWorldLocation(WorldPoint + WorldNormal * 18.0f);
		ImpactSparkLight->SetVisibility(true);
		SparkFlashRemaining = 0.12f;
	}

	if (SparkParticleTemplate && GetWorld() && Severity >= 0.08f)
	{
		const FRotator SparkRot = WorldNormal.Rotation();
		const FVector SparkScale(FMath::Lerp(0.22f, 0.65f, FMath::Clamp(Severity, 0.0f, 1.0f)));
		UGameplayStatics::SpawnEmitterAtLocation(GetWorld(), SparkParticleTemplate, WorldPoint + WorldNormal * 8.0f, SparkRot, SparkScale, true);
	}

	if (Severity >= 0.24f)
	{
		SpawnImpactDebris(WorldPoint, WorldNormal, Severity);
	}
}

void UWSPC2VehicleDamageComponent::SpawnImpactDebris(const FVector& WorldPoint, const FVector& WorldNormal, float Severity)
{
	UWorld* World = GetWorld();
	if (!World || !DebrisCubeMesh)
	{
		return;
	}

	const int32 NumShards = FMath::Clamp(FMath::RoundToInt(Severity * 4.0f), 1, 4);
	for (int32 i = 0; i < NumShards; ++i)
	{
		const FVector Jitter(
			FMath::FRandRange(-24.0f, 24.0f),
			FMath::FRandRange(-24.0f, 24.0f),
			FMath::FRandRange(6.0f, 28.0f));
		const FRotator RandRot(
			FMath::FRandRange(0.0f, 360.0f),
			FMath::FRandRange(0.0f, 360.0f),
			FMath::FRandRange(0.0f, 360.0f));

		FActorSpawnParameters SpawnParams;
		SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

		AStaticMeshActor* Shard = World->SpawnActor<AStaticMeshActor>(WorldPoint + WorldNormal * 16.0f + Jitter, RandRot, SpawnParams);
		if (!Shard)
		{
			continue;
		}

		UStaticMeshComponent* MeshComp = Shard->GetStaticMeshComponent();
		Shard->SetMobility(EComponentMobility::Movable);
		MeshComp->SetStaticMesh(DebrisCubeMesh);
		// Flat jagged sheet-metal / glass plate scraps rather than chunky cubes
		MeshComp->SetWorldScale3D(FVector(
			FMath::FRandRange(0.14f, 0.30f),
			FMath::FRandRange(0.08f, 0.22f),
			FMath::FRandRange(0.012f, 0.026f)));
		MeshComp->SetCollisionProfileName(TEXT("PhysicsActor"));
		MeshComp->SetCollisionResponseToAllChannels(ECR_Ignore);
		MeshComp->SetCollisionResponseToChannel(ECC_WorldStatic, ECR_Block);
		MeshComp->SetSimulatePhysics(true);
		MeshComp->SetMassOverrideInKg(NAME_None, 2.5f, true);

		if (GenericGlassFractured && (i % 3 == 0))
		{
			MeshComp->SetMaterial(0, GenericGlassFractured);
		}
		else if (BodyMIDs.Num() > 0 && BodyMIDs[0])
		{
			MeshComp->SetMaterial(0, BodyMIDs[0]);
		}

		const FVector EjectDir = (WorldNormal + FVector(FMath::FRandRange(-0.45f, 0.45f), FMath::FRandRange(-0.45f, 0.45f), 0.65f)).GetSafeNormal();
		MeshComp->SetPhysicsLinearVelocity(EjectDir * FMath::FRandRange(320.0f, 780.0f) * Severity);
		MeshComp->SetPhysicsAngularVelocityInDegrees(FVector(
			FMath::FRandRange(-540.0f, 540.0f),
			FMath::FRandRange(-540.0f, 540.0f),
			FMath::FRandRange(-540.0f, 540.0f)));

		Shard->SetLifeSpan(4.0f);
	}
}

bool UWSPC2VehicleDamageComponent::IsHoodSteamActive() const
{
	return IsValid(HoodSteamComp) && HoodSteamComp->IsActive();
}

bool UWSPC2VehicleDamageComponent::IsHoodSmokeActive() const
{
	return IsValid(HoodSmokeComp) && HoodSmokeComp->IsActive();
}

bool UWSPC2VehicleDamageComponent::IsRimSparkActive() const
{
	return IsValid(RimSparkComp) && RimSparkComp->IsActive();
}

void UWSPC2VehicleDamageComponent::ClearContactDamageDecals()
{
	if (!IsEngineExitRequested() && !GExitPurge)
	{
		for (const TWeakObjectPtr<UDecalComponent>& WeakDecal : ContactDamageDecals)
		{
			UDecalComponent* Decal = WeakDecal.Get();
			if (IsValid(Decal) && !Decal->IsUnreachable())
			{
				Decal->DestroyComponent();
			}
		}
	}
	ContactDamageDecals.Reset();
}

void UWSPC2VehicleDamageComponent::SpawnLocalizedContactDecal(const FVector& LocalHit, const FVector& InwardDir, float Severity)
{
	AActor* Owner = GetOwner();
	if (!Owner || GetNetMode() == NM_DedicatedServer || !LocalizedDamageDecalMat || Severity < 0.12f)
	{
		return;
	}
	if (!DeformableChassis || !DeformableChassis->IsActive() || DeformableChassis->UsesWSPC2DamageMaterial())
	{
		return;
	}

	USceneComponent* AttachParent = (BodyMesh && BodyMesh->GetAttachParent()) ? BodyMesh->GetAttachParent() : Owner->GetRootComponent();
	if (!AttachParent)
	{
		return;
	}

	while (ContactDamageDecals.Num() >= 10)
	{
		UDecalComponent* Oldest = ContactDamageDecals[0].Get();
		if (IsValid(Oldest) && !Oldest->IsUnreachable())
		{
			Oldest->DestroyComponent();
		}
		ContactDamageDecals.RemoveAt(0);
	}

	UDecalComponent* Decal = NewObject<UDecalComponent>(Owner, NAME_None);
	if (!Decal)
	{
		return;
	}

	const FVector SafeInward = InwardDir.IsNearlyZero() ? FVector(-1.0f, 0.0f, 0.0f) : InwardDir.GetSafeNormal();
	const FTransform ParentXf = AttachParent->GetComponentTransform();
	const FTransform ActorXf = Owner->GetActorTransform();
	const FVector WorldPos = ActorXf.TransformPosition(LocalHit - SafeInward * 2.5f);
	const FVector WorldInward = ActorXf.TransformVectorNoScale(SafeInward).GetSafeNormal();
	const float RollDeg = FMath::FRandRange(-18.0f, 18.0f);
	const FQuat WorldRot = FQuat(WorldInward.Rotation()) * FQuat(FVector(1.0f, 0.0f, 0.0f), FMath::DegreesToRadians(RollDeg));

	Decal->SetupAttachment(AttachParent);
	Decal->SetRelativeTransform(FTransform(WorldRot, WorldPos).GetRelativeTransform(ParentXf));
	Decal->DecalSize = FVector(
		18.0f,
		FMath::Clamp(22.0f + Severity * 20.0f, 20.0f, 42.0f),
		FMath::Clamp(16.0f + Severity * 16.0f, 16.0f, 32.0f));
	Decal->FadeScreenSize = 0.0005f;

	UMaterialInstanceDynamic* DecalMID = UMaterialInstanceDynamic::Create(LocalizedDamageDecalMat, Decal);
	if (DecalMID)
	{
		DecalMID->SetScalarParameterValue(TEXT("DecalIntensity"), FMath::Clamp(0.45f + Severity * 0.55f, 0.40f, 0.96f));
		DecalMID->SetScalarParameterValue(TEXT("SeedOffset"), FMath::FRandRange(0.0f, 19.0f));
		DecalMID->SetScalarParameterValue(TEXT("SootBias"), FMath::Clamp(Severity * 0.60f, 0.15f, 0.70f));
		Decal->SetDecalMaterial(DecalMID);
	}
	else
	{
		Decal->SetDecalMaterial(LocalizedDamageDecalMat);
	}

	Decal->RegisterComponent();
	ContactDamageDecals.Add(Decal);
}
