// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "WSPC2VehicleDamageComponent.generated.h"

class UPrimitiveComponent;
class UStaticMeshComponent;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class UPointLightComponent;
class UParticleSystemComponent;
class UParticleSystem;
class UStaticMesh;

UENUM(BlueprintType)
enum class EWSPC2DamageZone : uint8
{
	Front = 0,
	Rear = 1,
	Left = 2,
	Right = 3,
	Roof = 4,
	Count = 5
};

UENUM(BlueprintType)
enum class EWSPC2DamageStage : uint8
{
	Pristine = 0,
	Light = 1,
	Moderate = 2,
	Heavy = 3,
	Wrecked = 4
};

USTRUCT()
struct FWSPC2DamageImpactNet
{
	GENERATED_BODY()

	UPROPERTY()
	FVector_NetQuantize WorldPoint = FVector::ZeroVector;

	UPROPERTY()
	FVector_NetQuantizeNormal WorldNormal = FVector::UpVector;

	UPROPERTY()
	float Severity = 0.0f;

	UPROPERTY()
	uint8 Zone = 0;

	UPROPERTY()
	uint8 Sequence = 0;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FWSPC2OnVehicleDamaged, EWSPC2DamageZone, Zone, float, ImpactSeverity, float, NewHealthPercent);

/**
 * Real-time server-authoritative Chaos collision & vehicle damage manager.
 * Drives physical (wheel blowout, aero drag, debris, corner sag), visual
 * (wear/primer/metal/dent shader parameters, glass/lightbar fracture, steam/smoke/sparks/fire VFX),
 * and mechanical (engine torque loss, misfire, brake fade, ABS fault, steering pull/shimmy, stall)
 * degradation from light scuffs to total wreck.
 */
