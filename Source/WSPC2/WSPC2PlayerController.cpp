// Copyright Epic Games, Inc. All Rights Reserved.


#include "WSPC2PlayerController.h"
#include "WSPC2Pawn.h"
#include "WSPC2SportsCar.h"
#include "WSPC2VehicleProfile.h"
#include "WSPC2GunnerPawn.h"
#include "WSPC2GameMode.h"
#include "WSPC2VehicleTuning.h"
#include "WSPC2PlayerState.h"
#include "WSPC2UI.h"
#include "WSPC2VehicleDamageComponent.h"
#include "WSPC2Gunnery.h"
#include "WSPC2CrewComponent.h"
#include "WSPC2Mission.h"
#include "WSPC2TestTrackDirector.h"
#include "WSPC2VehicleAudioComponent.h"
#include "EnhancedInputSubsystems.h"
#include "EnhancedInputComponent.h"
#include "InputAction.h"
#include "InputActionValue.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "ChaosWheeledVehicleMovementComponent.h"
#include "ChaosVehicleWheel.h"
#include "Blueprint/UserWidget.h"
#include "WSPC2.h"
#include "Engine/Engine.h"
#include "Camera/CameraActor.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "UnrealClient.h"
#if WITH_EDITOR
#include "AssetCompilingManager.h"
#endif
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Components/SkeletalMeshComponent.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "RenderCore.h"
#include "RHI.h"
#include "TimerManager.h"
#include "Engine/World.h"
#include "EngineUtils.h"
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
	bTestGround = IsLocalPlayerController() && FParse::Param(FCommandLine::Get(), TEXT("WSPC2TestGround"));
	bTestDamage = IsLocalPlayerController() && FParse::Param(FCommandLine::Get(), TEXT("WSPC2TestDamage"));
	bTestFleet = IsLocalPlayerController() && FParse::Param(FCommandLine::Get(), TEXT("WSPC2TestFleet"));
	bTestGunnery = IsLocalPlayerController() && HasAuthority() && FParse::Param(FCommandLine::Get(), TEXT("WSPC2TestGunnery"));
	bTestTrackAudit = IsLocalPlayerController() && HasAuthority() && FParse::Param(FCommandLine::Get(), TEXT("WSPC2TestTrackAudit"));

	// -WSPC2Mission=<Id>: starts a campaign mission once the map has settled (on the server's own player)
	FString StartMissionId;
	if (IsLocalPlayerController() && HasAuthority() && FParse::Value(FCommandLine::Get(), TEXT("WSPC2Mission="), StartMissionId))
	{
		FTimerHandle MissionTimer;
		GetWorld()->GetTimerManager().SetTimer(MissionTimer, [this, StartMissionId]()
		{
			ServerStartMission_Implementation(FName(*StartMissionId));
		}, 8.0f, false);
	}

	// automated test hook: -WSPC2TestShots saves a screenshot every 20 seconds, swinging the chase camera
	// to a different side each time (shots land in Saved/Screenshots)
	if (IsLocalPlayerController() && FParse::Param(FCommandLine::Get(), TEXT("WSPC2TestShots")))
	{
		FTimerHandle ShotTimer;
		GetWorld()->GetTimerManager().SetTimer(ShotTimer, this, &AWSPC2PlayerController::TestScreenshot, 20.0f, true);
	}

	// automated test hook: -WSPC2Views=<file> visits a list of fixed cameras, saves one named screenshot
	// from each (Saved/Screenshots/Views) and then quits. One camera per line: name;x,y,z;lookX,lookY,lookZ
	// A name "car:<name>" gives the camera in the player's car space; "pawn:<view>" (coordinates ignored) looks
	// through the car's own camera of that name, as the player would
	FString ViewsFile;
	if (IsLocalPlayerController() && FParse::Value(FCommandLine::Get(), TEXT("WSPC2Views="), ViewsFile))
	{
		TArray<FString> Lines;
		FFileHelper::LoadFileToStringArray(Lines, *ViewsFile);

		for (const FString& Line : Lines)
		{
			TArray<FString> Parts, From, To;
			Line.ParseIntoArray(Parts, TEXT(";"));

			if (Parts.Num() == 3 && Parts[1].ParseIntoArray(From, TEXT(",")) == 3 && Parts[2].ParseIntoArray(To, TEXT(",")) == 3)
			{
				FTestView View;
				View.Name = Parts[0];
				if (View.Name.RemoveFromStart(TEXT("car:")))
				{
					View.bCarSpace = true;
				}
				else if (View.Name.RemoveFromStart(TEXT("pawn:")))
				{
					View.PawnView = View.Name;
					View.Name = TEXT("pawn_") + View.Name;
				}
				View.Location = FVector(FCString::Atod(*From[0]), FCString::Atod(*From[1]), FCString::Atod(*From[2]));
				View.LookAt = FVector(FCString::Atod(*To[0]), FCString::Atod(*To[1]), FCString::Atod(*To[2]));
				TestViews.Add(View);
			}
		}

		UE_LOG(LogWSPC2, Log, TEXT("Views: %d cameras read from %s"), TestViews.Num(), *ViewsFile);

		if (TestViews.Num() > 0)
		{
			FTimerHandle ViewTimer;
			GetWorld()->GetTimerManager().SetTimer(ViewTimer, this, &AWSPC2PlayerController::TestViewStep, 6.0f, true, 15.0f);
		}
	}
}

void AWSPC2PlayerController::TickTestGround(float Delta)
{
	// automated test hook: -WSPC2TestGround drives the car straight for a while on whatever map is loaded
	// and logs where it is, to prove the ground carries it (it does not fall through or get stuck)
	AWSPC2Pawn* Car = Cast<AWSPC2Pawn>(GetPawn());

	if (!IsValid(Car))
	{
		return;
	}

	Car->DisableInput(this);
	Car->DoSteering(0.0f);

	const float Before = TestGroundClock;
	TestGroundClock += Delta;

	if (TestGroundClock > 8.0f && TestGroundClock < 22.0f)
	{
		Car->DoThrottle(0.6f);
	}
	else if (Before < 22.0f && TestGroundClock >= 22.0f)
	{
		Car->DoThrottle(0.0f);
		Car->DoHandbrakeStart();
	}

	if (FMath::FloorToInt(TestGroundClock / 3.0f) != FMath::FloorToInt(Before / 3.0f))
	{
		const FVector Location = Car->GetActorLocation();
		const FRotator Rotation = Car->GetActorRotation();

		UE_LOG(LogWSPC2, Log, TEXT("Ground: t=%2.0f  pos (%.1f, %.1f, %.2f) m  %.0f km/h  wheels on ground %d  pitch %.1f roll %.1f"),
			TestGroundClock, Location.X * 0.01f, Location.Y * 0.01f, Location.Z * 0.01f, Car->GetSpeedKmh(),
			Car->GetChaosVehicleMovement()->IsMovingOnGround() ? 1 : 0, Rotation.Pitch, Rotation.Roll);
	}

	if (Before < 31.0f && TestGroundClock >= 31.0f)
	{
		UE_LOG(LogWSPC2, Log, TEXT("Ground: complete"));
		ConsoleCommand(TEXT("quit"));
	}
}

