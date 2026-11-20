#include "WSPC2Gunnery.h"
#include "WSPC2.h"
#include "WSPC2Pawn.h"
#include "WSPC2GunnerPawn.h"
#include "WSPC2VehicleDamageComponent.h"
#include "WheeledVehiclePawn.h"
#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/DamageType.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInterface.h"
#include "Net/UnrealNetwork.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundBase.h"

namespace WSPC2Guns
{
	// the campaign's weapons (cenarios/00_visao_geral.md): 9 mm pistol of 15, 12-gauge pump shotgun of 7, M4 of 30
	const FWSPC2WeaponSpec Specs[(int32)EWSPC2Weapon::Count] = {
		{ TEXT("Desarmado"), 0, 0, 1.0f, false, 0, 0.0f, 0.0f, 0.0f, 0.0f, false },
		{ TEXT("Pistola 9mm"), 15, 45, 0.25f, false, 1, 1.2f, 15000.0f, 14.0f, 1.6f, false },
		{ TEXT("Escopeta 12"), 7, 21, 0.85f, false, 8, 3.5f, 6000.0f, 7.0f, 2.6f, true },
		{ TEXT("Fuzil M4"), 30, 90, 0.09f, true, 1, 1.8f, 25000.0f, 12.0f, 2.2f, true },
	};

	// where shots leave the car when no officer is drawn (dedicated server): out of the passenger window, car space
	const FVector WindowMuzzle(25.0f, 105.0f, 150.0f);

	// the gunner's arc, as AWSPC2GunnerPawn's (MinYaw..MaxYaw, MinPitch..MaxPitch) with a little slack
	constexpr float MinYaw = -30.0f, MaxYaw = 160.0f, MinPitch = -35.0f, MaxPitch = 40.0f;

	constexpr float LockRangeCm = 20000.0f;     // a vehicle up to 200 m away can be locked
	constexpr float LockKeepCm = 30000.0f;      // and stays locked to 300 m
	constexpr float LockHalfFovDeg = 45.0f;     // within this angle of the middle of the view (half a 90-degree view)
	constexpr float DrawSeconds = 0.6f;         // from drawing the weapon to the first shot (leaning out)
	constexpr int32 NumTracers = 10;
}

FVector UWSPC2GunneryComponent::TargetCentre(const AActor* Target)
{
	// a car's own root (its physics body) is where it is; the bounds of every component can be thrown off by
	// cameras, booms or effects hanging off it
	if (const AWheeledVehiclePawn* Vehicle = Cast<AWheeledVehiclePawn>(Target))
	{
		return Vehicle->GetActorTransform().TransformPosition(FVector(0.0f, 0.0f, 80.0f));
	}
	return Target ? Target->GetComponentsBoundingBox(false).GetCenter() : FVector::ZeroVector;
}

UWSPC2GunneryComponent::UWSPC2GunneryComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	SetIsReplicatedByDefault(true);
}

const FWSPC2WeaponSpec& UWSPC2GunneryComponent::GetSpec(EWSPC2Weapon InWeapon)
{
	const int32 Index = FMath::Clamp((int32)InWeapon, 0, (int32)EWSPC2Weapon::Count - 1);
	return WSPC2Guns::Specs[Index];
}

FString UWSPC2GunneryComponent::GetWeaponName(EWSPC2Weapon InWeapon)
{
	return GetSpec(InWeapon).Name;
}

void UWSPC2GunneryComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(UWSPC2GunneryComponent, Weapon);
	DOREPLIFETIME(UWSPC2GunneryComponent, Magazine);
	DOREPLIFETIME(UWSPC2GunneryComponent, Reserve);
	DOREPLIFETIME(UWSPC2GunneryComponent, AllowedMask);
	DOREPLIFETIME(UWSPC2GunneryComponent, LockedTarget);
	DOREPLIFETIME(UWSPC2GunneryComponent, bReloading);
}

void UWSPC2GunneryComponent::BeginPlay()
{
	Super::BeginPlay();

	if (GetOwner() && GetOwner()->HasAuthority())
	{
		ResetLoadout();
	}
}

AWSPC2Pawn* UWSPC2GunneryComponent::GetCar() const
{
	return Cast<AWSPC2Pawn>(GetOwner());
}

