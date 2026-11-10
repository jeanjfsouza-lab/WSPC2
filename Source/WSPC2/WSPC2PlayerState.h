#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerState.h"
#include "WSPC2Types.h"
#include "WSPC2PlayerState.generated.h"

/** Replicates the seat each player holds so every client knows who drives and who shoots. */
UCLASS()
class AWSPC2PlayerState : public APlayerState
{
	GENERATED_BODY()

public:

	UPROPERTY(Replicated, BlueprintReadOnly, Category = "Seat")
	EWSPC2Seat Seat = EWSPC2Seat::None;

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
};
