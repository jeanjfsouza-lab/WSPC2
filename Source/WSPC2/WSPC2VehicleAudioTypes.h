// Shared types of the vehicle audio: engine archetypes, era DSP, forced induction, telemetry and the
// replicated scrape state.

#pragma once

#include "CoreMinimal.h"
#include "WSPC2VehicleAudioTypes.generated.h"

class USoundWave;

/** Engine families rendered in Engine Simulator (Tools/audio/pipeline), plus the two synthetic ones. */
UENUM(BlueprintType)
enum class EWSPC2EngineArchetype : uint8
{
	V8_EFI_90s,
	V8_Classic_70s,
	V8_Muscle,
	V6_American_90s,
	V6_Mid,
	I4_Econ,
	Boxer4_UEL_Turbo,
	I6_TwinTurbo,
	V12_Exotic,
	Diesel_I4_Truck,
	Diesel_Heavy,
	SyntheticTurbine,
	SyntheticElectric
};

UENUM(BlueprintType)
enum class EWSPC2VehicleEra : uint8
{
	Era_1970s,
	Era_1980s,
	Era_1990s,
	Era_2000s
};

UENUM(BlueprintType)
enum class EWSPC2ForcedInduction : uint8
{
	None,
	Turbo_BOV,
	Turbo_Flutter,
	Supercharger
};

/** What a scraping car body rubs against (picks the scrape loop). */
UENUM(BlueprintType)
enum class EWSPC2ScrapeSurface : uint8
{
	None,
	Asphalt,
	Concrete,
	Metal,
	Plastic,
	Dirt
};

/** One seamless loop of an engine bank: the RPM it was held at on the dyno and the throttle (load). */
USTRUCT(BlueprintType)
struct FWSPC2EngineSamplePoint
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Engine")
	float MeasuredRPM = 1000.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Engine")
	float Load = 0.0f;

	/** Linear gain of this loop on top of the bank's own normalisation */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Engine")
	float NormalizationGain = 1.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Engine")
	TSoftObjectPtr<USoundWave> WaveAsset;
};

/** Character of an era or model, applied at runtime on top of the archetype's bank. */
USTRUCT(BlueprintType)
struct FWSPC2EraDSPConfig
{
	GENERATED_BODY()

	/** Pitch of the whole engine (0.88..1.12) */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "DSP", meta = (ClampMin = "0.88", ClampMax = "1.12"))
	float PitchMultiplier = 1.0f;

	/** Low-pass on the engine heard from outside (Hz); 20000 = open exhaust */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "DSP")
	float ExhaustLowPassHz = 20000.0f;

	/** Low-pass on the engine heard from the cabin view (Hz) */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "DSP")
	float CabinLowPassHz = 1800.0f;

	/** Exhaust rasp; the native voice path has no per-voice distortion, so this only documents the intent */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "DSP")
	float ExhaustDistortion = 0.0f;

	/** Chance of an exhaust pop on a lift-off or upshift at high revs */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "DSP", meta = (ClampMin = "0", ClampMax = "1"))
	float BackfireChance = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "DSP")
	float GearWhineGain = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "DSP")
	float DieselClatterGain = 0.0f;

	/** Bounce off the rev limiter instead of a soft cut */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "DSP")
	bool bHardRevLimiter = false;

	/** Wander of the idle (0..1), the lumpy idle of a carburettor and a big cam */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "DSP", meta = (ClampMin = "0", ClampMax = "1"))
	float IdleInstabilityAmount = 0.0f;
};

/** Engine state for vehicles not driven by a Chaos movement component (SetExternalTelemetry). */
USTRUCT(BlueprintType)
struct FWSPC2VehicleAudioTelemetry
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Telemetry") float RPM = 800.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Telemetry") float MaxRPM = 6000.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Telemetry") float IdleRPM = 800.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Telemetry") float ThrottleLoad = 0.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Telemetry") int32 CurrentGear = 1;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Telemetry") float SpeedKmh = 0.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Telemetry") float BoostPsi = 0.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Telemetry") float MaxTireSlip = 0.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Telemetry") bool bIsInsideCabin = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Telemetry") bool bEngineRunning = true;
};

/** Scrape state found by the server (contact surface and 0..15 intensity), replicated to everyone. */
USTRUCT()
struct FWSPC2ScrapeNet
{
	GENERATED_BODY()

	UPROPERTY()
	uint8 Surface = 0;

	UPROPERTY()
	uint8 Intensity = 0;

	bool operator==(const FWSPC2ScrapeNet& Other) const { return Surface == Other.Surface && Intensity == Other.Intensity; }
	bool operator!=(const FWSPC2ScrapeNet& Other) const { return !(*this == Other); }
};