AWSPC2GunnerPawn* UWSPC2GunneryComponent::FindHumanGunner() const
{
	// looked up twice a second: the gunner seat changes rarely
	if (GunnerLookupAge < 0.5f && CachedGunner.IsValid())
	{
		return CachedGunner.Get();
	}

	GunnerLookupAge = 0.0f;
	CachedGunner = nullptr;

	if (UWorld* World = GetWorld())
	{
		for (TActorIterator<AWSPC2GunnerPawn> It(World); It; ++It)
		{
			if (It->GetVehicle() == GetOwner() && It->IsPlayerControlled())
			{
				CachedGunner = *It;
				break;
			}
		}
	}

	return CachedGunner.Get();
}

bool UWSPC2GunneryComponent::HasHumanGunner() const
{
	return FindHumanGunner() != nullptr;
}

int32 UWSPC2GunneryComponent::GetMagazine() const
{
	return Magazine.IsValidIndex((int32)Weapon) ? Magazine[(int32)Weapon] : 0;
}

int32 UWSPC2GunneryComponent::GetReserve() const
{
	return Reserve.IsValidIndex((int32)Weapon) ? Reserve[(int32)Weapon] : 0;
}

void UWSPC2GunneryComponent::ResetLoadout()
{
	TArray<int32> Mags, Spares;
	for (int32 Index = 0; Index < (int32)EWSPC2Weapon::Count; ++Index)
	{
		Mags.Add(WSPC2Guns::Specs[Index].Magazine);
		Spares.Add(WSPC2Guns::Specs[Index].Reserve);
	}
	SetLoadout(0xFF, Mags, Spares, EWSPC2Weapon::None);
}

void UWSPC2GunneryComponent::SetLoadout(int32 InAllowedMask, const TArray<int32>& Magazines, const TArray<int32>& Reserves, EWSPC2Weapon InHolding)
{
	AllowedMask = InAllowedMask | 1;     // holstered is always allowed
	Magazine.SetNumZeroed((int32)EWSPC2Weapon::Count);
	Reserve.SetNumZeroed((int32)EWSPC2Weapon::Count);

	for (int32 Index = 0; Index < (int32)EWSPC2Weapon::Count; ++Index)
	{
		Magazine[Index] = Magazines.IsValidIndex(Index) ? Magazines[Index] : 0;
		Reserve[Index] = Reserves.IsValidIndex(Index) ? Reserves[Index] : 0;
	}

	Weapon = (AllowedMask & (1 << (int32)InHolding)) ? InHolding : EWSPC2Weapon::None;
	bReloading = false;
	ReloadLeft = 0.0f;
	Cooldown = 0.0f;
	DrawnTime = 0.0f;
	ShotsFired = 0;
	ShotsHit = 0;
	OnRep_Weapon();
}

void UWSPC2GunneryComponent::CycleWeapon(int32 Direction)
{
	const int32 Count = (int32)EWSPC2Weapon::Count;
	int32 Index = (int32)Weapon;

	for (int32 Step = 0; Step < Count; ++Step)
	{
		Index = (Index + (Direction >= 0 ? 1 : Count - 1)) % Count;
		if (AllowedMask & (1 << Index))
		{
			break;
		}
	}

	if (Index != (int32)Weapon)
	{
		Weapon = (EWSPC2Weapon)Index;
		bReloading = false;
		ReloadLeft = 0.0f;
		DrawnTime = 0.0f;
		Cooldown = 0.0f;
		OnRep_Weapon();
		UE_LOG(LogWSPC2, Log, TEXT("Gunnery: %s in hand (%d | %d)"), *GetWeaponName(Weapon), GetMagazine(), GetReserve());
	}
}

void UWSPC2GunneryComponent::OnRep_Weapon()
{
	DrawnTime = 0.0f;

	if (Weapon != EWSPC2Weapon::None && GetOwner())
	{
		PlayGunSound(ESound::Draw, GetOwner()->GetActorTransform().TransformPosition(WSPC2Guns::WindowMuzzle));
	}
}

void UWSPC2GunneryComponent::OnRep_Reloading()
{
	if (bReloading && GetOwner())
	{
		PlayGunSound(ESound::Reload, GetOwner()->GetActorTransform().TransformPosition(WSPC2Guns::WindowMuzzle));
	}
}

