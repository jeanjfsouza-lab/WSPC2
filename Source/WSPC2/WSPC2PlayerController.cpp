// Copyright Epic Games, Inc. All Rights Reserved.


#include "WSPC2PlayerController.h"
#include "WSPC2Pawn.h"
#include "WSPC2GunnerPawn.h"
#include "WSPC2GameMode.h"
#include "WSPC2PlayerState.h"
#include "WSPC2UI.h"
#include "EnhancedInputSubsystems.h"
#include "EnhancedInputComponent.h"
#include "InputAction.h"
#include "InputActionValue.h"
#include "InputMappingContext.h"
#include "ChaosWheeledVehicleMovementComponent.h"
#include "ChaosVehicleWheel.h"
#include "Blueprint/UserWidget.h"
#include "WSPC2.h"
#include "Engine/Engine.h"
#include "Camera/CameraActor.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Components/SkeletalMeshComponent.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "TimerManager.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "GameFramework/PlayerStart.h"
#include "Widgets/Input/SVirtualJoystick.h"

void AWSPC2PlayerController::BeginPlay()
{
	Super::BeginPlay();

	// ensure we're attached to the vehicle pawn so that World Partition streaming works correctly
	bAttachToPawn = true;

	// automated test hook: -WSPC2TestSwap presses the change-seat key every 6 seconds
	if (IsLocalPlayerController() && FParse::Param(FCommandLine::Get(), TEXT("WSPC2TestSwap")))
	{
		FTimerHandle TestTimer;
		GetWorld()->GetTimerManager().SetTimer(TestTimer, this, &AWSPC2PlayerController::SwapSeat, 6.0f, true);
	}

	bTestDrive = IsLocalPlayerController() && FParse::Param(FCommandLine::Get(), TEXT("WSPC2TestDrive"));

	// automated test hook: -WSPC2TestShots saves a screenshot every 20 seconds, swinging the chase camera
	// to a different side each time (shots land in Saved/Screenshots)
	if (IsLocalPlayerController() && FParse::Param(FCommandLine::Get(), TEXT("WSPC2TestShots")))
	{
		FTimerHandle ShotTimer;
		GetWorld()->GetTimerManager().SetTimer(ShotTimer, this, &AWSPC2PlayerController::TestScreenshot, 20.0f, true);
	}
}

void AWSPC2PlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();

	// only add IMCs for local player controllers
	if (IsLocalPlayerController())
	{
		// Add Input Mapping Contexts
		if (UEnhancedInputLocalPlayerSubsystem* Subsystem = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(GetLocalPlayer()))
		{
			for (UInputMappingContext* CurrentContext : DefaultMappingContexts)
			{
				Subsystem->AddMappingContext(CurrentContext, 0);
			}

			// only add these IMCs if we're not using mobile touch input
			if (!ShouldUseTouchControls())
			{
				for (UInputMappingContext* CurrentContext : MobileExcludedMappingContexts)
				{
					Subsystem->AddMappingContext(CurrentContext, 0);
				}
			}

			if (bUseSteeringWheelControls)
			{
				Subsystem->AddMappingContext(SteeringWheelInputMappingContext, 0);
			}
		}

		SetupCrewInput();
	}

	// only spawn UI on local player controllers
	if (IsLocalPlayerController())
	{
		if (ShouldUseTouchControls())
		{
			// spawn the mobile controls widget
			MobileControlsWidget = CreateWidget<UUserWidget>(this, MobileControlsWidgetClass);

			if (MobileControlsWidget)
			{
				// add the controls to the player screen
				MobileControlsWidget->AddToPlayerScreen(0);

			} else {

				UE_LOG(LogWSPC2, Error, TEXT("Could not spawn mobile controls widget."));

			}
		}


		// spawn the UI widget and add it to the viewport
		VehicleUI = CreateWidget<UWSPC2UI>(this, VehicleUIClass);

		if (VehicleUI)
		{
			VehicleUI->AddToPlayerScreen(0);

		} else {

			UE_LOG(LogWSPC2, Error, TEXT("Could not spawn vehicle UI widget."));

		}
	}
}

