// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ProceduralMeshComponent.h"
#include "WSPC2DeformableMesh.generated.h"

class UMaterialInterface;
class UMaterialInstanceDynamic;
class UStaticMesh;
class UStaticMeshComponent;

UENUM(BlueprintType)
enum class EWSPC2DetachablePanel : uint8
{
	FrontBumper = 0,
	RearBumper = 1,
	Hood = 2,
	Trunk = 3,
	LeftDoor = 4,
	RightDoor = 5,
	LeftMirror = 6,
	RightMirror = 7,
	RoofLightbar = 8,
	Count = 9
};

UENUM(BlueprintType)
enum class EWSPC2PanelDamageState : uint8
{
	Intact = 0,
	Loose = 1,
	Detached = 2
};

UENUM(BlueprintType)
enum class EWSPC2GlassZone : uint8
{
	Headlight_FL = 0,
	Headlight_FR = 1,
	Taillight_RL = 2,
	Taillight_RR = 3,
	Lightbar_Glass = 4,
	Windshield = 5,
	RearWindow = 6,
	SideWindow_L = 7,
	SideWindow_R = 8,
	Count = 9
};

USTRUCT()
struct FWSPC2MeshImpactRecord
{
	GENERATED_BODY()

	UPROPERTY()
	FVector_NetQuantize LocalPos = FVector::ZeroVector;

	UPROPERTY()
	FVector_NetQuantizeNormal InwardDir = FVector(-1.0f, 0.0f, 0.0f);

	UPROPERTY()
	float Severity = 0.0f;

	UPROPERTY()
	float RadiusCm = 48.0f;

	UPROPERTY()
	float DepthCm = 14.0f;
};

/**
 * Physical world-tumbling detached vehicle part (bumper, hood, door, trunk, mirror, lightbar)
 * carrying the exact deformed ProceduralMesh geometry and materials it had at detachment.
 */
UCLASS()
class AWSPC2DetachedPartActor : public AActor
{
	GENERATED_BODY()

public:
	AWSPC2DetachedPartActor();

	UPROPERTY(VisibleAnywhere, Category = "Vehicle|Damage")
	TObjectPtr<UProceduralMeshComponent> PartMesh;

	struct FSectionInput
	{
		TArray<FVector> Vertices;
		TArray<int32> Triangles;
		TArray<FVector> Normals;
		TArray<FVector2D> UV0;
		TArray<FVector2D> UV1;
		TArray<FVector2D> UV2;
		TArray<FVector2D> UV3;
		TArray<FLinearColor> Colors;
		TArray<FProcMeshTangent> Tangents;
		TObjectPtr<UMaterialInterface> Material;
	};

	void InitFromDeformedGeometry(
		const TArray<FSectionInput>& Sections,
		const FBox& LocalBounds,
		float MassKg,
		const FVector& InheritedVelocity,
		const FVector& ImpulseDir,
		float ImpactSpeedKmh);
};

/**
 * Runtime procedural mesh cage that replaces static body/glass meshes on first impact:
 * performs welded plastic sheet-metal deformation, accordion hood buckling, sharp fold
 * normal recomputation, inverted VertexColor paint chipping, hinged/detachable body panels,
 * revealed internal engine bay / frame rails, and per-zone glass/headlight removal.
 */
class FWSPC2DeformableChassis
{
public:
	struct FDeformSection
	{
		TArray<FVector> Positions;
		TArray<FVector> RestPositions;
		TArray<FVector> Normals;
		TArray<FVector> RestNormals;
		TArray<FVector2D> UV0;
		TArray<FVector2D> UV1;
		TArray<FVector2D> UV2;
		TArray<FVector2D> UV3;
		TArray<FLinearColor> Colors;
		TArray<FProcMeshTangent> Tangents;
		TArray<int32> Triangles;
		TArray<float> CumulativeDispCm;
		TArray<FIntVector> WeldBuckets;
		TArray<int32> VertToIsland;
		TArray<uint8> IslandZones; // EWSPC2GlassZone for Glass sections
		TArray<bool> TriangleRemoved;
		TObjectPtr<UMaterialInterface> Material;
		FBox LocalBounds = FBox(ForceInit);
		bool bUsesWSPC2DamageMat = false;
		bool bDirty = false;
		bool bSectionCleared = false;
	};

	struct FPanelRuntime
	{
		TWeakObjectPtr<UProceduralMeshComponent> PMC;
		TArray<FDeformSection> Sections;
		FVector HingePivotBodySpace = FVector::ZeroVector;
		FVector HingeAxis = FVector(0.0f, 1.0f, 0.0f);
		FBox CarSpaceBounds = FBox(ForceInit);
		EWSPC2PanelDamageState State = EWSPC2PanelDamageState::Intact;
		float LooseSideSign = 1.0f;
		float BaseLooseAngleDeg = 0.0f;
		float FlutterPhase = 0.0f;
		bool bHasGeometry = false;
	};

