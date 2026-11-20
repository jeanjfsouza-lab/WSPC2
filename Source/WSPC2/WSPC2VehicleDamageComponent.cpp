// Copyright Epic Games, Inc. All Rights Reserved.

#include "WSPC2VehicleDamageComponent.h"
#include "WSPC2.h"
#include "WSPC2VehicleTuning.h"
#include "ChaosWheeledVehicleMovementComponent.h"
#include "ChaosVehicleWheel.h"
#include "Components/BoxComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/PrimitiveComponent.h"
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
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, HealthPercent);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, bIsWrecked);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, PropertyDamageDollars);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, CollisionCount);
	DOREPLIFETIME(UWSPC2VehicleDamageComponent, LastImpact);
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
		}
	}
}

void UWSPC2VehicleDamageComponent::CaptureBaselineTuning()
{
	AActor* Owner = GetOwner();
	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
	const UChaosWheeledVehicleMovementComponent* VehMove = Owner ? Owner->FindComponentByClass<UChaosWheeledVehicleMovementComponent>() : nullptr;

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
	else if (VehMove)
	{
		BaseMaxTorque = FMath::Max(VehMove->EngineSetup.MaxTorque, 100.0f);
		BaseDragCoefficient = VehMove->DragCoefficient;
		BaseDownforceCoefficient = VehMove->DownforceCoefficient;
		bBaselinesCaptured = true;
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
		}
	}

	if (GlassMesh)
	{
		InitialGlassRelativeTransform = GlassMesh->GetRelativeTransform();
		OriginalGlassMaterials.Reset();
		const int32 NumGlassMats = GlassMesh->GetNumMaterials();
		for (int32 Slot = 0; Slot < NumGlassMats; ++Slot)
		{
			OriginalGlassMaterials.Add(GlassMesh->GetMaterial(Slot));
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

	// Engine misfire / sputter cycles once radiator/engine block has moderate-to-heavy damage
	const float EngineStress = FMath::Max(ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Front)], (100.0f - HealthPercent) * 0.0085f);
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
		const bool bShowEngineFire = bIsWrecked || ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Front)] > 0.62f;
		EngineHazardLight->SetVisibility(bShowEngineFire);
		if (bShowEngineFire)
		{
			const float Flicker = 0.60f + 0.40f * FMath::Sin(HazardFlickerPhase) * FMath::Cos(HazardFlickerPhase * 2.3f);
			EngineHazardLight->SetIntensity((bIsWrecked ? 52000.0f : 24000.0f) * Flicker);
		}
	}

	// Continuous rim-on-asphalt sparks while rolling at speed on a punctured wheel
	if (RimSparkComp)
	{
		int32 ActiveFlatWheel = -1;
		for (int32 w = 0; w < 4; ++w)
		{
			if (bWheelPunctured[w])
			{
				ActiveFlatWheel = w;
				break;
			}
		}

		const bool bEmitRimSparks = (ActiveFlatWheel >= 0 && SpeedKmh > 16.0f);
		if (bEmitRimSparks)
		{
			const FVector Hub = WheelHubPositions[ActiveFlatWheel];
			RimSparkComp->SetRelativeLocation(FVector(Hub.X, Hub.Y, FMath::Max(6.0f, Hub.Z - WheelBaseRadii[ActiveFlatWheel] + 7.0f)));
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
	const float ArmorScale = bIsPoliceCruiser ? (Tuning ? Tuning->PoliceArmorDamageScale : 0.58f) : 1.0f;
	const float HealthMult = Tuning ? Tuning->DamageZoneToHealthScale : 27.5f;
	const float BlowoutSev = Tuning ? Tuning->DamageWheelBlowoutSeverity : 0.60f;

	const float SpeedFactor = FMath::Max(0.0f, (ImpactSpeedKmh - (MinSpeed * 0.65f)) / FMath::Max(SevereSpeed - MinSpeed, 20.0f));
	const float ImpulseFactor = ImpulseMagnitude / FMath::Max(SevereImpulse, 100000.0f);
	const float Severity = FMath::Clamp(FMath::Max(SpeedFactor, ImpulseFactor), 0.04f, 1.45f);

	const FVector LocalHit = Owner->GetActorTransform().InverseTransformPosition(WorldImpactPoint);
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
	bIsWrecked = (HealthPercent <= 0.0f);
	++CollisionCount;
	PropertyDamageDollars += FMath::Max(55, FMath::RoundToInt(Severity * 1750.0f));

	// Deplete per-wheel integrity on corner impacts; blow out tyre immediately on heavy impact or accumulated abuse
	if (Zone != EWSPC2DamageZone::Roof && Severity >= 0.16f)
	{
		int32 BestWheel = -1;
		float BestDist = 132.0f;
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
			const float ProxAlpha = FMath::Clamp(1.0f - (BestDist / 132.0f) * 0.45f, 0.55f, 1.0f);
			WheelHealth[BestWheel] = FMath::Clamp(WheelHealth[BestWheel] - Severity * ProxAlpha * ArmorScale * 0.90f, 0.0f, 1.0f);

			const float Threshold = bIsPoliceCruiser ? BlowoutSev : BlowoutSev * 0.72f;
			if (WheelHealth[BestWheel] <= 0.0f || Severity >= Threshold)
			{
				PunctureWheel(BestWheel);
			}
		}
	}

	// Catastrophic wreck can burst a weakened wheel on the hardest-hit corner
	if (bIsWrecked && GetPuncturedWheelCount() == 0)
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

	UE_LOG(LogWSPC2, Log, TEXT("ChaosDamage [%s]: tier=%s zone=%d severity=%.2f speed=%.1f km/h impulse=%.0f -> health=%.1f%% eng=%.0f%% prop=$%d tyresFlat=%d"),
		*GetNameSafe(Owner), GetDamageStageName(), ZoneIdx, Severity, ImpactSpeedKmh, ImpulseMagnitude,
		HealthPercent, GetEngineHealthTorqueFactor() * 100.0f, PropertyDamageDollars, GetPuncturedWheelCount());

	OnVehicleDamaged.Broadcast(Zone, Severity, HealthPercent);
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
		bWheelPunctured[w] = false;
		WheelCamberTiltDeg[w] = 0.0f;
	}

	PuncturedWheelMask = 0;
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
		for (int32 Slot = 0; Slot < OriginalGlassMaterials.Num(); ++Slot)
		{
			if (OriginalGlassMaterials[Slot])
			{
				GlassMesh->SetMaterial(Slot, OriginalGlassMaterials[Slot]);
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

void UWSPC2VehicleDamageComponent::RecalculateWheelCamberAndFlags()
{
	for (int32 w = 0; w < 4; ++w)
	{
		const uint8 Bit = static_cast<uint8>(1u << w);
		bWheelPunctured[w] = (PuncturedWheelMask & Bit) != 0;

		const bool bRightSide = (w % 2) == 1;
		const float Sign = bRightSide ? -1.0f : 1.0f;
		if (bWheelPunctured[w])
		{
			WheelCamberTiltDeg[w] = Sign * 8.5f;
		}
		else
		{
			const float HubWear = FMath::Clamp(1.0f - WheelHealth[w], 0.0f, 1.0f);
			WheelCamberTiltDeg[w] = (HubWear > 0.25f) ? Sign * FMath::Lerp(0.0f, 4.2f, (HubWear - 0.25f) / 0.75f) : 0.0f;
		}
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

	// Light front bumps shave off a touch of response; radiator & drivetrain crush sap heavy torque
	const float EngineWear = FMath::Clamp(FrontDamage * 0.78f + RearDamage * 0.14f + OverallDamage * 0.28f, 0.0f, 1.0f);
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

	// Crumple silhouette plus subtle broken-suspension sag toward punctured wheels
	const float LeftSag = (bWheelPunctured[0] ? 1.8f : 0.0f) + (bWheelPunctured[2] ? 1.8f : 0.0f);
	const float RightSag = (bWheelPunctured[1] ? 1.8f : 0.0f) + (bWheelPunctured[3] ? 1.8f : 0.0f);
	const float FrontSag = (bWheelPunctured[0] ? 1.6f : 0.0f) + (bWheelPunctured[1] ? 1.6f : 0.0f);
	const float RearSag = (bWheelPunctured[2] ? 1.6f : 0.0f) + (bWheelPunctured[3] ? 1.6f : 0.0f);

	const FVector CrushScale(
		1.0f - 0.050f * (Front + Rear),
		1.0f - 0.038f * (Left + Right),
		1.0f - 0.058f * Roof);

	const FVector CrushShift(
		(Rear - Front) * 6.5f,
		(Left - Right) * 3.5f,
		-Roof * 4.8f - 0.5f * (LeftSag + RightSag));

	const FRotator CrushTilt(
		(Rear - Front) * 1.9f + (RearSag - FrontSag) * 0.65f,
		(Left - Right) * 1.1f,
		(Right - Left) * 2.8f + (LeftSag - RightSag) * 0.95f);

	FTransform DeformedBody = InitialBodyRelativeTransform;
	DeformedBody.SetScale3D(InitialBodyRelativeTransform.GetScale3D() * CrushScale);
	DeformedBody.AddToTranslation(CrushShift);
	DeformedBody.SetRotation(InitialBodyRelativeTransform.GetRotation() * CrushTilt.Quaternion());
	BodyMesh->SetRelativeTransform(DeformedBody);

	for (int32 z = 0; z < 5; ++z)
	{
		BodyMesh->SetCustomPrimitiveDataFloat(z, ZoneDamage[z]);
	}

	if (GlassMesh)
	{
		FTransform DeformedGlass = InitialGlassRelativeTransform;
		DeformedGlass.SetScale3D(InitialGlassRelativeTransform.GetScale3D() * CrushScale);
		DeformedGlass.AddToTranslation(CrushShift);
		DeformedGlass.SetRotation(InitialGlassRelativeTransform.GetRotation() * CrushTilt.Quaternion());
		GlassMesh->SetRelativeTransform(DeformedGlass);
	}

	const float Clearcoat = FMath::Lerp(0.75f, 0.10f, TotalSeverity);
	const float DirtAmt = FMath::Lerp(0.88f, 3.60f, TotalSeverity);
	const float SplatterAmt = FMath::Lerp(1.00f, 3.90f, TotalSeverity);
	const float DustAmt = FMath::Lerp(0.20f, 1.95f, TotalSeverity);
	const float BulletNormal = FMath::Lerp(3.78f, 9.80f, TotalSeverity);
	const FLinearColor DentParams(0.50f, FMath::Lerp(0.20f, 0.46f, TotalSeverity), CurrentDentStrength, 0.66f);
	const FLinearColor DentOffset((Front - Rear) * 0.25f, (Right - Left) * 0.25f, 0.0f, 1.0f);

	for (UMaterialInstanceDynamic* MID : BodyMIDs)
	{
		if (!MID)
		{
			continue;
		}

		// Real CitySampleVehicles M_Veh_CarPaint / M_Veh_Opaque / VehicleImperfection parameters
		MID->SetScalarParameterValue(TEXT("Primer Threshold PI"), CurrentPrimerThreshold);
		MID->SetScalarParameterValue(TEXT("Metal Threshold PI"), CurrentMetalThreshold);
		MID->SetScalarParameterValue(TEXT("Dirt Amt PI"), DirtAmt);
		MID->SetScalarParameterValue(TEXT("DirtSplatter Amt PI"), SplatterAmt);
		MID->SetScalarParameterValue(TEXT("Dust Amt PI"), DustAmt);
		MID->SetScalarParameterValue(TEXT("ClearcoatIntensity"), Clearcoat);
		MID->SetScalarParameterValue(TEXT("BulletImpactNormalStrength"), BulletNormal);
		MID->SetVectorParameterValue(TEXT("Dent Params"), DentParams);
		MID->SetVectorParameterValue(TEXT("Dent Mask Offset"), DentOffset);

		// Fallback names for generic materials
		MID->SetScalarParameterValue(TEXT("Damage"), TotalSeverity);
		MID->SetScalarParameterValue(TEXT("Dirt"), TotalSeverity * 0.65f);
		MID->SetScalarParameterValue(TEXT("Roughness"), FMath::Lerp(0.22f, 0.68f, TotalSeverity));
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
	else if (GenericGlassFractured)
	{
		const int32 NumMats = GlassMesh->GetNumMaterials();
		const TArray<FName> SlotNames = GlassMesh->GetMaterialSlotNames();

		if (GlassCrackStage < 1 && (GlassStrain >= 0.20f || bIsWrecked))
		{
			bool bMatchedWindshield = false;
			for (int32 Slot = 0; Slot < NumMats; ++Slot)
			{
				const FString SlotStr = SlotNames.IsValidIndex(Slot) ? SlotNames[Slot].ToString() : FString();
				const FString MatStr = OriginalGlassMaterials.IsValidIndex(Slot) && OriginalGlassMaterials[Slot] ? OriginalGlassMaterials[Slot]->GetName() : FString();
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
					const FString SlotStr = SlotNames.IsValidIndex(Slot) ? SlotNames[Slot].ToString() : FString();
					const FString MatStr = OriginalGlassMaterials.IsValidIndex(Slot) && OriginalGlassMaterials[Slot] ? OriginalGlassMaterials[Slot]->GetName() : FString();
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
				const FString SlotStr = SlotNames.IsValidIndex(Slot) ? SlotNames[Slot].ToString() : FString();
				const FString MatStr = OriginalGlassMaterials.IsValidIndex(Slot) && OriginalGlassMaterials[Slot] ? OriginalGlassMaterials[Slot]->GetName() : FString();
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
}

void UWSPC2VehicleDamageComponent::UpdateLightMaterials()
{
	if (!BodyMesh)
	{
		return;
	}

	const float Front = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Front)];
	const float Rear = ZoneDamage[static_cast<int32>(EWSPC2DamageZone::Rear)];
	const float HeadlightHealth = bIsWrecked ? 0.0f : FMath::Clamp(1.0f - (Front - 0.18f) / 0.62f, 0.0f, 1.0f);
	const float TaillightHealth = bIsWrecked ? 0.0f : FMath::Clamp(1.0f - (Rear - 0.22f) / 0.65f, 0.0f, 1.0f);

	if (bIsPoliceCruiser)
	{
		// Slot 4 on SM_Body_NoFrontBrakes is 'veh_light' (MI_vehCar_vehicle13_3 / M_vehCar_vehicle13_3_Fractured)
		const int32 LightSlot = 4;
		if (BodyMesh->GetNumMaterials() > LightSlot)
		{
			if (!bHeadlightHousingFractured && (Front >= 0.65f || Rear >= 0.72f || bIsWrecked) && PoliceLightHousingFractured)
			{
				BodyMesh->SetMaterial(LightSlot, PoliceLightHousingFractured);
				UMaterialInstanceDynamic* FracturedMID = BodyMesh->CreateDynamicMaterialInstance(LightSlot, PoliceLightHousingFractured);
				if (BodyMIDs.IsValidIndex(LightSlot))
				{
					BodyMIDs[LightSlot] = FracturedMID;
				}
				bHeadlightHousingFractured = true;
			}

			if (BodyMIDs.IsValidIndex(LightSlot) && BodyMIDs[LightSlot])
			{
				BodyMIDs[LightSlot]->SetScalarParameterValue(TEXT("Headlight Amt LE"), HeadlightHealth);
				BodyMIDs[LightSlot]->SetScalarParameterValue(TEXT("Run Amt LE"), TaillightHealth);
				BodyMIDs[LightSlot]->SetScalarParameterValue(TEXT("Brake Amt LE"), TaillightHealth);
				BodyMIDs[LightSlot]->SetScalarParameterValue(TEXT("PoliceLight Amt"), CurrentSirenHealthFactor);
			}
		}
		return;
	}

	// Generic support for all other CitySampleVehicles & imported vehicles: dim any body slot named *light*
	const TArray<FName> SlotNames = BodyMesh->GetMaterialSlotNames();
	for (int32 Slot = 0; Slot < BodyMIDs.Num(); ++Slot)
	{
		if (!BodyMIDs[Slot])
		{
			continue;
		}
		const FString SlotStr = SlotNames.IsValidIndex(Slot) ? SlotNames[Slot].ToString() : FString();
		const FString MatStr = OriginalBodyMaterials.IsValidIndex(Slot) && OriginalBodyMaterials[Slot] ? OriginalBodyMaterials[Slot]->GetName() : FString();
		if (SlotStr.Contains(TEXT("light"), ESearchCase::IgnoreCase) || MatStr.Contains(TEXT("light"), ESearchCase::IgnoreCase))
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

		// 2. Crushed bodywork and dragging blown rims add aerodynamic & rolling drag while reducing downforce
		const float ExtraDrag = TotalSeverity * 0.42f + GetPuncturedWheelCount() * 0.06f + (bIsWrecked ? 0.35f : 0.0f);
		VehMove->SetDragCoefficient(BaseDragCoefficient + ExtraDrag);
		const float AeroLoss = FMath::Clamp(1.0f - (Front * 0.35f + Rear * 0.25f + TotalSeverity * 0.15f), 0.45f, 1.0f);
		VehMove->SetDownforceCoefficient(BaseDownforceCoefficient * AeroLoss);

		// 3. Per-wheel radius, friction, slip grip, brake torque fade, steering travel limit, and ABS failures
		const int32 NumWheels = FMath::Min(4, VehMove->WheelSetups.Num());
		for (int32 w = 0; w < NumWheels; ++w)
		{
			const bool bFront = (w < 2);
			const bool bRight = (w % 2) == 1;
			const float EndDmg = bFront ? Front : Rear;
			const float SideDmg = bRight ? Right : Left;
			const float CornerDmg = FMath::Clamp(0.65f * EndDmg + 0.55f * SideDmg, 0.0f, 1.0f);
			const float WheelDmg = FMath::Clamp(1.0f - WheelHealth[w], 0.0f, 1.0f);
			const bool bFlat = bWheelPunctured[w];

			const float RadiusDrop = bFlat ? FlatRadiusDrop : (WheelDmg * 1.2f);
			VehMove->SetWheelRadius(w, FMath::Max(18.0f, WheelBaseRadii[w] - RadiusDrop));

			const float FricScale = bFlat ? FlatFrictionScale : FMath::Lerp(1.0f, 0.84f, WheelDmg);
			WheelFrictionScale[w] = FricScale;
			VehMove->SetWheelFrictionMultiplier(w, WheelBaseFriction[w] * FricScale);
			VehMove->SetWheelSlipGraphMultiplier(w, bFlat ? 0.70f : FMath::Lerp(1.0f, 0.88f, WheelDmg));

			const float BrakeScale = bIsWrecked ? 0.35f : FMath::Clamp(1.0f - CornerDmg * 0.38f - (bFlat ? 0.25f : 0.0f), 0.35f, 1.0f);
			VehMove->SetWheelMaxBrakeTorque(w, WheelBaseBrakeTorque[w] * BrakeScale);

			if (bFront)
			{
				const float SteerScale = bIsWrecked ? 0.55f : FMath::Clamp(1.0f - CornerDmg * 0.22f - (bFlat ? 0.12f : 0.0f), 0.58f, 1.0f);
				VehMove->SetWheelMaxSteerAngle(w, WheelBaseSteerAngle[w] * SteerScale);

				const bool bABSOk = WheelBaseABS[w] && !bIsWrecked && !bFlat && CornerDmg < 0.65f;
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
		MeshComp->SetWorldScale3D(FVector(
			FMath::FRandRange(0.08f, 0.24f),
			FMath::FRandRange(0.05f, 0.16f),
			FMath::FRandRange(0.02f, 0.06f)));
		MeshComp->SetCollisionProfileName(TEXT("PhysicsActor"));
		MeshComp->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
		MeshComp->SetCollisionResponseToChannel(ECC_Vehicle, ECR_Ignore);
		MeshComp->SetSimulatePhysics(true);
		MeshComp->SetMassOverrideInKg(NAME_None, 2.5f, true);

		if (GenericGlassFractured && (i % 2 == 0))
		{
			MeshComp->SetMaterial(0, GenericGlassFractured);
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