void UWSPC2GunneryComponent::PlayGunSound(ESound Sound, const FVector& Where, float VolumeScale)
{
	if (GetNetMode() == NM_DedicatedServer || !GetWorld())
	{
		return;
	}

	if (!bSoundsLoaded)
	{
		bSoundsLoaded = true;
		static const TCHAR* Names[(int32)ESound::Count] = { TEXT("Pistol"), TEXT("Shotgun"), TEXT("Rifle"), TEXT("Reload"), TEXT("Draw") };
		int32 Found = 0;
		for (const TCHAR* Name : Names)
		{
			const FString Path = FString::Printf(TEXT("/Game/Audio/Generated/WSPC2_Gun_%s.WSPC2_Gun_%s"), Name, Name);
			USoundBase* Loaded = LoadObject<USoundBase>(nullptr, *Path, nullptr, LOAD_NoWarn | LOAD_Quiet);
			Found += Loaded ? 1 : 0;
			Sounds.Add(Loaded);
		}
		UE_LOG(LogWSPC2, Log, TEXT("Gunnery: %d of %d weapon sounds loaded"), Found, (int32)ESound::Count);

		// shots carry far (full up to 15 m, audible past 400 m); handling noises stay near the car
		auto MakeAttenuation = [this](float FullRadius, float Falloff)
		{
			USoundAttenuation* Attenuation = NewObject<USoundAttenuation>(this);
			FSoundAttenuationSettings& Settings = Attenuation->Attenuation;
			Settings.bAttenuate = true;
			Settings.bSpatialize = true;
			Settings.AttenuationShape = EAttenuationShape::Sphere;
			Settings.AttenuationShapeExtents = FVector(FullRadius);
			Settings.FalloffDistance = Falloff;
			Settings.DistanceAlgorithm = EAttenuationDistanceModel::NaturalSound;
			Settings.dBAttenuationAtMax = -60.0f;
			Settings.NonSpatializedRadiusStart = FullRadius;
			Settings.NonSpatializedRadiusEnd = FullRadius * 0.35f;
			return Attenuation;
		};
		ShotAttenuation = MakeAttenuation(1500.0f, 40000.0f);
		HandlingAttenuation = MakeAttenuation(400.0f, 2500.0f);
	}

	USoundBase* Asset = Sounds.IsValidIndex((int32)Sound) ? Sounds[(int32)Sound].Get() : nullptr;
	if (!Asset)
	{
		return;
	}

	const bool bShot = Sound == ESound::Pistol || Sound == ESound::Shotgun || Sound == ESound::Rifle;
	const float Pitch = bShot ? FMath::FRandRange(0.96f, 1.04f) : 1.0f;
	UGameplayStatics::PlaySoundAtLocation(this, Asset, Where, FRotator::ZeroRotator, VolumeScale * (bShot ? FMath::FRandRange(0.92f, 1.0f) : 1.0f),
		Pitch, 0.0f, bShot ? ShotAttenuation.Get() : HandlingAttenuation.Get());
}

void UWSPC2GunneryComponent::SetTrigger(bool bDown)
{
	bTriggerDown = bDown;
	if (!bDown)
	{
		bFiredSinceDown = false;
	}
}

void UWSPC2GunneryComponent::ClearLock()
{
	LockedTarget = nullptr;
}

