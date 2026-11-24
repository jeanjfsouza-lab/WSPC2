// Vehicle sound driven by the Chaos vehicle simulation: engine-sim banks (or recorded / synthetic stems),
// tyres by surface, wind, turbo, gears, diesel knock, backfires, sirens, horns, and layered collisions from
// the replicated damage events. See the header for the overall design.

#include "WSPC2VehicleAudioComponent.h"
#include "WSPC2Pawn.h"
#include "WSPC2VehicleProfile.h"
#include "WSPC2VehicleAudioProfile.h"
#include "WSPC2VehicleDamageComponent.h"
#include "WSPC2.h"
#include "Components/AudioComponent.h"
#include "Components/PrimitiveComponent.h"
#include "ChaosWheeledVehicleMovementComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Net/UnrealNetwork.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundBase.h"
#include "Sound/SoundConcurrency.h"
#include "Sound/SoundWave.h"
#include "Engine/World.h"
#include "TimerManager.h"
#include "UObject/UnrealType.h"

namespace
{
	// Studio-recorded engine sets (CitySample SoundWaves, optional and git-ignored)
	const TCHAR* SedanIdlePath      = TEXT("/Game/Audio/SoundWaves/NPC/Sedan/sfx_LeaveBehind_Veh_Npc_Sedan_Drive_Idle_lp_01.sfx_LeaveBehind_Veh_Npc_Sedan_Drive_Idle_lp_01");
	const TCHAR* SedanLowPath       = TEXT("/Game/Audio/SoundWaves/NPC/Sedan/sfx_LeaveBehind_Veh_Npc_Sedan_Drive_Low_lp_01.sfx_LeaveBehind_Veh_Npc_Sedan_Drive_Low_lp_01");
	const TCHAR* SedanHighPath      = TEXT("/Game/Audio/SoundWaves/NPC/Sedan/sfx_LeaveBehind_Veh_Npc_Sedan_Drive_High_lp_01.sfx_LeaveBehind_Veh_Npc_Sedan_Drive_High_lp_01");
	const TCHAR* SedanPinnedPath    = TEXT("/Game/Audio/Vehicles/Veh_Shared/wav/sfx_Veh_Shared_RPM_Pinned_Sedan_lp_01.sfx_Veh_Shared_RPM_Pinned_Sedan_lp_01");
	const TCHAR* SedanIdleAltPath   = TEXT("/Game/Audio/Vehicles/Metasounds/Sedan/wav/sfx_Veh_Sedan_Engine_Idle_lp.sfx_Veh_Sedan_Engine_Idle_lp");

	const TCHAR* SportsIdlePath     = TEXT("/Game/Audio/SoundWaves/NPC/Sports/sfx_LeaveBehind_Veh_Npc_Sports_Drive_Idle_lp_01.sfx_LeaveBehind_Veh_Npc_Sports_Drive_Idle_lp_01");
	const TCHAR* SportsLowPath      = TEXT("/Game/Audio/SoundWaves/NPC/Sports/sfx_LeaveBehind_Veh_Npc_Sports_Drive_Low_lp_01.sfx_LeaveBehind_Veh_Npc_Sports_Drive_Low_lp_01");
	const TCHAR* SportsHighPath     = TEXT("/Game/Audio/SoundWaves/NPC/Sports/sfx_LeaveBehind_Veh_Npc_Sports_Drive_High_lp_01.sfx_LeaveBehind_Veh_Npc_Sports_Drive_High_lp_01");
	const TCHAR* SportsPinnedPath   = TEXT("/Game/Audio/Vehicles/Metasounds/SportsCar/wavs/sfx_Veh_Sport_RPM_Pinned_lp_01.sfx_Veh_Sport_RPM_Pinned_lp_01");

	const TCHAR* SuvIdlePath        = TEXT("/Game/Audio/SoundWaves/NPC/SUV/sfx_LeaveBehind_Veh_Npc_SUV_Drive_Idle_lp_01.sfx_LeaveBehind_Veh_Npc_SUV_Drive_Idle_lp_01");
	const TCHAR* SuvHighPath        = TEXT("/Game/Audio/SoundWaves/NPC/SUV/sfx_LeaveBehind_Veh_Npc_SUV_Drive_High_lp_01.sfx_LeaveBehind_Veh_Npc_SUV_Drive_High_lp_01");
	const TCHAR* SuvPinnedPath      = TEXT("/Game/Audio/Vehicles/Metasounds/SUV/wav/sfx_Veh_SUV_Pinned_RPM_lp_01.sfx_Veh_SUV_Pinned_RPM_lp_01");

	const TCHAR* HatchIdlePath      = TEXT("/Game/Audio/SoundWaves/NPC/Hatchback/sfx_LeaveBehind_Veh_Npc_Hatchback_Drive_Idle_lp_01.sfx_LeaveBehind_Veh_Npc_Hatchback_Drive_Idle_lp_01");
	const TCHAR* HatchLowPath       = TEXT("/Game/Audio/SoundWaves/NPC/Hatchback/sfx_LeaveBehind_Veh_Npc_Hatchback_Drive_Low_lp_01.sfx_LeaveBehind_Veh_Npc_Hatchback_Drive_Low_lp_01");
	const TCHAR* HatchHighPath      = TEXT("/Game/Audio/SoundWaves/NPC/Hatchback/sfx_LeaveBehind_Veh_Npc_Hatchback_Drive_High_lp_01.sfx_LeaveBehind_Veh_Npc_Hatchback_Drive_High_lp_01");

	const TCHAR* MinivanIdlePath    = TEXT("/Game/Audio/SoundWaves/NPC/Minivan/sfx_LeaveBehind_Veh_Npc_Minivan_Drive_Idle_lp_01.sfx_LeaveBehind_Veh_Npc_Minivan_Drive_Idle_lp_01");
	const TCHAR* MinivanLowPath     = TEXT("/Game/Audio/SoundWaves/NPC/Minivan/sfx_LeaveBehind_Veh_Npc_Minivan_Drive_Low_01.sfx_LeaveBehind_Veh_Npc_Minivan_Drive_Low_01");
	const TCHAR* MinivanHighPath    = TEXT("/Game/Audio/SoundWaves/NPC/Minivan/sfx_LeaveBehind_Veh_Npc_Minivan_Drive_High_lp_01.sfx_LeaveBehind_Veh_Npc_Minivan_Drive_High_lp_01");

	const TCHAR* SemiIdlePath       = TEXT("/Game/Audio/SoundWaves/NPC/Semi/sfx_LeaveBehind_Veh_Npc_Semi_Drive_Idle_lp_01.sfx_LeaveBehind_Veh_Npc_Semi_Drive_Idle_lp_01");
	const TCHAR* SemiLowPath        = TEXT("/Game/Audio/SoundWaves/NPC/Semi/sfx_LeaveBehind_Veh_Npc_Semi_Drive_Low_lp_01.sfx_LeaveBehind_Veh_Npc_Semi_Drive_Low_lp_01");
	const TCHAR* SemiHighPath       = TEXT("/Game/Audio/SoundWaves/NPC/Semi/sfx_LeaveBehind_Veh_Npc_Semi_Drive_High_lp_01.sfx_LeaveBehind_Veh_Npc_Semi_Drive_High_lp_01");

	const TCHAR* BusIdlePath        = TEXT("/Game/Audio/SoundWaves/NPC/Bus/sfx_LeaveBehind_Veh_Npc_Bus_Drive_Idle_lp_01.sfx_LeaveBehind_Veh_Npc_Bus_Drive_Idle_lp_01");
	const TCHAR* BusLowPath         = TEXT("/Game/Audio/SoundWaves/NPC/Bus/sfx_LeaveBehind_Veh_Npc_Bus_Drive_Low_lp_01.sfx_LeaveBehind_Veh_Npc_Bus_Drive_Low_lp_01");
	const TCHAR* BusHighPath        = TEXT("/Game/Audio/SoundWaves/NPC/Bus/sfx_LeaveBehind_Veh_Npc_Bus_Drive_High_lp_01.sfx_LeaveBehind_Veh_Npc_Bus_Drive_High_lp_01");

	const TCHAR* GarbageIdlePath    = TEXT("/Game/Audio/SoundWaves/NPC/GarbageTruck/sfx_LeaveBehind_Veh_Npc_GarbageTruck_Drive_Idle_lp_01.sfx_LeaveBehind_Veh_Npc_GarbageTruck_Drive_Idle_lp_01");
	const TCHAR* GarbageLowPath     = TEXT("/Game/Audio/SoundWaves/NPC/GarbageTruck/sfx_LeaveBehind_Veh_Npc_GarbageTruck_Drive_Low_lp_01.sfx_LeaveBehind_Veh_Npc_GarbageTruck_Drive_Low_lp_01");
	const TCHAR* GarbageHighPath    = TEXT("/Game/Audio/SoundWaves/NPC/GarbageTruck/sfx_LeaveBehind_Veh_Npc_GarbageTruck_Drive_High_lp_01.sfx_LeaveBehind_Veh_Npc_GarbageTruck_Drive_High_lp_01");

	// Shared CitySample tyre, wind, siren, horn, backfire and crash assets (optional)
	const TCHAR* TyrePath           = TEXT("/Game/Audio/Vehicles/Veh_Shared/wav/sfx_veh_Shared_Tire_Drifting_lp_01.sfx_veh_Shared_Tire_Drifting_lp_01");
	const TCHAR* TyreHeavyPath      = TEXT("/Game/Audio/Vehicles/Veh_Shared/wav/sfx_veh_Shared_Tire_Drift_Heavy_lp_01.sfx_veh_Shared_Tire_Drift_Heavy_lp_01");
	const TCHAR* WindPath           = TEXT("/Game/Audio/Vehicles/Veh_Shared/wav/sfx_Veh_Shared_RoadNoiseAndWind_lp.sfx_Veh_Shared_RoadNoiseAndWind_lp");
	const TCHAR* SirenWailPath      = TEXT("/Game/Audio/Generated/WSPC2_Siren_Wail.WSPC2_Siren_Wail");
	const TCHAR* SirenFallbackPath  = TEXT("/Game/Audio/SoundWaves/Ambient/VariousCity/VEH_SIREN_001.VEH_SIREN_001");
	const TCHAR* SirenAltPath       = TEXT("/Game/Audio/SoundWaves/Ambient/Siren_Horn/Siren/sfx_LeaveBehind_amb_Swt_Siren_nl_01.sfx_LeaveBehind_amb_Swt_Siren_nl_01");
	const TCHAR* SirenPhaserPath    = TEXT("/Game/Audio/Vehicles/Generated/WSPC2_Siren_Phaser.WSPC2_Siren_Phaser");
	const TCHAR* TruckHornPath      = TEXT("/Game/Audio/SoundWaves/Ambient/Siren_Horn/Horns/sfx_LeaveBehind_amb_Swt_GarbageTruck_Horn_nl_01.sfx_LeaveBehind_amb_Swt_GarbageTruck_Horn_nl_01");
	const TCHAR* GeneratedAirhornPath = TEXT("/Game/Audio/Vehicles/Generated/WSPC2_Siren_Airhorn.WSPC2_Siren_Airhorn");
	const TCHAR* BackfireFolder     = TEXT("/Game/Audio/Vehicles/Metasounds/SportsCar/wavs/");
	const TCHAR* AmbiencePath       = TEXT("/Game/Audio/SoundWaves/Ambient/Air_Traffic/sfx_LeaveBehind_amb_Urban_Air_Mid_lp_01.sfx_LeaveBehind_amb_Urban_Air_Mid_lp_01");
	const TCHAR* CrashFolder        = TEXT("/Game/Audio/SoundWaves/SFX/Vehicles/Destruction/Crash/");

