// Vehicle sound driven by the Chaos vehicle simulation.
//
// Engine, in order of preference:
//   1. the archetype's bank rendered offline in Engine Simulator (Tools/audio/pipeline): a grid of seamless loops
//      over RPM x load, reached through /Game/Audio/Vehicles/Profiles/DA_Audio_<audio_profile>;
//   2. the studio-recorded CitySample stems (optional, git-ignored);
//   3. the synthetic families in /Game/Audio/Vehicles/Generated (always in the repository).
// Every engine voice starts with the car and loops; only its gain and pitch change while driving (silent voices
// are virtualised with PlayWhenSilent), so nothing restarts. Voices are rebuilt only on spawn, a car change,
// or a level-of-detail change for cars other than the listener's own.
//
// Collisions come from the damage component's replicated impact (impact, metal crunch 15-45 ms later, glass
// shatter and debris 150-350 ms later), so host and clients hear the same hit at the same point. Body scraping is
// found by the server from hit events and replicated as a small state (surface + intensity).

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "WSPC2VehicleAudioTypes.h"
#include "WSPC2VehicleAudioComponent.generated.h"

class UAudioComponent;
class UPrimitiveComponent;
class USoundAttenuation;
class USoundBase;
class USoundConcurrency;
class USoundWave;
class UWSPC2EngineSoundBank;
class UWSPC2VehicleAudioProfile;
class AWSPC2Pawn;
struct FWSPC2VehicleProfileSpec;

UENUM()
enum class EWSPC2EngineSource : uint8
{
	None,
	Bank,
	RecordedStems,
	SyntheticStems
};

