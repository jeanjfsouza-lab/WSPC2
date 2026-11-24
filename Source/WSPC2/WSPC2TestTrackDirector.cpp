#include "WSPC2TestTrackDirector.h"
#include "WSPC2.h"
#include "WSPC2Mission.h"
#include "WSPC2Pawn.h"
#include "WSPC2PlayerController.h"
#include "WSPC2SportsCar.h"
#include "WSPC2VehicleAudioComponent.h"
#include "WSPC2VehicleDamageComponent.h"
#include "WSPC2VehicleProfile.h"
#include "Components/BoxComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/PlayerController.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	UStaticMesh* LoadShowroomMesh(const FSoftObjectPath& Path)
	{
		if (!Path.IsValid())
		{
			return nullptr;
		}
		return LoadObject<UStaticMesh>(nullptr, *Path.ToString(), nullptr, LOAD_NoWarn | LOAD_Quiet);
	}

	bool ParseVectorArray(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Key, TArray<FVector>& OutPoints)
	{
		const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
		if (!Obj.IsValid() || !Obj->TryGetArrayField(Key, Arr) || !Arr)
		{
			return false;
		}
		OutPoints.Reset(Arr->Num());
		for (const TSharedPtr<FJsonValue>& Val : *Arr)
		{
			const TArray<TSharedPtr<FJsonValue>>* Coords = nullptr;
			if (Val.IsValid() && Val->TryGetArray(Coords) && Coords && Coords->Num() >= 3)
			{
				const float X = static_cast<float>((*Coords)[0]->AsNumber());
				const float Y = static_cast<float>((*Coords)[1]->AsNumber());
				const float Z = static_cast<float>((*Coords)[2]->AsNumber());
				OutPoints.Add(FVector(X, Y, Z));
			}
		}
		return OutPoints.Num() > 0;
	}

	bool ParseTransformSlots(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Key, TArray<FTransform>& OutTransforms)
	{
		const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
		if (!Obj.IsValid() || !Obj->TryGetArrayField(Key, Arr) || !Arr)
		{
			return false;
		}
		OutTransforms.Reset(Arr->Num());
		for (const TSharedPtr<FJsonValue>& Val : *Arr)
		{
			const TSharedPtr<FJsonObject>* SlotObjPtr = nullptr;
			if (!Val.IsValid() || !Val->TryGetObject(SlotObjPtr) || !SlotObjPtr)
			{
				continue;
			}
			const TArray<TSharedPtr<FJsonValue>>* LocArr = nullptr;
			if (!(*SlotObjPtr)->TryGetArrayField(TEXT("location"), LocArr) || !LocArr || LocArr->Num() < 3)
			{
				continue;
			}
			double Yaw = 0.0;
			(*SlotObjPtr)->TryGetNumberField(TEXT("yaw"), Yaw);
			const FVector Loc(
				static_cast<float>((*LocArr)[0]->AsNumber()),
				static_cast<float>((*LocArr)[1]->AsNumber()),
				static_cast<float>((*LocArr)[2]->AsNumber()));
			OutTransforms.Add(FTransform(FRotator(0.0f, static_cast<float>(Yaw), 0.0f), Loc));
		}
		return OutTransforms.Num() > 0;
	}

	FString DrivetrainLabel(EWSPC2Drivetrain Drive)
	{
		switch (Drive)
		{
		case EWSPC2Drivetrain::FWD: return TEXT("FWD");
		case EWSPC2Drivetrain::AWD: return TEXT("AWD");
		default:                    return TEXT("RWD");
		}
	}
}

AWSPC2TestTrackDirector::AWSPC2TestTrackDirector()
{
	PrimaryActorTick.bCanEverTick = true;
	bReplicates = false;
}

