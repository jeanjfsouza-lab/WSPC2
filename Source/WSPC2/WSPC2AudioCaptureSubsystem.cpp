#include "WSPC2AudioCaptureSubsystem.h"
#include "WSPC2Pawn.h"
#include "WSPC2VehicleAudioComponent.h"
#include "WSPC2.h"
#include "AudioDevice.h"
#include "AudioMixerBlueprintLibrary.h"
#include "Camera/PlayerCameraManager.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "Misc/CommandLine.h"
#include "Misc/Paths.h"
#include "Sound/SoundSubmixSend.h"
#include "TimerManager.h"

bool UWSPC2AudioCaptureSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	const UWorld* World = Cast<UWorld>(Outer);
	if (!World || !(World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE))
	{
		return false;
	}
	const TCHAR* Cmd = FCommandLine::Get();
	FString Ignored;
	return FParse::Value(Cmd, TEXT("WSPC2AudioCapture="), Ignored) || FParse::Param(Cmd, TEXT("WSPC2AudioCapture"))
		|| FParse::Param(Cmd, TEXT("WSPC2AudioTrace"));
}

void UWSPC2AudioCaptureSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	if (InWorld.GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	const TCHAR* Cmd = FCommandLine::Get();
	bTrace = FParse::Param(Cmd, TEXT("WSPC2AudioTrace"));
	bCapture = FParse::Value(Cmd, TEXT("WSPC2AudioCapture="), CaptureName) || FParse::Param(Cmd, TEXT("WSPC2AudioCapture"));
	if (CaptureName.IsEmpty())
	{
		CaptureName = TEXT("capture");
	}
	FParse::Value(Cmd, TEXT("WSPC2AudioCaptureSeconds="), CaptureSeconds);
	FParse::Value(Cmd, TEXT("WSPC2AudioCaptureDelay="), CaptureDelay);

	FTimerManager& Timers = InWorld.GetTimerManager();
	if (bCapture)
	{
		Timers.SetTimer(StartHandle, FTimerDelegate::CreateUObject(this, &UWSPC2AudioCaptureSubsystem::StartCapture), FMath::Max(CaptureDelay, 0.1f), false);
	}
	if (bTrace)
	{
		Timers.SetTimer(TraceHandle, FTimerDelegate::CreateUObject(this, &UWSPC2AudioCaptureSubsystem::Trace), 1.0f, true);
	}
	UE_LOG(LogWSPC2, Log, TEXT("AudioCapture: hooks ready (capture=%d name=%s seconds=%.0f trace=%d)"),
		bCapture ? 1 : 0, *CaptureName, CaptureSeconds, bTrace ? 1 : 0);
}

void UWSPC2AudioCaptureSubsystem::StartCapture()
{
	UWorld* World = GetWorld();
	if (!World || bRecording)
	{
		return;
	}
	UAudioMixerBlueprintLibrary::StartRecordingOutput(World, CaptureSeconds + 5.0f);
	bRecording = true;
	World->GetTimerManager().SetTimer(StopHandle, FTimerDelegate::CreateUObject(this, &UWSPC2AudioCaptureSubsystem::StopCapture), CaptureSeconds, false);
	LogProof(TEXT("start"));
	UE_LOG(LogWSPC2, Log, TEXT("AudioCapture: recording %s for %.0f s"), *CaptureName, CaptureSeconds);
}

void UWSPC2AudioCaptureSubsystem::StopCapture()
{
	UWorld* World = GetWorld();
	if (!World || !bRecording)
	{
		return;
	}
	bRecording = false;
	const FString Folder = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("Audio/Pipeline/capture"));
	IFileManager::Get().MakeDirectory(*Folder, true);
	UAudioMixerBlueprintLibrary::StopRecordingOutput(World, EAudioRecordingExportType::WavFile, CaptureName, Folder);
	LogProof(TEXT("end"));
	UE_LOG(LogWSPC2, Log, TEXT("AudioCapture: saved %s/%s.wav"), *Folder, *CaptureName);
}

