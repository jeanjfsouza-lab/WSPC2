// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "WSPC2Types.h"
#include "WSPC2GameMode.generated.h"

class AWSPC2Pawn;
class AWSPC2GunnerPawn;

/**
 *  Runs on the server only. Owns the patrol car's two seats:
 *  the first player to join drives, the second is the gunner,
 *  and they may trade places when the car is nearly stopped.
 */
UCLASS(abstract)
class AWSPC2GameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AWSPC2GameMode();

	virtual void HandleStartingNewPlayer_Implementation(APlayerController* NewPlayer) override;
	virtual void Logout(AController* Exiting) override;

	/** Driver and gunner trade places. Returns false if the swap was refused. */
	bool RequestSeatSwap(APlayerController* Requester);

	/** Called when the car was destroyed and a new one spawned for the driver */
	void OnPatrolCarReplaced(AWSPC2Pawn* NewCar);

	AWSPC2Pawn* GetPatrolCar() const { return PatrolCar; }

protected:

	UPROPERTY()
	TObjectPtr<AWSPC2Pawn> PatrolCar;

	UPROPERTY()
	TObjectPtr<AWSPC2GunnerPawn> GunnerPawn;

	UPROPERTY()
	TObjectPtr<APlayerController> DriverPC;

	UPROPERTY()
	TObjectPtr<APlayerController> GunnerPC;

	/** Puts a player in the gunner seat, creating the gunner pawn if needed */
	void SeatGunner(APlayerController* Player);

	/** Records the seat on the player's replicated state */
	void SetSeat(APlayerController* Player, EWSPC2Seat Seat);
};
