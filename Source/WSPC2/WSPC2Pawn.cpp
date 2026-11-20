// Copyright Epic Games, Inc. All Rights Reserved.

#include "WSPC2Pawn.h"
#include "WSPC2WheelFront.h"
#include "WSPC2WheelRear.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Camera/CameraComponent.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "InputActionValue.h"
#include "ChaosWheeledVehicleMovementComponent.h"
#include "ChaosVehicleWheel.h"
#include "WSPC2.h"
#include "WSPC2VehicleTuning.h"
#include "WSPC2VehicleDamageComponent.h"
#include "WSPC2VehicleAudioComponent.h"
#include "WSPC2Gunnery.h"
#include "Components/PointLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"
#include "Net/UnrealNetwork.h"
#include "Engine/Engine.h"
#include "TimerManager.h"

#define LOCTEXT_NAMESPACE "VehiclePawn"

AWSPC2Pawn::AWSPC2Pawn()
{
	// construct the front camera boom
	FrontSpringArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("Front Spring Arm"));
	FrontSpringArm->SetupAttachment(GetMesh());
	FrontSpringArm->TargetArmLength = 0.0f;
	FrontSpringArm->bDoCollisionTest = false;
	FrontSpringArm->bEnableCameraRotationLag = true;
	FrontSpringArm->CameraRotationLagSpeed = 15.0f;
	FrontSpringArm->SetRelativeLocation(FVector(30.0f, 0.0f, 120.0f));

	FrontCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("Front Camera"));
	FrontCamera->SetupAttachment(FrontSpringArm);
	FrontCamera->bAutoActivate = false;

	// construct the back camera boom
	BackSpringArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("Back Spring Arm"));
	BackSpringArm->SetupAttachment(GetMesh());
	BackSpringArm->TargetArmLength = 650.0f;
	BackSpringArm->SocketOffset.Z = 150.0f;
	BackSpringArm->bDoCollisionTest = false;
	BackSpringArm->bInheritPitch = false;
	BackSpringArm->bInheritRoll = false;
	BackSpringArm->bEnableCameraRotationLag = true;
	BackSpringArm->CameraRotationLagSpeed = 2.0f;

	// the camera trails the car a little: hard acceleration pulls the car away, braking brings it closer
	BackSpringArm->bEnableCameraLag = true;
	BackSpringArm->CameraLagSpeed = 7.0f;
	BackSpringArm->CameraLagMaxDistance = 160.0f;

	BackCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("Back Camera"));
	BackCamera->SetupAttachment(BackSpringArm);

	// Configure the car mesh
	GetMesh()->SetSimulatePhysics(true);
	GetMesh()->SetCollisionProfileName(FName("Vehicle"));
	GetMesh()->SetNotifyRigidBodyCollision(true);

	// get the Chaos Wheeled movement component
	ChaosVehicleMovement = CastChecked<UChaosWheeledVehicleMovementComponent>(GetVehicleMovement());

	VehicleDamage = CreateDefaultSubobject<UWSPC2VehicleDamageComponent>(TEXT("Vehicle Damage"));
	VehicleAudio = CreateDefaultSubobject<UWSPC2VehicleAudioComponent>(TEXT("Vehicle Audio"));
	Gunnery = CreateDefaultSubobject<UWSPC2GunneryComponent>(TEXT("Gunnery"));

	// gunner seat: passenger side (right), at window height
	GunnerSeat = CreateDefaultSubobject<USceneComponent>(TEXT("Gunner Seat"));
	GunnerSeat->SetupAttachment(GetMesh());
	GunnerSeat->SetRelativeLocation(FVector(-20.0f, 60.0f, 100.0f));

	// roof light bar
	SirenLightLeft = CreateDefaultSubobject<UPointLightComponent>(TEXT("Siren Light Left"));
	SirenLightLeft->SetupAttachment(GetMesh());
	SirenLightLeft->SetRelativeLocation(FVector(-20.0f, -35.0f, 150.0f));
	SirenLightLeft->SetLightColor(FLinearColor(1.0f, 0.03f, 0.02f));
	SirenLightLeft->SetIntensity(16000.0f);
	SirenLightLeft->SetAttenuationRadius(2200.0f);
	SirenLightLeft->SetCastShadows(false);
	SirenLightLeft->SetVisibility(false);

	SirenLightRight = CreateDefaultSubobject<UPointLightComponent>(TEXT("Siren Light Right"));
	SirenLightRight->SetupAttachment(GetMesh());
	SirenLightRight->SetRelativeLocation(FVector(-20.0f, 35.0f, 150.0f));
	SirenLightRight->SetLightColor(FLinearColor(0.02f, 0.12f, 1.0f));
	SirenLightRight->SetIntensity(16000.0f);
	SirenLightRight->SetAttenuationRadius(2200.0f);
	SirenLightRight->SetCastShadows(false);
	SirenLightRight->SetVisibility(false);

	// The point lights colour the road and the walls around the car, which only shows at night or in shade.
	// The lenses are what is seen flashing in daylight: two unlit blocks far brighter than a sunlit surface.
	static ConstructorHelpers::FObjectFinder<UStaticMesh> LensMesh(TEXT("/Engine/BasicShapes/Cube.Cube"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> LensMaterial(TEXT("/Engine/EngineMaterials/EmissiveMeshMaterial.EmissiveMeshMaterial"));

	SirenLensLeft = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Siren Lens Left"));
	SirenLensRight = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Siren Lens Right"));

	for (UStaticMeshComponent* Lens : { SirenLensLeft, SirenLensRight })
	{
		Lens->SetupAttachment(GetMesh());
		Lens->SetStaticMesh(LensMesh.Object);
		Lens->SetMaterial(0, LensMaterial.Object);
		Lens->SetRelativeScale3D(FVector(0.16f, 0.34f, 0.07f));
		Lens->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Lens->SetCastShadow(false);
		Lens->SetVisibility(false);
	}

	for (UPointLightComponent* Light : { SirenLightLeft, SirenLightRight })
	{
		// candelas, so the value means the same whatever the project's default light unit is
		Light->SetIntensityUnits(ELightUnits::Candelas);
		Light->SetIntensity(9000.0f);
		Light->SetAttenuationRadius(3500.0f);
		Light->SetSourceRadius(12.0f);
	}

	SirenLensLeft->SetRelativeLocation(SirenLightLeft->GetRelativeLocation());
	SirenLensRight->SetRelativeLocation(SirenLightRight->GetRelativeLocation());
}

void AWSPC2Pawn::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AWSPC2Pawn, bSirenOn);
}

