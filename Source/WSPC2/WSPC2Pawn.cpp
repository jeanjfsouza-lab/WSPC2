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
#include "WSPC2.h"
#include "WSPC2VehicleTuning.h"
#include "Components/PointLightComponent.h"
#include "Components/SceneComponent.h"
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
	BackSpringArm->CameraLagMaxDistance = 50.0f;

	BackCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("Back Camera"));
	BackCamera->SetupAttachment(BackSpringArm);

	// Configure the car mesh
	GetMesh()->SetSimulatePhysics(true);
	GetMesh()->SetCollisionProfileName(FName("Vehicle"));

	// get the Chaos Wheeled movement component
	ChaosVehicleMovement = CastChecked<UChaosWheeledVehicleMovementComponent>(GetVehicleMovement());

	// gunner seat: passenger side (right), at window height
	GunnerSeat = CreateDefaultSubobject<USceneComponent>(TEXT("Gunner Seat"));
	GunnerSeat->SetupAttachment(GetMesh());
	GunnerSeat->SetRelativeLocation(FVector(-20.0f, 60.0f, 100.0f));

	// roof light bar
	SirenLightLeft = CreateDefaultSubobject<UPointLightComponent>(TEXT("Siren Light Left"));
	SirenLightLeft->SetupAttachment(GetMesh());
	SirenLightLeft->SetRelativeLocation(FVector(-20.0f, -35.0f, 150.0f));
	SirenLightLeft->SetLightColor(FLinearColor(1.0f, 0.02f, 0.02f));
	SirenLightLeft->SetIntensity(60000.0f);
	SirenLightLeft->SetAttenuationRadius(2500.0f);
	SirenLightLeft->SetCastShadows(false);
	SirenLightLeft->SetVisibility(false);

	SirenLightRight = CreateDefaultSubobject<UPointLightComponent>(TEXT("Siren Light Right"));
	SirenLightRight->SetupAttachment(GetMesh());
	SirenLightRight->SetRelativeLocation(FVector(-20.0f, 35.0f, 150.0f));
	SirenLightRight->SetLightColor(FLinearColor(0.02f, 0.08f, 1.0f));
	SirenLightRight->SetIntensity(60000.0f);
	SirenLightRight->SetAttenuationRadius(2500.0f);
	SirenLightRight->SetCastShadows(false);
	SirenLightRight->SetVisibility(false);
}

void AWSPC2Pawn::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AWSPC2Pawn, bSirenOn);
}

void AWSPC2Pawn::SetCrewLayout(const FVector& GunnerSeatLocation, const FVector& LightBarCentre, float LightHalfSpacing)
{
	GunnerSeat->SetRelativeLocation(GunnerSeatLocation);
	SirenLightLeft->SetRelativeLocation(LightBarCentre + FVector(0.0f, -LightHalfSpacing, 0.0f));
	SirenLightRight->SetRelativeLocation(LightBarCentre + FVector(0.0f, LightHalfSpacing, 0.0f));
}

void AWSPC2Pawn::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);

	ChaosVehicleMovement->SetHandbrakeInput(false);
}

void AWSPC2Pawn::UnPossessed()
{
	Super::UnPossessed();

	// nobody at the wheel: no throttle, no steering, handbrake on
	ChaosVehicleMovement->SetThrottleInput(0.0f);
	ChaosVehicleMovement->SetBrakeInput(0.0f);
	ChaosVehicleMovement->SetSteeringInput(0.0f);
	ChaosVehicleMovement->SetHandbrakeInput(true);
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

	SirenLightLeft->SetVisibility(bSirenOn && bLeftPhase);
	SirenLightRight->SetVisibility(bSirenOn && !bLeftPhase);
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

void AWSPC2Pawn::DoSteering(float SteeringValue)
{
	// add the input
	ChaosVehicleMovement->SetSteeringInput(SteeringValue);
}

void AWSPC2Pawn::DoThrottle(float ThrottleValue)
{
	// add the input
	ChaosVehicleMovement->SetThrottleInput(ThrottleValue);

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
	ChaosVehicleMovement->SetHandbrakeInput(true);

	// call the Blueprint hook for the break lights
	BrakeLights(true);
}

void AWSPC2Pawn::DoHandbrakeStop()
{
	// add the input
	ChaosVehicleMovement->SetHandbrakeInput(false);

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