void AWSPC2PlayerController::SetupCrewInput()
{
	// actions and bindings are created here instead of as assets, so they live in source control as text
	SwapSeatAction = NewObject<UInputAction>(this, TEXT("IA_SwapSeat"));
	SirenAction = NewObject<UInputAction>(this, TEXT("IA_Siren"));

	GunnerLookMouseAction = NewObject<UInputAction>(this, TEXT("IA_GunnerLookMouse"));
	GunnerLookMouseAction->ValueType = EInputActionValueType::Axis2D;

	GunnerLookStickAction = NewObject<UInputAction>(this, TEXT("IA_GunnerLookStick"));
	GunnerLookStickAction->ValueType = EInputActionValueType::Axis2D;

	CrewMappingContext = NewObject<UInputMappingContext>(this, TEXT("IMC_Crew"));

	CrewMappingContext->MapKey(SwapSeatAction, EKeys::F);
	CrewMappingContext->MapKey(SwapSeatAction, EKeys::Gamepad_DPad_Up);

	CrewMappingContext->MapKey(SirenAction, EKeys::H);
	CrewMappingContext->MapKey(SirenAction, EKeys::Gamepad_DPad_Down);

	CameraAction = NewObject<UInputAction>(this, TEXT("IA_CrewCamera"));
	CrewMappingContext->MapKey(CameraAction, EKeys::C);
	CrewMappingContext->MapKey(CameraAction, EKeys::Gamepad_RightThumbstick);

	CrewMappingContext->MapKey(GunnerLookMouseAction, EKeys::Mouse2D);
	CrewMappingContext->MapKey(GunnerLookStickAction, EKeys::Gamepad_Right2D);

	if (UEnhancedInputLocalPlayerSubsystem* Subsystem = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(GetLocalPlayer()))
	{
		Subsystem->AddMappingContext(CrewMappingContext, 1);
	}

	if (UEnhancedInputComponent* EnhancedInput = Cast<UEnhancedInputComponent>(InputComponent))
	{
		EnhancedInput->BindAction(SwapSeatAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnSwapSeat);
		EnhancedInput->BindAction(SirenAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnSiren);
		EnhancedInput->BindAction(CameraAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnCamera);
		EnhancedInput->BindAction(GunnerLookMouseAction, ETriggerEvent::Triggered, this, &AWSPC2PlayerController::OnGunnerLookMouse);
		EnhancedInput->BindAction(GunnerLookStickAction, ETriggerEvent::Triggered, this, &AWSPC2PlayerController::OnGunnerLookStick);
	}
	else
	{
		UE_LOG(LogWSPC2, Error, TEXT("Crew input needs the Enhanced Input component."));
	}
}

void AWSPC2PlayerController::OnSwapSeat(const FInputActionValue& Value)
{
	ServerRequestSeatSwap();
}

void AWSPC2PlayerController::OnSiren(const FInputActionValue& Value)
{
	ServerToggleSiren();
}

void AWSPC2PlayerController::OnCamera(const FInputActionValue& Value)
{
	// driver: chase, dashboard, hood, bumper. Gunner: first or third person.
	if (AWSPC2Pawn* Car = Cast<AWSPC2Pawn>(GetPawn()))
	{
		Car->DoToggleCamera();
	}
	else if (AWSPC2GunnerPawn* Gunner = Cast<AWSPC2GunnerPawn>(GetPawn()))
	{
		Gunner->ToggleView();
	}
}