void AWSPC2Pawn::SetCrewLayout(const FVector& GunnerSeatLocation, const FVector& LightBarCentre, float LightHalfSpacing)
{
	GunnerSeat->SetRelativeLocation(GunnerSeatLocation);
	// the lenses sit on the bar; the lights hover just above it so the roof does not swallow them
	const FVector Left = LightBarCentre + FVector(0.0f, -LightHalfSpacing, 0.0f);
	const FVector Right = LightBarCentre + FVector(0.0f, LightHalfSpacing, 0.0f);
	const FVector Lift(0.0f, 0.0f, 14.0f);

	SirenLensLeft->SetRelativeLocation(Left);
	SirenLensRight->SetRelativeLocation(Right);
	SirenLightLeft->SetRelativeLocation(Left + Lift);
	SirenLightRight->SetRelativeLocation(Right + Lift);
}

void AWSPC2Pawn::SetRoofLightbarEnabled(bool bEnabled)
{
	bHasRoofLightbar = bEnabled;
	UpdateSirenLights();
}

namespace
{
	void ApplyHandbrakeWithMechanicalLock(UChaosWheeledVehicleMovementComponent* Movement, bool bEngaged)
	{
		if (!Movement)
		{
			return;
		}

		const bool bWasEngaged = Movement->GetHandbrakeInput();
		Movement->SetHandbrakeInput(bEngaged);
		if (bWasEngaged == bEngaged)
		{
			return;
		}

		const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
		const bool bTargetRearABS = bEngaged ? false : (Tuning ? Tuning->bABS : true);

		// Bypass ABS on handbrake wheels so the parking brake actually locks the rear axle for drifts and J-turns.
		for (int32 WheelIndex = 0; WheelIndex < Movement->WheelSetups.Num(); ++WheelIndex)
		{
			const TSubclassOf<UChaosVehicleWheel> WheelClass = Movement->WheelSetups[WheelIndex].WheelClass;
			if (WheelClass && WheelClass->GetDefaultObject<UChaosVehicleWheel>()->bAffectedByHandbrake)
			{
				Movement->SetABSEnabled(WheelIndex, bTargetRearABS);
			}
		}
	}
}