AWSPC2TestTrackDirector* AWSPC2TestTrackDirector::Get(UWorld* World)
{
	if (!World)
	{
		return nullptr;
	}
	for (TActorIterator<AWSPC2TestTrackDirector> It(World); It; ++It)
	{
		if (IsValid(*It))
		{
			return *It;
		}
	}
	return nullptr;
}

void AWSPC2TestTrackDirector::BeginPlay()
{
	Super::BeginPlay();

	if (!HasAuthority())
	{
		return;
	}

	bLayoutLoaded = LoadLayoutJson();
	BuildShowroomQueue();
	BuildTrafficQueues();
	BuildArenaQueue();

	UE_LOG(LogWSPC2, Log, TEXT("TestTrackDirector initialized: layout=%s, ShowroomQueued=%d, TrafficQueued=%d, ArenaQueued=%d, LaneAPts=%d, LaneBPts=%d"),
		bLayoutLoaded ? TEXT("OK") : TEXT("FALLBACK"),
		PendingShowroomPresets.Num(),
		PendingTrafficPresets.Num(),
		PendingArenaPresets.Num(),
		RouteLaneACm.Num(),
		RouteLaneBCm.Num());
}

void AWSPC2TestTrackDirector::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);

	if (!HasAuthority())
	{
		return;
	}

	if (!IsSpawningFinished())
	{
		if (ShowroomSpawnCursor < PendingShowroomPresets.Num())
		{
			StepShowroomSpawning(4);
		}
		else if (TrafficSpawnCursor < PendingTrafficPresets.Num())
		{
			StepTrafficSpawning(2);
		}
		else if (ArenaSpawnCursor < PendingArenaPresets.Num())
		{
			StepArenaSpawning(2);
		}
	}

	TickRepairPad(DeltaTime);
}

bool AWSPC2TestTrackDirector::LoadLayoutJson()
{
	TArray<FString> CandidatePaths;
	CandidatePaths.Add(FPaths::ProjectConfigDir() / TEXT("WSPC2TestTrackLayout.json"));
	CandidatePaths.Add(FPaths::ProjectSavedDir() / TEXT("TestTrack/track_layout.json"));

	FString RawJson;
	FString LoadedPath;
	for (const FString& Path : CandidatePaths)
	{
		if (FPaths::FileExists(Path) && FFileHelper::LoadFileToString(RawJson, *Path))
		{
			LoadedPath = Path;
			break;
		}
	}
	if (LoadedPath.IsEmpty())
	{
		UE_LOG(LogWSPC2, Warning, TEXT("TestTrackDirector: no TestTrack layout JSON found under Config/ or Saved/TestTrack/"));
		return false;
	}

	TSharedPtr<FJsonObject> Root;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(RawJson);
	if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
	{
		UE_LOG(LogWSPC2, Warning, TEXT("TestTrackDirector: failed parsing layout JSON %s"), *LoadedPath);
		return false;
	}

	ParseTransformSlots(Root, TEXT("showroom_spots"), ShowroomSlotTransforms);
	ParseTransformSlots(Root, TEXT("arena_targets"), ArenaTargetTransforms);
	ParseVectorArray(Root, TEXT("route_lane_a_cm"), RouteLaneACm);
	ParseVectorArray(Root, TEXT("route_lane_b_cm"), RouteLaneBCm);

	const TArray<TSharedPtr<FJsonValue>>* PadArr = nullptr;
	if (Root->TryGetArrayField(TEXT("repair_pad_cm"), PadArr) && PadArr && PadArr->Num() >= 3)
	{
		RepairPadCenterCm = FVector(
			static_cast<float>((*PadArr)[0]->AsNumber()),
			static_cast<float>((*PadArr)[1]->AsNumber()),
			static_cast<float>((*PadArr)[2]->AsNumber()));
		bHasRepairPad = true;
	}

	UE_LOG(LogWSPC2, Log, TEXT("TestTrackDirector loaded layout %s: %d showroom bays, %d arena bays, %d+%d lane points, repairPad=(%.0f, %.0f)"),
		*LoadedPath, ShowroomSlotTransforms.Num(), ArenaTargetTransforms.Num(),
		RouteLaneACm.Num(), RouteLaneBCm.Num(), RepairPadCenterCm.X, RepairPadCenterCm.Y);
	return true;
}