void AWSPC2PlayerController::TestViewStep()
{
#if WITH_EDITOR
	// a view is only worth capturing once nothing it shows is still being compiled
	const int32 Pending = FAssetCompilingManager::Get().GetNumRemainingAssets();

	if (Pending > 0 && TestViewWaits < 600)
	{
		if (TestViewWaits % 10 == 0)
		{
			UE_LOG(LogWSPC2, Log, TEXT("Views: waiting, %d assets or shaders still compiling"), Pending);
		}

		++TestViewWaits;
		TestViewFrame0 = GFrameCounter;
		TestViewTime0 = FPlatformTime::Seconds();
		return;
	}
#endif

	// the camera has sat at the current view for a full step, so streaming has caught up: capture it
	if (TestViews.IsValidIndex(TestViewIndex))
	{
		const double Seconds = FPlatformTime::Seconds() - TestViewTime0;
		const double Fps = Seconds > 0.0 ? double(GFrameCounter - TestViewFrame0) / Seconds : 0.0;

		// steady-state cost of the view (counters restart 3 s after the camera moved), split by thread
		UE_LOG(LogWSPC2, Log, TEXT("Views: %s at %.1f fps (game %.1f ms, render %.1f ms, gpu %.1f ms)"), *TestViews[TestViewIndex].Name, Fps,
			FPlatformTime::ToMilliseconds(GGameThreadTime), FPlatformTime::ToMilliseconds(GRenderThreadTime),
			FPlatformTime::ToMilliseconds(RHIGetGPUFrameCycles()));

		FString ProfileView;
		if (FParse::Value(FCommandLine::Get(), TEXT("WSPC2ProfileView="), ProfileView) && ProfileView == TestViews[TestViewIndex].Name)
		{
			ConsoleCommand(TEXT("ProfileGPU"));
		}

		const FString File = FPaths::ProjectSavedDir() / TEXT("Screenshots") / TEXT("Views") / FString::Printf(TEXT("%02d_%s.png"), TestViewIndex, *TestViews[TestViewIndex].Name);
		FScreenshotRequest::RequestScreenshot(File, false, false);
	}

	++TestViewIndex;

	if (TestViewIndex >= TestViews.Num())
	{
		// give the last screenshot a few seconds to reach the disk, then leave
		UE_LOG(LogWSPC2, Log, TEXT("Views: complete"));

		FTimerHandle QuitTimer;
		GetWorld()->GetTimerManager().SetTimer(QuitTimer, [this]() { ConsoleCommand(TEXT("quit")); }, 4.0f, false);
		TestViews.Reset();
		return;
	}

	// The screenshot asked for above is taken when this frame is drawn, so the camera must not move
	// until after that: moving it now would put the next view in a file named after this one.
	FTimerHandle MoveTimer;
	GetWorld()->GetTimerManager().SetTimer(MoveTimer, [this]()
	{
		if (!TestViews.IsValidIndex(TestViewIndex))
		{
			return;
		}

		if (!IsValid(TestCamera))
		{
			TestCamera = GetWorld()->SpawnActor<ACameraActor>();
		}

		const FTestView& Next = TestViews[TestViewIndex];
		AWSPC2Pawn* Car = Cast<AWSPC2Pawn>(GetPawn());

		if (!Next.PawnView.IsEmpty() && IsValid(Car))
		{
			// cycle the car's camera until the named one is in use (at most once round)
			for (int32 Step = 0; Step < 8 && Car->GetActiveCameraName() != Next.PawnView; ++Step)
			{
				Car->DoToggleCamera();
			}
			SetViewTarget(Car);
		}
		else
		{
			const FTransform Space = (Next.bCarSpace && IsValid(Car)) ? Car->GetActorTransform() : FTransform::Identity;
			const FVector From = Space.TransformPosition(Next.Location);
			TestCamera->DetachFromActor(FDetachmentTransformRules::KeepWorldTransform);
			TestCamera->SetActorLocationAndRotation(From, (Space.TransformPosition(Next.LookAt) - From).Rotation());
			if (Next.bCarSpace && IsValid(Car))
			{
				// a camera given in the car's space rides with the car (a moving car stays in the picture)
				TestCamera->AttachToComponent(Car->GetRootComponent(), FAttachmentTransformRules::KeepWorldTransform);
			}
			SetViewTarget(TestCamera);
		}

		TestViewFrame0 = GFrameCounter;
		TestViewTime0 = FPlatformTime::Seconds();

		// leave the first seconds out of the measurement: caches and streaming catch up after a jump
		FTimerHandle SettleTimer;
		GetWorld()->GetTimerManager().SetTimer(SettleTimer, [this]()
		{
			TestViewFrame0 = GFrameCounter;
			TestViewTime0 = FPlatformTime::Seconds();
		}, 3.0f, false);
	}, 0.5f, false);
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

	// the D-pad belongs to the weapons (left, right: weapon; up: lock alone) and the siren (down); the seat swap and the
	// vehicle cycle moved to Y and L3 (2026-11-19). The template's car uses RT, LT, A, X, LB, Back, Start, right stick.
	CrewMappingContext->MapKey(SwapSeatAction, EKeys::F);
	CrewMappingContext->MapKey(SwapSeatAction, EKeys::Gamepad_FaceButton_Top);

	CrewMappingContext->MapKey(SirenAction, EKeys::H);
	CrewMappingContext->MapKey(SirenAction, EKeys::Gamepad_DPad_Down);

	CameraAction = NewObject<UInputAction>(this, TEXT("IA_CrewCamera"));
	CrewMappingContext->MapKey(CameraAction, EKeys::C);
	CrewMappingContext->MapKey(CameraAction, EKeys::Gamepad_RightThumbstick);

	CycleVehicleAction = NewObject<UInputAction>(this, TEXT("IA_CycleVehicle"));
	CrewMappingContext->MapKey(CycleVehicleAction, EKeys::V);
	CrewMappingContext->MapKey(CycleVehicleAction, EKeys::Gamepad_LeftThumbstick);

	PrevVehicleAction = NewObject<UInputAction>(this, TEXT("IA_PrevVehicle"));
	CrewMappingContext->MapKey(PrevVehicleAction, EKeys::B);

	CategoryVehicleAction = NewObject<UInputAction>(this, TEXT("IA_CategoryVehicle"));
	CrewMappingContext->MapKey(CategoryVehicleAction, EKeys::N);

	SirenModeAction = NewObject<UInputAction>(this, TEXT("IA_SirenMode"));
	CrewMappingContext->MapKey(SirenModeAction, EKeys::J);

	AirhornAction = NewObject<UInputAction>(this, TEXT("IA_Airhorn"));
	CrewMappingContext->MapKey(AirhornAction, EKeys::K);

	ShowroomSwapAction = NewObject<UInputAction>(this, TEXT("IA_ShowroomSwap"));
	CrewMappingContext->MapKey(ShowroomSwapAction, EKeys::Enter);

	WeaponPrevAction = NewObject<UInputAction>(this, TEXT("IA_WeaponPrev"));
	CrewMappingContext->MapKey(WeaponPrevAction, EKeys::Q);
	CrewMappingContext->MapKey(WeaponPrevAction, EKeys::Gamepad_DPad_Left);

	WeaponNextAction = NewObject<UInputAction>(this, TEXT("IA_WeaponNext"));
	CrewMappingContext->MapKey(WeaponNextAction, EKeys::E);
	CrewMappingContext->MapKey(WeaponNextAction, EKeys::Gamepad_DPad_Right);

	LockAction = NewObject<UInputAction>(this, TEXT("IA_Lock"));
	CrewMappingContext->MapKey(LockAction, EKeys::T);
	CrewMappingContext->MapKey(LockAction, EKeys::Gamepad_DPad_Up);

	// fire: RB, G or the left mouse button for whoever has the gun (the driver alone); RT only for the second player,
	// since on the driver's pad RT is the throttle
	FireAction = NewObject<UInputAction>(this, TEXT("IA_Fire"));
	CrewMappingContext->MapKey(FireAction, EKeys::G);
	CrewMappingContext->MapKey(FireAction, EKeys::LeftMouseButton);
	CrewMappingContext->MapKey(FireAction, EKeys::Gamepad_RightShoulder);

	GunnerTriggerAction = NewObject<UInputAction>(this, TEXT("IA_GunnerTrigger"));
	CrewMappingContext->MapKey(GunnerTriggerAction, EKeys::Gamepad_RightTrigger);

	CrewMappingContext->MapKey(GunnerLookMouseAction, EKeys::Mouse2D);
	{
		// without a dead zone a resting stick that is a little off centre turns the view by itself
		FEnhancedActionKeyMapping& StickMapping = CrewMappingContext->MapKey(GunnerLookStickAction, EKeys::Gamepad_Right2D);
		UInputModifierDeadZone* DeadZone = NewObject<UInputModifierDeadZone>(this);
		DeadZone->Type = EDeadZoneType::Radial;
		DeadZone->LowerThreshold = 0.2f;
		DeadZone->UpperThreshold = 1.0f;
		StickMapping.Modifiers.Add(DeadZone);
	}

	if (UEnhancedInputLocalPlayerSubsystem* Subsystem = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(GetLocalPlayer()))
	{
		Subsystem->AddMappingContext(CrewMappingContext, 1);
	}

	if (UEnhancedInputComponent* EnhancedInput = Cast<UEnhancedInputComponent>(InputComponent))
	{
		EnhancedInput->BindAction(SwapSeatAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnSwapSeat);
		EnhancedInput->BindAction(SirenAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnSiren);
		EnhancedInput->BindAction(CameraAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnCamera);
		EnhancedInput->BindAction(CycleVehicleAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnCycleVehicle);
		EnhancedInput->BindAction(PrevVehicleAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnPrevVehicle);
		EnhancedInput->BindAction(CategoryVehicleAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnCategoryVehicle);
		EnhancedInput->BindAction(SirenModeAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnSirenMode);
		EnhancedInput->BindAction(AirhornAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnAirhorn);
		EnhancedInput->BindAction(ShowroomSwapAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnShowroomSwap);
		EnhancedInput->BindAction(WeaponPrevAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnWeaponPrev);
		EnhancedInput->BindAction(WeaponNextAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnWeaponNext);
		EnhancedInput->BindAction(LockAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnLock);
		EnhancedInput->BindAction(FireAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnFirePressed);
		EnhancedInput->BindAction(FireAction, ETriggerEvent::Completed, this, &AWSPC2PlayerController::OnFireReleased);
		EnhancedInput->BindAction(GunnerTriggerAction, ETriggerEvent::Started, this, &AWSPC2PlayerController::OnGunnerTriggerPressed);
		EnhancedInput->BindAction(GunnerTriggerAction, ETriggerEvent::Completed, this, &AWSPC2PlayerController::OnFireReleased);
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

void AWSPC2PlayerController::OnCycleVehicle(const FInputActionValue& Value)
{
	ServerCycleVehiclePreset();
}

void AWSPC2PlayerController::OnPrevVehicle(const FInputActionValue& Value)
{
	ServerCycleVehicleDirection(-1);
}

void AWSPC2PlayerController::OnCategoryVehicle(const FInputActionValue& Value)
{
	ServerCycleVehicleCategory();
}

void AWSPC2PlayerController::OnSirenMode(const FInputActionValue& Value)
{
	ServerCycleSirenMode();
}

void AWSPC2PlayerController::OnAirhorn(const FInputActionValue& Value)
{
	ServerTriggerAirhorn();
}

void AWSPC2PlayerController::OnShowroomSwap(const FInputActionValue& Value)
{
	ServerSwapNearestShowroom();
}

bool AWSPC2PlayerController::HoldsTheGun() const
{
	// the second player always; the driver only when nobody rides as gunner
	if (Cast<AWSPC2GunnerPawn>(GetPawn()))
	{
		return true;
	}
	const AWSPC2Pawn* Car = Cast<AWSPC2Pawn>(GetPawn());
	return Car && Car->GetGunnery() && !Car->GetGunnery()->HasHumanGunner();
}

void AWSPC2PlayerController::OnWeaponPrev(const FInputActionValue& Value)
{
	if (HoldsTheGun())
	{
		ServerCycleWeapon(-1);
	}
}

void AWSPC2PlayerController::OnWeaponNext(const FInputActionValue& Value)
{
	if (HoldsTheGun())
	{
		ServerCycleWeapon(1);
	}
}

void AWSPC2PlayerController::OnLock(const FInputActionValue& Value)
{
	// the lock is the lone driver's aim; a second player aims by hand
	if (!Cast<AWSPC2Pawn>(GetPawn()) || !HoldsTheGun() || !PlayerCameraManager)
	{
		return;
	}
	ServerToggleLock(PlayerCameraManager->GetCameraLocation(), PlayerCameraManager->GetCameraRotation().Vector());
}

void AWSPC2PlayerController::OnFirePressed(const FInputActionValue& Value)
{
	if (HoldsTheGun())
	{
		ServerSetTrigger(true);
	}
}

void AWSPC2PlayerController::OnGunnerTriggerPressed(const FInputActionValue& Value)
{
	if (Cast<AWSPC2GunnerPawn>(GetPawn()))
	{
		ServerSetTrigger(true);
	}
}

void AWSPC2PlayerController::OnFireReleased(const FInputActionValue& Value)
{
	ServerSetTrigger(false);
}

void AWSPC2PlayerController::ServerCycleWeapon_Implementation(int32 Direction)
{
	AWSPC2Pawn* Car = GetCurrentVehicle();
	if (Car && Car->GetGunnery() && HoldsTheGun())
	{
		Car->GetGunnery()->CycleWeapon(Direction);
	}
}

void AWSPC2PlayerController::ServerToggleLock_Implementation(FVector ViewLocation, FVector ViewDirection)
{
	AWSPC2Pawn* Car = Cast<AWSPC2Pawn>(GetPawn());
	if (Car && Car->GetGunnery() && HoldsTheGun())
	{
		Car->GetGunnery()->ToggleLock(ViewLocation, ViewDirection);
		ClientNotify(Car->GetGunnery()->GetLockedTarget() ? TEXT("Alvo travado") : TEXT("Trava solta"));
	}
}

void AWSPC2PlayerController::Mission(const FString& Id)
{
	ServerStartMission(FName(*Id));
}

void AWSPC2PlayerController::MissionStop()
{
	ServerStopMission();
}

void AWSPC2PlayerController::ServerStartMission_Implementation(FName Id)
{
	if (AWSPC2MissionDirector* Director = AWSPC2MissionDirector::Get(GetWorld(), true))
	{
		Director->StartMission(Id);
	}
}

void AWSPC2PlayerController::ServerStopMission_Implementation()
{
	if (AWSPC2MissionDirector* Director = AWSPC2MissionDirector::Get(GetWorld(), false))
	{
		Director->StopMission();
	}
}

void AWSPC2PlayerController::ServerSetTrigger_Implementation(bool bDown)
{
	AWSPC2Pawn* Car = GetCurrentVehicle();
	if (Car && Car->GetGunnery() && (!bDown || HoldsTheGun()))
	{
		Car->GetGunnery()->SetTrigger(bDown);
	}
}

void AWSPC2PlayerController::TickTestDrive(float Delta)
{
	AWSPC2Pawn* Car = Cast<AWSPC2Pawn>(GetPawn());

	if (!IsValid(Car) || TestDrivePhase > 11)
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

		// -WSPC2TestWheelCam: a camera that rides beside the car, so the picture has settled the way it does for a
		// player, and one screenshot of the real frame at speed (Saved/Screenshots/WheelCam.png). Used to judge
		// motion blur and upscaler artefacts on the spinning wheels.
		static const bool bWheelCam = FParse::Param(FCommandLine::Get(), TEXT("WSPC2TestWheelCam"));
		static bool bWheelShotTaken = false;

		if (bWheelCam && !IsValid(TestCamera))
		{
			TestCamera = GetWorld()->SpawnActor<ACameraActor>();
			TestCamera->AttachToComponent(Car->GetMesh(), FAttachmentTransformRules::KeepRelativeTransform);
			TestCamera->SetActorRelativeLocation(FVector(40.0f, -330.0f, 55.0f));
			TestCamera->SetActorRelativeRotation(FRotator(0.0f, 90.0f, 0.0f));
			SetViewTarget(TestCamera);
		}

		if (bWheelCam && !bWheelShotTaken && Speed >= 92.0f)
		{
			bWheelShotTaken = true;
			FScreenshotRequest::RequestScreenshot(FPaths::ProjectSavedDir() / TEXT("Screenshots") / TEXT("WheelCam.png"), false, false);
		}

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
	else if (TestDrivePhase == 2)
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
			TestPlaceCar(Car, 400.0f);
			TestDrivePhase = 3;
			TestDriveClock = 0.0f;
			TestPeakSlip = 0.0f;
			TestPeakYawRate = 0.0f;
		}
	}
	else
	{
		// Handling. Sideslip is the angle between where the car points and where it travels: a few degrees while
		// cornering, past ~10 the tail is out, past ~60 the car has spun.
		float Slip = 0.0f;
		float YawRate = 0.0f;
		TestSlip(Car, Slip, YawRate);

		const float AbsSlip = FMath::Abs(Slip);
		const bool bTrace = FMath::FloorToInt(TestDriveClock * 4.0f) != FMath::FloorToInt((TestDriveClock - Delta) * 4.0f);

		if (TestDrivePhase == 3)
		{
			// power oversteer: full lock and full throttle from rest, as in a tight junction with the traction control off
			Car->DoThrottle(TestDriveClock > 1.0f ? 1.0f : 0.0f);
			Car->DoSteering(TestDriveClock > 1.0f ? 1.0f : 0.0f);

			if (TestDriveClock > 1.0f)
			{
				TestPeakSlip = FMath::Max(TestPeakSlip, AbsSlip);
				TestPeakYawRate = FMath::Max(TestPeakYawRate, FMath::Abs(YawRate));
			}
			if (bTrace)
			{
				UE_LOG(LogWSPC2, Log, TEXT("TestTrace: power t=%.2f  %.0f km/h  slip %.1f deg  yaw rate %.0f deg/s  gear %d"),
					TestDriveClock, Speed, Slip, YawRate, Movement->GetCurrentGear());
			}
			if (TestDriveClock > 5.0f)
			{
				UE_LOG(LogWSPC2, Log, TEXT("TestDrive: power oversteer from rest at full lock: peak sideslip %.1f deg, peak yaw rate %.0f deg/s, %.0f km/h after 4 s"),
					TestPeakSlip, TestPeakYawRate, Speed);

				TestPlaceCar(Car, 600.0f);
				TestDrivePhase = 4;
				TestDriveClock = 0.0f;
			}
		}
		else if (TestDrivePhase == 4 || TestDrivePhase == 6)
		{
			// run up to 110 km/h, dead straight
			Car->DoSteering(0.0f);
			Car->DoThrottle(1.0f);

			if (Speed >= 110.0f || TestDriveClock > 25.0f)
			{
				TestDrivePhase += 1;
				TestDriveClock = 0.0f;
				TestPeakSlip = 0.0f;
				TestPeakYawRate = 0.0f;
				TestSlideSign = 0.0f;
				bTestSlideReported = false;
			}
		}
		else if (TestDrivePhase == 5)
		{
			// a keyboard tap on full lock at 110 km/h for 0.4 s, then hands off: a stable car settles by itself
			Car->DoThrottle(0.5f);
			Car->DoSteering(TestDriveClock < 0.4f ? 1.0f : 0.0f);

			TestPeakSlip = FMath::Max(TestPeakSlip, AbsSlip);
			TestPeakYawRate = FMath::Max(TestPeakYawRate, FMath::Abs(YawRate));

			if (bTrace)
			{
				UE_LOG(LogWSPC2, Log, TEXT("TestTrace: flick t=%.2f  %.0f km/h  slip %.1f deg  yaw rate %.0f deg/s"), TestDriveClock, Speed, Slip, YawRate);
			}
			if (TestDriveClock > 4.0f)
			{
				const AWSPC2SportsCar* SportsCar = Cast<AWSPC2SportsCar>(Car);
				UE_LOG(LogWSPC2, Log, TEXT("TestDrive: full-lock tap at 110 km/h, hands off: peak sideslip %.1f deg, peak yaw rate %.0f deg/s; after 3.5 s slip %.1f deg, yaw rate %.0f deg/s (%s) | steerWheel=(vis=%d, deg=%.1f)"),
					TestPeakSlip, TestPeakYawRate, Slip, YawRate, (AbsSlip < 3.0f && FMath::Abs(YawRate) < 5.0f) ? TEXT("settled") : TEXT("NOT settled"),
					(SportsCar && SportsCar->HasSteeringWheelMesh()) ? 1 : 0, SportsCar ? SportsCar->GetDrawnSteeringWheelDeg() : 0.0f);

				TestPlaceCar(Car, 500.0f);
				TestDrivePhase = 8;
				TestDriveClock = 0.0f;
			}
		}
		else if (TestDrivePhase == 8 || TestDrivePhase == 10)
		{
			// run up to 150 km/h, dead straight
			Car->DoHandbrakeStop();
			Car->DoSteering(0.0f);
			Car->DoThrottle(1.0f);

			if (Speed >= 150.0f || TestDriveClock > 25.0f)
			{
				TestDrivePhase += 1;
				TestDriveClock = 0.0f;
				TestPeakSlip = 0.0f;
				TestPeakYawRate = 0.0f;
			}
		}
		else if (TestDrivePhase == 9)
		{
			// sustained high-speed steer under power at 150 km/h for 0.8 s, then hands off
			const bool bTurn = TestDriveClock < 0.8f;
			Car->DoThrottle(bTurn ? 0.85f : 0.4f);
			Car->DoSteering(bTurn ? 1.0f : 0.0f);

			TestPeakSlip = FMath::Max(TestPeakSlip, AbsSlip);
			TestPeakYawRate = FMath::Max(TestPeakYawRate, FMath::Abs(YawRate));

			if (bTrace)
			{
				UE_LOG(LogWSPC2, Log, TEXT("TestTrace: bend150 t=%.2f  %.0f km/h  slip %.1f deg  yaw rate %.0f deg/s"), TestDriveClock, Speed, Slip, YawRate);
			}
			if (TestDriveClock > 4.3f)
			{
				UE_LOG(LogWSPC2, Log, TEXT("TestDrive: sustained steer at 150 km/h, hands off: peak sideslip %.1f deg, peak yaw rate %.0f deg/s; after 3.5 s slip %.1f deg, yaw rate %.0f deg/s (%s)"),
					TestPeakSlip, TestPeakYawRate, Slip, YawRate,
					TestPeakSlip > 60.0f ? TEXT("SPUN") : ((AbsSlip < 3.0f && FMath::Abs(YawRate) < 5.0f) ? TEXT("settled") : TEXT("NOT settled")));

				TestPlaceCar(Car, 500.0f);
				TestDrivePhase = 10;
				TestDriveClock = 0.0f;
			}
		}
		else if (TestDrivePhase == 11)
		{
			// provoke a heavy slide at 150 km/h, pause briefly for reaction time, then catch with opposite lock under throttle
			const bool bProvoke = TestDriveClock < 0.75f;
			const bool bReactDelay = !bProvoke && TestDriveClock < 0.90f;
			float Steer = 0.0f;
			if (bProvoke)
			{
				Steer = 1.0f;
				Car->DoHandbrakeStart();
			}
			else
			{
				Car->DoHandbrakeStop();
				if (!bReactDelay)
				{
					Steer = AbsSlip > 2.0f ? FMath::Sign(Slip) : FMath::Clamp(Slip * 0.5f, -1.0f, 1.0f);
				}
			}

			Car->DoThrottle(0.6f);
			Car->DoSteering(Steer);

			TestPeakSlip = FMath::Max(TestPeakSlip, AbsSlip);
			TestPeakYawRate = FMath::Max(TestPeakYawRate, FMath::Abs(YawRate));

			if (bTrace)
			{
				UE_LOG(LogWSPC2, Log, TEXT("TestTrace: catch150 t=%.2f  %.0f km/h  slip %.1f deg  yaw rate %.0f deg/s  steer %.2f"), TestDriveClock, Speed, Slip, YawRate, Steer);
			}
			if (TestDriveClock > 4.75f)
			{
				UE_LOG(LogWSPC2, Log, TEXT("TestDrive: slide at 150 km/h caught with opposite lock: peak sideslip %.1f deg, peak yaw rate %.0f deg/s; after 4.0 s slip %.1f deg, yaw rate %.0f deg/s, %.0f km/h (%s)"),
					TestPeakSlip, TestPeakYawRate, Slip, YawRate, Speed,
					TestPeakSlip > 60.0f ? TEXT("SPUN") : ((AbsSlip < 3.0f && FMath::Abs(YawRate) < 5.0f) ? TEXT("recovered") : TEXT("NOT recovered")));

				TestPlaceCar(Car, 1300.0f);
				TestDrivePhase = 6;
				TestDriveClock = 0.0f;
			}
		}
		else if (TestDrivePhase == 7)
		{
			// full lock and a pull of the handbrake for 0.6 s at 110 km/h to throw the tail out, then a driver
			// catching it: front wheels pointed where the car is going, at once
			const bool bProvoke = TestDriveClock < 0.6f;
			float Steer = 1.0f;
			if (!bProvoke)
			{
				Steer = FMath::Clamp(Slip / FMath::Max(GetDefault<UWSPC2VehicleTuning>()->MaxSteerAngle, 1.0f) * 1.5f, -1.0f, 1.0f);
			}

			if (bProvoke) { Car->DoHandbrakeStart(); } else { Car->DoHandbrakeStop(); }
			Car->DoThrottle(bProvoke ? 0.5f : 0.2f);
			Car->DoSteering(Steer);

			TestPeakSlip = FMath::Max(TestPeakSlip, AbsSlip);
			TestPeakYawRate = FMath::Max(TestPeakYawRate, FMath::Abs(YawRate));

			if (bTrace)
			{
				UE_LOG(LogWSPC2, Log, TEXT("TestTrace: catch t=%.2f  %.0f km/h  slip %.1f deg  yaw rate %.0f deg/s  steer %.2f"), TestDriveClock, Speed, Slip, YawRate, Steer);
			}
			if (TestDriveClock > 5.0f)
			{
				UE_LOG(LogWSPC2, Log, TEXT("TestDrive: handbrake slide at 110 km/h caught with countersteer: peak sideslip %.1f deg, peak yaw rate %.0f deg/s; after 4.4 s slip %.1f deg, yaw rate %.0f deg/s, %.0f km/h (%s)"),
					TestPeakSlip, TestPeakYawRate, Slip, YawRate, Speed,
					TestPeakSlip > 60.0f ? TEXT("SPUN") : ((AbsSlip < 3.0f && FMath::Abs(YawRate) < 5.0f) ? TEXT("recovered") : TEXT("NOT recovered")));

				Car->DoThrottle(0.0f);
				Car->DoSteering(0.0f);
				Car->DoBrake(1.0f);
				TestDrivePhase = 12;
			}
		}
	}
}

