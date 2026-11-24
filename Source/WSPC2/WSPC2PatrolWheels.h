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

/** Front wheel variant driven by the engine (used by FWD and AWD real-world vehicles). */
UCLASS()
class UWSPC2PatrolWheelFrontDriven : public UWSPC2PatrolWheelFront
{
	GENERATED_BODY()

public:
	UWSPC2PatrolWheelFrontDriven();
};

/** Rear wheel variant not driven by the engine (used by FWD real-world vehicles). */
UCLASS()
class UWSPC2PatrolWheelRearFree : public UWSPC2PatrolWheelRear
{
	GENERATED_BODY()

public:
	UWSPC2PatrolWheelRearFree();
};
