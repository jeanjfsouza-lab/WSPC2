#include "WSPC2GunnerPawn.h"
#include "WSPC2Pawn.h"
#include "WSPC2VehicleTuning.h"
#include "Camera/CameraComponent.h"
#include "Components/SceneComponent.h"
#include "Net/UnrealNetwork.h"
#include "Engine/Engine.h"

AWSPC2GunnerPawn::AWSPC2GunnerPawn()
{
	PrimaryActorTick.bCanEverTick = true;

	bReplicates = true;
	SetReplicateMovement(true);

	SeatRoot = CreateDefaultSubobject<USceneComponent>(TEXT("Seat Root"));
	RootComponent = SeatRoot;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(SeatRoot);
	Camera->bUsePawnControlRotation = false;

	// the car carries us; never collide with it
	SetActorEnableCollision(false);
}

void AWSPC2GunnerPawn::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AWSPC2GunnerPawn, Vehicle);
	DOREPLIFETIME_CONDITION(AWSPC2GunnerPawn, RelativeAim, COND_SkipOwner);
}

void AWSPC2GunnerPawn::AttachToVehicle(AWSPC2Pawn* InVehicle)
{
	Vehicle = InVehicle;

	if (IsValid(InVehicle))
	{
		AttachToComponent(InVehicle->GetGunnerSeat(), FAttachmentTransformRules::SnapToTargetNotIncludingScale);
	}

	bHasLastVelocity = false;
}

void AWSPC2GunnerPawn::AddAimInput(const FVector2D& DeltaDegrees)
{
	RelativeAim.X = FMath::Clamp(RelativeAim.X + DeltaDegrees.X, MinYaw, MaxYaw);
	RelativeAim.Y = FMath::Clamp(RelativeAim.Y + DeltaDegrees.Y, MinPitch, MaxPitch);
}

void AWSPC2GunnerPawn::ToggleView()
{
	bThirdPerson = !bThirdPerson;

	if (GEngine && IsLocallyControlled())
	{
		GEngine->AddOnScreenDebugMessage(7001, 2.0f, FColor::Cyan, bThirdPerson ? TEXT("Camera: Third person") : TEXT("Camera: First person"));
	}
}

FRotator AWSPC2GunnerPawn::GetAimRotation() const
{
	const FRotator Local(RelativeAim.Y + Sway.Y, RelativeAim.X + Sway.X, 0.0f);

	if (IsValid(Vehicle))
	{
		return (Vehicle->GetActorQuat() * Local.Quaternion()).Rotator();
	}

	return Local;
}

void AWSPC2GunnerPawn::UpdateSway(float DeltaSeconds)
{
	const UWSPC2VehicleTuning* Tuning = GetDefault<UWSPC2VehicleTuning>();

	if (!IsValid(Vehicle) || DeltaSeconds <= KINDA_SMALL_NUMBER)
	{
		return;
	}

	// acceleration of the car in its own frame, in g (velocity is cm/s, 1 g = 981 cm/s^2)
	const FVector Velocity = Vehicle->GetVelocity();
	FVector LocalAccelG = FVector::ZeroVector;

	if (bHasLastVelocity)
	{
		const FVector WorldAccel = (Velocity - LastVehicleVelocity) / DeltaSeconds;
		LocalAccelG = Vehicle->GetActorQuat().UnrotateVector(WorldAccel) / 981.0f;

		// a collision can spike far beyond what a body can follow
		LocalAccelG = LocalAccelG.GetClampedToMaxSize(6.0f);
	}

	LastVehicleVelocity = Velocity;
	bHasLastVelocity = true;

	// the body lags behind the car: turning right throws the aim left, braking throws it forward and down,
	// a bump throws it down then up
	const FVector2D Target(
		-LocalAccelG.Y * Tuning->AimSwayDegPerG,
		(LocalAccelG.X * 0.5f - LocalAccelG.Z) * Tuning->AimSwayDegPerG);

	// underdamped spring, so the aim overshoots and wobbles before it settles
	SwayVelocity += ((Target - Sway) * Tuning->AimSwayStiffness - SwayVelocity * Tuning->AimSwayDamping) * DeltaSeconds;
	Sway += SwayVelocity * DeltaSeconds;
}

void AWSPC2GunnerPawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	UpdateSway(DeltaSeconds);

	// the view is the aim: what the gunner sees shakes exactly as the weapon does
	const FRotator Aim = GetAimRotation();

	if (bThirdPerson && IsValid(Vehicle))
	{
		// orbit the car: the camera sits behind the aim direction, so the car and the target are both in view
		const FVector Pivot = Vehicle->GetActorLocation() + FVector(0.0f, 0.0f, 170.0f);
		Camera->SetWorldLocationAndRotation(Pivot - Aim.Vector() * 720.0f, Aim);
	}
	else
	{
		Camera->SetRelativeLocation(FVector::ZeroVector);
		Camera->SetWorldRotation(Aim);
	}

	if (IsLocallyControlled() && !HasAuthority())
	{
		AimSendTimer += DeltaSeconds;

		if (AimSendTimer >= 0.05f)
		{
			AimSendTimer = 0.0f;
			ServerSetAim(RelativeAim);
		}
	}
}

void AWSPC2GunnerPawn::ServerSetAim_Implementation(FVector2D NewAim)
{
	RelativeAim.X = FMath::Clamp(NewAim.X, MinYaw, MaxYaw);
	RelativeAim.Y = FMath::Clamp(NewAim.Y, MinPitch, MaxPitch);
}
