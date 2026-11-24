#include "WSPC2Mission.h"
#include "WSPC2.h"
#include "WSPC2Pawn.h"
#include "WSPC2SportsCar.h"
#include "WSPC2PlayerController.h"
#include "WSPC2LayoutDirector.h"
#include "WSPC2VehicleDamageComponent.h"
#include "ChaosWheeledVehicleMovementComponent.h"
#include "ChaosVehicleWheel.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Net/UnrealNetwork.h"

namespace WSPC2Missions
{
	const TCHAR* SetPath = TEXT("/Game/Bay/Missions/DA_Missions.DA_Missions");
	constexpr float CountdownSeconds = 3.0f;
	constexpr float EndLingerSeconds = 8.0f;

	float Dist2D(const FVector& A, const FVector& B)
	{
		return FVector2D::Distance(FVector2D(A.X, A.Y), FVector2D(B.X, B.Y));
	}

	/** Holds a car where it is: the brake while it rolls, the handbrake once slow (the template's brake, held at a
	 *  standstill, engages reverse) */
	void Halt(AWSPC2Pawn* Car)
	{
		if (!Car)
		{
			return;
		}
		Car->DoSteering(0.0f);
		if (FMath::Abs(Car->GetSpeedKmh()) > 6.0f)
		{
			Car->DoBrake(1.0f);
		}
		else
		{
			Car->DoThrottle(0.0f);
			Car->DoHandbrakeStart();
		}
	}
}

// ------------------------------------------------------------------------------------------------------------------
// Mission set

const FWSPC2MissionSpec* UWSPC2MissionSet::Find(FName Id) const
{
	return Missions.FindByPredicate([Id](const FWSPC2MissionSpec& M) { return M.Id == Id; });
}

// ------------------------------------------------------------------------------------------------------------------
// Route driver

UWSPC2RouteDriver::UWSPC2RouteDriver()
{
	PrimaryComponentTick.bCanEverTick = true;
}

void UWSPC2RouteDriver::Drive(const TArray<FVector2D>& InRoute, float InMaxKmh, bool bInLoop)
{
	Route = InRoute;
	MaxKmh = InMaxKmh;
	bLoop = bInLoop;
	bFinished = Route.Num() < 2;
	StuckTime = 0.0f;
	ReverseLeft = 0.0f;
	HoldLeft = 0.0f;

	Along.SetNum(Route.Num());
	float Sum = 0.0f;
	for (int32 Point = 0; Point < Route.Num(); ++Point)
	{
		Sum += Point > 0 ? FVector2D::Distance(Route[Point - 1], Route[Point]) : 0.0f;
		Along[Point] = Sum;
	}

	// a player's own pawn: his pad would keep setting the controls back (as -WSPC2TestDrive, take them away)
	if (AWSPC2Pawn* Car = Cast<AWSPC2Pawn>(GetOwner()))
	{
		if (APlayerController* PC = Cast<APlayerController>(Car->GetController()))
		{
			Car->DisableInput(PC);
		}
	}

	// start from the point nearest the car
	Index = 0;
	if (const AActor* Owner = GetOwner())
	{
		const FVector2D Here(Owner->GetActorLocation().X, Owner->GetActorLocation().Y);
		float Best = TNumericLimits<float>::Max();
		for (int32 Point = 0; Point < Route.Num(); ++Point)
		{
			const float D = FVector2D::DistSquared(Here, Route[Point]);
			if (D < Best)
			{
				Best = D;
				Index = Point;
			}
		}
	}
}

void UWSPC2RouteDriver::Stop()
{
	bFinished = true;
	if (AWSPC2Pawn* Car = Cast<AWSPC2Pawn>(GetOwner()))
	{
		if (APlayerController* PC = Cast<APlayerController>(Car->GetController()))
		{
			Car->EnableInput(PC);
		}
	}
	WSPC2Missions::Halt(Cast<AWSPC2Pawn>(GetOwner()));
}

float UWSPC2RouteDriver::GetProgress() const
{
	return Along.Num() > 1 && Along.Last() > 0.0f ? Along[FMath::Clamp(Index, 0, Along.Num() - 1)] / Along.Last() : 0.0f;
}

