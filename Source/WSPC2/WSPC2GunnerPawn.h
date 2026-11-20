#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "WSPC2GunnerPawn.generated.h"

class UCameraComponent;
class USceneComponent;
class AWSPC2Pawn;

/**
 *  The second player: rides in the passenger seat, half out of the window.
 *  Aim is stored relative to the car, so every turn, brake and bump of the car
 *  moves the aim. Weapons are added in a later stage.
 */
UCLASS()
class AWSPC2GunnerPawn : public APawn
{
	GENERATED_BODY()

	UPROPERTY(VisibleAnywhere, Category = "Components")
	USceneComponent* SeatRoot;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	UCameraComponent* Camera;

	/** The car this gunner rides in */
	UPROPERTY(Replicated)
	TObjectPtr<AWSPC2Pawn> Vehicle;

	/** Aim relative to the car: X = yaw (0 is straight ahead, 90 is out of the passenger window), Y = pitch */
	UPROPERTY(Replicated)
	FVector2D RelativeAim = FVector2D(70.0f, 0.0f);

	/** Aim displacement caused by the car's motion, in degrees (X = yaw, Y = pitch) */
	FVector2D Sway = FVector2D::ZeroVector;
	FVector2D SwayVelocity = FVector2D::ZeroVector;

	/** Car velocity on the previous frame, to measure acceleration */
	FVector LastVehicleVelocity = FVector::ZeroVector;
	bool bHasLastVelocity = false;

	/** Time since the aim was last sent to the server */
	float AimSendTimer = 0.0f;

	/** False: view from the gunner's eyes. True: camera behind the car, looking along the aim. */
	bool bThirdPerson = false;

public:

	AWSPC2GunnerPawn();

	virtual void Tick(float DeltaSeconds) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Seats this gunner in a car. Server only. */
	void AttachToVehicle(AWSPC2Pawn* InVehicle);

	AWSPC2Pawn* GetVehicle() const { return Vehicle; }

	/** True when the camera is behind the car; false when it looks from the gunner's own eyes */
	bool IsThirdPerson() const { return bThirdPerson; }

	/** The aim relative to the car (yaw, pitch degrees), without the sway; replicated to everyone but the owner */
	FVector2D GetRelativeAimDeg() const { return RelativeAim; }

	/** Turns the aim by a number of degrees. Called on the owning client. */
	void AddAimInput(const FVector2D& DeltaDegrees);

	/** Switches between first and third person. Local to this player. */
	void ToggleView();

	/** Direction the weapon points at, in world space, including the sway */
	FRotator GetAimRotation() const;

protected:

	/** Arc the gunner can cover from the passenger window */
	UPROPERTY(EditAnywhere, Category = "Aim")
	float MinYaw = -25.0f;

	UPROPERTY(EditAnywhere, Category = "Aim")
	float MaxYaw = 155.0f;

	UPROPERTY(EditAnywhere, Category = "Aim")
	float MinPitch = -30.0f;

	UPROPERTY(EditAnywhere, Category = "Aim")
	float MaxPitch = 35.0f;

	/** Sends the aim to the server so other players and, later, hit checks can use it */
	UFUNCTION(Server, Unreliable)
	void ServerSetAim(FVector2D NewAim);

	/** Advances the sway spring from the car's current acceleration */
	void UpdateSway(float DeltaSeconds);
};