void AWSPC2PlayerController::TickTestDrive(float Delta)
{
	AWSPC2Pawn* Car = Cast<AWSPC2Pawn>(GetPawn());

	if (!IsValid(Car) || TestDrivePhase > 2)
	{
		return;
	}

	UChaosWheeledVehicleMovementComponent* Movement = Car->GetChaosVehicleMovement();
	const float Speed = Car->GetSpeedKmh();

	// the test drives the car itself: ignore any gamepad or wheel plugged into this PC
	Car->DisableInput(this);
	Car->DoSteering(0.0f);

	TestDriveClock += Delta;

	if (TestDrivePhase == 0)
	{
		// the test map is too small to reach 100 km/h: build a 3 km straight high above it and put the car on it
		if (!bTestDriveStripBuilt && TestDriveClock > 3.0f)
		{
			bTestDriveStripBuilt = true;

			if (UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")))
			{
				AStaticMeshActor* Strip = GetWorld()->SpawnActor<AStaticMeshActor>(FVector(150000.0f, 0.0f, 20000.0f), FRotator::ZeroRotator);
				Strip->SetMobility(EComponentMobility::Movable);
				Strip->GetStaticMeshComponent()->SetStaticMesh(Cube);
				Strip->SetActorScale3D(FVector(3000.0f, 200.0f, 1.0f));
			}

			Car->SetActorTransform(FTransform(FRotator::ZeroRotator, FVector(2000.0f, 0.0f, 20080.0f)), false, nullptr, ETeleportType::TeleportPhysics);
			Car->GetMesh()->SetPhysicsLinearVelocity(FVector::ZeroVector);
			Car->GetMesh()->SetPhysicsAngularVelocityInDegrees(FVector::ZeroVector);
		}

		if (FMath::FloorToInt(TestDriveClock) != FMath::FloorToInt(TestDriveClock - Delta))
		{
			const FVector Location = Car->GetActorLocation();
			const FVector Spin = Car->GetMesh()->GetPhysicsAngularVelocityInDegrees();

			UE_LOG(LogWSPC2, Log, TEXT("TestTrace: settle t=%.0f  pos (%.1f, %.1f, %.2f) m  yaw %.1f  spin (%.1f, %.1f, %.1f) deg/s  steer %.2f throttle %.2f handbrake %d"),
				TestDriveClock, Location.X * 0.01f, Location.Y * 0.01f, Location.Z * 0.01f, Car->GetActorRotation().Yaw,
				Spin.X, Spin.Y, Spin.Z, Movement->GetSteeringInput(), Movement->GetThrottleInput(), Movement->GetHandbrakeInput() ? 1 : 0);
		}

		// let the car settle on its springs
		if (TestDriveClock > 9.0f)
		{
			TestDrivePhase = 1;
			TestDriveClock = 0.0f;
			TestDriveDistance = 0.0f;
			TestDriveStartYaw = Car->GetActorRotation().Yaw;
		}

		return;
	}

	TestDriveDistance += Car->GetVelocity().Size() * Delta * 0.01f;

	// a trace line every two seconds, to see what the car is actually doing
	if (FMath::FloorToInt(TestDriveClock / 2.0f) != FMath::FloorToInt((TestDriveClock - Delta) / 2.0f))
	{
		const FVector Location = Car->GetActorLocation();
		const FRotator Rotation = Car->GetActorRotation();

		UE_LOG(LogWSPC2, Log, TEXT("TestTrace: t=%.0f phase %d  %.0f km/h  gear %d  rpm %.0f  pos (%.0f, %.0f, %.0f) m  yaw %.1f pitch %.1f roll %.1f"),
			TestDriveClock, TestDrivePhase, Speed, Movement->GetCurrentGear(), Movement->GetEngineRotationSpeed(),
			Location.X * 0.01f, Location.Y * 0.01f, Location.Z * 0.01f, Rotation.Yaw, Rotation.Pitch, Rotation.Roll);
	}

	if (TestDrivePhase == 1)
	{
		Car->DoThrottle(1.0f);
		TestDrivePeakSpeed = FMath::Max(TestDrivePeakSpeed, Speed);

		// check the wheel animation input once: an undriven front wheel should turn exactly as fast as the road passes
		if (Movement->Wheels.IsValidIndex(0) && Movement->Wheels[0])
		{
			const float Angle = Movement->Wheels[0]->GetRotationAngle();

			if (!bTestDriveSpinLogged && Speed > 40.0f && Delta > KINDA_SMALL_NUMBER)
			{
				const float Expected = FMath::RadiansToDegrees(Car->GetVelocity().Size() * Delta / Movement->Wheels[0]->GetWheelRadius());

				UE_LOG(LogWSPC2, Log, TEXT("TestDrive: at %.0f km/h the front wheel turned %.1f deg this frame, road speed implies %.1f deg (frame %.1f ms)"),
					Speed, Angle - TestDriveLastFrontAngle, Expected, Delta * 1000.0f);

				bTestDriveSpinLogged = true;
			}

			TestDriveLastFrontAngle = Angle;
		}

		if (TestDriveTo60 < 0.0f && Speed >= 60.0f)
		{
			TestDriveTo60 = TestDriveClock;
		}

		if (Speed >= 100.0f || TestDriveClock > 40.0f)
		{
			UE_LOG(LogWSPC2, Log, TEXT("TestDrive: 0-60 km/h in %.1f s, 0-%.0f km/h in %.1f s over %.0f m, gear %d, heading drift %.1f deg"),
				TestDriveTo60, Speed, TestDriveClock, TestDriveDistance, Movement->GetCurrentGear(), FRotator::NormalizeAxis(Car->GetActorRotation().Yaw - TestDriveStartYaw));

			TestDrivePhase = 2;
			TestDriveClock = 0.0f;
			TestDriveDistance = 0.0f;
			TestDrivePeakSpeed = Speed;
		}
	}
	else
	{
		Car->DoBrake(1.0f);

		if (Speed < 1.0f || TestDriveClock > 20.0f)
		{
			const float Mps = TestDrivePeakSpeed / 3.6f;

			UE_LOG(LogWSPC2, Log, TEXT("TestDrive: %.0f-0 km/h in %.1f s over %.1f m (average %.2f g), heading drift %.1f deg"),
				TestDrivePeakSpeed, TestDriveClock, TestDriveDistance,
				TestDriveDistance > 0.0f ? (Mps * Mps) / (2.0f * TestDriveDistance * 9.81f) : 0.0f,
				FRotator::NormalizeAxis(Car->GetActorRotation().Yaw - TestDriveStartYaw));

			Car->DoBrake(0.0f);
			TestDrivePhase = 3;
		}
	}
}

void AWSPC2PlayerController::OnGunnerLookMouse(const FInputActionValue& Value)
{
	if (AWSPC2GunnerPawn* Gunner = Cast<AWSPC2GunnerPawn>(GetPawn()))
	{
		// moving the mouse up should raise the aim
		const FVector2D Delta = Value.Get<FVector2D>();
		Gunner->AddAimInput(FVector2D(Delta.X, Delta.Y) * GunnerMouseSensitivity);
	}
}

void AWSPC2PlayerController::OnGunnerLookStick(const FInputActionValue& Value)
{
	if (AWSPC2GunnerPawn* Gunner = Cast<AWSPC2GunnerPawn>(GetPawn()))
	{
		const FVector2D Stick = Value.Get<FVector2D>();
		const float Step = GunnerStickRate * GetWorld()->GetDeltaSeconds();
		Gunner->AddAimInput(FVector2D(Stick.X, Stick.Y) * Step);
	}
}

void AWSPC2PlayerController::ServerRequestSeatSwap_Implementation()
{
	if (AWSPC2GameMode* GameMode = GetWorld()->GetAuthGameMode<AWSPC2GameMode>())
	{
		GameMode->RequestSeatSwap(this);
	}
}

void AWSPC2PlayerController::ServerToggleSiren_Implementation()
{
	if (AWSPC2Pawn* Car = GetCurrentVehicle())
	{
		Car->SetSiren(!Car->IsSirenOn());
	}
}

void AWSPC2PlayerController::TestScreenshot()
{
	// camera positions relative to the car: X forward, Y right, Z up
	static const FVector Offsets[] =
	{
		FVector(0.0f, -750.0f, 110.0f),		// left side
		FVector(520.0f, -480.0f, 170.0f),	// front left
		FVector(-560.0f, 480.0f, 190.0f),	// rear right
		FVector(650.0f, 0.0f, 130.0f),		// front
	};

	const int32 View = TestShotIndex % (UE_ARRAY_COUNT(Offsets) + 1);
	++TestShotIndex;

	if (AWSPC2Pawn* Car = GetCurrentVehicle())
	{
		if (View == UE_ARRAY_COUNT(Offsets))
		{
			// every fifth shot is the player's own chase camera
			SetViewTarget(GetPawn());
		}
		else
		{
			if (!IsValid(TestCamera))
			{
				TestCamera = GetWorld()->SpawnActor<ACameraActor>();
			}

			const FVector Target = Car->GetActorLocation() + FVector(0.0f, 0.0f, 70.0f);
			const FVector Location = Car->GetActorTransform().TransformPosition(Offsets[View]);

			TestCamera->SetActorLocationAndRotation(Location, (Target - Location).Rotation());
			SetViewTarget(TestCamera);
		}
	}

	// let the camera move this frame, then capture
	GetWorld()->GetTimerManager().SetTimerForNextTick([this]()
	{
		ConsoleCommand(TEXT("HighResShot 1280x720"));
	});
}

void AWSPC2PlayerController::SwapSeat()
{
	ServerRequestSeatSwap();
}

void AWSPC2PlayerController::ClientNotify_Implementation(const FString& Message)
{
	UE_LOG(LogWSPC2, Log, TEXT("Notify: %s"), *Message);

	if (GEngine)
	{
		GEngine->AddOnScreenDebugMessage(-1, 3.0f, FColor::Yellow, Message);
	}
}

AWSPC2Pawn* AWSPC2PlayerController::GetCurrentVehicle() const
{
	if (AWSPC2Pawn* Car = Cast<AWSPC2Pawn>(GetPawn()))
	{
		return Car;
	}

	if (const AWSPC2GunnerPawn* Gunner = Cast<AWSPC2GunnerPawn>(GetPawn()))
	{
		return Gunner->GetVehicle();
	}

	return nullptr;
}

void AWSPC2PlayerController::Tick(float Delta)
{
	Super::Tick(Delta);

	if (!IsLocalPlayerController())
	{
		return;
	}

	if (bTestDrive)
	{
		TickTestDrive(Delta);
	}

	// resolved from the pawn each frame, because OnPossess only runs on the server
	AWSPC2Pawn* Car = GetCurrentVehicle();

	if (IsValid(Car) && IsValid(VehicleUI))
	{
		VehicleUI->UpdateSpeed(Car->GetChaosVehicleMovement()->GetForwardSpeed());
		VehicleUI->UpdateGear(Car->GetChaosVehicleMovement()->GetCurrentGear());
	}

	// temporary status line until the real HUD exists
	if (GEngine)
	{
		const AWSPC2PlayerState* State = GetPlayerState<AWSPC2PlayerState>();
		const EWSPC2Seat Seat = State ? State->Seat : EWSPC2Seat::None;

		const TCHAR* SeatName = Seat == EWSPC2Seat::Driver ? TEXT("DRIVER") : Seat == EWSPC2Seat::Gunner ? TEXT("GUNNER") : TEXT("NO SEAT");

		const FString Status = FString::Printf(TEXT("%s  |  %3.0f km/h  |  Siren %s  |  [F] change seat (stopped)  [H] siren  [C] camera"),
			SeatName,
			IsValid(Car) ? Car->GetSpeedKmh() : 0.0f,
			IsValid(Car) && Car->IsSirenOn() ? TEXT("ON") : TEXT("off"));

		GEngine->AddOnScreenDebugMessage(static_cast<uint64>(GetUniqueID()), 0.0f, FColor::White, Status);
	}
}

void AWSPC2PlayerController::OnPossess(APawn* InPawn)
{
	Super::OnPossess(InPawn);

	// the pawn is the car for the driver and a gunner pawn for the passenger
	VehiclePawn = Cast<AWSPC2Pawn>(InPawn);

	if (IsValid(VehiclePawn))
	{
		// subscribe to the pawn's OnDestroyed delegate
		VehiclePawn->OnDestroyed.AddUniqueDynamic(this, &AWSPC2PlayerController::OnPawnDestroyed);
	}
}

void AWSPC2PlayerController::PawnLeavingGame()
{
	// leave the car where it is so the gunner can take the wheel; anything else is cleaned up as usual
	if (Cast<AWSPC2Pawn>(GetPawn()))
	{
		UnPossess();
		return;
	}

	Super::PawnLeavingGame();
}

void AWSPC2PlayerController::OnPawnDestroyed(AActor* DestroyedPawn)
{
	// only whoever is driving that car respawns it
	if (DestroyedPawn != VehiclePawn)
	{
		return;
	}

	// find the player start
	TArray<AActor*> ActorList;
	UGameplayStatics::GetAllActorsOfClass(GetWorld(), APlayerStart::StaticClass(), ActorList);

	if (ActorList.Num() > 0)
	{
		// spawn a vehicle at the player start
		const FTransform SpawnTransform = ActorList[0]->GetActorTransform();

		if (AWSPC2Pawn* RespawnedVehicle = GetWorld()->SpawnActor<AWSPC2Pawn>(VehiclePawnClass, SpawnTransform))
		{
			// possess the vehicle
			Possess(RespawnedVehicle);

			// tell the game mode, so the gunner is moved to the new car
			if (AWSPC2GameMode* GameMode = GetWorld()->GetAuthGameMode<AWSPC2GameMode>())
			{
				GameMode->OnPatrolCarReplaced(RespawnedVehicle);
			}
		}
	}
}

bool AWSPC2PlayerController::ShouldUseTouchControls() const
{
	// are we on a mobile platform? Should we force touch?
	return SVirtualJoystick::ShouldDisplayTouchInterface() || bForceTouchControls;
}