void UWSPC2RouteDriver::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	AWSPC2Pawn* Car = Cast<AWSPC2Pawn>(GetOwner());
	if (!Car || !Car->HasAuthority() || Route.Num() < 2)
	{
		return;
	}

	if (bFinished)
	{
		WSPC2Missions::Halt(Car);
		return;
	}

	if (const UWSPC2VehicleDamageComponent* DamageComp = Car->GetVehicleDamage())
	{
		if (DamageComp->IsEngineStalled())
		{
			WSPC2Missions::Halt(Car);
			return;
		}
	}

	const FVector Location = Car->GetActorLocation();
	const FVector2D Here(Location.X, Location.Y);
	const int32 Num = Route.Num();

	// where on the route: the nearest point a little ahead of the last one
	float BestDistance = FVector2D::Distance(Here, Route[Index]);
	for (int32 Step = 1; Step < 60; ++Step)
	{
		const int32 Point = bLoop ? (Index + Step) % Num : Index + Step;
		if (Point >= Num)
		{
			break;
		}
		const float D = FVector2D::Distance(Here, Route[Point]);
		if (D < BestDistance)
		{
			BestDistance = D;
			Index = Point;
		}
	}

	if (!bLoop && Index >= Num - 2 && FVector2D::Distance(Here, Route.Last()) < 900.0f)
	{
		Stop();
		return;
	}

	const float Speed = Car->GetSpeedKmh();
	if (HoldLeft > 0.0f)
	{
		HoldLeft -= DeltaTime;
		WSPC2Missions::Halt(Car);
		bHandbrake = true;
		return;
	}

	// how far along the route the car is: its foot on the segment before or after the nearest point
	float AlongHere = Along[Index];
	for (const int32 From : { Index - 1, Index })
	{
		if (From >= 0 && From + 1 < Num)
		{
			const FVector2D Segment = Route[From + 1] - Route[From];
			const float Length = Segment.Size();
			const float Foot = Length > 1.0f ? FVector2D::DotProduct(Here - Route[From], Segment / Length) : 0.0f;
			if (Foot >= 0.0f && Foot <= Length)
			{
				AlongHere = Along[From] + Foot;
			}
		}
	}

	// the point to aim at, further ahead the faster we go
	auto PointAt = [this, Num, AlongHere](float Distance) -> FVector2D
	{
		const float Total = Along.Last();
		float Want = AlongHere + Distance;
		if (bLoop && Total > 0.0f)
		{
			Want = FMath::Fmod(Want, Total);
		}
		Want = FMath::Min(Want, Total);
		int32 Point = 0;
		while (Point < Num - 1 && Along[Point + 1] < Want)
		{
			++Point;
		}
		if (Point >= Num - 1)
		{
			return Route.Last();
		}
		const float Span = FMath::Max(Along[Point + 1] - Along[Point], 1.0f);
		return FMath::Lerp(Route[Point], Route[Point + 1], (Want - Along[Point]) / Span);
	};

	// a lane of cones wants the aim close in front; open road can look further ahead
	const float Look = bTight ? FMath::Clamp(250.0f + Speed * 10.0f, 350.0f, 1500.0f) : FMath::Clamp(600.0f + Speed * 22.0f, 900.0f, 2800.0f);
	const FVector2D Target = PointAt(Look);
	const FVector Local = Car->GetActorTransform().InverseTransformPositionNoScale(FVector(Target.X, Target.Y, Location.Z));
	const float ErrorDeg = FMath::RadiansToDegrees(FMath::Atan2(Local.Y, Local.X));

	// the speed for the road ahead: every 3 m out to 60 m, the bend there (heading change per metre) allows a speed,
	// and from here to there the car can shed 4 m/s each second; the lowest of those, and the route's own top speed
	const float SideG = (bTight ? 0.3f : 0.5f) * 9.81f;
	const float Decel = bTight ? 2.0f : 3.0f;
	float WantMs = MaxKmh * SpeedScale / 3.6f;
	for (float Ahead = 3.0f; Ahead <= 60.0f; Ahead += 3.0f)
	{
		const FVector2D A = PointAt((Ahead - 3.0f) * 100.0f);
		const FVector2D B = PointAt(Ahead * 100.0f);
		const FVector2D C = PointAt((Ahead + 3.0f) * 100.0f);
		const FVector2D In = (B - A).GetSafeNormal();
		const FVector2D Out = (C - B).GetSafeNormal();
		if (In.IsNearlyZero() || Out.IsNearlyZero())
		{
			continue;
		}
		const float PerMetre = FMath::Acos(FMath::Clamp(FVector2D::DotProduct(In, Out), -1.0f, 1.0f)) / 3.0f;
		const float CornerMs = FMath::Sqrt(SideG / FMath::Max(PerMetre, 0.0005f));
		WantMs = FMath::Min(WantMs, FMath::Sqrt(CornerMs * CornerMs + 2.0f * Decel * Ahead));
	}
	float Want = FMath::Clamp(WantMs * 3.6f, bTight ? 8.0f : 18.0f, 220.0f);
	if (FMath::Abs(ErrorDeg) > 40.0f)
	{
		Want = FMath::Min(Want, 28.0f);
	}

	if (bAvoidTrafficAhead)
	{
		if (const UWorld* World = GetWorld())
		{
			const FVector Fwd = Car->GetActorForwardVector();
			const FVector Up = Car->GetActorUpVector();
			const FVector Start = Location + Fwd * 320.0f + Up * 85.0f;
			const FVector End = Location + Fwd * 2300.0f + Up * 85.0f;
			FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(WSPC2TrafficLookahead), false, Car);
			FHitResult Hit;
			if (World->SweepSingleByChannel(Hit, Start, End, FQuat::Identity, ECC_Vehicle, FCollisionShape::MakeSphere(135.0f), QueryParams))
			{
				if (Cast<AWSPC2Pawn>(Hit.GetActor()))
				{
					const float HitDistCm = FVector::Dist(Location, Hit.ImpactPoint);
					const float Alpha = FMath::Clamp((HitDistCm - 900.0f) / 1300.0f, 0.0f, 1.0f);
					Want *= Alpha;
				}
			}
		}
	}

	// stuck against something: back out for a moment, steering the other way
	if (ReverseLeft > 0.0f)
	{
		ReverseLeft -= DeltaTime;
		Car->DoSteering(-FMath::Clamp(ErrorDeg / 30.0f, -1.0f, 1.0f));
		Car->DoBrake(1.0f);
		return;
	}
	StuckTime = (Speed < 3.0f && Want > 10.0f) ? StuckTime + DeltaTime : 0.0f;
	if (StuckTime > 2.5f)
	{
		StuckTime = 0.0f;
		ReverseLeft = 1.8f;
	}

	DebugAge += DeltaTime;
	if (DebugAge > 1.0f)
	{
		DebugAge = 0.0f;
		UE_LOG(LogWSPC2, Verbose, TEXT("RouteDriver %s: point %d/%d at (%.0f, %.0f), %.0f km/h want %.0f, aim (%.0f, %.0f) %.0f deg off, steering input %.2f, wheel FL %.1f deg, controller %s"), *Car->GetName(), Index, Num,
			Here.X / 100.0f, -Here.Y / 100.0f, Speed, Want, Target.X / 100.0f, -Target.Y / 100.0f, ErrorDeg,
			Car->GetChaosVehicleMovement() ? Car->GetChaosVehicleMovement()->GetSteeringInput() : -9.0f,
			Car->GetChaosVehicleMovement() && Car->GetChaosVehicleMovement()->Wheels.Num() > 0 && Car->GetChaosVehicleMovement()->Wheels[0] ? Car->GetChaosVehicleMovement()->Wheels[0]->GetSteerAngle() : -99.0f,
			*GetNameSafe(Car->GetController()));
	}
	if (bHandbrake)
	{
		bHandbrake = false;
		Car->DoHandbrakeStop();
	}
	Car->DoSteering(FMath::Clamp(ErrorDeg / (bTight ? 14.0f : 28.0f), -1.0f, 1.0f));
	if (Want < 2.0f)
	{
		Car->DoThrottle(0.0f);
		Car->DoBrake(0.85f);
		return;
	}
	const float Gap = Want - Speed;
	if (Gap > 2.0f)
	{
		Car->DoThrottle(FMath::Clamp(Gap / 12.0f, 0.25f, 1.0f));
	}
	else if (Gap < -5.0f)
	{
		Car->DoBrake(FMath::Clamp(-Gap / 25.0f, 0.15f, 1.0f));
	}
	else
	{
		Car->DoThrottle(0.15f);
	}
}