void UWSPC2GunneryComponent::ToggleLock(const FVector& ViewLocation, const FVector& ViewDirection)
{
	if (LockedTarget)
	{
		LockedTarget = nullptr;
		UE_LOG(LogWSPC2, Log, TEXT("Gunnery: lock released"));
		return;
	}

	UWorld* World = GetWorld();
	AActor* Owner = GetOwner();
	if (!World || !Owner)
	{
		return;
	}

	const FVector Look = ViewDirection.GetSafeNormal();
	const float MinCos = FMath::Cos(FMath::DegreesToRadians(WSPC2Guns::LockHalfFovDeg));
	AActor* Best = nullptr;
	float BestCos = MinCos;

	FCollisionQueryParams Params(SCENE_QUERY_STAT(WSPC2Lock), false, Owner);
	if (AWSPC2GunnerPawn* Gunner = FindHumanGunner())
	{
		Params.AddIgnoredActor(Gunner);
	}

	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* Candidate = *It;
		if (Candidate == Owner || Candidate->IsActorBeingDestroyed() || Candidate->ActorHasTag(TEXT("WSPC2TargetDown")))
		{
			continue;
		}

		const bool bVehicle = Candidate->IsA<AWheeledVehiclePawn>();
		if (!bVehicle && !Candidate->ActorHasTag(TEXT("WSPC2Target")))
		{
			continue;
		}

		const FVector Centre = TargetCentre(Candidate);
		const FVector ToTarget = Centre - ViewLocation;
		const float Distance = ToTarget.Size();
		const float Cos = Distance > 1.0f ? FVector::DotProduct(ToTarget / Distance, Look) : -1.0f;

		// in sight: nothing solid between the view and the target
		FHitResult Hit;
		const bool bBlocked = World->LineTraceSingleByChannel(Hit, ViewLocation, Centre, ECC_Visibility, Params) && Hit.GetActor() != Candidate;
		UE_LOG(LogWSPC2, Verbose, TEXT("Gunnery: lock candidate %s at %.0f m, %.0f deg off the view%s"), *Candidate->GetName(), Distance / 100.0f,
			FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(Cos, -1.0f, 1.0f))), bBlocked ? *FString::Printf(TEXT(", hidden by %s"), *GetNameSafe(Hit.GetActor())) : TEXT(""));

		if (Distance > WSPC2Guns::LockRangeCm || Distance < 100.0f || Cos <= BestCos || bBlocked)
		{
			continue;
		}

		Best = Candidate;
		BestCos = Cos;
	}

	LockedTarget = Best;
	UE_LOG(LogWSPC2, Log, TEXT("Gunnery: lock %s"), Best ? *Best->GetName() : TEXT("found nothing in view"));
}

void UWSPC2GunneryComponent::GetAim(FVector& OutOrigin, FVector& OutDirection, bool& bOutInArc) const
{
	const AWSPC2Pawn* Car = GetCar();
	if (!Car)
	{
		OutOrigin = FVector::ZeroVector;
		OutDirection = FVector::ForwardVector;
		bOutInArc = false;
		return;
	}

	const FTransform CarTransform = Car->GetActorTransform();
	FVector MuzzleDir;
	if (!Car->GetGunnerMuzzle(OutOrigin, MuzzleDir))
	{
		OutOrigin = CarTransform.TransformPosition(WSPC2Guns::WindowMuzzle);
	}

	if (const AWSPC2GunnerPawn* Gunner = FindHumanGunner())
	{
		OutDirection = Gunner->GetAimRotation().Vector();
	}
	else if (LockedTarget)
	{
		OutDirection = (TargetCentre(LockedTarget) - OutOrigin).GetSafeNormal();
	}
	else
	{
		OutDirection = CarTransform.TransformVectorNoScale(FRotator(0.0f, 20.0f, 0.0f).Vector());
	}

	const FVector Local = CarTransform.InverseTransformVectorNoScale(OutDirection);
	const float Yaw = FMath::RadiansToDegrees(FMath::Atan2(Local.Y, Local.X));
	const float Pitch = FMath::RadiansToDegrees(FMath::Asin(FMath::Clamp(Local.Z, -1.0f, 1.0f)));
	bOutInArc = Yaw >= WSPC2Guns::MinYaw && Yaw <= WSPC2Guns::MaxYaw && Pitch >= WSPC2Guns::MinPitch && Pitch <= WSPC2Guns::MaxPitch;
}

