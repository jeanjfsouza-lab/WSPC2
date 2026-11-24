// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "WSPC2Pawn.h"
#include "WSPC2VehicleProfile.h"
#include "PrimitiveComponentId.h"
#include "WSPC2SportsCar.generated.h"

class UStaticMeshComponent;
class USkeletalMeshComponent;
class UStaticMesh;
class UBoxComponent;
class UWSPC2CrewComponent;

/**
 *  Playable hero pursuit vehicle (defaults to the Police Department patrol cruiser).
 *  Handling comes from UWSPC2VehicleTuning with optional per-profile class scaling.
 *
 *  Supports switching across built-in CitySampleVehicles hero profiles (Patrol, Undercover,
 *  Interceptor, SUV, Pickup, SWATVan), /Game/CrownVic fallback, or any custom UWSPC2VehicleProfile
 *  DataAsset (including +X prepared GLB vehicles) while preserving Chaos physics, audio,
 *  progressive damage, crew seats, and cameras.
 */
UCLASS(abstract)
class AWSPC2SportsCar : public AWSPC2Pawn
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, Category = "Components")
	UStaticMeshComponent* SedanBody;

	/** Transparent windows, headlights, taillights, and roof police lightbar */
	UPROPERTY(VisibleAnywhere, Category = "Components")
	UStaticMeshComponent* SedanGlass;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TArray<TObjectPtr<UStaticMeshComponent>> SedanWheels;

	/** Front brake discs and calipers: they steer with the front wheels and ride the suspension, but do not spin. */
	UPROPERTY(VisibleAnywhere, Category = "Components")
	TArray<TObjectPtr<UStaticMeshComponent>> FrontBrakes;

	/** Collision for the lower body, bumper to bumper */
	UPROPERTY(VisibleAnywhere, Category = "Components")
	UBoxComponent* BodyCollision;

	/** Collision for the cabin and roof */
	UPROPERTY(VisibleAnywhere, Category = "Components")
	UBoxComponent* CabinCollision;

	/** The officers drawn in the car (driver and gunner), posed every frame; from the preset's CrewProfile, empty when
	 *  the crew assets are not installed */
	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<UWSPC2CrewComponent> Crew;

	/** The steering wheel cut out of the body (car space), turned with the steering */
	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<UStaticMeshComponent> SteeringWheel;

	FVector SteeringWheelCentre = FVector::ZeroVector;
	FVector SteeringWheelAxis = FVector(-1.0f, 0.0f, 0.0f);
	float SteeringWheelMaxDeg = 0.0f;
	float DrawnSteering = 0.0f;

	/** Optional DataAsset overriding the built-in preset (allows dropping in any custom/GLB hero vehicle). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Vehicle", meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UWSPC2VehicleProfile> VehicleProfileAsset;

	/** Replicated active built-in preset identifier (Patrol, Undercover, Interceptor, SUV, Pickup, SWATVan, CrownVic). */
	UPROPERTY(ReplicatedUsing = OnRep_ActiveVehiclePresetId)
	FName ActiveVehiclePresetId = FName("Patrol");

	/** True once a hero vehicle body was found and applied */
	bool bUsingSedanBody = false;

	/** True when wearing vehicle13_Car (enables vehicle13_Car multi-stage windshield & lightbar fracture slots) */
	bool bUsingPoliceCruiserMesh = false;

	/** True once the player or CLI explicitly selected a built-in preset, overriding VehicleProfileAsset */
	bool bPresetOverrideActive = false;

	/** Set to false on AI traffic/arena cars so -WSPC2Vehicle=<Id> only picks the player's car */
	bool bAllowCliVehicleOverride = true;

	/** Active wheel authoring convention for Tick wheel transforms */
	EWSPC2WheelLayoutMode ActiveWheelLayoutMode = EWSPC2WheelLayoutMode::BakedCarSpace;

	/** Whether each front brake mesh is baked in car space (true) or centered at origin (false) */
	bool bFrontBrakeBakedCarSpace[2] = { true, true };

	/** Measured or profile-supplied car-space wheel hub positions and tyre radii */
	FVector WheelMeshOrigins[4] = { FVector::ZeroVector, FVector::ZeroVector, FVector::ZeroVector, FVector::ZeroVector };
	float WheelRadii[4] = { 35.27f, 35.27f, 35.27f, 35.27f };

	/** Active display name and handling class scales */
	FString ActiveVehicleDisplayName = TEXT("Patrol Cruiser");
	FWSPC2VehicleProfileSpec ActiveProfileSpec;
	float ActiveMassScale = 1.0f;
	float ActiveMaxTorqueScale = 1.0f;
	float ActiveChassisHeightCm = 144.0f;
	float ActiveMaxSteerAngle = 36.0f;

	/** Wheel spin as drawn (see Tick) */
	float DrawnWheelAngle[4] = { 0.0f, 0.0f, 0.0f, 0.0f };

	UFUNCTION()
	void OnRep_ActiveVehiclePresetId();

