// Copyright Epic Games, Inc. All Rights Reserved.

#include "WSPC2DeformableMesh.h"
#include "WSPC2.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "StaticMeshResources.h"

namespace WSPC2Deform
{
	struct FDisjointSet
	{
		TArray<int32> Parent;

		void Init(int32 Count)
		{
			Parent.SetNumUninitialized(Count);
			for (int32 i = 0; i < Count; ++i)
			{
				Parent[i] = i;
			}
		}

		int32 Find(int32 X)
		{
			while (Parent[X] != X)
			{
				Parent[X] = Parent[Parent[X]];
				X = Parent[X];
			}
			return X;
		}

		void Unite(int32 A, int32 B)
		{
			const int32 RA = Find(A);
			const int32 RB = Find(B);
			if (RA != RB)
			{
				Parent[RB] = RA;
			}
		}
	};

	FIntVector QuantizeHalfCm(const FVector& Pos)
	{
		return FIntVector(
			FMath::RoundToInt(Pos.X * 2.0),
			FMath::RoundToInt(Pos.Y * 2.0),
			FMath::RoundToInt(Pos.Z * 2.0));
	}

	float DeterministicCreaseNoise(const FVector& P)
	{
		const double A = FMath::Sin(P.X * 0.11 + P.Y * 0.08 + P.Z * 0.05);
		const double B = FMath::Cos(P.Y * 0.14 - P.Z * 0.12 + P.X * 0.04);
		const double Ridge = 1.0 - FMath::Abs(A * B);
		// Monotonic [0.86..1.12] prevents outer painted skin from punching through inner dark wheel arches
		return static_cast<float>(0.86 + Ridge * 0.26);
	}

	FVector SafeNormalizeOrFallback(const FVector& V, const FVector& Fallback)
	{
		const FVector N = V.GetSafeNormal();
		return N.IsNearlyZero() ? Fallback : N;
	}

	/** Recomputes face/crease normals across displaced vertices without flipping back-faces black. */
	void RecomputeSectionNormals(FWSPC2DeformableChassis::FDeformSection& Sec, float WindingSign)
	{
		const int32 NumVerts = Sec.Positions.Num();
		const int32 NumTris = Sec.Triangles.Num() / 3;
		if (NumVerts == 0 || NumTris == 0)
		{
			return;
		}

		TMap<FIntVector, FVector> BucketNormalAccum;
		BucketNormalAccum.Reserve(NumVerts);
		TMap<FIntVector, FVector> BucketSteepFaceNormal;
		BucketSteepFaceNormal.Reserve(NumVerts);

		for (int32 t = 0; t < NumTris; ++t)
		{
			if (Sec.TriangleRemoved.IsValidIndex(t) && Sec.TriangleRemoved[t])
			{
				continue;
			}
			const int32 I0 = Sec.Triangles[t * 3 + 0];
			const int32 I1 = Sec.Triangles[t * 3 + 1];
			const int32 I2 = Sec.Triangles[t * 3 + 2];
			if (!Sec.Positions.IsValidIndex(I0) || !Sec.Positions.IsValidIndex(I1) || !Sec.Positions.IsValidIndex(I2))
			{
				continue;
			}

			const FVector& P0 = Sec.Positions[I0];
			const FVector& P1 = Sec.Positions[I1];
			const FVector& P2 = Sec.Positions[I2];
			const FVector AreaCross = FVector::CrossProduct(P1 - P0, P2 - P0) * WindingSign;
			const float TwiceArea = AreaCross.Size();
			if (TwiceArea <= 1e-4f)
			{
				continue;
			}

			const FVector UnitFaceN = AreaCross / TwiceArea;
			const int32 Idxs[3] = { I0, I1, I2 };
			for (int32 k = 0; k < 3; ++k)
			{
				const int32 VIdx = Idxs[k];
				const FIntVector Bucket = Sec.WeldBuckets[VIdx];
				BucketNormalAccum.FindOrAdd(Bucket) += AreaCross;

				FVector& Steep = BucketSteepFaceNormal.FindOrAdd(Bucket);
				if (Steep.IsNearlyZero() || FVector::DotProduct(UnitFaceN, Sec.RestNormals[VIdx]) < FVector::DotProduct(Steep, Sec.RestNormals[VIdx]))
				{
					Steep = UnitFaceN;
				}
			}
		}

		for (int32 v = 0; v < NumVerts; ++v)
		{
			const float Disp = Sec.CumulativeDispCm[v];
			if (Disp <= 0.25f)
			{
				continue;
			}

			const FVector* Accum = BucketNormalAccum.Find(Sec.WeldBuckets[v]);
			if (!Accum || Accum->IsNearlyZero())
			{
				continue;
			}

			FVector NewNorm = Accum->GetSafeNormal();
			if (Disp > 2.5f)
			{
				if (const FVector* Steep = BucketSteepFaceNormal.Find(Sec.WeldBuckets[v]))
				{
					if (!Steep->IsNearlyZero())
					{
						// Blend toward sharpest adjacent deformed face to emphasize crisp metallic sheet folds
						const float FoldAlpha = FMath::Clamp((Disp - 2.5f) / 14.0f, 0.0f, 0.62f);
						NewNorm = SafeNormalizeOrFallback(FMath::Lerp(NewNorm, *Steep, FoldAlpha), NewNorm);
					}
				}
			}

			// Guard against accidental normal inversion (> 110 deg from rest normal) on extreme pinches
			if (FVector::DotProduct(NewNorm, Sec.RestNormals[v]) < -0.35f)
			{
				NewNorm = SafeNormalizeOrFallback(FMath::Lerp(Sec.RestNormals[v], NewNorm, 0.35f), Sec.RestNormals[v]);
			}

			Sec.Normals[v] = NewNorm;
			const FVector RefUp = (FMath::Abs(NewNorm.Z) < 0.90f) ? FVector::UpVector : FVector::ForwardVector;
			const FVector Tang = SafeNormalizeOrFallback(FVector::CrossProduct(RefUp, NewNorm), FVector::ForwardVector);
			Sec.Tangents[v] = FProcMeshTangent(Tang, false);
		}
	}

	bool IsWSPC2DamageMaterial(const UMaterialInterface* Mat)
	{
		const UMaterial* Base = Mat ? Mat->GetMaterial() : nullptr;
		return Base && Base->GetName().Contains(TEXT("M_WSPC2_VehicleDamage"));
	}

	void AppendSectionToSingleTarget(
		FWSPC2DeformableChassis::FDeformSection& Dst,
		const FWSPC2DeformableChassis::FDeformSection& Src,
		int32 TriIndex,
		const FVector& PivotOffset,
		TMap<int32, int32>& Remap)
	{
		for (int32 Corner = 0; Corner < 3; ++Corner)
		{
			const int32 OldIdx = Src.Triangles[TriIndex * 3 + Corner];
			int32* Found = Remap.Find(OldIdx);
			int32 NewIdx = INDEX_NONE;
			if (Found)
			{
				NewIdx = *Found;
			}
			else
			{
				const FVector Pos = Src.Positions[OldIdx] - PivotOffset;
				const FVector RestPos = Src.RestPositions[OldIdx] - PivotOffset;
				NewIdx = Dst.Positions.Add(Pos);
				Dst.RestPositions.Add(RestPos);
				Dst.Normals.Add(Src.Normals[OldIdx]);
				Dst.RestNormals.Add(Src.RestNormals[OldIdx]);
				Dst.UV0.Add(Src.UV0[OldIdx]);
				if (Src.UV1.IsValidIndex(OldIdx)) Dst.UV1.Add(Src.UV1[OldIdx]);
				if (Src.UV2.IsValidIndex(OldIdx)) Dst.UV2.Add(Src.UV2[OldIdx]);
				if (Src.UV3.IsValidIndex(OldIdx)) Dst.UV3.Add(Src.UV3[OldIdx]);
				Dst.Colors.Add(Src.Colors[OldIdx]);
				Dst.Tangents.Add(Src.Tangents[OldIdx]);
				Dst.CumulativeDispCm.Add(Src.CumulativeDispCm[OldIdx]);
				Dst.WeldBuckets.Add(QuantizeHalfCm(RestPos));
				Dst.LocalBounds += Pos;
				Remap.Add(OldIdx, NewIdx);
			}
			Dst.Triangles.Add(NewIdx);
		}
		Dst.TriangleRemoved.Add(false);
	}

	void AppendBoxGeometry(
		FWSPC2DeformableChassis::FDeformSection& Sec,
		const FVector& Center,
		const FVector& Extent,
		const FLinearColor& Color)
	{
		const FVector Corners[8] = {
			Center + FVector(-Extent.X, -Extent.Y, -Extent.Z),
			Center + FVector(Extent.X, -Extent.Y, -Extent.Z),
			Center + FVector(Extent.X,  Extent.Y, -Extent.Z),
			Center + FVector(-Extent.X,  Extent.Y, -Extent.Z),
			Center + FVector(-Extent.X, -Extent.Y,  Extent.Z),
			Center + FVector(Extent.X, -Extent.Y,  Extent.Z),
			Center + FVector(Extent.X,  Extent.Y,  Extent.Z),
			Center + FVector(-Extent.X,  Extent.Y,  Extent.Z),
		};

		const int32 Faces[6][4] = {
			{4, 5, 6, 7}, // +Z top
			{3, 2, 1, 0}, // -Z bottom
			{1, 2, 6, 5}, // +X front
			{3, 0, 4, 7}, // -X rear
			{2, 3, 7, 6}, // +Y right
			{0, 1, 5, 4}, // -Y left
		};
		const FVector FaceNormals[6] = {
			FVector(0, 0, 1), FVector(0, 0, -1),
			FVector(1, 0, 0), FVector(-1, 0, 0),
			FVector(0, 1, 0), FVector(0, -1, 0),
		};

		for (int32 f = 0; f < 6; ++f)
		{
			const int32 BaseV = Sec.Positions.Num();
			const FVector Tang = SafeNormalizeOrFallback(FVector::CrossProduct(FVector::UpVector, FaceNormals[f]), FVector::ForwardVector);
			const FVector2D UVs[4] = { FVector2D(0, 0), FVector2D(1, 0), FVector2D(1, 1), FVector2D(0, 1) };
			for (int32 c = 0; c < 4; ++c)
			{
				const FVector& P = Corners[Faces[f][c]];
				Sec.Positions.Add(P);
				Sec.RestPositions.Add(P);
				Sec.Normals.Add(FaceNormals[f]);
				Sec.RestNormals.Add(FaceNormals[f]);
				Sec.UV0.Add(UVs[c]);
				Sec.Colors.Add(Color);
				Sec.Tangents.Add(FProcMeshTangent(Tang, false));
				Sec.CumulativeDispCm.Add(0.0f);
				Sec.WeldBuckets.Add(QuantizeHalfCm(P));
				Sec.LocalBounds += P;
			}
			Sec.Triangles.Add(BaseV + 0); Sec.Triangles.Add(BaseV + 1); Sec.Triangles.Add(BaseV + 2);
			Sec.Triangles.Add(BaseV + 0); Sec.Triangles.Add(BaseV + 2); Sec.Triangles.Add(BaseV + 3);
			Sec.TriangleRemoved.Add(false);
			Sec.TriangleRemoved.Add(false);
		}
	}

	void RebuildSectionBox(FWSPC2DeformableChassis::FDeformSection& Sec)
	{
		Sec.LocalBounds.Init();
		for (const FVector& P : Sec.Positions)
		{
			Sec.LocalBounds += P;
		}
	}

