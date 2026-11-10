#pragma once

#include "CoreMinimal.h"
#include "WSPC2Types.generated.h"

/** Which seat of the patrol car a player occupies. */
UENUM(BlueprintType)
enum class EWSPC2Seat : uint8
{
	None,
	Driver,
	Gunner
};