void UWSPC2AudioCaptureSubsystem::LogProof(const TCHAR* When)
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	for (TActorIterator<AWSPC2Pawn> It(World); It; ++It)
	{
		const UWSPC2VehicleAudioComponent* Audio = It->GetVehicleAudio();
		if (!Audio)
		{
			continue;
		}
		UE_LOG(LogWSPC2, Log, TEXT("AudioProof %s: %s source=%s family=%s lod=%d voices=%d starts=%d builds=%d impacts=%d local=%d"),
			When, *It->GetName(), *Audio->GetEngineSourceName(), *Audio->GetActiveEngineFamilyName(), Audio->GetAudioLod(),
			Audio->GetEngineVoiceCount(), Audio->GetEngineVoicePlayCount(), Audio->GetEngineVoiceBuilds(),
			Audio->GetImpactLayersPlayed(), It->IsLocallyControlled() ? 1 : 0);
	}
}

void UWSPC2AudioCaptureSubsystem::Trace()
{
	UWorld* World = GetWorld();
	const APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	if (!PC)
	{
		return;
	}
	const FVector Listener = PC->PlayerCameraManager ? PC->PlayerCameraManager->GetCameraLocation() : PC->GetFocalLocation();
	int32 Cars = 0;
	int32 EngineVoices = 0;
	int32 AudibleVoices = 0;
	int32 Lods[4] = { 0, 0, 0, 0 }; // culled, LOD0, LOD1, LOD2
	for (TActorIterator<AWSPC2Pawn> It(World); It; ++It)
	{
		const UWSPC2VehicleAudioComponent* Audio = It->GetVehicleAudio();
		if (Audio)
		{
			++Cars;
			EngineVoices += Audio->GetEngineVoiceCount();
			AudibleVoices += Audio->GetAudibleEngineVoiceCount();
			++Lods[FMath::Clamp(Audio->GetAudioLod() + 1, 0, 3)];
		}
		const float Distance = FVector::Dist(Listener, It->GetActorLocation());
		if (!Audio || Distance > 6000.0f)
		{
			continue;
		}
		UE_LOG(LogWSPC2, Log, TEXT("AudioTrace: %s dist=%.0fm source=%s family=%s lod=%d rpm=%.0f load=%.2f gain=%.2f voices=%d starts=%d impacts=%d scrape=%d/%d local=%d"),
			*It->GetName(), Distance / 100.0f, *Audio->GetEngineSourceName(), *Audio->GetActiveEngineFamilyName(),
			Audio->GetAudioLod(), Audio->GetSmoothedRpm(), Audio->GetSmoothedLoad(), Audio->GetAudibleEngineGain(),
			Audio->GetEngineVoiceCount(), Audio->GetEngineVoicePlayCount(), Audio->GetImpactLayersPlayed(),
			static_cast<int32>(Audio->GetScrapeSurface()), Audio->GetScrapeIntensity(), It->IsLocallyControlled() ? 1 : 0);
	}

	// voice budget of the whole scene (game-thread data only: the audio device's own lists belong to the audio
	// thread): engine voices by level of detail and how many of them are audible this frame (silent ones are virtual)
	const FAudioDeviceHandle Device = World->GetAudioDevice();
	UE_LOG(LogWSPC2, Log, TEXT("AudioBudget: cars=%d engineVoices=%d audibleEngineVoices=%d lod0=%d lod1=%d lod2=%d culled=%d maxChannels=%d fps=%.0f"),
		Cars, EngineVoices, AudibleVoices, Lods[1], Lods[2], Lods[3], Lods[0], Device ? Device->GetMaxChannels() : -1,
		World->GetDeltaSeconds() > 0.0f ? 1.0f / World->GetDeltaSeconds() : 0.0f);
}

void UWSPC2AudioCaptureSubsystem::Deinitialize()
{
	if (bRecording)
	{
		StopCapture();
	}
	Super::Deinitialize();
}
