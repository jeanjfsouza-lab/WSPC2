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
#include "Blueprint/UserWidget.h"
#include "WSPC2.h"
#include "Engine/Engine.h"
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

		const FString Status = FString::Printf(TEXT("%s  |  %3.0f km/h  |  Siren %s  |  [F] change seat (stopped)  [H] siren"),
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
