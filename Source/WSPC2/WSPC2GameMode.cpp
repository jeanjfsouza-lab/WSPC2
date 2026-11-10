// Copyright Epic Games, Inc. All Rights Reserved.

#include "WSPC2GameMode.h"
#include "WSPC2PlayerController.h"
#include "WSPC2PlayerState.h"
#include "WSPC2Pawn.h"
#include "WSPC2GunnerPawn.h"
#include "WSPC2VehicleTuning.h"
#include "WSPC2.h"
#include "Engine/World.h"

AWSPC2GameMode::AWSPC2GameMode()
{
	PlayerControllerClass = AWSPC2PlayerController::StaticClass();
	PlayerStateClass = AWSPC2PlayerState::StaticClass();
}

void AWSPC2GameMode::SetSeat(APlayerController* Player, EWSPC2Seat Seat)
{
	if (IsValid(Player))
	{
		if (AWSPC2PlayerState* State = Player->GetPlayerState<AWSPC2PlayerState>())
		{
			State->Seat = Seat;
			State->ForceNetUpdate();
		}
	}
}

void AWSPC2GameMode::HandleStartingNewPlayer_Implementation(APlayerController* NewPlayer)
{
	if (!IsValid(DriverPC))
	{
		if (IsValid(PatrolCar))
		{
			// a car was left behind by a driver who quit: take it over
			NewPlayer->Possess(PatrolCar);
		}
		else
		{
			// spawns the default pawn (the patrol car) at a player start and possesses it
			Super::HandleStartingNewPlayer_Implementation(NewPlayer);

			PatrolCar = Cast<AWSPC2Pawn>(NewPlayer->GetPawn());
		}

		DriverPC = NewPlayer;
		SetSeat(NewPlayer, EWSPC2Seat::Driver);

		UE_LOG(LogWSPC2, Log, TEXT("%s takes the driver seat"), *GetNameSafe(NewPlayer));
	}
	else if (!IsValid(GunnerPC) && IsValid(PatrolCar))
	{
		SeatGunner(NewPlayer);

		UE_LOG(LogWSPC2, Log, TEXT("%s takes the gunner seat"), *GetNameSafe(NewPlayer));
	}
	else
	{
		// one car, two seats for now: anyone else joins without a pawn
		SetSeat(NewPlayer, EWSPC2Seat::None);

		UE_LOG(LogWSPC2, Warning, TEXT("%s joined but both seats are taken"), *GetNameSafe(NewPlayer));
	}
}

void AWSPC2GameMode::SeatGunner(APlayerController* Player)
{
	if (!IsValid(Player) || !IsValid(PatrolCar))
	{
		return;
	}

	if (!IsValid(GunnerPawn))
	{
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

		GunnerPawn = GetWorld()->SpawnActor<AWSPC2GunnerPawn>(AWSPC2GunnerPawn::StaticClass(), PatrolCar->GetActorTransform(), Params);
	}

	if (IsValid(GunnerPawn))
	{
		GunnerPawn->AttachToVehicle(PatrolCar);
		Player->Possess(GunnerPawn);

		GunnerPC = Player;
		SetSeat(Player, EWSPC2Seat::Gunner);
	}
}

bool AWSPC2GameMode::RequestSeatSwap(APlayerController* Requester)
{
	AWSPC2PlayerController* RequesterPC = Cast<AWSPC2PlayerController>(Requester);

	// only someone sitting in the car may ask
	if (!IsValid(PatrolCar) || !IsValid(Requester) || (Requester != DriverPC && Requester != GunnerPC))
	{
		return false;
	}

	// nobody climbs across the cabin at speed
	const float MaxSpeed = GetDefault<UWSPC2VehicleTuning>()->SeatSwapMaxSpeedKmh;

	if (PatrolCar->GetSpeedKmh() > MaxSpeed)
	{
		if (RequesterPC)
		{
			RequesterPC->ClientNotify(FString::Printf(TEXT("Stop the car to change seats (below %.0f km/h)"), MaxSpeed));
		}

		return false;
	}

	// alone in the car: just move to the other seat. The car stays parked with the handbrake on.
	if (!IsValid(DriverPC) || !IsValid(GunnerPC))
	{
		if (Requester == DriverPC)
		{
			DriverPC = nullptr;
			Requester->UnPossess();
			SeatGunner(Requester);
		}
		else
		{
			GunnerPC = nullptr;
			Requester->UnPossess();
			Requester->Possess(PatrolCar);

			DriverPC = Requester;
			SetSeat(Requester, EWSPC2Seat::Driver);
		}

		if (RequesterPC)
		{
			RequesterPC->ClientNotify(Requester == DriverPC ? TEXT("You moved to the driver seat") : TEXT("You moved to the gunner seat"));
		}

		return true;
	}

	if (!IsValid(GunnerPawn))
	{
		return false;
	}

	APlayerController* OldDriver = DriverPC;
	APlayerController* OldGunner = GunnerPC;

	OldDriver->UnPossess();
	OldGunner->UnPossess();

	OldGunner->Possess(PatrolCar);
	OldDriver->Possess(GunnerPawn);

	DriverPC = OldGunner;
	GunnerPC = OldDriver;

	SetSeat(DriverPC, EWSPC2Seat::Driver);
	SetSeat(GunnerPC, EWSPC2Seat::Gunner);

	UE_LOG(LogWSPC2, Log, TEXT("Seats swapped: %s now drives"), *GetNameSafe(DriverPC));

	if (AWSPC2PlayerController* NewDriver = Cast<AWSPC2PlayerController>(DriverPC))
	{
		NewDriver->ClientNotify(TEXT("Seats swapped: you drive"));
	}

	if (AWSPC2PlayerController* NewGunner = Cast<AWSPC2PlayerController>(GunnerPC))
	{
		NewGunner->ClientNotify(TEXT("Seats swapped: you are the gunner"));
	}

	return true;
}

void AWSPC2GameMode::OnPatrolCarReplaced(AWSPC2Pawn* NewCar)
{
	PatrolCar = NewCar;

	// move the gunner over to the new car
	if (IsValid(GunnerPawn) && IsValid(NewCar))
	{
		GunnerPawn->AttachToVehicle(NewCar);
	}
}

void AWSPC2GameMode::Logout(AController* Exiting)
{
	if (Exiting == GunnerPC)
	{
		GunnerPC = nullptr;

		if (IsValid(GunnerPawn))
		{
			GunnerPawn->Destroy();
		}

		GunnerPawn = nullptr;
	}
	else if (Exiting == DriverPC)
	{
		DriverPC = nullptr;

		// the car stays in the world; the gunner, if any, slides over and drives
		if (IsValid(GunnerPC) && IsValid(PatrolCar))
		{
			APlayerController* NewDriver = GunnerPC;
			GunnerPC = nullptr;

			NewDriver->UnPossess();

			if (IsValid(GunnerPawn))
			{
				GunnerPawn->Destroy();
			}

			GunnerPawn = nullptr;

			NewDriver->Possess(PatrolCar);

			DriverPC = NewDriver;
			SetSeat(NewDriver, EWSPC2Seat::Driver);
		}
	}

	Super::Logout(Exiting);
}