// ------------------------------------------------------------------------------------------------------------------
// Pop-up target

AWSPC2PopupTarget::AWSPC2PopupTarget()
{
	PrimaryActorTick.bCanEverTick = true;
	bReplicates = true;
	Tags.Add(TEXT("WSPC2Target"));
	Tags.Add(TEXT("WSPC2TargetDown"));

	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));

	Post = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Post"));
	Post->SetupAttachment(RootComponent);
	Post->SetStaticMesh(Cube);
	Post->SetRelativeLocation(FVector(0.0f, 0.0f, 40.0f));
	Post->SetRelativeScale3D(FVector(0.08f, 0.08f, 0.8f));

	Hinge = CreateDefaultSubobject<USceneComponent>(TEXT("Hinge"));
	Hinge->SetupAttachment(RootComponent);
	Hinge->SetRelativeLocation(FVector(0.0f, 0.0f, 80.0f));

	// the board stands up from the hinge, its face along x
	Board = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Board"));
	Board->SetupAttachment(Hinge);
	Board->SetStaticMesh(Cube);
	Board->SetRelativeLocation(FVector(0.0f, 0.0f, 45.0f));
	Board->SetRelativeScale3D(FVector(0.05f, 0.65f, 0.9f));
	Board->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
	Board->SetCollisionResponseToChannel(ECC_Vehicle, ECR_Ignore);
}

void AWSPC2PopupTarget::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AWSPC2PopupTarget, bUp);
	DOREPLIFETIME(AWSPC2PopupTarget, bHit);
}

void AWSPC2PopupTarget::Raise(float Seconds)
{
	if (bHit)
	{
		return;
	}
	bUp = true;
	UpLeft = Seconds;
	Tags.Remove(TEXT("WSPC2TargetDown"));
}

void AWSPC2PopupTarget::Lower()
{
	bUp = false;
	Tags.AddUnique(TEXT("WSPC2TargetDown"));
}

float AWSPC2PopupTarget::TakeDamage(float DamageAmount, FDamageEvent const& DamageEvent, AController* EventInstigator, AActor* DamageCauser)
{
	if (HasAuthority() && bUp && !bHit)
	{
		bHit = true;
		Lower();
		UE_LOG(LogWSPC2, Log, TEXT("Mission: target %s hit"), *GetName());
	}
	return DamageAmount;
}

void AWSPC2PopupTarget::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);

	if (HasAuthority() && bUp)
	{
		UpLeft -= DeltaTime;
		if (UpLeft <= 0.0f)
		{
			Lower();
		}
	}

	// up stands at 0 degrees, down lies back flat; a hit one lies red-side down
	const float Want = bUp ? 0.0f : -88.0f;
	Angle = FMath::FInterpConstantTo(Angle, Want, DeltaTime, 320.0f);
	Hinge->SetRelativeRotation(FRotator(Angle, 0.0f, 0.0f));
}

// ------------------------------------------------------------------------------------------------------------------
// Director

AWSPC2MissionDirector::AWSPC2MissionDirector()
{
	PrimaryActorTick.bCanEverTick = true;
	bReplicates = true;
	bAlwaysRelevant = true;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

void AWSPC2MissionDirector::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AWSPC2MissionDirector, State);
	DOREPLIFETIME(AWSPC2MissionDirector, StatusLine);
	DOREPLIFETIME(AWSPC2MissionDirector, MissionId);
	DOREPLIFETIME(AWSPC2MissionDirector, Marker);
	DOREPLIFETIME(AWSPC2MissionDirector, bMarker);
}

AWSPC2MissionDirector* AWSPC2MissionDirector::Get(UWorld* World, bool bCreate)
{
	if (!World)
	{
		return nullptr;
	}
	for (TActorIterator<AWSPC2MissionDirector> It(World); It; ++It)
	{
		return *It;
	}
	if (bCreate && World->GetNetMode() != NM_Client)
	{
		return World->SpawnActor<AWSPC2MissionDirector>();
	}
	return nullptr;
}

AWSPC2Pawn* AWSPC2MissionDirector::GetPlayerCar() const
{
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		if (const AWSPC2PlayerController* PC = Cast<AWSPC2PlayerController>(It->Get()))
		{
			if (AWSPC2Pawn* Car = PC->GetCurrentVehicle())
			{
				return Car;
			}
		}
	}
	return nullptr;
}

void AWSPC2MissionDirector::Notify(const FString& Message) const
{
	UE_LOG(LogWSPC2, Log, TEXT("Mission %s: %s"), *MissionId.ToString(), *Message);
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		if (AWSPC2PlayerController* PC = Cast<AWSPC2PlayerController>(It->Get()))
		{
			PC->ClientNotify(Message);
		}
	}
}

FTransform AWSPC2MissionDirector::Grounded(const FTransform& At) const
{
	// on the ground under the point (static geometry only, so a car in the way does not lift it)
	FHitResult Hit;
	const FVector From = At.GetLocation() + FVector(0.0f, 0.0f, 400.0f);
	const FVector To = At.GetLocation() - FVector(0.0f, 0.0f, 900.0f);
	FCollisionObjectQueryParams Objects(ECC_WorldStatic);
	FTransform Out = At;
	if (GetWorld()->LineTraceSingleByObjectType(Hit, From, To, Objects))
	{
		Out.SetLocation(Hit.ImpactPoint + FVector(0.0f, 0.0f, 60.0f));
	}
	return Out;
}

void AWSPC2MissionDirector::PlaceCar(AWSPC2Pawn* Car, const FTransform& At) const
{
	if (!Car)
	{
		return;
	}
	Car->SetActorTransform(At, false, nullptr, ETeleportType::TeleportPhysics);
	if (UPrimitiveComponent* Body = Car->GetMesh())
	{
		Body->SetPhysicsLinearVelocity(FVector::ZeroVector);
		Body->SetPhysicsAngularVelocityInDegrees(FVector::ZeroVector);
	}
}