UClass* AWSPC2TestTrackDirector::ResolveSpawnableVehicleClass() const
{
	if (UClass* Override = VehicleClassOverride.Get())
	{
		if (!Override->HasAnyClassFlags(CLASS_Abstract) && Override->IsChildOf(AWSPC2SportsCar::StaticClass()))
		{
			return Override;
		}
	}

	if (const UWorld* World = GetWorld())
	{
		for (TActorIterator<AWSPC2SportsCar> It(World); It; ++It)
		{
			if (IsValid(*It) && !It->GetClass()->HasAnyClassFlags(CLASS_Abstract))
			{
				return It->GetClass();
			}
		}

		if (const AGameModeBase* GM = World->GetAuthGameMode())
		{
			if (GM->DefaultPawnClass && !GM->DefaultPawnClass->HasAnyClassFlags(CLASS_Abstract)
				&& GM->DefaultPawnClass->IsChildOf(AWSPC2SportsCar::StaticClass()))
			{
				return GM->DefaultPawnClass;
			}
		}
	}

	UClass* Loaded = LoadClass<AWSPC2Pawn>(nullptr, TEXT("/Game/VehicleTemplate/Blueprints/SportsCar/BP_SportsCar_Pawn.BP_SportsCar_Pawn_C"));
	if (Loaded && !Loaded->HasAnyClassFlags(CLASS_Abstract) && Loaded->IsChildOf(AWSPC2SportsCar::StaticClass()))
	{
		return Loaded;
	}

	return nullptr;
}

FVector AWSPC2TestTrackDirector::GroundLocation(const FVector& InLoc, float ZOffsetCm) const
{
	if (const UWorld* World = GetWorld())
	{
		FHitResult Hit;
		FCollisionQueryParams Params(SCENE_QUERY_STAT(WSPC2DirectorGround), false);
		const FVector Start = InLoc + FVector(0.0f, 0.0f, 450.0f);
		const FVector End = InLoc - FVector(0.0f, 0.0f, 900.0f);
		if (World->LineTraceSingleByChannel(Hit, Start, End, ECC_WorldStatic, Params))
		{
			return Hit.ImpactPoint + FVector(0.0f, 0.0f, ZOffsetCm);
		}
	}
	return InLoc + FVector(0.0f, 0.0f, ZOffsetCm);
}

void AWSPC2TestTrackDirector::BuildShowroomQueue()
{
	PendingShowroomPresets.Reset();
	const TArray<FWSPC2VehicleProfileSpec>& AllPresets = UWSPC2VehicleProfile::GetBuiltinPresets();

	static const TCHAR* GroupOrder[] = {
		TEXT("Builtin"),
		TEXT("Fleet_Playable"),
		TEXT("Fleet_Bonus"),
		TEXT("Military"),
		TEXT("Mission")
	};

	for (const TCHAR* Group : GroupOrder)
	{
		for (const FWSPC2VehicleProfileSpec& Spec : AllPresets)
		{
			if (UWSPC2VehicleProfile::GetNormalizedRoleGroup(Spec) == Group
				&& UWSPC2VehicleProfile::CanLoadPresetAssets(Spec))
			{
				PendingShowroomPresets.Add(Spec.PresetId);
			}
		}
	}
}

void AWSPC2TestTrackDirector::BuildTrafficQueues()
{
	PendingTrafficPresets.Reset();
	UWSPC2VehicleProfile::GetPresetsByRoleGroup(TEXT("Traffic"), PendingTrafficPresets);
}