	~FWSPC2DeformableChassis();

	bool BuildFromStaticMeshes(
		AActor* Owner,
		USceneComponent* AttachParent,
		UStaticMeshComponent* BodySMC,
		UStaticMeshComponent* GlassSMC,
		const FBox& EngineBlockBoxCarSpace,
		const TArray<TObjectPtr<UMaterialInstanceDynamic>>& BodyMIDs,
		const TArray<TObjectPtr<UMaterialInstanceDynamic>>& GlassMIDs);

	void ApplyPlasticImpact(
		const FWSPC2MeshImpactRecord& Impact,
		const FVector& ChassisTwistDeg,
		float FloorTouchTwistDeg);

	void SetPanelState(
		EWSPC2DetachablePanel Panel,
		EWSPC2PanelDamageState NewState,
		const FVector& ImpulseDirWorld,
		float SpeedKmh);

	void ShatterGlassZone(
		EWSPC2GlassZone Zone,
		const FVector& ImpulseDirWorld,
		float SpeedKmh,
		UMaterialInterface* ShardMaterial);

	void TickLoosePanels(float DeltaTime, float ForwardSpeedKmh);
	void ResetAndDestroy(UStaticMeshComponent* BodySMC, UStaticMeshComponent* GlassSMC);

	bool IsActive() const { return bInitialized; }
	bool UsesWSPC2DamageMaterial() const;
	float GetMaxVertexDisplacementCm() const { return MaxVertexDisplacementCm; }
	bool HasPanelGeometry(EWSPC2DetachablePanel Panel) const;
	EWSPC2PanelDamageState GetPanelState(EWSPC2DetachablePanel Panel) const;
	bool IsAnyBumperDragging() const;
	FVector GetAnyDraggingBumperWorldLoc() const;
	FVector GetGlassZoneCenterCarSpace(EWSPC2GlassZone Zone) const;
	bool HasGlassZoneGeometry(EWSPC2GlassZone Zone) const;

	const TArray<TWeakObjectPtr<UProceduralMeshComponent>>& GetActiveBodyPMCs() const { return AllCreatedPMCs; }

private:
	void CreateInternalEngineCore(AActor* Owner, USceneComponent* AttachParent, const FBox& EngineBlockBoxCarSpace);
	void UpdateInternalCoreVisibility();
	void DarkenLightCavityInBody(const FVector& CarSpaceCenter, float RadiusCm);
	void SpawnGlassShards(const FVector& CarSpaceCenter, const FVector& ImpulseDirWorld, float SpeedKmh, UMaterialInterface* ShardMat);
	void PushDirtySections();
	void RebuildGlassSectionFromActiveTriangles(int32 SecIdx);

	TWeakObjectPtr<AActor> OwnerActor;
	TWeakObjectPtr<USceneComponent> AttachParentComp;

	TWeakObjectPtr<UProceduralMeshComponent> MainBodyPMC;
	TWeakObjectPtr<UProceduralMeshComponent> GlassPMC;
	TWeakObjectPtr<UProceduralMeshComponent> EngineCorePMC;

	TArray<TWeakObjectPtr<UProceduralMeshComponent>> AllCreatedPMCs;
	TArray<TObjectPtr<UStaticMeshComponent>> InternalCoreMeshes;
	TArray<TWeakObjectPtr<AWSPC2DetachedPartActor>> SpawnedDetachedActors;

	TArray<FDeformSection> MainBodySections;
	TArray<FDeformSection> GlassSections;
	FPanelRuntime Panels[static_cast<int32>(EWSPC2DetachablePanel::Count)];

	FVector GlassZoneCentersCarSpace[static_cast<int32>(EWSPC2GlassZone::Count)];
	bool GlassZoneHasTris[static_cast<int32>(EWSPC2GlassZone::Count)];
	bool GlassZoneShattered[static_cast<int32>(EWSPC2GlassZone::Count)];

	FTransform BodyRelativeTransform = FTransform::Identity;
	FTransform GlassRelativeTransform = FTransform::Identity;
	FBox BodyBoundsCarSpace = FBox(ForceInit);
	float BodyWindingSign = 1.0f;
	float MaxVertexDisplacementCm = 0.0f;
	float GlobalTwistPhase = 0.0f;
	bool bInitialized = false;
	bool bInternalCoreVisible = false;
};
