// Campaign missions (operations 1 to 4): their data, the director that runs one, the route driver that drives the
// suspects (and the test autopilot), and the pop-up targets of the elite course.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Engine/DataAsset.h"
#include "GameFramework/Actor.h"
#include "WSPC2Gunnery.h"
#include "WSPC2Mission.generated.h"

class AWSPC2Pawn;
class UStaticMeshComponent;

UENUM(BlueprintType)
enum class EWSPC2MissionKind : uint8
{
	/** Laps through checkpoints against the clock, between cones (Op 01) */
	Circuit,
	/** Stop a fleeing car by damage or intimidation, without losing it (Op 02) */
	Chase,
	/** Follow an armed suspect, hold fire, then recover what he throws out (Op 03) */
	Interception,
	/** One lap with a full stop and pop-up targets to shoot (Op 04) */
	Elite
};

/** One mission, in Unreal units (cm, world space of WSPC2_Bay). Written by Tools/bay/write_missions.py. */
USTRUCT(BlueprintType)
struct FWSPC2MissionSpec
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mission") FName Id;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mission") FString Title;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mission") FString Briefing;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mission") EWSPC2MissionKind Kind = EWSPC2MissionKind::Circuit;

	/** Training yard layout to show (AWSPC2LayoutDirector), or none */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mission") FName Layout;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mission") FTransform PlayerStart;

	/** Checkpoints in order (one lap), their radius, how many laps, then the finish */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course") TArray<FVector> Checkpoints;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course") TArray<FString> CheckpointLabels;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course") float CheckpointRadius = 1400.0f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course") int32 Laps = 1;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course") FVector Finish = FVector::ZeroVector;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course") float FinishRadius = 1400.0f;

	/** Seconds allowed (0: none) and the medal's */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course") float TimeLimit = 0.0f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course") float MedalTime = 0.0f;

	/** The checkpoint (index in Checkpoints) where the car must stand still, and for how long */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course") int32 StopCheckpoint = -1;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course") float StopSeconds = 3.0f;

	/** Areas the car must stay out of: x, y, z centre and radius (w), cm */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course") TArray<FVector4> FailZones;

	/** Cones knocked over that fail the mission (0: no limit), and whether any collision fails it */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course") int32 MaxCones = 0;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course") bool bNoCollisions = false;

	/** A parked car not to be touched (the instructor's), with its preset */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Cars") bool bHasParkedCar = false;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Cars") FTransform ParkedCar;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Cars") FName ParkedPreset = FName("SUV");

	/** The suspect: preset, start, route (x, y cm) and top speed */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Cars") FName SuspectPreset;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Cars") FTransform SuspectStart;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Cars") TArray<FVector2D> SuspectRoute;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Cars") float SuspectSpeedKmh = 90.0f;

	/** Losing the suspect: farther than this fails the mission (0: no leash) */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Cars") float LeashCm = 0.0f;

	/** The player's own route (the course's line, or the street route), for the test autopilot */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Cars") TArray<FVector2D> PlayerRoute;

	/** Pop-up targets, how many must be hit, and the checkpoint at which each rises */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Targets") TArray<FVector> Targets;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Targets") TArray<int32> TargetRiseCheckpoint;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Targets") int32 TargetsNeeded = 0;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Targets") float TargetUpSeconds = 8.0f;

	/** Weapons: the one issued (None: unarmed), its rounds, and the spare rounds alone or with a second player */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Weapons") EWSPC2Weapon Weapon = EWSPC2Weapon::None;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Weapons") int32 Magazine = 0;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Weapons") int32 Reserve = 0;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Weapons") int32 ReserveCoop = 0;

	/** Interception: shots before this fail the mission; at EvidenceAt the suspect throws the evidence out and speeds up
	 *  by EvidenceBoost; then EvidenceWindow seconds to pick it up (within EvidenceRadius) */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interception") float NoFireSeconds = 0.0f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interception") float EvidenceAt = 0.0f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interception") float EvidenceBoost = 1.5f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interception") float EvidenceWindow = 70.0f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Interception") float EvidenceRadius = 480.0f;

	/** Medal: own damage at most this percent (Chase, Interception) and accuracy at least this percent */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Medal") float MedalMaxDamage = 0.0f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Medal") float MedalAccuracy = 0.0f;
};

/** Every mission of the campaign that is built. /Game/Bay/Missions/DA_Missions. */
UCLASS(BlueprintType)
class UWSPC2MissionSet : public UDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Mission")
	TArray<FWSPC2MissionSpec> Missions;

	const FWSPC2MissionSpec* Find(FName Id) const;
};

/**
 * Drives a car along a route (x, y points) with its own inputs: pure pursuit for the steering, speed held down for
 * the bends ahead, backing out when stuck. Server only. The suspects use it, and the -WSPC2MissionAutopilot test.
 */
UCLASS(ClassGroup = (WSPC2))
class UWSPC2RouteDriver : public UActorComponent
{
	GENERATED_BODY()

public:

	UWSPC2RouteDriver();

	void Drive(const TArray<FVector2D>& InRoute, float InMaxKmh, bool bInLoop = false);
	void Stop();

	/** Stands still this many seconds, then goes on */
	void HoldFor(float Seconds) { HoldLeft = Seconds; }

	void SetSpeedScale(float Scale) { SpeedScale = Scale; }

	/** Between cones: aims close ahead and takes the bends gently */
	void SetTight(bool bInTight) { bTight = bInTight; }
	bool IsFinished() const { return bFinished; }
	bool IsDriving() const { return Route.Num() > 1 && !bFinished; }
	float GetProgress() const;
	int32 GetIndex() const { return Index; }

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

private:

