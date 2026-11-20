// Editor helpers used by the city build scripts (Tools/citymap).

#include "WSPC2CityTools.h"
#include "WSPC2.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Misc/FileHelper.h"
#include "Landscape.h"
#include "LandscapeInfo.h"
#include "LandscapeProxy.h"
#include "LandscapeLayerInfoObject.h"
#include "LandscapeSubsystem.h"
#include "Materials/MaterialInterface.h"
#include "Engine/StaticMesh.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "GameFramework/Actor.h"

#if WITH_EDITOR
#include "MeshMergeModule.h"
#include "IMeshMergeUtilities.h"
#include "MeshMerge/MeshMergingSettings.h"
#include "Modules/ModuleManager.h"
#include "MeshDescription.h"
#endif

ALandscape* UWSPC2CityTools::CreateLandscapeFromRaw(UObject* WorldContextObject, const FString& HeightmapFile, int32 VertsX, int32 VertsY,
	int32 QuadsPerSection, int32 SectionsPerComponent, FVector Location, FVector Scale, UMaterialInterface* Material,
	const TArray<ULandscapeLayerInfoObject*>& LayerInfos, const TArray<FString>& LayerFiles)
{
#if WITH_EDITOR
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;
	if (!World)
	{
		UE_LOG(LogWSPC2, Error, TEXT("CreateLandscapeFromRaw: no world"));
		return nullptr;
	}

	const int32 QuadsPerComponent = QuadsPerSection * SectionsPerComponent;
	if (QuadsPerComponent <= 0 || (VertsX - 1) % QuadsPerComponent != 0 || (VertsY - 1) % QuadsPerComponent != 0)
	{
		UE_LOG(LogWSPC2, Error, TEXT("CreateLandscapeFromRaw: %d x %d vertices do not fit components of %d quads"), VertsX, VertsY, QuadsPerComponent);
		return nullptr;
	}

	const int64 VertexCount = int64(VertsX) * int64(VertsY);

	TArray<uint8> Bytes;
	if (!FFileHelper::LoadFileToArray(Bytes, *HeightmapFile) || Bytes.Num() != VertexCount * 2)
	{
		UE_LOG(LogWSPC2, Error, TEXT("CreateLandscapeFromRaw: %s is missing or is not %lld bytes"), *HeightmapFile, VertexCount * 2);
		return nullptr;
	}

	TArray<uint16> Heights;
	Heights.SetNumUninitialized(VertexCount);
	FMemory::Memcpy(Heights.GetData(), Bytes.GetData(), Bytes.Num());
	Bytes.Empty();

	TArray<FLandscapeImportLayerInfo> ImportLayers;
	for (int32 Index = 0; Index < LayerInfos.Num(); ++Index)
	{
		ULandscapeLayerInfoObject* LayerInfo = LayerInfos[Index];
		if (!LayerInfo)
		{
			continue;
		}

		FLandscapeImportLayerInfo Layer(LayerInfo->GetLayerName());
		Layer.LayerInfo = LayerInfo;

		if (LayerFiles.IsValidIndex(Index) && !LayerFiles[Index].IsEmpty())
		{
			if (!FFileHelper::LoadFileToArray(Layer.LayerData, *LayerFiles[Index]) || Layer.LayerData.Num() != VertexCount)
			{
				UE_LOG(LogWSPC2, Warning, TEXT("CreateLandscapeFromRaw: layer file %s is missing or the wrong size; layer left empty"), *LayerFiles[Index]);
				Layer.LayerData.Reset();
			}
		}

		ImportLayers.Add(MoveTemp(Layer));
	}

	TMap<FGuid, TArray<uint16>> HeightDataPerLayers;
	HeightDataPerLayers.Add(FGuid(), MoveTemp(Heights));

	TMap<FGuid, TArray<FLandscapeImportLayerInfo>> LayerDataPerLayers;
	LayerDataPerLayers.Add(FGuid(), MoveTemp(ImportLayers));

	ALandscape* Landscape = World->SpawnActor<ALandscape>(Location, FRotator::ZeroRotator);
	if (!Landscape)
	{
		UE_LOG(LogWSPC2, Error, TEXT("CreateLandscapeFromRaw: could not spawn the landscape"));
		return nullptr;
	}

	Landscape->LandscapeMaterial = Material;
	Landscape->SetActorRelativeScale3D(Scale);
	Landscape->StaticLightingLOD = FMath::DivideAndRoundUp(FMath::CeilLogTwo((VertsX * VertsY) / (2048 * 2048) + 1), (uint32)2);

	Landscape->Import(FGuid::NewGuid(), 0, 0, VertsX - 1, VertsY - 1, SectionsPerComponent, QuadsPerSection, HeightDataPerLayers,
		TEXT(""), LayerDataPerLayers, ELandscapeImportAlphamapType::Additive, TArrayView<const FLandscapeLayer>());

	ULandscapeInfo* Info = Landscape->GetLandscapeInfo();
	if (Info)
	{
		Info->UpdateLayerInfoMap(Landscape);

		for (ULandscapeLayerInfoObject* LayerInfo : LayerInfos)
		{
			if (!LayerInfo)
			{
				continue;
			}

			Landscape->AddTargetLayer(LayerInfo->GetLayerName(), FLandscapeTargetLayerSettings(LayerInfo));

			const int32 LayerIndex = Info->GetLayerInfoIndex(LayerInfo->GetLayerName());
			if (LayerIndex != INDEX_NONE)
			{
				Info->Layers[LayerIndex].LayerInfoObj = LayerInfo;
			}
		}
	}

	// merge the edit layers into the final height and paint textures now (needs a GPU), so a save straight after keeps them
	Landscape->ForceUpdateLayersContent();

	UE_LOG(LogWSPC2, Log, TEXT("CreateLandscapeFromRaw: %d x %d vertices, %d layers, at %s scale %s, up to date: %d"),
		VertsX, VertsY, LayerInfos.Num(), *Location.ToString(), *Scale.ToString(), Landscape->IsUpToDate() ? 1 : 0);

	return Landscape;
#else
	return nullptr;
#endif
}

