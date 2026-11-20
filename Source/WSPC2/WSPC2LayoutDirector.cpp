#include "WSPC2LayoutDirector.h"
#include "WSPC2.h"
#include "Components/PrimitiveComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/GameModeBase.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Net/UnrealNetwork.h"

namespace
{
	const TCHAR* LayoutTagPrefix = TEXT("WSPC2Layout.");
	const FName PhysicsTag(TEXT("WSPC2Physics"));
}

AWSPC2LayoutDirector::AWSPC2LayoutDirector()
{
	PrimaryActorTick.bCanEverTick = false;
	bReplicates = true;
	bAlwaysRelevant = true;

	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

void AWSPC2LayoutDirector::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AWSPC2LayoutDirector, ActiveLayout);
}

void AWSPC2LayoutDirector::BeginPlay()
{
	Super::BeginPlay();

	if (HasAuthority())
	{
		FName Chosen = DefaultLayout;
		FString Named;

		if (const AGameModeBase* GameMode = GetWorld()->GetAuthGameMode())
		{
			const FString FromUrl = UGameplayStatics::ParseOption(GameMode->OptionsString, TEXT("layout"));

			if (!FromUrl.IsEmpty())
			{
				Named = FromUrl;
			}
		}

		// test hook: -WSPC2Layout=<name> overrides the map's URL
		FString FromCommandLine;

		if (FParse::Value(FCommandLine::Get(), TEXT("WSPC2Layout="), FromCommandLine))
		{
			Named = FromCommandLine;
		}

		if (!Named.IsEmpty())
		{
			Chosen = Named.Equals(TEXT("none"), ESearchCase::IgnoreCase) ? NAME_None : FName(*Named);
		}

		ActiveLayout = Chosen;
	}

	// a client that joins while no layout is active gets no OnRep: it hides them all here
	ApplyLayout();
}

void AWSPC2LayoutDirector::SetActiveLayout(FName Layout)
{
	if (!HasAuthority() || Layout == ActiveLayout)
	{
		return;
	}

	ActiveLayout = Layout;
	ForceNetUpdate();
	ApplyLayout();
}

void AWSPC2LayoutDirector::OnRep_ActiveLayout()
{
	ApplyLayout();
}

void AWSPC2LayoutDirector::ApplyLayout()
{
	const FString Wanted = ActiveLayout.IsNone() ? FString() : FString(LayoutTagPrefix) + ActiveLayout.ToString();
	int32 Shown = 0;
	int32 Hidden = 0;

	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		AActor* Actor = *It;
		bool bInLayout = false;
		bool bActive = false;

		for (const FName& Tag : Actor->Tags)
		{
			const FString Text = Tag.ToString();

			if (Text.StartsWith(LayoutTagPrefix))
			{
				bInLayout = true;
				bActive = bActive || (!Wanted.IsEmpty() && Text.Equals(Wanted, ESearchCase::IgnoreCase));
			}
		}

		if (!bInLayout)
		{
			continue;
		}

		Actor->SetActorHiddenInGame(!bActive);
		Actor->SetActorEnableCollision(bActive);

		if (Actor->ActorHasTag(PhysicsTag))
		{
			if (UPrimitiveComponent* Body = Cast<UPrimitiveComponent>(Actor->GetRootComponent()))
			{
				Body->SetSimulatePhysics(bActive);
			}
		}

		(bActive ? Shown : Hidden)++;
	}

	UE_LOG(LogWSPC2, Log, TEXT("Layout '%s': %d actors shown, %d hidden"), *ActiveLayout.ToString(), Shown, Hidden);
}