UCLASS(Config = Game, ClassGroup = (WSPC2), meta = (BlueprintSpawnableComponent))
class UWSPC2VehicleAudioComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UWSPC2VehicleAudioComponent();

	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
	virtual void TickComponent(float Delta, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	/** Picks the engine source and character for the vehicle profile (audio_profile, idle and max RPM). */
	void ConfigureForVehicleProfile(const FWSPC2VehicleProfileSpec& Spec);

	/** Lighter voice set and distance culling for AI traffic. */
	void SetLightweightTrafficMode(bool bLightweight) { bLightweightTrafficMode = bLightweight; }

	/** Plays a short police/truck airhorn blast at the vehicle. */
	void PlayAirhornBlast();

	/** Engine state for a vehicle not driven by Chaos; used while it keeps arriving (0.5 s timeout). */
	UFUNCTION(BlueprintCallable, Category = "Audio")
	void SetExternalTelemetry(const FWSPC2VehicleAudioTelemetry& Telemetry);

	/** Glass shatter at WorldLocation, with the debris tail 150-350 ms later. */
	UFUNCTION(BlueprintCallable, Category = "Audio")
	void TriggerGlassBreak(FVector WorldLocation);

	UFUNCTION(BlueprintPure, Category = "Audio")
	FString GetActiveEngineFamilyName() const { return ActiveEngineFamily; }

	/** True when the engine plays recorded or rendered loops (an engine-sim bank or the CitySample stems) */
	UFUNCTION(BlueprintPure, Category = "Audio")
	bool IsUsingRealRecordedAudio() const { return EngineSource == EWSPC2EngineSource::Bank || EngineSource == EWSPC2EngineSource::RecordedStems; }

	/** The engine runs on native audio components, not on a MetaSound graph */
	UFUNCTION(BlueprintPure, Category = "Audio")
	bool IsUsingMetaSound() const { return false; }

	UFUNCTION(BlueprintPure, Category = "Audio")
	bool IsUsingEngineBank() const { return EngineSource == EWSPC2EngineSource::Bank; }

	// test and trace accessors
	EWSPC2EngineSource GetEngineSource() const { return EngineSource; }
	FString GetEngineSourceName() const;
	int32 GetAudioLod() const { return CurrentLod; }
	int32 GetEngineVoiceCount() const { return EngineVoices.Num(); }
	int32 GetAudibleEngineVoiceCount() const;
	int32 GetEngineVoicePlayCount() const { return EngineVoicePlayCount; }
	int32 GetEngineVoiceBuilds() const { return EngineVoiceBuilds; }
	float GetSmoothedRpm() const { return SmoothedRpm; }
	float GetSmoothedLoad() const { return SmoothedLoad; }
	int32 GetImpactLayersPlayed() const { return ImpactLayersPlayed; }
	int32 GetScrapeIntensity() const { return ScrapeNet.Intensity; }
	EWSPC2ScrapeSurface GetScrapeSurface() const { return static_cast<EWSPC2ScrapeSurface>(ScrapeNet.Surface); }
	float GetAudibleEngineGain() const { return LastEngineGain; }

	/** Overall loudness of this vehicle */
	UPROPERTY(Config, EditAnywhere, Category = "Audio")
	float MasterVolume = 1.0f;

	/** Loudness of engine, tyres, wind and auxiliary sounds */
	UPROPERTY(Config, EditAnywhere, Category = "Audio")
	float EngineVolume = 1.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Audio")
	float SirenVolume = 0.85f;

	/** Volume of the city ambience heard by the local player */
	UPROPERTY(Config, EditAnywhere, Category = "Audio")
	float AmbienceVolume = 0.25f;

	/** Impulse (kg cm/s) below which a body hit makes no sound, and at which a local bump is heaviest */
	UPROPERTY(Config, EditAnywhere, Category = "Audio")
	float CrashMinImpulse = 95000.0f;

	UPROPERTY(Config, EditAnywhere, Category = "Audio")
	float CrashHeavyImpulse = 1500000.0f;

	/** Use the engine-sim banks when the profile has one (false = the recorded stems, for A/B comparison) */
	UPROPERTY(Config, EditAnywhere, Category = "Audio|Engine")
	bool bUseEngineSimBanks = true;

	/** Gain of the banks on top of their loudness trim (dB) */
	UPROPERTY(Config, EditAnywhere, Category = "Audio|Engine")
	float EngineBankGainDb = 0.0f;

	/** How fast the heard RPM follows the simulation (1/s) */
	UPROPERTY(Config, EditAnywhere, Category = "Audio|Engine")
	float RpmFollowSpeed = 12.0f;

	/** Cars that are not the listener's own use the medium voice set within this distance (cm) */
	UPROPERTY(Config, EditAnywhere, Category = "Audio|LOD")
	float MediumLodDistance = 6000.0f;

	/** Beyond this distance (cm) a car other than the listener's own has no engine voices */
	UPROPERTY(Config, EditAnywhere, Category = "Audio|LOD")
	float CullDistance = 13500.0f;

	/** Gain of every collision layer (impact, crunch, glass, debris, bumps); a heavy crash stacks four of them
	 *  and at full gain the sum hit 0 dBFS through the master limiter (0.56 = -5 dB) */
	UPROPERTY(Config, EditAnywhere, Category = "Audio|Collision")
	float CollisionVolume = 0.56f;

	/** Primary impact recordings from CitySample when they exist (the CC0 set is the fallback) */
	UPROPERTY(Config, EditAnywhere, Category = "Audio|Collision")
	bool bPreferRecordedCrashes = true;

	/** Replicated damage severity (0.04..1.45) above which the impact is medium, heavy, and adds metal crunch */
	UPROPERTY(Config, EditAnywhere, Category = "Audio|Collision")
	float MediumImpactSeverity = 0.3f;

	UPROPERTY(Config, EditAnywhere, Category = "Audio|Collision")
	float HeavyImpactSeverity = 0.7f;

	UPROPERTY(Config, EditAnywhere, Category = "Audio|Collision")
	float CrunchSeverity = 0.35f;

	/** Minimum time between two impacts on the same side of the car (s) */
	UPROPERTY(Config, EditAnywhere, Category = "Audio|Collision")
	float ImpactZoneCooldown = 0.08f;

	/** Tangential speed (cm/s) of a sustained body contact that counts as scraping */
	UPROPERTY(Config, EditAnywhere, Category = "Audio|Collision")
	float ScrapeMinTangentialSpeed = 100.0f;

	/** Tangential speed (cm/s) at which the scrape is at full intensity */
	UPROPERTY(Config, EditAnywhere, Category = "Audio|Collision")
	float ScrapeFullSpeed = 2500.0f;

protected:
	UAudioComponent* MakeLoop(const TCHAR* Path, const TCHAR* Name, float FullVolumeRadius, float FalloffDistance, bool b2D = false);
	UAudioComponent* MakeLoopSound(USoundBase* Sound, const TCHAR* Name, float FullVolumeRadius, float FalloffDistance, bool b2D = false,
		USoundAttenuation* Attenuation = nullptr, USoundConcurrency* Concurrency = nullptr);
	void LoadSharedSounds();
	void ApplyEngineStems();
	void ResolveFamilyFromProfile(const FString& AudioProfileTag);
	void ResolveEngineSource();
	bool LoadSyntheticFamily(const FString& Tag);
	void BindCollisionAudio(AActor* Owner);

	// engine-sim bank voices
	int32 DesiredLod(const AWSPC2Pawn* Car, float ListenerDistance, bool bListenerCar) const;
	void BuildEngineVoices(int32 Lod);
	void DestroyEngineVoices();
	void UpdateBankVoices(float Rpm, float Load, float Gain, float PitchScale, float LowPassHz);
	void UpdateStemVoices(float Rev, float Load, float Gain, float PitchScale, float LowPassHz);

	// extras
	void UpdateExtras(AWSPC2Pawn* Car, float Delta, double Now, float Rpm, float Rev, float Throttle, int32 Gear, float SpeedKmh, bool bListenerCar, float LowPassHz);
	void UpdateCollisions(AWSPC2Pawn* Car, double Now, bool bAudible);
	void PlayImpactLayers(const FVector& Point, float Severity, int32 Zone);
	void PlayOneShot(USoundBase* Sound, const FVector& Location, float Volume, float Pitch, float LowPassHz = 0.0f);
	USoundBase* PickVariant(const TArray<TObjectPtr<USoundBase>>& Set) const;
	void DetectScrapeOnServer(float Delta, double Now);

	UFUNCTION()
	void OnCarHit(AActor* SelfActor, AActor* OtherActor, FVector NormalImpulse, const FHitResult& Hit);

	UFUNCTION()
	void OnComponentHit(UPrimitiveComponent* HitComp, AActor* OtherActor, UPrimitiveComponent* OtherComp, FVector NormalImpulse, const FHitResult& Hit);

	UFUNCTION()
	void OnRep_Scrape();

	// --- engine: engine-sim bank -------------------------------------------------------------------------
	UPROPERTY() TObjectPtr<UWSPC2VehicleAudioProfile> AudioProfile;
	UPROPERTY() TObjectPtr<UWSPC2EngineSoundBank> EngineBank;
	UPROPERTY() TArray<TObjectPtr<UAudioComponent>> EngineVoices;
	UPROPERTY() TObjectPtr<USoundBase> StartSound;
	UPROPERTY() TObjectPtr<USoundBase> ShutdownSound;
	UPROPERTY() TObjectPtr<UAudioComponent> StartVoice;
	TArray<int32> VoiceRpmIndex;
	TArray<int32> VoiceLoadIndex;
	TArray<int32> LodRpmIndices;
	TArray<int32> LodLoadIndices;

	// --- engine: stems (CitySample recordings or synthetic families) --------------------------------------
	UPROPERTY() TObjectPtr<UAudioComponent> EngineIdle;
	UPROPERTY() TObjectPtr<UAudioComponent> EngineLow;
	UPROPERTY() TObjectPtr<UAudioComponent> EngineHigh;
	UPROPERTY() TObjectPtr<UAudioComponent> EnginePinned;

	// Selected SoundWaves for the stem family: [0]=Idle, [1]=Low, [2]=High, [3]=Pinned (optional)
	UPROPERTY() TArray<TObjectPtr<USoundBase>> FamilySounds;

	// --- tyres, wind, sirens, ambience and mechanical loops -----------------------------------------------
	UPROPERTY() TObjectPtr<UAudioComponent> Tyres;
	UPROPERTY() TObjectPtr<UAudioComponent> TyresHeavy;
	UPROPERTY() TObjectPtr<UAudioComponent> TyresDirt;
	UPROPERTY() TObjectPtr<UAudioComponent> Wind;
	UPROPERTY() TObjectPtr<UAudioComponent> SirenWail;
	UPROPERTY() TObjectPtr<UAudioComponent> SirenAlt;
	UPROPERTY() TObjectPtr<UAudioComponent> Ambience;
	UPROPERTY() TObjectPtr<UAudioComponent> TurboSpool;
	UPROPERTY() TObjectPtr<UAudioComponent> SuperchargerWhine;
	UPROPERTY() TObjectPtr<UAudioComponent> GearWhine;
	UPROPERTY() TObjectPtr<UAudioComponent> DieselClatter;
	UPROPERTY() TArray<TObjectPtr<UAudioComponent>> ScrapeLoops;

	// --- one-shot banks -------------------------------------------------------------------------------------
	UPROPERTY() TArray<TObjectPtr<USoundBase>> BackfireSounds;
	UPROPERTY() TArray<TObjectPtr<USoundBase>> AirhornSounds;
	UPROPERTY() TArray<TObjectPtr<USoundBase>> CrashLight;
	UPROPERTY() TArray<TObjectPtr<USoundBase>> CrashMedium;
	UPROPERTY() TArray<TObjectPtr<USoundBase>> CrashHeavy;
	UPROPERTY() TArray<TObjectPtr<USoundBase>> CrunchMedium;
	UPROPERTY() TArray<TObjectPtr<USoundBase>> CrunchHeavy;
	UPROPERTY() TArray<TObjectPtr<USoundBase>> GlassShatter;
	UPROPERTY() TArray<TObjectPtr<USoundBase>> GlassDebris;
	UPROPERTY() TArray<TObjectPtr<USoundBase>> TurboBlowOff;
	UPROPERTY() TArray<TObjectPtr<USoundBase>> TurboFlutter;
	UPROPERTY() TArray<TObjectPtr<USoundBase>> GearClunks;
	UPROPERTY() TObjectPtr<USoundAttenuation> CollisionAttenuation;
	UPROPERTY() TObjectPtr<USoundAttenuation> EngineAttenuation;
	UPROPERTY() TObjectPtr<USoundConcurrency> CollisionConcurrency;
	UPROPERTY() TObjectPtr<USoundConcurrency> TrafficConcurrency;

	// --- replicated scrape ----------------------------------------------------------------------------------
	UPROPERTY(ReplicatedUsing = OnRep_Scrape)
	FWSPC2ScrapeNet ScrapeNet;

	// --- state ----------------------------------------------------------------------------------------------
	EWSPC2EngineSource EngineSource = EWSPC2EngineSource::None;
	FString ActiveAudioProfileStr = TEXT("V8_Cruiser");
	FString ActiveEngineFamily = TEXT("Sedan_Real");
	FWSPC2EraDSPConfig EraDSP;
	EWSPC2ForcedInduction ForcedInduction = EWSPC2ForcedInduction::None;
	float FamilyPitchTrim = 1.0f;
	float FamilyGainTrim = 1.0f;
	float BankGain = 1.0f;
	float ActiveIdleRpm = 720.0f;
	float ActiveMaxRpm = 5750.0f;
	bool bHasBackfire = false;
	bool bElectricQuiet = false;
	bool bIsDiesel = false;
	bool bLightweightTrafficMode = false;
	bool bAudioInitialized = false;
	int32 CurrentLod = -1;
	int32 EngineVoicePlayCount = 0;
	int32 EngineVoiceBuilds = 0;
	int32 ImpactLayersPlayed = 0;
	float CurrentLowPassHz = 0.0f;
	float LastEngineGain = 0.0f;

	// runtime smoothing and triggers
	float SmoothedRpm = 720.0f;
	float SmoothedLoad = 0.0f;
	float SmoothedSlip = 0.0f;
	float SmoothedBoost = 0.0f;
	float SmoothedScrape = 0.0f;
	float PrevThrottle = 0.0f;
	int32 PrevGear = 1;
	double LastCrashTime = -10.0;
	double LastBackfireTime = -10.0;
	double LastBlowOffTime = -10.0;
	double StartSoundTime = -10.0;
	bool bWasStalled = false;
	bool bStartPlayed = false;
	bool bStartFadedOut = false;
	float EngineLowPassApplied = -1.0f;
	float OutsideLowPassApplied = -1.0f;
	EWSPC2ScrapeSurface AudibleScrapeSurface = EWSPC2ScrapeSurface::None;

	// impacts seen through the damage component
	uint8 LastImpactSequence = 0;
	bool bImpactSequenceKnown = false;
	int32 LastGlassStage = 0;
	bool bLastSideGlass = false;
	double LastZoneImpactTime[5] = { -10.0, -10.0, -10.0, -10.0, -10.0 };
	double LastDamageImpactTime = -10.0;
	double PendingBumpTime = -10.0;
	FVector PendingBumpPoint = FVector::ZeroVector;
	float PendingBumpImpulse = 0.0f;

	// server-side scrape detection
	double ScrapeContactTime = -10.0;
	float ScrapeSpeed = 0.0f;
	float ScrapeForce = 0.0f;
	EWSPC2ScrapeSurface ScrapeContactSurface = EWSPC2ScrapeSurface::None;

	// external telemetry
	FWSPC2VehicleAudioTelemetry ExternalTelemetry;
	double ExternalTelemetryTime = -10.0;
};
