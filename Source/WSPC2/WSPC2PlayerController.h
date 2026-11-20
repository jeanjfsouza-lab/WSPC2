// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "WSPC2PlayerController.generated.h"

class UInputMappingContext;
class UInputAction;
class AWSPC2Pawn;
class AWSPC2GunnerPawn;
class UWSPC2UI;
struct FInputActionValue;

/**
 *  Vehicle Player Controller class
 *  Handles input mapping and user interface, and carries the player's requests
 *  (swap seats, siren) to the server.
 */
UCLASS(abstract, Config="Game")
class AWSPC2PlayerController : public APlayerController
{
	GENERATED_BODY()

protected:

	/** Input Mapping Contexts */
	UPROPERTY(EditAnywhere, Category ="Input|Input Mappings")
	TArray<UInputMappingContext*> DefaultMappingContexts;

	/** Input Mapping Contexts */
	UPROPERTY(EditAnywhere, Category="Input|Input Mappings")
	TArray<UInputMappingContext*> MobileExcludedMappingContexts;

	/** Mobile controls widget to spawn */
	UPROPERTY(EditAnywhere, Category="Input|Touch Controls")
	TSubclassOf<UUserWidget> MobileControlsWidgetClass;

	/** Pointer to the mobile controls widget */
	UPROPERTY()
	TObjectPtr<UUserWidget> MobileControlsWidget;

	/** If true, the player will use UMG touch controls even if not playing on mobile platforms */
	UPROPERTY(EditAnywhere, Config, Category = "Input|Touch Controls")
	bool bForceTouchControls = false;

	/** If true, the optional steering wheel input mapping context will be registered */
	UPROPERTY(EditAnywhere, Category = "Input|Steering Wheel Controls")
	bool bUseSteeringWheelControls = false;

	/** Optional Input Mapping Context to be used for steering wheel input.
	 *  This is added alongside the default Input Mapping Context and does not block other forms of input.
	 */
	UPROPERTY(EditAnywhere, Category = "Input|Steering Wheel Controls", meta = (EditCondition = "bUseSteeringWheelControls"))
	UInputMappingContext* SteeringWheelInputMappingContext;

	/** Type of vehicle to automatically respawn when it's destroyed */
	UPROPERTY(EditAnywhere, Category="Vehicle|Respawn")
	TSubclassOf<AWSPC2Pawn> VehiclePawnClass;

	/** Pointer to the controlled vehicle pawn */
	TObjectPtr<AWSPC2Pawn> VehiclePawn;

	/** Type of the UI to spawn */
	UPROPERTY(EditAnywhere, Category="Vehicle|UI")
	TSubclassOf<UWSPC2UI> VehicleUIClass;

	/** Pointer to the UI widget */
	UPROPERTY()
	TObjectPtr<UWSPC2UI> VehicleUI;

	// ---- Crew input, built in code so it needs no input assets ----

	UPROPERTY()
	TObjectPtr<UInputMappingContext> CrewMappingContext;

	UPROPERTY()
	TObjectPtr<UInputAction> SwapSeatAction;

	UPROPERTY()
	TObjectPtr<UInputAction> SirenAction;

	UPROPERTY()
	TObjectPtr<UInputAction> CameraAction;

	UPROPERTY()
	TObjectPtr<UInputAction> CycleVehicleAction;

	UPROPERTY()
	TObjectPtr<UInputAction> WeaponPrevAction;

	UPROPERTY()
	TObjectPtr<UInputAction> WeaponNextAction;

	UPROPERTY()
	TObjectPtr<UInputAction> LockAction;

	UPROPERTY()
	TObjectPtr<UInputAction> FireAction;

	UPROPERTY()
	TObjectPtr<UInputAction> GunnerTriggerAction;

	UPROPERTY()
	TObjectPtr<UInputAction> GunnerLookMouseAction;

	UPROPERTY()
	TObjectPtr<UInputAction> GunnerLookStickAction;

	/** Degrees of aim per unit of mouse movement */
	UPROPERTY(EditAnywhere, Config, Category = "Input|Gunner")
	float GunnerMouseSensitivity = 0.12f;

