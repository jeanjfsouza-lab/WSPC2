// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "WSPC2Pawn.h"
#include "WSPC2SportsCar.generated.h"

class UStaticMeshComponent;
class UStaticMesh;
class UBoxComponent;

/**
 *  Patrol car. Handling comes from UWSPC2VehicleTuning: a heavy rear-wheel-drive
 *  sedan with no driver aids.
 *
 *  If the sedan body model is present in /Game/CrownVic (it is a local, untracked
 *  placeholder), the car wears it: body, four wheels driven from the wheel simulation,
 *  and collision boxes sized to it. Without the model the car falls back to the
 *  template's sports car body.
 */
UCLASS(abstract)
class AWSPC2SportsCar : public AWSPC2Pawn
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, Category = "Components")
	UStaticMeshComponent* SedanBody;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TArray<TObjectPtr<UStaticMeshComponent>> SedanWheels;

	/** Collision for the lower body, bumper to bumper */
	UPROPERTY(VisibleAnywhere, Category = "Components")
	UBoxComponent* BodyCollision;

	/** Collision for the cabin and roof */
	UPROPERTY(VisibleAnywhere, Category = "Components")
	UBoxComponent* CabinCollision;

	/** True once the sedan model was found and applied */
	bool bUsingSedanBody = false;

public:

	AWSPC2SportsCar();

	/** Applies the tuning before the physics vehicle is built, so Blueprint defaults cannot override it */
	virtual void PreRegisterAllComponents() override;

	/** Applies the per-wheel tuning once the wheels exist */
	virtual void BeginPlay() override;

	/** Moves the visible wheels with the simulated ones */
	virtual void Tick(float Delta) override;

protected:

	/** Copies chassis, engine, gearbox and steering values from the tuning settings */
	void ApplyTuning();

	/** Copies tyre, brake and suspension values from the tuning settings */
	void ApplyWheelTuning();

	/** Loads the sedan model, if present, and lays out wheels and collision for it */
	void ApplySedanBody();

	/** Where wheel number Index sits at rest, relative to the car */
	FVector GetSedanWheelPosition(int32 Index) const;

	/** Writes the simulated wheel positions to the log shortly after spawning, as a check */
	void LogWheelLayout();
};