AWSPC2Pawn* AWSPC2MissionDirector::SpawnCar(FName Preset, const FTransform& At, bool bDriven)
{
	AWSPC2Pawn* Player = GetPlayerCar();
	if (!Player)
	{
		return nullptr;
	}

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
	AWSPC2Pawn* Car = GetWorld()->SpawnActor<AWSPC2Pawn>(Player->GetClass(), Grounded(At), Params);
	if (!Car)
	{
		return nullptr;
	}

	if (AWSPC2SportsCar* Hero = Cast<AWSPC2SportsCar>(Car))
	{
		if (!Preset.IsNone() && !Hero->SetVehiclePreset(Preset))
		{
			UE_LOG(LogWSPC2, Warning, TEXT("Mission: preset %s not installed for %s, it keeps its own"), *Preset.ToString(), *Car->GetName());
		}
	}

	if (bDriven)
	{
		Car->SpawnDefaultController();
		UWSPC2RouteDriver* Driver = NewObject<UWSPC2RouteDriver>(Car, TEXT("RouteDriver"));
		Driver->RegisterComponent();
	}
	return Car;
}

bool AWSPC2MissionDirector::StartMission(FName Id)
{
	if (!HasAuthority())
	{
		return false;
	}

	const UWSPC2MissionSet* Set = Cast<UWSPC2MissionSet>(StaticLoadObject(UWSPC2MissionSet::StaticClass(), nullptr, WSPC2Missions::SetPath, nullptr, LOAD_NoWarn | LOAD_Quiet));
	const FWSPC2MissionSpec* Found = Set ? Set->Find(Id) : nullptr;
	AWSPC2Pawn* Car = GetPlayerCar();
	if (!Found || !Car)
	{
		Notify(FString::Printf(TEXT("Missao %s indisponivel (%s)"), *Id.ToString(), !Set ? TEXT("sem DA_Missions: rode Tools/bay/write_missions.py") : !Found ? TEXT("nao existe") : TEXT("sem viatura")));
		return false;
	}

	Cleanup();
	Spec = *Found;
	MissionId = Id;
	Clock = 0.0f;
	EndClock = 0.0f;
	NextCheckpoint = 0;
	Lap = 0;
	StoppedFor = 0.0f;
	bStopDone = false;
	ConesKnocked = 0;
	Collisions = 0;
	Intimidation = 0.0f;
	bEvidenceOut = false;
	EvidenceClock = 0.0f;
	TargetsHit = 0;
	TargetsRaised = 0;
	bAutopilot = FParse::Param(FCommandLine::Get(), TEXT("WSPC2MissionAutopilot"));
	bCoop = Car->GetGunnery() && Car->GetGunnery()->HasHumanGunner();

	// the yard's layout, and its cones put back where they stand
	if (!Spec.Layout.IsNone())
	{
		for (TActorIterator<AWSPC2LayoutDirector> It(GetWorld()); It; ++It)
		{
			It->SetActiveLayout(Spec.Layout);
		}
		const FName LayoutTag(*(FString(TEXT("WSPC2Layout.")) + Spec.Layout.ToString()));
		for (TActorIterator<AActor> It(GetWorld()); It; ++It)
		{
			if (It->ActorHasTag(LayoutTag) && It->ActorHasTag(TEXT("WSPC2Physics")))
			{
				Cones.Add(*It);
			}
		}
	}

	// the patrol car at the start, mended, siren off
	PlaceCar(Car, Grounded(Spec.PlayerStart));
	if (UWSPC2VehicleDamageComponent* Damage = Car->GetVehicleDamage())
	{
		Damage->RepairAll();
		CollisionBase = Damage->GetCollisionCount();
	}

	if (Spec.bHasParkedCar)
	{
		Parked = SpawnCar(Spec.ParkedPreset, Spec.ParkedCar, false);
		ParkedHitsBase = Parked && Parked->GetVehicleDamage() ? Parked->GetVehicleDamage()->GetCollisionCount() : 0;
	}

	if (Spec.SuspectRoute.Num() > 1)
	{
		Suspect = SpawnCar(Spec.SuspectPreset, Spec.SuspectStart, true);
		SuspectHitsBase = Suspect && Suspect->GetVehicleDamage() ? Suspect->GetVehicleDamage()->GetCollisionCount() : 0;
	}

	// pop-up targets where the yard's still ones stand (those are hidden while the mission runs)
	for (int32 Index = 0; Index < Spec.Targets.Num(); ++Index)
	{
		const int32 Rise = Spec.TargetRiseCheckpoint.IsValidIndex(Index) ? Spec.TargetRiseCheckpoint[Index] : 0;
		const FVector Facing = Spec.Checkpoints.IsValidIndex(Rise) ? Spec.Checkpoints[Rise] : Spec.PlayerStart.GetLocation();
		const FRotator Yaw(0.0f, (Facing - Spec.Targets[Index]).Rotation().Yaw, 0.0f);
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		Targets.Add(GetWorld()->SpawnActor<AWSPC2PopupTarget>(AWSPC2PopupTarget::StaticClass(), FTransform(Yaw, Spec.Targets[Index]), Params));

		for (TActorIterator<AStaticMeshActor> It(GetWorld()); It; ++It)
		{
			const UStaticMesh* Mesh = It->GetStaticMeshComponent() ? It->GetStaticMeshComponent()->GetStaticMesh() : nullptr;
			if (Mesh && Mesh->GetName().Contains(TEXT("TrainingTarget")) && WSPC2Missions::Dist2D(It->GetActorLocation(), Spec.Targets[Index]) < 500.0f)
			{
				It->SetActorHiddenInGame(true);
				It->SetActorEnableCollision(false);
				HiddenStatics.Add(*It);
			}
		}
	}

	// the weapon issued for this mission, and nothing else
	if (UWSPC2GunneryComponent* Gun = Car->GetGunnery())
	{
		TArray<int32> Mags, Spares;
		Mags.SetNumZeroed((int32)EWSPC2Weapon::Count);
		Spares.SetNumZeroed((int32)EWSPC2Weapon::Count);
		Mags[(int32)Spec.Weapon] = Spec.Magazine;
		Spares[(int32)Spec.Weapon] = bCoop ? Spec.ReserveCoop : Spec.Reserve;
		Gun->SetLoadout(Spec.Weapon == EWSPC2Weapon::None ? 0 : (1 << (int32)Spec.Weapon), Mags, Spares, EWSPC2Weapon::None);
		Gun->ClearLock();
		ShotHandle = Gun->OnShot.AddUObject(this, &AWSPC2MissionDirector::OnShot);
	}

	State = EWSPC2MissionState::Countdown;
	Notify(FString::Printf(TEXT("%s - %s"), *Spec.Title, *Spec.Briefing));
	return true;
}

void AWSPC2MissionDirector::StopMission()
{
	if (State == EWSPC2MissionState::Countdown || State == EWSPC2MissionState::Running)
	{
		End(false, TEXT("interrompida"));
	}
}