void AWSPC2Pawn::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);

	ApplyHandbrakeWithMechanicalLock(ChaosVehicleMovement, false);
}

void AWSPC2Pawn::UnPossessed()
{
	Super::UnPossessed();

	// nobody at the wheel: no throttle, no steering, handbrake on
	ChaosVehicleMovement->SetThrottleInput(0.0f);
	ChaosVehicleMovement->SetBrakeInput(0.0f);
	ChaosVehicleMovement->SetSteeringInput(0.0f);
	ApplyHandbrakeWithMechanicalLock(ChaosVehicleMovement, true);
}

void AWSPC2Pawn::SetSiren(bool bOn)
{
	if (HasAuthority() && bSirenOn != bOn)
	{
		bSirenOn = bOn;

		// the server does not receive its own replication, so run the handler by hand
		OnRep_Siren();
	}
}

void AWSPC2Pawn::OnRep_Siren()
{
	SirenFlashTime = 0.0f;
	UpdateSirenLights();
	OnSirenChanged(bSirenOn);
}

void AWSPC2Pawn::UpdateSirenLights()
{
	// alternate the two sides four times a second
	const bool bLeftPhase = FMath::Fmod(SirenFlashTime, 0.5f) < 0.25f;
	const float SirenHealth = VehicleDamage ? VehicleDamage->GetSirenLightHealthFactor() : 1.0f;
	const bool bSirenFunctional = bSirenOn && SirenHealth > 0.0f;

	SirenLightLeft->SetVisibility(bSirenFunctional && bLeftPhase);
	SirenLightRight->SetVisibility(bSirenFunctional && !bLeftPhase);
	SirenLensLeft->SetVisibility(bHasRoofLightbar && bSirenFunctional && bLeftPhase);
	SirenLensRight->SetVisibility(bHasRoofLightbar && bSirenFunctional && !bLeftPhase);

	const float ScaledIntensity = 9000.0f * FMath::Clamp(SirenHealth, 0.0f, 1.0f);
	SirenLightLeft->SetIntensity(ScaledIntensity);
	SirenLightRight->SetIntensity(ScaledIntensity);
}

void AWSPC2Pawn::UpdateSpeedCamera(float Delta)
{
	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();

	const float Target = FMath::Clamp(GetSpeedKmh() / FMath::Max(Tuning->CameraFullSpeedKmh, 1.0f), 0.0f, 1.0f);
	CameraSpeedAlpha = FMath::FInterpTo(CameraSpeedAlpha, Target, Delta, 2.5f);

	// most of the widening happens early, where the eye needs the most help judging speed
	const float Alpha = FMath::Sqrt(CameraSpeedAlpha);

	BackCamera->SetFieldOfView(FMath::Lerp(Tuning->ChaseFov, Tuning->ChaseFovAtSpeed, Alpha));
	FrontCamera->SetFieldOfView(FMath::Lerp(Tuning->OnCarFov, Tuning->OnCarFovAtSpeed, Alpha));

	BackSpringArm->TargetArmLength = Tuning->ChaseDistance + Tuning->ChaseStretchAtSpeed * CameraSpeedAlpha;
	BackSpringArm->SocketOffset.Z = Tuning->ChaseHeight;
	BackSpringArm->CameraLagSpeed = Tuning->ChaseLagSpeed;

	for (UCameraComponent* Camera : { BackCamera, FrontCamera })
	{
		FPostProcessSettings& Settings = Camera->PostProcessSettings;
		Settings.bOverride_MotionBlurAmount = true;
		Settings.MotionBlurAmount = Tuning->MotionBlurAmount;
		Settings.bOverride_MotionBlurMax = true;
		Settings.MotionBlurMax = Tuning->MotionBlurMaxPercent;
	}
}