	// Our CC0 / synthesised sets (Tools/audio/pipeline, always in the repository)
	const TCHAR* ImpactFolder       = TEXT("/Game/Audio/Vehicles/Collisions/Impacts/");
	const TCHAR* CrunchFolder       = TEXT("/Game/Audio/Vehicles/Collisions/Crunch/");
	const TCHAR* GlassFolder        = TEXT("/Game/Audio/Vehicles/Collisions/Glass/");
	const TCHAR* ScrapeFolder       = TEXT("/Game/Audio/Vehicles/Collisions/Scrape/");
	const TCHAR* MechFolder         = TEXT("/Game/Audio/Vehicles/Mechanical/");
	const TCHAR* GeneratedFolder    = TEXT("/Game/Audio/Vehicles/Generated/");
	const TCHAR* ProfileFolder      = TEXT("/Game/Audio/Vehicles/Profiles/");
	const TCHAR* EngineAttenuationPath    = TEXT("/Game/Audio/Vehicles/Mix/SA_VehicleEngine.SA_VehicleEngine");
	const TCHAR* CollisionAttenuationPath = TEXT("/Game/Audio/Vehicles/Mix/SA_VehicleCollision.SA_VehicleCollision");
	const TCHAR* CollisionConcurrencyPath = TEXT("/Game/Audio/Vehicles/Mix/SC_VehicleCollisions.SC_VehicleCollisions");
	const TCHAR* TrafficConcurrencyPath   = TEXT("/Game/Audio/Vehicles/Mix/SC_TrafficEngines.SC_TrafficEngines");

	// scrape loops in EWSPC2ScrapeSurface order (index = surface - 1)
	const TCHAR* ScrapeLoopNames[5] = {
		TEXT("WSPC2_Col_Scrape_MetalOnAsphalt_Loop"), TEXT("WSPC2_Col_Scrape_MetalOnConcrete_Loop"),
		TEXT("WSPC2_Col_Scrape_MetalOnMetal_Loop"), TEXT("WSPC2_Col_Scrape_PlasticOnAsphalt_Loop"),
		TEXT("WSPC2_Col_Scrape_MetalOnDirt_Loop") };

	// (full volume radius cm, falloff distance cm)
	const float EngineReach[2] = { 1200.0f, 9500.0f };
	const float TyreReach[2]   = { 1200.0f, 12000.0f };
	const float SirenReach[2]  = { 1600.0f, 60000.0f };
	const float ScrapeReach[2] = { 900.0f, 9000.0f };

	USoundBase* LoadSound(const FString& Path)
	{
		return LoadObject<USoundBase>(nullptr, *Path, nullptr, LOAD_NoWarn | LOAD_Quiet);
	}

	USoundBase* LoadNamed(const TCHAR* Folder, const FString& Name)
	{
		return LoadSound(FString(Folder) + Name + TEXT(".") + Name);
	}

	USoundBase* LoadFirstValid(const TCHAR* Primary, const TCHAR* Fallback)
	{
		if (USoundBase* S = LoadSound(Primary))
		{
			return S;
		}
		return Fallback ? LoadSound(Fallback) : nullptr;
	}

	void LoadVariants(TArray<TObjectPtr<USoundBase>>& Out, const FString& Folder, const FString& Stem, int32 MaxCount, int32 Digits)
	{
		for (int32 Index = 1; Index <= MaxCount; ++Index)
		{
			const FString Num = (Digits >= 3) ? FString::Printf(TEXT("%03d"), Index) : FString::Printf(TEXT("%02d"), Index);
			const FString Name = Stem + Num;
			if (USoundBase* Sound = LoadSound(Folder + Name + TEXT(".") + Name))
			{
				Out.Add(Sound);
			}
		}
	}

	/** Equal-power crossfade window: 1 at Centre, falling smoothly to 0 at Low and High. */
	float LayerWeight(float Value, float Low, float Centre, float High)
	{
		const float Linear = Value <= Centre
			? FMath::GetMappedRangeValueClamped(FVector2f(Low, Centre), FVector2f(0.0f, 1.0f), Value)
			: FMath::GetMappedRangeValueClamped(FVector2f(Centre, High), FVector2f(1.0f, 0.0f), Value);

		return FMath::Sin(Linear * UE_HALF_PI);
	}

	void SetLoop(UAudioComponent* Loop, float Volume, float Pitch = 1.0f)
	{
		if (Loop)
		{
			Loop->SetVolumeMultiplier(FMath::Max(Volume, 0.0f));
			Loop->SetPitchMultiplier(FMath::Clamp(Pitch, 0.4f, 2.0f));
		}
	}

	void SetLowPass(UAudioComponent* Loop, float Hz)
	{
		if (!Loop)
		{
			return;
		}
		const bool bOn = Hz > 10.0f && Hz < 19500.0f;
		Loop->SetLowPassFilterEnabled(bOn);
		if (bOn)
		{
			Loop->SetLowPassFilterFrequency(Hz);
		}
	}

	float DbToGain(float Db)
	{
		return FMath::Pow(10.0f, Db / 20.0f);
	}

	/** Synthetic family (Tools/audio/make_vehicle_audio.py) for an audio_profile tag */
	const TCHAR* SyntheticFamilyFor(const FString& Tag)
	{
		if (Tag == TEXT("Tank_Turbine")) return TEXT("Tank_Turbine");
		if (Tag == TEXT("GolfCart_Electric")) return TEXT("Electric_DC");
		if (Tag.Contains(TEXT("Diesel"))) return TEXT("Diesel_Heavy");
		if (Tag == TEXT("I6_TwinTurbo") || Tag == TEXT("Flat6_Turbo")) return TEXT("I6_TwinTurbo");
		if (Tag == TEXT("V12_Exotic") || Tag == TEXT("Flat12_Exotic")) return TEXT("Exotic_HighRev");
		if (Tag.StartsWith(TEXT("V6"))) return TEXT("V6_Exotic");
		if (Tag.StartsWith(TEXT("I4"))) return TEXT("I4_Boxer_Turbo");
		return TEXT("V8_American");
	}

	FVector ListenerLocation(const UWorld* World, bool& bValid, const AActor*& ViewTarget)
	{
		bValid = false;
		ViewTarget = nullptr;
		const APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
		if (!PC)
		{
			return FVector::ZeroVector;
		}
		bValid = true;
		ViewTarget = PC->GetViewTarget();
		if (PC->PlayerCameraManager)
		{
			return PC->PlayerCameraManager->GetCameraLocation();
		}
		return ViewTarget ? ViewTarget->GetActorLocation() : PC->GetFocalLocation();
	}

	const FVehicleReplicatedState* ReadReplicatedState(const UChaosVehicleMovementComponent* Movement)
	{
		// on a remote car the raw inputs are empty; the server's throttle and gear arrive in the protected,
		// replicated ReplicatedState of the movement component
		static const FStructProperty* Property = []()
		{
			const FStructProperty* Found = FindFProperty<FStructProperty>(UChaosVehicleMovementComponent::StaticClass(), TEXT("ReplicatedState"));
			return (Found && Found->Struct == FVehicleReplicatedState::StaticStruct()) ? Found : nullptr;
		}();
		return (Property && Movement) ? Property->ContainerPtrToValuePtr<FVehicleReplicatedState>(Movement) : nullptr;
	}

	const FWSPC2DamageImpactNet* ReadLastImpact(const UWSPC2VehicleDamageComponent* Damage)
	{
		// the replicated impact is a protected UPROPERTY of the damage component: read it through reflection
		static const FStructProperty* Property = []()
		{
			const FStructProperty* Found = FindFProperty<FStructProperty>(UWSPC2VehicleDamageComponent::StaticClass(), TEXT("LastImpact"));
			return (Found && Found->Struct == FWSPC2DamageImpactNet::StaticStruct()) ? Found : nullptr;
		}();
		return (Property && Damage) ? Property->ContainerPtrToValuePtr<FWSPC2DamageImpactNet>(Damage) : nullptr;
	}
}

UWSPC2VehicleAudioComponent::UWSPC2VehicleAudioComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickGroup = TG_PostPhysics;
	SetIsReplicatedByDefault(true);
	FamilySounds.SetNum(4);
}

void UWSPC2VehicleAudioComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(UWSPC2VehicleAudioComponent, ScrapeNet);
}

int32 UWSPC2VehicleAudioComponent::GetAudibleEngineVoiceCount() const
{
	int32 Count = 0;
	for (const UAudioComponent* Voice : EngineVoices)
	{
		Count += (Voice && Voice->VolumeMultiplier > 0.001f) ? 1 : 0;
	}
	for (const UAudioComponent* Stem : { EngineIdle.Get(), EngineLow.Get(), EngineHigh.Get(), EnginePinned.Get() })
	{
		Count += (Stem && Stem->VolumeMultiplier > 0.001f) ? 1 : 0;
	}
	return Count;
}

FString UWSPC2VehicleAudioComponent::GetEngineSourceName() const
{
	switch (EngineSource)
	{
	case EWSPC2EngineSource::Bank: return TEXT("EngineSimBank");
	case EWSPC2EngineSource::RecordedStems: return TEXT("RecordedStems");
	case EWSPC2EngineSource::SyntheticStems: return TEXT("SyntheticStems");
	default: return TEXT("None");
	}
}

// --- engine source -----------------------------------------------------------------------------------------