UCLASS(ClassGroup = (WSPC2), meta = (BlueprintSpawnableComponent))
class UWSPC2VehicleDamageComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UWSPC2VehicleDamageComponent();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** Registers chassis collision & visual meshes so Chaos impacts drive deformation, glass fracture, VFX, and wheel/engine damage. */
	void SetupDamageRig(
		UPrimitiveComponent* InRootPhysicsBody,
		UStaticMeshComponent* InBodyMesh,
		UStaticMeshComponent* InGlassMesh,
		const TArray<TObjectPtr<UStaticMeshComponent>>& InWheelMeshes,
		const FVector InWheelHubPositions[4],
		const float InWheelRadii[4],
		bool bInIsPoliceCruiser);

	/** Re-reads baseline Chaos engine, aero, brake, and friction values from tuning settings/movement component. */
	void CaptureBaselineTuning();

	/** Scales baseline engine torque to match the active hero vehicle profile (1.0 = default patrol car). */
	void SetBaselineTorqueScale(float InScale) { BaselineTorqueScale = FMath::Clamp(InScale, 0.25f, 4.0f); }

	/** Applies a collision impact authoritatively (server/standalone only; no-op on simulated clients). */
	UFUNCTION(BlueprintCallable, Category = "Vehicle|Damage")
	void ApplyDirectImpact(const FVector& WorldImpactPoint, const FVector& WorldImpactNormal, float ImpactSpeedKmh, float ImpulseMagnitude);

	/** Punctures/buckles a specific wheel (0=FL, 1=FR, 2=RL, 3=RR) authoritatively. */
	UFUNCTION(BlueprintCallable, Category = "Vehicle|Damage")
	void PunctureWheel(int32 WheelIndex);

	/** Restores vehicle body, glass, lights, VFX, tyres, suspension, brakes, and engine to 100% pristine condition. */
	UFUNCTION(BlueprintCallable, Category = "Vehicle|Damage")
	void RepairAll();

	UFUNCTION(BlueprintPure, Category = "Vehicle|Damage")
	float GetHealthPercent() const { return HealthPercent; }

	UFUNCTION(BlueprintPure, Category = "Vehicle|Damage")
	EWSPC2DamageStage GetDamageStage() const;

	const TCHAR* GetDamageStageName() const;

	UFUNCTION(BlueprintPure, Category = "Vehicle|Damage")
	bool IsWrecked() const { return bIsWrecked; }

	UFUNCTION(BlueprintPure, Category = "Vehicle|Damage")
	bool IsEngineStalled() const { return bIsWrecked; }

	UFUNCTION(BlueprintPure, Category = "Vehicle|Damage")
	int32 GetPropertyDamageDollars() const { return PropertyDamageDollars; }

	UFUNCTION(BlueprintPure, Category = "Vehicle|Damage")
	int32 GetCollisionCount() const { return CollisionCount; }

	UFUNCTION(BlueprintPure, Category = "Vehicle|Damage")
	int32 GetPuncturedWheelCount() const;

	bool IsWheelPunctured(int32 WheelIndex) const
	{
		return (WheelIndex >= 0 && WheelIndex < 4) ? bWheelPunctured[WheelIndex] : false;
	}

	float GetWheelHealth(int32 WheelIndex) const
	{
		return (WheelIndex >= 0 && WheelIndex < 4) ? WheelHealth[WheelIndex] : 1.0f;
	}

	float GetWheelCamberDamageDeg(int32 WheelIndex) const
	{
		return (WheelIndex >= 0 && WheelIndex < 4) ? WheelCamberTiltDeg[WheelIndex] : 0.0f;
	}

	float GetWheelVisualDropCm(int32 WheelIndex) const;

	float GetZoneDamage(EWSPC2DamageZone Zone) const
	{
		const int32 Idx = static_cast<int32>(Zone);
		return (Idx >= 0 && Idx < 5) ? ZoneDamage[Idx] : 0.0f;
	}

	/** Current effective engine torque ratio [0..1] after damage penalties (0 when wrecked). */
	float GetEngineHealthTorqueFactor() const;

	/** Instantaneous throttle multiplier [0..1] including misfire sputters in moderate/heavy damage. */
	float GetThrottleDamageMultiplier() const;

	/** Siren/lightbar electrical reliability factor [0..1] for roof light & audio glitches. */
	float GetSirenLightHealthFactor() const { return CurrentSirenHealthFactor; }

	/** Asymmetric front suspension/tie-rod pull + speed shimmy bias caused by hits and flat front tyres. */
	float GetSteeringPullBias() const;

	/** Active shader wear parameters pushed to body MIDs (for verification & telemetry). */
	float GetCurrentPrimerThreshold() const { return CurrentPrimerThreshold; }
	float GetCurrentMetalThreshold() const { return CurrentMetalThreshold; }
	float GetCurrentDentStrength() const { return CurrentDentStrength; }

	/** Visual fracture & VFX active flags (for HUD diagnostics & automated tests). */
	int32 GetGlassCrackStage() const { return GlassCrackStage; }
	bool IsSideGlassFractured() const { return bSideGlassFractured; }
	bool IsLightbarFractured() const { return bLightbarFractured; }
	bool IsHeadlightHousingFractured() const { return bHeadlightHousingFractured; }
	bool IsHoodSteamActive() const;
	bool IsHoodSmokeActive() const;
	bool IsRimSparkActive() const;

	UPROPERTY(BlueprintAssignable, Category = "Vehicle|Damage")
	FWSPC2OnVehicleDamaged OnVehicleDamaged;

protected:
	UFUNCTION()
	void HandleActorHit(AActor* SelfActor, AActor* OtherActor, FVector NormalImpulse, const FHitResult& Hit);

	UFUNCTION()
	void OnRep_DamageState();

	UFUNCTION()
	void OnRep_LastImpact();

	void RefreshAllDamageSystems();
	void ApplyVisualDeformation();
	void UpdateGlassFractureMaterials();
	void UpdateLightMaterials();
	void UpdateDamageVFX();
	void ApplyMechanicalPenalties();
	void TriggerImpactBurstFX(const FVector& WorldPoint, const FVector& WorldNormal, float Severity);
	void SpawnImpactDebris(const FVector& WorldPoint, const FVector& WorldNormal, float Severity);
	void RecalculateWheelCamberAndFlags();