float AWSPC2Pawn::GetSpeedKmh() const
{
	// velocity is in cm/s
	return GetVelocity().Size() * 0.036f;
}

void AWSPC2Pawn::ServerResetVehicle_Implementation()
{
	DoResetVehicle();
}

void AWSPC2Pawn::SetupPlayerInputComponent(class UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);

	if (UEnhancedInputComponent* EnhancedInputComponent = Cast<UEnhancedInputComponent>(PlayerInputComponent))
	{
		// steering 
		EnhancedInputComponent->BindAction(SteeringAction, ETriggerEvent::Triggered, this, &AWSPC2Pawn::Steering);
		EnhancedInputComponent->BindAction(SteeringAction, ETriggerEvent::Completed, this, &AWSPC2Pawn::Steering);

		// throttle 
		EnhancedInputComponent->BindAction(ThrottleAction, ETriggerEvent::Triggered, this, &AWSPC2Pawn::Throttle);
		EnhancedInputComponent->BindAction(ThrottleAction, ETriggerEvent::Completed, this, &AWSPC2Pawn::Throttle);

		// break 
		EnhancedInputComponent->BindAction(BrakeAction, ETriggerEvent::Triggered, this, &AWSPC2Pawn::Brake);
		EnhancedInputComponent->BindAction(BrakeAction, ETriggerEvent::Started, this, &AWSPC2Pawn::StartBrake);
		EnhancedInputComponent->BindAction(BrakeAction, ETriggerEvent::Completed, this, &AWSPC2Pawn::StopBrake);

		// handbrake 
		EnhancedInputComponent->BindAction(HandbrakeAction, ETriggerEvent::Started, this, &AWSPC2Pawn::StartHandbrake);
		EnhancedInputComponent->BindAction(HandbrakeAction, ETriggerEvent::Completed, this, &AWSPC2Pawn::StopHandbrake);

		// look around 
		EnhancedInputComponent->BindAction(LookAroundAction, ETriggerEvent::Triggered, this, &AWSPC2Pawn::LookAround);

		// toggle camera 
		EnhancedInputComponent->BindAction(ToggleCameraAction, ETriggerEvent::Triggered, this, &AWSPC2Pawn::ToggleCamera);

		// reset the vehicle 
		EnhancedInputComponent->BindAction(ResetVehicleAction, ETriggerEvent::Triggered, this, &AWSPC2Pawn::ResetVehicle);
	}
	else
	{
		UE_LOG(LogWSPC2, Error, TEXT("'%s' Failed to find an Enhanced Input component! This template is built to use the Enhanced Input system. If you intend to use the legacy system, then you will need to update this C++ file."), *GetNameSafe(this));
	}
}

void AWSPC2Pawn::BeginPlay()
{
	Super::BeginPlay();

	// colour the lenses: red on the driver's side, blue on the passenger's, far above daylight brightness
	const float LensBrightness = 40000.0f;
	const FLinearColor LensColours[2] = { FLinearColor(1.0f, 0.02f, 0.01f), FLinearColor(0.02f, 0.10f, 1.0f) };
	UStaticMeshComponent* Lenses[2] = { SirenLensLeft, SirenLensRight };

	for (int32 Index = 0; Index < 2; ++Index)
	{
		if (UMaterialInstanceDynamic* Glow = Lenses[Index]->CreateDynamicMaterialInstance(0))
		{
			Glow->SetVectorParameterValue(TEXT("Color"), LensColours[Index] * LensBrightness);
		}
	}

	// set up the flipped check timer
	GetWorld()->GetTimerManager().SetTimer(FlipCheckTimer, this, &AWSPC2Pawn::FlippedCheck, FlipCheckTime, true);
}

void AWSPC2Pawn::EndPlay(EEndPlayReason::Type EndPlayReason)
{
	// clear the flipped check timer
	GetWorld()->GetTimerManager().ClearTimer(FlipCheckTimer);

	Super::EndPlay(EndPlayReason);
}

