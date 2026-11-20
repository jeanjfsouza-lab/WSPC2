// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "WheeledVehiclePawn.h"
#include "WSPC2Pawn.generated.h"

class UCameraComponent;
class USpringArmComponent;
class UInputAction;
class UChaosWheeledVehicleMovementComponent;
class UPointLightComponent;
class USceneComponent;
class UStaticMeshComponent;
class UWSPC2VehicleDamageComponent;
class UWSPC2VehicleAudioComponent;
struct FInputActionValue;

/**
 *  Vehicle Pawn class
 *  Handles common functionality for all vehicle types,
 *  including input handling and camera management.
 *  
 *  Specific vehicle configurations are handled in subclasses.
 */
UCLASS(abstract)
class AWSPC2Pawn : public AWheeledVehiclePawn
{
	GENERATED_BODY()

	/** Spring Arm for the front camera */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category ="Components", meta = (AllowPrivateAccess = "true"))
	USpringArmComponent* FrontSpringArm;

	/** Front Camera component */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category ="Components", meta = (AllowPrivateAccess = "true"))
	UCameraComponent* FrontCamera;

	/** Spring Arm for the back camera */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category ="Components", meta = (AllowPrivateAccess = "true"))
	USpringArmComponent* BackSpringArm;

	/** Back Camera component */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category ="Components", meta = (AllowPrivateAccess = "true"))
	UCameraComponent* BackCamera;

	/** Cast pointer to the Chaos Vehicle movement component */
	TObjectPtr<UChaosWheeledVehicleMovementComponent> ChaosVehicleMovement;

	/** Where the gunner sits: passenger side, at window height */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category ="Components", meta = (AllowPrivateAccess = "true"))
	USceneComponent* GunnerSeat;

	/** Roof light bar, red side */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category ="Components", meta = (AllowPrivateAccess = "true"))
	UPointLightComponent* SirenLightLeft;

	/** Roof light bar, blue side */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category ="Components", meta = (AllowPrivateAccess = "true"))
	UPointLightComponent* SirenLightRight;

	/** The glowing lenses of the light bar: what the eye sees flash, day or night */
	UPROPERTY(VisibleAnywhere, Category = "Components")
	UStaticMeshComponent* SirenLensLeft;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	UStaticMeshComponent* SirenLensRight;

	/** Real-time Chaos collision & vehicle deformation/damage manager */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category ="Components", meta = (AllowPrivateAccess = "true"))
	UWSPC2VehicleDamageComponent* VehicleDamage;

	/** Engine, tyre, wind, crash and siren sounds */
	UPROPERTY(VisibleAnywhere, Category = "Components")
	UWSPC2VehicleAudioComponent* VehicleAudio;

	/** Siren state, owned by the server and replicated to everyone */
	UPROPERTY(ReplicatedUsing = OnRep_Siren)
	bool bSirenOn = false;

	/** Drives the light bar flash */
	float SirenFlashTime = 0.0f;

	/** True when this chassis carries an external roof light bar (shows external glowing lens blocks). */
	bool bHasRoofLightbar = true;

	UFUNCTION()
	void OnRep_Siren();

	/** Shows or hides the light bar for the current siren state and flash phase */
	void UpdateSirenLights();

	/** Widens the view and lets the chase camera fall back as the car goes faster */
	void UpdateSpeedCamera(float Delta);

	/** Chase camera orbit (yaw around the car, pitch above its normal height) and its swing back behind the car */
	void UpdateChaseOrbit(float Delta);

	/** Brake assist and the rear grip lost on power (UWSPC2VehicleTuning::BrakeAssistG, RearThrottleGripLoss) */
	void ApplyDriveAssists(float Delta);

	float ChaseOrbitYaw = 0.0f;
	float ChaseOrbitPitch = 0.0f;
	float ChaseLookIdle = 10.0f;
	float AppliedRearGripScale = 1.0f;

	/** Smoothed 0..1 speed used by the cameras */
	float CameraSpeedAlpha = 0.0f;