private:
	UPROPERTY()
	TObjectPtr<UPrimitiveComponent> RootPhysicsBody;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> BodyMesh;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> GlassMesh;

	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> WheelMeshes;

	UPROPERTY()
	TArray<TObjectPtr<UMaterialInstanceDynamic>> BodyMIDs;

	UPROPERTY()
	TArray<TObjectPtr<UMaterialInterface>> OriginalBodyMaterials;

	UPROPERTY()
	TArray<TObjectPtr<UMaterialInterface>> OriginalGlassMaterials;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> PoliceWindshieldCrack1;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> PoliceWindshieldCrack2;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> PoliceLightbarFractured;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> PoliceLightHousingFractured;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> GenericGlassFractured;

	UPROPERTY()
	TObjectPtr<UStaticMesh> DebrisCubeMesh;

	UPROPERTY()
	TObjectPtr<UParticleSystem> SteamParticleTemplate;

	UPROPERTY()
	TObjectPtr<UParticleSystem> SmokeParticleTemplate;

	UPROPERTY()
	TObjectPtr<UParticleSystem> WreckSmokeParticleTemplate;

	UPROPERTY()
	TObjectPtr<UParticleSystem> SparkParticleTemplate;

	UPROPERTY()
	TObjectPtr<UPointLightComponent> ImpactSparkLight;

	UPROPERTY()
	TObjectPtr<UPointLightComponent> EngineHazardLight;

	UPROPERTY()
	TObjectPtr<UParticleSystemComponent> HoodSteamComp;

	UPROPERTY()
	TObjectPtr<UParticleSystemComponent> HoodSmokeComp;

	UPROPERTY()
	TObjectPtr<UParticleSystemComponent> RimSparkComp;

	FTransform InitialBodyRelativeTransform;
	FTransform InitialGlassRelativeTransform;
	bool bRigConfigured = false;
	bool bIsPoliceCruiser = false;
	bool bBaselinesCaptured = false;

	FVector WheelHubPositions[4];
	float WheelBaseRadii[4] = { 35.2f, 35.2f, 35.2f, 35.2f };
	float WheelBaseFriction[4] = { 2.35f, 2.35f, 2.42f, 2.42f };
	float WheelBaseBrakeTorque[4] = { 4200.0f, 4200.0f, 2200.0f, 2200.0f };
	float WheelBaseSteerAngle[4] = { 36.0f, 36.0f, 0.0f, 0.0f };
	bool WheelBaseABS[4] = { true, true, true, true };
	float BaseMaxTorque = 520.0f;
	float BaselineTorqueScale = 1.0f;
	float BaseDragCoefficient = 0.34f;
	float BaseDownforceCoefficient = 0.14f;

	UPROPERTY(ReplicatedUsing = OnRep_DamageState)
	float ZoneDamage[5] = { 0.0f, 0.0f, 0.0f, 0.0f, 0.0f };

	UPROPERTY(ReplicatedUsing = OnRep_DamageState)
	float WheelHealth[4] = { 1.0f, 1.0f, 1.0f, 1.0f };

	UPROPERTY(ReplicatedUsing = OnRep_DamageState)
	uint8 PuncturedWheelMask = 0;

	UPROPERTY(ReplicatedUsing = OnRep_DamageState)
	float HealthPercent = 100.0f;

	UPROPERTY(ReplicatedUsing = OnRep_DamageState)
	bool bIsWrecked = false;

	UPROPERTY(ReplicatedUsing = OnRep_DamageState)
	int32 PropertyDamageDollars = 0;

	UPROPERTY(ReplicatedUsing = OnRep_DamageState)
	int32 CollisionCount = 0;

	UPROPERTY(ReplicatedUsing = OnRep_LastImpact)
	FWSPC2DamageImpactNet LastImpact;

	bool bWheelPunctured[4] = { false, false, false, false };
	float WheelCamberTiltDeg[4] = { 0.0f, 0.0f, 0.0f, 0.0f };
	int32 GlassCrackStage = 0;
	bool bSideGlassFractured = false;
	bool bLightbarFractured = false;
	bool bHeadlightHousingFractured = false;
	bool bWreckSmokeTemplateActive = false;

	double LastHitTimeSeconds = -10.0;
	float SparkFlashRemaining = 0.0f;
	float HazardFlickerPhase = 0.0f;
	float MisfireTimer = 0.0f;
	float MisfireCutRemaining = 0.0f;
	float CurrentSirenHealthFactor = 1.0f;
	float ShimmyPhase = 0.0f;

	float CurrentPrimerThreshold = 0.80f;
	float CurrentMetalThreshold = 0.95f;
	float CurrentDentStrength = 0.15f;
};