void AWSPC2TestTrackDirector::BuildArenaQueue()
{
	PendingArenaPresets.Reset();
	static const TCHAR* PreferredTargets[] = {
		TEXT("Zhab_Murphy97_SP"),
		TEXT("Zhab_Duke69"),
		TEXT("Traffic_Kiri86"),
		TEXT("Zhab_MD84_Armored")
	};

	for (const TCHAR* Name : PreferredTargets)
	{
		const FName PresetId(Name);
		const FWSPC2VehicleProfileSpec* Spec = UWSPC2VehicleProfile::FindBuiltinPreset(PresetId);
		if (Spec && UWSPC2VehicleProfile::CanLoadPresetAssets(*Spec))
		{
			PendingArenaPresets.Add(PresetId);
		}
	}

	if (PendingArenaPresets.Num() < 4)
	{
		for (const FWSPC2VehicleProfileSpec& Spec : UWSPC2VehicleProfile::GetBuiltinPresets())
		{
			if (!PendingArenaPresets.Contains(Spec.PresetId) && UWSPC2VehicleProfile::CanLoadPresetAssets(Spec))
			{
				PendingArenaPresets.Add(Spec.PresetId);
				if (PendingArenaPresets.Num() >= 4)
				{
					break;
				}
			}
		}
	}
}

