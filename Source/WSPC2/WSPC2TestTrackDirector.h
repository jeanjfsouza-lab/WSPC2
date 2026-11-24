// Orchestrates the expanded WSPC2 Test Track showcase: showroom bays for every playable/bonus/military/mission
// vehicle, all 33 live Traffic presets circling the two-lane circuit, Damage Arena targets, and the Repair Pad.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WSPC2TestTrackDirector.generated.h"

class AWSPC2Pawn;
class AWSPC2SportsCar;
struct FWSPC2VehicleProfileSpec;

USTRUCT()
struct FWSPC2ShowroomSpot
{
	GENERATED_BODY()

	UPROPERTY()
	FName PresetId = NAME_None;

	UPROPERTY()
	FString DisplayName;

	UPROPERTY()
	FString RoleGroup;

	UPROPERTY()
	FVector Location = FVector::ZeroVector;

	UPROPERTY()
	TObjectPtr<AActor> DisplayActor;
};

UCLASS()
class WSPC2_API AWSPC2TestTrackDirector : public AActor
{
	GENERATED_BODY()

public:

	AWSPC2TestTrackDirector();

	/** Optional explicit pawn blueprint/class to spawn for AI Traffic and Arena targets. */
	UPROPERTY(EditAnywhere, Category = "TestTrack")
	TSubclassOf<AWSPC2Pawn> VehicleClassOverride;

	/** Trigger radius (cm) around the Green Repair Pad center for auto-repairing the player car. */
	UPROPERTY(EditAnywhere, Category = "TestTrack")
	float RepairPadRadiusCm = 700.0f;

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaTime) override;

	static AWSPC2TestTrackDirector* Get(UWorld* World);

	bool FindNearestShowroomPreset(const FVector& WorldLoc, float MaxDistCm, FName& OutPresetId, FString& OutDisplayName) const;

	int32 GetShowroomCount() const { return ShowroomSpots.Num(); }
	int32 GetExpectedTrafficCount() const { return PendingTrafficPresets.Num(); }
	int32 GetLiveTrafficCount() const;
	int32 GetMovingTrafficCount(float MinSpeedKmh = 8.0f) const;
	int32 GetArenaTargetCount() const;
	AWSPC2SportsCar* GetFirstLiveTrafficCar() const;
	AWSPC2SportsCar* GetFirstArenaTargetCar() const;
	bool IsSpawningFinished() const;

private:

	bool LoadLayoutJson();
	UClass* ResolveSpawnableVehicleClass() const;
	FVector GroundLocation(const FVector& InLoc, float ZOffsetCm) const;
	AActor* SpawnShowroomDisplay(const FWSPC2VehicleProfileSpec& Spec, const FTransform& SlotTransform);
	AWSPC2SportsCar* SpawnLiveVehicle(FName PresetId, const FTransform& Transform, bool bLightweightTraffic);
	void BuildTrafficQueues();
	void BuildShowroomQueue();
	void BuildArenaQueue();
	void StepShowroomSpawning(int32 MaxPerTick);
	void StepTrafficSpawning(int32 MaxPerTick);
	void StepArenaSpawning(int32 MaxPerTick);
	void TickRepairPad(float DeltaTime);

	UPROPERTY()
	TArray<FWSPC2ShowroomSpot> ShowroomSpots;

	TArray<TWeakObjectPtr<AWSPC2SportsCar>> TrafficCars;
	TArray<TWeakObjectPtr<AWSPC2SportsCar>> ArenaTargetCars;

	TArray<FVector> RouteLaneACm;
	TArray<FVector> RouteLaneBCm;
	TArray<FTransform> ShowroomSlotTransforms;
	TArray<FTransform> ArenaTargetTransforms;

	FVector RepairPadCenterCm = FVector(7500.0f, 2600.0f, 200.0f);
	bool bHasRepairPad = false;
	bool bLayoutLoaded = false;

	TArray<FName> PendingShowroomPresets;
	int32 ShowroomSpawnCursor = 0;

	TArray<FName> PendingTrafficPresets;
	int32 TrafficSpawnCursor = 0;

	TArray<FName> PendingArenaPresets;
	int32 ArenaSpawnCursor = 0;

	float RepairCooldown = 0.0f;
};
