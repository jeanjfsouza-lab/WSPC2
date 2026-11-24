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

/** Multi-mode US police siren state (toggled/cycled cleanly via H / J). */
UENUM(BlueprintType)
enum class EWSPC2SirenMode : uint8
{
	Off = 0,
	Wail = 1,
	Yelp = 2,
	Phaser = 3
};