AActor* AWSPC2TestTrackDirector::SpawnShowroomDisplay(const FWSPC2VehicleProfileSpec& Spec, const FTransform& SlotTransform)
{
	UWorld* World = GetWorld();
	UStaticMesh* BodyMesh = LoadShowroomMesh(Spec.BodyMesh);
	if (!World || !BodyMesh)
	{
		return nullptr;
	}

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AActor* Display = World->SpawnActor<AActor>(AActor::StaticClass(), SlotTransform, Params);
	if (!Display)
	{
		return nullptr;
	}

	USceneComponent* Root = NewObject<USceneComponent>(Display, TEXT("ShowroomRoot"));
	Display->SetRootComponent(Root);
	Root->RegisterComponent();
	Display->SetActorTransform(SlotTransform);

	auto AddStaticPart = [Display, Root](const TCHAR* Name, UStaticMesh* Mesh, const FVector& RelLoc, const FRotator& RelRot) -> UStaticMeshComponent*
	{
		if (!Mesh)
		{
			return nullptr;
		}
		UStaticMeshComponent* Comp = NewObject<UStaticMeshComponent>(Display, Name);
		Comp->SetStaticMesh(Mesh);
		Comp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Comp->SetCastShadow(true);
		Comp->SetupAttachment(Root);
		Comp->SetRelativeLocationAndRotation(RelLoc, RelRot);
		Comp->RegisterComponent();
		return Comp;
	};

	AddStaticPart(TEXT("BodyMesh"), BodyMesh, FVector::ZeroVector, Spec.BodyRelativeRotation);
	{
		const FBox BodyBounds = BodyMesh->GetBounds().GetBox().TransformBy(FTransform(Spec.BodyRelativeRotation, FVector::ZeroVector));
		FVector Extent = BodyBounds.GetExtent();
		Extent.X = FMath::Max(Extent.X, 80.0f);
		Extent.Y = FMath::Max(Extent.Y, 60.0f);
		Extent.Z = FMath::Max(Extent.Z, 50.0f);
		FVector Center = BodyBounds.GetCenter();

		UBoxComponent* ShowroomCollider = NewObject<UBoxComponent>(Display, TEXT("ShowroomCollider"));
		ShowroomCollider->SetBoxExtent(Extent, false);
		ShowroomCollider->SetCollisionProfileName(FName("BlockAll"));
		ShowroomCollider->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		ShowroomCollider->SetNotifyRigidBodyCollision(true);
		ShowroomCollider->SetupAttachment(Root);
		ShowroomCollider->SetRelativeLocation(Center);
		ShowroomCollider->RegisterComponent();
	}
	if (UStaticMesh* GlassMesh = LoadShowroomMesh(Spec.GlassMesh))
	{
		AddStaticPart(TEXT("GlassMesh"), GlassMesh, FVector::ZeroVector, Spec.BodyRelativeRotation);
	}

	if (!Spec.bBakedRunningGear)
	{
		UStaticMesh* BaseWheel = Spec.WheelMeshes.IsValidIndex(0) ? LoadShowroomMesh(Spec.WheelMeshes[0]) : nullptr;
		for (int32 i = 0; i < 4; ++i)
		{
			UStaticMesh* WheelMesh = (Spec.WheelMeshes.IsValidIndex(i) ? LoadShowroomMesh(Spec.WheelMeshes[i]) : nullptr);
			if (!WheelMesh && Spec.WheelLayoutMode != EWSPC2WheelLayoutMode::BakedCarSpace)
			{
				WheelMesh = BaseWheel;
			}
			if (!WheelMesh)
			{
				continue;
			}

			FVector WheelLoc = FVector::ZeroVector;
			FRotator WheelRot = FRotator::ZeroRotator;
			if (Spec.WheelLayoutMode == EWSPC2WheelLayoutMode::CenteredOriginPlusX)
			{
				WheelLoc = Spec.WheelOffsetsCm.IsValidIndex(i) ? Spec.WheelOffsetsCm[i] : FVector::ZeroVector;
				WheelRot = FRotator(0.0f, (i % 2 == 1) ? 180.0f : 0.0f, 0.0f);
			}
			else if (Spec.WheelLayoutMode == EWSPC2WheelLayoutMode::CenteredOriginCrownVicLegacy)
			{
				WheelLoc = Spec.WheelOffsetsCm.IsValidIndex(i) ? Spec.WheelOffsetsCm[i] : FVector::ZeroVector;
				WheelRot = FRotator(0.0f, (i % 2 == 1) ? 90.0f : -90.0f, 0.0f);
			}
			// BakedCarSpace leaves WheelLoc/WheelRot at Zero since geometry is already in car space.

			const FString CompName = FString::Printf(TEXT("Wheel_%d"), i);
			AddStaticPart(*CompName, WheelMesh, WheelLoc, WheelRot);
		}
	}

	UTextRenderComponent* Plaque = NewObject<UTextRenderComponent>(Display, TEXT("SpecPlaque"));
	Plaque->SetupAttachment(Root);
	Plaque->SetRelativeLocation(FVector(270.0f, 0.0f, 195.0f));
	Plaque->SetRelativeRotation(FRotator(0.0f, 0.0f, 0.0f));
	Plaque->SetHorizontalAlignment(EHTA_Center);
	Plaque->SetVerticalAlignment(EVRTA_TextCenter);
	Plaque->SetWorldSize(24.0f);
	Plaque->SetTextRenderColor(FColor(255, 225, 95));
	Plaque->SetCastShadow(false);

	const FString RoleGroup = UWSPC2VehicleProfile::GetNormalizedRoleGroup(Spec);
	const FString Counterpart = Spec.RealWorldCounterpart.IsEmpty() ? Spec.PresetId.ToString() : Spec.RealWorldCounterpart;
	const int32 NumGears = FMath::Max(1, Spec.ForwardGearRatios.Num());
	const FString PlaqueText = FString::Printf(
		TEXT("%s [%s]\n%s\n%.0f HP | %.0f Nm | %dG %s | %s"),
		*Spec.DisplayName.ToString(),
		*RoleGroup,
		*Counterpart,
		Spec.RealHorsepower,
		Spec.RealMaxTorqueNm,
		NumGears,
		*DrivetrainLabel(Spec.Drivetrain),
		*Spec.AudioProfile);
	Plaque->SetText(FText::FromString(PlaqueText));
	Plaque->RegisterComponent();

	return Display;
}

