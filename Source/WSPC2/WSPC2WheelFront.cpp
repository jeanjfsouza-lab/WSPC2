// Copyright Epic Games, Inc. All Rights Reserved.

#include "WSPC2WheelFront.h"
#include "UObject/ConstructorHelpers.h"

UWSPC2WheelFront::UWSPC2WheelFront()
{
	AxleType = EAxleType::Front;
	bAffectedBySteering = true;
	MaxSteerAngle = 40.f;
}