void UWSPC2GunneryComponent::FireOnce()
{
	UWorld* World = GetWorld();
	AActor* Owner = GetOwner();
	const FWSPC2WeaponSpec& Spec = GetSpec(Weapon);

	FVector Origin, Direction;
	bool bInArc = false;
	GetAim(Origin, Direction, bInArc);
	if (!World || !Owner || !bInArc)
	{
		return;
	}

	FCollisionQueryParams Params(SCENE_QUERY_STAT(WSPC2Shot), false, Owner);
	if (AWSPC2GunnerPawn* Gunner = FindHumanGunner())
	{
		Params.AddIgnoredActor(Gunner);
	}

	TArray<FVector_NetQuantize> Ends;
	int32 Hits = 0;
	AActor* FirstHit = nullptr;
	const float Spread = FMath::DegreesToRadians(Spec.SpreadDeg);

	for (int32 Pellet = 0; Pellet < Spec.Pellets; ++Pellet)
	{
		const FVector Dir = FMath::VRandCone(Direction, Spread);
		const FVector End = Origin + Dir * Spec.RangeCm;
		FHitResult Hit;

		if (!World->LineTraceSingleByChannel(Hit, Origin, End, ECC_Visibility, Params))
		{
			UE_LOG(LogWSPC2, Verbose, TEXT("Gunnery: shot from %s along %s hit nothing"), *Origin.ToString(), *Dir.ToString());
			Ends.Add(End);
			continue;
		}

		Ends.Add(Hit.ImpactPoint);
		AActor* HitActor = Hit.GetActor();
		UE_LOG(LogWSPC2, Verbose, TEXT("Gunnery: shot from %s hit %s (%s) at %.0f m"), *Origin.ToString(), *GetNameSafe(HitActor),
			*GetNameSafe(Hit.GetComponent()), Hit.Distance / 100.0f);
		bool bCounts = false;

		if (HitActor)
		{
			if (UWSPC2VehicleDamageComponent* Damage = HitActor->FindComponentByClass<UWSPC2VehicleDamageComponent>())
			{
				Damage->ApplyDirectImpact(Hit.ImpactPoint, Hit.ImpactNormal, Spec.ImpactKmh, 0.0f);

				// low on a wheel: now and then the tyre goes
				const FVector Local = HitActor->GetActorTransform().InverseTransformPosition(Hit.ImpactPoint);
				if (Local.Z < 60.0f && FMath::Abs(FMath::Abs(Local.X) - 145.0f) < 45.0f && FMath::FRand() < 0.3f)
				{
					Damage->PunctureWheel((Local.X >= 0.0f ? 0 : 2) + (Local.Y >= 0.0f ? 1 : 0));
				}
				bCounts = true;
			}

			if (HitActor->ActorHasTag(TEXT("WSPC2Target")))
			{
				bCounts = true;
			}

			// targets (and anything else that listens) take the hit as ordinary point damage
			UGameplayStatics::ApplyPointDamage(HitActor, 1.0f, Dir, Hit, Owner->GetInstigatorController(), Owner, UDamageType::StaticClass());
		}

		if (UPrimitiveComponent* Struck = Hit.GetComponent())
		{
			if (Struck->IsSimulatingPhysics())
			{
				Struck->AddImpulseAtLocation(Dir * 2500.0f, Hit.ImpactPoint);
			}
		}

		if (bCounts)
		{
			++Hits;
			FirstHit = FirstHit ? FirstHit : HitActor;
		}
	}

	++ShotsFired;
	ShotsHit += Hits > 0 ? 1 : 0;
	OnShot.Broadcast(Weapon, Hits, FirstHit);
	MulticastShotFx(Origin, Ends);
}