void AWSPC2Pawn::Tick(float Delta)
{
	Super::Tick(Delta);

	// angular damping while airborne comes from the tuning settings (0 = none)
	bool bMovingOnGround = ChaosVehicleMovement->IsMovingOnGround();
	GetMesh()->SetAngularDamping(bMovingOnGround ? 0.0f : GetDefault<UWSPC2VehicleTuning>()->MidAirAngularDamping);

	// flash the light bar
	if (bSirenOn)
	{
		SirenFlashTime += Delta;
		UpdateSirenLights();
	}

	UpdateSpeedCamera(Delta);

	// realign the camera yaw to face front
	float CameraYaw = BackSpringArm->GetRelativeRotation().Yaw;
	CameraYaw = FMath::FInterpTo(CameraYaw, 0.0f, Delta, 1.0f);

	BackSpringArm->SetRelativeRotation(FRotator(0.0f, CameraYaw, 0.0f));
}

void AWSPC2Pawn::Steering(const FInputActionValue& Value)
{
	// route the input
	DoSteering(Value.Get<float>());
}

void AWSPC2Pawn::Throttle(const FInputActionValue& Value)
{
	// route the input
	DoThrottle(Value.Get<float>());
}

void AWSPC2Pawn::Brake(const FInputActionValue& Value)
{
	// route the input
	DoBrake(Value.Get<float>());
}

void AWSPC2Pawn::StartBrake(const FInputActionValue& Value)
{
	// route the input
	DoBrakeStart();
}

void AWSPC2Pawn::StopBrake(const FInputActionValue& Value)
{
	// route the input
	DoBrakeStop();
}

void AWSPC2Pawn::StartHandbrake(const FInputActionValue& Value)
{
	// route the input
	DoHandbrakeStart();
}

void AWSPC2Pawn::StopHandbrake(const FInputActionValue& Value)
{
	// route the input
	DoHandbrakeStop();
}

void AWSPC2Pawn::LookAround(const FInputActionValue& Value)
{
	// route the input
	DoLookAround(Value.Get<float>());
}

void AWSPC2Pawn::ToggleCamera(const FInputActionValue& Value)
{
	// route the input
	DoToggleCamera();
}

void AWSPC2Pawn::ResetVehicle(const FInputActionValue& Value)
{
	// route the input
	DoResetVehicle();
}

namespace
{
	struct FWSPC2SteerContext
	{
		float SpeedAllowance = 1.0f;
		float EffectiveAllowance = 1.0f;
		float ActivityDeg = 0.0f;
		bool bCountersteering = false;
	};

	FWSPC2SteerContext EvaluateSteerContext(const AWSPC2Pawn* Pawn, const UWSPC2VehicleTuning* Tuning, float Input)
	{
		FWSPC2SteerContext Ctx;

		const float Speed = Pawn->GetSpeedKmh();
		static const float Speeds[] = { 0.0f, 25.0f, 60.0f, 100.0f, 180.0f };
		const float Limits[] = { 1.0f, 0.85f, Tuning->SteerAt60Kmh, Tuning->SteerAt100Kmh, Tuning->SteerAt180Kmh };

		float SpeedAllowance = Limits[UE_ARRAY_COUNT(Limits) - 1];
		for (int32 Key = 1; Key < UE_ARRAY_COUNT(Speeds); ++Key)
		{
			if (Speed <= Speeds[Key])
			{
				SpeedAllowance = FMath::GetMappedRangeValueClamped(FVector2f(Speeds[Key - 1], Speeds[Key]), FVector2f(Limits[Key - 1], Limits[Key]), Speed);
				break;
			}
		}

		Ctx.SpeedAllowance = SpeedAllowance;
		Ctx.EffectiveAllowance = SpeedAllowance;

		const FVector Local = Pawn->GetActorTransform().InverseTransformVectorNoScale(Pawn->GetVelocity());
		const float YawRateDeg = Pawn->GetMesh() ? Pawn->GetMesh()->GetPhysicsAngularVelocityInDegrees().Z : 0.0f;
		const float MaxSteer = FMath::Max(Tuning->MaxSteerAngle, 1.0f);

		// Unlock steering smoothly when the driver opposes the slide or an active pendulum swing.
		if (Local.Size2D() > 300.0f && Local.X > 0.0f)
		{
			const float SlipDeg = FMath::RadiansToDegrees(FMath::Atan2(FMath::Abs(Local.Y), Local.X));
			float TargetDeg = 0.0f;

			if (Input * Local.Y > 0.0f)
			{
				// Positive when yaw rate is driving the tail further out.
				const float SlipSign = (Local.Y >= 0.0f) ? 1.0f : -1.0f;
				const float YawIntoSlideDegPerSec = FMath::Max(0.0f, -SlipSign * YawRateDeg);
				TargetDeg = SlipDeg + YawIntoSlideDegPerSec * Tuning->CountersteerYawRateLookahead;
				Ctx.bCountersteering = true;
			}
			else if (FMath::Abs(YawRateDeg) > Tuning->CountersteerHoldYawRateDeg && Input * YawRateDeg < 0.0f)
			{
				// Retain catch authority across zero sideslip while arresting a rebound swing.
				TargetDeg = FMath::Abs(YawRateDeg) * Tuning->CountersteerYawRateLookahead;
				Ctx.bCountersteering = true;
			}

			if (Ctx.bCountersteering)
			{
				Ctx.ActivityDeg = TargetDeg;
				const float CatchFraction = (TargetDeg + Tuning->CountersteerMarginDeg) / MaxSteer;
				Ctx.EffectiveAllowance = FMath::Max(SpeedAllowance, FMath::Min(CatchFraction, 1.0f));
			}
		}

		return Ctx;
	}
}

