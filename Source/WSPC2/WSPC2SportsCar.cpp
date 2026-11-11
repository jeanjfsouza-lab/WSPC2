// Copyright Epic Games, Inc. All Rights Reserved.


#include "WSPC2SportsCar.h"
#include "WSPC2PatrolWheels.h"
#include "WSPC2VehicleTuning.h"
#include "WSPC2.h"
#include "ChaosWheeledVehicleMovementComponent.h"
#include "ChaosVehicleWheel.h"
#include "Components/BoxComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkinnedAsset.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/SpringArmComponent.h"
#include "TimerManager.h"

namespace WSPC2Sedan
{
	// Measured from the model, in cm, in car space (X forward, Y right, Z up, origin on the ground).
	const float FrontAxleX = 153.0f;
	const float RearAxleX = -140.6f;
	const float FrontHalfTrack = 80.4f;
	const float RearHalfTrack = 83.3f;
	const float AxleHeight = 35.2f;
	const float WheelRadius = 35.1f;

	// The imported meshes face +Y; a quarter turn points them down the car's X axis.
	const FRotator BodyRotation(0.0f, -90.0f, 0.0f);

	const TCHAR* BodyMeshPath = TEXT("/Game/CrownVic/CrownVic_Body/StaticMeshes/CrownVic_Body.CrownVic_Body");
	const TCHAR* WheelMeshPath = TEXT("/Game/CrownVic/CrownVic_Wheel/StaticMeshes/CrownVic_Wheel.CrownVic_Wheel");

	const FName WheelBones[4] = { FName("Phys_Wheel_FL"), FName("Phys_Wheel_FR"), FName("Phys_Wheel_BL"), FName("Phys_Wheel_BR") };
}

AWSPC2SportsCar::AWSPC2SportsCar()
{
	// Set up the chassis
	GetChaosVehicleMovement()->ChassisHeight = 144.0f;

	// Set up the wheels. The bone names belong to the physics skeleton.
	GetChaosVehicleMovement()->bLegacyWheelFrictionPosition = true;
	GetChaosVehicleMovement()->WheelSetups.SetNum(4);

	for (int32 Index = 0; Index < 4; ++Index)
	{
		GetChaosVehicleMovement()->WheelSetups[Index].BoneName = WSPC2Sedan::WheelBones[Index];
	}

	// sedan body and wheels: empty until the model is found
	SedanBody = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Sedan Body"));
	SedanBody->SetupAttachment(GetMesh());
	SedanBody->SetRelativeRotation(WSPC2Sedan::BodyRotation);
	SedanBody->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	static const TCHAR* WheelNames[4] = { TEXT("Sedan Wheel FL"), TEXT("Sedan Wheel FR"), TEXT("Sedan Wheel RL"), TEXT("Sedan Wheel RR") };

	for (int32 Index = 0; Index < 4; ++Index)
	{
		UStaticMeshComponent* Wheel = CreateDefaultSubobject<UStaticMeshComponent>(WheelNames[Index]);
		Wheel->SetupAttachment(GetMesh());
		Wheel->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		SedanWheels.Add(Wheel);
	}

	// collision boxes sized to the sedan; switched on only when the model is in use
	BodyCollision = CreateDefaultSubobject<UBoxComponent>(TEXT("Body Collision"));
	BodyCollision->SetupAttachment(GetMesh());
	BodyCollision->SetRelativeLocation(FVector(-9.0f, 0.0f, 62.0f));
	BodyCollision->SetBoxExtent(FVector(268.0f, 95.0f, 33.0f));
	BodyCollision->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	CabinCollision = CreateDefaultSubobject<UBoxComponent>(TEXT("Cabin Collision"));
	CabinCollision->SetupAttachment(GetMesh());
	CabinCollision->SetRelativeLocation(FVector(-35.0f, 0.0f, 122.0f));
	CabinCollision->SetBoxExtent(FVector(115.0f, 78.0f, 27.0f));
	CabinCollision->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	ApplyTuning();
}

void AWSPC2SportsCar::PreRegisterAllComponents()
{
	Super::PreRegisterAllComponents();

	// runs again per instance so the values win over whatever the Blueprint saved
	ApplyTuning();
	ApplySedanBody();
}