	/** Degrees of aim per second at full stick deflection */
	UPROPERTY(EditAnywhere, Config, Category = "Input|Gunner")
	float GunnerStickRate = 120.0f;

protected:

	/** Gameplay initialization */
	virtual void BeginPlay() override;

	/** Input setup */
	virtual void SetupInputComponent() override;

	/** Creates the crew actions and key bindings */
	void SetupCrewInput();

	void OnSwapSeat(const FInputActionValue& Value);
	void OnSiren(const FInputActionValue& Value);
	void OnCamera(const FInputActionValue& Value);
	void OnCycleVehicle(const FInputActionValue& Value);
	void OnWeaponPrev(const FInputActionValue& Value);
	void OnWeaponNext(const FInputActionValue& Value);
	void OnLock(const FInputActionValue& Value);
	void OnFirePressed(const FInputActionValue& Value);
	void OnGunnerTriggerPressed(const FInputActionValue& Value);
	void OnFireReleased(const FInputActionValue& Value);

	/** This player handles the weapons: the second player, or the driver when he is alone in the car */
	bool HoldsTheGun() const;

	UFUNCTION(Server, Reliable)
	void ServerCycleWeapon(int32 Direction);

	UFUNCTION(Server, Reliable)
	void ServerToggleLock(FVector ViewLocation, FVector ViewDirection);

	UFUNCTION(Server, Reliable)
	void ServerSetTrigger(bool bDown);

	UFUNCTION(Server, Reliable)
	void ServerStartMission(FName Id);

	UFUNCTION(Server, Reliable)
	void ServerStopMission();

	/** The mission director of this world, looked up now and then (clients show its status line) */
	TWeakObjectPtr<class AWSPC2MissionDirector> CachedDirector;
	float DirectorLookupAge = 10.0f;

	// ---- Automated test drive (-WSPC2TestDrive): full throttle to 100 km/h, then full brake ----

	bool bTestDrive = false;
	int32 TestDrivePhase = 0;
	float TestDriveClock = 0.0f;
	float TestDriveDistance = 0.0f;
	float TestDriveTo60 = -1.0f;
	float TestDrivePeakSpeed = 0.0f;
	float TestDriveLastFrontAngle = 0.0f;
	bool bTestDriveSpinLogged = false;
	bool bTestDriveStripBuilt = false;
	float TestDriveStartYaw = 0.0f;

	// ---- Handling part of the test drive (phases 3..8): power oversteer, a disturbance at speed, a slide caught ----

	float TestPeakSlip = 0.0f;
	float TestPeakYawRate = 0.0f;
	float TestSlideSign = 0.0f;
	bool bTestSlideReported = false;

	/** Puts the car back on the strip, pointing along it, at rest */
	void TestPlaceCar(class AWSPC2Pawn* Car, float XMetres);

	/** Car's sideslip angle (degrees, + = moving to its right) and yaw rate (degrees per second) */
	static void TestSlip(const class AWSPC2Pawn* Car, float& OutSlipDeg, float& OutYawRate);

	void TickTestDrive(float Delta);

	void OnGunnerLookMouse(const FInputActionValue& Value);
	void OnGunnerLookStick(const FInputActionValue& Value);

public:

	/** Update vehicle UI on tick */
	virtual void Tick(float Delta) override;

	/** Keeps the patrol car in the world when its driver disconnects */
	virtual void PawnLeavingGame() override;

	/** Hides, for this player's view only, the officer whose head the camera is in (the driver in the Dashboard
	 *  view, the gunner in his first-person view); everyone else still sees him */
	virtual void UpdateHiddenComponents(const FVector& ViewLocation, TSet<FPrimitiveComponentId>& HiddenComponents) override;

	/** Test hook: swings the chase camera and saves a screenshot */
	void TestScreenshot();

	int32 TestShotIndex = 0;

