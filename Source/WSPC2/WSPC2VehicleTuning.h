#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "WSPC2VehicleTuning.generated.h"

/**
 *  Handling values for the patrol car, kept in Config/DefaultGame.ini
 *  (also editable in Project Settings > Game > WSPC2 Patrol Car Tuning).
 *  They are applied when a car spawns, so a change takes effect on the next Play
 *  without recompiling.
 *
 *  Values model a rear-wheel-drive V8 police sedan: ABS as the real car has, no traction control.
 */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "WSPC2 Patrol Car Tuning"))
class UWSPC2VehicleTuning : public UDeveloperSettings
{
	GENERATED_BODY()

public:

	virtual FName GetCategoryName() const override { return FName("Game"); }

	// ---- Chassis ----

	UPROPERTY(Config, EditAnywhere, Category = "Chassis", meta = (Units = "kg"))
	float MassKg = 1850.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Chassis")
	float DragCoefficient = 0.34f;

	UPROPERTY(Config, EditAnywhere, Category = "Chassis")
	float DownforceCoefficient = 0.0f;

	/** Angular damping while airborne. 0 is physically honest; the template used 3. */
	UPROPERTY(Config, EditAnywhere, Category = "Chassis")
	float MidAirAngularDamping = 0.0f;

	/** If true, a car left on its roof is put back on its wheels automatically. */
	UPROPERTY(Config, EditAnywhere, Category = "Chassis")
	bool bAutoFlipReset = false;

	// ---- Engine ----

	UPROPERTY(Config, EditAnywhere, Category = "Engine", meta = (Units = "Nm"))
	float MaxTorqueNm = 390.0f;

	/** Torque multiplication of the automatic's torque converter with the car stopped. 1 = none. */
	UPROPERTY(Config, EditAnywhere, Category = "Engine")
	float ConverterStallRatio = 2.0f;

	/** Engine speed at which the converter's multiplication has faded to nothing */
	UPROPERTY(Config, EditAnywhere, Category = "Engine")
	float ConverterFadeRPM = 2800.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Engine")
	float MaxRPM = 5750.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Engine")
	float IdleRPM = 750.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Engine")
	float EngineBrakeEffect = 0.15f;

	UPROPERTY(Config, EditAnywhere, Category = "Engine")
	float EngineRevUpMOI = 5.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Engine")
	float EngineRevDownRate = 600.0f;

	// ---- Transmission (4-speed automatic, rear-wheel drive) ----

	UPROPERTY(Config, EditAnywhere, Category = "Transmission")
	TArray<float> ForwardGearRatios = { 2.84f, 1.55f, 1.0f, 0.70f };

	UPROPERTY(Config, EditAnywhere, Category = "Transmission")
	float ReverseGearRatio = 2.32f;

	UPROPERTY(Config, EditAnywhere, Category = "Transmission")
	float FinalDriveRatio = 3.27f;

	UPROPERTY(Config, EditAnywhere, Category = "Transmission")
	float ChangeUpRPM = 5200.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Transmission")
	float ChangeDownRPM = 1800.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Transmission", meta = (Units = "s"))
	float GearChangeTime = 0.45f;

	UPROPERTY(Config, EditAnywhere, Category = "Transmission")
	float TransmissionEfficiency = 0.88f;

	// ---- Driver aids ----

	UPROPERTY(Config, EditAnywhere, Category = "Driver Aids")
	bool bABS = true;

	UPROPERTY(Config, EditAnywhere, Category = "Driver Aids")
	bool bTractionControl = false;

	// ---- Tyres and brakes ----

	UPROPERTY(Config, EditAnywhere, Category = "Tyres")
	float FrontFriction = 2.3f;

	UPROPERTY(Config, EditAnywhere, Category = "Tyres")
	float RearFriction = 2.3f;

	UPROPERTY(Config, EditAnywhere, Category = "Tyres", meta = (Units = "deg"))
	float MaxSteerAngle = 36.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Brakes")
	float FrontBrakeTorque = 3200.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Brakes")
	float RearBrakeTorque = 1900.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Brakes")
	float HandbrakeTorque = 4500.0f;

	// ---- Suspension (soft, with body roll) ----

	UPROPERTY(Config, EditAnywhere, Category = "Suspension")
	float SpringRate = 200.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Suspension")
	float SpringPreload = 50.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Suspension")
	float DampingRatio = 0.45f;

	UPROPERTY(Config, EditAnywhere, Category = "Suspension", meta = (Units = "cm"))
	float MaxRaise = 9.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Suspension", meta = (Units = "cm"))
	float MaxDrop = 11.0f;

	// ---- Input smoothing (matters for keyboard, which is all-or-nothing) ----

	UPROPERTY(Config, EditAnywhere, Category = "Input")
	float SteeringRiseRate = 3.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Input")
	float SteeringFallRate = 4.5f;

	UPROPERTY(Config, EditAnywhere, Category = "Input")
	float ThrottleRiseRate = 4.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Input")
	float BrakeRiseRate = 5.0f;

	// ---- Seats ----

	/** Driver and gunner may only trade seats below this speed. */
	UPROPERTY(Config, EditAnywhere, Category = "Seats", meta = (Units = "km/h"))
	float SeatSwapMaxSpeedKmh = 5.0f;

	// ---- Gunner aim disturbance ----

	/** Degrees of aim displacement per g of car acceleration. */
	UPROPERTY(Config, EditAnywhere, Category = "Gunner")
	float AimSwayDegPerG = 4.0f;

	/** Spring stiffness pulling the aim back; lower means longer wobble. */
	UPROPERTY(Config, EditAnywhere, Category = "Gunner")
	float AimSwayStiffness = 60.0f;

	/** Damping of the aim wobble; lower means more overshoot. */
	UPROPERTY(Config, EditAnywhere, Category = "Gunner")
	float AimSwayDamping = 6.0f;
};
