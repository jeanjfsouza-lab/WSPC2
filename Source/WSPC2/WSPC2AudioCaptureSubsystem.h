// Test hooks of the vehicle audio, driven from the command line:
//   -WSPC2AudioCapture=<Name>    records the main audio output to Saved/Audio/Pipeline/capture/<Name>.wav
//   -WSPC2AudioCaptureSeconds=N  length of the recording (default 60)
//   -WSPC2AudioCaptureDelay=S    wait before recording starts (default 1)
//   -WSPC2AudioTrace             logs the audio state of the vehicles near the listener once per second
//   -WSPC2AudioStems             engines play the recorded/synthetic stems instead of the engine-sim banks (A/B)
// When a capture ends it logs one "AudioProof" line per vehicle on an engine-sim bank: how many engine voices it
// has, how many times an engine voice was started and how many voice sets were built. For the listener's car,
// builds=1 and starts=voices prove that no engine loop restarted during the run.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "WSPC2AudioCaptureSubsystem.generated.h"

UCLASS()
class UWSPC2AudioCaptureSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;

private:
	void StartCapture();
	void StopCapture();
	void Trace();
	void LogProof(const TCHAR* When);

	FTimerHandle StartHandle;
	FTimerHandle StopHandle;
	FTimerHandle TraceHandle;
	FString CaptureName;
	float CaptureSeconds = 60.0f;
	float CaptureDelay = 1.0f;
	bool bCapture = false;
	bool bRecording = false;
	bool bTrace = false;
};