UStaticMesh* UWSPC2CityTools::MergeActorsToStaticMesh(const TArray<AActor*>& Actors, const FString& PackageName, bool bNanite)
{
	TArray<UStaticMeshComponent*> Components;
	for (AActor* Actor : Actors)
	{
		if (Actor)
		{
			TArray<UStaticMeshComponent*> MeshComponents;
			Actor->GetComponents<UStaticMeshComponent>(MeshComponents, true);
			Components.Append(MeshComponents);
		}
	}
	return MergeComponentsToStaticMesh(Components, PackageName, bNanite);
}

UStaticMesh* UWSPC2CityTools::MergeComponentsToStaticMesh(const TArray<UStaticMeshComponent*>& MeshComponents, const FString& PackageName, bool bNanite)
{
#if WITH_EDITOR
	TArray<UPrimitiveComponent*> Components;
	UWorld* World = nullptr;
	for (UStaticMeshComponent* Component : MeshComponents)
	{
		if (Component && Component->GetStaticMesh() && Component->IsVisible())
		{
			const UInstancedStaticMeshComponent* Instanced = Cast<UInstancedStaticMeshComponent>(Component);
			if (Instanced && Instanced->GetInstanceCount() == 0)
			{
				continue;
			}
			World = World ? World : Component->GetWorld();
			Components.Add(Component);
		}
	}

	if (!World || Components.Num() == 0)
	{
		UE_LOG(LogWSPC2, Warning, TEXT("MergeActorsToStaticMesh: nothing to merge for %s"), *PackageName);
		return nullptr;
	}

	FMeshMergingSettings Settings;
	Settings.LODSelectionType = EMeshLODSelectionType::SpecificLOD;
	Settings.SpecificLOD = 0;
	Settings.bMergeMaterials = false;
	Settings.bMergePhysicsData = false;
	Settings.bGenerateLightMapUV = false;
	Settings.bIncludeImposters = false;
	Settings.bAllowDistanceField = true;
	Settings.PivotType = EMeshMergePivotType::WorldOrigin;
	Settings.NaniteSettings.bEnabled = bNanite;
	// the fallback mesh feeds ray tracing and distance fields: a light one keeps thousands of instances affordable
	Settings.NaniteSettings.FallbackTarget = ENaniteFallbackTarget::PercentTriangles;
	Settings.NaniteSettings.FallbackPercentTriangles = 0.03f;

	const IMeshMergeUtilities& Utilities = FModuleManager::Get().LoadModuleChecked<IMeshMergeModule>("MeshMergeUtilities").GetUtilities();
	TArray<UObject*> Created;
	FVector Pivot = FVector::ZeroVector;
	Utilities.MergeComponentsToStaticMesh(Components, World, Settings, nullptr, nullptr, PackageName, Created, Pivot, 1.0f, true);

	for (UObject* Object : Created)
	{
		if (UStaticMesh* Mesh = Cast<UStaticMesh>(Object))
		{
			UE_LOG(LogWSPC2, Log, TEXT("MergeActorsToStaticMesh: %s from %d components"), *Mesh->GetPathName(), Components.Num());
			return Mesh;
		}
	}

	UE_LOG(LogWSPC2, Warning, TEXT("MergeActorsToStaticMesh: merge produced no mesh for %s"), *PackageName);
	return nullptr;
#else
	return nullptr;
#endif
}