protected:

	/** Steering Action */
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* SteeringAction;

	/** Throttle Action */
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* ThrottleAction;

	/** Brake Action */
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* BrakeAction;

	/** Handbrake Action */
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* HandbrakeAction;

	/** Look Around Action */
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* LookAroundAction;

	/** Toggle Camera Action */
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* ToggleCameraAction;

	/** Reset Vehicle Action */
	UPROPERTY(EditAnywhere, Category="Input")
	UInputAction* ResetVehicleAction;

	/** Keeps track of which camera is active */
	bool bFrontCameraActive = false;

	/** 0 is the chase camera; 1..N are the on-car views below */
	int32 CameraMode = 0;

	/** On-car camera positions (car space) and their names, cycled after the chase camera */
	TArray<FVector> OnCarViews = { FVector(30.0f, 0.0f, 120.0f) };
	TArray<FString> OnCarViewNames = { TEXT("Hood") };

	/** Replaces the on-car camera positions for a given body */
	void SetOnCarViews(const TArray<FVector>& Locations, const TArray<FString>& Names);

	/** Keeps track of whether the car is flipped. If this is true for two flip checks, resets the vehicle automatically */
	bool bPreviousFlipCheck = false;

	/** Time between automatic flip checks */
	UPROPERTY(EditAnywhere, Category="Flip Check", meta = (Units = "s"))
	float FlipCheckTime = 3.0f;

	/** Minimum dot product value for the vehicle's up direction that we still consider upright */
	UPROPERTY(EditAnywhere, Category="Flip Check")
	float FlipCheckMinDot = -0.2f;

	/** Flip check timer */
	FTimerHandle FlipCheckTimer;

public:
	AWSPC2Pawn();

	// Begin Pawn interface

	virtual void SetupPlayerInputComponent(UInputComponent* InputComponent) override;

	// End Pawn interface

	// Begin Actor interface

	/** Initialization */
	virtual void BeginPlay() override;

	/** Cleanup */
	virtual void EndPlay(EEndPlayReason::Type EndPlayReason) override;

	/** Update */
	virtual void Tick(float Delta) override;

	// End Actor interface

protected:

	/** Handles steering input */
	void Steering(const FInputActionValue& Value);

	/** Handles throttle input */
	void Throttle(const FInputActionValue& Value);

	/** Handles brake input */
	void Brake(const FInputActionValue& Value);

	/** Handles brake start/stop inputs */
	void StartBrake(const FInputActionValue& Value);
	void StopBrake(const FInputActionValue& Value);

	/** Handles handbrake start/stop inputs */
	void StartHandbrake(const FInputActionValue& Value);
	void StopHandbrake(const FInputActionValue& Value);

	/** Handles look around input */
	void LookAround(const FInputActionValue& Value);

	/** Handles toggle camera input */
	void ToggleCamera(const FInputActionValue& Value);

	/** Handles reset vehicle input */
	void ResetVehicle(const FInputActionValue& Value);

public:

	/** Handle steering input by input actions or mobile interface */
	UFUNCTION(BlueprintCallable, Category="Input")
	void DoSteering(float SteeringValue);

	/** Handle throttle input by input actions or mobile interface */
	UFUNCTION(BlueprintCallable, Category="Input")
	void DoThrottle(float ThrottleValue);

	/** Handle brake input by input actions or mobile interface */
	UFUNCTION(BlueprintCallable, Category="Input")
	void DoBrake(float BrakeValue);

	/** Handle brake start input by input actions or mobile interface */
	UFUNCTION(BlueprintCallable, Category="Input")
	void DoBrakeStart();

	/** Handle brake stop input by input actions or mobile interface */
	UFUNCTION(BlueprintCallable, Category="Input")
	void DoBrakeStop();

	/** Handle handbrake start input by input actions or mobile interface */
	UFUNCTION(BlueprintCallable, Category="Input")
	void DoHandbrakeStart();

	/** Handle handbrake stop input by input actions or mobile interface */
	UFUNCTION(BlueprintCallable, Category="Input")
	void DoHandbrakeStop();

	/** Handle look input by input actions or mobile interface */
	UFUNCTION(BlueprintCallable, Category="Input")
	void DoLookAround(float YawDelta);

	/** Turns the chase camera around the car: X yaw (+ right), Y pitch (+ camera higher), in degrees */
	void AddChaseLook(const FVector2D& DeltaDegrees);

	/** Handle toggle camera input by input actions or mobile interface */
	UFUNCTION(BlueprintCallable, Category="Input")
	void DoToggleCamera();

	/** Handle reset vehicle input by input actions or mobile interface */
	UFUNCTION(BlueprintCallable, Category="Input")
	void DoResetVehicle();

