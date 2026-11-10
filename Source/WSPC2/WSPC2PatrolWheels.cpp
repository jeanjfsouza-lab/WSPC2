#include "WSPC2PatrolWheels.h"

// Values that have no runtime setter live here. Friction, brake torque, steer angle,
// driver aids and spring settings are overwritten from UWSPC2VehicleTuning when the car spawns.

namespace
{
	void SetupCommon(UChaosVehicleWheel* Wheel)
	{
		// street tyres: grip falls away early and progressively instead of holding on
		Wheel->CorneringStiffness = 800.0f;
		Wheel->SlipThreshold = 20.0f;
		Wheel->SkidThreshold = 20.0f;

		// no electronics
		Wheel->bABSEnabled = false;
		Wheel->bTractionControlEnabled = false;

		// soft springs and a weak anti-roll bar, so the body leans and dives
		Wheel->SuspensionMaxRaise = 9.0f;
		Wheel->SuspensionMaxDrop = 11.0f;
		Wheel->SuspensionDampingRatio = 0.45f;
		Wheel->SpringRate = 200.0f;
		Wheel->SpringPreload = 50.0f;
		Wheel->RollbarScaling = 0.25f;
	}
}

UWSPC2PatrolWheelFront::UWSPC2PatrolWheelFront()
{
	SetupCommon(this);

	AxleType = EAxleType::Front;

	// radius and width match the placeholder mesh
	WheelRadius = 39.0f;
	WheelWidth = 35.0f;

	FrictionForceMultiplier = 2.3f;

	bAffectedBySteering = true;
	MaxSteerAngle = 36.0f;

	bAffectedByEngine = false;
	bAffectedByHandbrake = false;

	MaxBrakeTorque = 3200.0f;
	MaxHandBrakeTorque = 0.0f;
}

UWSPC2PatrolWheelRear::UWSPC2PatrolWheelRear()
{
	SetupCommon(this);

	AxleType = EAxleType::Rear;

	WheelRadius = 40.0f;
	WheelWidth = 40.0f;

	FrictionForceMultiplier = 2.3f;

	bAffectedBySteering = false;
	MaxSteerAngle = 0.0f;

	bAffectedByEngine = true;
	bAffectedByHandbrake = true;

	MaxBrakeTorque = 1900.0f;
	MaxHandBrakeTorque = 4500.0f;
}
