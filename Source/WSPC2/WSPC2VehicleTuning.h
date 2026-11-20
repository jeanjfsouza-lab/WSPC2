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
	float DownforceCoefficient = 0.14f;

	/** Overrides the physics-asset center of mass in actor local coordinates so sedan body colliders do not pull weight onto the rear axle. */
	UPROPERTY(Config, EditAnywhere, Category = "Chassis")
	bool bOverrideCenterOfMass = true;

	/** Desired actor-local center of mass (cm): forward of wheelbase center (+X) and low (Z) for high-speed yaw stability. */
	UPROPERTY(Config, EditAnywhere, Category = "Chassis", meta = (Units = "cm", EditCondition = "bOverrideCenterOfMass"))
	FVector CenterOfMassOffset = FVector(4.0f, 0.0f, 54.0f);

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
	float FrontFriction = 2.35f;

	UPROPERTY(Config, EditAnywhere, Category = "Tyres")
	float RearFriction = 2.42f;

	UPROPERTY(Config, EditAnywhere, Category = "Tyres", meta = (Units = "deg"))
	float MaxSteerAngle = 36.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Brakes")
	float FrontBrakeTorque = 3200.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Brakes")
	float RearBrakeTorque = 1900.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Brakes")
	float HandbrakeTorque = 6800.0f;

	/** Extra deceleration on top of the tyres, in g at full brake (moving forward, on the ground). The tyres alone stop
	 *  the car at ~0.83 g whatever the brake torque; this brings it to a police car's ~1 g without adding cornering grip */
	UPROPERTY(Config, EditAnywhere, Category = "Brakes")
	float BrakeAssistG = 0.0f;

	/** Rear grip kept while the handbrake is pulled (1 = all of it); lower swings the tail out more readily */
	UPROPERTY(Config, EditAnywhere, Category = "Brakes")
	float HandbrakeRearGrip = 1.0f;

	/** Rear grip taken away at full throttle (0.15 = 15 %), so the tail steps out on power at low and medium speed */
	UPROPERTY(Config, EditAnywhere, Category = "Tyres")
	float RearThrottleGripLoss = 0.0f;

	/** The throttle grip loss is whole up to the first speed and gone at the second (stable at high speed) */
	UPROPERTY(Config, EditAnywhere, Category = "Tyres", meta = (Units = "km/h"))
	float RearThrottleGripLossFullBelowKmh = 50.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Tyres", meta = (Units = "km/h"))
	float RearThrottleGripLossGoneAboveKmh = 110.0f;

	// ---- Suspension (soft, with body roll) ----

	UPROPERTY(Config, EditAnywhere, Category = "Suspension")
	float SpringRate = 225.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Suspension")
	float SpringPreload = 50.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Suspension")
	float DampingRatio = 0.55f;

	/** Wheel travel up and down from rest. A 15 cm kerb needs most of the upward travel. */
	UPROPERTY(Config, EditAnywhere, Category = "Suspension", meta = (Units = "cm"))
	float MaxRaise = 13.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Suspension", meta = (Units = "cm"))
	float MaxDrop = 13.0f;

	/** Front anti-roll bar transfer ratio; firmer front bar builds progressive high-speed understeer margin. */
	UPROPERTY(Config, EditAnywhere, Category = "Suspension")
	float FrontRollbarScaling = 0.30f;

	/** Rear anti-roll bar transfer ratio; softer rear bar keeps tail planted through high-speed bumps and transitions. */
	UPROPERTY(Config, EditAnywhere, Category = "Suspension")
	float RearRollbarScaling = 0.20f;

	// ---- Input smoothing (matters for keyboard, which is all-or-nothing) ----

	UPROPERTY(Config, EditAnywhere, Category = "Input")
	float SteeringRiseRate = 3.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Input")
	float SteeringFallRate = 7.0f;

	/** Steering rack slew rate while countersteering or catching a pendulum swing. */
	UPROPERTY(Config, EditAnywhere, Category = "Input")
	float CountersteerSlewRate = 14.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Input")
	float ThrottleRiseRate = 4.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Input")
	float BrakeRiseRate = 5.0f;

	// ---- Steering against speed ----

	/** Fraction of full lock still available at 60, 100 and 180 km/h. Full lock is always available when parking. */
	UPROPERTY(Config, EditAnywhere, Category = "Tyres")
	float SteerAt60Kmh = 0.45f;

	UPROPERTY(Config, EditAnywhere, Category = "Tyres")
	float SteerAt100Kmh = 0.24f;

	UPROPERTY(Config, EditAnywhere, Category = "Tyres")
	float SteerAt180Kmh = 0.15f;

	/** Steering towards a slide may always reach the car's sideslip angle plus this many degrees */
	UPROPERTY(Config, EditAnywhere, Category = "Tyres", meta = (Units = "deg"))
	float CountersteerMarginDeg = 10.0f;

	/** Predictive yaw-rate horizon (seconds) added to current sideslip so countersteer opens early before spin rate peaks. */
	UPROPERTY(Config, EditAnywhere, Category = "Tyres", meta = (Units = "s"))
	float CountersteerYawRateLookahead = 0.25f;

	/** Minimum yaw rate (deg/s) that keeps opposing steering unlocked across zero sideslip to prevent tank-slappers. */
	UPROPERTY(Config, EditAnywhere, Category = "Tyres", meta = (Units = "deg/s"))
	float CountersteerHoldYawRateDeg = 12.0f;

	/** Front tyre linear cornering stiffness; kept lower than rear so the chassis naturally aligns at speed. */
	UPROPERTY(Config, EditAnywhere, Category = "Tyres")
	float FrontCorneringStiffness = 900.0f;

	/** Rear tyre linear cornering stiffness; higher rear bite damps high-speed oversteer before tyres saturate. */
	UPROPERTY(Config, EditAnywhere, Category = "Tyres")
	float RearCorneringStiffness = 1040.0f;

	/** Grip a sliding tyre keeps, relative to one still holding: below 1 the tail stays out once loose */
	UPROPERTY(Config, EditAnywhere, Category = "Tyres")
	float FrontSlideGrip = 0.93f;

	UPROPERTY(Config, EditAnywhere, Category = "Tyres")
	float RearSlideGrip = 0.96f;

	/** Multiplies the body's resistance to yawing. The physics shapes come from a smaller car (3330 kg m2 measured);
	 *  a 5.4 m sedan is nearer 4500. */
	UPROPERTY(Config, EditAnywhere, Category = "Chassis")
	float YawInertiaScale = 1.35f;

	// ---- Camera: these carry most of the feeling of speed ----

	/** Chase camera distance behind the car and height above it, at rest */
	UPROPERTY(Config, EditAnywhere, Category = "Camera", meta = (Units = "cm"))
	float ChaseDistance = 640.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Camera", meta = (Units = "cm"))
	float ChaseHeight = 165.0f;

	/** Extra distance the chase camera falls back at full speed */
	UPROPERTY(Config, EditAnywhere, Category = "Camera", meta = (Units = "cm"))
	float ChaseStretchAtSpeed = 140.0f;

	/** How quickly the chase camera catches up with the car; lower lets the car pull away under acceleration */
	UPROPERTY(Config, EditAnywhere, Category = "Camera")
	float ChaseLagSpeed = 7.0f;

	/** Field of view at rest and at full speed: the view widens as the car goes faster */
	UPROPERTY(Config, EditAnywhere, Category = "Camera", meta = (Units = "deg"))
	float ChaseFov = 84.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Camera", meta = (Units = "deg"))
	float ChaseFovAtSpeed = 106.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Camera", meta = (Units = "deg"))
	float OnCarFov = 92.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Camera", meta = (Units = "deg"))
	float OnCarFovAtSpeed = 110.0f;

	/** Speed at which the widest view and the full stretch are reached */
	UPROPERTY(Config, EditAnywhere, Category = "Camera", meta = (Units = "km/h"))
	float CameraFullSpeedKmh = 170.0f;

	/** The chase camera looks down at the car by this much, so the whole car stays in the frame up close */
	UPROPERTY(Config, EditAnywhere, Category = "Camera", meta = (Units = "deg"))
	float ChaseLookDownDeg = 0.0f;

	/** Chase camera orbit with the right stick (degrees per second at full tilt); the mouse moves it directly */
	UPROPERTY(Config, EditAnywhere, Category = "Camera")
	float ChaseOrbitStickRate = 200.0f;

	/** Seconds without look input before the chase camera swings back behind a moving car, and how fast it does */
	UPROPERTY(Config, EditAnywhere, Category = "Camera", meta = (Units = "s"))
	float ChaseRecenterDelay = 2.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Camera")
	float ChaseRecenterRate = 2.0f;

	/** How far the chase camera may go below (negative) and above its normal height, in degrees of orbit */
	UPROPERTY(Config, EditAnywhere, Category = "Camera", meta = (Units = "deg"))
	float ChaseOrbitPitchMin = -10.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Camera", meta = (Units = "deg"))
	float ChaseOrbitPitchMax = 40.0f;

	/** Strength of the motion blur (the engine's default is 0.5) and its longest streak, in percent of the screen width */
	UPROPERTY(Config, EditAnywhere, Category = "Camera")
	float MotionBlurAmount = 0.4f;

	UPROPERTY(Config, EditAnywhere, Category = "Camera")
	float MotionBlurMaxPercent = 3.0f;

	/**
	 * Largest wheel rotation drawn in one frame, in degrees. Motion blur and the temporal upscaler follow each pixel
	 * in a straight line from one frame to the next, so a spoke swinging through a wide arc smears. Above this
	 * limit the drawn wheel turns slower than the real one; keep it under half the spoke spacing (36 for 5 spokes).
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Camera", meta = (Units = "deg"))
	float WheelMaxDrawnStepDeg = 10.0f;

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

	// ---- Vehicle damage (physical, visual and mechanical progression) ----

	/** Master toggle for patrol car collision damage */
	UPROPERTY(Config, EditAnywhere, Category = "Damage")
	bool bEnableVehicleDamage = true;

	/** Reinforced cruiser structure multiplier (< 1 absorbs more punishment than civilian sheet metal) */
	UPROPERTY(Config, EditAnywhere, Category = "Damage")
	float PoliceArmorDamageScale = 0.58f;

	/** Minimum closing or scrape speed (km/h) that starts scuffed/light collision damage */
	UPROPERTY(Config, EditAnywhere, Category = "Damage", meta = (Units = "km/h"))
	float DamageMinSpeedKmh = 6.5f;

	/** Minimum impulse (kg cm/s) to register a scrape when closing speed is very low */
	UPROPERTY(Config, EditAnywhere, Category = "Damage")
	float DamageMinImpulse = 95000.0f;

	/** Impact speed corresponding to 1.0 single-hit normalized severity */
	UPROPERTY(Config, EditAnywhere, Category = "Damage", meta = (Units = "km/h"))
	float DamageSevereSpeedKmh = 105.0f;

	/** Impulse (kg cm/s) corresponding to 1.0 single-hit normalized severity */
	UPROPERTY(Config, EditAnywhere, Category = "Damage")
	float DamageSevereImpulse = 3800000.0f;

	/** Minimum interval (s) between continuous scraping damage ticks */
	UPROPERTY(Config, EditAnywhere, Category = "Damage", meta = (Units = "s"))
	float DamageScrapeCooldown = 0.085f;

	/** Overall structural health multiplier from accumulated zone damage */
	UPROPERTY(Config, EditAnywhere, Category = "Damage")
	float DamageZoneToHealthScale = 27.5f;

	/** Single-corner severity (0..1+) needed to blow a tyre immediately; lighter corner hits also chip wheel health */
	UPROPERTY(Config, EditAnywhere, Category = "Damage")
	float DamageWheelBlowoutSeverity = 0.60f;

	/** Radius loss when a tyre blows out and the car drops onto its rim */
	UPROPERTY(Config, EditAnywhere, Category = "Damage", meta = (Units = "cm"))
	float DamageFlatTyreRadiusDropCm = 6.0f;

	/** Multiplier applied to that axle's base tyre friction when punctured */
	UPROPERTY(Config, EditAnywhere, Category = "Damage")
	float DamageFlatTyreFrictionScale = 0.52f;

	/** Maximum fraction of peak engine torque retained at maximum heavy front/overall damage (before full wreck) */
	UPROPERTY(Config, EditAnywhere, Category = "Damage")
	float DamageHeavyMinTorqueScale = 0.34f;

	/** Maximum steering alignment pull added at full left/right asymmetry plus flat front tyre */
	UPROPERTY(Config, EditAnywhere, Category = "Damage")
	float DamageMaxSteeringPull = 0.24f;
};
