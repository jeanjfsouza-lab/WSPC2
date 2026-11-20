#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WSPC2LayoutDirector.generated.h"

/**
 *  Shows one of several sets of actors placed in the same spot of a map, and hides the others: the cones and
 *  barriers of the training ground, a different set for each operation that uses it.
 *
 *  An actor belongs to a layout by its tag "WSPC2Layout.<name>". The actors of the active layout are visible and
 *  solid; all others are hidden, have no collision and do not simulate. An actor also tagged "WSPC2Physics" (a
 *  cone) simulates physics while its layout is active.
 *
 *  One of these stands in the map (Tools/bay/build_bay.py, stage "training"). The server chooses the layout and
 *  replicates its name; every machine applies it to its own copy of the actors.
 *  Chosen, in this order, by: the command line (-WSPC2Layout=Op04), the map's URL (?layout=Op04), DefaultLayout.
 *  "none" shows no layout.
 */
UCLASS()
class AWSPC2LayoutDirector : public AActor
{
	GENERATED_BODY()

public:

	AWSPC2LayoutDirector();

	/** The layout shown when neither the command line nor the map's URL names one (None: no layout) */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Layout")
	FName DefaultLayout;

	/** Server only: shows this layout and hides the others, on every machine */
	UFUNCTION(BlueprintCallable, Category = "Layout")
	void SetActiveLayout(FName Layout);

	UFUNCTION(BlueprintPure, Category = "Layout")
	FName GetActiveLayout() const { return ActiveLayout; }

	virtual void BeginPlay() override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

protected:

	UPROPERTY(ReplicatedUsing = OnRep_ActiveLayout)
	FName ActiveLayout;

	UFUNCTION()
	void OnRep_ActiveLayout();

	/** Shows the active layout's actors and hides those of every other layout, on this machine */
	void ApplyLayout();
};
