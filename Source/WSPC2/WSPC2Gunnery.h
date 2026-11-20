// The gunner's weapons: which one is in his hands, its rounds, the target lock and the shots (server-authoritative).

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Engine/NetSerialization.h"
#include "WSPC2Gunnery.generated.h"

class AWSPC2Pawn;
class AWSPC2GunnerPawn;
class UStaticMeshComponent;
class UPointLightComponent;
class USoundBase;
class USoundAttenuation;

/** What the gunner holds. None: nothing, and he sits inside the car. */
UENUM(BlueprintType)
enum class EWSPC2Weapon : uint8
{
	None = 0,
	Pistol,
	Shotgun,
	Rifle,
	Count UMETA(Hidden)
};

/** Fixed numbers of one weapon (the campaign's: 9 mm pistol, 12-gauge shotgun, M4) */
struct FWSPC2WeaponSpec
{
	const TCHAR* Name = TEXT("");
	int32 Magazine = 0;          // rounds per magazine
	int32 Reserve = 0;           // spare rounds in free play
	float Interval = 0.3f;       // seconds between shots
	bool bAutomatic = false;     // fires while the trigger is held
	int32 Pellets = 1;
	float SpreadDeg = 1.0f;      // half-angle of each pellet's cone
	float RangeCm = 10000.0f;
	float ImpactKmh = 10.0f;     // how hard one hit lands on a car (UWSPC2VehicleDamageComponent::ApplyDirectImpact)
	float ReloadSeconds = 2.0f;
	bool bLongGun = false;       // held at the shoulder (shotgun, rifle) rather than out in both hands
};

/** Server: a shot went off. Hits counts pellets that struck something solid that can be hurt (a car or a target). */
DECLARE_MULTICAST_DELEGATE_ThreeParams(FWSPC2OnShot, EWSPC2Weapon /*Weapon*/, int32 /*Hits*/, AActor* /*FirstHitActor*/);

/**
 * Lives on the car. The gunner (in co-op the second player, alone the driver for him) picks the weapon with the
 * D-pad's left and right; with a weapon in his hands the gunner leans out of the window, and he comes back in when the
 * car rolls over. Alone, D-pad up locks the aim on a vehicle in view and the gunner shoots at it. State replicates;
 * players ask through AWSPC2PlayerController's Server RPCs.
 */
UCLASS(ClassGroup = (WSPC2), meta = (BlueprintSpawnableComponent))
class UWSPC2GunneryComponent : public UActorComponent
{
	GENERATED_BODY()

public:

	UWSPC2GunneryComponent();

	static const FWSPC2WeaponSpec& GetSpec(EWSPC2Weapon InWeapon);
	static FString GetWeaponName(EWSPC2Weapon InWeapon);

	/** Where to aim at a target: a car's body (80 cm over its origin), anything else its bounds' middle */
	static FVector TargetCentre(const AActor* Target);

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	// ---- server ----

	/** Next (+1) or previous (-1) weapon among the allowed ones, holstered included */
	void CycleWeapon(int32 Direction);

	/** Trigger pressed or released */
	void SetTrigger(bool bDown);

	/** Locks on the vehicle (or target) nearest the middle of the given view, or drops the lock */
	void ToggleLock(const FVector& ViewLocation, const FVector& ViewDirection);

	void ClearLock();

	/** Missions: the weapons allowed (bit 1 << EWSPC2Weapon) and the rounds of each, magazine and spare */
	void SetLoadout(int32 InAllowedMask, const TArray<int32>& Magazines, const TArray<int32>& Reserves, EWSPC2Weapon InHolding);

	/** Free play: every weapon, full rounds, nothing in hand */
	void ResetLoadout();

	/** Shots and hits since the last loadout (accuracy) */
	int32 GetShotsFired() const { return ShotsFired; }
	int32 GetShotsHit() const { return ShotsHit; }

	FWSPC2OnShot OnShot;

	// ---- everyone ----

	EWSPC2Weapon GetWeapon() const { return Weapon; }
	AActor* GetLockedTarget() const { return LockedTarget; }
	int32 GetMagazine() const;
	int32 GetReserve() const;
	bool IsReloading() const { return bReloading; }

	/** The car is on its side or roof: the gunner is back inside */
	bool IsRetracted() const { return bRetracted; }

	/** A second player rides as gunner of this car */
	bool HasHumanGunner() const;

	/** Where the gunner's body points: yaw (+ right of the nose) and pitch in degrees, relative to the car */
	FVector2D GetDisplayAim() const { return DisplayAim; }

	/** One line for the HUD: weapon, rounds, lock */
	FString GetStatusText() const;

protected:

	virtual void BeginPlay() override;

	UPROPERTY(ReplicatedUsing = OnRep_Weapon)
	EWSPC2Weapon Weapon = EWSPC2Weapon::None;

	UPROPERTY(Replicated)
	TArray<int32> Magazine;

	UPROPERTY(Replicated)
	TArray<int32> Reserve;

	UPROPERTY(Replicated)
	int32 AllowedMask = 0xFF;

	UPROPERTY(Replicated)
	TObjectPtr<AActor> LockedTarget;

	UPROPERTY(ReplicatedUsing = OnRep_Reloading)
	bool bReloading = false;

	UFUNCTION()
	void OnRep_Weapon();

	UFUNCTION()
	void OnRep_Reloading();

	/** Draws the shots on every machine: tracers from the muzzle to where each pellet stopped, a flash */
	UFUNCTION(NetMulticast, Unreliable)
	void MulticastShotFx(FVector_NetQuantize Start, const TArray<FVector_NetQuantize>& Ends);

	AWSPC2Pawn* GetCar() const;
	AWSPC2GunnerPawn* FindHumanGunner() const;

	/** Where the shots start and where they go (world), per who aims: the second player, the lock, or ahead */
	void GetAim(FVector& OutOrigin, FVector& OutDirection, bool& bOutInArc) const;
	void FireOnce();
	void UpdateDisplayAim(float DeltaTime);
	void UpdateLockMarker(float DeltaTime);

	FVector2D DisplayAim = FVector2D(20.0f, 0.0f);
	bool bRetracted = false;
	float Cooldown = 0.0f;
	float ReloadLeft = 0.0f;
	float DrawnTime = 0.0f;
	bool bTriggerDown = false;
	bool bFiredSinceDown = false;
	int32 ShotsFired = 0;
	int32 ShotsHit = 0;
	mutable TWeakObjectPtr<AWSPC2GunnerPawn> CachedGunner;
	mutable float GunnerLookupAge = 10.0f;

	/** Tracers and flash, made on first use (cosmetic) */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> Tracers;

	UPROPERTY(Transient)
	TObjectPtr<UPointLightComponent> MuzzleFlash;

	UPROPERTY(Transient)
	TObjectPtr<UStaticMeshComponent> LockMarker;

	/** Sounds (Tools/audio/make_gunshots.py), loaded on first use; missing assets leave the weapons silent */
	enum class ESound : uint8 { Pistol, Shotgun, Rifle, Reload, Draw, Count };
	void PlayGunSound(ESound Sound, const FVector& Where, float VolumeScale = 1.0f);

	UPROPERTY(Transient)
	TArray<TObjectPtr<USoundBase>> Sounds;

	UPROPERTY(Transient)
	TObjectPtr<USoundAttenuation> ShotAttenuation;

	UPROPERTY(Transient)
	TObjectPtr<USoundAttenuation> HandlingAttenuation;

	bool bSoundsLoaded = false;

	float TracerAge = 1.0f;
	float MarkerSpin = 0.0f;
};