AActor* UWSPC2CityTools::SpawnInstancedMeshes(UObject* WorldContextObject, UStaticMesh* Mesh, const TArray<FTransform>& Transforms,
	bool bCollision, bool bHiddenInGame, const FString& Label, const FString& Folder, float CullDistance, bool bLightweight)
{
#if WITH_EDITOR
	UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::LogAndReturnNull) : nullptr;
	if (!World || !Mesh || Transforms.Num() == 0)
	{
		return nullptr;
	}

	AActor* Actor = World->SpawnActor<AActor>(AActor::StaticClass(), FTransform::Identity);
	if (!Actor)
	{
		return nullptr;
	}

	// hierarchical: per-cluster culling and LOD, which non-Nanite meshes (the park trees) need in large numbers
	UHierarchicalInstancedStaticMeshComponent* Instances = NewObject<UHierarchicalInstancedStaticMeshComponent>(Actor, TEXT("Instances"), RF_Transactional);
	Instances->SetMobility(EComponentMobility::Static);
	Actor->SetRootComponent(Instances);
	Actor->AddInstanceComponent(Instances);
	Instances->SetStaticMesh(Mesh);
	Instances->SetCollisionProfileName(bCollision ? UCollisionProfile::BlockAll_ProfileName : UCollisionProfile::NoCollision_ProfileName);
	Instances->SetCollisionEnabled(bCollision ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
	Instances->SetHiddenInGame(bHiddenInGame);
	// collision only: invisible in the editor too, where the grey boxes would otherwise hide the buildings they enclose
	Instances->SetVisibility(!bHiddenInGame);
	Instances->SetCastShadow(!bHiddenInGame);
	if (bLightweight || bHiddenInGame)
	{
		// many small things: out of the ray tracing scene and the distance fields, which would cost more than they give
		Instances->bVisibleInRayTracing = false;
		Instances->bAffectDistanceFieldLighting = false;
		Instances->bAffectDynamicIndirectLighting = !bHiddenInGame;
	}
	if (CullDistance > 0.0f)
	{
		Instances->SetCullDistances(0, int32(CullDistance));
	}
	Instances->RegisterComponent();
	Instances->AddInstances(Transforms, false, true);

	Actor->SetActorLabel(Label);
	Actor->SetFolderPath(FName(*Folder));
	return Actor;
#else
	return nullptr;
#endif
}

bool UWSPC2CityTools::UpdateLandscapeNow(ALandscape* Landscape)
{
#if WITH_EDITOR
	if (!Landscape)
	{
		return false;
	}

	Landscape->ForceUpdateLayersContent();
	return Landscape->IsUpToDate();
#else
	return false;
#endif
}