	/** One fixed camera of the -WSPC2Views tour */
	struct FTestView
	{
		FString Name;
		FVector Location = FVector::ZeroVector;
		FVector LookAt = FVector::ZeroVector;
		/** "car:" name prefix: Location and LookAt are in the player's car space, not the world */
		bool bCarSpace = false;
		/** "pawn:<view>" name: look through the car's own camera of that name (Chase, Dashboard, Hood, Bumper) */
		FString PawnView;
	};

	TArray<FTestView> TestViews;
	int32 TestViewIndex = -1;
	int32 TestViewWaits = 0;
	uint64 TestViewFrame0 = 0;
	double TestViewTime0 = 0.0;

	/** Test hook: captures the current fixed camera and moves on to the next */
	void TestViewStep();

	/** Test hook (-WSPC2TestGround): drives straight on the loaded map and logs the car's position */
	void TickTestGround(float Delta);

	/** Test hook (-WSPC2TestDamage): tests progressive physical, visual and mechanical damage from Light to Wrecked and repair */
	void TickTestDamage(float Delta);

	/** Test hook (-WSPC2TestFleet): cycles through every built-in hero preset, verifies physics drive and damage on each */
	void TickTestFleet(float Delta);

	bool bTestGround = false;
	float TestGroundClock = 0.0f;

	bool bTestDamage = false;
	bool bTestDamageStripBuilt = false;
	int32 TestDamagePhase = 0;
	float TestDamageClock = 0.0f;

	bool bTestFleet = false;
	bool bTestFleetStripBuilt = false;
	int32 TestFleetIndex = 0;
	int32 TestFleetSubPhase = 0;
	float TestFleetClock = 0.0f;

	/** Test hook (-WSPC2TestGunnery): a car parked ahead, the lock on it, then pistol, shotgun and rifle fired at it */
	void TickTestGunnery(float Delta);

	bool bTestGunnery = false;
	int32 TestGunPhase = 0;
	float TestGunClock = 0.0f;
	int32 TestGunPulses = 0;

	UPROPERTY()
	TObjectPtr<AActor> TestGunTarget;

	UPROPERTY()
	TObjectPtr<class ACameraActor> TestCamera;

	UPROPERTY()
	TObjectPtr<class AStaticMeshActor> TestDamageBarrier;

	/** Console command: same as pressing the change-seat key */
	UFUNCTION(Exec)
	void SwapSeat();

	/** Console command: switches hero vehicle to a named preset (Patrol, Undercover, Interceptor, SUV, Pickup, SWATVan, CrownVic). */
	UFUNCTION(Exec)
	void SetVehicle(const FString& PresetName);

	/** Console command: cycles to the next available hero vehicle preset (same as [V]). */
	UFUNCTION(Exec)
	void NextVehicle();

	/** Shows a short message on this player's screen. Called by the server. */
	UFUNCTION(Client, Reliable)
	void ClientNotify(const FString& Message);

	/** Console command: starts a campaign mission of WSPC2_Bay (Op01, Op02, Op03, Op04) */
	UFUNCTION(Exec)
	void Mission(const FString& Id);

	/** Console command: gives up the mission under way */
	UFUNCTION(Exec)
	void MissionStop();

	/** The car this player is in, whether driving or riding as gunner. Works on clients too. */
	AWSPC2Pawn* GetCurrentVehicle() const;

protected:

	/** Pawn setup */
	virtual void OnPossess(APawn* InPawn) override;

	/** Handles pawn destruction and respawning */
	UFUNCTION()
	void OnPawnDestroyed(AActor* DestroyedPawn);

	/** Returns true if the player should use UMG touch controls */
	bool ShouldUseTouchControls() const;

	/** Asks the server to trade seats with the other crew member */
	UFUNCTION(Server, Reliable)
	void ServerRequestSeatSwap();

	/** Asks the server to toggle the siren of the car this player is in */
	UFUNCTION(Server, Reliable)
	void ServerToggleSiren();

	/** Asks the server to switch the hero vehicle to a specific built-in preset */
	UFUNCTION(Server, Reliable)
	void ServerSetVehiclePreset(FName PresetId);

	/** Asks the server to cycle to the next available built-in hero vehicle preset */
	UFUNCTION(Server, Reliable)
	void ServerCycleVehiclePreset();
};