void UWSPC2VehicleAudioComponent::ResolveFamilyFromProfile(const FString& AudioProfileTag)
{
	FamilyPitchTrim = 1.0f;
	FamilyGainTrim = 1.0f;
	bHasBackfire = false;
	bElectricQuiet = false;

	const TCHAR* IdlePath = SedanIdlePath;
	const TCHAR* LowPath = SedanLowPath;
	const TCHAR* HighPath = SedanHighPath;
	const TCHAR* PinnedPath = SedanPinnedPath;
	const FString& Tag = AudioProfileTag;

	if (Tag == TEXT("V8_Cruiser") || Tag == TEXT("V8_Classic"))
	{
		ActiveEngineFamily = TEXT("Sedan_Real");
		FamilyPitchTrim = (Tag == TEXT("V8_Classic")) ? 0.94f : 1.0f;
	}
	else if (Tag == TEXT("V8_Muscle"))
	{
		ActiveEngineFamily = TEXT("SUV_V8_Real");
		IdlePath = SuvIdlePath;
		LowPath = SedanLowPath;
		HighPath = SportsHighPath;
		PinnedPath = SuvPinnedPath;
		FamilyPitchTrim = 0.92f;
		bHasBackfire = true;
	}
	else if (Tag == TEXT("V12_Exotic") || Tag == TEXT("Flat12_Exotic") || Tag == TEXT("Flat6_Turbo")
		|| Tag == TEXT("I6_TwinTurbo") || Tag == TEXT("V6_MidEngine"))
	{
		ActiveEngineFamily = TEXT("Sports_Real");
		IdlePath = SportsIdlePath;
		LowPath = SportsLowPath;
		HighPath = SportsHighPath;
		PinnedPath = SportsPinnedPath;
		FamilyPitchTrim = (Tag == TEXT("Flat6_Turbo")) ? 0.95f : (Tag == TEXT("V6_MidEngine") ? 0.98f : 1.03f);
		bHasBackfire = true;
	}
	else if (Tag == TEXT("I4_Compact") || Tag == TEXT("I4_Turbo_Rally"))
	{
		ActiveEngineFamily = TEXT("Hatchback_Real");
		IdlePath = HatchIdlePath;
		LowPath = HatchLowPath;
		HighPath = HatchHighPath;
		PinnedPath = SportsPinnedPath;
		FamilyPitchTrim = (Tag == TEXT("I4_Turbo_Rally")) ? 1.04f : 0.98f;
		bHasBackfire = (Tag == TEXT("I4_Turbo_Rally"));
	}
	else if (Tag == TEXT("V6_Sedan") || Tag == TEXT("V6_Turbo") || Tag == TEXT("V8_Van"))
	{
		ActiveEngineFamily = TEXT("Minivan_Real");
		IdlePath = MinivanIdlePath;
		LowPath = MinivanLowPath;
		HighPath = MinivanHighPath;
		PinnedPath = SuvPinnedPath;
		FamilyPitchTrim = (Tag == TEXT("V8_Van")) ? 0.92f : 1.0f;
		bHasBackfire = (Tag == TEXT("V6_Turbo"));
	}
	else if (Tag == TEXT("I4_Diesel_Truck") || Tag == TEXT("V8_Diesel_Armored") || Tag == TEXT("APC_V6_Diesel"))
	{
		ActiveEngineFamily = TEXT("Semi_Diesel_Real");
		const bool bUseBus = (Tag == TEXT("I4_Diesel_Truck"));
		IdlePath = bUseBus ? BusIdlePath : SemiIdlePath;
		LowPath = bUseBus ? BusLowPath : SemiLowPath;
		HighPath = bUseBus ? BusHighPath : SemiHighPath;
		PinnedPath = nullptr;
		FamilyPitchTrim = (Tag == TEXT("APC_V6_Diesel")) ? 0.93f : 0.98f;
	}
	else if (Tag == TEXT("Tank_Turbine"))
	{
		ActiveEngineFamily = TEXT("Heavy_Armored_Real");
		IdlePath = GarbageIdlePath;
		LowPath = GarbageLowPath;
		HighPath = GarbageHighPath;
		PinnedPath = nullptr;
		FamilyPitchTrim = 0.86f;
		FamilyGainTrim = 1.08f;
	}
	else if (Tag == TEXT("GolfCart_Electric"))
	{
		ActiveEngineFamily = TEXT("Electric_Quiet");
		IdlePath = HatchIdlePath;
		LowPath = HatchLowPath;
		HighPath = HatchHighPath;
		PinnedPath = nullptr;
		FamilyPitchTrim = 1.15f;
		FamilyGainTrim = 0.22f;
		bElectricQuiet = true;
	}
	else
	{
		ActiveEngineFamily = TEXT("Sedan_Real");
	}

	FamilySounds.SetNum(4);
	FamilySounds[0] = LoadFirstValid(IdlePath, SedanIdleAltPath);
	FamilySounds[1] = LoadFirstValid(LowPath, SedanLowPath);
	FamilySounds[2] = LoadFirstValid(HighPath, SedanHighPath);
	FamilySounds[3] = PinnedPath ? LoadSound(PinnedPath) : nullptr;
}

bool UWSPC2VehicleAudioComponent::LoadSyntheticFamily(const FString& Tag)
{
	const FString Family = SyntheticFamilyFor(Tag);
	const FString Stem = FString(TEXT("WSPC2_Eng_")) + Family + TEXT("_");
	FamilySounds.SetNum(4);
	FamilySounds[0] = LoadNamed(GeneratedFolder, Stem + TEXT("Idle"));
	FamilySounds[1] = LoadNamed(GeneratedFolder, Stem + TEXT("LowOn"));
	FamilySounds[2] = LoadNamed(GeneratedFolder, Stem + TEXT("HighOn"));
	FamilySounds[3] = nullptr;
	if (!FamilySounds[0] || !FamilySounds[2])
	{
		return false;
	}
	ActiveEngineFamily = FString(TEXT("Synthetic_")) + Family;
	bElectricQuiet = (Family == TEXT("Electric_DC"));
	FamilyGainTrim = bElectricQuiet ? 0.35f : 1.0f;
	FamilyPitchTrim = 1.0f;
	return true;
}

void UWSPC2VehicleAudioComponent::ResolveEngineSource()
{
	const FString Tag = ActiveAudioProfileStr;
	EngineSource = EWSPC2EngineSource::None;
	EngineBank = nullptr;
	StartSound = nullptr;
	ShutdownSound = nullptr;
	EraDSP = FWSPC2EraDSPConfig();
	ForcedInduction = EWSPC2ForcedInduction::None;
	BankGain = 1.0f;
	bIsDiesel = Tag.Contains(TEXT("Diesel"));
	FamilySounds.Init(nullptr, 4);

	const FString ProfileName = FString(TEXT("DA_Audio_")) + Tag;
	AudioProfile = LoadObject<UWSPC2VehicleAudioProfile>(nullptr, *(FString(ProfileFolder) + ProfileName + TEXT(".") + ProfileName),
		nullptr, LOAD_NoWarn | LOAD_Quiet);
	if (AudioProfile)
	{
		EraDSP = AudioProfile->EraDSP;
		ForcedInduction = AudioProfile->ForcedInduction;
	}

	static const bool bForceStems = FParse::Param(FCommandLine::Get(), TEXT("WSPC2AudioStems"));
	if (AudioProfile && bUseEngineSimBanks && !bForceStems)
	{
		UWSPC2EngineSoundBank* Bank = AudioProfile->EngineBank.LoadSynchronous();
		if (Bank && Bank->IsValidGrid())
		{
			EngineBank = Bank;
			EngineSource = EWSPC2EngineSource::Bank;
			ActiveEngineFamily = Bank->ArchetypeId.ToString();
			BankGain = DbToGain(Bank->LoudnessTrimDb + AudioProfile->GainDb + EngineBankGainDb);
			StartSound = Bank->StartSound.LoadSynchronous();
			ShutdownSound = Bank->ShutdownSound.LoadSynchronous();
			bHasBackfire = EraDSP.BackfireChance > 0.0f;
			bElectricQuiet = false;
			FamilyPitchTrim = 1.0f;
			FamilyGainTrim = 1.0f;
			return;
		}
	}

	ResolveFamilyFromProfile(Tag);
	if (AudioProfile)
	{
		bHasBackfire = bHasBackfire || EraDSP.BackfireChance > 0.0f;
	}
	if (FamilySounds[0] && FamilySounds[2])
	{
		EngineSource = EWSPC2EngineSource::RecordedStems;
		return;
	}
	if (LoadSyntheticFamily(Tag))
	{
		EngineSource = EWSPC2EngineSource::SyntheticStems;
		return;
	}
	UE_LOG(LogWSPC2, Warning, TEXT("Vehicle audio: no engine sound for audio_profile %s"), *Tag);
}

void UWSPC2VehicleAudioComponent::ConfigureForVehicleProfile(const FWSPC2VehicleProfileSpec& Spec)
{
	ActiveAudioProfileStr = Spec.AudioProfile.IsEmpty() ? FString(TEXT("V8_Cruiser")) : Spec.AudioProfile;
	ActiveIdleRpm = Spec.bUseRealWorldSpecs ? FMath::Max(400.0f, Spec.IdleRPM) : 720.0f;
	ActiveMaxRpm = Spec.bUseRealWorldSpecs ? FMath::Max(ActiveIdleRpm + 800.0f, Spec.MaxRPM) : 5750.0f;
	SmoothedRpm = ActiveIdleRpm;
	PrevGear = 1;
	ResolveEngineSource();

	if (bAudioInitialized && GetNetMode() != NM_DedicatedServer)
	{
		// a car change: the only moment besides spawn when engine voices are rebuilt
		DestroyEngineVoices();
		CurrentLod = -1;
		ApplyEngineStems();
		bStartPlayed = false;
		bStartFadedOut = false;
		EngineLowPassApplied = -1.0f;
		BindCollisionAudio(GetOwner());
	}
	UE_LOG(LogWSPC2, Log, TEXT("Vehicle audio: %s -> %s (%s)"), *ActiveAudioProfileStr, *ActiveEngineFamily, *GetEngineSourceName());
}

// --- voices ------------------------------------------------------------------------------------------------

UAudioComponent* UWSPC2VehicleAudioComponent::MakeLoopSound(USoundBase* Sound, const TCHAR* Name, float FullVolumeRadius,
	float FalloffDistance, bool b2D, USoundAttenuation* Attenuation, USoundConcurrency* Concurrency)
{
	AActor* Owner = GetOwner();
	if (!Sound || !Owner)
	{
		return nullptr;
	}

	Sound->VirtualizationMode = EVirtualizationMode::PlayWhenSilent;
	if (USoundWave* Wave = Cast<USoundWave>(Sound))
	{
		Wave->bLooping = true;
	}

	UAudioComponent* Audio = NewObject<UAudioComponent>(Owner, MakeUniqueObjectName(Owner, UAudioComponent::StaticClass(), FName(Name)));
	Audio->SetSound(Sound);
	Audio->bAutoActivate = false;
	Audio->bAutoDestroy = false;
	Audio->bStopWhenOwnerDestroyed = true;
	Audio->bAllowSpatialization = !b2D;
	Audio->bIsUISound = false;
	if (Concurrency)
	{
		Audio->ConcurrencySet.Add(Concurrency);
	}

	if (!b2D && Attenuation)
	{
		Audio->AttenuationSettings = Attenuation;
		Audio->bOverrideAttenuation = false;
	}
	else if (!b2D)
	{
		Audio->bOverrideAttenuation = true;
		FSoundAttenuationSettings& Settings = Audio->AttenuationOverrides;
		Settings.bAttenuate = true;
		Settings.bSpatialize = true;
		Settings.AttenuationShapeExtents = FVector(FullVolumeRadius);
		Settings.FalloffDistance = FalloffDistance;
		Settings.DistanceAlgorithm = EAttenuationDistanceModel::NaturalSound;
		Settings.dBAttenuationAtMax = -50.0f;
		Settings.NonSpatializedRadiusStart = FullVolumeRadius;
		Settings.NonSpatializedRadiusEnd = FullVolumeRadius * 0.35f;
	}

	Audio->RegisterComponent();
	if (!b2D && Owner->GetRootComponent())
	{
		Audio->AttachToComponent(Owner->GetRootComponent(), FAttachmentTransformRules::SnapToTargetNotIncludingScale);
		Audio->SetRelativeLocation(FVector(40.0f, 0.0f, 80.0f));
	}

	Audio->SetVolumeMultiplier(0.0f);
	Audio->Play();
	return Audio;
}