	EWSPC2DetachablePanel ClassifyBodyIsland(
		const FBox& IslCarBox,
		const FBox& TotalCarBox,
		int32 IslVerts,
		int32 TotalVerts)
	{
		const FVector TotalSize = TotalCarBox.GetSize().ComponentMax(FVector(100.0f));
		const FVector RelMin = (IslCarBox.Min - TotalCarBox.Min) / TotalSize;
		const FVector RelMax = (IslCarBox.Max - TotalCarBox.Min) / TotalSize;
		const FVector RelCtr = 0.5f * (RelMin + RelMax);
		const FVector RelSpan = RelMax - RelMin;
		const float VertRatio = static_cast<float>(IslVerts) / FMath::Max(1, TotalVerts);

		// Reject monolithic single-piece chassis shells (would tear the entire car off)
		if (VertRatio > 0.32f || (RelSpan.X > 0.72f && RelSpan.Y > 0.65f))
		{
			return EWSPC2DetachablePanel::Count;
		}

		// Ignore tiny rivets/bolts/undercarriage bits during primary pass
		if (IslVerts < 16 || (RelMax.Z < 0.14f))
		{
			return EWSPC2DetachablePanel::Count;
		}

		// Side mirrors (small outboard ears forward of doors)
		if (RelMin.X >= 0.36f && RelMax.X <= 0.76f && RelMin.Z >= 0.40f && RelMax.Z <= 0.90f
			&& RelSpan.X <= 0.18f && IslVerts <= 450)
		{
			if (RelMin.Y <= 0.14f && RelCtr.Y < 0.25f)
			{
				return EWSPC2DetachablePanel::LeftMirror;
			}
			if (RelMax.Y >= 0.86f && RelCtr.Y > 0.75f)
			{
				return EWSPC2DetachablePanel::RightMirror;
			}
		}

		// Roof lightbar / siren assembly
		if (RelMin.Z >= 0.83f && RelMax.Z >= 0.93f && RelSpan.X <= 0.32f && VertRatio < 0.24f)
		{
			return EWSPC2DetachablePanel::RoofLightbar;
		}

		// Front bumper + optional pushbar bullbar
		if ((RelMin.X >= 0.78f && RelMax.Z <= 0.58f && RelSpan.Y >= 0.32f)
			|| (RelMin.X >= 0.90f && RelMax.Z <= 0.68f && RelSpan.Y >= 0.22f))
		{
			return EWSPC2DetachablePanel::FrontBumper;
		}

		// Rear bumper
		if (RelMax.X <= 0.22f && RelMax.Z <= 0.58f && RelSpan.Y >= 0.32f)
		{
			return EWSPC2DetachablePanel::RearBumper;
		}

		// Hood (upper front centered sheet metal; includes Zhabotinsky long hoods starting near uX~0.54)
		if (RelMin.X >= 0.54f && RelMax.X >= 0.80f && RelMin.Z >= 0.22f && RelMax.Z <= 0.76f
			&& RelSpan.Z <= 0.44f && FMath::Abs(RelCtr.Y - 0.5f) <= 0.19f && RelSpan.Y >= 0.28f)
		{
			return EWSPC2DetachablePanel::Hood;
		}

		// Trunk / Decklid
		if (RelMax.X <= 0.44f && RelMin.X <= 0.15f && RelMin.Z >= 0.30f && RelMax.Z <= 0.76f
			&& RelSpan.Z <= 0.40f && FMath::Abs(RelCtr.Y - 0.5f) <= 0.18f && RelSpan.Y >= 0.28f)
		{
			return EWSPC2DetachablePanel::Trunk;
		}

		// Side Doors (outer skin panels in cabin mid-section)
		if (RelMin.X >= 0.22f && RelMax.X <= 0.78f && RelSpan.X <= 0.48f
			&& RelMin.Z >= 0.05f && RelMax.Z <= 0.76f && RelSpan.Y <= 0.28f)
		{
			if (RelMax.Y <= 0.24f && RelCtr.Y < 0.20f)
			{
				return EWSPC2DetachablePanel::LeftDoor;
			}
			if (RelMin.Y >= 0.76f && RelCtr.Y > 0.80f)
			{
				return EWSPC2DetachablePanel::RightDoor;
			}
		}

		return EWSPC2DetachablePanel::Count;
	}

	EWSPC2GlassZone ClassifyGlassIsland(const FBox& IslCarBox, const FBox& RefCarBox)
	{
		const FVector RefSize = RefCarBox.GetSize().ComponentMax(FVector(100.0f));
		const FVector RelMin = (IslCarBox.Min - RefCarBox.Min) / RefSize;
		const FVector RelMax = (IslCarBox.Max - RefCarBox.Min) / RefSize;
		const FVector RelCtr = 0.5f * (RelMin + RelMax);
		const FVector RelSpan = RelMax - RelMin;

		if (RelMin.Z >= 0.80f && RelMax.Z >= 0.90f && RelSpan.X <= 0.35f)
		{
			return EWSPC2GlassZone::Lightbar_Glass;
		}

		// Front headlights / blinkers (Left is -Y -> RelCtr.Y < 0.5, Right is +Y -> RelCtr.Y > 0.5)
		if (RelCtr.X >= 0.72f && RelMax.Z <= 0.66f)
		{
			return (RelCtr.Y < 0.5f) ? EWSPC2GlassZone::Headlight_FL : EWSPC2GlassZone::Headlight_FR;
		}

		// Rear taillights
		if (RelCtr.X <= 0.28f && RelMax.Z <= 0.72f)
		{
			return (RelCtr.Y < 0.5f) ? EWSPC2GlassZone::Taillight_RL : EWSPC2GlassZone::Taillight_RR;
		}

		// Windshield & Rear Window
		if (RelSpan.Y >= 0.34f && RelMax.Z >= 0.64f)
		{
			return (RelCtr.X >= 0.44f) ? EWSPC2GlassZone::Windshield : EWSPC2GlassZone::RearWindow;
		}

		// Side Windows
		if (RelCtr.Y < 0.45f)
		{
			return EWSPC2GlassZone::SideWindow_L;
		}
		if (RelCtr.Y > 0.55f)
		{
			return EWSPC2GlassZone::SideWindow_R;
		}

		return (RelCtr.X >= 0.44f) ? EWSPC2GlassZone::Windshield : EWSPC2GlassZone::RearWindow;
	}
}

AWSPC2DetachedPartActor::AWSPC2DetachedPartActor()
{
	PrimaryActorTick.bCanEverTick = false;

	PartMesh = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("DetachedPartMesh"));
	PartMesh->bUseComplexAsSimpleCollision = false;
	SetRootComponent(PartMesh);
}

void AWSPC2DetachedPartActor::InitFromDeformedGeometry(
	const TArray<FSectionInput>& Sections,
	const FBox& LocalBounds,
	float MassKg,
	const FVector& InheritedVelocity,
	const FVector& ImpulseDir,
	float ImpactSpeedKmh)
{
	if (!PartMesh || Sections.Num() == 0)
	{
		return;
	}

	const FVector BoundsCenter = LocalBounds.IsValid ? LocalBounds.GetCenter() : FVector::ZeroVector;
	FBox CenteredBounds(ForceInit);

	for (int32 s = 0; s < Sections.Num(); ++s)
	{
		const FSectionInput& Src = Sections[s];
		if (Src.Vertices.Num() == 0 || Src.Triangles.Num() < 3)
		{
			continue;
		}

		TArray<FVector> CenteredVerts;
		CenteredVerts.SetNumUninitialized(Src.Vertices.Num());
		for (int32 i = 0; i < Src.Vertices.Num(); ++i)
		{
			CenteredVerts[i] = Src.Vertices[i] - BoundsCenter;
			CenteredBounds += CenteredVerts[i];
		}

		PartMesh->CreateMeshSection_LinearColor(
			s, CenteredVerts, Src.Triangles, Src.Normals, Src.UV0, Src.UV1, Src.UV2, Src.UV3, Src.Colors, Src.Tangents, false, false);
		if (Src.Material)
		{
			PartMesh->SetMaterial(s, Src.Material);
		}
	}

	if (!CenteredBounds.IsValid)
	{
		CenteredBounds = FBox(FVector(-25.0f, -35.0f, -8.0f), FVector(25.0f, 35.0f, 8.0f));
	}

	// Ensure convex box thickness >= 8 cm so Chaos physics never builds a degenerate plane collider
	const FVector MinC = CenteredBounds.Min.ComponentMin(CenteredBounds.GetCenter() - FVector(4.0f));
	const FVector MaxC = CenteredBounds.Max.ComponentMax(CenteredBounds.GetCenter() + FVector(4.0f));
	TArray<FVector> BoxVerts = {
		FVector(MinC.X, MinC.Y, MinC.Z), FVector(MaxC.X, MinC.Y, MinC.Z),
		FVector(MaxC.X, MaxC.Y, MinC.Z), FVector(MinC.X, MaxC.Y, MinC.Z),
		FVector(MinC.X, MinC.Y, MaxC.Z), FVector(MaxC.X, MinC.Y, MaxC.Z),
		FVector(MaxC.X, MaxC.Y, MaxC.Z), FVector(MinC.X, MaxC.Y, MaxC.Z),
	};
	PartMesh->ClearCollisionConvexMeshes();
	PartMesh->AddCollisionConvexMesh(BoxVerts);

	PartMesh->SetCollisionProfileName(TEXT("PhysicsActor"));
	PartMesh->SetCollisionResponseToAllChannels(ECR_Ignore);
	PartMesh->SetCollisionResponseToChannel(ECC_WorldStatic, ECR_Block);
	PartMesh->SetSimulatePhysics(true);
	PartMesh->SetMassOverrideInKg(NAME_None, FMath::Clamp(MassKg, 4.0f, 45.0f), true);

	const FVector SafeDir = ImpulseDir.IsNearlyZero() ? FVector(0.0f, 0.0f, 1.0f) : ImpulseDir.GetSafeNormal();
	const FVector EjectDir = (SafeDir * 0.55f + FVector(FMath::FRandRange(-0.45f, 0.45f), FMath::FRandRange(-0.45f, 0.45f), FMath::FRandRange(0.45f, 0.85f))).GetSafeNormal();
	const float EjectSpeed = FMath::Clamp(ImpactSpeedKmh * 11.5f + 320.0f, 280.0f, 1150.0f);

	PartMesh->SetPhysicsLinearVelocity(InheritedVelocity * 0.60f + EjectDir * EjectSpeed);
	PartMesh->SetPhysicsAngularVelocityInDegrees(FVector(
		FMath::FRandRange(-360.0f, 360.0f),
		FMath::FRandRange(-420.0f, 420.0f),
		FMath::FRandRange(-320.0f, 320.0f)));
	SetLifeSpan(25.0f);
}

FWSPC2DeformableChassis::~FWSPC2DeformableChassis()
{
	ResetAndDestroy(nullptr, nullptr);
}