AWSPC2SportsCar* AWSPC2TestTrackDirector::SpawnLiveVehicle(FName PresetId, const FTransform& Transform, bool bLightweightTraffic)
{
	UWorld* World = GetWorld();
	UClass* VehicleClass = ResolveSpawnableVehicleClass();
	if (!World || !VehicleClass)
	{
		return nullptr;
	}

	AWSPC2SportsCar* Car = World->SpawnActorDeferred<AWSPC2SportsCar>(
		VehicleClass,
		Transform,
		this,
		nullptr,
		ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn);
	if (!Car)
	{
		return nullptr;
	}

	Car->SetAllowCliVehicleOverride(false);
	Car->FinishSpawning(Transform);
	Car->SetVehiclePreset(PresetId);

	if (bLightweightTraffic && Car->GetVehicleAudio())
	{
		Car->GetVehicleAudio()->SetLightweightTrafficMode(true);
	}
	if (!Car->GetController())
	{
		Car->SpawnDefaultController();
	}
	return Car;
}

void AWSPC2TestTrackDirector::StepShowroomSpawning(int32 MaxPerTick)
{
	int32 Spawned = 0;
	while (ShowroomSpawnCursor < PendingShowroomPresets.Num() && Spawned < MaxPerTick)
	{
		const int32 Index = ShowroomSpawnCursor++;
		const FName PresetId = PendingShowroomPresets[Index];
		const FWSPC2VehicleProfileSpec* Spec = UWSPC2VehicleProfile::FindBuiltinPreset(PresetId);
		if (!Spec)
		{
			continue;
		}

		FTransform SlotTf;
		if (ShowroomSlotTransforms.IsValidIndex(Index))
		{
			SlotTf = ShowroomSlotTransforms[Index];
		}
		else
		{
			const int32 Col = Index % 18;
			const int32 Row = Index / 18;
			SlotTf = FTransform(
				FRotator(0.0f, -90.0f, 0.0f),
				FVector((110.0f + Col * 18.0f) * 100.0f, (32.0f + Row * 26.0f) * 100.0f, 200.0f));
		}

		const FVector Grounded = GroundLocation(SlotTf.GetLocation(), 4.0f);
		SlotTf.SetLocation(Grounded);

		AActor* Display = SpawnShowroomDisplay(*Spec, SlotTf);
		if (Display)
		{
			FWSPC2ShowroomSpot Spot;
			Spot.PresetId = PresetId;
			Spot.DisplayName = Spec->DisplayName.ToString();
			Spot.RoleGroup = UWSPC2VehicleProfile::GetNormalizedRoleGroup(*Spec);
			Spot.Location = Grounded;
			Spot.DisplayActor = Display;
			ShowroomSpots.Add(Spot);
		}
		++Spawned;
	}
}