UAudioComponent* UWSPC2VehicleAudioComponent::MakeLoop(const TCHAR* Path, const TCHAR* Name, float FullVolumeRadius, float FalloffDistance, bool b2D)
{
	USoundBase* Sound = LoadSound(Path);
	if (!Sound)
	{
		UE_LOG(LogWSPC2, Verbose, TEXT("Vehicle audio: optional asset missing %s"), Path);
		return nullptr;
	}
	return MakeLoopSound(Sound, Name, FullVolumeRadius, FalloffDistance, b2D);
}

void UWSPC2VehicleAudioComponent::ApplyEngineStems()
{
	const bool bStems = EngineSource == EWSPC2EngineSource::RecordedStems || EngineSource == EWSPC2EngineSource::SyntheticStems;
	TObjectPtr<UAudioComponent>* Slots[4] = { &EngineIdle, &EngineLow, &EngineHigh, &EnginePinned };
	const TCHAR* Names[4] = { TEXT("EngineIdle"), TEXT("EngineLow"), TEXT("EngineHigh"), TEXT("EnginePinned") };
	for (int32 i = 0; i < 4; ++i)
	{
		USoundBase* Sound = (bStems && FamilySounds.IsValidIndex(i)) ? FamilySounds[i].Get() : nullptr;
		UAudioComponent* Comp = *Slots[i];
		if (!Comp)
		{
			if (Sound)
			{
				*Slots[i] = MakeLoopSound(Sound, Names[i], EngineReach[0], EngineReach[1], false, EngineAttenuation,
					bLightweightTrafficMode ? TrafficConcurrency.Get() : nullptr);
			}
			continue;
		}
		if (Sound)
		{
			Sound->VirtualizationMode = EVirtualizationMode::PlayWhenSilent;
			if (USoundWave* Wave = Cast<USoundWave>(Sound))
			{
				Wave->bLooping = true;
			}
			if (Comp->Sound != Sound)
			{
				Comp->Stop();
				Comp->SetSound(Sound);
			}
			if (!Comp->IsPlaying())
			{
				Comp->SetVolumeMultiplier(0.0f);
				Comp->Play();
			}
		}
		else
		{
			Comp->SetVolumeMultiplier(0.0f);
			if (Comp->IsPlaying())
			{
				Comp->Stop();
			}
		}
	}
}

int32 UWSPC2VehicleAudioComponent::DesiredLod(const AWSPC2Pawn* Car, float ListenerDistance, bool bListenerCar) const
{
	if (bListenerCar)
	{
		return 0;
	}
	const float Cull = CullDistance * (CurrentLod < 0 ? 1.0f : 1.1f);
	if (ListenerDistance > Cull)
	{
		return -1;
	}
	if (bLightweightTrafficMode)
	{
		return 2;
	}
	const float Medium = MediumLodDistance * (CurrentLod == 1 ? 1.1f : 1.0f);
	return ListenerDistance <= Medium ? 1 : 2;
}

void UWSPC2VehicleAudioComponent::DestroyEngineVoices()
{
	for (UAudioComponent* Voice : EngineVoices)
	{
		if (Voice)
		{
			Voice->Stop();
			Voice->DestroyComponent();
		}
	}
	EngineVoices.Reset();
	VoiceRpmIndex.Reset();
	VoiceLoadIndex.Reset();
	LodRpmIndices.Reset();
	LodLoadIndices.Reset();
}

void UWSPC2VehicleAudioComponent::BuildEngineVoices(int32 Lod)
{
	DestroyEngineVoices();
	CurrentLod = Lod;
	EngineLowPassApplied = -1.0f;
	if (Lod < 0 || !EngineBank || !EngineBank->IsValidGrid())
	{
		return;
	}

	const int32 NumRpm = EngineBank->Rpms.Num();
	const int32 NumLoads = EngineBank->Loads.Num();
	if (Lod == 0)
	{
		for (int32 r = 0; r < NumRpm; ++r) { LodRpmIndices.Add(r); }
		for (int32 l = 0; l < NumLoads; ++l) { LodLoadIndices.Add(l); }
	}
	else if (Lod == 1)
	{
		for (int32 r = 0; r < NumRpm; ++r) { LodRpmIndices.Add(r); }
		LodLoadIndices.AddUnique(0);
		LodLoadIndices.AddUnique(NumLoads - 1);
	}
	else
	{
		LodRpmIndices.AddUnique(FMath::Min(1, NumRpm - 1));
		LodRpmIndices.AddUnique(NumRpm / 2);
		int32 Nearest = 0;
		for (int32 l = 1; l < NumLoads; ++l)
		{
			if (FMath::Abs(EngineBank->Loads[l] - 0.45f) < FMath::Abs(EngineBank->Loads[Nearest] - 0.45f))
			{
				Nearest = l;
			}
		}
		LodLoadIndices.Add(Nearest);
	}
	LodRpmIndices.Sort();
	LodLoadIndices.Sort();

	USoundConcurrency* Concurrency = bLightweightTrafficMode ? TrafficConcurrency.Get() : nullptr;
	for (const int32 r : LodRpmIndices)
	{
		for (const int32 l : LodLoadIndices)
		{
			USoundWave* Wave = EngineBank->Point(r, l).WaveAsset.LoadSynchronous();
			if (!Wave)
			{
				continue;
			}
			const FString Name = FString::Printf(TEXT("EngineR%02dL%02d"), r, l);
			if (UAudioComponent* Voice = MakeLoopSound(Wave, *Name, EngineReach[0], EngineReach[1], false, EngineAttenuation, Concurrency))
			{
				EngineVoices.Add(Voice);
				VoiceRpmIndex.Add(r);
				VoiceLoadIndex.Add(l);
				++EngineVoicePlayCount;
			}
		}
	}
	++EngineVoiceBuilds;
	UE_LOG(LogWSPC2, Verbose, TEXT("Vehicle audio: %s bank %s LOD %d -> %d voices"),
		*GetNameSafe(GetOwner()), *ActiveEngineFamily, Lod, EngineVoices.Num());
}

void UWSPC2VehicleAudioComponent::UpdateBankVoices(float Rpm, float Load, float Gain, float PitchScale, float LowPassHz)
{
	if (!EngineBank || EngineVoices.Num() == 0 || LodRpmIndices.Num() == 0 || LodLoadIndices.Num() == 0)
	{
		return;
	}

	// neighbouring rows and columns among the ones this LOD plays, and the constant-power weights between them
	auto Neighbours = [](const TArray<int32>& Indices, const TArray<float>& Axis, float Value, int32& A, int32& B, float& T)
	{
		A = B = Indices[0];
		T = 0.0f;
		if (Value <= Axis[Indices[0]])
		{
			return;
		}
		if (Value >= Axis[Indices.Last()])
		{
			A = B = Indices.Last();
			return;
		}
		for (int32 k = 0; k + 1 < Indices.Num(); ++k)
		{
			if (Value < Axis[Indices[k + 1]])
			{
				A = Indices[k];
				B = Indices[k + 1];
				T = (Value - Axis[A]) / FMath::Max(Axis[B] - Axis[A], 1e-3f);
				return;
			}
		}
	};

	int32 R0, R1, L0, L1;
	float T, U;
	Neighbours(LodRpmIndices, EngineBank->Rpms, Rpm, R0, R1, T);
	Neighbours(LodLoadIndices, EngineBank->Loads, Load, L0, L1, U);
	const float WR0 = R0 == R1 ? 1.0f : FMath::Cos(T * UE_HALF_PI);
	const float WR1 = R0 == R1 ? 0.0f : FMath::Sin(T * UE_HALF_PI);
	const float WL0 = L0 == L1 ? 1.0f : FMath::Cos(U * UE_HALF_PI);
	const float WL1 = L0 == L1 ? 0.0f : FMath::Sin(U * UE_HALF_PI);

	const bool bLowPassChanged = FMath::Abs(LowPassHz - EngineLowPassApplied) > 25.0f;
	for (int32 i = 0; i < EngineVoices.Num(); ++i)
	{
		UAudioComponent* Voice = EngineVoices[i];
		if (!Voice)
		{
			continue;
		}
		const int32 r = VoiceRpmIndex[i];
		const int32 l = VoiceLoadIndex[i];
		const float WR = (r == R0 ? WR0 : 0.0f) + (r == R1 && R1 != R0 ? WR1 : 0.0f);
		const float WL = (l == L0 ? WL0 : 0.0f) + (l == L1 && L1 != L0 ? WL1 : 0.0f);
		const FWSPC2EngineSamplePoint& Point = EngineBank->Point(r, l);
		Voice->SetVolumeMultiplier(FMath::Max(0.0f, Gain * WR * WL * Point.NormalizationGain));
		Voice->SetPitchMultiplier(FMath::Clamp(Rpm / FMath::Max(Point.MeasuredRPM, 1.0f) * PitchScale, 0.4f, 2.0f));
		if (bLowPassChanged)
		{
			SetLowPass(Voice, LowPassHz);
		}
	}
	if (bLowPassChanged)
	{
		EngineLowPassApplied = LowPassHz;
	}
}

