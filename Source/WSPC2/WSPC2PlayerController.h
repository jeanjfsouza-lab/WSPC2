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
	void OnGunnerLookMouse(const FInputActionValue& Value);
	void OnGunnerLookStick(const FInputActionValue& Value);

public:

	/** Update vehicle UI on tick */
	virtual void Tick(float Delta) override;

	/** Keeps the patrol car in the world when its driver disconnects */
	virtual void PawnLeavingGame() override;

	/** Console command: same as pressing the change-seat key */
	UFUNCTION(Exec)
	void SwapSeat();

	/** Shows a short message on this player's screen. Called by the server. */
	UFUNCTION(Client, Reliable)
	void ClientNotify(const FString& Message);

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
};
