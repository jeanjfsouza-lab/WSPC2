// Copyright Epic Games, Inc. All Rights Reserved.

#include "WSPC2WheelRear.h"
#include "UObject/ConstructorHelpers.h"

UWSPC2WheelRear::UWSPC2WheelRear()
{
	AxleType = EAxleType::Rear;
	bAffectedByHandbrake = true;
	bAffectedByEngine = true;
}