void AWSPC2SportsCar::BeginPlay()
{
	Super::BeginPlay();

	ApplyWheelTuning();

	if (bUsingSedanBody)
	{
		// hide the template's sports car parts; ours stay visible
		TInlineComponentArray<UStaticMeshComponent*> StaticMeshes(this);

		for (UStaticMeshComponent* Component : StaticMeshes)
		{
			if (Component != SedanBody && !SedanWheels.Contains(Component))
			{
				Component->SetVisibility(false);
				Component->SetHiddenInGame(true);
			}
		}

		FTimerHandle LogTimer;
		GetWorld()->GetTimerManager().SetTimer(LogTimer, this, &AWSPC2SportsCar::LogWheelLayout, 3.0f, false);
	}
}

FVector AWSPC2SportsCar::GetSedanWheelPosition(int32 Index) const
{
	const bool bFront = Index < 2;
	const bool bRight = (Index % 2) == 1;

	return FVector(
		bFront ? WSPC2Sedan::FrontAxleX : WSPC2Sedan::RearAxleX,
		(bFront ? WSPC2Sedan::FrontHalfTrack : WSPC2Sedan::RearHalfTrack) * (bRight ? 1.0f : -1.0f),
		WSPC2Sedan::AxleHeight);
}

void AWSPC2SportsCar::ApplySedanBody()
{
	UStaticMesh* BodyMesh = Cast<UStaticMesh>(StaticLoadObject(UStaticMesh::StaticClass(), nullptr, WSPC2Sedan::BodyMeshPath, nullptr, LOAD_NoWarn | LOAD_Quiet));
	UStaticMesh* WheelMesh = Cast<UStaticMesh>(StaticLoadObject(UStaticMesh::StaticClass(), nullptr, WSPC2Sedan::WheelMeshPath, nullptr, LOAD_NoWarn | LOAD_Quiet));

	bUsingSedanBody = BodyMesh != nullptr && WheelMesh != nullptr;

	if (!bUsingSedanBody)
	{
		return;
	}

	SedanBody->SetStaticMesh(BodyMesh);

	for (UStaticMeshComponent* Wheel : SedanWheels)
	{
		Wheel->SetStaticMesh(WheelMesh);
	}

	// collision the size of the sedan, welded to the chassis
	BodyCollision->SetCollisionProfileName(FName("Vehicle"));
	CabinCollision->SetCollisionProfileName(FName("Vehicle"));

	// the physics skeleton has its wheels where the sports car had them: shift each one to the sedan's axle
	UChaosWheeledVehicleMovementComponent* Movement = GetChaosVehicleMovement();
	const USkinnedAsset* Skeleton = GetMesh() ? GetMesh()->GetSkinnedAsset() : nullptr;

	if (Movement && Skeleton && Movement->WheelSetups.Num() == 4)
	{
		for (int32 Index = 0; Index < 4; ++Index)
		{
			const FVector BonePosition = Skeleton->GetComposedRefPoseMatrix(Movement->WheelSetups[Index].BoneName).GetOrigin();
			Movement->WheelSetups[Index].AdditionalOffset = GetSedanWheelPosition(Index) - BonePosition;
		}
	}

	// crew positions for this body: gunner at the front passenger window, light bar on the roof,
	// first-person camera at the driver's head
	SetCrewLayout(FVector(0.0f, 78.0f, 118.0f), FVector(-40.0f, 0.0f, 158.0f), 40.0f);
	SetOnCarViews(
		{ FVector(-5.0f, -38.0f, 118.0f), FVector(105.0f, 0.0f, 112.0f), FVector(268.0f, 0.0f, 52.0f) },
		{ TEXT("Dashboard"), TEXT("Hood"), TEXT("Bumper") });

	// the sedan is longer and taller than the sports car: pull the chase camera back and up
	GetBackSpringArm()->TargetArmLength = 820.0f;
	GetBackSpringArm()->SocketOffset.Z = 210.0f;
}

