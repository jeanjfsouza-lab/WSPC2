#pragma once

#include "CoreMinimal.h"
#include "ChaosVehicleWheel.h"
#include "WSPC2PatrolWheels.generated.h"

/** Front wheel of the patrol car: steers, brakes, is not driven. */
UCLASS()
class UWSPC2PatrolWheelFront : public UChaosVehicleWheel
{
	GENERATED_BODY()

public:
	UWSPC2PatrolWheelFront();
};

/** Rear wheel of the patrol car: driven, carries the handbrake. */
UCLASS()
class UWSPC2PatrolWheelRear : public UChaosVehicleWheel
{
	GENERATED_BODY()

public:
	UWSPC2PatrolWheelRear();
};