public:

	AWSPC2SportsCar();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	virtual void OnConstruction(const FTransform& Transform) override;

	/** Applies the profile and tuning before the physics vehicle is built, so Blueprint defaults cannot override it */
	virtual void PreRegisterAllComponents() override;

	/** Applies the per-wheel tuning and damage rig once the wheels exist */
	virtual void BeginPlay() override;

	/** Moves the visible wheels with the simulated ones */
	virtual void Tick(float Delta) override;

	virtual FString GetActiveVehicleDisplayName() const override { return ActiveVehicleDisplayName; }
	virtual FName GetActivePresetId() const override { return ActiveVehiclePresetId; }
	virtual FString GetActiveRoleGroup() const override { return UWSPC2VehicleProfile::GetNormalizedRoleGroup(ActiveProfileSpec); }
	virtual FString GetActiveAudioProfile() const override { return ActiveProfileSpec.AudioProfile; }
	virtual float GetActiveIdleRPM() const override { return ActiveProfileSpec.bUseRealWorldSpecs ? ActiveProfileSpec.IdleRPM : 720.0f; }
	virtual float GetActiveMaxRPM() const override { return ActiveProfileSpec.bUseRealWorldSpecs ? ActiveProfileSpec.MaxRPM : 5750.0f; }
	virtual EWSPC2Drivetrain GetActiveDrivetrain() const override { return ActiveProfileSpec.bUseRealWorldSpecs ? ActiveProfileSpec.Drivetrain : EWSPC2Drivetrain::RWD; }
	virtual float GetActiveBaseRearFriction() const override;

	const FWSPC2VehicleProfileSpec& GetActiveProfileSpec() const { return ActiveProfileSpec; }
	void SetAllowCliVehicleOverride(bool bAllow) { bAllowCliVehicleOverride = bAllow; }

	UFUNCTION(BlueprintPure, Category = "Vehicle")
	float GetDrawnSteeringWheelDeg() const { return DrawnSteering * SteeringWheelMaxDeg; }

	UFUNCTION(BlueprintPure, Category = "Vehicle")
	bool HasSteeringWheelMesh() const { return SteeringWheel && SteeringWheel->IsVisible(); }

	UFUNCTION(BlueprintPure, Category = "Vehicle")
	FName GetActiveVehiclePresetId() const { return ActiveVehiclePresetId; }

	/** Server-authoritative switch to a built-in hero preset (Patrol, Undercover, Interceptor, SUV, Pickup, SWATVan, CrownVic). */
	UFUNCTION(BlueprintCallable, Category = "Vehicle")
	bool SetVehiclePreset(FName NewPresetId);

	/** Server-authoritative cycle to the next available built-in hero preset. */
	UFUNCTION(BlueprintCallable, Category = "Vehicle")
	FName CycleVehiclePreset();

	/** Server-authoritative cycle forward (+1) or backward (-1) across all loadable presets. */
	UFUNCTION(BlueprintCallable, Category = "Vehicle")
	FName CycleVehiclePresetDirection(int32 Direction);

	/** Server-authoritative jump to the first loadable vehicle of the next category (Builtin/Fleet_Playable/Fleet_Bonus/Military/Mission/Traffic). */
	UFUNCTION(BlueprintCallable, Category = "Vehicle")
	FName CycleVehicleCategory();

	/** Crew slots: who sits where */
	static constexpr int32 CrewDriver = 0;
	static constexpr int32 CrewGunner = 1;

	/** Adds the drawn parts of one officer (CrewDriver or CrewGunner) to a view's hidden list, so a camera placed
	 *  inside that officer's head does not look out through his own face */
	void AddCrewToHiddenList(int32 Slot, TSet<FPrimitiveComponentId>& HiddenComponents) const;

	virtual bool GetGunnerMuzzle(FVector& OutLocation, FVector& OutDirection) const override;

	UWSPC2CrewComponent* GetCrew() const { return Crew; }

protected:

	/** Copies chassis, engine, gearbox and steering values from the tuning settings + active profile class scales */
	void ApplyTuning();

	/** Copies tyre, brake and suspension values from the tuning settings */
	void ApplyWheelTuning();

	/** Resolves and applies the active hero vehicle profile (with optional runtime Chaos physics rebuild) */
	void ApplyVehicleProfile(bool bRuntimeSwitch);

	/** Attempts to load and mount a single FWSPC2VehicleProfileSpec; returns true on success */
	bool TryMountProfileSpec(const FWSPC2VehicleProfileSpec& Spec);

	/** Seats the profile's officers and mounts its steering wheel (optional assets: whatever is missing is not drawn) */
	void MountCrew(const FWSPC2VehicleProfileSpec& Spec);

	/** Turns the steering wheel and tells the officers what to do this frame */
	void UpdateCrewAndWheel(float Delta);

	/** Applies center-of-mass override and updates Chaos rigid body mass properties */
	void ApplyCenterOfMassOverride();

	/** Binds the damage component to the currently mounted body, glass and wheels */
	void ConfigureDamageRig();

	/** Hides inherited template sports car StaticMeshComponents when a hero body is active */
	void HideTemplateBodyParts();

	/** Stops the template sports car's own physics shapes from touching the world; the sedan boxes remain */
	void DisableTemplateBodyCollision();

	/** Unwelds, resizes/rebuilds physics state, and re-welds BodyCollision/CabinCollision onto Root. */
	void ReweldProfileCollision();

	/** Where wheel number Index sits at rest, relative to the car */
	FVector GetSedanWheelPosition(int32 Index) const;

	/** Writes the simulated wheel positions to the log shortly after spawning, as a check */
	void LogWheelLayout();
};