void AWSPC2MissionDirector::Cleanup()
{
	if (Suspect)
	{
		Suspect->Destroy();
	}
	if (Parked)
	{
		Parked->Destroy();
	}
	for (AWSPC2PopupTarget* Target : Targets)
	{
		if (Target)
		{
			Target->Destroy();
		}
	}
	for (AActor* Still : HiddenStatics)
	{
		if (Still)
		{
			Still->SetActorHiddenInGame(false);
			Still->SetActorEnableCollision(true);
		}
	}
	Suspect = nullptr;
	Parked = nullptr;
	Targets.Reset();
	HiddenStatics.Reset();
	Cones.Reset();
	ConeStart.Reset();
	bMarker = false;

	if (AWSPC2Pawn* Car = GetPlayerCar())
	{
		if (UWSPC2GunneryComponent* Gun = Car->GetGunnery())
		{
			Gun->OnShot.Remove(ShotHandle);
			Gun->ResetLoadout();
		}
		if (UWSPC2RouteDriver* Auto = Car->FindComponentByClass<UWSPC2RouteDriver>())
		{
			Auto->DestroyComponent();
		}
	}
	ShotHandle.Reset();
}

void AWSPC2MissionDirector::End(bool bWon, const FString& Reason)
{
	State = bWon ? EWSPC2MissionState::Won : EWSPC2MissionState::Failed;
	EndClock = 0.0f;

	if (Suspect)
	{
		if (UWSPC2RouteDriver* Driver = Suspect->FindComponentByClass<UWSPC2RouteDriver>())
		{
			Driver->Stop();
		}
	}
	AWSPC2Pawn* Car = GetPlayerCar();
	if (Car)
	{
		if (UWSPC2RouteDriver* Auto = Car->FindComponentByClass<UWSPC2RouteDriver>())
		{
			Auto->Stop();
		}
	}

	const UWSPC2GunneryComponent* Gun = Car ? Car->GetGunnery() : nullptr;
	const float OwnDamage = Car && Car->GetVehicleDamage() ? 100.0f - Car->GetVehicleDamage()->GetHealthPercent() : 0.0f;
	const float Accuracy = Gun && Gun->GetShotsFired() > 0 ? 100.0f * Gun->GetShotsHit() / Gun->GetShotsFired() : 100.0f;
	bool bMedal = bWon;
	if (bWon && Spec.MedalTime > 0.0f)
	{
		bMedal &= Clock <= Spec.MedalTime && ConesKnocked == 0;
	}
	if (bWon && Spec.MedalMaxDamage > 0.0f)
	{
		bMedal &= OwnDamage <= Spec.MedalMaxDamage;
	}
	if (bWon && Spec.MedalAccuracy > 0.0f)
	{
		bMedal &= Accuracy >= Spec.MedalAccuracy;
	}
	if (bWon && Spec.TargetsNeeded > 0)
	{
		bMedal &= TargetsHit == Spec.Targets.Num();
	}

	Notify(FString::Printf(TEXT("%s - %s | %.1f s | dano proprio %.0f%% | cones %d | precisao %.0f%%%s"),
		bWon ? TEXT("MISSAO CUMPRIDA") : TEXT("MISSAO FALHOU"), *Reason, Clock, OwnDamage, ConesKnocked, Accuracy, bMedal ? TEXT(" | MEDALHA") : TEXT("")));
	StatusLine = FString::Printf(TEXT("%s: %s"), bWon ? TEXT("CUMPRIDA") : TEXT("FALHOU"), *Reason);
	bMarker = false;
}

int32 AWSPC2MissionDirector::CountKnockedCones() const
{
	// knocked: pushed half a metre along the ground or tipped over (the start places are taken when the countdown
	// ends, once the cones have settled on the ground)
	int32 Knocked = 0;
	for (int32 Index = 0; Index < Cones.Num(); ++Index)
	{
		const AActor* Cone = Cones[Index];
		if (Cone && ConeStart.IsValidIndex(Index)
			&& (WSPC2Missions::Dist2D(Cone->GetActorLocation(), ConeStart[Index]) > 50.0f || Cone->GetActorUpVector().Z < 0.7f))
		{
			++Knocked;
		}
	}
	return Knocked;
}

void AWSPC2MissionDirector::OnShot(EWSPC2Weapon Weapon, int32 Hits, AActor* FirstHit)
{
	if (State == EWSPC2MissionState::Running && Spec.NoFireSeconds > 0.0f && Clock < Spec.NoFireSeconds)
	{
		End(false, FString::Printf(TEXT("atirou antes dos %.0f s"), Spec.NoFireSeconds));
	}
}

bool AWSPC2MissionDirector::CheckCommonFailures(AWSPC2Pawn* Car)
{
	const UWSPC2VehicleDamageComponent* Damage = Car->GetVehicleDamage();
	if (Damage && (Damage->IsWrecked() || Damage->GetHealthPercent() <= 0.0f))
	{
		End(false, TEXT("viatura destruida"));
		return true;
	}
	if (Spec.TimeLimit > 0.0f && Clock > Spec.TimeLimit)
	{
		End(false, FString::Printf(TEXT("tempo esgotado (%.0f s)"), Spec.TimeLimit));
		return true;
	}
	for (int32 ZoneIndex = 0; ZoneIndex < Spec.FailZones.Num(); ++ZoneIndex)
	{
		const FVector4& Zone = Spec.FailZones[ZoneIndex];
		if (WSPC2Missions::Dist2D(Car->GetActorLocation(), FVector(Zone.X, Zone.Y, Zone.Z)) < Zone.W)
		{
			End(false, FString::Printf(TEXT("saiu da area do circuito (zona %d)"), ZoneIndex + 1));
			return true;
		}
	}
	return false;
}