void AWSPC2TestTrackDirector::StepTrafficSpawning(int32 MaxPerTick)
{
	UClass* VehicleClass = ResolveSpawnableVehicleClass();
	if (!VehicleClass)
	{
		return;
	}

	const int32 TotalTraffic = PendingTrafficPresets.Num();
	if (TotalTraffic == 0)
	{
		return;
	}

	int32 Spawned = 0;
	while (TrafficSpawnCursor < TotalTraffic && Spawned < MaxPerTick)
	{
		const int32 Index = TrafficSpawnCursor++;
		const FName PresetId = PendingTrafficPresets[Index];

		const bool bUseLaneB = (Index % 2) == 1 && RouteLaneBCm.Num() >= 8;
		const TArray<FVector>& Lane = (bUseLaneB || RouteLaneACm.Num() < 8) ? RouteLaneBCm : RouteLaneACm;
		if (Lane.Num() < 8)
		{
			break;
		}

		const int32 LaneCount = bUseLaneB ? FMath::Max(1, TotalTraffic / 2) : FMath::Max(1, (TotalTraffic + 1) / 2);
		const int32 LaneRank = Index / 2;
		const int32 StartIdx = (LaneRank * Lane.Num()) / LaneCount;
		const int32 NextIdx = (StartIdx + 2) % Lane.Num();

		const FVector SpawnPos = GroundLocation(Lane[StartIdx], 35.0f);
		const FVector AheadPos = Lane[NextIdx];
		const float YawDeg = FMath::RadiansToDegrees(FMath::Atan2(AheadPos.Y - SpawnPos.Y, AheadPos.X - SpawnPos.X));
		const FTransform SpawnTf(FRotator(0.0f, YawDeg, 0.0f), SpawnPos);

		AWSPC2SportsCar* Car = SpawnLiveVehicle(PresetId, SpawnTf, true);
		if (Car)
		{
			TArray<FVector2D> RotatedRoute;
			RotatedRoute.Reserve(Lane.Num());
			for (int32 k = 0; k < Lane.Num(); ++k)
			{
				const FVector& P = Lane[(StartIdx + k) % Lane.Num()];
				RotatedRoute.Add(FVector2D(P.X, P.Y));
			}

			UWSPC2RouteDriver* Driver = Car->FindComponentByClass<UWSPC2RouteDriver>();
			if (!Driver)
			{
				Driver = NewObject<UWSPC2RouteDriver>(Car, TEXT("TrafficRouteDriver"));
				Driver->RegisterComponent();
			}
			const float CruiseKmh = bUseLaneB ? 66.0f : 54.0f;
			Driver->SetAvoidTrafficAhead(true);
			Driver->Drive(RotatedRoute, CruiseKmh, true);

			TrafficCars.Add(Car);
		}
		++Spawned;
	}
}

void AWSPC2TestTrackDirector::StepArenaSpawning(int32 MaxPerTick)
{
	if (!ResolveSpawnableVehicleClass())
	{
		return;
	}

	int32 Spawned = 0;
	while (ArenaSpawnCursor < PendingArenaPresets.Num() && Spawned < MaxPerTick)
	{
		const int32 Index = ArenaSpawnCursor++;
		const FName PresetId = PendingArenaPresets[Index];

		FTransform SlotTf;
		if (ArenaTargetTransforms.IsValidIndex(Index))
		{
			SlotTf = ArenaTargetTransforms[Index];
		}
		else
		{
			SlotTf = FTransform(
				FRotator(0.0f, 180.0f, 0.0f),
				FVector((320.0f + Index * 20.0f) * 100.0f, -(32.0f + Index * 20.0f) * 100.0f, 200.0f));
		}

		SlotTf.SetLocation(GroundLocation(SlotTf.GetLocation(), 35.0f));
		AWSPC2SportsCar* Target = SpawnLiveVehicle(PresetId, SlotTf, true);
		if (Target)
		{
			Target->DoHandbrakeStart();
			ArenaTargetCars.Add(Target);
		}
		++Spawned;
	}
}

void AWSPC2TestTrackDirector::TickRepairPad(float DeltaTime)
{
	if (RepairCooldown > 0.0f)
	{
		RepairCooldown = FMath::Max(0.0f, RepairCooldown - DeltaTime);
	}
	if (!bHasRepairPad || RepairCooldown > 0.0f)
	{
		return;
	}

	UWorld* World = GetWorld();
	APlayerController* FirstPC = World ? World->GetFirstPlayerController() : nullptr;
	AWSPC2Pawn* PlayerCar = FirstPC ? Cast<AWSPC2Pawn>(FirstPC->GetPawn()) : nullptr;
	if (!PlayerCar)
	{
		if (AWSPC2PlayerController* WSPC = Cast<AWSPC2PlayerController>(FirstPC))
		{
			PlayerCar = WSPC->GetCurrentVehicle();
		}
	}
	if (!PlayerCar || PlayerCar->GetSpeedKmh() >= 18.0f)
	{
		return;
	}

	if (FVector::Dist2D(PlayerCar->GetActorLocation(), RepairPadCenterCm) > RepairPadRadiusCm)
	{
		return;
	}

	UWSPC2VehicleDamageComponent* Damage = PlayerCar->GetVehicleDamage();
	if (!Damage)
	{
		return;
	}

	const bool bNeedsRepair =
		Damage->GetHealthPercent() < 99.5f
		|| Damage->GetDetachedWheelCount() > 0
		|| Damage->GetPuncturedWheelCount() > 0
		|| Damage->IsWrecked();
	if (!bNeedsRepair)
	{
		return;
	}

	Damage->RepairAll();
	RepairCooldown = 4.0f;

	if (AWSPC2PlayerController* WSPC = Cast<AWSPC2PlayerController>(FirstPC))
	{
		WSPC->ClientNotify(TEXT("Veiculo reparado no Pad Verde!"));
	}
}