void UWSPC2VehicleAudioComponent::UpdateStemVoices(float Rev, float Load, float Gain, float PitchScale, float LowPassHz)
{
	const float IdleMix   = LayerWeight(Rev, -1.0f, 0.14f, 0.34f);
	const float LowMix    = LayerWeight(Rev, 0.12f, 0.40f, 0.74f);
	const float HighMix   = LayerWeight(Rev, 0.36f, 0.82f, 1.35f);
	const float PinnedMix = FamilySounds.IsValidIndex(3) && FamilySounds[3] ? FMath::Clamp((Rev - 0.72f) / 0.28f, 0.0f, 1.0f) : 0.0f;
	const float StemLoad = FMath::Lerp(0.56f, 1.0f, Load);

	SetLoop(EngineIdle, Gain * IdleMix * 0.82f,
		FMath::GetMappedRangeValueClamped(FVector2f(0.10f, 0.34f), FVector2f(0.95f, 1.30f), Rev) * PitchScale);
	SetLoop(EngineLow, Gain * LowMix * StemLoad,
		FMath::GetMappedRangeValueClamped(FVector2f(0.12f, 0.74f), FVector2f(0.80f, 1.32f), Rev) * PitchScale);
	SetLoop(EngineHigh, Gain * HighMix * StemLoad,
		FMath::GetMappedRangeValueClamped(FVector2f(0.36f, 1.00f), FVector2f(0.76f, 1.16f), Rev) * PitchScale);
	SetLoop(EnginePinned, Gain * PinnedMix * StemLoad * 0.55f,
		FMath::GetMappedRangeValueClamped(FVector2f(0.72f, 1.00f), FVector2f(0.94f, 1.12f), Rev) * PitchScale);

	if (FMath::Abs(LowPassHz - EngineLowPassApplied) > 25.0f)
	{
		SetLowPass(EngineIdle, LowPassHz);
		SetLowPass(EngineLow, LowPassHz);
		SetLowPass(EngineHigh, LowPassHz);
		SetLowPass(EnginePinned, LowPassHz);
		EngineLowPassApplied = LowPassHz;
	}
}

// --- lifecycle -----------------------------------------------------------------------------------------------

void UWSPC2VehicleAudioComponent::BindCollisionAudio(AActor* Owner)
{
	if (!Owner)
	{
		return;
	}
	Owner->OnActorHit.AddUniqueDynamic(this, &UWSPC2VehicleAudioComponent::OnCarHit);
	TInlineComponentArray<UPrimitiveComponent*> Prims(Owner);
	for (UPrimitiveComponent* Prim : Prims)
	{
		if (Prim && Prim->GetCollisionEnabled() != ECollisionEnabled::NoCollision)
		{
			Prim->OnComponentHit.AddUniqueDynamic(this, &UWSPC2VehicleAudioComponent::OnComponentHit);
		}
	}
}