bool FWSPC2DeformableChassis::BuildFromStaticMeshes(
	AActor* Owner,
	USceneComponent* AttachParent,
	UStaticMeshComponent* BodySMC,
	UStaticMeshComponent* GlassSMC,
	const FBox& EngineBlockBoxCarSpace,
	const TArray<TObjectPtr<UMaterialInstanceDynamic>>& BodyMIDs,
	const TArray<TObjectPtr<UMaterialInstanceDynamic>>& GlassMIDs)
{
	if (!Owner || !AttachParent || !BodySMC)
	{
		return false;
	}

	UStaticMesh* BodyMeshAsset = BodySMC->GetStaticMesh();
	const FStaticMeshRenderData* RenderData = BodyMeshAsset ? BodyMeshAsset->GetRenderData() : nullptr;
	if (!RenderData || RenderData->LODResources.Num() == 0)
	{
		return false;
	}

	// Select highest-detail LOD under the 65k vertex cap for responsive real-time CPU crumpling
	int32 ChosenLod = RenderData->LODResources.Num() - 1;
	for (int32 LodIdx = 0; LodIdx < RenderData->LODResources.Num(); ++LodIdx)
	{
		const int32 VCount = static_cast<int32>(RenderData->LODResources[LodIdx].VertexBuffers.PositionVertexBuffer.GetNumVertices());
		if (VCount > 0 && VCount <= 65000)
		{
			ChosenLod = LodIdx;
			break;
		}
	}

	const FStaticMeshLODResources& BodyLOD = RenderData->LODResources[ChosenLod];
	const int32 TotalBodyVerts = static_cast<int32>(BodyLOD.VertexBuffers.PositionVertexBuffer.GetNumVertices());
	const int32 TotalBodyIndices = BodyLOD.IndexBuffer.GetNumIndices();
	if (TotalBodyVerts <= 0 || TotalBodyIndices < 3)
	{
		UE_LOG(LogWSPC2, Verbose, TEXT("DeformableChassis [%s]: Body mesh %s lacks CPU vertex buffers (verts=%d)"),
			*Owner->GetName(), *GetNameSafe(BodyMeshAsset), TotalBodyVerts);
		return false;
	}

	ResetAndDestroy(nullptr, nullptr);
	OwnerActor = Owner;
	AttachParentComp = AttachParent;
	BodyRelativeTransform = BodySMC->GetRelativeTransform();
	GlassRelativeTransform = GlassSMC ? GlassSMC->GetRelativeTransform() : BodyRelativeTransform;

	for (int32 p = 0; p < static_cast<int32>(EWSPC2DetachablePanel::Count); ++p)
	{
		Panels[p] = FPanelRuntime();
	}
	for (int32 g = 0; g < static_cast<int32>(EWSPC2GlassZone::Count); ++g)
	{
		GlassZoneCentersCarSpace[g] = FVector::ZeroVector;
		GlassZoneHasTris[g] = false;
		GlassZoneShattered[g] = false;
	}

	// 1. Extract raw sections + build unified spatial weld buckets across all materials
	const FIndexArrayView BodyIndexView = BodyLOD.IndexBuffer.GetArrayView();
	const int32 NumTexCoords = static_cast<int32>(BodyLOD.VertexBuffers.StaticMeshVertexBuffer.GetNumTexCoords());
	const bool bHasSrcBodyColors = BodyLOD.VertexBuffers.ColorVertexBuffer.GetNumVertices() == static_cast<uint32>(TotalBodyVerts);

	TArray<FDeformSection> RawSections;
	RawSections.SetNum(BodyLOD.Sections.Num());

	TMap<FIntVector, int32> BucketToWeldId;
	TArray<FIntVector> WeldIdToBucket;
	BodyBoundsCarSpace.Init();

	double WindingVote = 0.0;
	int32 WindingSamples = 0;

	for (int32 s = 0; s < BodyLOD.Sections.Num(); ++s)
	{
		const FStaticMeshSection& SM = BodyLOD.Sections[s];
		FDeformSection& Sec = RawSections[s];

		const int32 MatIdx = SM.MaterialIndex;
		if (BodyMIDs.IsValidIndex(MatIdx) && BodyMIDs[MatIdx])
		{
			Sec.Material = BodyMIDs[MatIdx];
			Sec.bUsesWSPC2DamageMat = WSPC2Deform::IsWSPC2DamageMaterial(Sec.Material);
			if (Sec.bUsesWSPC2DamageMat)
			{
				BodyMIDs[MatIdx]->SetScalarParameterValue(TEXT("UseWPO"), 0.0f);
				BodyMIDs[MatIdx]->SetScalarParameterValue(TEXT("ScratchAmount"), 0.0f);
				BodyMIDs[MatIdx]->SetScalarParameterValue(TEXT("SootAmount"), 0.0f);
			}
		}
		else
		{
			Sec.Material = BodySMC->GetMaterial(MatIdx);
			Sec.bUsesWSPC2DamageMat = WSPC2Deform::IsWSPC2DamageMaterial(Sec.Material);
		}

		const int32 NumTris = static_cast<int32>(SM.NumTriangles);
		TMap<int32, int32> GlobalToLocalVert;
		GlobalToLocalVert.Reserve(NumTris * 2);

		for (int32 t = 0; t < NumTris; ++t)
		{
			const int32 BaseIdx = static_cast<int32>(SM.FirstIndex) + t * 3;
			if (BaseIdx + 2 >= TotalBodyIndices)
			{
				break;
			}

			int32 LocalCorner[3];
			bool bValidTri = true;
			for (int32 c = 0; c < 3; ++c)
			{
				const int32 SrcV = static_cast<int32>(BodyIndexView[BaseIdx + c]);
				if (SrcV < 0 || SrcV >= TotalBodyVerts)
				{
					bValidTri = false;
					break;
				}

				if (int32* Existing = GlobalToLocalVert.Find(SrcV))
				{
					LocalCorner[c] = *Existing;
				}
				else
				{
					const FVector Pos = FVector(BodyLOD.VertexBuffers.PositionVertexBuffer.VertexPosition(SrcV));
					const FVector Norm = WSPC2Deform::SafeNormalizeOrFallback(
						FVector(FVector4(BodyLOD.VertexBuffers.StaticMeshVertexBuffer.VertexTangentZ(SrcV))),
						FVector::UpVector);
					const FVector Tang = WSPC2Deform::SafeNormalizeOrFallback(
						FVector(FVector4(BodyLOD.VertexBuffers.StaticMeshVertexBuffer.VertexTangentX(SrcV))),
						FVector::ForwardVector);
					const FVector2D UV = (NumTexCoords > 0)
						? FVector2D(BodyLOD.VertexBuffers.StaticMeshVertexBuffer.GetVertexUV(SrcV, 0))
						: FVector2D::ZeroVector;

					const int32 NewV = Sec.Positions.Add(Pos);
					Sec.RestPositions.Add(Pos);
					Sec.Normals.Add(Norm);
					Sec.RestNormals.Add(Norm);
					Sec.UV0.Add(UV);
					if (NumTexCoords > 1) Sec.UV1.Add(FVector2D(BodyLOD.VertexBuffers.StaticMeshVertexBuffer.GetVertexUV(SrcV, 1)));
					if (NumTexCoords > 2) Sec.UV2.Add(FVector2D(BodyLOD.VertexBuffers.StaticMeshVertexBuffer.GetVertexUV(SrcV, 2)));
					if (NumTexCoords > 3) Sec.UV3.Add(FVector2D(BodyLOD.VertexBuffers.StaticMeshVertexBuffer.GetVertexUV(SrcV, 3)));

					FLinearColor VertCol = FLinearColor::White;
					if (!Sec.bUsesWSPC2DamageMat && bHasSrcBodyColors)
					{
						const FColor RawC = BodyLOD.VertexBuffers.ColorVertexBuffer.VertexColor(SrcV);
						VertCol = FLinearColor(RawC.R / 255.0f, RawC.G / 255.0f, RawC.B / 255.0f, RawC.A / 255.0f);
					}
					Sec.Colors.Add(VertCol);
					Sec.Tangents.Add(FProcMeshTangent(Tang, false));
					Sec.CumulativeDispCm.Add(0.0f);

					const FIntVector Bucket = WSPC2Deform::QuantizeHalfCm(Pos);
					Sec.WeldBuckets.Add(Bucket);
					if (!BucketToWeldId.Contains(Bucket))
					{
						const int32 WId = WeldIdToBucket.Add(Bucket);
						BucketToWeldId.Add(Bucket, WId);
					}

					const FVector CarPos = BodyRelativeTransform.TransformPosition(Pos);
					BodyBoundsCarSpace += CarPos;
					Sec.LocalBounds += Pos;

					GlobalToLocalVert.Add(SrcV, NewV);
					LocalCorner[c] = NewV;
				}
			}
			if (!bValidTri)
			{
				continue;
			}

			Sec.Triangles.Add(LocalCorner[0]);
			Sec.Triangles.Add(LocalCorner[1]);
			Sec.Triangles.Add(LocalCorner[2]);
			Sec.TriangleRemoved.Add(false);

			if (WindingSamples < 128)
			{
				const FVector Cross = FVector::CrossProduct(
					Sec.RestPositions[LocalCorner[1]] - Sec.RestPositions[LocalCorner[0]],
					Sec.RestPositions[LocalCorner[2]] - Sec.RestPositions[LocalCorner[0]]);
				const FVector AvgNorm = Sec.RestNormals[LocalCorner[0]] + Sec.RestNormals[LocalCorner[1]] + Sec.RestNormals[LocalCorner[2]];
				if (Cross.SizeSquared() > 1e-4f)
				{
					WindingVote += FVector::DotProduct(Cross.GetSafeNormal(), AvgNorm.GetSafeNormal());
					++WindingSamples;
				}
			}
		}
	}

	BodyWindingSign = (WindingVote < 0.0) ? -1.0f : 1.0f;

	// 2. Union-Find connected topological islands across welded spatial buckets
	const int32 NumWelds = WeldIdToBucket.Num();
	if (NumWelds == 0)
	{
		return false;
	}

	WSPC2Deform::FDisjointSet DSU;
	DSU.Init(NumWelds);
	for (const FDeformSection& Sec : RawSections)
	{
		const int32 NumTris = Sec.Triangles.Num() / 3;
		for (int32 t = 0; t < NumTris; ++t)
		{
			const int32 W0 = BucketToWeldId[Sec.WeldBuckets[Sec.Triangles[t * 3 + 0]]];
			const int32 W1 = BucketToWeldId[Sec.WeldBuckets[Sec.Triangles[t * 3 + 1]]];
			const int32 W2 = BucketToWeldId[Sec.WeldBuckets[Sec.Triangles[t * 3 + 2]]];
			DSU.Unite(W0, W1);
			DSU.Unite(W0, W2);
		}
	}

	struct FIslandInfo
	{
		FBox CarBox = FBox(ForceInit);
		int32 VertCount = 0;
		EWSPC2DetachablePanel Panel = EWSPC2DetachablePanel::Count;
	};
	TMap<int32, int32> RootToIslandIdx;
	TArray<FIslandInfo> Islands;
	int32 TotalExtractedVerts = 0;

	for (FDeformSection& Sec : RawSections)
	{
		Sec.VertToIsland.SetNum(Sec.Positions.Num());
		TotalExtractedVerts += Sec.Positions.Num();
		for (int32 v = 0; v < Sec.Positions.Num(); ++v)
		{
			const int32 Root = DSU.Find(BucketToWeldId[Sec.WeldBuckets[v]]);
			int32* FoundIdx = RootToIslandIdx.Find(Root);
			int32 IslIdx = FoundIdx ? *FoundIdx : INDEX_NONE;
			if (IslIdx == INDEX_NONE)
			{
				IslIdx = Islands.AddDefaulted();
				RootToIslandIdx.Add(Root, IslIdx);
			}
			Sec.VertToIsland[v] = IslIdx;
			Islands[IslIdx].CarBox += BodyRelativeTransform.TransformPosition(Sec.RestPositions[v]);
			++Islands[IslIdx].VertCount;
		}
	}

	// Primary island classification + panel bounding accumulation
	FBox PrimaryPanelCarBox[static_cast<int32>(EWSPC2DetachablePanel::Count)];
	bool bPanelHasPrimary[static_cast<int32>(EWSPC2DetachablePanel::Count)] = {};
	for (int32 p = 0; p < static_cast<int32>(EWSPC2DetachablePanel::Count); ++p)
	{
		PrimaryPanelCarBox[p].Init();
	}

	for (int32 i = 0; i < Islands.Num(); ++i)
	{
		FIslandInfo& Isl = Islands[i];
		Isl.Panel = WSPC2Deform::ClassifyBodyIsland(Isl.CarBox, BodyBoundsCarSpace, Isl.VertCount, TotalExtractedVerts);
		if (Isl.Panel != EWSPC2DetachablePanel::Count)
		{
			const int32 PIdx = static_cast<int32>(Isl.Panel);
			PrimaryPanelCarBox[PIdx] += Isl.CarBox;
			bPanelHasPrimary[PIdx] = true;
		}
	}

	// Secondary trim/plate/emblem adoption pass so bolted trim travels cleanly with its parent panel
	const float BodyBottomCutoffZ = BodyBoundsCarSpace.Min.Z + BodyBoundsCarSpace.GetSize().Z * 0.14f;
	for (int32 i = 0; i < Islands.Num(); ++i)
	{
		FIslandInfo& Isl = Islands[i];
		if (Isl.Panel != EWSPC2DetachablePanel::Count || Isl.VertCount > 280 || Isl.CarBox.Max.Z <= BodyBottomCutoffZ)
		{
			continue;
		}
		const FVector IslCtr = Isl.CarBox.GetCenter();
		const float IslVol = Isl.CarBox.GetVolume();
		for (int32 p = 0; p < static_cast<int32>(EWSPC2DetachablePanel::Count); ++p)
		{
			if (!bPanelHasPrimary[p])
			{
				continue;
			}
			const FBox Expanded = PrimaryPanelCarBox[p].ExpandBy(7.0f);
			if (Expanded.IsInside(IslCtr) && IslVol < PrimaryPanelCarBox[p].GetVolume() * 0.75f)
			{
				Isl.Panel = static_cast<EWSPC2DetachablePanel>(p);
				break;
			}
		}
	}

	// 3. Create MainBodyPMC and compute natural hinge pivots for populated Panels[]
	UProceduralMeshComponent* MBComp = NewObject<UProceduralMeshComponent>(Owner, NAME_None);
	MBComp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	MBComp->SetCastShadow(true);
	MBComp->bUseComplexAsSimpleCollision = false;
	MBComp->bReceivesDecals = true;
	MBComp->SetupAttachment(AttachParent);
	MBComp->SetRelativeTransform(BodyRelativeTransform);
	const TArray<float>& BodyCPD = BodySMC->GetCustomPrimitiveData().Data;
	for (int32 i = 0; i < BodyCPD.Num(); ++i)
	{
		MBComp->SetCustomPrimitiveDataFloat(i, BodyCPD[i]);
	}
	MBComp->RegisterComponent();
	MainBodyPMC = MBComp;
	AllCreatedPMCs.Add(MBComp);

	for (int32 p = 0; p < static_cast<int32>(EWSPC2DetachablePanel::Count); ++p)
	{
		if (!bPanelHasPrimary[p])
		{
			continue;
		}
		FBox PCarBox(ForceInit);
		for (const FIslandInfo& Isl : Islands)
		{
			if (Isl.Panel == static_cast<EWSPC2DetachablePanel>(p))
			{
				PCarBox += Isl.CarBox;
			}
		}
		if (!PCarBox.IsValid)
		{
			continue;
		}

		Panels[p].CarSpaceBounds = PCarBox;
		const FVector CarCtr = PCarBox.GetCenter();
		FVector CarPivot = CarCtr;
		FVector CarAxis(0.0f, 1.0f, 0.0f);

		switch (static_cast<EWSPC2DetachablePanel>(p))
		{
		case EWSPC2DetachablePanel::Hood:
			CarPivot = FVector(PCarBox.Min.X, CarCtr.Y, PCarBox.Max.Z);
			CarAxis = FVector(0.0f, 1.0f, 0.0f); // +Pitch tilts front edge UP around rear cowl hinge
			break;
		case EWSPC2DetachablePanel::Trunk:
			CarPivot = FVector(PCarBox.Max.X, CarCtr.Y, PCarBox.Max.Z);
			CarAxis = FVector(0.0f, 1.0f, 0.0f);
			break;
		case EWSPC2DetachablePanel::FrontBumper:
			CarPivot = FVector(PCarBox.Min.X, CarCtr.Y, CarCtr.Z);
			CarAxis = FVector(0.0f, 1.0f, 0.0f);
			break;
		case EWSPC2DetachablePanel::RearBumper:
			CarPivot = FVector(PCarBox.Max.X, CarCtr.Y, CarCtr.Z);
			CarAxis = FVector(0.0f, 1.0f, 0.0f);
			break;
		case EWSPC2DetachablePanel::LeftDoor:
		case EWSPC2DetachablePanel::RightDoor:
			CarPivot = FVector(PCarBox.Max.X, CarCtr.Y, CarCtr.Z);
			CarAxis = FVector(0.0f, 0.0f, 1.0f); // +Yaw swings rear edge out
			break;
		default:
			break;
		}

		Panels[p].HingePivotBodySpace = BodyRelativeTransform.InverseTransformPosition(CarPivot);
		Panels[p].HingeAxis = BodyRelativeTransform.InverseTransformVectorNoScale(CarAxis).GetSafeNormal();
		Panels[p].Sections.SetNum(RawSections.Num());
		for (int32 s = 0; s < RawSections.Num(); ++s)
		{
			Panels[p].Sections[s].Material = RawSections[s].Material;
			Panels[p].Sections[s].bUsesWSPC2DamageMat = RawSections[s].bUsesWSPC2DamageMat;
		}
	}

	MainBodySections.SetNum(RawSections.Num());
	for (int32 s = 0; s < RawSections.Num(); ++s)
	{
		MainBodySections[s].Material = RawSections[s].Material;
		MainBodySections[s].bUsesWSPC2DamageMat = RawSections[s].bUsesWSPC2DamageMat;
	}

	// Route triangles to either MainBodySections or their assigned PanelRuntime
	for (int32 s = 0; s < RawSections.Num(); ++s)
	{
		const FDeformSection& Src = RawSections[s];
		const int32 NumTris = Src.Triangles.Num() / 3;
		TMap<int32, int32> BodyRemap;
		TMap<int32, int32> PanelRemaps[static_cast<int32>(EWSPC2DetachablePanel::Count)];

		for (int32 t = 0; t < NumTris; ++t)
		{
			const int32 V0 = Src.Triangles[t * 3 + 0];
			const int32 IslIdx = Src.VertToIsland[V0];
			const EWSPC2DetachablePanel AssignedPanel = Islands[IslIdx].Panel;

			if (AssignedPanel == EWSPC2DetachablePanel::Count)
			{
				WSPC2Deform::AppendSectionToSingleTarget(MainBodySections[s], Src, t, FVector::ZeroVector, BodyRemap);
			}
			else
			{
				const int32 PIdx = static_cast<int32>(AssignedPanel);
				WSPC2Deform::AppendSectionToSingleTarget(
					Panels[PIdx].Sections[s], Src, t, Panels[PIdx].HingePivotBodySpace, PanelRemaps[PIdx]);
				Panels[PIdx].bHasGeometry = true;
			}
		}
	}

	for (int32 s = 0; s < MainBodySections.Num(); ++s)
	{
		const FDeformSection& Sec = MainBodySections[s];
		if (Sec.Positions.Num() > 0 && Sec.Triangles.Num() >= 3)
		{
			MBComp->CreateMeshSection_LinearColor(
				s, Sec.Positions, Sec.Triangles, Sec.Normals, Sec.UV0, Sec.UV1, Sec.UV2, Sec.UV3, Sec.Colors, Sec.Tangents, false, false);
			if (Sec.Material)
			{
				MBComp->SetMaterial(s, Sec.Material);
			}
		}
	}

	for (int32 p = 0; p < static_cast<int32>(EWSPC2DetachablePanel::Count); ++p)
	{
		if (!Panels[p].bHasGeometry)
		{
			continue;
		}
		UProceduralMeshComponent* PComp = NewObject<UProceduralMeshComponent>(Owner, NAME_None);
		PComp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		PComp->SetCastShadow(true);
		PComp->bUseComplexAsSimpleCollision = false;
		PComp->bReceivesDecals = true;
		PComp->SetupAttachment(MBComp);
		PComp->SetRelativeLocation(Panels[p].HingePivotBodySpace);
		for (int32 i = 0; i < BodyCPD.Num(); ++i)
		{
			PComp->SetCustomPrimitiveDataFloat(i, BodyCPD[i]);
		}
		PComp->RegisterComponent();

		for (int32 s = 0; s < Panels[p].Sections.Num(); ++s)
		{
			const FDeformSection& Sec = Panels[p].Sections[s];
			if (Sec.Positions.Num() > 0 && Sec.Triangles.Num() >= 3)
			{
				PComp->CreateMeshSection_LinearColor(
					s, Sec.Positions, Sec.Triangles, Sec.Normals, Sec.UV0, Sec.UV1, Sec.UV2, Sec.UV3, Sec.Colors, Sec.Tangents, false, false);
				if (Sec.Material)
				{
					PComp->SetMaterial(s, Sec.Material);
				}
			}
		}
		Panels[p].PMC = PComp;
		AllCreatedPMCs.Add(PComp);
	}

	// 4. Extract GlassMesh into GlassPMC with per-corner headlight/taillight/window zones
	UStaticMesh* GlassMeshAsset = GlassSMC ? GlassSMC->GetStaticMesh() : nullptr;
	const FStaticMeshRenderData* GlassRD = GlassMeshAsset ? GlassMeshAsset->GetRenderData() : nullptr;
	if (GlassRD && GlassRD->LODResources.Num() > 0)
	{
		const FStaticMeshLODResources& GlassLOD = GlassRD->LODResources[0];
		const int32 GVerts = static_cast<int32>(GlassLOD.VertexBuffers.PositionVertexBuffer.GetNumVertices());
		const int32 GIndices = GlassLOD.IndexBuffer.GetNumIndices();
		if (GVerts > 0 && GVerts <= 65000 && GIndices >= 3)
		{
			UProceduralMeshComponent* GComp = NewObject<UProceduralMeshComponent>(Owner, NAME_None);
			GComp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			GComp->SetCastShadow(false);
			GComp->bUseComplexAsSimpleCollision = false;
			GComp->bReceivesDecals = false;
			GComp->SetupAttachment(AttachParent);
			GComp->SetRelativeTransform(GlassRelativeTransform);
			if (GlassSMC)
			{
				const TArray<float>& GlassCPD = GlassSMC->GetCustomPrimitiveData().Data;
				for (int32 i = 0; i < GlassCPD.Num(); ++i)
				{
					GComp->SetCustomPrimitiveDataFloat(i, GlassCPD[i]);
				}
			}
			GComp->RegisterComponent();
			GlassPMC = GComp;
			AllCreatedPMCs.Add(GComp);

			const FIndexArrayView GIndexView = GlassLOD.IndexBuffer.GetArrayView();
			const int32 GNumUV = static_cast<int32>(GlassLOD.VertexBuffers.StaticMeshVertexBuffer.GetNumTexCoords());
			const bool bHasSrcGlassColors = GlassLOD.VertexBuffers.ColorVertexBuffer.GetNumVertices() == static_cast<uint32>(GVerts);
			GlassSections.SetNum(GlassLOD.Sections.Num());

			TMap<FIntVector, int32> GBucketToWeld;
			TArray<FIntVector> GWeldToBucket;

			for (int32 s = 0; s < GlassLOD.Sections.Num(); ++s)
			{
				const FStaticMeshSection& GSM = GlassLOD.Sections[s];
				FDeformSection& GSec = GlassSections[s];
				const int32 MatIdx = GSM.MaterialIndex;
				GSec.Material = (GlassMIDs.IsValidIndex(MatIdx) && GlassMIDs[MatIdx]) ? Cast<UMaterialInterface>(GlassMIDs[MatIdx]) : GlassSMC->GetMaterial(MatIdx);
				GSec.bUsesWSPC2DamageMat = WSPC2Deform::IsWSPC2DamageMaterial(GSec.Material);

				TMap<int32, int32> GRemap;
				for (uint32 t = 0; t < GSM.NumTriangles; ++t)
				{
					const int32 BaseIdx = static_cast<int32>(GSM.FirstIndex) + static_cast<int32>(t) * 3;
					if (BaseIdx + 2 >= GIndices)
					{
						break;
					}
					int32 Corner[3];
					bool bOk = true;
					for (int32 c = 0; c < 3; ++c)
					{
						const int32 SrcV = static_cast<int32>(GIndexView[BaseIdx + c]);
						if (SrcV < 0 || SrcV >= GVerts) { bOk = false; break; }
						if (int32* Found = GRemap.Find(SrcV))
						{
							Corner[c] = *Found;
						}
						else
						{
							const FVector Pos = FVector(GlassLOD.VertexBuffers.PositionVertexBuffer.VertexPosition(SrcV));
							const FVector Norm = WSPC2Deform::SafeNormalizeOrFallback(
								FVector(FVector4(GlassLOD.VertexBuffers.StaticMeshVertexBuffer.VertexTangentZ(SrcV))), FVector::UpVector);
							const FVector Tang = WSPC2Deform::SafeNormalizeOrFallback(
								FVector(FVector4(GlassLOD.VertexBuffers.StaticMeshVertexBuffer.VertexTangentX(SrcV))), FVector::ForwardVector);
							const FVector2D UV = (GNumUV > 0) ? FVector2D(GlassLOD.VertexBuffers.StaticMeshVertexBuffer.GetVertexUV(SrcV, 0)) : FVector2D::ZeroVector;

							const int32 NV = GSec.Positions.Add(Pos);
							GSec.RestPositions.Add(Pos);
							GSec.Normals.Add(Norm);
							GSec.RestNormals.Add(Norm);
							GSec.UV0.Add(UV);
							if (GNumUV > 1) GSec.UV1.Add(FVector2D(GlassLOD.VertexBuffers.StaticMeshVertexBuffer.GetVertexUV(SrcV, 1)));
							if (GNumUV > 2) GSec.UV2.Add(FVector2D(GlassLOD.VertexBuffers.StaticMeshVertexBuffer.GetVertexUV(SrcV, 2)));
							if (GNumUV > 3) GSec.UV3.Add(FVector2D(GlassLOD.VertexBuffers.StaticMeshVertexBuffer.GetVertexUV(SrcV, 3)));

							FLinearColor GCol = FLinearColor::White;
							if (!GSec.bUsesWSPC2DamageMat && bHasSrcGlassColors)
							{
								const FColor RawGC = GlassLOD.VertexBuffers.ColorVertexBuffer.VertexColor(SrcV);
								GCol = FLinearColor(RawGC.R / 255.0f, RawGC.G / 255.0f, RawGC.B / 255.0f, RawGC.A / 255.0f);
							}
							GSec.Colors.Add(GCol);
							GSec.Tangents.Add(FProcMeshTangent(Tang, false));
							GSec.CumulativeDispCm.Add(0.0f);
							const FIntVector Bucket = WSPC2Deform::QuantizeHalfCm(Pos);
							GSec.WeldBuckets.Add(Bucket);
							if (!GBucketToWeld.Contains(Bucket))
							{
								const int32 WId = GWeldToBucket.Add(Bucket);
								GBucketToWeld.Add(Bucket, WId);
							}
							GSec.LocalBounds += Pos;
							GRemap.Add(SrcV, NV);
							Corner[c] = NV;
						}
					}
					if (!bOk) continue;
					GSec.Triangles.Add(Corner[0]);
					GSec.Triangles.Add(Corner[1]);
					GSec.Triangles.Add(Corner[2]);
					GSec.TriangleRemoved.Add(false);
				}
			}

			// Union-Find connected glass windows/headlights/taillights
			WSPC2Deform::FDisjointSet GDSU;
			GDSU.Init(GWeldToBucket.Num());
			for (const FDeformSection& GSec : GlassSections)
			{
				const int32 NTris = GSec.Triangles.Num() / 3;
				for (int32 t = 0; t < NTris; ++t)
				{
					const int32 W0 = GBucketToWeld[GSec.WeldBuckets[GSec.Triangles[t * 3 + 0]]];
					const int32 W1 = GBucketToWeld[GSec.WeldBuckets[GSec.Triangles[t * 3 + 1]]];
					const int32 W2 = GBucketToWeld[GSec.WeldBuckets[GSec.Triangles[t * 3 + 2]]];
					GDSU.Unite(W0, W1);
					GDSU.Unite(W0, W2);
				}
			}

			TMap<int32, int32> GRootToIsl;
			TArray<FBox> GIslandCarBoxes;
			for (FDeformSection& GSec : GlassSections)
			{
				GSec.VertToIsland.SetNum(GSec.Positions.Num());
				for (int32 v = 0; v < GSec.Positions.Num(); ++v)
				{
					const int32 Root = GDSU.Find(GBucketToWeld[GSec.WeldBuckets[v]]);
					int32* Found = GRootToIsl.Find(Root);
					int32 Isl = Found ? *Found : INDEX_NONE;
					if (Isl == INDEX_NONE)
					{
						Isl = GIslandCarBoxes.Add(FBox(ForceInit));
						GRootToIsl.Add(Root, Isl);
					}
					GSec.VertToIsland[v] = Isl;
					GIslandCarBoxes[Isl] += GlassRelativeTransform.TransformPosition(GSec.RestPositions[v]);
				}
			}

			TArray<uint8> GIslandZone;
			GIslandZone.SetNum(GIslandCarBoxes.Num());
			FBox ZoneBoxes[static_cast<int32>(EWSPC2GlassZone::Count)];
			for (int32 z = 0; z < static_cast<int32>(EWSPC2GlassZone::Count); ++z)
			{
				ZoneBoxes[z].Init();
			}
			for (int32 i = 0; i < GIslandCarBoxes.Num(); ++i)
			{
				const EWSPC2GlassZone Zone = WSPC2Deform::ClassifyGlassIsland(GIslandCarBoxes[i], BodyBoundsCarSpace);
				GIslandZone[i] = static_cast<uint8>(Zone);
				const int32 ZIdx = static_cast<int32>(Zone);
				ZoneBoxes[ZIdx] += GIslandCarBoxes[i];
				GlassZoneHasTris[ZIdx] = true;
			}
			for (int32 z = 0; z < static_cast<int32>(EWSPC2GlassZone::Count); ++z)
			{
				if (ZoneBoxes[z].IsValid)
				{
					GlassZoneCentersCarSpace[z] = ZoneBoxes[z].GetCenter();
				}
			}

			for (int32 s = 0; s < GlassSections.Num(); ++s)
			{
				FDeformSection& GSec = GlassSections[s];
				GSec.IslandZones = GIslandZone;
				if (GSec.Positions.Num() > 0 && GSec.Triangles.Num() >= 3)
				{
					GComp->CreateMeshSection_LinearColor(
						s, GSec.Positions, GSec.Triangles, GSec.Normals, GSec.UV0, GSec.UV1, GSec.UV2, GSec.UV3, GSec.Colors, GSec.Tangents, false, false);
					if (GSec.Material)
					{
						GComp->SetMaterial(s, GSec.Material);
					}
				}
			}
		}
	}

	// Fallback zone centers when a vehicle lacks a dedicated glass mesh corner
	const FVector BodyCtr = BodyBoundsCarSpace.GetCenter();
	const FVector BodyHalf = BodyBoundsCarSpace.GetExtent();
	if (!GlassZoneHasTris[0]) GlassZoneCentersCarSpace[0] = BodyCtr + FVector(BodyHalf.X * 0.90f, -BodyHalf.Y * 0.72f, 0.0f);
	if (!GlassZoneHasTris[1]) GlassZoneCentersCarSpace[1] = BodyCtr + FVector(BodyHalf.X * 0.90f,  BodyHalf.Y * 0.72f, 0.0f);
	if (!GlassZoneHasTris[2]) GlassZoneCentersCarSpace[2] = BodyCtr + FVector(-BodyHalf.X * 0.90f, -BodyHalf.Y * 0.72f, 4.0f);
	if (!GlassZoneHasTris[3]) GlassZoneCentersCarSpace[3] = BodyCtr + FVector(-BodyHalf.X * 0.90f,  BodyHalf.Y * 0.72f, 4.0f);

	// 5. Internal engine block + radiator + frame rails (revealed when hood/bumper pop off)
	CreateInternalEngineCore(Owner, AttachParent, EngineBlockBoxCarSpace);

	// Swap visibility cleanly from rigid static meshes to procedural deformable chassis
	BodySMC->SetVisibility(false);
	BodySMC->SetHiddenInGame(true);
	if (GlassSMC)
	{
		GlassSMC->SetVisibility(false);
		GlassSMC->SetHiddenInGame(true);
	}

	bInitialized = true;
	UE_LOG(LogWSPC2, Log,
		TEXT("DeformableChassis [%s]: ACTIVE (LOD=%d verts=%d, FrontBumper=%d Hood=%d RearBumper=%d Trunk=%d Doors=%d/%d Lightbar=%d)"),
		*Owner->GetName(), ChosenLod, TotalExtractedVerts,
		HasPanelGeometry(EWSPC2DetachablePanel::FrontBumper) ? 1 : 0,
		HasPanelGeometry(EWSPC2DetachablePanel::Hood) ? 1 : 0,
		HasPanelGeometry(EWSPC2DetachablePanel::RearBumper) ? 1 : 0,
		HasPanelGeometry(EWSPC2DetachablePanel::Trunk) ? 1 : 0,
		HasPanelGeometry(EWSPC2DetachablePanel::LeftDoor) ? 1 : 0,
		HasPanelGeometry(EWSPC2DetachablePanel::RightDoor) ? 1 : 0,
		HasPanelGeometry(EWSPC2DetachablePanel::RoofLightbar) ? 1 : 0);

	return true;
}