#if WITH_EDITOR
namespace
{
	/**
	 * Removes the polygons of one mesh description that fall on the unwanted side of the cylinder; returns how many
	 * triangles went with them. Whole polygons are removed: deleting single triangles that belong to a polygon
	 * trips an assertion in the engine's element indexer.
	 */
	int32 CutDescription(FMeshDescription& Description, const FVector& Centre, const FVector& Axis, float Radius, float AlongMin, float AlongMax, bool bKeepInside)
	{
		const FVector3f A = FVector3f(Axis.GetSafeNormal());
		const FVector3f C = FVector3f(Centre);
		const auto Positions = static_cast<const FMeshDescription&>(Description).GetVertexPositions();
		TArray<FPolygonID> Doomed;
		int32 DoomedTriangles = 0;

		for (const FPolygonID Polygon : Description.Polygons().GetElementIDs())
		{
			TArray<FVertexID> Vertices;
			Description.GetPolygonVertices(Polygon, Vertices);
			if (Vertices.Num() == 0)
			{
				continue;
			}

			FVector3f Middle = FVector3f::ZeroVector;
			for (const FVertexID Vertex : Vertices)
			{
				Middle += Positions[Vertex];
			}
			Middle /= static_cast<float>(Vertices.Num());

			const FVector3f D = Middle - C;
			const float Along = FVector3f::DotProduct(D, A);
			const bool bInside = Along >= AlongMin && Along <= AlongMax && (D - A * Along).SizeSquared() <= Radius * Radius;

			if (bInside != bKeepInside)
			{
				Doomed.Add(Polygon);
				DoomedTriangles += Description.GetPolygonTriangles(Polygon).Num();
			}
		}

		Description.DeletePolygons(Doomed);
		return DoomedTriangles;
	}
}
#endif

int32 UWSPC2CityTools::KeepTrianglesInCylinder(UStaticMesh* Mesh, FVector Centre, float Radius, float YMin, float YMax, bool bKeepInside)
{
	return KeepTrianglesInAxisCylinder(Mesh, Centre, FVector(0.0, 1.0, 0.0), Radius, YMin - Centre.Y, YMax - Centre.Y, bKeepInside);
}

int32 UWSPC2CityTools::KeepTrianglesInAxisCylinder(UStaticMesh* Mesh, FVector Centre, FVector Axis, float Radius, float AlongMin, float AlongMax, bool bKeepInside)
{
#if WITH_EDITOR
	if (!Mesh || Axis.IsNearlyZero())
	{
		return 0;
	}

	Mesh->Modify();
	int32 Removed = 0;

	if (Mesh->IsHiResMeshDescriptionValid())
	{
		if (FMeshDescription* HiRes = Mesh->GetHiResMeshDescription())
		{
			const int32 HiResRemoved = CutDescription(*HiRes, Centre, Axis, Radius, AlongMin, AlongMax, bKeepInside);
			Mesh->CommitHiResMeshDescription();
			UE_LOG(LogWSPC2, Log, TEXT("KeepTrianglesInCylinder: %s hi-res source, %d triangles removed"), *Mesh->GetName(), HiResRemoved);
		}
	}

	if (FMeshDescription* Lod0 = Mesh->GetMeshDescription(0))
	{
		Removed = CutDescription(*Lod0, Centre, Axis, Radius, AlongMin, AlongMax, bKeepInside);
		Mesh->CommitMeshDescription(0);
	}

	Mesh->Build(false);
	Mesh->PostEditChange();
	Mesh->MarkPackageDirty();

	UE_LOG(LogWSPC2, Log, TEXT("KeepTrianglesInCylinder: %s LOD 0, %d triangles removed, %d left"),
		*Mesh->GetName(), Removed, Mesh->GetMeshDescription(0) ? Mesh->GetMeshDescription(0)->Triangles().Num() : 0);
	return Removed;
#else
	return 0;
#endif
}