void UWSPC2VehicleAudioComponent::LoadSharedSounds()
{
	EngineAttenuation = LoadObject<USoundAttenuation>(nullptr, EngineAttenuationPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
	CollisionAttenuation = LoadObject<USoundAttenuation>(nullptr, CollisionAttenuationPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
	CollisionConcurrency = LoadObject<USoundConcurrency>(nullptr, CollisionConcurrencyPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
	TrafficConcurrency = LoadObject<USoundConcurrency>(nullptr, TrafficConcurrencyPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
	if (!CollisionAttenuation)
	{
		// one-shots without an attenuation asset would play in 2D: make a natural 3D falloff in memory
		CollisionAttenuation = NewObject<USoundAttenuation>(this);
		FSoundAttenuationSettings& Settings = CollisionAttenuation->Attenuation;
		Settings.bAttenuate = true;
		Settings.bSpatialize = true;
		Settings.AttenuationShapeExtents = FVector(300.0f);
		Settings.FalloffDistance = 11700.0f;
		Settings.DistanceAlgorithm = EAttenuationDistanceModel::NaturalSound;
		Settings.dBAttenuationAtMax = -50.0f;
	}

	// primary impacts: CitySample recordings when preferred and present, else our CC0 set
	if (bPreferRecordedCrashes)
	{
		LoadVariants(CrashLight,  CrashFolder, TEXT("sfx_Crash_Veh_to-Wall_Impact_Light_nl_"), 6, 2);
		LoadVariants(CrashMedium, CrashFolder, TEXT("sfx_Crash_Veh_to-Veh_Impact_Med_nl_"),   6, 2);
		LoadVariants(CrashHeavy,  CrashFolder, TEXT("sfx_Crash_Veh_to-Veh_Impact_Heavy_nl_"), 6, 2);
	}
	if (CrashLight.Num() == 0)  { LoadVariants(CrashLight,  ImpactFolder, TEXT("WSPC2_Col_Impact_Light_"), 8, 2); }
	if (CrashMedium.Num() == 0) { LoadVariants(CrashMedium, ImpactFolder, TEXT("WSPC2_Col_Impact_Medium_"), 8, 2); }
	if (CrashHeavy.Num() == 0)  { LoadVariants(CrashHeavy,  ImpactFolder, TEXT("WSPC2_Col_Impact_Heavy_"), 8, 2); }
	LoadVariants(CrunchMedium, CrunchFolder, TEXT("WSPC2_Col_MetalCrunch_Med_"), 8, 2);
	LoadVariants(CrunchHeavy,  CrunchFolder, TEXT("WSPC2_Col_MetalCrunch_Heavy_"), 8, 2);
	LoadVariants(GlassShatter, GlassFolder, TEXT("WSPC2_Col_Glass_Shatter_"), 6, 2);
	LoadVariants(GlassDebris,  GlassFolder, TEXT("WSPC2_Col_Glass_Debris_"), 6, 2);
	LoadVariants(TurboBlowOff, MechFolder, TEXT("WSPC2_Mech_Turbo_BOV_"), 4, 2);
	LoadVariants(TurboFlutter, MechFolder, TEXT("WSPC2_Mech_Turbo_Flutter_"), 4, 2);
	LoadVariants(GearClunks,   MechFolder, TEXT("WSPC2_Mech_Gear_Shift_Clunk_"), 4, 2);
}

void UWSPC2VehicleAudioComponent::BeginPlay()
{
	Super::BeginPlay();

	if (GetNetMode() == NM_DedicatedServer)
	{
		// no sound on a dedicated server; it still finds scraping and replicates it
		BindCollisionAudio(GetOwner());
		bAudioInitialized = true;
		return;
	}

	LoadSharedSounds();
	if (EngineSource == EWSPC2EngineSource::None)
	{
		ResolveEngineSource();
	}

	Tyres = MakeLoop(TyrePath, TEXT("Tyres"), TyreReach[0], TyreReach[1]);
	if (!Tyres)
	{
		Tyres = MakeLoopSound(LoadNamed(MechFolder, TEXT("WSPC2_Mech_Tire_Skid_Asphalt_Loop")), TEXT("Tyres"), TyreReach[0], TyreReach[1]);
	}

	if (!bLightweightTrafficMode)
	{
		TyresHeavy = MakeLoop(TyreHeavyPath, TEXT("TyresHeavy"), TyreReach[0], TyreReach[1]);
		TyresDirt  = MakeLoopSound(LoadNamed(MechFolder, TEXT("WSPC2_Mech_Tire_Skid_Dirt_Loop")), TEXT("TyresDirt"), TyreReach[0], TyreReach[1]);
		Wind       = MakeLoop(WindPath, TEXT("Wind"), EngineReach[0], EngineReach[1]);

		SirenWail = MakeLoop(SirenWailPath, TEXT("SirenWail"), SirenReach[0], SirenReach[1]);
		if (!SirenWail)
		{
			SirenWail = MakeLoop(SirenFallbackPath, TEXT("SirenWail"), SirenReach[0], SirenReach[1]);
		}
		if (SirenWail)
		{
			SirenWail->SetRelativeLocation(FVector(-40.0f, 0.0f, 170.0f));
		}

		SirenAlt = MakeLoop(SirenAltPath, TEXT("SirenAlt"), SirenReach[0], SirenReach[1]);
		if (!SirenAlt)
		{
			SirenAlt = MakeLoop(SirenPhaserPath, TEXT("SirenAlt"), SirenReach[0], SirenReach[1]);
		}
		if (SirenAlt)
		{
			SirenAlt->SetRelativeLocation(FVector(-40.0f, 0.0f, 170.0f));
		}

		LoadVariants(BackfireSounds, BackfireFolder, TEXT("sfx_Veh_Sport_Backfire_nl_"), 6, 2);
		if (BackfireSounds.Num() == 0)
		{
			LoadVariants(BackfireSounds, MechFolder, TEXT("WSPC2_Mech_Backfire_Pop_"), 6, 2);
		}
		if (USoundBase* TruckHorn = LoadSound(TruckHornPath))
		{
			AirhornSounds.Add(TruckHorn);
		}
		LoadVariants(AirhornSounds, TEXT("/Game/Audio/SoundWaves/Ambient/Horns/"), TEXT("VEH_SEDAN_Horn_A_"), 4, 3);
		if (AirhornSounds.Num() == 0)
		{
			if (USoundBase* Horn = LoadSound(GeneratedAirhornPath))
			{
				AirhornSounds.Add(Horn);
			}
		}
	}

	BindCollisionAudio(GetOwner());
	bAudioInitialized = true;
	ApplyEngineStems();
}

void UWSPC2VehicleAudioComponent::EndPlay(const EEndPlayReason::Type Reason)
{
	if (Ambience)
	{
		Ambience->Stop();
	}
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearAllTimersForObject(this);
	}
	Super::EndPlay(Reason);
}

void UWSPC2VehicleAudioComponent::PlayAirhornBlast()
{
	AActor* Owner = GetOwner();
	if (!Owner || GetNetMode() == NM_DedicatedServer || AirhornSounds.Num() == 0)
	{
		return;
	}
	// primary police airhorn (index 0 is the deep truck horn when present)
	if (USoundBase* Horn = AirhornSounds[0])
	{
		UGameplayStatics::PlaySoundAtLocation(this, Horn, Owner->GetActorLocation() + FVector(120.0f, 0.0f, 95.0f), 0.92f * MasterVolume, 1.0f);
	}
}

void UWSPC2VehicleAudioComponent::SetExternalTelemetry(const FWSPC2VehicleAudioTelemetry& Telemetry)
{
	ExternalTelemetry = Telemetry;
	ExternalTelemetryTime = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
}

// --- tick ----------------------------------------------------------------------------------------------------

void UWSPC2VehicleAudioComponent::TickComponent(float Delta, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(Delta, TickType, ThisTickFunction);

	const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
	AActor* Owner = GetOwner();
	if (Owner && Owner->HasAuthority())
	{
		DetectScrapeOnServer(Delta, Now);
	}
	if (GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	AWSPC2Pawn* Car = Cast<AWSPC2Pawn>(Owner);
	if (!Car)
	{
		return;
	}
	UChaosWheeledVehicleMovementComponent* Movement = Cast<UChaosWheeledVehicleMovementComponent>(Car->GetVehicleMovementComponent());
	const bool bExternal = (Now - ExternalTelemetryTime) < 0.5;
	if (!Movement && !bExternal)
	{
		return;
	}

	// listener and level of detail
	bool bHasListener = false;
	const AActor* ViewTarget = nullptr;
	const FVector Listener = ListenerLocation(GetWorld(), bHasListener, ViewTarget);
	// AI drivers are "locally controlled" on the server too: only a local *player's* car (or the one the camera
	// follows, the gunner's case) gets the full voice set
	const bool bLocalPlayerCar = Car->IsPlayerControlled() && Car->IsLocallyControlled();
	const bool bListenerCar = bLocalPlayerCar || ViewTarget == Car;
	const float ListenerDistance = bHasListener ? FVector::Dist(Listener, Car->GetActorLocation()) : 0.0f;
	const bool bAudible = bListenerCar || ListenerDistance <= CullDistance;

	if (EngineSource == EWSPC2EngineSource::Bank)
	{
		const int32 Lod = DesiredLod(Car, ListenerDistance, bListenerCar);
		if (Lod != CurrentLod)
		{
			BuildEngineVoices(Lod);
		}
	}

	// telemetry
	float SpeedKmh, Rpm, Throttle, MaxRpm;
	int32 CurGear;
	if (bExternal)
	{
		SpeedKmh = ExternalTelemetry.SpeedKmh;
		Rpm = ExternalTelemetry.RPM;
		Throttle = FMath::Clamp(ExternalTelemetry.ThrottleLoad, 0.0f, 1.0f);
		CurGear = ExternalTelemetry.CurrentGear;
		MaxRpm = FMath::Max(1200.0f, ExternalTelemetry.MaxRPM);
	}
	else
	{
		SpeedKmh = FMath::Abs(Movement->GetForwardSpeed()) * 0.036f;
		MaxRpm = FMath::Max(1200.0f, FMath::Max(ActiveMaxRpm, Movement->GetEngineMaxRotationSpeed()));
		Rpm = Movement->GetEngineRotationSpeed();
		if (Rpm < 100.0f)
		{
			Rpm = ActiveIdleRpm + FMath::Fmod(SpeedKmh * 48.0f, MaxRpm * 0.52f);
		}
		Throttle = FMath::Clamp(FMath::Abs(Movement->GetThrottleInput()), 0.0f, 1.0f);
		CurGear = Movement->GetCurrentGear();
		if (!Car->HasAuthority() && !Car->IsLocallyControlled())
		{
			if (const FVehicleReplicatedState* State = ReadReplicatedState(Movement))
			{
				Throttle = FMath::Clamp(FMath::Abs(State->ThrottleInput), 0.0f, 1.0f);
				CurGear = State->TargetGear;
			}
		}
	}

	// carburettor / big-cam idle wander
	if (EraDSP.IdleInstabilityAmount > 0.0f && Rpm < ActiveIdleRpm * 1.4f)
	{
		const float Wander = static_cast<float>(FMath::Sin(Now * 7.3) + 0.6 * FMath::Sin(Now * 2.9 + 1.3));
		Rpm += EraDSP.IdleInstabilityAmount * 45.0f * Wander;
	}

	SmoothedRpm = FMath::FInterpTo(SmoothedRpm, Rpm, Delta, EngineSource == EWSPC2EngineSource::Bank ? RpmFollowSpeed : 7.0f);
	const float Rev = FMath::Clamp(SmoothedRpm / MaxRpm, 0.0f, 1.0f);
	SmoothedLoad = FMath::FInterpTo(SmoothedLoad, Throttle, Delta, 6.0f);

	// damage on the engine
	const UWSPC2VehicleDamageComponent* Damage = Car->GetVehicleDamage();
	const bool bStalled = (Damage && Damage->IsEngineStalled()) || (bExternal && !ExternalTelemetry.bEngineRunning);
	const float EngineFactor = Damage ? Damage->GetEngineHealthTorqueFactor() : 1.0f;
	const float ThrottleMult = Damage ? Damage->GetThrottleDamageMultiplier() : 1.0f;
	const float MisfireFlutter = (!bStalled && EngineFactor < 0.78f)
		? FMath::Lerp(1.0f, 0.78f + 0.22f * static_cast<float>(FMath::Sin(Now * 29.0)), ThrottleMult < 0.9f ? 1.0f : (0.78f - EngineFactor) * 0.7f)
		: 1.0f;

	// start and shutdown (the listener's own car on a bank)
	float StartGain = 1.0f;
	if (EngineSource == EWSPC2EngineSource::Bank && bListenerCar)
	{
		if (!bStartPlayed && !bStalled)
		{
			bStartPlayed = true;
			bStartFadedOut = false;
			StartSoundTime = Now;
			StartVoice = StartSound ? UGameplayStatics::SpawnSoundAttached(StartSound, Car->GetRootComponent(), NAME_None,
				FVector(40.0f, 0.0f, 80.0f), EAttachLocation::KeepRelativeOffset, true, MasterVolume * EngineVolume * BankGain,
				1.0f, 0.0f, EngineAttenuation) : nullptr;
		}
		if (StartVoice)
		{
			const double Since = Now - StartSoundTime;
			StartGain = FMath::Clamp(static_cast<float>((Since - 1.9) / 0.8), 0.0f, 1.0f);
			if (Since >= 1.9 && !bStartFadedOut)
			{
				StartVoice->FadeOut(0.8f, 0.0f);
				bStartFadedOut = true;
			}
		}
		if (bStalled && !bWasStalled && ShutdownSound)
		{
			UGameplayStatics::SpawnSoundAttached(ShutdownSound, Car->GetRootComponent(), NAME_None, FVector(40.0f, 0.0f, 80.0f),
				EAttachLocation::KeepRelativeOffset, true, MasterVolume * EngineVolume * BankGain, 1.0f, 0.0f, EngineAttenuation);
		}
		if (!bStalled && bWasStalled)
		{
			bStartPlayed = false; // repaired: crank it again
		}
	}
	bWasStalled = bStalled;

	// rev limiter bounce
	float LimiterGain = 1.0f;
	if (EraDSP.bHardRevLimiter && SmoothedRpm >= MaxRpm * 0.985f && Throttle > 0.85f)
	{
		LimiterGain = FMath::Frac(Now * 14.0) < 0.5 ? 1.0f : 0.35f;
	}

	const float TrafficGain = bLightweightTrafficMode ? 0.55f : 1.0f;
	const float EngineGain = bStalled ? 0.0f
		: MasterVolume * EngineVolume * FamilyGainTrim * TrafficGain * FMath::Lerp(0.75f, 1.0f, EngineFactor) * MisfireFlutter * LimiterGain;
	const float DamagePitch = bStalled ? 0.65f : FMath::Lerp(0.90f, 1.0f, EngineFactor) * (ThrottleMult < 0.9f ? 0.88f : 1.0f);
	LastEngineGain = bAudible ? EngineGain * StartGain : 0.0f;

	// low-pass: exhaust colour always, cabin muffling when the local player sits inside
	const bool bInCabin = (bListenerCar && Car->IsCabinViewActive()) || (bExternal && ExternalTelemetry.bIsInsideCabin);
	const float EngineLowPass = bInCabin ? FMath::Min(EraDSP.ExhaustLowPassHz, EraDSP.CabinLowPassHz) : EraDSP.ExhaustLowPassHz;
	CurrentLowPassHz = CurrentLowPassHz <= 0.0f ? EngineLowPass : FMath::FInterpTo(CurrentLowPassHz, EngineLowPass, Delta, 6.0f);

	if (EngineSource == EWSPC2EngineSource::Bank)
	{
		const float PitchScale = EraDSP.PitchMultiplier * DamagePitch;
		UpdateBankVoices(SmoothedRpm, SmoothedLoad * MisfireFlutter, bAudible ? EngineGain * BankGain * StartGain : 0.0f, PitchScale, CurrentLowPassHz);
	}
	else
	{
		const bool bCulled = bLightweightTrafficMode && !bAudible;
		UpdateStemVoices(Rev, SmoothedLoad * MisfireFlutter, bCulled ? 0.0f : EngineGain, FamilyPitchTrim * DamagePitch, CurrentLowPassHz);
	}

	UpdateExtras(Car, Delta, Now, SmoothedRpm, Rev, Throttle, CurGear, SpeedKmh, bListenerCar, bInCabin ? EraDSP.CabinLowPassHz * 1.6f : 0.0f);
	UpdateCollisions(Car, Now, bAudible);

	if (bLightweightTrafficMode && !bAudible)
	{
		SetLoop(Tyres, 0.0f);
		PrevThrottle = Throttle;
		PrevGear = CurGear;
		return;
	}

	// tyres: squeal on hard surfaces, gravel spray on dirt, sand and grass, rim thump on a flat
	float Slip = 0.0f;
	float SoftSlip = 0.0f;
	int32 SoftWheels = 0;
	int32 Contacts = 0;
	if (Movement)
	{
		for (int32 Index = 0; Index < Movement->GetNumWheels(); ++Index)
		{
			const FWheelStatus& Wheel = Movement->GetWheelState(Index);
			if (!Wheel.bInContact)
			{
				continue;
			}
			++Contacts;
			float WheelSlip = 0.0f;
			if (Wheel.bIsSkidding)
			{
				WheelSlip = FMath::Max(WheelSlip, FMath::Clamp(Wheel.SkidMagnitude / 600.0f, 0.0f, 1.0f));
			}
			if (Wheel.bIsSlipping)
			{
				WheelSlip = FMath::Max(WheelSlip, FMath::Clamp(Wheel.SlipMagnitude / 900.0f, 0.0f, 1.0f));
			}
			const UPhysicalMaterial* Material = Wheel.PhysMaterial.Get();
			const EPhysicalSurface Surface = Material ? Material->SurfaceType.GetValue() : SurfaceType_Default;
			const bool bSoft = Surface == SurfaceType4 || Surface == SurfaceType5 || Surface == SurfaceType6;
			if (bSoft)
			{
				++SoftWheels;
				SoftSlip = FMath::Max(SoftSlip, WheelSlip);
			}
			else
			{
				Slip = FMath::Max(Slip, WheelSlip);
			}
		}
	}
	else if (bExternal)
	{
		Slip = ExternalTelemetry.MaxTireSlip;
	}
	if (Damage && (Damage->GetPuncturedWheelCount() > 0 || Damage->GetDetachedWheelCount() > 0) && SpeedKmh > 6.0f)
	{
		const float RimPulse = 0.55f + 0.45f * FMath::Abs(static_cast<float>(FMath::Sin(Now * FMath::Clamp(SpeedKmh * 0.42f, 3.0f, 24.0f))));
		Slip = FMath::Max(Slip, FMath::Clamp(SpeedKmh / 60.0f, 0.22f, 0.78f) * RimPulse);
	}
	SmoothedSlip = FMath::FInterpTo(SmoothedSlip, SpeedKmh > 4.0f ? Slip : 0.0f, Delta, 10.0f);

	const float TyreBaseGain = MasterVolume * EngineVolume * TrafficGain;
	SetLoop(Tyres, TyreBaseGain * FMath::SmoothStep(0.08f, 0.45f, SmoothedSlip) * 0.8f, FMath::Lerp(0.85f, 1.10f, SmoothedSlip));
	SetLoop(TyresHeavy, TyreBaseGain * FMath::SmoothStep(0.45f, 0.90f, SmoothedSlip));
	const float SoftShare = Contacts > 0 ? static_cast<float>(SoftWheels) / Contacts : 0.0f;
	const float Gravel = SoftShare * FMath::Clamp(SpeedKmh / 60.0f, 0.0f, 1.0f) * 0.35f + FMath::SmoothStep(0.05f, 0.6f, SoftSlip);
	SetLoop(TyresDirt, TyreBaseGain * FMath::Clamp(Gravel, 0.0f, 1.2f) * 0.8f, FMath::Lerp(0.85f, 1.15f, FMath::Clamp(SpeedKmh / 120.0f, 0.0f, 1.0f)));

	// road and wind roar
	const float WindAmount = FMath::Clamp((SpeedKmh - 10.0f) / 150.0f, 0.0f, 1.0f);
	SetLoop(Wind, MasterVolume * EngineVolume * FMath::Sqrt(WindAmount) * (bElectricQuiet ? 1.15f : 1.0f),
		FMath::Lerp(0.82f, 1.26f, WindAmount));

	// sirens: Wail / Yelp / Phaser
	const float SirenHealth = Damage ? Damage->GetSirenLightHealthFactor() : 1.0f;
	const EWSPC2SirenMode SMode = Car->GetSirenMode();
	const float SirenBaseGain = (Car->IsSirenOn() && SMode != EWSPC2SirenMode::Off) ? MasterVolume * SirenVolume * SirenHealth : 0.0f;
	if (SMode == EWSPC2SirenMode::Phaser && SirenAlt)
	{
		SetLoop(SirenWail, 0.0f, 1.0f);
		SetLoop(SirenAlt, SirenBaseGain * 0.95f, FMath::Lerp(0.88f, 1.05f, SirenHealth));
	}
	else if (SMode == EWSPC2SirenMode::Yelp)
	{
		SetLoop(SirenAlt, 0.0f, 1.0f);
		SetLoop(SirenWail, SirenBaseGain, 1.24f * FMath::Lerp(0.84f, 1.0f, SirenHealth));
	}
	else
	{
		SetLoop(SirenAlt, 0.0f, 1.0f);
		SetLoop(SirenWail, SirenBaseGain, FMath::Lerp(0.84f, 1.0f, SirenHealth));
	}

	// outside sounds are muffled too when the local player sits in the cabin
	const float OutsideLowPass = bInCabin ? EraDSP.CabinLowPassHz * 1.6f : 0.0f;
	if (FMath::Abs(OutsideLowPass - OutsideLowPassApplied) > 25.0f)
	{
		for (UAudioComponent* Loop : { Tyres.Get(), TyresHeavy.Get(), TyresDirt.Get(), Wind.Get() })
		{
			SetLowPass(Loop, OutsideLowPass);
		}
		OutsideLowPassApplied = OutsideLowPass;
	}

	// city air for the local player
	const bool bLocalCrew = bLocalPlayerCar;
	if (bLocalCrew && !Ambience)
	{
		Ambience = MakeLoop(AmbiencePath, TEXT("Ambience"), 0.0f, 0.0f, true);
	}
	SetLoop(Ambience, bLocalCrew ? AmbienceVolume : 0.0f);

	PrevThrottle = Throttle;
	PrevGear = CurGear;
}

void UWSPC2VehicleAudioComponent::UpdateExtras(AWSPC2Pawn* Car, float Delta, double Now, float Rpm, float Rev, float Throttle,
	int32 Gear, float SpeedKmh, bool bListenerCar, float LowPassHz)
{
	const bool bNear = bListenerCar || CurrentLod == 1 || EngineSource != EWSPC2EngineSource::Bank;
	const UWSPC2VehicleDamageComponent* Damage = Car->GetVehicleDamage();
	const bool bStalled = Damage && Damage->IsEngineStalled();
	const float Base = bStalled ? 0.0f : MasterVolume * EngineVolume;

	// turbo: boost builds with load above ~2200 rpm, falls when the throttle closes (blow-off or flutter)
	const bool bTurbo = ForcedInduction == EWSPC2ForcedInduction::Turbo_BOV || ForcedInduction == EWSPC2ForcedInduction::Turbo_Flutter;
	const float BoostTarget = bTurbo && !bStalled
		? Throttle * FMath::Clamp((Rpm - 2200.0f) / FMath::Max(ActiveMaxRpm - 2200.0f, 500.0f), 0.0f, 1.0f) : 0.0f;
	const float PrevBoost = SmoothedBoost;
	SmoothedBoost = FMath::FInterpTo(SmoothedBoost, BoostTarget, Delta, BoostTarget > SmoothedBoost ? 1.8f : 6.0f);
	if (bTurbo && bListenerCar)
	{
		if (!TurboSpool)
		{
			TurboSpool = MakeLoopSound(LoadNamed(MechFolder, TEXT("WSPC2_Mech_Turbo_Spool_Loop")), TEXT("TurboSpool"), EngineReach[0], EngineReach[1]);
		}
		SetLoop(TurboSpool, Base * 0.35f * FMath::Pow(SmoothedBoost, 1.5f), 0.6f + 0.7f * SmoothedBoost);
	}
	if (bTurbo && bNear && PrevThrottle > 0.6f && Throttle < 0.2f && PrevBoost > 0.45f && Now - LastBlowOffTime > 0.8)
	{
		LastBlowOffTime = Now;
		const TArray<TObjectPtr<USoundBase>>& Set = ForcedInduction == EWSPC2ForcedInduction::Turbo_Flutter ? TurboFlutter : TurboBlowOff;
		PlayOneShot(PickVariant(Set), Car->GetActorLocation() + Car->GetActorForwardVector() * 120.0f + FVector(0, 0, 70.0f),
			Base * 0.6f * PrevBoost, FMath::RandRange(0.95f, 1.05f));
	}

	// supercharger whine follows the crank
	if (ForcedInduction == EWSPC2ForcedInduction::Supercharger && bListenerCar)
	{
		if (!SuperchargerWhine)
		{
			SuperchargerWhine = MakeLoopSound(LoadNamed(MechFolder, TEXT("WSPC2_Mech_Supercharger_Whine_Loop")), TEXT("Supercharger"), EngineReach[0], EngineReach[1]);
		}
		SetLoop(SuperchargerWhine, Base * 0.25f * (0.3f + 0.7f * Throttle) * Rev, 0.5f + 1.0f * Rev);
	}

	// gearbox whine (strongest in reverse) and shift clunk
	if (bListenerCar)
	{
		const bool bReverse = Gear < 0;
		const float WhineGain = bReverse ? FMath::Max(EraDSP.GearWhineGain, 0.3f) * 1.8f : EraDSP.GearWhineGain;
		if (WhineGain > 0.0f && !GearWhine)
		{
			GearWhine = MakeLoopSound(LoadNamed(MechFolder, TEXT("WSPC2_Mech_Gear_Whine_Loop")), TEXT("GearWhine"), EngineReach[0], EngineReach[1]);
		}
		SetLoop(GearWhine, Base * WhineGain * FMath::Clamp(SpeedKmh / 80.0f, 0.0f, 1.0f) * (0.4f + 0.6f * Throttle) * 0.5f, 0.6f + Rev);
		if (Gear != PrevGear && !bStalled && GearClunks.Num() > 0)
		{
			PlayOneShot(PickVariant(GearClunks), Car->GetActorLocation() + FVector(0, 0, 60.0f), Base * 0.35f, FMath::RandRange(0.95f, 1.05f));
		}
	}

	// diesel injector knock, loudest at idle
	if ((bIsDiesel || EraDSP.DieselClatterGain > 0.0f) && bListenerCar)
	{
		if (!DieselClatter)
		{
			DieselClatter = MakeLoopSound(LoadNamed(MechFolder, TEXT("WSPC2_Mech_Diesel_Clatter_Loop")), TEXT("DieselClatter"), EngineReach[0], EngineReach[1]);
		}
		const float ClatterGain = EraDSP.DieselClatterGain > 0.0f ? EraDSP.DieselClatterGain : 0.5f;
		SetLoop(DieselClatter, Base * ClatterGain * (1.0f - 0.6f * Rev) * 0.6f, Rpm / 1000.0f);
	}

	// exhaust pops on a sharp lift-off or a fast upshift at high revs
	if (!bStalled && bNear && bHasBackfire && BackfireSounds.Num() > 0 && Now - LastBackfireTime > 1.2)
	{
		const bool bLiftOff = (PrevThrottle > 0.60f && Throttle < 0.15f && Rev > 0.58f);
		const bool bUpshift = (Gear > PrevGear && PrevGear >= 1 && Rev > 0.65f);
		const float Chance = EraDSP.BackfireChance > 0.0f ? EraDSP.BackfireChance : 1.0f;
		if ((bLiftOff || bUpshift) && FMath::FRand() < Chance)
		{
			LastBackfireTime = Now;
			PlayOneShot(PickVariant(BackfireSounds), Car->GetActorLocation() - Car->GetActorForwardVector() * 195.0f,
				0.72f * MasterVolume, FMath::RandRange(0.95f, 1.06f));
		}
	}

	if (FMath::Abs(LowPassHz - OutsideLowPassApplied) > 25.0f)
	{
		for (UAudioComponent* Loop : { TurboSpool.Get(), SuperchargerWhine.Get(), GearWhine.Get(), DieselClatter.Get() })
		{
			SetLowPass(Loop, LowPassHz);
		}
	}

	// body scraping (state from the server)
	const float ScrapeTarget = ScrapeNet.Intensity / 15.0f;
	SmoothedScrape = FMath::FInterpTo(SmoothedScrape, ScrapeTarget, Delta, ScrapeTarget > SmoothedScrape ? 30.0f : 8.3f);
	if (ScrapeNet.Surface != 0)
	{
		AudibleScrapeSurface = static_cast<EWSPC2ScrapeSurface>(ScrapeNet.Surface);
	}
	if (SmoothedScrape > 0.01f && bNear && ScrapeLoops.Num() == 0)
	{
		for (const TCHAR* Name : ScrapeLoopNames)
		{
			ScrapeLoops.Add(MakeLoopSound(LoadNamed(ScrapeFolder, Name), Name, ScrapeReach[0], ScrapeReach[1]));
		}
	}
	for (int32 i = 0; i < ScrapeLoops.Num(); ++i)
	{
		const bool bActiveSurface = (i + 1) == static_cast<int32>(AudibleScrapeSurface);
		SetLoop(ScrapeLoops[i], bActiveSurface ? MasterVolume * SmoothedScrape * 0.9f : 0.0f, 0.8f + 0.4f * SmoothedScrape);
	}
}

// --- collisions ------------------------------------------------------------------------------------------------

USoundBase* UWSPC2VehicleAudioComponent::PickVariant(const TArray<TObjectPtr<USoundBase>>& Set) const
{
	return Set.Num() > 0 ? Set[FMath::RandRange(0, Set.Num() - 1)].Get() : nullptr;
}

void UWSPC2VehicleAudioComponent::PlayOneShot(USoundBase* Sound, const FVector& Location, float Volume, float Pitch, float LowPassHz)
{
	if (!Sound || Volume <= 0.0f || GetNetMode() == NM_DedicatedServer)
	{
		return;
	}
	UAudioComponent* Voice = UGameplayStatics::SpawnSoundAtLocation(this, Sound, Location, FRotator::ZeroRotator, Volume, Pitch, 0.0f,
		CollisionAttenuation, CollisionConcurrency, true);
	if (Voice && LowPassHz > 0.0f)
	{
		SetLowPass(Voice, LowPassHz);
	}
}

void UWSPC2VehicleAudioComponent::PlayImpactLayers(const FVector& Point, float Severity, int32 Zone)
{
	const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
	const int32 ZoneIndex = FMath::Clamp(Zone, 0, 4);
	if (Now - LastZoneImpactTime[ZoneIndex] < ImpactZoneCooldown)
	{
		return;
	}
	LastZoneImpactTime[ZoneIndex] = Now;
	LastDamageImpactTime = Now;

	// layer 1: the hit itself, duller for light knocks
	const bool bHeavy = Severity >= HeavyImpactSeverity;
	const bool bMedium = !bHeavy && Severity >= MediumImpactSeverity;
	const TArray<TObjectPtr<USoundBase>>& Set = bHeavy ? CrashHeavy : (bMedium ? CrashMedium : CrashLight);
	const float Strength = FMath::Clamp(Severity / 1.2f, 0.0f, 1.0f);
	PlayOneShot(PickVariant(Set), Point, FMath::Lerp(0.5f, 1.0f, Strength) * MasterVolume * CollisionVolume, FMath::RandRange(0.95f, 1.05f),
		FMath::Lerp(3500.0f, 20000.0f, Strength));
	++ImpactLayersPlayed;

	// layer 2: the panel giving way, 15-45 ms later
	if (Severity >= CrunchSeverity && GetWorld())
	{
		USoundBase* Crunch = PickVariant(Severity >= 0.8f ? CrunchHeavy : CrunchMedium);
		const float Volume = FMath::Lerp(0.55f, 0.9f, Strength) * MasterVolume * CollisionVolume;
		FTimerHandle Handle;
		GetWorld()->GetTimerManager().SetTimer(Handle, FTimerDelegate::CreateWeakLambda(this, [this, Crunch, Point, Volume]()
		{
			PlayOneShot(Crunch, Point, Volume, FMath::RandRange(0.94f, 1.04f));
			++ImpactLayersPlayed;
		}), FMath::RandRange(0.015f, 0.045f), false);
	}
	UE_LOG(LogWSPC2, Verbose, TEXT("Vehicle audio: impact %s zone %d severity %.2f"), *GetNameSafe(GetOwner()), Zone, Severity);
}

void UWSPC2VehicleAudioComponent::TriggerGlassBreak(FVector WorldLocation)
{
	if (GetNetMode() == NM_DedicatedServer)
	{
		return;
	}
	PlayOneShot(PickVariant(GlassShatter), WorldLocation, 0.8f * MasterVolume * CollisionVolume, FMath::RandRange(0.96f, 1.06f));
	++ImpactLayersPlayed;
	if (UWorld* World = GetWorld())
	{
		USoundBase* Debris = PickVariant(GlassDebris);
		FTimerHandle Handle;
		World->GetTimerManager().SetTimer(Handle, FTimerDelegate::CreateWeakLambda(this, [this, Debris, WorldLocation]()
		{
			PlayOneShot(Debris, WorldLocation - FVector(0, 0, 80.0f), 0.55f * MasterVolume * CollisionVolume, FMath::RandRange(0.95f, 1.08f));
			++ImpactLayersPlayed;
		}), FMath::RandRange(0.15f, 0.35f), false);
	}
}

void UWSPC2VehicleAudioComponent::UpdateCollisions(AWSPC2Pawn* Car, double Now, bool bAudible)
{
	const UWSPC2VehicleDamageComponent* Damage = Car->GetVehicleDamage();
	if (Damage)
	{
		if (const FWSPC2DamageImpactNet* Impact = ReadLastImpact(Damage))
		{
			if (!bImpactSequenceKnown)
			{
				bImpactSequenceKnown = true; // an impact from before this machine saw the car is not replayed
			}
			else if (Impact->Sequence != LastImpactSequence && Impact->Severity > 0.0f && bAudible)
			{
				PlayImpactLayers(Impact->WorldPoint, Impact->Severity, Impact->Zone);
			}
			LastImpactSequence = Impact->Sequence;
		}

		const int32 GlassStage = Damage->GetGlassCrackStage();
		const bool bSideGlass = Damage->IsSideGlassFractured();
		if (bAudible && (GlassStage > LastGlassStage || (bSideGlass && !bLastSideGlass)))
		{
			TriggerGlassBreak(Car->GetActorLocation() + Car->GetActorUpVector() * 110.0f);
		}
		LastGlassStage = GlassStage;
		bLastSideGlass = bSideGlass;
	}

	// a knock the damage model ignored still makes a light local bump
	if (PendingBumpTime > 0.0 && Now - PendingBumpTime > 0.06)
	{
		if (LastDamageImpactTime < PendingBumpTime - 0.02 && bAudible)
		{
			const float Strength = FMath::Clamp((PendingBumpImpulse - CrashMinImpulse) / FMath::Max(CrashHeavyImpulse - CrashMinImpulse, 1.0f), 0.0f, 1.0f);
			PlayOneShot(PickVariant(CrashLight), PendingBumpPoint, FMath::Lerp(0.35f, 0.7f, Strength) * MasterVolume * CollisionVolume,
				FMath::RandRange(0.95f, 1.08f), FMath::Lerp(3000.0f, 9000.0f, Strength));
			++ImpactLayersPlayed;
		}
		PendingBumpTime = -10.0;
	}
}

void UWSPC2VehicleAudioComponent::OnComponentHit(UPrimitiveComponent* HitComp, AActor* OtherActor, UPrimitiveComponent* OtherComp, FVector NormalImpulse, const FHitResult& Hit)
{
	OnCarHit(GetOwner(), OtherActor, NormalImpulse, Hit);

	// the server also watches sustained contacts for scraping
	AActor* Owner = GetOwner();
	if (!Owner || !Owner->HasAuthority() || !GetWorld())
	{
		return;
	}
	const FVector Point = Hit.ImpactPoint;
	FVector Normal = Hit.ImpactNormal.GetSafeNormal();
	if (Normal.IsNearlyZero())
	{
		Normal = Hit.Normal.GetSafeNormal();
	}
	const UPrimitiveComponent* Root = Cast<UPrimitiveComponent>(Owner->GetRootComponent());
	const FVector Velocity = (Root && Root->IsSimulatingPhysics()) ? Root->GetPhysicsLinearVelocityAtPoint(Point) : Owner->GetVelocity();
	const FVector OtherVelocity = (OtherComp && OtherComp->IsSimulatingPhysics()) ? OtherComp->GetPhysicsLinearVelocityAtPoint(Point) : FVector::ZeroVector;
	const FVector Relative = Velocity - OtherVelocity;
	const float Tangential = (Relative - (Relative | Normal) * Normal).Size();
	if (Tangential < ScrapeMinTangentialSpeed)
	{
		return;
	}

	EWSPC2ScrapeSurface Surface;
	if (OtherActor && OtherActor->IsA<APawn>())
	{
		Surface = EWSPC2ScrapeSurface::Metal;
	}
	else
	{
		const UPhysicalMaterial* Material = Hit.PhysMaterial.Get();
		const EPhysicalSurface Type = Material ? Material->SurfaceType.GetValue() : SurfaceType_Default;
		const float LocalZ = Owner->GetActorTransform().InverseTransformPosition(Point).Z;
		if (Type == SurfaceType4 || Type == SurfaceType5 || Type == SurfaceType6)
		{
			Surface = EWSPC2ScrapeSurface::Dirt;
		}
		else if (Type == SurfaceType1)
		{
			Surface = LocalZ < 30.0f ? EWSPC2ScrapeSurface::Plastic : EWSPC2ScrapeSurface::Asphalt;
		}
		else
		{
			Surface = EWSPC2ScrapeSurface::Concrete;
		}
	}
	ScrapeContactTime = GetWorld()->GetTimeSeconds();
	ScrapeSpeed = FMath::Max(ScrapeSpeed, Tangential);
	ScrapeForce = FMath::Max(ScrapeForce, FMath::Clamp(NormalImpulse.Size() / FMath::Max(CrashMinImpulse * 2.0f, 1.0f), 0.3f, 1.0f));
	ScrapeContactSurface = Surface;
}

void UWSPC2VehicleAudioComponent::DetectScrapeOnServer(float Delta, double Now)
{
	const bool bActive = (Now - ScrapeContactTime) < 0.12 && ScrapeSpeed >= ScrapeMinTangentialSpeed;
	FWSPC2ScrapeNet NewState;
	if (bActive)
	{
		const float SpeedFactor = FMath::Clamp(ScrapeSpeed / FMath::Max(ScrapeFullSpeed, 1.0f), 0.1f, 1.0f);
		const float Amount = SpeedFactor * (0.5f + 0.5f * FMath::Clamp(ScrapeForce, 0.0f, 1.0f));
		NewState.Surface = static_cast<uint8>(ScrapeContactSurface);
		NewState.Intensity = static_cast<uint8>(FMath::Clamp(FMath::RoundToInt(15.0f * Amount), 1, 15));
	}
	if (NewState != ScrapeNet)
	{
		ScrapeNet = NewState;
	}
	ScrapeSpeed = FMath::FInterpTo(ScrapeSpeed, 0.0f, Delta, 6.0f);
	ScrapeForce = FMath::FInterpTo(ScrapeForce, 0.0f, Delta, 6.0f);
}

void UWSPC2VehicleAudioComponent::OnRep_Scrape()
{
	// the tick follows ScrapeNet; nothing else to do when it arrives
}

void UWSPC2VehicleAudioComponent::OnCarHit(AActor* SelfActor, AActor* OtherActor, FVector NormalImpulse, const FHitResult& Hit)
{
	const float Impulse = NormalImpulse.Size();
	const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
	if (Impulse < CrashMinImpulse || Now - LastCrashTime < 0.25)
	{
		return;
	}
	LastCrashTime = Now;

	// wait a moment: when the damage model turns this hit into a replicated impact, the layered impact plays instead
	PendingBumpTime = Now;
	PendingBumpPoint = Hit.ImpactPoint;
	PendingBumpImpulse = Impulse;
}