void AWSPC2SportsCar::Tick(float Delta)
{
	Super::Tick(Delta);

	if (!bUsingSedanBody)
	{
		return;
	}

	const UChaosWheeledVehicleMovementComponent* Movement = GetChaosVehicleMovement();

	for (int32 Index = 0; Index < SedanWheels.Num(); ++Index)
	{
		FVector Position = GetSedanWheelPosition(Index);
		FRotator Motion = FRotator::ZeroRotator;

		if (Movement->Wheels.IsValidIndex(Index) && Movement->Wheels[Index])
		{
			const UChaosVehicleWheel* Wheel = Movement->Wheels[Index];

			// same formula the engine's wheel animation uses
			Position += -Wheel->GetSuspensionAxis() * Wheel->GetSuspensionOffset();
			Motion.Yaw = Wheel->GetSteerAngle();

			// A five-spoke wheel looks the same every 72 degrees. At road speed the real wheel turns more
			// than that per frame, so drawing the true angle makes it seem to crawl or run backwards.
			// Limit the drawn step per frame: above that speed the wheel just reads as "spinning fast".
			const float TrueAngle = Wheel->GetRotationAngle();
			const float Step = FMath::Clamp(TrueAngle - LastWheelAngle[Index], -MaxDrawnSpinStep, MaxDrawnSpinStep);

			LastWheelAngle[Index] = TrueAngle;
			DrawnWheelAngle[Index] = FMath::Fmod(DrawnWheelAngle[Index] + Step, 360.0f);

			Motion.Pitch = DrawnWheelAngle[Index];
		}

		// the wheel mesh is a left wheel: the right side gets it turned around
		const bool bRight = (Index % 2) == 1;
		const FQuat Facing = FRotator(0.0f, bRight ? 90.0f : -90.0f, 0.0f).Quaternion();

		SedanWheels[Index]->SetRelativeLocationAndRotation(Position, Motion.Quaternion() * Facing);
	}
}

void AWSPC2SportsCar::LogWheelLayout()
{
	const UChaosWheeledVehicleMovementComponent* Movement = GetChaosVehicleMovement();
	for (int32 Index = 0; Index < Movement->Wheels.Num(); ++Index)
	{
		if (const UChaosVehicleWheel* Wheel = Movement->Wheels[Index])
		{
			UE_LOG(LogWSPC2, Log, TEXT("Wheel %d: axle at (%s), radius %.1f, suspension offset %.1f"),
				Index, *GetSedanWheelPosition(Index).ToCompactString(), Wheel->GetWheelRadius(), Wheel->GetSuspensionOffset());
		}
	}

	UE_LOG(LogWSPC2, Log, TEXT("Car at height %.1f, roll %.1f, pitch %.1f, speed %.1f km/h"),
		GetActorLocation().Z, GetActorRotation().Roll, GetActorRotation().Pitch, GetSpeedKmh());
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

		// engine torque as a fraction of its peak
		static const float Rpm[] = { 0.0f, 750.0f, 1500.0f, 2500.0f, 4000.0f, 5000.0f, 5750.0f };
		static const float Fraction[] = { 0.55f, 0.62f, 0.80f, 0.93f, 1.0f, 0.90f, 0.72f };

		// The simulation has no torque converter, so an automatic would launch on idle torque alone.
		// A real converter multiplies torque when the car is nearly stopped and fades out as revs rise;
		// fold that into the curve.
		float Peak = 0.0f;

		TorqueCurve->Reset();

		for (int32 Key = 0; Key < UE_ARRAY_COUNT(Rpm); ++Key)
		{
			const float Fade = FMath::Clamp(1.0f - Rpm[Key] / Tuning->ConverterFadeRPM, 0.0f, 1.0f);
			const float Value = Fraction[Key] * (1.0f + (Tuning->ConverterStallRatio - 1.0f) * Fade);

			TorqueCurve->AddKey(Rpm[Key] * RpmScale, Value);
			Peak = FMath::Max(Peak, Value);
		}

		// the simulation rescales the curve so its highest point equals MaxTorque
		Movement->EngineSetup.MaxTorque = Tuning->MaxTorqueNm * Peak;
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

		if (bUsingSedanBody)
		{
			Movement->SetWheelRadius(WheelIndex, WSPC2Sedan::WheelRadius);
		}
	}
}
