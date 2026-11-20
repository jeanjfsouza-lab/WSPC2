// Vehicle sound: engine, tyres, wind, crashes and siren, driven by the Chaos vehicle simulation.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "WSPC2VehicleAudioComponent.generated.h"

class UAudioComponent;
class USoundBase;

/**
 *  Plays the patrol car's sounds:
 *  - engine: three steady recordings (idle, low revs, high revs) crossfaded and pitched by the engine's real RPM
 *  - tyres: a squeal loop that follows wheel slip and skid, heavier when the car slides hard
 *  - road noise and wind rising with speed
 *  - crash one-shots scaled by the impact
 *  - siren loop while the siren is on
 *  - for the local player only, a quiet city ambience
 *
 *  Every loop is attached to the car and keeps running while silent, so a sound that fades back in
 *  carries on from where it was instead of starting over.
 */
UCLASS(ClassGroup = (WSPC2), meta = (BlueprintSpawnableComponent))
class UWSPC2VehicleAudioComponent : public UActorComponent
{
	GENERATED_BODY()

public:

	UWSPC2VehicleAudioComponent();

	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
	virtual void TickComponent(float Delta, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** Overall loudness of this vehicle */
	UPROPERTY(EditAnywhere, Category = "Audio")
	float MasterVolume = 1.0f;

	/** Loudness of the engine, tyres and wind relative to the rest */
	UPROPERTY(EditAnywhere, Category = "Audio")
	float EngineVolume = 1.0f;

	UPROPERTY(EditAnywhere, Category = "Audio")
	float SirenVolume = 0.8f;

	/** Volume of the city ambience heard by the local player */
	UPROPERTY(EditAnywhere, Category = "Audio")
	float AmbienceVolume = 0.25f;

	/** Impulse (kg cm/s) below which a hit makes no sound, and at which it is heaviest */
	UPROPERTY(EditAnywhere, Category = "Audio")
	float CrashMinImpulse = 95000.0f;

	UPROPERTY(EditAnywhere, Category = "Audio")
	float CrashHeavyImpulse = 1500000.0f;

protected:

	/**
	 * Starts a silent, looping sound on the car.
	 * FullVolumeRadius is how far from the car it stays at full volume, FalloffDistance how much further it carries (cm).
	 * b2D plays it in the listener's head instead (ambience).
	 */
	UAudioComponent* MakeLoop(const TCHAR* Path, const TCHAR* Name, float FullVolumeRadius, float FalloffDistance, bool b2D = false);

	UFUNCTION()
	void OnCarHit(AActor* SelfActor, AActor* OtherActor, FVector NormalImpulse, const FHitResult& Hit);

	UPROPERTY() TObjectPtr<UAudioComponent> EngineIdle;
	UPROPERTY() TObjectPtr<UAudioComponent> EngineLow;
	UPROPERTY() TObjectPtr<UAudioComponent> EngineHigh;
	UPROPERTY() TObjectPtr<UAudioComponent> Tyres;
	UPROPERTY() TObjectPtr<UAudioComponent> TyresHeavy;
	UPROPERTY() TObjectPtr<UAudioComponent> Wind;
	UPROPERTY() TObjectPtr<UAudioComponent> Siren;
	UPROPERTY() TObjectPtr<UAudioComponent> Ambience;

	UPROPERTY() TArray<TObjectPtr<USoundBase>> CrashLight;
	UPROPERTY() TArray<TObjectPtr<USoundBase>> CrashMedium;
	UPROPERTY() TArray<TObjectPtr<USoundBase>> CrashHeavy;

	float SmoothedRpm = 0.0f;
	float SmoothedLoad = 0.0f;
	float SmoothedSlip = 0.0f;
	double LastCrashTime = -10.0;
};