protected:

	/** Called when the brake lights are turned on or off */
	UFUNCTION(BlueprintImplementableEvent, Category="Vehicle")
	void BrakeLights(bool bBraking);

	/** Checks if the car is flipped upside down and automatically resets it */
	UFUNCTION()
	void FlippedCheck();

public:

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** A driver took the wheel: release the parking brake */
	virtual void PossessedBy(AController* NewController) override;

	/** The driver left the seat: park the car */
	virtual void UnPossessed() override;

	/** Turns the siren on or off. Server only; clients go through their player controller. */
	void SetSiren(bool bOn);

	UFUNCTION(BlueprintPure, Category="Vehicle")
	bool IsSirenOn() const { return bSirenOn; }

	/** Fraction of full lock the driver may use now: limited by speed when turning in, never when countersteering */
	float GetSteeringAllowance(float Input) const;

	/** Ground speed in km/h, always positive */
	UFUNCTION(BlueprintPure, Category="Vehicle")
	float GetSpeedKmh() const;

	/** Human-readable name of the active hero chassis (overridden by AWSPC2SportsCar). */
	UFUNCTION(BlueprintPure, Category="Vehicle")
	virtual FString GetActiveVehicleDisplayName() const { return TEXT("Patrol Cruiser"); }

	USceneComponent* GetGunnerSeat() const { return GunnerSeat; }

	/** Name of the camera in use: "Chase" or one of the on-car views ("Dashboard", "Hood", "Bumper") */
	FString GetActiveCameraName() const
	{
		return bFrontCameraActive && OnCarViewNames.IsValidIndex(CameraMode - 1) ? OnCarViewNames[CameraMode - 1] : FString(TEXT("Chase"));
	}

	/** True while the driver looks through the in-car "Dashboard" view (the camera is where the driver's head is) */
	bool IsCabinViewActive() const { return GetActiveCameraName() == TEXT("Dashboard"); }

	/** The gunner's weapon muzzle (world) when an officer is drawn holding one; false otherwise */
	virtual bool GetGunnerMuzzle(FVector& OutLocation, FVector& OutDirection) const { return false; }

	/** The gunner's weapons, rounds, lock and shots */
	FORCEINLINE class UWSPC2GunneryComponent* GetGunnery() const { return Gunnery; }

protected:

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<class UWSPC2GunneryComponent> Gunnery;

	/** Places the gunner seat and the roof light bar for a given car body (car space, cm) */
	void SetCrewLayout(const FVector& GunnerSeatLocation, const FVector& LightBarCentre, float LightHalfSpacing);

	/** Toggles external roof lightbar lens meshes (hidden on undercover / non-lightbar hero chassis). */
	void SetRoofLightbarEnabled(bool bEnabled);

	/** Hook for siren sound and effects, implemented in Blueprint */
	UFUNCTION(BlueprintImplementableEvent, Category="Vehicle")
	void OnSirenChanged(bool bOn);

	/** Asks the server to put the car back on its wheels */
	UFUNCTION(Server, Reliable)
	void ServerResetVehicle();

public:
	/** Returns the front spring arm subobject */
	FORCEINLINE USpringArmComponent* GetFrontSpringArm() const { return FrontSpringArm; }
	/** Returns the front camera subobject */
	FORCEINLINE UCameraComponent* GetFollowCamera() const { return FrontCamera; }
	/** Returns the back spring arm subobject */
	FORCEINLINE USpringArmComponent* GetBackSpringArm() const { return BackSpringArm; }
	/** Returns the back camera subobject */
	FORCEINLINE UCameraComponent* GetBackCamera() const { return BackCamera; }
	/** Returns the cast Chaos Vehicle Movement subobject */
	FORCEINLINE const TObjectPtr<UChaosWheeledVehicleMovementComponent>& GetChaosVehicleMovement() const { return ChaosVehicleMovement; }
	/** Returns the Chaos vehicle damage component */
	FORCEINLINE UWSPC2VehicleDamageComponent* GetVehicleDamage() const { return VehicleDamage; }
};