	TArray<FVector2D> Route;
	TArray<float> Along;      // distance along the route to each point, cm
	float MaxKmh = 80.0f;
	float SpeedScale = 1.0f;
	bool bLoop = false;
	bool bFinished = true;
	int32 Index = 0;
	float StuckTime = 0.0f;
	float ReverseLeft = 0.0f;
	float HoldLeft = 0.0f;
	bool bHandbrake = false;
	bool bTight = false;
	float DebugAge = 0.0f;
};

/** A target board on a post that rises at its moment and falls when hit (or when its time is up). Replicated. */
UCLASS()
class AWSPC2PopupTarget : public AActor
{
	GENERATED_BODY()

public:

	AWSPC2PopupTarget();

	/** Server */
	void Raise(float Seconds);
	void Lower();

	bool IsUp() const { return bUp; }
	bool WasHit() const { return bHit; }

	virtual float TakeDamage(float DamageAmount, struct FDamageEvent const& DamageEvent, AController* EventInstigator, AActor* DamageCauser) override;
	virtual void Tick(float DeltaTime) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

protected:

	UPROPERTY(VisibleAnywhere, Category = "Target")
	TObjectPtr<USceneComponent> Hinge;

	UPROPERTY(VisibleAnywhere, Category = "Target")
	TObjectPtr<UStaticMeshComponent> Board;

	UPROPERTY(VisibleAnywhere, Category = "Target")
	TObjectPtr<UStaticMeshComponent> Post;

	UPROPERTY(Replicated)
	bool bUp = false;

	UPROPERTY(Replicated)
	bool bHit = false;

	float UpLeft = 0.0f;
	float Angle = -88.0f;
};

UENUM()
enum class EWSPC2MissionState : uint8
{
	Idle,
	Countdown,
	Running,
	Won,
	Failed
};

/**
 * Runs one mission at a time on the server (started with the PlayerController's Mission console command or
 * -WSPC2Mission=<Id>): puts the patrol car at the start, shows the yard's layout, spawns the suspect, the parked car or
 * the targets, issues the weapon, keeps the score and decides. Replicates a status line and the next marker; the
 * players' controllers show them.
 */
UCLASS()
class AWSPC2MissionDirector : public AActor
{
	GENERATED_BODY()

public:

	AWSPC2MissionDirector();

	/** The director of this world, made on the server when missing */
	static AWSPC2MissionDirector* Get(UWorld* World, bool bCreate);

	/** Server */
	bool StartMission(FName Id);
	void StopMission();

	EWSPC2MissionState GetState() const { return State; }
	const FString& GetStatusLine() const { return StatusLine; }
	FName GetMissionId() const { return MissionId; }

	virtual void Tick(float DeltaTime) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

protected:

	UPROPERTY(Replicated)
	EWSPC2MissionState State = EWSPC2MissionState::Idle;

	UPROPERTY(Replicated)
	FString StatusLine;

	UPROPERTY(Replicated)
	FName MissionId;

	/** The next place to go (a cone spins over it), when bMarker */
	UPROPERTY(Replicated)
	FVector_NetQuantize Marker;

	UPROPERTY(Replicated)
	bool bMarker = false;

	UPROPERTY(Transient)
	TObjectPtr<UStaticMeshComponent> MarkerMesh;

	UPROPERTY(Transient)
	TObjectPtr<AWSPC2Pawn> Suspect;

	UPROPERTY(Transient)
	TObjectPtr<AWSPC2Pawn> Parked;

	UPROPERTY(Transient)
	TArray<TObjectPtr<AWSPC2PopupTarget>> Targets;

	UPROPERTY(Transient)
	TArray<TObjectPtr<AActor>> Cones;

	UPROPERTY(Transient)
	TArray<TObjectPtr<AActor>> HiddenStatics;

private:

	AWSPC2Pawn* GetPlayerCar() const;
	void Notify(const FString& Message) const;
	void End(bool bWon, const FString& Reason);
	void Cleanup();
	AWSPC2Pawn* SpawnCar(FName Preset, const FTransform& At, bool bDriven);
	void PlaceCar(AWSPC2Pawn* Car, const FTransform& At) const;
	FTransform Grounded(const FTransform& At) const;
	void TickCourse(float DeltaTime, AWSPC2Pawn* Car);
	void TickChase(float DeltaTime, AWSPC2Pawn* Car);
	void TickInterception(float DeltaTime, AWSPC2Pawn* Car);
	bool CheckCommonFailures(AWSPC2Pawn* Car);
	int32 CountKnockedCones() const;
	void UpdateMarker(float DeltaTime);
	void OnShot(EWSPC2Weapon Weapon, int32 Hits, AActor* FirstHit);

	FWSPC2MissionSpec Spec;
	float Clock = 0.0f;
	float EndClock = 0.0f;
	float StatusAge = 0.0f;
	int32 NextCheckpoint = 0;
	int32 Lap = 0;
	bool bAtFinish = false;
	float StoppedFor = 0.0f;
	bool bStopDone = false;
	int32 ConesKnocked = 0;
	int32 CollisionBase = 0;
	int32 Collisions = 0;
	int32 ParkedHitsBase = 0;
	int32 SuspectHitsBase = 0;
	float Intimidation = 0.0f;
	bool bEvidenceOut = false;
	FVector Evidence = FVector::ZeroVector;
	float EvidenceClock = 0.0f;
	int32 TargetsHit = 0;
	int32 TargetsRaised = 0;
	TArray<FVector> ConeStart;
	bool bAutopilot = false;
	bool bCoop = false;
	FDelegateHandle ShotHandle;
};
