// Copyright Epic Games, Inc. All Rights Reserved.


#include "WSPC2SportsCar.h"
#include "WSPC2PatrolWheels.h"
#include "WSPC2VehicleTuning.h"
#include "ChaosWheeledVehicleMovementComponent.h"

AWSPC2SportsCar::AWSPC2SportsCar()
{
	// Set up the chassis
	GetChaosVehicleMovement()->ChassisHeight = 144.0f;

	// Set up the wheels. The bone names belong to the placeholder mesh.
	GetChaosVehicleMovement()->bLegacyWheelFrictionPosition = true;
	GetChaosVehicleMovement()->WheelSetups.SetNum(4);

	GetChaosVehicleMovement()->WheelSetups[0].BoneName = FName("Phys_Wheel_FL");
	GetChaosVehicleMovement()->WheelSetups[1].BoneName = FName("Phys_Wheel_FR");
	GetChaosVehicleMovement()->WheelSetups[2].BoneName = FName("Phys_Wheel_BL");
	GetChaosVehicleMovement()->WheelSetups[3].BoneName = FName("Phys_Wheel_BR");

	ApplyTuning();
}

void AWSPC2SportsCar::PreRegisterAllComponents()
{
	Super::PreRegisterAllComponents();

	// runs again per instance so the values win over whatever the Blueprint saved
	ApplyTuning();
}

void AWSPC2SportsCar::BeginPlay()
{
	Super::BeginPlay();

	ApplyWheelTuning();
}

void AWSPC2SportsCar::ApplyTuning()
{
	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
	UChaosWheeledVehicleMovementComponent* Movement = GetChaosVehicleMovement();

	if (!Tuning || !Movement)
	{
		return;
	}

	// chassis
	Movement->Mass = Tuning->MassKg;
	Movement->DragCoefficient = Tuning->DragCoefficient;
	Movement->DownforceCoefficient = Tuning->DownforceCoefficient;

	// wheels: steer at the front, drive and handbrake at the rear
	if (Movement->WheelSetups.Num() == 4)
	{
		Movement->WheelSetups[0].WheelClass = UWSPC2PatrolWheelFront::StaticClass();
		Movement->WheelSetups[1].WheelClass = UWSPC2PatrolWheelFront::StaticClass();
		Movement->WheelSetups[2].WheelClass = UWSPC2PatrolWheelRear::StaticClass();
		Movement->WheelSetups[3].WheelClass = UWSPC2PatrolWheelRear::StaticClass();
	}

	Movement->DifferentialSetup.DifferentialType = EVehicleDifferential::RearWheelDrive;

	// engine: a lazy V8, strong in the midrange and fading towards the redline
	Movement->EngineSetup.MaxTorque = Tuning->MaxTorqueNm;
	Movement->EngineSetup.MaxRPM = Tuning->MaxRPM;
	Movement->EngineSetup.EngineIdleRPM = Tuning->IdleRPM;
	Movement->EngineSetup.EngineBrakeEffect = Tuning->EngineBrakeEffect;
	Movement->EngineSetup.EngineRevUpMOI = Tuning->EngineRevUpMOI;
	Movement->EngineSetup.EngineRevDownRate = Tuning->EngineRevDownRate;

	// drop any curve asset the Blueprint points at, so we never edit a shared asset
	Movement->EngineSetup.TorqueCurve.ExternalCurve = nullptr;

	if (FRichCurve* TorqueCurve = Movement->EngineSetup.TorqueCurve.GetRichCurve())
	{
		const float RpmScale = Tuning->MaxRPM / 5750.0f;

		TorqueCurve->Reset();
		TorqueCurve->AddKey(0.0f, 0.55f);
		TorqueCurve->AddKey(750.0f * RpmScale, 0.62f);
		TorqueCurve->AddKey(1500.0f * RpmScale, 0.80f);
		TorqueCurve->AddKey(2500.0f * RpmScale, 0.93f);
		TorqueCurve->AddKey(4000.0f * RpmScale, 1.0f);
		TorqueCurve->AddKey(5000.0f * RpmScale, 0.90f);
		TorqueCurve->AddKey(5750.0f * RpmScale, 0.72f);
	}

	// transmission
	Movement->TransmissionSetup.bUseAutomaticGears = true;
	Movement->TransmissionSetup.bUseAutoReverse = true;
	Movement->TransmissionSetup.FinalRatio = Tuning->FinalDriveRatio;
	Movement->TransmissionSetup.ChangeUpRPM = Tuning->ChangeUpRPM;
	Movement->TransmissionSetup.ChangeDownRPM = Tuning->ChangeDownRPM;
	Movement->TransmissionSetup.GearChangeTime = Tuning->GearChangeTime;
	Movement->TransmissionSetup.TransmissionEfficiency = Tuning->TransmissionEfficiency;
	Movement->TransmissionSetup.ForwardGearRatios = Tuning->ForwardGearRatios;

	Movement->TransmissionSetup.ReverseGearRatios.SetNum(1);
	Movement->TransmissionSetup.ReverseGearRatios[0] = Tuning->ReverseGearRatio;

	// steering: full lock at parking speed, less as speed rises so a keyboard tap does not spin the car
	Movement->SteeringSetup.SteeringType = ESteeringType::Ackermann;
	Movement->SteeringSetup.AngleRatio = 0.7f;
	Movement->SteeringSetup.SteeringCurve.ExternalCurve = nullptr;

	if (FRichCurve* SteeringCurve = Movement->SteeringSetup.SteeringCurve.GetRichCurve())
	{
		SteeringCurve->Reset();
		SteeringCurve->AddKey(0.0f, 1.0f);
		SteeringCurve->AddKey(40.0f, 0.75f);
		SteeringCurve->AddKey(100.0f, 0.45f);
		SteeringCurve->AddKey(180.0f, 0.30f);
	}

	// input smoothing
	Movement->SteeringInputRate.RiseRate = Tuning->SteeringRiseRate;
	Movement->SteeringInputRate.FallRate = Tuning->SteeringFallRate;
	Movement->ThrottleInputRate.RiseRate = Tuning->ThrottleRiseRate;
	Movement->BrakeInputRate.RiseRate = Tuning->BrakeRiseRate;
}

void AWSPC2SportsCar::ApplyWheelTuning()
{
	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
	UChaosWheeledVehicleMovementComponent* Movement = GetChaosVehicleMovement();

	if (!Tuning || !Movement)
	{
		return;
	}

	for (int32 WheelIndex = 0; WheelIndex < Movement->WheelSetups.Num(); ++WheelIndex)
	{
		const bool bFront = WheelIndex < 2;

		Movement->SetWheelFrictionMultiplier(WheelIndex, bFront ? Tuning->FrontFriction : Tuning->RearFriction);
		Movement->SetWheelMaxBrakeTorque(WheelIndex, bFront ? Tuning->FrontBrakeTorque : Tuning->RearBrakeTorque);
		Movement->SetWheelHandbrakeTorque(WheelIndex, bFront ? 0.0f : Tuning->HandbrakeTorque);
		Movement->SetWheelMaxSteerAngle(WheelIndex, bFront ? Tuning->MaxSteerAngle : 0.0f);
		Movement->SetABSEnabled(WheelIndex, Tuning->bABS);
		Movement->SetTractionControlEnabled(WheelIndex, Tuning->bTractionControl);
		Movement->SetSuspensionParams(Tuning->SpringRate, Tuning->DampingRatio, Tuning->SpringPreload, Tuning->MaxRaise, Tuning->MaxDrop, WheelIndex);
	}
}
