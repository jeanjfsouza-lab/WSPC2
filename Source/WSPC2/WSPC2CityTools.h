// Editor helpers used by the city build scripts (Tools/citymap). They do nothing in a packaged game.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "WSPC2CityTools.generated.h"

class ALandscape;
class ULandscapeLayerInfoObject;
class UMaterialInterface;
class UStaticMesh;

UCLASS()
class UWSPC2CityTools : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:

	/**
	 * Editor only. Creates a landscape in the world from raw files on disk:
	 *  HeightmapFile  VertsX * VertsY little-endian uint16 heights (Unreal's encoding: 32768 = zero)
	 *  LayerFiles[i]  VertsX * VertsY uint8 paint weights for LayerInfos[i] (all layers summing to 255)
	 * VertsX - 1 and VertsY - 1 must be whole multiples of QuadsPerSection * SectionsPerComponent.
	 * Location is where the first vertex goes; Scale is the landscape's scale (X/Y = vertex spacing in cm).
	 */
	UFUNCTION(BlueprintCallable, Category = "WSPC2|City", meta = (WorldContext = "WorldContextObject"))
	static ALandscape* CreateLandscapeFromRaw(UObject* WorldContextObject, const FString& HeightmapFile, int32 VertsX, int32 VertsY,
		int32 QuadsPerSection, int32 SectionsPerComponent, FVector Location, FVector Scale, UMaterialInterface* Material,
		const TArray<ULandscapeLayerInfoObject*>& LayerInfos, const TArray<FString>& LayerFiles);

	/** Editor only. Merges the landscape's edit layers into its final textures right away; true when up to date. */
	UFUNCTION(BlueprintCallable, Category = "WSPC2|City")
	static bool UpdateLandscapeNow(ALandscape* Landscape);

	/**
	 * Editor only. Merges every mesh component of the actors (instanced components expanded, materials kept)
	 * into one static mesh asset, pivot at the world origin. PackageName is the full asset path, e.g.
	 * /Game/CityMap/Buildings/SM_Tower. Returns the new mesh (not yet saved).
	 */
	UFUNCTION(BlueprintCallable, Category = "WSPC2|City")
	static UStaticMesh* MergeActorsToStaticMesh(const TArray<AActor*>& Actors, const FString& PackageName, bool bNanite);

	/**
	 * Editor only. Same as MergeActorsToStaticMesh for a chosen set of components. Nanite takes at most 64 material
	 * sections per mesh, so a big building is merged as several such sets.
	 */
	UFUNCTION(BlueprintCallable, Category = "WSPC2|City")
	static UStaticMesh* MergeComponentsToStaticMesh(const TArray<UStaticMeshComponent*>& Components, const FString& PackageName, bool bNanite);

	/**
	 * Editor only. Edits a static mesh in place, keeping only the triangles inside (bKeepInside) or outside a cylinder
	 * whose axis runs along the mesh's Y axis: centre Centre (mesh space, cm), radius Radius, Y from YMin to YMax.
	 * A triangle is inside when its centre is. Both the hi-res (Nanite) source and LOD 0 are edited, then rebuilt.
	 * Returns the number of triangles removed from LOD 0. Used to cut wheel hardware out of a car body.
	 */
	UFUNCTION(BlueprintCallable, Category = "WSPC2|Vehicle")
	static int32 KeepTrianglesInCylinder(UStaticMesh* Mesh, FVector Centre, float Radius, float YMin, float YMax, bool bKeepInside);

	/**
	 * Editor only. As KeepTrianglesInCylinder, for a cylinder on any axis: centre Centre, axis direction Axis (mesh
	 * space), radius Radius, from AlongMin to AlongMax cm along the axis measured from the centre. Used to cut the
	 * steering wheel (whose axis leans back towards the driver) out of a car body.
	 */
	UFUNCTION(BlueprintCallable, Category = "WSPC2|Vehicle")
	static int32 KeepTrianglesInAxisCylinder(UStaticMesh* Mesh, FVector Centre, FVector Axis, float Radius, float AlongMin, float AlongMax, bool bKeepInside);

	/**
	 * Editor only. Spawns one actor holding a single instanced component that draws Mesh at every transform
	 * (world space). With bCollision the instances block everything; bHiddenInGame hides them (collision only).
	 * bLightweight keeps them out of ray tracing and distance fields (vegetation, street furniture).
	 */
	UFUNCTION(BlueprintCallable, Category = "WSPC2|City", meta = (WorldContext = "WorldContextObject"))
	static AActor* SpawnInstancedMeshes(UObject* WorldContextObject, UStaticMesh* Mesh, const TArray<FTransform>& Transforms,
		bool bCollision, bool bHiddenInGame, const FString& Label, const FString& Folder, float CullDistance, bool bLightweight);
};