void AWSPC2Pawn::DoSteering(float SteeringValue)
{
	const float PullBias = VehicleDamage ? VehicleDamage->GetSteeringPullBias() : 0.0f;
	const float Input = FMath::Clamp(SteeringValue + PullBias, -1.0f, 1.0f);

	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();
	const FWSPC2SteerContext Ctx = EvaluateSteerContext(this, Tuning, Input);

	// Snap the rack fast while catching a slide; preserve smooth normal turn-in otherwise.
	ChaosVehicleMovement->SteeringInputRate.RiseRate = Ctx.bCountersteering ? Tuning->CountersteerSlewRate : Tuning->SteeringRiseRate;
	ChaosVehicleMovement->SteeringInputRate.FallRate = Ctx.bCountersteering ? Tuning->CountersteerSlewRate : Tuning->SteeringFallRate;

	float ScaledInput = Input * Ctx.SpeedAllowance;
	if (Ctx.bCountersteering && FMath::Abs(Input) > KINDA_SMALL_NUMBER)
	{
		// Avoid double-scaling partial inputs by CatchFraction once a slide develops; blend continuously from 0 deg.
		const float Blend = FMath::Clamp(Ctx.ActivityDeg / 3.0f, 0.0f, 1.0f);
		const float ResponseScale = FMath::Lerp(Ctx.SpeedAllowance, 1.0f, Blend);
		const float CounterMag = FMath::Min(FMath::Abs(Input) * ResponseScale, Ctx.EffectiveAllowance);
		ScaledInput = FMath::Sign(Input) * FMath::Max(FMath::Abs(ScaledInput), CounterMag);
	}

	ChaosVehicleMovement->SetSteeringInput(ScaledInput);
}

float AWSPC2Pawn::GetSteeringAllowance(float Input) const
{
	return EvaluateSteerContext(this, GetDefault<UWSPC2VehicleTuning>(), Input).EffectiveAllowance;
}

void AWSPC2Pawn::DoThrottle(float ThrottleValue)
{
	const float DamageMult = VehicleDamage ? VehicleDamage->GetThrottleDamageMultiplier() : 1.0f;
	ChaosVehicleMovement->SetThrottleInput(ThrottleValue * DamageMult);

	// reset the brake input
	ChaosVehicleMovement->SetBrakeInput(0.0f);
}

void AWSPC2Pawn::DoBrake(float BrakeValue)
{
	// add the input
	ChaosVehicleMovement->SetBrakeInput(BrakeValue);

	// reset the throttle input
	ChaosVehicleMovement->SetThrottleInput(0.0f);
}

void AWSPC2Pawn::DoBrakeStart()
{
	// call the Blueprint hook for the brake lights
	BrakeLights(true);
}