void FWSPC2DeformableChassis::CreateInternalEngineCore(AActor* Owner, USceneComponent* AttachParent, const FBox& EngineBlockBoxCarSpace)
{
	if (!Owner || !AttachParent || !EngineBlockBoxCarSpace.IsValid)
	{
		return;
	}

	UProceduralMeshComponent* CorePMC = NewObject<UProceduralMeshComponent>(Owner, NAME_None);
	CorePMC->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	CorePMC->SetCastShadow(true);
	CorePMC->bUseComplexAsSimpleCollision = false;
	CorePMC->bReceivesDecals = false;
	CorePMC->SetupAttachment(AttachParent);
	CorePMC->SetVisibility(false);
	CorePMC->SetHiddenInGame(true);
	CorePMC->RegisterComponent();

	FDeformSection Sec;
	const FVector OrigCtr = EngineBlockBoxCarSpace.GetCenter();
	const FVector OrigExt = EngineBlockBoxCarSpace.GetExtent().ComponentMax(FVector(22.0f, 20.0f, 16.0f));
	const FVector BodyCtr = BodyBoundsCarSpace.GetCenter();
	const FVector BodyHalf = BodyBoundsCarSpace.GetExtent();

	// Keep internal engine bay & radiator recessed >= 30 cm behind nose tip so extreme crushes never poke out front
	const bool bFrontEngine = OrigCtr.X >= BodyCtr.X;
	const float SafeFrontX = bFrontEngine
		? FMath::Min(EngineBlockBoxCarSpace.Max.X - 18.0f, BodyBoundsCarSpace.Max.X - 30.0f)
		: (OrigCtr.X + OrigExt.X * 0.55f);
	const FVector SafeExt(OrigExt.X * 0.58f, OrigExt.Y * 0.52f, OrigExt.Z * 0.58f);
	const FVector SafeCtr(bFrontEngine ? FMath::Min(OrigCtr.X - 8.0f, SafeFrontX - SafeExt.X - 4.0f) : OrigCtr.X, OrigCtr.Y, OrigCtr.Z - 2.0f);

	// Use pure White vertex colors on CorePMC so M_WSPC2_VehicleDamage doesn't turn metal_mask silver-blue under roof strobes
	const FLinearColor NeutralVC = FLinearColor::White;
	// Main cast-iron engine block + twin valve covers + intake plenum
	WSPC2Deform::AppendBoxGeometry(Sec, SafeCtr, SafeExt, NeutralVC);
	WSPC2Deform::AppendBoxGeometry(Sec, SafeCtr + FVector(0.0f, -SafeExt.Y * 0.45f, SafeExt.Z * 0.65f), FVector(SafeExt.X * 0.72f, SafeExt.Y * 0.28f, SafeExt.Z * 0.22f), NeutralVC);
	WSPC2Deform::AppendBoxGeometry(Sec, SafeCtr + FVector(0.0f,  SafeExt.Y * 0.45f, SafeExt.Z * 0.65f), FVector(SafeExt.X * 0.72f, SafeExt.Y * 0.28f, SafeExt.Z * 0.22f), NeutralVC);
	WSPC2Deform::AppendBoxGeometry(Sec, SafeCtr + FVector(0.0f, 0.0f, SafeExt.Z * 0.86f), FVector(SafeExt.X * 0.52f, SafeExt.Y * 0.30f, 5.0f), NeutralVC);

	if (bFrontEngine)
	{
		// Recessed radiator core + deep frame rails tucked well inside the crushed front apron
		const float RadX = FMath::Min(SafeFrontX - 4.0f, BodyBoundsCarSpace.Max.X - 34.0f);
		WSPC2Deform::AppendBoxGeometry(Sec, FVector(RadX, SafeCtr.Y, SafeCtr.Z), FVector(3.5f, SafeExt.Y * 1.15f, SafeExt.Z * 0.85f), NeutralVC);
		const float RailCtrX = BodyBoundsCarSpace.Max.X - 46.0f;
		const float RailZ = BodyBoundsCarSpace.Min.Z + 28.0f;
		WSPC2Deform::AppendBoxGeometry(Sec, FVector(RailCtrX, -34.0f, RailZ), FVector(20.0f, 4.5f, 4.5f), NeutralVC);
		WSPC2Deform::AppendBoxGeometry(Sec, FVector(RailCtrX,  34.0f, RailZ), FVector(20.0f, 4.5f, 4.5f), NeutralVC);
	}

	CorePMC->CreateMeshSection_LinearColor(
		0, Sec.Positions, Sec.Triangles, Sec.Normals, Sec.UV0, Sec.Colors, Sec.Tangents, false, false);
	if (UMaterialInterface* DmgMaster = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Vehicles/Imported/Materials/M_WSPC2_VehicleDamage.M_WSPC2_VehicleDamage"), nullptr, LOAD_NoWarn | LOAD_Quiet))
	{
		UMaterialInstanceDynamic* CoreMID = UMaterialInstanceDynamic::Create(DmgMaster, CorePMC);
		CoreMID->SetVectorParameterValue(TEXT("BaseColorFactor"), FLinearColor(0.045f, 0.045f, 0.050f, 1.0f));
		CoreMID->SetScalarParameterValue(TEXT("MetallicFactor"), 0.28f);
		CoreMID->SetScalarParameterValue(TEXT("RoughnessFactor"), 0.84f);
		CoreMID->SetScalarParameterValue(TEXT("UseBaseColorTex"), 0.0f);
		CoreMID->SetScalarParameterValue(TEXT("UseMRTex"), 0.0f);
		CoreMID->SetScalarParameterValue(TEXT("UseNormalTex"), 0.0f);
		CoreMID->SetScalarParameterValue(TEXT("UseWPO"), 0.0f);
		CoreMID->SetScalarParameterValue(TEXT("ScratchAmount"), 0.0f);
		CoreMID->SetScalarParameterValue(TEXT("SootAmount"), 0.0f);
		CorePMC->SetMaterial(0, CoreMID);
	}
	else if (MainBodySections.Num() > 0 && MainBodySections[0].Material)
	{
		CorePMC->SetMaterial(0, MainBodySections[0].Material);
	}

	EngineCorePMC = CorePMC;
	bInternalCoreVisible = false;
	AllCreatedPMCs.Add(CorePMC);
}

void FWSPC2DeformableChassis::UpdateInternalCoreVisibility()
{
	const bool bShouldShow =
		GetPanelState(EWSPC2DetachablePanel::Hood) != EWSPC2PanelDamageState::Intact ||
		GetPanelState(EWSPC2DetachablePanel::FrontBumper) == EWSPC2PanelDamageState::Detached;

	if (bShouldShow == bInternalCoreVisible)
	{
		return;
	}
	bInternalCoreVisible = bShouldShow;

	if (UProceduralMeshComponent* Core = EngineCorePMC.Get())
	{
		Core->SetVisibility(bShouldShow);
		Core->SetHiddenInGame(!bShouldShow);
	}
}

void FWSPC2DeformableChassis::ApplyPlasticImpact(
	const FWSPC2MeshImpactRecord& Impact,
	const FVector& ChassisTwistDeg,
	float FloorTouchTwistDeg)
{
	if (!bInitialized)
	{
		return;
	}

	const FVector CarHit = Impact.LocalPos;
	const FVector CarInward = WSPC2Deform::SafeNormalizeOrFallback(Impact.InwardDir, -CarHit.GetSafeNormal());
	const FVector BodySize = BodyBoundsCarSpace.GetSize().ComponentMax(FVector(120.0f));
	const FVector BodyMin = BodyBoundsCarSpace.Min;

	// Axial barrier slams widen lateral crush across bumper/grille/fenders instead of poking one narrow corner
	const float AxialX = FMath::Abs(CarInward.X);
	const float RadiusX = Impact.RadiusCm * (AxialX > 0.58f ? 1.25f : 1.0f);
	const float RadiusY = Impact.RadiusCm * (AxialX > 0.58f ? 1.75f : 1.0f);
	const float RadiusZ = Impact.RadiusCm * 1.15f;

	// Tight contact zone for paint chipping/scratches so folding metal further back stays painted
	const float PaintRadX = FMath::Clamp(Impact.RadiusCm * 0.36f, 18.0f, 42.0f);
	const float PaintRadY = FMath::Clamp(Impact.RadiusCm * (AxialX > 0.58f ? 0.72f : 0.40f), 22.0f, 68.0f);
	const float PaintRadZ = FMath::Clamp(Impact.RadiusCm * 0.38f, 18.0f, 42.0f);

	const FVector MeshHit = BodyRelativeTransform.InverseTransformPosition(CarHit);
	const FBox CarImpactBounds(CarHit - FVector(RadiusX, RadiusY, RadiusZ), CarHit + FVector(RadiusX, RadiusY, RadiusZ));
	const float TwistNorm = FMath::Clamp(FMath::Max3(FMath::Abs(ChassisTwistDeg.X), FMath::Abs(ChassisTwistDeg.Y), FMath::Abs(ChassisTwistDeg.Z)) / FMath::Max(FloorTouchTwistDeg, 1.0f), 0.0f, 1.35f);
	const bool bFrontBuckleTrigger = (CarHit.X - BodyMin.X) / BodySize.X > 0.65f && CarInward.X < -0.40f && Impact.Severity >= 0.35f;

	auto DeformSectionList = [&](TArray<FDeformSection>& Sections, const FVector& PivotBodySpace, const FTransform& MeshToCarXf, float StiffnessScale)
	{
		for (int32 s = 0; s < Sections.Num(); ++s)
		{
			FDeformSection& Sec = Sections[s];
			if (Sec.Positions.Num() == 0)
			{
				continue;
			}

			// Broad-phase check in Car Space
			const FBox SecCarBox = Sec.LocalBounds.ShiftBy(PivotBodySpace).TransformBy(MeshToCarXf);
			const bool bInImpact = SecCarBox.Intersect(CarImpactBounds);
			const bool bNeedGlobalBuckle = bFrontBuckleTrigger || TwistNorm > 0.15f;
			if (!bInImpact && !bNeedGlobalBuckle)
			{
				continue;
			}

			bool bChanged = false;
			TMap<FIntVector, FVector> BucketDeltaCache;

			for (int32 v = 0; v < Sec.Positions.Num(); ++v)
			{
				const FVector RestBody = Sec.RestPositions[v] + PivotBodySpace;
				const FVector RestCar = MeshToCarXf.TransformPosition(RestBody);
				const FVector u = (RestCar - BodyMin) / BodySize;

				// Compute displacement by quantized 0.5 cm bucket so UV seams NEVER open into holes
				const FIntVector& Bucket = Sec.WeldBuckets[v];
				FVector TotalDeltaCar = FVector::ZeroVector;
				if (const FVector* Cached = BucketDeltaCache.Find(Bucket))
				{
					TotalDeltaCar = *Cached;
				}
				else
				{
					// Localized 3D ellipsoid plastic crush
					const FVector Rel = RestCar - CarHit;
					const float EllipsoidNorm = FMath::Sqrt(
						FMath::Square(Rel.X / FMath::Max(RadiusX, 1.0f)) +
						FMath::Square(Rel.Y / FMath::Max(RadiusY, 1.0f)) +
						FMath::Square(Rel.Z / FMath::Max(RadiusZ, 1.0f)));

					if (EllipsoidNorm < 1.0f)
					{
						const float SmoothFalloff = FMath::Pow(1.0f - EllipsoidNorm, 1.65f);
						const float CreaseNoise = WSPC2Deform::DeterministicCreaseNoise(RestCar);

						// Stiffer roof/A-pillars, softer front/rear crumple aprons
						float ZoneStiff = StiffnessScale;
						if (u.Z > 0.68f) ZoneStiff *= 0.72f;
						else if (u.X > 0.24f && u.X < 0.74f) ZoneStiff *= 0.85f;

						FVector LocalDelta = CarInward * (Impact.DepthCm * SmoothFalloff * CreaseNoise * ZoneStiff);

						// Accordion upward V-fold buckling along front hood/fenders when nose slams barrier
						if (bFrontBuckleTrigger && u.X >= 0.62f && u.X <= 0.90f && u.Z >= 0.34f && u.Z <= 0.72f)
						{
							const float FoldT = FMath::Sin(((u.X - 0.62f) / 0.28f) * UE_PI);
							const float BuckleZ = FoldT * FMath::Clamp(Impact.Severity * 17.5f, 4.0f, 23.0f) * (0.65f + 0.35f * (1.0f - FMath::Abs(u.Y - 0.5f) * 2.0f));
							LocalDelta.Z += BuckleZ * (0.75f + 0.25f * CreaseNoise);
						}

						TotalDeltaCar += LocalDelta;
					}

					// Safety cage guard so extreme crashes don't impale through the driver/gunner seats
					const bool bInsideSafetyCabin = (u.X >= 0.34f && u.X <= 0.66f && FMath::Abs(u.Y - 0.5f) <= 0.26f && u.Z >= 0.34f && u.Z <= 0.78f);
					if (bInsideSafetyCabin)
					{
						TotalDeltaCar *= 0.38f;
					}

					BucketDeltaCache.Add(Bucket, TotalDeltaCar);
				}

				const bool bHasPosDelta = !TotalDeltaCar.IsNearlyZero(0.05f);
				if (bHasPosDelta)
				{
					const FVector DeltaMesh = MeshToCarXf.InverseTransformVectorNoScale(TotalDeltaCar);
					Sec.Positions[v] += DeltaMesh;

					// Clamp maximum vertex excursion relative to rest pose to prevent inside-out explosion
					const FVector TotalFromRest = Sec.Positions[v] - Sec.RestPositions[v];
					const float DistFromRest = TotalFromRest.Size();
					if (DistFromRest > 54.0f)
					{
						Sec.Positions[v] = Sec.RestPositions[v] + TotalFromRest * (54.0f / DistFromRest);
					}

					const float DispCm = (Sec.Positions[v] - Sec.RestPositions[v]).Size();
					Sec.CumulativeDispCm[v] = DispCm;
					MaxVertexDisplacementCm = FMath::Max(MaxVertexDisplacementCm, DispCm);
					Sec.LocalBounds += Sec.Positions[v];
					bChanged = true;
				}

				// Localized contact paint scratches/primer/steel/soot strictly within contact patch on M_WSPC2_VehicleDamage
				if (Sec.bUsesWSPC2DamageMat)
				{
					const FVector ContactRel = RestCar - CarHit;
					const float ContactNorm = FMath::Sqrt(
						FMath::Square(ContactRel.X / FMath::Max(PaintRadX, 1.0f)) +
						FMath::Square(ContactRel.Y / FMath::Max(PaintRadY, 1.0f)) +
						FMath::Square(ContactRel.Z / FMath::Max(PaintRadZ, 1.0f)));
					if (ContactNorm < 1.0f)
					{
						const float ContactFalloff = FMath::Pow(1.0f - ContactNorm, 1.85f);
						const float ContactIntensity = ContactFalloff * FMath::Clamp(Impact.Severity * 1.15f, 0.22f, 1.0f);
						const float TargetR = 1.0f - FMath::Clamp(ContactIntensity * 0.90f, 0.0f, 0.92f);
						const float TargetG = 1.0f - FMath::Clamp(ContactIntensity * 1.05f, 0.0f, 0.95f);
						const float TargetB = 1.0f - FMath::Clamp(FMath::Max(0.0f, ContactIntensity - 0.42f) * 1.05f, 0.0f, 0.65f);
						if (TargetR < Sec.Colors[v].R || TargetG < Sec.Colors[v].G || TargetB < Sec.Colors[v].B)
						{
							Sec.Colors[v].R = FMath::Min(Sec.Colors[v].R, TargetR);
							Sec.Colors[v].G = FMath::Min(Sec.Colors[v].G, TargetG);
							Sec.Colors[v].B = FMath::Min(Sec.Colors[v].B, TargetB);
							bChanged = true;
						}
					}
				}
			}

			if (bChanged)
			{
				WSPC2Deform::RebuildSectionBox(Sec);
				WSPC2Deform::RecomputeSectionNormals(Sec, BodyWindingSign);
				Sec.bDirty = true;
			}
		}
	};

	DeformSectionList(MainBodySections, FVector::ZeroVector, BodyRelativeTransform, 1.0f);

	for (int32 p = 0; p < static_cast<int32>(EWSPC2DetachablePanel::Count); ++p)
	{
		if (Panels[p].bHasGeometry && Panels[p].State != EWSPC2PanelDamageState::Detached)
		{
			const float PanelStiff = (p == static_cast<int32>(EWSPC2DetachablePanel::FrontBumper) || p == static_cast<int32>(EWSPC2DetachablePanel::RearBumper)) ? 1.12f : 1.0f;
			DeformSectionList(Panels[p].Sections, Panels[p].HingePivotBodySpace, BodyRelativeTransform, PanelStiff);
		}
	}

	if (GlassPMC.IsValid())
	{
		DeformSectionList(GlassSections, FVector::ZeroVector, GlassRelativeTransform, 0.65f);
	}

	PushDirtySections();
}

void FWSPC2DeformableChassis::PushDirtySections()
{
	if (UProceduralMeshComponent* MB = MainBodyPMC.Get())
	{
		for (int32 s = 0; s < MainBodySections.Num(); ++s)
		{
			FDeformSection& Sec = MainBodySections[s];
			if (Sec.bDirty && Sec.Positions.Num() > 0)
			{
				MB->UpdateMeshSection_LinearColor(s, Sec.Positions, Sec.Normals, Sec.UV0, Sec.UV1, Sec.UV2, Sec.UV3, Sec.Colors, Sec.Tangents, false);
				Sec.bDirty = false;
			}
		}
	}

	for (int32 p = 0; p < static_cast<int32>(EWSPC2DetachablePanel::Count); ++p)
	{
		UProceduralMeshComponent* PComp = Panels[p].PMC.Get();
		if (PComp && Panels[p].State != EWSPC2PanelDamageState::Detached)
		{
			for (int32 s = 0; s < Panels[p].Sections.Num(); ++s)
			{
				FDeformSection& Sec = Panels[p].Sections[s];
				if (Sec.bDirty && Sec.Positions.Num() > 0)
				{
					PComp->UpdateMeshSection_LinearColor(s, Sec.Positions, Sec.Normals, Sec.UV0, Sec.UV1, Sec.UV2, Sec.UV3, Sec.Colors, Sec.Tangents, false);
					Sec.bDirty = false;
				}
			}
		}
	}

	if (UProceduralMeshComponent* GComp = GlassPMC.Get())
	{
		for (int32 s = 0; s < GlassSections.Num(); ++s)
		{
			FDeformSection& Sec = GlassSections[s];
			if (Sec.bDirty && !Sec.bSectionCleared && Sec.Positions.Num() > 0)
			{
				GComp->UpdateMeshSection_LinearColor(s, Sec.Positions, Sec.Normals, Sec.UV0, Sec.UV1, Sec.UV2, Sec.UV3, Sec.Colors, Sec.Tangents, false);
				Sec.bDirty = false;
			}
			else
			{
				Sec.bDirty = false;
			}
		}
	}
}

void FWSPC2DeformableChassis::SetPanelState(
	EWSPC2DetachablePanel Panel,
	EWSPC2PanelDamageState NewState,
	const FVector& ImpulseDirWorld,
	float SpeedKmh)
{
	if (!bInitialized)
	{
		return;
	}

	const int32 PIdx = static_cast<int32>(Panel);
	if (PIdx < 0 || PIdx >= static_cast<int32>(EWSPC2DetachablePanel::Count))
	{
		return;
	}

	FPanelRuntime& PR = Panels[PIdx];
	UProceduralMeshComponent* PComp = PR.PMC.Get();
	if (!PR.bHasGeometry || !PComp || PR.State >= NewState)
	{
		return;
	}

	PR.State = NewState;

	if (NewState == EWSPC2PanelDamageState::Loose)
	{
		PR.LooseSideSign = FMath::RandBool() ? 1.0f : -1.0f;
		PR.FlutterPhase = FMath::FRandRange(0.0f, 6.28f);
		switch (Panel)
		{
		case EWSPC2DetachablePanel::Hood:
			PR.BaseLooseAngleDeg = FMath::FRandRange(12.0f, 22.0f);
			break;
		case EWSPC2DetachablePanel::Trunk:
			PR.BaseLooseAngleDeg = -FMath::FRandRange(14.0f, 24.0f);
			break;
		case EWSPC2DetachablePanel::FrontBumper:
		case EWSPC2DetachablePanel::RearBumper:
			PR.BaseLooseAngleDeg = FMath::FRandRange(9.0f, 16.0f);
			break;
		case EWSPC2DetachablePanel::LeftDoor:
			PR.BaseLooseAngleDeg = FMath::FRandRange(10.0f, 22.0f);
			break;
		case EWSPC2DetachablePanel::RightDoor:
			PR.BaseLooseAngleDeg = -FMath::FRandRange(10.0f, 22.0f);
			break;
		default:
			PR.BaseLooseAngleDeg = FMath::FRandRange(8.0f, 15.0f);
			break;
		}
		TickLoosePanels(0.016f, SpeedKmh);
		UpdateInternalCoreVisibility();
		UE_LOG(LogWSPC2, Log, TEXT("DeformableChassis [%s]: Panel %d -> LOOSE"), *GetNameSafe(OwnerActor.Get()), PIdx);
		return;
	}

	if (NewState == EWSPC2PanelDamageState::Detached)
	{
		AActor* Owner = OwnerActor.Get();
		UWorld* World = Owner ? Owner->GetWorld() : nullptr;
		if (World && Owner && Owner->GetNetMode() != NM_DedicatedServer)
		{
			TArray<AWSPC2DetachedPartActor::FSectionInput> PartInputs;
			FBox PartBounds(ForceInit);
			for (const FDeformSection& Sec : PR.Sections)
			{
				if (Sec.Positions.Num() == 0 || Sec.Triangles.Num() < 3)
				{
					continue;
				}
				AWSPC2DetachedPartActor::FSectionInput In;
				In.Vertices = Sec.Positions;
				In.Triangles = Sec.Triangles;
				In.Normals = Sec.Normals;
				In.UV0 = Sec.UV0;
				In.UV1 = Sec.UV1;
				In.UV2 = Sec.UV2;
				In.UV3 = Sec.UV3;
				In.Colors = Sec.Colors;
				In.Tangents = Sec.Tangents;
				In.Material = Sec.Material;
				PartBounds += Sec.LocalBounds;
				PartInputs.Add(MoveTemp(In));
			}

			if (PartInputs.Num() > 0 && PartBounds.IsValid)
			{
				const FTransform PMCWorldXf = PComp->GetComponentTransform();
				const FVector WorldCenter = PMCWorldXf.TransformPosition(PartBounds.GetCenter());
				const FRotator WorldRot = PMCWorldXf.GetRotation().Rotator();

				FActorSpawnParameters SpawnParams;
				SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
				AWSPC2DetachedPartActor* PartActor = World->SpawnActor<AWSPC2DetachedPartActor>(WorldCenter, WorldRot, SpawnParams);
				if (PartActor)
				{
					const float Mass = (Panel == EWSPC2DetachablePanel::Hood || Panel == EWSPC2DetachablePanel::LeftDoor || Panel == EWSPC2DetachablePanel::RightDoor)
						? 22.0f
						: ((Panel == EWSPC2DetachablePanel::LeftMirror || Panel == EWSPC2DetachablePanel::RightMirror) ? 4.0f : 16.0f);
					PartActor->InitFromDeformedGeometry(PartInputs, PartBounds, Mass, Owner->GetVelocity(), ImpulseDirWorld, SpeedKmh);
					SpawnedDetachedActors.Add(PartActor);
				}
			}
		}

		PComp->ClearAllMeshSections();
		PComp->SetVisibility(false);
		PComp->SetHiddenInGame(true);
		UpdateInternalCoreVisibility();
		UE_LOG(LogWSPC2, Log, TEXT("DeformableChassis [%s]: Panel %d -> DETACHED"), *GetNameSafe(OwnerActor.Get()), PIdx);
	}
}

void FWSPC2DeformableChassis::TickLoosePanels(float DeltaTime, float ForwardSpeedKmh)
{
	if (!bInitialized)
	{
		return;
	}

	const float SpeedAlpha = FMath::Clamp(ForwardSpeedKmh / 100.0f, 0.0f, 1.0f);
	for (int32 p = 0; p < static_cast<int32>(EWSPC2DetachablePanel::Count); ++p)
	{
		FPanelRuntime& PR = Panels[p];
		UProceduralMeshComponent* PComp = PR.PMC.Get();
		if (PR.State != EWSPC2PanelDamageState::Loose || !PComp)
		{
			continue;
		}

		PR.FlutterPhase += DeltaTime * (4.5f + SpeedAlpha * 16.0f);
		const EWSPC2DetachablePanel PanelType = static_cast<EWSPC2DetachablePanel>(p);

		if (PanelType == EWSPC2DetachablePanel::Hood || PanelType == EWSPC2DetachablePanel::Trunk)
		{
			const float AerodynamicLift = (PanelType == EWSPC2DetachablePanel::Hood) ? (SpeedAlpha * 24.0f) : (SpeedAlpha * 8.0f);
			const float Flutter = FMath::Sin(PR.FlutterPhase) * (1.2f + SpeedAlpha * 7.5f);
			const float TotalDeg = PR.BaseLooseAngleDeg + (PanelType == EWSPC2DetachablePanel::Hood ? (AerodynamicLift + Flutter) : -(AerodynamicLift + FMath::Abs(Flutter) * 0.5f));
			const FQuat Rot(PR.HingeAxis, FMath::DegreesToRadians(TotalDeg));
			PComp->SetRelativeRotation(Rot);
		}
		else if (PanelType == EWSPC2DetachablePanel::FrontBumper || PanelType == EWSPC2DetachablePanel::RearBumper)
		{
			const float Rattle = FMath::Sin(PR.FlutterPhase * 1.4f) * (1.0f + SpeedAlpha * 4.5f);
			const FQuat DroopPitch(FVector(0.0f, 1.0f, 0.0f), FMath::DegreesToRadians(PR.BaseLooseAngleDeg + Rattle));
			const FQuat CrookedRoll(FVector(1.0f, 0.0f, 0.0f), FMath::DegreesToRadians(PR.LooseSideSign * 11.0f));
			PComp->SetRelativeRotation(DroopPitch * CrookedRoll);
			PComp->SetRelativeLocation(PR.HingePivotBodySpace + FVector(0.0f, 0.0f, -8.0f));
		}
		else
		{
			const float Swing = FMath::Sin(PR.FlutterPhase * 0.9f) * (1.5f + SpeedAlpha * 5.0f);
			const FQuat Rot(PR.HingeAxis, FMath::DegreesToRadians(PR.BaseLooseAngleDeg + Swing));
			PComp->SetRelativeRotation(Rot);
		}
	}
}

void FWSPC2DeformableChassis::ShatterGlassZone(
	EWSPC2GlassZone Zone,
	const FVector& ImpulseDirWorld,
	float SpeedKmh,
	UMaterialInterface* ShardMaterial)
{
	const int32 ZIdx = static_cast<int32>(Zone);
	if (ZIdx < 0 || ZIdx >= static_cast<int32>(EWSPC2GlassZone::Count) || GlassZoneShattered[ZIdx])
	{
		return;
	}
	GlassZoneShattered[ZIdx] = true;

	const FVector ZoneCenter = GlassZoneCentersCarSpace[ZIdx];

	if (bInitialized && GlassPMC.IsValid())
	{
		for (int32 s = 0; s < GlassSections.Num(); ++s)
		{
			FDeformSection& GSec = GlassSections[s];
			const int32 NTris = GSec.Triangles.Num() / 3;
			bool bRemovedAny = false;
			for (int32 t = 0; t < NTris; ++t)
			{
				if (GSec.TriangleRemoved[t])
				{
					continue;
				}
				const int32 V0 = GSec.Triangles[t * 3 + 0];
				const int32 Isl = GSec.VertToIsland[V0];
				if (GSec.IslandZones.IsValidIndex(Isl) && GSec.IslandZones[Isl] == static_cast<uint8>(Zone))
				{
					GSec.TriangleRemoved[t] = true;
					bRemovedAny = true;
				}
			}
			if (bRemovedAny)
			{
				RebuildGlassSectionFromActiveTriangles(s);
			}
		}

		// Darken and dent the lamp socket cavity on MainBodyPMC behind broken headlights/taillights
		if (Zone == EWSPC2GlassZone::Headlight_FL || Zone == EWSPC2GlassZone::Headlight_FR
			|| Zone == EWSPC2GlassZone::Taillight_RL || Zone == EWSPC2GlassZone::Taillight_RR)
		{
			DarkenLightCavityInBody(ZoneCenter, 22.0f);
		}
	}

	SpawnGlassShards(ZoneCenter, ImpulseDirWorld, SpeedKmh, ShardMaterial);
}

void FWSPC2DeformableChassis::RebuildGlassSectionFromActiveTriangles(int32 SecIdx)
{
	UProceduralMeshComponent* GComp = GlassPMC.Get();
	if (!GComp || !GlassSections.IsValidIndex(SecIdx))
	{
		return;
	}
	FDeformSection& GSec = GlassSections[SecIdx];
	const int32 NTris = GSec.Triangles.Num() / 3;
	TArray<int32> ActiveTris;
	ActiveTris.Reserve(GSec.Triangles.Num());
	for (int32 t = 0; t < NTris; ++t)
	{
		if (!GSec.TriangleRemoved[t])
		{
			ActiveTris.Add(GSec.Triangles[t * 3 + 0]);
			ActiveTris.Add(GSec.Triangles[t * 3 + 1]);
			ActiveTris.Add(GSec.Triangles[t * 3 + 2]);
		}
	}

	if (ActiveTris.Num() < 3)
	{
		GSec.bSectionCleared = true;
		GComp->ClearMeshSection(SecIdx);
	}
	else
	{
		GSec.bSectionCleared = false;
		GComp->CreateMeshSection_LinearColor(
			SecIdx, GSec.Positions, ActiveTris, GSec.Normals, GSec.UV0, GSec.UV1, GSec.UV2, GSec.UV3, GSec.Colors, GSec.Tangents, false, false);
		if (GSec.Material)
		{
			GComp->SetMaterial(SecIdx, GSec.Material);
		}
	}
}

void FWSPC2DeformableChassis::DarkenLightCavityInBody(const FVector& CarSpaceCenter, float RadiusCm)
{
	UProceduralMeshComponent* MB = MainBodyPMC.Get();
	if (!MB || CarSpaceCenter.IsNearlyZero())
	{
		return;
	}

	const float RadSq = RadiusCm * RadiusCm;
	for (int32 s = 0; s < MainBodySections.Num(); ++s)
	{
		FDeformSection& Sec = MainBodySections[s];
		bool bDirty = false;
		for (int32 v = 0; v < Sec.Positions.Num(); ++v)
		{
			const FVector CarPos = BodyRelativeTransform.TransformPosition(Sec.Positions[v]);
			const float DistSq = FVector::DistSquared(CarPos, CarSpaceCenter);
			if (DistSq <= RadSq)
			{
				const float Alpha = 1.0f - FMath::Sqrt(DistSq) / RadiusCm;
				if (Sec.bUsesWSPC2DamageMat)
				{
					Sec.Colors[v].R = FMath::Min(Sec.Colors[v].R, 0.25f);
					Sec.Colors[v].G = FMath::Min(Sec.Colors[v].G, 0.20f);
					Sec.Colors[v].B = FMath::Min(Sec.Colors[v].B, 0.08f);
				}
				const FVector InwardDir = (CarSpaceCenter.X >= 0.0f) ? FVector(-1.0f, 0.0f, 0.0f) : FVector(1.0f, 0.0f, 0.0f);
				Sec.Positions[v] += BodyRelativeTransform.InverseTransformVectorNoScale(InwardDir) * (4.5f * Alpha);
				bDirty = true;
			}
		}
		if (bDirty)
		{
			MB->UpdateMeshSection_LinearColor(s, Sec.Positions, Sec.Normals, Sec.UV0, Sec.UV1, Sec.UV2, Sec.UV3, Sec.Colors, Sec.Tangents, false);
		}
	}
}

void FWSPC2DeformableChassis::SpawnGlassShards(const FVector& CarSpaceCenter, const FVector& ImpulseDirWorld, float SpeedKmh, UMaterialInterface* ShardMat)
{
	AActor* Owner = OwnerActor.Get();
	UWorld* World = Owner ? Owner->GetWorld() : nullptr;
	UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"), nullptr, LOAD_NoWarn | LOAD_Quiet);
	if (!Owner || !World || !Cube || Owner->GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	const FVector OriginWorld = Owner->GetActorTransform().TransformPosition(CarSpaceCenter);
	const FVector SafeImpulse = ImpulseDirWorld.IsNearlyZero() ? Owner->GetActorForwardVector() : ImpulseDirWorld.GetSafeNormal();

	for (int32 i = 0; i < 14; ++i)
	{
		const FVector Offset(FMath::FRandRange(-18.0f, 18.0f), FMath::FRandRange(-18.0f, 18.0f), FMath::FRandRange(-8.0f, 16.0f));
		const FRotator Rot(FMath::FRandRange(0.0f, 360.0f), FMath::FRandRange(0.0f, 360.0f), FMath::FRandRange(0.0f, 360.0f));
		FActorSpawnParameters Params;
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

		AStaticMeshActor* Shard = World->SpawnActor<AStaticMeshActor>(OriginWorld + Offset, Rot, Params);
		if (!Shard)
		{
			continue;
		}
		UStaticMeshComponent* MC = Shard->GetStaticMeshComponent();
		Shard->SetMobility(EComponentMobility::Movable);
		MC->SetStaticMesh(Cube);
		MC->SetWorldScale3D(FVector(FMath::FRandRange(0.03f, 0.08f), FMath::FRandRange(0.02f, 0.06f), 0.008f));
		MC->SetCollisionProfileName(TEXT("PhysicsActor"));
		MC->SetCollisionResponseToAllChannels(ECR_Ignore);
		MC->SetCollisionResponseToChannel(ECC_WorldStatic, ECR_Block);
		MC->SetSimulatePhysics(true);
		MC->SetMassOverrideInKg(NAME_None, 0.25f, true);
		if (ShardMat)
		{
			MC->SetMaterial(0, ShardMat);
		}
		const FVector VelDir = (SafeImpulse + FVector(FMath::FRandRange(-0.7f, 0.7f), FMath::FRandRange(-0.7f, 0.7f), FMath::FRandRange(0.2f, 0.9f))).GetSafeNormal();
		MC->SetPhysicsLinearVelocity(Owner->GetVelocity() * 0.45f + VelDir * FMath::FRandRange(220.0f, 680.0f + SpeedKmh * 3.0f));
		MC->SetPhysicsAngularVelocityInDegrees(FVector(FMath::FRandRange(-720.0f, 720.0f), FMath::FRandRange(-720.0f, 720.0f), FMath::FRandRange(-720.0f, 720.0f)));
		Shard->SetLifeSpan(2.8f);
	}
}

void FWSPC2DeformableChassis::ResetAndDestroy(UStaticMeshComponent* BodySMC, UStaticMeshComponent* GlassSMC)
{
	// During engine shutdown / GC purge UObjects may already be unreachable or partially freed; skip unsafe component ops
	if (!IsEngineExitRequested() && !GExitPurge)
	{
		for (const TWeakObjectPtr<UProceduralMeshComponent>& CompWeak : AllCreatedPMCs)
		{
			UProceduralMeshComponent* Comp = CompWeak.Get();
			if (IsValid(Comp) && !Comp->IsUnreachable())
			{
				Comp->ClearAllMeshSections();
				Comp->DestroyComponent();
			}
		}

		for (const TWeakObjectPtr<AWSPC2DetachedPartActor>& WeakActor : SpawnedDetachedActors)
		{
			AWSPC2DetachedPartActor* Part = WeakActor.Get();
			if (IsValid(Part) && !Part->IsUnreachable())
			{
				Part->Destroy();
			}
		}

		if (IsValid(BodySMC) && !BodySMC->IsUnreachable())
		{
			BodySMC->SetVisibility(true);
			BodySMC->SetHiddenInGame(false);
		}
		if (IsValid(GlassSMC) && !GlassSMC->IsUnreachable())
		{
			GlassSMC->SetVisibility(true);
			GlassSMC->SetHiddenInGame(false);
		}
	}

	AllCreatedPMCs.Reset();
	MainBodyPMC.Reset();
	GlassPMC.Reset();
	EngineCorePMC.Reset();

	for (int32 p = 0; p < static_cast<int32>(EWSPC2DetachablePanel::Count); ++p)
	{
		Panels[p] = FPanelRuntime();
	}

	SpawnedDetachedActors.Reset();
	MainBodySections.Reset();
	GlassSections.Reset();
	MaxVertexDisplacementCm = 0.0f;
	bInitialized = false;
	bInternalCoreVisible = false;
}

bool FWSPC2DeformableChassis::HasPanelGeometry(EWSPC2DetachablePanel Panel) const
{
	const int32 Idx = static_cast<int32>(Panel);
	return (Idx >= 0 && Idx < static_cast<int32>(EWSPC2DetachablePanel::Count)) ? Panels[Idx].bHasGeometry : false;
}

EWSPC2PanelDamageState FWSPC2DeformableChassis::GetPanelState(EWSPC2DetachablePanel Panel) const
{
	const int32 Idx = static_cast<int32>(Panel);
	return (Idx >= 0 && Idx < static_cast<int32>(EWSPC2DetachablePanel::Count)) ? Panels[Idx].State : EWSPC2PanelDamageState::Intact;
}

bool FWSPC2DeformableChassis::IsAnyBumperDragging() const
{
	return GetPanelState(EWSPC2DetachablePanel::FrontBumper) == EWSPC2PanelDamageState::Loose
		|| GetPanelState(EWSPC2DetachablePanel::RearBumper) == EWSPC2PanelDamageState::Loose;
}

FVector FWSPC2DeformableChassis::GetAnyDraggingBumperWorldLoc() const
{
	const EWSPC2DetachablePanel Both[2] = { EWSPC2DetachablePanel::FrontBumper, EWSPC2DetachablePanel::RearBumper };
	for (EWSPC2DetachablePanel P : Both)
	{
		const int32 Idx = static_cast<int32>(P);
		if (UProceduralMeshComponent* PComp = Panels[Idx].PMC.Get())
		{
			if (Panels[Idx].State == EWSPC2PanelDamageState::Loose)
			{
				return PComp->GetComponentLocation();
			}
		}
	}
	return FVector::ZeroVector;
}

FVector FWSPC2DeformableChassis::GetGlassZoneCenterCarSpace(EWSPC2GlassZone Zone) const
{
	const int32 ZIdx = static_cast<int32>(Zone);
	return (ZIdx >= 0 && ZIdx < static_cast<int32>(EWSPC2GlassZone::Count)) ? GlassZoneCentersCarSpace[ZIdx] : FVector::ZeroVector;
}

bool FWSPC2DeformableChassis::HasGlassZoneGeometry(EWSPC2GlassZone Zone) const
{
	const int32 ZIdx = static_cast<int32>(Zone);
	return (ZIdx >= 0 && ZIdx < static_cast<int32>(EWSPC2GlassZone::Count)) ? GlassZoneHasTris[ZIdx] : false;
}

bool FWSPC2DeformableChassis::UsesWSPC2DamageMaterial() const
{
	for (const FDeformSection& Sec : MainBodySections)
	{
		if (Sec.bUsesWSPC2DamageMat)
		{
			return true;
		}
	}
	for (int32 p = 0; p < static_cast<int32>(EWSPC2DetachablePanel::Count); ++p)
	{
		for (const FDeformSection& Sec : Panels[p].Sections)
		{
			if (Sec.bUsesWSPC2DamageMat)
			{
				return true;
			}
		}
	}
	return false;
}