void AWSPC2MissionDirector::TickCourse(float DeltaTime, AWSPC2Pawn* Car)
{
	const int32 PerLap = Spec.Checkpoints.Num();
	const int32 Total = PerLap * FMath::Max(1, Spec.Laps);
	const bool bToFinish = NextCheckpoint >= Total;
	const int32 Current = PerLap > 0 ? NextCheckpoint % PerLap : 0;
	const FVector Goal = bToFinish || PerLap == 0 ? Spec.Finish : Spec.Checkpoints[Current];
	const float Radius = bToFinish ? Spec.FinishRadius : Spec.CheckpointRadius;
	const bool bInside = WSPC2Missions::Dist2D(Car->GetActorLocation(), Goal) < Radius && FMath::Abs(Car->GetActorLocation().Z - Goal.Z) < 800.0f;
	UWSPC2RouteDriver* Auto = Car->FindComponentByClass<UWSPC2RouteDriver>();

	Marker = Goal;
	bMarker = true;

	// cones, the instructor's car, other collisions
	const int32 ConesBefore = ConesKnocked;
	ConesKnocked = CountKnockedCones();
	if (ConesKnocked > ConesBefore)
	{
		UE_LOG(LogWSPC2, Log, TEXT("Mission %s: cone knocked (%d) at %.1f s, car at %s"), *MissionId.ToString(), ConesKnocked, Clock, *Car->GetActorLocation().ToString());
	}
	// (the test autopilot cannot turn in the stop's pocket like a driver: its cones and knocks are logged, not failed)
	if (Spec.MaxCones > 0 && ConesKnocked >= Spec.MaxCones && !bAutopilot)
	{
		End(false, FString::Printf(TEXT("%d cones derrubados"), ConesKnocked));
		return;
	}
	if (Parked && Parked->GetVehicleDamage() && Parked->GetVehicleDamage()->GetCollisionCount() > ParkedHitsBase)
	{
		End(false, TEXT("bateu na viatura do instrutor"));
		return;
	}
	if (Spec.bNoCollisions && Car->GetVehicleDamage())
	{
		// a cone knocked over counts as a cone, not a crash
		Collisions = FMath::Max(0, Car->GetVehicleDamage()->GetCollisionCount() - CollisionBase - ConesKnocked);
		if (Collisions > 0 && !bAutopilot)
		{
			End(false, TEXT("bateu"));
			return;
		}
	}

	const FString StopNote = !bToFinish && Current == Spec.StopCheckpoint ? FString::Printf(TEXT(" (PARE %.1f/%.0f s)"), StoppedFor, Spec.StopSeconds) : FString();
	if (Spec.Kind == EWSPC2MissionKind::Elite)
	{
		StatusLine = FString::Printf(TEXT("%s | PC %d/%d%s | %.1f / %.0f s | Alvos %d/%d (min %d) | Cones %d"), *Spec.Title, FMath::Min(NextCheckpoint + 1, Total),
			Total, *StopNote, Clock, Spec.TimeLimit, TargetsHit, Spec.Targets.Num(), Spec.TargetsNeeded, ConesKnocked);
	}
	else
	{
		StatusLine = FString::Printf(TEXT("%s | Volta %d/%d | PC %d/%d | %.1f / %.0f s | Cones %d/%d"), *Spec.Title, FMath::Min(Lap + 1, Spec.Laps), Spec.Laps,
			bToFinish ? PerLap : Current + 1, PerLap, Clock, Spec.TimeLimit, ConesKnocked, Spec.MaxCones);
	}
	if (bToFinish)
	{
		StatusLine += TEXT(" | CHEGADA");
	}

	if (!bToFinish && Current == Spec.StopCheckpoint && !bStopDone)
	{
		// the full stop: still for StopSeconds inside the circle before going on (the autopilot creeps in and stops)
		if (Auto && Auto->IsDriving())
		{
			const float ToStop = WSPC2Missions::Dist2D(Car->GetActorLocation(), Goal);
			Auto->SetSpeedScale(ToStop < Radius + 3000.0f ? 0.3f : 1.0f);
			if (bInside && ToStop < Radius * 0.6f && StoppedFor == 0.0f)
			{
				Auto->HoldFor(Spec.StopSeconds + 1.0f);
			}
		}
		if (bInside)
		{
			StoppedFor = FMath::Abs(Car->GetSpeedKmh()) < 2.0f ? StoppedFor + DeltaTime : 0.0f;
			if (StoppedFor >= Spec.StopSeconds)
			{
				bStopDone = true;
				Notify(TEXT("Parada cumprida"));
				if (Auto)
				{
					Auto->SetSpeedScale(1.0f);
				}
			}
		}
		else if (Spec.Checkpoints.IsValidIndex(Current + 1) && WSPC2Missions::Dist2D(Car->GetActorLocation(), Spec.Checkpoints[Current + 1]) < Spec.CheckpointRadius)
		{
			End(false, TEXT("passou sem parar na Parada Obrigatoria"));
		}
		return;
	}

	if (bInside)
	{
		if (bToFinish)
		{
			if (Spec.TargetsNeeded > 0 && TargetsHit < Spec.TargetsNeeded)
			{
				End(false, FString::Printf(TEXT("acertou %d de %d alvos (minimo %d)"), TargetsHit, Spec.Targets.Num(), Spec.TargetsNeeded));
			}
			else
			{
				End(true, Spec.TargetsNeeded > 0 ? FString::Printf(TEXT("%d de %d alvos"), TargetsHit, Spec.Targets.Num()) : TEXT("percurso completo"));
			}
			return;
		}

		// the targets that rise as this checkpoint is passed (first lap)
		if (NextCheckpoint < PerLap)
		{
			for (int32 Index = 0; Index < Targets.Num(); ++Index)
			{
				if (Spec.TargetRiseCheckpoint.IsValidIndex(Index) && Spec.TargetRiseCheckpoint[Index] == Current && Targets[Index])
				{
					Targets[Index]->Raise(Spec.TargetUpSeconds);
					++TargetsRaised;
				}
			}
		}

		++NextCheckpoint;
		Lap = PerLap > 0 ? NextCheckpoint / PerLap : 0;
		StoppedFor = 0.0f;
		bStopDone = false;
	}

	TargetsHit = 0;
	for (const AWSPC2PopupTarget* Target : Targets)
	{
		TargetsHit += Target && Target->WasHit() ? 1 : 0;
	}

	// the test autopilot shoots: the shotgun out, the lock on a raised target, the trigger pulled now and then
	if (bAutopilot && Spec.Targets.Num() > 0)
	{
		UWSPC2GunneryComponent* Gun = Car->GetGunnery();
		const AWSPC2PopupTarget* Up = nullptr;
		for (const AWSPC2PopupTarget* Target : Targets)
		{
			if (Target && Target->IsUp() && FVector::Dist(Target->GetActorLocation(), Car->GetActorLocation()) < 4500.0f)
			{
				Up = Target;
			}
		}
		if (Gun && Up)
		{
			if (Gun->GetWeapon() == EWSPC2Weapon::None)
			{
				Gun->CycleWeapon(1);
			}
			if (Gun->GetLockedTarget() != Up)
			{
				Gun->ClearLock();
				const FVector From = Car->GetActorLocation() + FVector(0.0f, 0.0f, 200.0f);
				Gun->ToggleLock(From, (Up->GetActorLocation() + FVector(0.0f, 0.0f, 120.0f) - From).GetSafeNormal());
			}
			Gun->SetTrigger(FMath::Fmod(Clock, 1.0f) < 0.5f);
		}
		else if (Gun)
		{
			Gun->SetTrigger(false);
		}
	}

}