void AWSPC2Pawn::DoBrakeStop()
{
	// call the Blueprint hook for the brake lights
	BrakeLights(false);

	// reset brake input to zero
	ChaosVehicleMovement->SetBrakeInput(0.0f);
}

void AWSPC2Pawn::DoHandbrakeStart()
{
	// add the input
	ApplyHandbrakeWithMechanicalLock(ChaosVehicleMovement, true);

	// call the Blueprint hook for the break lights
	BrakeLights(true);
}

void AWSPC2Pawn::DoHandbrakeStop()
{
	// add the input
	ApplyHandbrakeWithMechanicalLock(ChaosVehicleMovement, false);

	// call the Blueprint hook for the break lights
	BrakeLights(false);
}

void AWSPC2Pawn::DoLookAround(float YawDelta)
{
	// rotate the spring arm
	BackSpringArm->AddLocalRotation(FRotator(0.0f, YawDelta, 0.0f));
}

void AWSPC2Pawn::DoToggleCamera()
{
	// cycle: chase camera, then each on-car view
	CameraMode = (CameraMode + 1) % (OnCarViews.Num() + 1);
	bFrontCameraActive = CameraMode > 0;

	if (bFrontCameraActive)
	{
		FrontSpringArm->SetRelativeLocation(OnCarViews[CameraMode - 1]);
	}

	FrontCamera->SetActive(bFrontCameraActive);
	BackCamera->SetActive(!bFrontCameraActive);

	if (GEngine && IsLocallyControlled())
	{
		const FString Name = bFrontCameraActive && OnCarViewNames.IsValidIndex(CameraMode - 1) ? OnCarViewNames[CameraMode - 1] : FString(TEXT("Chase"));
		GEngine->AddOnScreenDebugMessage(7001, 2.0f, FColor::Cyan, FString::Printf(TEXT("Camera: %s"), *Name));
	}
}

void AWSPC2Pawn::SetOnCarViews(const TArray<FVector>& Locations, const TArray<FString>& Names)
{
	OnCarViews = Locations;
	OnCarViewNames = Names;

	if (bFrontCameraActive && OnCarViews.IsValidIndex(CameraMode - 1))
	{
		FrontSpringArm->SetRelativeLocation(OnCarViews[CameraMode - 1]);
	}
}

void AWSPC2Pawn::DoResetVehicle()
{
	// the server owns the car's position; a client asks it to do the reset
	if (!HasAuthority())
	{
		ServerResetVehicle();
		return;
	}

	// reset to a location slightly above our current one
	FVector ResetLocation = GetActorLocation() + FVector(0.0f, 0.0f, 50.0f);

	// reset to our yaw. Ignore pitch and roll
	FRotator ResetRotation = GetActorRotation();
	ResetRotation.Pitch = 0.0f;
	ResetRotation.Roll = 0.0f;

	// teleport the actor to the reset spot and reset physics
	SetActorTransform(FTransform(ResetRotation, ResetLocation, FVector::OneVector), false, nullptr, ETeleportType::TeleportPhysics);

	GetMesh()->SetPhysicsAngularVelocityInDegrees(FVector::ZeroVector);
	GetMesh()->SetPhysicsLinearVelocity(FVector::ZeroVector);

	if (VehicleDamage)
	{
		VehicleDamage->RepairAll();
	}
}

void AWSPC2Pawn::FlippedCheck()
{
	// check the difference in angle between the mesh's up vector and world up
	const float UpDot = FVector::DotProduct(FVector::UpVector, GetMesh()->GetUpVector());

	if (UpDot < FlipCheckMinDot && HasAuthority() && GetDefault<UWSPC2VehicleTuning>()->bAutoFlipReset)
	{
		// is this the second time we've checked that the vehicle is still flipped?
		if (bPreviousFlipCheck)
		{
			// reset the vehicle to upright
			DoResetVehicle();
		}
		
		// set the flipped check flag so the next check resets the car
		bPreviousFlipCheck = true;

	} else {

		// we're upright. reset the flipped check flag
		bPreviousFlipCheck = false;
	}
}

#undef LOCTEXT_NAMESPACE