void UWSPC2GunneryComponent::MulticastShotFx_Implementation(FVector_NetQuantize Start, const TArray<FVector_NetQuantize>& Ends)
{
	AActor* Owner = GetOwner();
	if (!Owner || GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	// tracers: thin unlit bars from the muzzle, drawn for a few frames; a flash at the muzzle
	if (Tracers.Num() == 0)
	{
		UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
		UMaterialInterface* Glow = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/EngineMaterials/EmissiveMeshMaterial.EmissiveMeshMaterial"));

		for (int32 Index = 0; Index < WSPC2Guns::NumTracers; ++Index)
		{
			UStaticMeshComponent* Tracer = NewObject<UStaticMeshComponent>(Owner);
			Tracer->SetStaticMesh(Cube);
			Tracer->SetMaterial(0, Glow);
			Tracer->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			Tracer->SetCastShadow(false);
			Tracer->SetUsingAbsoluteLocation(true);
			Tracer->SetUsingAbsoluteRotation(true);
			Tracer->SetUsingAbsoluteScale(true);
			Tracer->ComponentTags.Add(TEXT("WSPC2Crew"));
			Tracer->SetupAttachment(Owner->GetRootComponent());
			Tracer->RegisterComponent();
			Tracer->SetVisibility(false);
			Tracers.Add(Tracer);
		}

		MuzzleFlash = NewObject<UPointLightComponent>(Owner);
		MuzzleFlash->SetUsingAbsoluteLocation(true);
		MuzzleFlash->SetIntensityUnits(ELightUnits::Candelas);
		MuzzleFlash->SetIntensity(4000.0f);
		MuzzleFlash->SetLightColor(FLinearColor(1.0f, 0.75f, 0.4f));
		MuzzleFlash->SetAttenuationRadius(600.0f);
		MuzzleFlash->SetCastShadows(false);
		MuzzleFlash->SetupAttachment(Owner->GetRootComponent());
		MuzzleFlash->RegisterComponent();
		MuzzleFlash->SetVisibility(false);
	}

	for (int32 Index = 0; Index < Tracers.Num(); ++Index)
	{
		UStaticMeshComponent* Tracer = Tracers[Index];
		if (!Ends.IsValidIndex(Index))
		{
			Tracer->SetVisibility(false);
			continue;
		}

		// the visible stretch starts a little out of the muzzle and stops at the hit (a cube is 100 cm a side)
		const FVector Segment = FVector(Ends[Index]) - FVector(Start);
		const float Length = Segment.Size();
		const FVector From = FVector(Start) + Segment.GetSafeNormal() * FMath::Min(150.0f, Length * 0.2f);
		Tracer->SetWorldLocationAndRotation((From + FVector(Ends[Index])) * 0.5f, Segment.Rotation());
		Tracer->SetWorldScale3D(FVector(FMath::Max(0.05f, (FVector(Ends[Index]) - From).Size() / 100.0f), 0.012f, 0.012f));
		Tracer->SetVisibility(true);
	}

	MuzzleFlash->SetWorldLocation(Start);
	MuzzleFlash->SetVisibility(true);
	TracerAge = 0.0f;

	switch (Weapon)
	{
	case EWSPC2Weapon::Shotgun: PlayGunSound(ESound::Shotgun, Start); break;
	case EWSPC2Weapon::Rifle: PlayGunSound(ESound::Rifle, Start); break;
	default: PlayGunSound(ESound::Pistol, Start); break;
	}
}

void UWSPC2GunneryComponent::UpdateDisplayAim(float DeltaTime)
{
	const AWSPC2Pawn* Car = GetCar();
	FVector2D Target(20.0f, 0.0f);

	if (const AWSPC2GunnerPawn* Gunner = FindHumanGunner())
	{
		Target = Gunner->GetRelativeAimDeg();
	}
	else if (LockedTarget && Car)
	{
		FVector Origin, Direction;
		bool bInArc = false;
		GetAim(Origin, Direction, bInArc);
		const FVector Local = Car->GetActorTransform().InverseTransformVectorNoScale(Direction);
		Target.X = FMath::RadiansToDegrees(FMath::Atan2(Local.Y, Local.X));
		Target.Y = FMath::RadiansToDegrees(FMath::Asin(FMath::Clamp(Local.Z, -1.0f, 1.0f)));
	}

	Target.X = FMath::Clamp(Target.X, WSPC2Guns::MinYaw + 5.0f, WSPC2Guns::MaxYaw - 5.0f);
	Target.Y = FMath::Clamp(Target.Y, WSPC2Guns::MinPitch + 5.0f, WSPC2Guns::MaxPitch - 5.0f);
	const float Alpha = 1.0f - FMath::Exp(-8.0f * DeltaTime);
	DisplayAim += (Target - DisplayAim) * Alpha;
}

void UWSPC2GunneryComponent::UpdateLockMarker(float DeltaTime)
{
	AActor* Owner = GetOwner();
	if (!Owner || GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	if (!LockedTarget)
	{
		if (LockMarker)
		{
			LockMarker->SetVisibility(false);
		}
		return;
	}

	if (!LockMarker)
	{
		LockMarker = NewObject<UStaticMeshComponent>(Owner);
		LockMarker->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cone.Cone")));
		LockMarker->SetMaterial(0, LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/EngineMaterials/EmissiveMeshMaterial.EmissiveMeshMaterial")));
		LockMarker->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		LockMarker->SetCastShadow(false);
		LockMarker->SetUsingAbsoluteLocation(true);
		LockMarker->SetUsingAbsoluteRotation(true);
		LockMarker->SetUsingAbsoluteScale(true);
		LockMarker->SetWorldScale3D(FVector(0.6f, 0.6f, 0.8f));
		LockMarker->ComponentTags.Add(TEXT("WSPC2Crew"));
		LockMarker->SetupAttachment(Owner->GetRootComponent());
		LockMarker->RegisterComponent();
	}

	// an upside-down cone spinning over the target
	MarkerSpin = FMath::Fmod(MarkerSpin + DeltaTime * 180.0f, 360.0f);
	LockMarker->SetWorldLocationAndRotation(TargetCentre(LockedTarget) + FVector(0.0f, 0.0f, 260.0f), FRotator(180.0f, MarkerSpin, 0.0f));
	LockMarker->SetVisibility(true);
}

void UWSPC2GunneryComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	AActor* Owner = GetOwner();
	if (!Owner)
	{
		return;
	}

	GunnerLookupAge += DeltaTime;
	DrawnTime += DeltaTime;

	// on its side or on its roof the gunner comes back in; out again once the car is back on its wheels
	const float Up = Owner->GetActorUpVector().Z;
	bRetracted = bRetracted ? Up < 0.75f : Up < 0.45f;
	if (bRetracted)
	{
		DrawnTime = 0.0f;
	}

	UpdateDisplayAim(DeltaTime);
	UpdateLockMarker(DeltaTime);

	TracerAge += DeltaTime;
	if (TracerAge > 0.06f)
	{
		for (UStaticMeshComponent* Tracer : Tracers)
		{
			Tracer->SetVisibility(false);
		}
		if (MuzzleFlash)
		{
			MuzzleFlash->SetVisibility(false);
		}
	}

	if (!Owner->HasAuthority())
	{
		return;
	}

	// the lock lets go of a target that is gone, down or too far
	if (LockedTarget && (!IsValid(LockedTarget) || LockedTarget->ActorHasTag(TEXT("WSPC2TargetDown"))
		|| FVector::Dist(LockedTarget->GetActorLocation(), Owner->GetActorLocation()) > WSPC2Guns::LockKeepCm))
	{
		LockedTarget = nullptr;
	}

	Cooldown -= DeltaTime;
	const int32 Index = (int32)Weapon;

	if (bReloading)
	{
		ReloadLeft -= DeltaTime;
		if (ReloadLeft <= 0.0f && Magazine.IsValidIndex(Index))
		{
			const int32 Take = FMath::Min(GetSpec(Weapon).Magazine - Magazine[Index], Reserve[Index]);
			Magazine[Index] += Take;
			Reserve[Index] -= Take;
			bReloading = false;
		}
		return;
	}

	if (Weapon == EWSPC2Weapon::None || bRetracted || DrawnTime < WSPC2Guns::DrawSeconds || !bTriggerDown || Cooldown > 0.0f || !Magazine.IsValidIndex(Index))
	{
		return;
	}

	const FWSPC2WeaponSpec& Spec = GetSpec(Weapon);
	if (!Spec.bAutomatic && bFiredSinceDown)
	{
		return;
	}

	if (Magazine[Index] > 0)
	{
		FireOnce();
		--Magazine[Index];
		Cooldown = Spec.Interval;
		bFiredSinceDown = true;
	}

	if (Magazine[Index] == 0 && Reserve[Index] > 0)
	{
		bReloading = true;
		ReloadLeft = Spec.ReloadSeconds;
		OnRep_Reloading();
	}
}

FString UWSPC2GunneryComponent::GetStatusText() const
{
	FString Text = FString::Printf(TEXT("Arma: %s"), *GetWeaponName(Weapon));

	if (Weapon != EWSPC2Weapon::None)
	{
		Text += bReloading ? TEXT("  recarregando") : FString::Printf(TEXT("  %d | %d"), GetMagazine(), GetReserve());
	}

	if (bRetracted)
	{
		Text += TEXT("  (atirador recolhido)");
	}

	if (LockedTarget)
	{
		const float Metres = GetOwner() ? FVector::Dist(LockedTarget->GetActorLocation(), GetOwner()->GetActorLocation()) / 100.0f : 0.0f;
		Text += FString::Printf(TEXT("  |  Alvo travado a %.0f m"), Metres);
	}

	return Text;
}