void AWSPC2MissionDirector::TickChase(float DeltaTime, AWSPC2Pawn* Car)
{
	if (!Suspect)
	{
		End(false, TEXT("o suspeito sumiu"));
		return;
	}

	const float Distance = FVector::Dist(Car->GetActorLocation(), Suspect->GetActorLocation());
	const UWSPC2VehicleDamageComponent* SuspectDamage = Suspect->GetVehicleDamage();
	const float SuspectHurt = SuspectDamage ? 100.0f - SuspectDamage->GetHealthPercent() : 0.0f;
	UWSPC2RouteDriver* Driver = Suspect->FindComponentByClass<UWSPC2RouteDriver>();
	Marker = Suspect->GetActorLocation();
	bMarker = true;

	// pressure: close behind him, more with the siren; every bump; it fades when he gets away
	const bool bSiren = Car->IsSirenOn();
	if (Distance < 1500.0f)
	{
		Intimidation += (3.0f + (bSiren ? 2.0f : 0.0f)) * DeltaTime;
	}
	else if (Distance < 3000.0f)
	{
		Intimidation += (1.0f + (bSiren ? 1.0f : 0.0f)) * DeltaTime;
	}
	else if (Distance > 5000.0f)
	{
		Intimidation -= 3.0f * DeltaTime;
	}
	if (SuspectDamage && SuspectDamage->GetCollisionCount() > SuspectHitsBase)
	{
		if (Distance < 900.0f)
		{
			Intimidation += 8.0f * (SuspectDamage->GetCollisionCount() - SuspectHitsBase);
		}
		SuspectHitsBase = SuspectDamage->GetCollisionCount();
	}
	Intimidation = FMath::Clamp(Intimidation, 0.0f, 100.0f);

	StatusLine = FString::Printf(TEXT("%s | Distancia %.0f m (max %.0f) | Intimidacao %.0f%% | Dano no alvo %.0f%% | %.0f s%s"), *Spec.Title, Distance / 100.0f,
		Spec.LeashCm / 100.0f, Intimidation, SuspectHurt, Clock, bSiren ? TEXT("") : TEXT(" | ligue a sirene [H]"));

	if (SuspectDamage && (SuspectDamage->IsWrecked() || SuspectDamage->GetHealthPercent() <= 0.0f))
	{
		End(true, TEXT("suspeito imobilizado"));
	}
	else if (Intimidation >= 100.0f)
	{
		End(true, TEXT("o suspeito se rendeu"));
	}
	else if (Spec.LeashCm > 0.0f && Clock > 6.0f && Distance > Spec.LeashCm)
	{
		End(false, FString::Printf(TEXT("perdeu o suspeito (mais de %.0f m)"), Spec.LeashCm / 100.0f));
	}
	else if (Driver && Driver->IsFinished())
	{
		End(false, TEXT("o suspeito chegou ao destino"));
	}
}

void AWSPC2MissionDirector::TickInterception(float DeltaTime, AWSPC2Pawn* Car)
{
	UWSPC2RouteDriver* Driver = Suspect ? Suspect->FindComponentByClass<UWSPC2RouteDriver>() : nullptr;
	const UWSPC2GunneryComponent* Gun = Car->GetGunnery();
	const int32 Fired = Gun ? Gun->GetShotsFired() : 0;
	const int32 Hit = Gun ? Gun->GetShotsHit() : 0;

	if (!bEvidenceOut)
	{
		if (!Suspect)
		{
			End(false, TEXT("o suspeito sumiu"));
			return;
		}
		const float Distance = FVector::Dist(Car->GetActorLocation(), Suspect->GetActorLocation());
		Marker = Suspect->GetActorLocation();
		bMarker = true;
		StatusLine = Clock < Spec.NoFireSeconds
			? FString::Printf(TEXT("%s | Siga o alvo - NAO ATIRE antes de %.0f s | %.0f s | Distancia %.0f m (max %.0f)"), *Spec.Title, Spec.NoFireSeconds, Clock, Distance / 100.0f, Spec.LeashCm / 100.0f)
			: FString::Printf(TEXT("%s | Fogo liberado | %.0f s | Distancia %.0f m (max %.0f) | Tiros %d, acertos %d"), *Spec.Title, Clock, Distance / 100.0f, Spec.LeashCm / 100.0f, Fired, Hit);

		if (Spec.LeashCm > 0.0f && Clock > 6.0f && Distance > Spec.LeashCm)
		{
			End(false, FString::Printf(TEXT("perdeu o suspeito (mais de %.0f m)"), Spec.LeashCm / 100.0f));
			return;
		}
		if (Driver && Driver->IsFinished())
		{
			End(false, TEXT("o suspeito chegou ao destino"));
			return;
		}
		if (Clock >= Spec.EvidenceAt)
		{
			// out of the window, onto the road; he speeds away
			bEvidenceOut = true;
			Evidence = Grounded(FTransform(Suspect->GetActorLocation())).GetLocation();
			EvidenceClock = 0.0f;
			if (Driver)
			{
				Driver->SetSpeedScale(Spec.EvidenceBoost);
			}
			Notify(TEXT("O suspeito jogou a evidencia pela janela! Recupere-a"));
			if (UWSPC2RouteDriver* Auto = Car->FindComponentByClass<UWSPC2RouteDriver>())
			{
				const FVector Here = Car->GetActorLocation();
				Auto->Drive({ FVector2D(Here.X, Here.Y), FVector2D(Evidence.X, Evidence.Y) }, 60.0f);
			}
		}
		return;
	}

	EvidenceClock += DeltaTime;
	const float ToEvidence = WSPC2Missions::Dist2D(Car->GetActorLocation(), Evidence);
	Marker = Evidence;
	bMarker = true;
	StatusLine = FString::Printf(TEXT("%s | Recupere a evidencia: %.0f m | %.0f s restantes | Tiros %d, acertos %d"), *Spec.Title, ToEvidence / 100.0f,
		FMath::Max(0.0f, Spec.EvidenceWindow - EvidenceClock), Fired, Hit);

	if (ToEvidence < Spec.EvidenceRadius)
	{
		End(true, TEXT("evidencia recuperada"));
	}
	else if (EvidenceClock > Spec.EvidenceWindow)
	{
		End(false, TEXT("a evidencia se perdeu"));
	}
}