bool AWSPC2TestTrackDirector::FindNearestShowroomPreset(const FVector& WorldLoc, float MaxDistCm, FName& OutPresetId, FString& OutDisplayName) const
{
	float BestDistSq = MaxDistCm * MaxDistCm;
	int32 BestIdx = INDEX_NONE;
	for (int32 i = 0; i < ShowroomSpots.Num(); ++i)
	{
		const float DistSq = FVector::DistSquared2D(WorldLoc, ShowroomSpots[i].Location);
		if (DistSq < BestDistSq)
		{
			BestDistSq = DistSq;
			BestIdx = i;
		}
	}

	if (BestIdx == INDEX_NONE)
	{
		return false;
	}

	OutPresetId = ShowroomSpots[BestIdx].PresetId;
	OutDisplayName = ShowroomSpots[BestIdx].DisplayName;
	return true;
}

int32 AWSPC2TestTrackDirector::GetLiveTrafficCount() const
{
	int32 Count = 0;
	for (const TWeakObjectPtr<AWSPC2SportsCar>& WeakCar : TrafficCars)
	{
		if (WeakCar.IsValid())
		{
			++Count;
		}
	}
	return Count;
}

int32 AWSPC2TestTrackDirector::GetMovingTrafficCount(float MinSpeedKmh) const
{
	int32 Count = 0;
	for (const TWeakObjectPtr<AWSPC2SportsCar>& WeakCar : TrafficCars)
	{
		if (const AWSPC2SportsCar* Car = WeakCar.Get())
		{
			if (Car->GetSpeedKmh() >= MinSpeedKmh)
			{
				++Count;
			}
		}
	}
	return Count;
}

int32 AWSPC2TestTrackDirector::GetArenaTargetCount() const
{
	int32 Count = 0;
	for (const TWeakObjectPtr<AWSPC2SportsCar>& WeakCar : ArenaTargetCars)
	{
		if (WeakCar.IsValid())
		{
			++Count;
		}
	}
	return Count;
}

AWSPC2SportsCar* AWSPC2TestTrackDirector::GetFirstLiveTrafficCar() const
{
	for (const TWeakObjectPtr<AWSPC2SportsCar>& WeakCar : TrafficCars)
	{
		if (AWSPC2SportsCar* Car = WeakCar.Get())
		{
			return Car;
		}
	}
	return nullptr;
}

AWSPC2SportsCar* AWSPC2TestTrackDirector::GetFirstArenaTargetCar() const
{
	for (const TWeakObjectPtr<AWSPC2SportsCar>& WeakCar : ArenaTargetCars)
	{
		if (AWSPC2SportsCar* Car = WeakCar.Get())
		{
			return Car;
		}
	}
	return nullptr;
}

bool AWSPC2TestTrackDirector::IsSpawningFinished() const
{
	return ShowroomSpawnCursor >= PendingShowroomPresets.Num()
		&& TrafficSpawnCursor >= PendingTrafficPresets.Num()
		&& ArenaSpawnCursor >= PendingArenaPresets.Num();
}
