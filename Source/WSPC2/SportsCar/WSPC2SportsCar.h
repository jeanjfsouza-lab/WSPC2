// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "WSPC2Pawn.h"
#include "WSPC2SportsCar.generated.h"

/**
 *  Patrol car. Still uses the template's sports car body as a placeholder,
 *  but the handling comes from UWSPC2VehicleTuning: a heavy rear-wheel-drive
 *  sedan with no driver aids.
 */
UCLASS(abstract)
class AWSPC2SportsCar : public AWSPC2Pawn
{
	GENERATED_BODY()

public:

	AWSPC2SportsCar();

	/** Applies the tuning before the physics vehicle is built, so Blueprint defaults cannot override it */
	virtual void PreRegisterAllComponents() override;

	/** Applies the per-wheel tuning once the wheels exist */
	virtual void BeginPlay() override;

protected:

	/** Copies chassis, engine, gearbox and steering values from the tuning settings */
	void ApplyTuning();

	/** Copies tyre, brake and suspension values from the tuning settings */
	void ApplyWheelTuning();
};