void AWSPC2MissionDirector::UpdateMarker(float DeltaTime)
{
	if (GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	const bool bShow = bMarker && (State == EWSPC2MissionState::Running || State == EWSPC2MissionState::Countdown);
	if (!bShow)
	{
		if (MarkerMesh)
		{
			MarkerMesh->SetVisibility(false);
		}
		return;
	}

	if (!MarkerMesh)
	{
		MarkerMesh = NewObject<UStaticMeshComponent>(this);
		MarkerMesh->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cone.Cone")));
		MarkerMesh->SetMaterial(0, LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/EngineMaterials/EmissiveMeshMaterial.EmissiveMeshMaterial")));
		MarkerMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		MarkerMesh->SetCastShadow(false);
		MarkerMesh->SetUsingAbsoluteLocation(true);
		MarkerMesh->SetUsingAbsoluteRotation(true);
		MarkerMesh->SetUsingAbsoluteScale(true);
		MarkerMesh->SetWorldScale3D(FVector(1.6f, 1.6f, 2.4f));
		MarkerMesh->SetupAttachment(RootComponent);
		MarkerMesh->RegisterComponent();
	}

	// an upside-down cone hovering and turning over the place to go
	const float Spin = FMath::Fmod(GetWorld()->GetTimeSeconds() * 120.0f, 360.0f);
	MarkerMesh->SetWorldLocationAndRotation(FVector(Marker) + FVector(0.0f, 0.0f, 600.0f), FRotator(180.0f, Spin, 0.0f));
	MarkerMesh->SetVisibility(true);
}

void AWSPC2MissionDirector::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);

	UpdateMarker(DeltaTime);

	if (!HasAuthority() || State == EWSPC2MissionState::Idle)
	{
		return;
	}

	AWSPC2Pawn* Car = GetPlayerCar();
	if (!Car)
	{
		return;
	}

	if (State == EWSPC2MissionState::Won || State == EWSPC2MissionState::Failed)
	{
		EndClock += DeltaTime;
		if (EndClock > WSPC2Missions::EndLingerSeconds)
		{
			Cleanup();
			State = EWSPC2MissionState::Idle;
			if (bAutopilot)
			{
				FPlatformMisc::RequestExit(false);
			}
		}
		return;
	}

	if (State == EWSPC2MissionState::Countdown)
	{
		Clock += DeltaTime;
		WSPC2Missions::Halt(Car);
		WSPC2Missions::Halt(Suspect);
		StatusLine = FString::Printf(TEXT("%s | Prepare-se: %.0f"), *Spec.Title, FMath::CeilToFloat(WSPC2Missions::CountdownSeconds - Clock));
		if (Clock >= WSPC2Missions::CountdownSeconds)
		{
			State = EWSPC2MissionState::Running;
			Clock = 0.0f;
			Notify(TEXT("Valendo!"));
			Car->DoHandbrakeStop();
			if (Suspect)
			{
				Suspect->DoHandbrakeStop();
			}

			// the cones have settled: where they stand now is where they belong
			ConeStart.Reset();
			for (const AActor* Cone : Cones)
			{
				ConeStart.Add(Cone ? Cone->GetActorLocation() : FVector::ZeroVector);
			}
			UE_LOG(LogWSPC2, Log, TEXT("Mission %s: %d cones in the layout"), *MissionId.ToString(), Cones.Num());

			if (Suspect)
			{
				if (UWSPC2RouteDriver* Driver = Suspect->FindComponentByClass<UWSPC2RouteDriver>())
				{
					Driver->Drive(Spec.SuspectRoute, Spec.SuspectSpeedKmh);
				}
			}

			// the test autopilot drives the patrol car along the course (every lap) or the chase route
			if (bAutopilot && Spec.PlayerRoute.Num() > 1)
			{
				UWSPC2RouteDriver* Auto = Car->FindComponentByClass<UWSPC2RouteDriver>();
				if (!Auto)
				{
					Auto = NewObject<UWSPC2RouteDriver>(Car, TEXT("Autopilot"));
					Auto->RegisterComponent();
				}
				TArray<FVector2D> Route;
				const FVector Start = Car->GetActorLocation();
				Route.Add(FVector2D(Start.X, Start.Y));
				const int32 Laps = Spec.Kind == EWSPC2MissionKind::Circuit ? FMath::Max(1, Spec.Laps) : 1;
				for (int32 L = 0; L < Laps; ++L)
				{
					Route.Append(Spec.PlayerRoute);
				}
				if (Spec.Kind == EWSPC2MissionKind::Circuit || Spec.Kind == EWSPC2MissionKind::Elite)
				{
					Route.Add(FVector2D(Spec.Finish.X, Spec.Finish.Y));
				}
				const float Max = Spec.Kind == EWSPC2MissionKind::Circuit || Spec.Kind == EWSPC2MissionKind::Elite ? 55.0f : Spec.SuspectSpeedKmh + 15.0f;
				Auto->SetTight(Spec.Kind == EWSPC2MissionKind::Circuit || Spec.Kind == EWSPC2MissionKind::Elite);
				Auto->Drive(Route, Max);
				Car->SetSiren(true);
			}
		}
		return;
	}

	Clock += DeltaTime;
	if (CheckCommonFailures(Car))
	{
		return;
	}

	switch (Spec.Kind)
	{
	case EWSPC2MissionKind::Circuit:
	case EWSPC2MissionKind::Elite:
		TickCourse(DeltaTime, Car);
		break;
	case EWSPC2MissionKind::Chase:
		TickChase(DeltaTime, Car);
		break;
	case EWSPC2MissionKind::Interception:
		TickInterception(DeltaTime, Car);
		break;
	}

	StatusAge += DeltaTime;
	if (StatusAge > 2.0f)
	{
		StatusAge = 0.0f;
		UE_LOG(LogWSPC2, Log, TEXT("Mission status: %s"), *StatusLine);
	}
}