void AWSPC2PlayerController::TestPlaceCar(AWSPC2Pawn* Car, float XMetres)
{
	Car->SetActorTransform(FTransform(FRotator::ZeroRotator, FVector(XMetres * 100.0f, 0.0f, 20080.0f)), false, nullptr, ETeleportType::TeleportPhysics);
	Car->GetMesh()->SetPhysicsLinearVelocity(FVector::ZeroVector);
	Car->GetMesh()->SetPhysicsAngularVelocityInDegrees(FVector::ZeroVector);
	Car->DoThrottle(0.0f);
	Car->DoSteering(0.0f);
	Car->DoBrake(0.0f);
}

void AWSPC2PlayerController::TestSlip(const AWSPC2Pawn* Car, float& OutSlipDeg, float& OutYawRate)
{
	const FVector Local = Car->GetActorTransform().InverseTransformVectorNoScale(Car->GetVelocity());
	OutSlipDeg = Local.Size2D() > 300.0f ? FMath::RadiansToDegrees(FMath::Atan2(Local.Y, Local.X)) : 0.0f;
	OutYawRate = Car->GetMesh()->GetPhysicsAngularVelocityInDegrees().Z;
}

void AWSPC2PlayerController::TickTestDamage(float Delta)
{
	AWSPC2Pawn* Car = Cast<AWSPC2Pawn>(GetPawn());
	if (!IsValid(Car) || TestDamagePhase > 99)
	{
		return;
	}

	UWSPC2VehicleDamageComponent* Dmg = Car->GetVehicleDamage();
	if (!Dmg)
	{
		return;
	}

	Car->DisableInput(this);
	TestDamageClock += Delta;

	static int32 PrevHits = 0;

	auto LogDamageSnapshot = [Car, Dmg](const TCHAR* Label)
	{
		UE_LOG(LogWSPC2, Log,
			TEXT("TestDamage [%s]: tier=%s wrecked=%d reason=%s hull=%.1f%% hits=%d prop=$%d flat=%d det=%d bent0=%.2f engIntrus=%.1f%% twist=%.1f/%.1f deg camber0=%.1f drop0=%.1f engFactor=%.2f thrMult=%.2f siren=%.2f steerPull=%.3f primer=%.2f metal=%.2f dent=%.2f glass=%d rimSpark=%d speed=%.1f"),
			Label,
			Dmg->GetDamageStageName(),
			Dmg->IsWrecked() ? 1 : 0,
			Dmg->GetDisableReasonName(),
			Dmg->GetHealthPercent(),
			Dmg->GetCollisionCount(),
			Dmg->GetPropertyDamageDollars(),
			Dmg->GetPuncturedWheelCount(),
			Dmg->GetDetachedWheelCount(),
			Dmg->GetWheelBentAmount(0),
			Dmg->GetEngineBlockIntrusionPct(),
			Dmg->GetMaxChassisTwistDeg(),
			Dmg->GetFloorTouchTwistDeg(),
			Dmg->GetWheelCamberDamageDeg(0),
			Dmg->GetWheelVisualDropCm(0),
			Dmg->GetEngineHealthTorqueFactor(),
			Dmg->GetThrottleDamageMultiplier(),
			Dmg->GetSirenLightHealthFactor(),
			Dmg->GetSteeringPullBias(),
			Dmg->GetCurrentPrimerThreshold(),
			Dmg->GetCurrentMetalThreshold(),
			Dmg->GetCurrentDentStrength(),
			Dmg->GetGlassCrackStage(),
			Dmg->IsRimSparkActive() ? 1 : 0,
			Car->GetSpeedKmh());
	};

	// Phase 0: build elevated strip + concrete barrier at X=230m, settle springs, verify Pristine
	if (TestDamagePhase == 0)
	{
		Car->DoSteering(0.0f);
		Car->DoThrottle(0.0f);
		Car->DoBrake(0.0f);

		if (!bTestDamageStripBuilt && TestDamageClock > 3.0f)
		{
			bTestDamageStripBuilt = true;
			if (UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")))
			{
				AStaticMeshActor* Strip = GetWorld()->SpawnActor<AStaticMeshActor>(FVector(150000.0f, 0.0f, 20000.0f), FRotator::ZeroRotator);
				Strip->SetMobility(EComponentMobility::Movable);
				Strip->GetStaticMeshComponent()->SetStaticMesh(Cube);
				Strip->SetActorScale3D(FVector(3000.0f, 200.0f, 1.0f));

				TestDamageBarrier = GetWorld()->SpawnActor<AStaticMeshActor>(FVector(23000.0f, 0.0f, 20200.0f), FRotator::ZeroRotator);
				TestDamageBarrier->SetMobility(EComponentMobility::Movable);
				TestDamageBarrier->GetStaticMeshComponent()->SetStaticMesh(Cube);
				TestDamageBarrier->GetStaticMeshComponent()->SetCollisionProfileName(TEXT("BlockAll"));
				TestDamageBarrier->GetStaticMeshComponent()->SetNotifyRigidBodyCollision(true);
				TestDamageBarrier->SetActorScale3D(FVector(4.0f, 20.0f, 3.0f));
			}

			TestPlaceCar(Car, 200.0f);
			Car->SetSiren(true);
		}

		if (TestDamageClock > 7.5f)
		{
			LogDamageSnapshot(TEXT("Pristine"));
			PrevHits = Dmg->GetCollisionCount();
			TestPlaceCar(Car, 212.0f);
			TestDamagePhase = 1;
			TestDamageClock = 0.0f;
		}
		return;
	}

	// Phase 1: drive into barrier at ~30 km/h (real Chaos Light impact)
	if (TestDamagePhase == 1)
	{
		const float Speed = Car->GetSpeedKmh();
		Car->DoSteering(0.0f);
		Car->DoBrake(0.0f);
		Car->DoThrottle(Speed < 28.0f ? 0.52f : 0.20f);

		if (Dmg->GetCollisionCount() > PrevHits || TestDamageClock > 9.0f)
		{
			TestDamagePhase = 2;
			TestDamageClock = 0.0f;
		}
		return;
	}

	// Phase 2: settle 0.6s after Light impact, log snapshot, then stage Moderate high-speed crash from X=145m
	if (TestDamagePhase == 2)
	{
		Car->DoThrottle(0.0f);
		Car->DoBrake(1.0f);

		if (TestDamageClock > 0.6f)
		{
			LogDamageSnapshot(TEXT("AfterWallLight"));
			PrevHits = Dmg->GetCollisionCount();
			Car->DoBrake(0.0f);
			TestPlaceCar(Car, 145.0f);
			TestDamagePhase = 3;
			TestDamageClock = 0.0f;
		}
		return;
	}

	// Phase 3: full throttle from X=145m into X=228m barrier (~70+ km/h real Chaos crash)
	if (TestDamagePhase == 3)
	{
		Car->DoSteering(0.0f);
		Car->DoBrake(0.0f);
		Car->DoThrottle(1.0f);

		if (Dmg->GetCollisionCount() > PrevHits || TestDamageClock > 12.0f)
		{
			TestDamagePhase = 4;
			TestDamageClock = 0.0f;
		}
		return;
	}

	// Phase 4: settle after Moderate barrier crash, log it, move barrier aside, then apply Heavy front-left corner blowout
	if (TestDamagePhase == 4)
	{
		Car->DoThrottle(0.0f);
		Car->DoBrake(1.0f);

		if (TestDamageClock > 0.7f)
		{
			LogDamageSnapshot(TEXT("AfterWallModerate"));

			if (IsValid(TestDamageBarrier))
			{
				TestDamageBarrier->SetActorLocation(FVector(23000.0f, 50000.0f, 20200.0f));
			}

			Car->DoBrake(0.0f);
			TestPlaceCar(Car, 100.0f);

			const FVector FLWorld = Car->GetActorTransform().TransformPosition(FVector(148.0f, -86.0f, 34.0f));
			const FVector FLNormal = (-Car->GetActorForwardVector() + Car->GetActorRightVector() * 0.45f).GetSafeNormal();
			Dmg->ApplyDirectImpact(FLWorld, FLNormal, 88.0f, 3100000.0f);

			LogDamageSnapshot(TEXT("AfterHeavyCornerBlowout"));
			TestDamagePhase = 5;
			TestDamageClock = 0.0f;
		}
		return;
	}

	// Phase 5: accelerate for 2.5s on punctured front-left rim (verify rim sparks, misfire, pull, slower accel)
	if (TestDamagePhase == 5)
	{
		Car->DoSteering(0.0f);
		Car->DoBrake(0.0f);
		Car->DoThrottle(1.0f);

		if (TestDamageClock > 2.5f)
		{
			LogDamageSnapshot(TEXT("HeavyDrivingRimSpark"));
			Car->DoThrottle(0.0f);
			Car->DoBrake(1.0f);
			TestDamagePhase = 6;
			TestDamageClock = 0.0f;
		}
		return;
	}

	// Phase 6: Test Rule 2 — Bent wheel & loss of 2 wheels disables vehicle, and stall check
	if (TestDamagePhase == 6)
	{
		if (TestDamageClock > 0.4f && TestDamageClock - Delta <= 0.4f)
		{
			Dmg->RepairAll();
			TestPlaceCar(Car, 100.0f);

			const FVector FLWorld = Car->GetActorTransform().TransformPosition(FVector(142.0f, -78.0f, 35.0f));
			const FVector FRWorld = Car->GetActorTransform().TransformPosition(FVector(142.0f, 78.0f, 35.0f));
			Dmg->ApplyDirectImpact(FLWorld, -Car->GetActorRightVector(), 62.0f, 2200000.0f);
			LogDamageSnapshot(TEXT("BentWheelFL"));

			for (int32 Retry = 0; Retry < 2 && !Dmg->IsWheelDetached(0); ++Retry)
			{
				Dmg->ApplyDirectImpact(FLWorld, -Car->GetActorRightVector(), 122.0f, 4600000.0f);
			}
			for (int32 Retry = 0; Retry < 2 && !Dmg->IsWheelDetached(1); ++Retry)
			{
				Dmg->ApplyDirectImpact(FRWorld, Car->GetActorRightVector(), 122.0f, 4600000.0f);
			}
			LogDamageSnapshot(TEXT("Rule2_TwoWheelsLost"));
		}

		Car->DoBrake(0.0f);
		Car->DoSteering(0.0f);
		Car->DoThrottle(TestDamageClock > 0.5f ? 1.0f : 0.0f);

		if (TestDamageClock > 1.8f)
		{
			LogDamageSnapshot(TEXT("Rule2_StallThrottleHold"));
			Car->DoThrottle(0.0f);
			TestDamagePhase = 7;
			TestDamageClock = 0.0f;
		}
		return;
	}

	// Phase 7: Test Rule 1 — Engine block intrusion > 30% disables vehicle
	if (TestDamagePhase == 7)
	{
		if (TestDamageClock > 0.3f && TestDamageClock - Delta <= 0.3f)
		{
			Dmg->RepairAll();
			TestPlaceCar(Car, 100.0f);

			const FVector FrontBumper = Car->GetActorTransform().TransformPosition(FVector(215.0f, 0.0f, 55.0f));
			for (int32 Strike = 0; Strike < 4 && !Dmg->IsWrecked(); ++Strike)
			{
				Dmg->ApplyDirectImpact(FrontBumper, -Car->GetActorForwardVector(), 108.0f, 3900000.0f);
			}
			LogDamageSnapshot(TEXT("Rule1_EngineIntrusion"));
		}

		Car->DoBrake(0.0f);
		Car->DoSteering(0.0f);
		Car->DoThrottle(TestDamageClock > 0.4f ? 1.0f : 0.0f);

		if (TestDamageClock > 1.7f)
		{
			LogDamageSnapshot(TEXT("Rule1_StallThrottleHold"));
			Car->DoThrottle(0.0f);
			TestDamagePhase = 8;
			TestDamageClock = 0.0f;
		}
		return;
	}

	// Phase 8: Test Rule 3 — Chassis torsion/twist > FloorTouchTwistDeg disables vehicle, then verify full RepairAll()
	if (TestDamagePhase == 8)
	{
		if (TestDamageClock > 0.3f && TestDamageClock - Delta <= 0.3f)
		{
			Dmg->RepairAll();
			TestPlaceCar(Car, 100.0f);

			const FVector SideRoofHit = Car->GetActorTransform().TransformPosition(FVector(15.0f, -86.0f, 118.0f));
			const FVector RoofHit = Car->GetActorTransform().TransformPosition(FVector(-12.0f, 0.0f, 138.0f));
			for (int32 Strike = 0; Strike < 5 && !Dmg->IsWrecked(); ++Strike)
			{
				Dmg->ApplyDirectImpact(SideRoofHit, (Car->GetActorRightVector() - Car->GetActorUpVector() * 0.5f).GetSafeNormal(), 105.0f, 3700000.0f);
				if (!Dmg->IsWrecked())
				{
					Dmg->ApplyDirectImpact(RoofHit, -Car->GetActorUpVector(), 95.0f, 3500000.0f);
				}
			}
			LogDamageSnapshot(TEXT("Rule3_ChassisTwisted"));
		}

		Car->DoBrake(0.0f);
		Car->DoSteering(0.0f);
		Car->DoThrottle(TestDamageClock > 0.4f ? 1.0f : 0.0f);

		if (TestDamageClock > 1.7f)
		{
			LogDamageSnapshot(TEXT("Rule3_StallThrottleHold"));
			Car->DoThrottle(0.0f);
			Car->DoResetVehicle();
			TestPlaceCar(Car, 100.0f);
			TestDamagePhase = 9;
			TestDamageClock = 0.0f;
		}
		return;
	}

	// Phase 9: wait 0.4s after RepairAll/DoResetVehicle, log Pristine restoration, then accelerate 2.2s to verify Chaos torque recovery
	if (TestDamagePhase == 9)
	{
		Car->DoBrake(0.0f);
		Car->DoSteering(0.0f);
		Car->DoThrottle(TestDamageClock > 0.4f ? 1.0f : 0.0f);

		if (TestDamageClock > 0.4f && TestDamageClock - Delta <= 0.4f)
		{
			LogDamageSnapshot(TEXT("AfterRepair"));
		}

		if (TestDamageClock > 2.6f)
		{
			LogDamageSnapshot(TEXT("PostRepairDriveCheck"));
			UE_LOG(LogWSPC2, Log, TEXT("TestDamage: COMPLETE"));
			TestDamagePhase = 100;
			FPlatformMisc::RequestExit(false);
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
	else if (AWSPC2Pawn* Car = Cast<AWSPC2Pawn>(GetPawn()))
	{
		// driving: the mouse turns the chase camera around the car (up = camera lower, looking up)
		const FVector2D Delta = Value.Get<FVector2D>();
		Car->AddChaseLook(FVector2D(Delta.X, -Delta.Y) * GunnerMouseSensitivity);
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
	else if (AWSPC2Pawn* Car = Cast<AWSPC2Pawn>(GetPawn()))
	{
		// driving: the right stick turns the chase camera all the way around the car
		const FVector2D Stick = Value.Get<FVector2D>();
		const float Step = GetDefault<UWSPC2VehicleTuning>()->ChaseOrbitStickRate * GetWorld()->GetDeltaSeconds();
		Car->AddChaseLook(FVector2D(Stick.X, -Stick.Y) * Step);
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

void AWSPC2PlayerController::ServerSetVehiclePreset_Implementation(FName PresetId)
{
	if (AWSPC2SportsCar* SportsCar = Cast<AWSPC2SportsCar>(GetCurrentVehicle()))
	{
		if (SportsCar->SetVehiclePreset(PresetId))
		{
			ClientNotify(FString::Printf(TEXT("Vehicle: %s"), *SportsCar->GetActiveVehicleDisplayName()));
		}
		else
		{
			ClientNotify(FString::Printf(TEXT("Vehicle preset unavailable: %s"), *PresetId.ToString()));
		}
	}
}

void AWSPC2PlayerController::ServerCycleVehiclePreset_Implementation()
{
	if (AWSPC2SportsCar* SportsCar = Cast<AWSPC2SportsCar>(GetCurrentVehicle()))
	{
		SportsCar->CycleVehiclePreset();
		const UWSPC2VehicleAudioComponent* Audio = SportsCar->GetVehicleAudio();
		ClientNotify(FString::Printf(TEXT("Vehicle: %s [%s | %s]"),
			*SportsCar->GetActiveVehicleDisplayName(),
			*SportsCar->GetActiveRoleGroup(),
			Audio ? *Audio->GetActiveEngineFamilyName() : *SportsCar->GetActiveAudioProfile()));
	}
}

void AWSPC2PlayerController::ServerCycleVehicleDirection_Implementation(int32 Direction)
{
	if (AWSPC2SportsCar* SportsCar = Cast<AWSPC2SportsCar>(GetCurrentVehicle()))
	{
		SportsCar->CycleVehiclePresetDirection(Direction >= 0 ? 1 : -1);
		const UWSPC2VehicleAudioComponent* Audio = SportsCar->GetVehicleAudio();
		ClientNotify(FString::Printf(TEXT("Vehicle: %s [%s | %s]"),
			*SportsCar->GetActiveVehicleDisplayName(),
			*SportsCar->GetActiveRoleGroup(),
			Audio ? *Audio->GetActiveEngineFamilyName() : *SportsCar->GetActiveAudioProfile()));
	}
}

void AWSPC2PlayerController::ServerCycleVehicleCategory_Implementation()
{
	if (AWSPC2SportsCar* SportsCar = Cast<AWSPC2SportsCar>(GetCurrentVehicle()))
	{
		SportsCar->CycleVehicleCategory();
		const UWSPC2VehicleAudioComponent* Audio = SportsCar->GetVehicleAudio();
		ClientNotify(FString::Printf(TEXT("Category %s -> %s [%s]"),
			*SportsCar->GetActiveRoleGroup(),
			*SportsCar->GetActiveVehicleDisplayName(),
			Audio ? *Audio->GetActiveEngineFamilyName() : *SportsCar->GetActiveAudioProfile()));
	}
}

void AWSPC2PlayerController::ServerCycleSirenMode_Implementation()
{
	if (AWSPC2Pawn* Car = GetCurrentVehicle())
	{
		Car->CycleSirenMode();
		ClientNotify(FString::Printf(TEXT("Sirene: %s"), Car->GetSirenModeName()));
	}
}

void AWSPC2PlayerController::ServerTriggerAirhorn_Implementation()
{
	if (AWSPC2Pawn* Car = GetCurrentVehicle())
	{
		Car->TriggerAirhorn();
	}
}

void AWSPC2PlayerController::ServerRepairCurrentVehicle_Implementation()
{
	if (AWSPC2Pawn* Car = GetCurrentVehicle())
	{
		if (UWSPC2VehicleDamageComponent* Damage = Car->GetVehicleDamage())
		{
			Damage->RepairAll();
			ClientNotify(TEXT("Veiculo reparado!"));
		}
	}
}

void AWSPC2PlayerController::ServerSwapNearestShowroom_Implementation()
{
	AWSPC2SportsCar* SportsCar = Cast<AWSPC2SportsCar>(GetCurrentVehicle());
	AWSPC2TestTrackDirector* Director = AWSPC2TestTrackDirector::Get(GetWorld());
	if (!SportsCar || !Director)
	{
		return;
	}

	FName NearestPresetId = NAME_None;
	FString NearestDisplayName;
	if (Director->FindNearestShowroomPreset(SportsCar->GetActorLocation(), 1000.0f, NearestPresetId, NearestDisplayName))
	{
		if (SportsCar->SetVehiclePreset(NearestPresetId))
		{
			const UWSPC2VehicleAudioComponent* Audio = SportsCar->GetVehicleAudio();
			ClientNotify(FString::Printf(TEXT("Showroom -> %s [%s | %s]"),
				*SportsCar->GetActiveVehicleDisplayName(),
				*SportsCar->GetActiveRoleGroup(),
				Audio ? *Audio->GetActiveEngineFamilyName() : *SportsCar->GetActiveAudioProfile()));
		}
		else
		{
			ClientNotify(FString::Printf(TEXT("Preset indisponivel no momento: %s"), *NearestPresetId.ToString()));
		}
	}
	else
	{
		ClientNotify(TEXT("Aproxime-se de uma vaga do Showroom (<=10m) e aperte [Enter]"));
	}
}

void AWSPC2PlayerController::UpdateHiddenComponents(const FVector& ViewLocation, TSet<FPrimitiveComponentId>& HiddenComponents)
{
	Super::UpdateHiddenComponents(ViewLocation, HiddenComponents);

	// only while this player looks through his own pawn's camera (not a spectator or test camera)
	if (GetViewTarget() != GetPawn())
	{
		return;
	}

	if (const AWSPC2SportsCar* Car = Cast<AWSPC2SportsCar>(GetPawn()))
	{
		if (Car->IsCabinViewActive())
		{
			Car->AddCrewToHiddenList(AWSPC2SportsCar::CrewDriver, HiddenComponents);
		}
	}
	else if (const AWSPC2GunnerPawn* Gunner = Cast<AWSPC2GunnerPawn>(GetPawn()))
	{
		const AWSPC2SportsCar* GunnerCar = Cast<AWSPC2SportsCar>(Gunner->GetVehicle());
		if (GunnerCar && !Gunner->IsThirdPerson())
		{
			GunnerCar->AddCrewToHiddenList(AWSPC2SportsCar::CrewGunner, HiddenComponents);
		}
	}
}

void AWSPC2PlayerController::TickTestGunnery(float Delta)
{
	AWSPC2Pawn* Car = Cast<AWSPC2Pawn>(GetPawn());
	UWSPC2GunneryComponent* Gun = IsValid(Car) ? Car->GetGunnery() : nullptr;
	if (!Gun || TestGunPhase > 99)
	{
		return;
	}

	TestGunClock += Delta;
	auto Report = [&](const TCHAR* Step)
	{
		const UWSPC2VehicleDamageComponent* Damage = IsValid(TestGunTarget) ? TestGunTarget->FindComponentByClass<UWSPC2VehicleDamageComponent>() : nullptr;
		UE_LOG(LogWSPC2, Log, TEXT("TestGunnery %s: %s | shots %d hits %d | target health %.1f%% flat %d | retracted %d"), Step, *Gun->GetStatusText(),
			Gun->GetShotsFired(), Gun->GetShotsHit(), Damage ? Damage->GetHealthPercent() : -1.0f, Damage ? Damage->GetPuncturedWheelCount() : -1,
			Gun->IsRetracted() ? 1 : 0);
	};
	auto Pulse = [&](float Every, int32 Count, int32 NextPhase, const TCHAR* Step)
	{
		// press and release the trigger Count times, one press every Every seconds
		if (TestGunClock >= Every * 0.5f && TestGunPulses % 2 == 0 && TestGunPulses < Count * 2)
		{
			Gun->SetTrigger(true);
			++TestGunPulses;
		}
		else if (TestGunClock >= Every && TestGunPulses % 2 == 1)
		{
			Gun->SetTrigger(false);
			++TestGunPulses;
			TestGunClock = 0.0f;
		}
		if (TestGunPulses >= Count * 2 && TestGunClock > 1.0f)
		{
			Report(Step);
			TestGunPulses = 0;
			TestGunClock = 0.0f;
			TestGunPhase = NextPhase;
		}
	};

	switch (TestGunPhase)
	{
	case 0:
		if (TestGunClock > 3.0f)
		{
			// a second car parked 25 m ahead and 5 m to the right, nose to the right
			FActorSpawnParameters Params;
			Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
			const FTransform At(Car->GetActorRotation() + FRotator(0.0f, 90.0f, 0.0f), Car->GetActorTransform().TransformPosition(FVector(2500.0f, 500.0f, 60.0f)));
			TestGunTarget = GetWorld()->SpawnActor<AActor>(Car->GetClass(), At, Params);
			UE_LOG(LogWSPC2, Log, TEXT("TestGunnery: target %s"), TestGunTarget ? *TestGunTarget->GetName() : TEXT("NOT SPAWNED"));
			TestGunPhase = 1;
			TestGunClock = 0.0f;
		}
		break;
	case 1:
		if (TestGunClock > 3.0f)
		{
			Gun->CycleWeapon(1);
			TestGunPhase = 2;
			TestGunClock = 0.0f;
		}
		break;
	case 2:
		if (TestGunClock > 1.0f && PlayerCameraManager)
		{
			Gun->ToggleLock(PlayerCameraManager->GetCameraLocation(), PlayerCameraManager->GetCameraRotation().Vector());
			UE_LOG(LogWSPC2, Log, TEXT("TestGunnery lock: %s (wanted %s)"), Gun->GetLockedTarget() ? *Gun->GetLockedTarget()->GetName() : TEXT("none"),
				IsValid(TestGunTarget) ? *TestGunTarget->GetName() : TEXT("-"));
			TestGunPhase = 3;
			TestGunClock = 0.0f;
		}
		break;
	case 3:
		Pulse(0.5f, 6, 4, TEXT("pistol x6"));
		break;
	case 4:
		Gun->CycleWeapon(1);
		TestGunPhase = 5;
		TestGunClock = -1.0f;
		break;
	case 5:
		if (TestGunClock >= 0.0f)
		{
			Pulse(1.2f, 3, 6, TEXT("shotgun x3"));
		}
		break;
	case 6:
		Gun->CycleWeapon(1);
		TestGunPhase = 7;
		TestGunClock = -1.0f;
		break;
	case 7:
		if (TestGunClock >= 0.0f && TestGunPulses == 0)
		{
			Gun->SetTrigger(true);
			TestGunPulses = 1;
		}
		if (TestGunClock >= 2.0f)
		{
			Gun->SetTrigger(false);
			TestGunPulses = 0;
			TestGunClock = -1.0f;
			Report(TEXT("rifle 2 s held"));
			TestGunPhase = 8;
		}
		break;
	case 8:
		if (TestGunClock >= 0.0f)
		{
			Gun->CycleWeapon(1);
			Report(TEXT("holstered"));
			UE_LOG(LogWSPC2, Log, TEXT("TestGunnery: COMPLETE"));
			TestGunPhase = 100;
			FPlatformMisc::RequestExit(false);
		}
		break;
	default:
		break;
	}
}

void AWSPC2PlayerController::TickTestFleet(float Delta)
{
	AWSPC2SportsCar* Car = Cast<AWSPC2SportsCar>(GetPawn());
	if (!IsValid(Car) || TestFleetSubPhase > 99)
	{
		return;
	}

	const TArray<FWSPC2VehicleProfileSpec>& Presets = UWSPC2VehicleProfile::GetBuiltinPresets();
	Car->DisableInput(this);
	TestFleetClock += Delta;

	if (!bTestFleetStripBuilt)
	{
		if (TestFleetClock > 2.0f)
		{
			bTestFleetStripBuilt = true;
			if (UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube")))
			{
				AStaticMeshActor* Strip = GetWorld()->SpawnActor<AStaticMeshActor>(FVector(150000.0f, 0.0f, 20000.0f), FRotator::ZeroRotator);
				Strip->SetMobility(EComponentMobility::Movable);
				Strip->GetStaticMeshComponent()->SetStaticMesh(Cube);
				Strip->SetActorScale3D(FVector(3000.0f, 200.0f, 1.0f));
			}
			TestPlaceCar(Car, 100.0f);
			TestFleetIndex = 0;
			TestFleetSubPhase = 0;
			TestFleetClock = 0.0f;
		}
		return;
	}

	if (!Presets.IsValidIndex(TestFleetIndex))
	{
		UE_LOG(LogWSPC2, Log, TEXT("TestFleet: COMPLETE (%d presets verified)"), Presets.Num());
		TestFleetSubPhase = 100;
		FPlatformMisc::RequestExit(false);
		return;
	}

	const FWSPC2VehicleProfileSpec& Spec = Presets[TestFleetIndex];

	if (TestFleetSubPhase == 0)
	{
		const bool bOk = Car->SetVehiclePreset(Spec.PresetId);
		TestPlaceCar(Car, 100.0f);
		if (!bOk)
		{
			UE_LOG(LogWSPC2, Warning, TEXT("TestFleet [%s]: SKIPPED (assets unavailable)"), *Spec.PresetId.ToString());
			++TestFleetIndex;
			TestFleetClock = 0.0f;
			return;
		}
		Car->SetSiren(true);
		TestFleetSubPhase = 1;
		TestFleetClock = 0.0f;
		return;
	}

	if (TestFleetSubPhase == 1)
	{
		Car->DoSteering(0.0f);
		Car->DoBrake(0.0f);
		Car->DoThrottle(TestFleetClock > 0.6f ? 1.0f : 0.0f);

		if (TestFleetClock > 2.6f)
		{
			const float SpeedKmh = Car->GetSpeedKmh();
			UWSPC2VehicleDamageComponent* Dmg = Car->GetVehicleDamage();
			if (Dmg)
			{
				const FVector FrontWorld = Car->GetActorTransform().TransformPosition(FVector(210.0f, 0.0f, 55.0f));
				Dmg->ApplyDirectImpact(FrontWorld, -Car->GetActorForwardVector(), 68.0f, 2200000.0f);
			}

			UChaosWheeledVehicleMovementComponent* Movement = Car->GetChaosVehicleMovement();
			const float WheelR0 = (Movement && Movement->Wheels.IsValidIndex(0) && Movement->Wheels[0]) ? Movement->Wheels[0]->GetWheelRadius() : 0.0f;
			const bool bInContact0 = (Movement && Movement->GetNumWheels() > 0) ? Movement->GetWheelState(0).bInContact : false;
			const float Susp0 = (Movement && Movement->Wheels.IsValidIndex(0) && Movement->Wheels[0]) ? Movement->Wheels[0]->GetSuspensionOffset() : 0.0f;
			const FVector Pos = Car->GetActorLocation();
			const bool bAwake = Car->GetMesh() && Car->GetMesh()->IsAnyRigidBodyAwake();
			UE_LOG(LogWSPC2, Log,
				TEXT("TestFleet [%s]: name='%s' mass=%.0f kg wheelR=%.1f cm speed2s=%.1f km/h pos=(%.1f,%.1f,%.1f) gear=%d rpm=%.0f thr=%.2f hb=%d awake=%d contact0=%d susp0=%.1f grounded=%d dmgHull=%.1f%% glass=%d primer=%.2f"),
				*Spec.PresetId.ToString(),
				*Car->GetActiveVehicleDisplayName(),
				Car->GetMesh() ? Car->GetMesh()->GetMass() : 0.0f,
				WheelR0,
				SpeedKmh,
				Pos.X * 0.01f, Pos.Y * 0.01f, Pos.Z,
				Movement ? Movement->GetCurrentGear() : -99,
				Movement ? Movement->GetEngineRotationSpeed() : 0.0f,
				Movement ? Movement->GetThrottleInput() : 0.0f,
				(Movement && Movement->GetHandbrakeInput()) ? 1 : 0,
				bAwake ? 1 : 0,
				bInContact0 ? 1 : 0,
				Susp0,
				(Movement && Movement->IsMovingOnGround()) ? 1 : 0,
				Dmg ? Dmg->GetHealthPercent() : 100.0f,
				Dmg ? Dmg->GetGlassCrackStage() : 0,
				Dmg ? Dmg->GetCurrentPrimerThreshold() : 0.8f);

			++TestFleetIndex;
			TestFleetSubPhase = 0;
			TestFleetClock = 0.0f;
		}
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
		FVector(-22000.0f, -16000.0f, 16000.0f),	// district, from the air
		FVector(-70000.0f, 50000.0f, 60000.0f),		// whole city, from far and high
		FVector(-2500.0f, 0.0f, 900.0f),		// down the street
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

void AWSPC2PlayerController::SetVehicle(const FString& PresetName)
{
	if (!PresetName.IsEmpty())
	{
		ServerSetVehiclePreset(FName(*PresetName));
	}
}

void AWSPC2PlayerController::NextVehicle()
{
	ServerCycleVehiclePreset();
}

void AWSPC2PlayerController::PrevVehicle()
{
	ServerCycleVehicleDirection(-1);
}

void AWSPC2PlayerController::NextCategory()
{
	ServerCycleVehicleCategory();
}

void AWSPC2PlayerController::SirenMode()
{
	ServerCycleSirenMode();
}

void AWSPC2PlayerController::Airhorn()
{
	ServerTriggerAirhorn();
}

void AWSPC2PlayerController::RepairCar()
{
	ServerRepairCurrentVehicle();
}

void AWSPC2PlayerController::ListVehicles()
{
	const TArray<FWSPC2VehicleProfileSpec>& All = UWSPC2VehicleProfile::GetBuiltinPresets();
	int32 Loadable = 0;
	for (const FWSPC2VehicleProfileSpec& Spec : All)
	{
		const bool bOk = UWSPC2VehicleProfile::CanLoadPresetAssets(Spec);
		if (bOk)
		{
			++Loadable;
		}
		UE_LOG(LogWSPC2, Log, TEXT("Preset [%s] %-28s | %-34s | %4.0f HP | %4.0f Nm | Audio=%-18s | Loadable=%s"),
			*UWSPC2VehicleProfile::GetNormalizedRoleGroup(Spec),
			*Spec.PresetId.ToString(),
			*Spec.DisplayName.ToString(),
			Spec.RealHorsepower,
			Spec.RealMaxTorqueNm,
			*Spec.AudioProfile,
			bOk ? TEXT("YES") : TEXT("no"));
	}
	ClientNotify(FString::Printf(TEXT("Catalog: %d loadable / %d total presets (ver LogWSPC2)"), Loadable, All.Num()));
}

void AWSPC2PlayerController::DamageDemo()
{
	AWSPC2Pawn* Car = GetCurrentVehicle();
	if (!Car)
	{
		return;
	}
	if (UWSPC2VehicleDamageComponent* Damage = Car->GetVehicleDamage())
	{
		const FVector HitPt = Car->GetActorLocation() + Car->GetActorForwardVector() * 170.0f + Car->GetActorUpVector() * 65.0f;
		Damage->ApplyDirectImpact(HitPt, -Car->GetActorForwardVector(), 130.0f, 2200000.0f);
		Damage->PunctureWheel(0);
		ClientNotify(FString::Printf(TEXT("DamageDemo: Hull %.0f%% | EngIntr %.1f%% | Twist %.1f deg"),
			Damage->GetHealthPercent(),
			Damage->GetEngineBlockIntrusionPct(),
			Damage->GetMaxChassisTwistDeg()));
	}
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

	if (bTestGround)
	{
		TickTestGround(Delta);
	}

	if (bTestDamage)
	{
		TickTestDamage(Delta);
	}

	if (bTestGunnery)
	{
		TickTestGunnery(Delta);
	}

	if (bTestFleet)
	{
		TickTestFleet(Delta);
	}

	if (bTestTrackAudit)
	{
		TickTestTrackAudit(Delta);
	}

	// -WSPC2TestSteerShot: parked, close-ups of the front left wheel, then quit. Checks that brakes and wheels steer
	// together: Outside and Inner at full left lock, then InnerStraight with the wheel straight
	// (Saved/Screenshots/SteerShot_<name>.png). Inner looks at the back of the wheel from under the front of the car.
	static const bool bSteerShot = IsLocalPlayerController() && FParse::Param(FCommandLine::Get(), TEXT("WSPC2TestSteerShot"));
	if (bSteerShot)
	{
		static float Clock = 0.0f;
		Clock += Delta;

		if (AWSPC2Pawn* Car = GetCurrentVehicle())
		{
			static const FVector Offsets[3] = { FVector(170.0f, -260.0f, 60.0f), FVector(250.0f, 5.0f, 12.0f), FVector(250.0f, 5.0f, 12.0f) };
			static const TCHAR* Names[3] = { TEXT("Outside"), TEXT("Inner"), TEXT("InnerStraight") };
			static int32 Shot = 0;

			// full lock for the first two shots, straight for the last (time for the wheels to come back)
			Car->DoSteering(Clock < 6.2f ? -1.0f : 0.0f);

			if (Shot < 3 && Clock > 4.0f + Shot * 1.5f + (Shot == 2 ? 2.0f : 0.0f))
			{
				if (!IsValid(TestCamera))
				{
					TestCamera = GetWorld()->SpawnActor<ACameraActor>();
				}
				const FVector Hub = Car->GetActorTransform().TransformPosition(FVector(152.0f, -78.0f, 34.0f));
				const FVector Eye = Car->GetActorTransform().TransformPosition(Offsets[Shot]);
				TestCamera->SetActorLocationAndRotation(Eye, (Hub - Eye).Rotation());
				SetViewTarget(TestCamera);

				const int32 Index = Shot++;
				GetWorld()->GetTimerManager().SetTimerForNextTick([this, Index]()
				{
					FScreenshotRequest::RequestScreenshot(FPaths::ProjectSavedDir() / TEXT("Screenshots") / FString::Printf(TEXT("SteerShot_%s.png"), Names[Index]), false, false);
				});
			}
			if (Clock > 10.5f)
			{
				ConsoleCommand(TEXT("quit"));
			}
		}
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
		const UWSPC2VehicleDamageComponent* Dmg = IsValid(Car) ? Car->GetVehicleDamage() : nullptr;
		const UWSPC2VehicleAudioComponent* Aud = IsValid(Car) ? Car->GetVehicleAudio() : nullptr;
		const UChaosWheeledVehicleMovementComponent* Move = IsValid(Car) ? Car->GetChaosVehicleMovement() : nullptr;

		const float HullPct = Dmg ? Dmg->GetHealthPercent() : 100.0f;
		const TCHAR* StageName = Dmg ? Dmg->GetDamageStageName() : TEXT("Pristine");
		const int32 FlatTyres = Dmg ? Dmg->GetPuncturedWheelCount() : 0;
		const int32 WheelsLost = Dmg ? Dmg->GetDetachedWheelCount() : 0;
		const float EngIntrPct = Dmg ? Dmg->GetEngineBlockIntrusionPct() : 0.0f;
		const float TwistDeg = Dmg ? Dmg->GetMaxChassisTwistDeg() : 0.0f;
		const float TwistMaxDeg = Dmg ? Dmg->GetFloorTouchTwistDeg() : 10.5f;

		const FString CarName = IsValid(Car) ? Car->GetActiveVehicleDisplayName() : FString(TEXT("None"));
		const FString RoleGroup = IsValid(Car) ? Car->GetActiveRoleGroup() : FString(TEXT("-"));
		const FString AudioFam = Aud ? Aud->GetActiveEngineFamilyName() : (IsValid(Car) ? Car->GetActiveAudioProfile() : FString(TEXT("-")));
		const int32 Gear = Move ? Move->GetCurrentGear() : 0;
		const float Rpm = Move ? Move->GetEngineRotationSpeed() : 0.0f;
		const TCHAR* SirenName = IsValid(Car) ? Car->GetSirenModeName() : TEXT("Off");

		const int32 LoosePanels = Dmg ? Dmg->GetLoosePanelCount() : 0;
		const int32 DetachedPanels = Dmg ? Dmg->GetDetachedPanelCount() : 0;
		const int32 BrokenLights = Dmg ? Dmg->GetBrokenLightCount() : 0;
		const float MaxDentCm = Dmg ? Dmg->GetMaxVertexDisplacementCm() : 0.0f;

		const FString Status = FString::Printf(
			TEXT("%s [%s | %s]  |  %s  |  G%d %.0f RPM  |  %3.0f km/h  |  Siren %s  |  Hull %3.0f%% [%s]  |  EngIntr %.1f%%/30%%  |  Wheels %d/2  |  Panels %d/%d  |  Lights %d/4  |  Dent %.0fcm  |  Twist %.1f/%.1f deg"),
			*CarName,
			*RoleGroup,
			*AudioFam,
			SeatName,
			Gear,
			Rpm,
			IsValid(Car) ? Car->GetSpeedKmh() : 0.0f,
			SirenName,
			HullPct,
			StageName,
			EngIntrPct,
			WheelsLost,
			LoosePanels,
			DetachedPanels,
			BrokenLights,
			MaxDentCm,
			TwistDeg,
			TwistMaxDeg);

		const FColor StatusColor = (Dmg && Dmg->IsWrecked()) ? FColor::Red
			: (HullPct < 55.0f ? FColor::Orange : (HullPct < 85.0f ? FColor::Yellow : FColor::White));
		GEngine->AddOnScreenDebugMessage(static_cast<uint64>(GetUniqueID()), 0.0f, StatusColor, Status);

		const FString KeyHints = TEXT("[V/B] car  [N] cat  [Enter] showroom  [H] siren  [J] mode  [K] airhorn  [C] cam  [F] seat  [R] reset");
		GEngine->AddOnScreenDebugMessage(static_cast<uint64>(GetUniqueID()) + 7300, 0.0f, FColor(180, 215, 255), KeyHints);

		if (IsValid(Car))
		{
			if (const AWSPC2TestTrackDirector* TrackDirector = AWSPC2TestTrackDirector::Get(GetWorld()))
			{
				FName NearId = NAME_None;
				FString NearName;
				if (TrackDirector->FindNearestShowroomPreset(Car->GetActorLocation(), 1000.0f, NearId, NearName))
				{
					const FString Prompt = FString::Printf(TEXT("[Enter] Dirigir: %s (%s)"), *NearName, *NearId.ToString());
					GEngine->AddOnScreenDebugMessage(static_cast<uint64>(GetUniqueID()) + 7310, 0.0f, FColor::Green, Prompt, true, FVector2D(1.3f, 1.3f));
				}
			}
		}

		// the mission under way
		DirectorLookupAge += Delta;
		if (!CachedDirector.IsValid() && DirectorLookupAge > 2.0f)
		{
			DirectorLookupAge = 0.0f;
			CachedDirector = AWSPC2MissionDirector::Get(GetWorld(), false);
		}
		if (const AWSPC2MissionDirector* Director = CachedDirector.Get())
		{
			if (Director->GetState() != EWSPC2MissionState::Idle)
			{
				const FColor MissionColor = Director->GetState() == EWSPC2MissionState::Won ? FColor::Green
					: Director->GetState() == EWSPC2MissionState::Failed ? FColor::Red : FColor::Orange;
				GEngine->AddOnScreenDebugMessage(static_cast<uint64>(GetUniqueID()) + 7200, 0.0f, MissionColor, Director->GetStatusLine(), true, FVector2D(1.4f, 1.4f));
			}
		}

		// the gun, for whoever handles it: weapon, rounds, lock, and the keys
		const AWSPC2Pawn* Vehicle = GetCurrentVehicle();
		if (Vehicle && Vehicle->GetGunnery() && HoldsTheGun())
		{
			const bool bAlone = Cast<AWSPC2Pawn>(GetPawn()) != nullptr;
			const FString Gun = Vehicle->GetGunnery()->GetStatusText() + (bAlone ? TEXT("  |  [Q/E, D-pad <>] arma  [T, D-pad ^] travar  [G, RB] atirar")
				: TEXT("  |  [Q/E, D-pad <>] arma  [RT, G] atirar"));
			GEngine->AddOnScreenDebugMessage(static_cast<uint64>(GetUniqueID()) + 7100, 0.0f, FColor::Cyan, Gun);
		}
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

void AWSPC2PlayerController::TickTestTrackAudit(float Delta)
{
	TestTrackAuditClock += Delta;

	AWSPC2TestTrackDirector* Director = AWSPC2TestTrackDirector::Get(GetWorld());
	AWSPC2SportsCar* SportsCar = Cast<AWSPC2SportsCar>(GetCurrentVehicle());
	if (!Director || !SportsCar)
	{
		if (TestTrackAuditClock > 25.0f)
		{
			UE_LOG(LogWSPC2, Error, TEXT("TestTrackAudit: missing Director=%s or PlayerSportsCar=%s"),
				Director ? TEXT("ok") : TEXT("NULL"), SportsCar ? TEXT("ok") : TEXT("NULL"));
			UE_LOG(LogWSPC2, Log, TEXT("TestTrackAudit: COMPLETE (PASS=false, Showroom=0, Traffic=0/0, Arena=0, RealAudio=false)"));
			ConsoleCommand(TEXT("quit"));
		}
		return;
	}

	SportsCar->DisableInput(this);

	auto TeleportCar = [](AWSPC2SportsCar* CarToMove, const FVector& WorldLoc, const FRotator& WorldRot)
	{
		if (!CarToMove)
		{
			return;
		}
		CarToMove->SetActorTransform(FTransform(WorldRot, WorldLoc), false, nullptr, ETeleportType::TeleportPhysics);
		if (UPrimitiveComponent* RootMesh = CarToMove->GetMesh())
		{
			RootMesh->SetPhysicsLinearVelocity(FVector::ZeroVector);
			RootMesh->SetPhysicsAngularVelocityInDegrees(FVector::ZeroVector);
			RootMesh->WakeAllRigidBodies();
		}
		CarToMove->DoThrottle(0.0f);
		CarToMove->DoSteering(0.0f);
		CarToMove->DoBrake(0.0f);
	};

	auto AimTestCam = [this](const FVector& Eye, const FVector& LookAt)
	{
		if (!IsValid(TestCamera))
		{
			TestCamera = GetWorld()->SpawnActor<ACameraActor>();
		}
		if (TestCamera)
		{
			TestCamera->SetActorLocationAndRotation(Eye, (LookAt - Eye).Rotation());
			SetViewTarget(TestCamera);
		}
	};

	// Phase 0: Wait for staggered spawning + initial traffic acceleration warmup
	if (TestTrackAuditPhase == 0)
	{
		if ((!Director->IsSpawningFinished() || TestTrackAuditClock < 4.0f) && TestTrackAuditClock < 35.0f)
		{
			return;
		}
		const int32 Showroom = Director->GetShowroomCount();
		const int32 ExpectedTraffic = Director->GetExpectedTrafficCount();
		const int32 LiveTraffic = Director->GetLiveTrafficCount();
		const int32 Arena = Director->GetArenaTargetCount();
		if (Showroom < 50 || LiveTraffic < 33 || Arena < 4)
		{
			bTestTrackAuditPass = false;
			UE_LOG(LogWSPC2, Error, TEXT("TestTrackAudit Phase0 FAIL: Showroom=%d (want>=50), LiveTraffic=%d (expected %d, want>=33), Arena=%d (want>=4)"),
				Showroom, LiveTraffic, ExpectedTraffic, Arena);
		}
		else
		{
			UE_LOG(LogWSPC2, Log, TEXT("TestTrackAudit Phase0 OK: Showroom=%d, LiveTraffic=%d/%d, Arena=%d"),
				Showroom, LiveTraffic, ExpectedTraffic, Arena);
		}
		TestTrackAuditPhase = 1;
		TestTrackAuditSubStep = 0;
		TestTrackAuditClock = 0.0f;
		return;
	}

	// Phase 1: Verify live Chaos traffic accelerates cleanly around the circuit
	if (TestTrackAuditPhase == 1)
	{
		if (TestTrackAuditClock < 6.0f)
		{
			return;
		}
		const int32 LiveTraffic = Director->GetLiveTrafficCount();
		const int32 MovingTraffic = Director->GetMovingTrafficCount(8.0f);
		if (MovingTraffic < 25)
		{
			bTestTrackAuditPass = false;
			UE_LOG(LogWSPC2, Error, TEXT("TestTrackAudit Phase1 FAIL: MovingTraffic=%d/%d (want>=25 >= 8 km/h)"), MovingTraffic, LiveTraffic);
		}
		else
		{
			UE_LOG(LogWSPC2, Log, TEXT("TestTrackAudit Phase1 OK: MovingTraffic=%d/%d"), MovingTraffic, LiveTraffic);
		}
		TestTrackAuditPhase = 2;
		TestTrackAuditAudioStep = 0;
		TestTrackAuditSubStep = 0;
		TestTrackAuditClock = 1.0f;
		return;
	}

	// Phase 2: Hot-switch across real CitySample audio families, check siren/airhorn, capture Showroom screenshot
	if (TestTrackAuditPhase == 2)
	{
		struct FAuditFamilyCase
		{
			const TCHAR* PresetId;
			const TCHAR* ExpectedBankArchetype;
			const TCHAR* ExpectedStemFamily;
		};
		static const FAuditFamilyCase Cases[] = {
			{ TEXT("Patrol"),                       TEXT("arch_v8_efi_90s"),       TEXT("Sedan_Real") },
			{ TEXT("Police_Thunderbolt96_Retro"),   TEXT("arch_boxer4_uel_turbo"), TEXT("Hatchback_Real") },
			{ TEXT("Zhab_Gallo99_Police"),          TEXT("arch_i6_twinturbo"),     TEXT("Sports_Real") },
			{ TEXT("Zhab_SabaV12_95_Police"),       TEXT("arch_v12_exotic"),       TEXT("Sports_Real") },
			{ TEXT("Zhab_MD84_Armored"),            TEXT("arch_diesel_heavy"),     TEXT("Semi_Diesel_Real") },
			{ TEXT("Military_AbramsM1"),            TEXT("Heavy_Armored_Real"),    TEXT("Heavy_Armored_Real") },
			{ TEXT("Zhab_Club90"),                  TEXT("Electric_Quiet"),        TEXT("Electric_Quiet") },
		};
		constexpr int32 NumCases = UE_ARRAY_COUNT(Cases);

		if (TestTrackAuditSubStep == 0)
		{
			if (TestTrackAuditClock < 0.7f)
			{
				return;
			}
			if (TestTrackAuditAudioStep < NumCases)
			{
				const FAuditFamilyCase& Case = Cases[TestTrackAuditAudioStep++];
				const bool bSet = SportsCar->SetVehiclePreset(FName(Case.PresetId));
				const UWSPC2VehicleAudioComponent* Audio = SportsCar->GetVehicleAudio();
				const FString ActualFamily = Audio ? Audio->GetActiveEngineFamilyName() : TEXT("NULL");
				const bool bRealAudio = Audio && Audio->IsUsingRealRecordedAudio();
				const bool bFamilyMatch = (ActualFamily == Case.ExpectedBankArchetype) || (ActualFamily == Case.ExpectedStemFamily);
				if (!bSet || !bFamilyMatch || !bRealAudio)
				{
					bTestTrackAuditPass = false;
					UE_LOG(LogWSPC2, Error, TEXT("TestTrackAudit Phase2 FAIL [%s]: Set=%s, Family=%s (want %s or %s), RealAudio=%s"),
						Case.PresetId, bSet ? TEXT("true") : TEXT("false"), *ActualFamily, Case.ExpectedBankArchetype, Case.ExpectedStemFamily, bRealAudio ? TEXT("true") : TEXT("false"));
				}
				else
				{
					UE_LOG(LogWSPC2, Log, TEXT("TestTrackAudit Phase2 OK [%s]: Family=%s, RealAudio=%s"),
						Case.PresetId, *ActualFamily, bRealAudio ? TEXT("true") : TEXT("false"));
				}
				TestTrackAuditClock = 0.0f;
				return;
			}

			for (int32 i = 0; i < 4; ++i)
			{
				SportsCar->CycleSirenMode();
				UE_LOG(LogWSPC2, Log, TEXT("TestTrackAudit Phase2 Siren step %d: Mode=%s"), i, SportsCar->GetSirenModeName());
			}
			SportsCar->TriggerAirhorn();

			// Stage Murphy '97 SP near Showroom row 0 bays to visually confirm materials & colors
			SportsCar->SetVehiclePreset(FName(TEXT("Zhab_Murphy97_SP")));
			TeleportCar(SportsCar, FVector(12000.0f, 2250.0f, 235.0f), FRotator(0.0f, 35.0f, 0.0f));
			AimTestCam(FVector(10300.0f, 2100.0f, 430.0f), FVector(14200.0f, 3550.0f, 240.0f));
			TestTrackAuditSubStep = 1;
			TestTrackAuditClock = 0.0f;
			return;
		}
		if (TestTrackAuditSubStep == 1 && TestTrackAuditClock >= 0.8f)
		{
			FScreenshotRequest::RequestScreenshot(FPaths::ProjectSavedDir() / TEXT("Screenshots") / TEXT("Audit_Showroom.png"), false, false);
			UE_LOG(LogWSPC2, Log, TEXT("TestTrackAudit Phase2: requested Audit_Showroom.png"));
			TestTrackAuditSubStep = 2;
			TestTrackAuditClock = 0.0f;
			return;
		}
		if (TestTrackAuditSubStep == 2 && TestTrackAuditClock >= 0.7f)
		{
			TestTrackAuditPhase = 3;
			TestTrackAuditSubStep = 0;
			TestTrackAuditClock = 0.0f;
			return;
		}
		return;
	}

	// Phase 3: Real High-Speed Arena Wall Crash (Zhab_Murphy97_SP vs Concrete Barrier #1 at X=22000, Y=-2800)
	if (TestTrackAuditPhase == 3)
	{
		UWSPC2VehicleDamageComponent* Dmg = SportsCar->GetVehicleDamage();
		if (TestTrackAuditSubStep == 0)
		{
			SportsCar->SetVehiclePreset(FName(TEXT("Zhab_Murphy97_SP")));
			if (Dmg)
			{
				Dmg->RepairAll();
			}
			TeleportCar(SportsCar, FVector(11200.0f, -2800.0f, 235.0f), FRotator(0.0f, 0.0f, 0.0f));
			AimTestCam(FVector(12100.0f, -3350.0f, 390.0f), FVector(11400.0f, -2800.0f, 240.0f));
			TestTrackAuditSubStep = 1;
			TestTrackAuditClock = 0.0f;
			return;
		}
		if (TestTrackAuditSubStep == 1 && TestTrackAuditClock >= 0.8f)
		{
			FScreenshotRequest::RequestScreenshot(FPaths::ProjectSavedDir() / TEXT("Screenshots") / TEXT("Audit_Wreckfest_Before.png"), false, false);
			UE_LOG(LogWSPC2, Log, TEXT("TestTrackAudit Phase3: requested Audit_Wreckfest_Before.png at X=%.1f"), SportsCar->GetActorLocation().X);
			SetViewTarget(SportsCar);
			TestTrackAuditSubStep = 2;
			TestTrackAuditClock = 0.0f;
			return;
		}
		if (TestTrackAuditSubStep == 2)
		{
			SportsCar->DoSteering(0.0f);
			SportsCar->DoBrake(0.0f);
			SportsCar->DoThrottle(TestTrackAuditClock >= 0.30f ? 1.0f : 0.0f);

			const bool bHit = Dmg && Dmg->GetCollisionCount() > 0;
			if ((bHit && TestTrackAuditClock >= 2.2f && SportsCar->GetSpeedKmh() < 30.0f)
				|| (bHit && TestTrackAuditClock >= 6.2f)
				|| TestTrackAuditClock >= 7.8f)
			{
				SportsCar->DoThrottle(0.0f);
				TestTrackAuditSubStep = 3;
				TestTrackAuditClock = 0.0f;
			}
			return;
		}
		if (TestTrackAuditSubStep == 3 && TestTrackAuditClock >= 0.7f)
		{
			const float FinalX = SportsCar->GetActorLocation().X;
			const int32 Hits = Dmg ? Dmg->GetCollisionCount() : 0;
			const float HullPct = Dmg ? Dmg->GetHealthPercent() : 100.0f;
			const float EngIntr = Dmg ? Dmg->GetEngineBlockIntrusionPct() : 0.0f;
			const bool bDeformActive = Dmg && Dmg->IsDeformableMeshActive();
			const float MaxVertDisp = Dmg ? Dmg->GetMaxVertexDisplacementCm() : 0.0f;
			const int32 LooseP = Dmg ? Dmg->GetLoosePanelCount() : 0;
			const int32 DetP = Dmg ? Dmg->GetDetachedPanelCount() : 0;
			const int32 BrokenL = Dmg ? Dmg->GetBrokenLightCount() : 0;

			const bool bBlockedByWall = FinalX < 22150.0f;
			const bool bDamaged = Hits > 0 && HullPct < 95.0f && EngIntr > 0.0f;
			const bool bWreckfestOK = bDeformActive && MaxVertDisp >= 15.0f && (LooseP + DetP) >= 1 && BrokenL >= 1;
			if (!bBlockedByWall || !bDamaged || !bWreckfestOK)
			{
				bTestTrackAuditPass = false;
				UE_LOG(LogWSPC2, Error, TEXT("TestTrackAudit Phase3 FAIL WallCrash: FinalX=%.1f, Hits=%d, Hull=%.1f%%, EngIntr=%.1f%%, Deform=%d, MaxDisp=%.1fcm, Panels=%d/%d, BrokenLights=%d"),
					FinalX, Hits, HullPct, EngIntr, bDeformActive ? 1 : 0, MaxVertDisp, LooseP, DetP, BrokenL);
			}
			else
			{
				UE_LOG(LogWSPC2, Log, TEXT("TestTrackAudit Phase3 OK WallCrash: FinalX=%.1f, Hits=%d, Hull=%.1f%%, EngIntr=%.1f%%, Deform=%d, MaxDisp=%.1fcm, Panels=%d/%d, BrokenLights=%d"),
					FinalX, Hits, HullPct, EngIntr, bDeformActive ? 1 : 0, MaxVertDisp, LooseP, DetP, BrokenL);
			}

			const FTransform CarTf = SportsCar->GetActorTransform();
			AimTestCam(
				CarTf.TransformPosition(FVector(380.0f, -240.0f, 145.0f)),
				CarTf.TransformPosition(FVector(120.0f, 0.0f, 52.0f)));
			TestTrackAuditSubStep = 4;
			TestTrackAuditClock = 0.0f;
			return;
		}
		if (TestTrackAuditSubStep == 4 && TestTrackAuditClock >= 0.4f)
		{
			FScreenshotRequest::RequestScreenshot(FPaths::ProjectSavedDir() / TEXT("Screenshots") / TEXT("Audit_Wreckfest_WallFront.png"), false, false);
			UE_LOG(LogWSPC2, Log, TEXT("TestTrackAudit Phase3: requested Audit_Wreckfest_WallFront.png"));
			TestTrackAuditSubStep = 5;
			TestTrackAuditClock = 0.0f;
			return;
		}
		if (TestTrackAuditSubStep == 5 && TestTrackAuditClock >= 0.7f)
		{
			const FTransform CarTf = SportsCar->GetActorTransform();
			AimTestCam(
				CarTf.TransformPosition(FVector(580.0f, 420.0f, 320.0f)),
				CarTf.TransformPosition(FVector(100.0f, 0.0f, 45.0f)));
			TestTrackAuditSubStep = 6;
			TestTrackAuditClock = 0.0f;
			return;
		}
		if (TestTrackAuditSubStep == 6 && TestTrackAuditClock >= 0.4f)
		{
			FScreenshotRequest::RequestScreenshot(FPaths::ProjectSavedDir() / TEXT("Screenshots") / TEXT("Audit_Wreckfest_WallOverview.png"), false, false);
			UE_LOG(LogWSPC2, Log, TEXT("TestTrackAudit Phase3: requested Audit_Wreckfest_WallOverview.png"));
			TestTrackAuditSubStep = 7;
			TestTrackAuditClock = 0.0f;
			return;
		}
		if (TestTrackAuditSubStep == 7 && TestTrackAuditClock >= 0.7f)
		{
			TestTrackAuditPhase = 4;
			TestTrackAuditSubStep = 0;
			TestTrackAuditClock = 0.0f;
			return;
		}
		return;
	}

	// Phase 4: Real Car-to-Car Chaos Collision (Patrol vs Arena Target #1) + RepairAll reset check
	if (TestTrackAuditPhase == 4)
	{
		if (TestTrackAuditSubStep == 0)
		{
			SportsCar->SetVehiclePreset(FName(TEXT("Patrol")));
			if (UWSPC2VehicleDamageComponent* Dmg = SportsCar->GetVehicleDamage())
			{
				Dmg->RepairAll();
			}
			SetViewTarget(SportsCar);

			AWSPC2SportsCar* ArenaTarget = Director->GetFirstArenaTargetCar();
			if (!ArenaTarget || !ArenaTarget->GetVehicleDamage())
			{
				bTestTrackAuditPass = false;
				UE_LOG(LogWSPC2, Error, TEXT("TestTrackAudit Phase4 FAIL: missing ArenaTarget #1"));
				TestTrackAuditPhase = 5;
				TestTrackAuditClock = 0.0f;
				return;
			}
			TestTrackAuditTargetCar = ArenaTarget;
			TestTrackAuditTargetStartPos = ArenaTarget->GetActorLocation();
			TeleportCar(SportsCar, TestTrackAuditTargetStartPos + FVector(-5500.0f, 0.0f, 20.0f), FRotator(0.0f, 0.0f, 0.0f));
			TestTrackAuditSubStep = 1;
			TestTrackAuditClock = 0.0f;
			return;
		}
		if (TestTrackAuditSubStep == 1 && TestTrackAuditClock >= 0.8f)
		{
			TestTrackAuditSubStep = 2;
			TestTrackAuditClock = 0.0f;
			return;
		}
		if (TestTrackAuditSubStep == 2)
		{
			AWSPC2SportsCar* ArenaTarget = Cast<AWSPC2SportsCar>(TestTrackAuditTargetCar.Get());
			float SteerCmd = 0.0f;
			if (ArenaTarget)
			{
				const FVector LocalTarget = SportsCar->GetActorTransform().InverseTransformPosition(ArenaTarget->GetActorLocation());
				const float TargetYawDeg = FMath::RadiansToDegrees(FMath::Atan2(LocalTarget.Y, FMath::Max(LocalTarget.X, 100.0f)));
				SteerCmd = FMath::Clamp(TargetYawDeg / 25.0f, -1.0f, 1.0f);
			}
			SportsCar->DoSteering(SteerCmd);
			SportsCar->DoBrake(0.0f);
			SportsCar->DoThrottle(1.0f);

			UWSPC2VehicleDamageComponent* PlayerDmg = SportsCar->GetVehicleDamage();
			UWSPC2VehicleDamageComponent* TargetDmg = ArenaTarget ? ArenaTarget->GetVehicleDamage() : nullptr;
			const bool bBothHit = PlayerDmg && TargetDmg && PlayerDmg->GetCollisionCount() > 0 && TargetDmg->GetCollisionCount() > 0;
			if ((bBothHit && TestTrackAuditClock >= 1.4f) || TestTrackAuditClock >= 5.2f)
			{
				SportsCar->DoThrottle(0.0f);
				SportsCar->DoSteering(0.0f);
				TestTrackAuditSubStep = 3;
				TestTrackAuditClock = 0.0f;
			}
			return;
		}
		if (TestTrackAuditSubStep == 3 && TestTrackAuditClock >= 0.7f)
		{
			AWSPC2SportsCar* ArenaTarget = Cast<AWSPC2SportsCar>(TestTrackAuditTargetCar.Get());
			UWSPC2VehicleDamageComponent* PlayerDmg = SportsCar->GetVehicleDamage();
			UWSPC2VehicleDamageComponent* TargetDmg = ArenaTarget ? ArenaTarget->GetVehicleDamage() : nullptr;
			const int32 PlayerHits = PlayerDmg ? PlayerDmg->GetCollisionCount() : 0;
			const int32 TargetHits = TargetDmg ? TargetDmg->GetCollisionCount() : 0;
			const float MovedCm = ArenaTarget ? FVector::Dist2D(ArenaTarget->GetActorLocation(), TestTrackAuditTargetStartPos) : 0.0f;
			const bool bPatrolDeform = PlayerDmg && PlayerDmg->IsDeformableMeshActive();
			const float PatrolDisp = PlayerDmg ? PlayerDmg->GetMaxVertexDisplacementCm() : 0.0f;
			const int32 TargetLoose = TargetDmg ? TargetDmg->GetLoosePanelCount() : 0;
			const int32 TargetDet = TargetDmg ? TargetDmg->GetDetachedPanelCount() : 0;

			if (PlayerHits == 0 || TargetHits == 0 || MovedCm < 80.0f || !bPatrolDeform || PatrolDisp < 8.0f)
			{
				bTestTrackAuditPass = false;
				UE_LOG(LogWSPC2, Error, TEXT("TestTrackAudit Phase4 FAIL CarToCar: PlayerHits=%d, TargetHits=%d, Moved=%.1f cm, PatrolDeform=%d, PatrolDisp=%.1f cm, TargetPanels=%d/%d"),
					PlayerHits, TargetHits, MovedCm, bPatrolDeform ? 1 : 0, PatrolDisp, TargetLoose, TargetDet);
			}
			else
			{
				UE_LOG(LogWSPC2, Log, TEXT("TestTrackAudit Phase4 OK CarToCar: PlayerHits=%d, TargetHits=%d, Moved=%.1f cm, PatrolDeform=%d, PatrolDisp=%.1f cm, TargetPanels=%d/%d"),
					PlayerHits, TargetHits, MovedCm, bPatrolDeform ? 1 : 0, PatrolDisp, TargetLoose, TargetDet);
			}

			const FVector PPos = SportsCar->GetActorLocation();
			const FVector Fwd = SportsCar->GetActorForwardVector();
			const FVector Right = SportsCar->GetActorRightVector();
			AimTestCam(
				PPos + Fwd * 440.0f - Right * 290.0f + FVector(0.0f, 0.0f, 135.0f),
				PPos + Fwd * 95.0f + FVector(0.0f, 0.0f, 55.0f));
			TestTrackAuditSubStep = 4;
			TestTrackAuditClock = 0.0f;
			return;
		}
		if (TestTrackAuditSubStep == 4 && TestTrackAuditClock >= 0.4f)
		{
			FScreenshotRequest::RequestScreenshot(FPaths::ProjectSavedDir() / TEXT("Screenshots") / TEXT("Audit_Wreckfest_PatrolCrash.png"), false, false);
			UE_LOG(LogWSPC2, Log, TEXT("TestTrackAudit Phase4: requested Audit_Wreckfest_PatrolCrash.png"));
			TestTrackAuditSubStep = 5;
			TestTrackAuditClock = 0.0f;
			return;
		}
		if (TestTrackAuditSubStep == 5 && TestTrackAuditClock >= 0.7f)
		{
			if (UWSPC2VehicleDamageComponent* PlayerDmg = SportsCar->GetVehicleDamage())
			{
				PlayerDmg->RepairAll();
				if (PlayerDmg->GetHealthPercent() < 99.5f || PlayerDmg->IsEngineStalled() || PlayerDmg->IsDeformableMeshActive())
				{
					bTestTrackAuditPass = false;
					UE_LOG(LogWSPC2, Error, TEXT("TestTrackAudit Phase4 FAIL: RepairAll left Hull=%.1f%%, stalled=%s, deformActive=%s"),
						PlayerDmg->GetHealthPercent(), PlayerDmg->IsEngineStalled() ? TEXT("true") : TEXT("false"),
						PlayerDmg->IsDeformableMeshActive() ? TEXT("true") : TEXT("false"));
				}
			}

			TestTrackAuditPhase = 5;
			TestTrackAuditSubStep = 0;
			TestTrackAuditClock = 0.0f;
			return;
		}
		return;
	}

	// Phase 5: Finalize audit after giving screenshots time to flush
	if (TestTrackAuditPhase == 5)
	{
		if (TestTrackAuditClock < 1.0f)
		{
			return;
		}
		const UWSPC2VehicleAudioComponent* Audio = SportsCar->GetVehicleAudio();
		UE_LOG(LogWSPC2, Log, TEXT("TestTrackAudit: COMPLETE (PASS=%s, Showroom=%d, Traffic=%d/%d, Arena=%d, RealAudio=%s)"),
			bTestTrackAuditPass ? TEXT("true") : TEXT("false"),
			Director->GetShowroomCount(),
			Director->GetLiveTrafficCount(),
			Director->GetMovingTrafficCount(8.0f),
			Director->GetArenaTargetCount(),
			(Audio && Audio->IsUsingRealRecordedAudio()) ? TEXT("true") : TEXT("false"));

		ConsoleCommand(TEXT("quit"));
		bTestTrackAudit = false;
	}
}
