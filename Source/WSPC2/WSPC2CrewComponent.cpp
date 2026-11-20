#include "WSPC2CrewComponent.h"
#include "WSPC2.h"
#include "WSPC2VehicleProfile.h"
#include "Components/PoseableMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "ReferenceSkeleton.h"

namespace WSPC2Crew
{
	const FName Steer(TEXT("Steer"));
	const FName Seated(TEXT("Seated"));
	const FName Handgun(TEXT("Handgun"));
	const FName Longgun(TEXT("Longgun"));
	const FName Tag(TEXT("WSPC2Crew"));

	UObject* Load(const FSoftObjectPath& Path, UClass* Class)
	{
		return Path.IsValid() ? StaticLoadObject(Class, nullptr, *Path.ToString(), nullptr, LOAD_NoWarn | LOAD_Quiet) : nullptr;
	}

	/** A placeholder weapon: boxes in weapon space (x along the barrel, y right, z up; centre and size in cm, pitch) */
	struct FBox3 { FVector Centre; FVector Size; float Pitch; };

	const TArray<FBox3>& Boxes(EWSPC2Weapon Weapon)
	{
		static const TArray<FBox3> Pistol = {
			{ FVector(6.0f, 0.0f, 4.5f), FVector(19.0f, 2.6f, 3.2f), 0.0f },
			{ FVector(5.5f, 0.0f, 2.2f), FVector(17.0f, 2.8f, 2.0f), 0.0f },
			{ FVector(-0.5f, 0.0f, -2.0f), FVector(3.2f, 3.0f, 10.0f), -15.0f } };
		static const TArray<FBox3> Shotgun = {
			{ FVector(32.0f, 0.0f, 4.0f), FVector(56.0f, 2.6f, 2.6f), 0.0f },
			{ FVector(27.0f, 0.0f, 1.0f), FVector(44.0f, 2.4f, 2.4f), 0.0f },
			{ FVector(4.0f, 0.0f, 2.5f), FVector(20.0f, 4.2f, 7.0f), 0.0f },
			{ FVector(27.0f, 0.0f, 0.8f), FVector(16.0f, 4.6f, 4.6f), 0.0f },
			{ FVector(-16.0f, 0.0f, 0.0f), FVector(26.0f, 4.0f, 8.0f), 8.0f },
			{ FVector(-1.0f, 0.0f, -4.0f), FVector(4.0f, 3.0f, 8.0f), -15.0f } };
		static const TArray<FBox3> Rifle = {
			{ FVector(4.0f, 0.0f, 3.0f), FVector(26.0f, 4.0f, 8.0f), 0.0f },
			{ FVector(25.0f, 0.0f, 3.5f), FVector(20.0f, 5.0f, 5.0f), 0.0f },
			{ FVector(44.0f, 0.0f, 3.5f), FVector(20.0f, 1.6f, 1.6f), 0.0f },
			{ FVector(7.0f, 0.0f, -6.0f), FVector(4.0f, 2.4f, 13.0f), 10.0f },
			{ FVector(-16.0f, 0.0f, 2.5f), FVector(24.0f, 4.0f, 7.0f), 0.0f },
			{ FVector(-1.0f, 0.0f, -4.0f), FVector(3.5f, 3.0f, 9.0f), -15.0f },
			{ FVector(5.0f, 0.0f, 9.0f), FVector(12.0f, 1.5f, 3.0f), 0.0f } };
		static const TArray<FBox3> Nothing;
		switch (Weapon)
		{
		case EWSPC2Weapon::Pistol: return Pistol;
		case EWSPC2Weapon::Shotgun: return Shotgun;
		case EWSPC2Weapon::Rifle: return Rifle;
		default: return Nothing;
		}
	}

	/** The muzzle, weapon space */
	FVector Muzzle(EWSPC2Weapon Weapon)
	{
		switch (Weapon)
		{
		case EWSPC2Weapon::Shotgun: return FVector(60.0f, 0.0f, 4.0f);
		case EWSPC2Weapon::Rifle: return FVector(54.0f, 0.0f, 3.5f);
		default: return FVector(15.5f, 0.0f, 4.5f);
		}
	}

	void Blend(const TArray<FTransform>& A, const TArray<FTransform>& B, float Alpha, TArray<FTransform>& Out)
	{
		Out.SetNum(A.Num());
		for (int32 Index = 0; Index < A.Num(); ++Index)
		{
			Out[Index].SetRotation(FQuat::Slerp(A[Index].GetRotation(), B[Index].GetRotation(), Alpha).GetNormalized());
			Out[Index].SetTranslation(FMath::Lerp(A[Index].GetTranslation(), B[Index].GetTranslation(), Alpha));
			Out[Index].SetScale3D(FMath::Lerp(A[Index].GetScale3D(), B[Index].GetScale3D(), Alpha));
		}
	}
}

UWSPC2CrewComponent::UWSPC2CrewComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	// after the car has moved and steered this frame
	PrimaryComponentTick.TickGroup = TG_PostPhysics;
}

void UWSPC2CrewComponent::SetProfile(const FSoftObjectPath& Path)
{
	if (Path != ProfilePath || BuiltPath != Path)
	{
		ProfilePath = Path;
		bDirty = true;
	}
}

void UWSPC2CrewComponent::SetDriveState(float InSteeringWheelDeg, EWSPC2Weapon Weapon, bool bOut, const FVector2D& AimDeg)
{
	SteeringWheelDeg = InSteeringWheelDeg;
	GunnerWeapon = Weapon;
	bGunnerOut = bOut;
	GunnerAim = AimDeg;
}

int32 UWSPC2CrewComponent::GetSeatedCount() const
{
	return (Officers[Driver].Body ? 1 : 0) + (Officers[Gunner].Body ? 1 : 0);
}

void UWSPC2CrewComponent::Clear()
{
	for (USceneComponent* Part : Parts)
	{
		if (Part)
		{
			Part->DestroyComponent();
		}
	}
	Parts.Reset();
	Officers[Driver] = FOfficer();
	Officers[Gunner] = FOfficer();
}

void UWSPC2CrewComponent::Rebuild()
{
	Clear();
	BuiltPath = ProfilePath;

	if (GetNetMode() == NM_DedicatedServer || !ProfilePath.IsValid() || !GetOwner())
	{
		return;
	}

	const UWSPC2CrewProfile* Profile = Cast<UWSPC2CrewProfile>(WSPC2Crew::Load(ProfilePath, UWSPC2CrewProfile::StaticClass()));
	if (!Profile)
	{
		UE_LOG(LogWSPC2, Log, TEXT("Crew: %s not installed (the crowd pack is optional): no officers drawn"), *ProfilePath.ToString());
		return;
	}

	static const FName Roles[2] = { FName(TEXT("Driver")), FName(TEXT("Gunner")) };
	for (int32 Slot = 0; Slot < 2; ++Slot)
	{
		if (const FWSPC2CrewMember* Member = Profile->Members.FindByPredicate([Slot](const FWSPC2CrewMember& M) { return M.Role == Roles[Slot]; }))
		{
			BuildOfficer(Slot, *Member, *Profile);
		}
	}

	UE_LOG(LogWSPC2, Log, TEXT("Crew: %d of 2 officers drawn, driver %d keys, gunner %d keys"), GetSeatedCount(),
		Officers[Driver].Keys.Num(), Officers[Gunner].Keys.Num());
}

bool UWSPC2CrewComponent::BuildOfficer(int32 Slot, const FWSPC2CrewMember& Member, const UWSPC2CrewProfile& Profile)
{
	AActor* Owner = GetOwner();
	USkeletalMesh* BodyMesh = Member.BodyParts.Num() > 0 ? Cast<USkeletalMesh>(WSPC2Crew::Load(Member.BodyParts[0], USkeletalMesh::StaticClass())) : nullptr;
	if (!BodyMesh || Member.Bones.Num() == 0 || Member.Poses.Num() == 0)
	{
		return false;
	}

	FOfficer& Officer = Officers[Slot];
	auto Register = [this](UPrimitiveComponent* Part)
	{
		Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Part->SetGenerateOverlapEvents(false);
		Part->SetCanEverAffectNavigation(false);
		Part->ComponentTags.Add(WSPC2Crew::Tag);
		Part->RegisterComponent();
		Parts.Add(Part);
	};
	auto Swap = [&Profile](UMeshComponent* Mesh)
	{
		for (int32 Index = 0; Index < Mesh->GetNumMaterials(); ++Index)
		{
			// by name or name prefix: a garment's sleeves or belt loops carry the garment's name with a suffix
			const UMaterialInterface* Current = Mesh->GetMaterial(Index);
			const FString Name = Current ? Current->GetName() : FString();
			const int32 Found = Current ? Profile.SwapFrom.IndexOfByPredicate([&Name](const FName& From) { return Name.StartsWith(From.ToString()); }) : INDEX_NONE;
			if (Found != INDEX_NONE && Profile.SwapTo.IsValidIndex(Found))
			{
				if (UMaterialInterface* To = Cast<UMaterialInterface>(WSPC2Crew::Load(Profile.SwapTo[Found], UMaterialInterface::StaticClass())))
				{
					Mesh->SetMaterial(Index, To);
				}
			}
		}
	};

	// the body leads, the outfit follows its pose
	Officer.Body = NewObject<UPoseableMeshComponent>(Owner, MakeUniqueObjectName(Owner, UPoseableMeshComponent::StaticClass(), *FString::Printf(TEXT("Crew%dBody"), Slot)));
	Officer.Body->SetupAttachment(this);
	Officer.Body->SetSkinnedAssetAndUpdate(BodyMesh, false);
	Register(Officer.Body);
	Swap(Officer.Body);

	for (int32 Index = 1; Index < Member.BodyParts.Num(); ++Index)
	{
		if (USkeletalMesh* PartMesh = Cast<USkeletalMesh>(WSPC2Crew::Load(Member.BodyParts[Index], USkeletalMesh::StaticClass())))
		{
			USkeletalMeshComponent* Part = NewObject<USkeletalMeshComponent>(Owner, MakeUniqueObjectName(Owner, USkeletalMeshComponent::StaticClass(), *FString::Printf(TEXT("Crew%dOutfit"), Slot)));
			Part->SetupAttachment(Officer.Body);
			Part->SetSkeletalMeshAsset(PartMesh);
			Part->PrimaryComponentTick.TickGroup = TG_PostUpdateWork;
			Register(Part);
			Part->SetLeaderPoseComponent(Officer.Body);
			Swap(Part);
			Officer.Outfit.Add(Part);
		}
	}

	// the skeleton: rest places in the character's space, then every key as local transforms
	const FReferenceSkeleton& Ref = BodyMesh->GetRefSkeleton();
	const int32 Num = Ref.GetNum();
	TArray<FTransform> Rest;
	Rest.SetNum(Num);
	Officer.Parent.SetNum(Num);
	for (int32 Bone = 0; Bone < Num; ++Bone)
	{
		Officer.Parent[Bone] = Ref.GetParentIndex(Bone);
		Rest[Bone] = Officer.Parent[Bone] == INDEX_NONE ? Ref.GetRefBonePose()[Bone] : Ref.GetRefBonePose()[Bone] * Rest[Officer.Parent[Bone]];
	}

	TArray<int32> DataOf;
	DataOf.Init(INDEX_NONE, Num);
	for (int32 Data = 0; Data < Member.Bones.Num(); ++Data)
	{
		const int32 Bone = Ref.FindBoneIndex(Member.Bones[Data]);
		if (Bone != INDEX_NONE)
		{
			DataOf[Bone] = Data;
		}
	}

	const int32 HandR = Ref.FindBoneIndex(TEXT("hand_r"));
	for (const FWSPC2CrewPose& Pose : Member.Poses)
	{
		FKey& Key = Officer.Keys.AddDefaulted_GetRef();
		Key.Name = Pose.Name;
		Key.Param = Pose.Param;
		Key.Grip = Pose.Grip;
		TArray<FTransform> Comp;
		Comp.SetNum(Num);
		Key.Local.SetNum(Num);

		for (int32 Bone = 0; Bone < Num; ++Bone)
		{
			const int32 Up = Officer.Parent[Bone];
			const int32 Data = DataOf[Bone];
			Comp[Bone] = (Data != INDEX_NONE && Pose.Moves.IsValidIndex(Data)) ? Rest[Bone] * Pose.Moves[Data]
				: (Up == INDEX_NONE ? Ref.GetRefBonePose()[Bone] : Ref.GetRefBonePose()[Bone] * Comp[Up]);
			Key.Local[Bone] = Up == INDEX_NONE ? Comp[Bone] : Comp[Bone].GetRelativeTransform(Comp[Up]);
		}

		Key.HandComponent = HandR != INDEX_NONE ? Comp[HandR] : FTransform::Identity;
	}

	Officer.Keys.Sort([](const FKey& A, const FKey& B) { return A.Name == B.Name ? A.Param < B.Param : A.Name.LexicalLess(B.Name); });
	Officer.Neck = Ref.FindBoneIndex(TEXT("neck_01"));
	Officer.Spine = Ref.FindBoneIndex(TEXT("spine_04"));

	// where each kind of weapon sits in the right hand (from the first key that holds one)
	for (const FKey& Key : Officer.Keys)
	{
		if (Key.Name == WSPC2Crew::Handgun && Officer.HandgunGrip.Equals(FTransform::Identity))
		{
			Officer.HandgunGrip = Key.Grip.GetRelativeTransform(Key.HandComponent);
		}
		if (Key.Name == WSPC2Crew::Longgun && Officer.LonggunGrip.Equals(FTransform::Identity))
		{
			Officer.LonggunGrip = Key.Grip.GetRelativeTransform(Key.HandComponent);
		}
	}

	// the face and the hair ride the head bone: at rest they sit on the body as they are, so relative to the head
	// they are the head's rest place undone
	const int32 Head = Ref.FindBoneIndex(TEXT("head"));
	const FTransform OnHead = Head != INDEX_NONE ? Rest[Head].Inverse() : FTransform::Identity;
	if (USkeletalMesh* FaceMesh = Cast<USkeletalMesh>(WSPC2Crew::Load(Member.FaceMesh, USkeletalMesh::StaticClass())))
	{
		Officer.Face = NewObject<USkeletalMeshComponent>(Owner, MakeUniqueObjectName(Owner, USkeletalMeshComponent::StaticClass(), *FString::Printf(TEXT("Crew%dFace"), Slot)));
		Officer.Face->SetupAttachment(Officer.Body, TEXT("head"));
		Officer.Face->SetRelativeTransform(OnHead);
		Officer.Face->SetSkeletalMeshAsset(FaceMesh);
		Officer.Face->SetDisablePostProcessBlueprint(true);
		Officer.Face->PrimaryComponentTick.bStartWithTickEnabled = false;
		Register(Officer.Face);
	}

	if (UStaticMesh* HairMesh = Cast<UStaticMesh>(WSPC2Crew::Load(Member.HairMesh, UStaticMesh::StaticClass())))
	{
		Officer.Hair = NewObject<UStaticMeshComponent>(Owner, MakeUniqueObjectName(Owner, UStaticMeshComponent::StaticClass(), *FString::Printf(TEXT("Crew%dHair"), Slot)));
		Officer.Hair->SetupAttachment(Officer.Body, TEXT("head"));
		Officer.Hair->SetRelativeTransform(OnHead);
		Officer.Hair->SetStaticMesh(HairMesh);
		if (UMaterialInterface* HairMaterial = Cast<UMaterialInterface>(WSPC2Crew::Load(Member.HairMaterial, UMaterialInterface::StaticClass())))
		{
			Officer.Hair->SetMaterial(0, HairMaterial);
		}
		Register(Officer.Hair);
	}

	// the gunner's weapon hangs from his right hand
	if (Slot == Gunner && HandR != INDEX_NONE)
	{
		Officer.WeaponRoot = NewObject<USceneComponent>(Owner, MakeUniqueObjectName(Owner, USceneComponent::StaticClass(), TEXT("CrewWeapon")));
		Officer.WeaponRoot->SetupAttachment(Officer.Body, TEXT("hand_r"));
		Officer.WeaponRoot->RegisterComponent();
		Parts.Add(Officer.WeaponRoot);
	}

	return true;
}

void UWSPC2CrewComponent::ShowWeapon(FOfficer& Officer, EWSPC2Weapon Weapon)
{
	if (!Officer.WeaponRoot || Officer.ShownWeapon == Weapon)
	{
		return;
	}

	Officer.ShownWeapon = Weapon;
	const TArray<WSPC2Crew::FBox3>& Layout = WSPC2Crew::Boxes(Weapon);
	Officer.WeaponRoot->SetRelativeTransform(UWSPC2GunneryComponent::GetSpec(Weapon).bLongGun ? Officer.LonggunGrip : Officer.HandgunGrip);

	static UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	UMaterialInterface* Gunmetal = Cast<UMaterialInterface>(WSPC2Crew::Load(FSoftObjectPath(TEXT("/Game/Bay/Materials/MI_Bay_Railing.MI_Bay_Railing")), UMaterialInterface::StaticClass()));

	while (Officer.WeaponBoxes.Num() < Layout.Num())
	{
		UStaticMeshComponent* Box = NewObject<UStaticMeshComponent>(GetOwner(), MakeUniqueObjectName(GetOwner(), UStaticMeshComponent::StaticClass(), TEXT("CrewWeaponPart")));
		Box->SetupAttachment(Officer.WeaponRoot);
		Box->SetStaticMesh(Cube);
		if (Gunmetal)
		{
			Box->SetMaterial(0, Gunmetal);
		}
		Box->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Box->SetGenerateOverlapEvents(false);
		Box->SetCanEverAffectNavigation(false);
		Box->ComponentTags.Add(WSPC2Crew::Tag);
		Box->RegisterComponent();
		Parts.Add(Box);
		Officer.WeaponBoxes.Add(Box);
	}

	for (int32 Index = 0; Index < Officer.WeaponBoxes.Num(); ++Index)
	{
		UStaticMeshComponent* Box = Officer.WeaponBoxes[Index];
		if (Layout.IsValidIndex(Index))
		{
			Box->SetRelativeTransform(FTransform(FRotator(Layout[Index].Pitch, 0.0f, 0.0f), Layout[Index].Centre, Layout[Index].Size / 100.0f));
			Box->SetVisibility(true);
		}
		else
		{
			Box->SetVisibility(false);
		}
	}
}

bool UWSPC2CrewComponent::BlendNamed(const FOfficer& Officer, FName Name, float Param, TArray<FTransform>& Out, FTransform* OutGrip)
{
	// the keys are sorted by name, then by Param: the last at or under Param and the first at or over it
	const FKey* First = nullptr;
	const FKey* Last = nullptr;
	const FKey* Below = nullptr;
	const FKey* Above = nullptr;
	for (const FKey& Key : Officer.Keys)
	{
		if (Key.Name != Name)
		{
			continue;
		}
		First = First ? First : &Key;
		Last = &Key;
		if (Key.Param <= Param)
		{
			Below = &Key;
		}
		if (Key.Param >= Param && !Above)
		{
			Above = &Key;
		}
	}

	if (!First)
	{
		return false;
	}
	Below = Below ? Below : First;
	Above = Above ? Above : Last;
	if (Above == Below)
	{
		Out = Below->Local;
		return true;
	}

	const float Alpha = FMath::Clamp((Param - Below->Param) / FMath::Max(Above->Param - Below->Param, KINDA_SMALL_NUMBER), 0.0f, 1.0f);
	WSPC2Crew::Blend(Below->Local, Above->Local, Alpha, Out);
	return true;
}

void UWSPC2CrewComponent::RotateSubtree(const FOfficer& Officer, TArray<FTransform>& Local, int32 Bone, const FQuat& Rotation)
{
	if (!Local.IsValidIndex(Bone))
	{
		return;
	}

	// component-space places of the bone's parent chain
	TArray<FTransform> Comp;
	Comp.SetNum(Local.Num());
	for (int32 Index = 0; Index <= Bone; ++Index)
	{
		const int32 Up = Officer.Parent[Index];
		Comp[Index] = Up == INDEX_NONE ? Local[Index] : Local[Index] * Comp[Up];
	}

	const FVector Pivot = Comp[Bone].GetLocation();
	const FTransform Turned = Comp[Bone] * FTransform(FQuat::Identity, -Pivot) * FTransform(Rotation) * FTransform(FQuat::Identity, Pivot);
	const int32 Up = Officer.Parent[Bone];
	Local[Bone] = Up == INDEX_NONE ? Turned : Turned.GetRelativeTransform(Comp[Up]);
}

void UWSPC2CrewComponent::Animate(float DeltaTime)
{
	TArray<FTransform> Pose;

	// the driver: hands with the rim (they stay at the last key past it), the head a little into the corner
	FOfficer& Driving = Officers[Driver];
	if (Driving.Body && BlendNamed(Driving, WSPC2Crew::Steer, SteeringWheelDeg, Pose))
	{
		const float HeadYaw = FMath::Clamp(SteeringWheelDeg * 0.08f, -12.0f, 12.0f);
		RotateSubtree(Driving, Pose, Driving.Neck, FQuat(FVector::UpVector, FMath::DegreesToRadians(HeadYaw)));
		if (Driving.Body->BoneSpaceTransforms.Num() == Pose.Num())
		{
			Driving.Body->BoneSpaceTransforms = Pose;
			Driving.Body->RefreshBoneTransforms();
		}
	}

	// the gunner: seated, or out of the window with the weapon towards the aim
	FOfficer& Shooting = Officers[Gunner];
	if (Shooting.Body)
	{
		const bool bOut = bGunnerOut && GunnerWeapon != EWSPC2Weapon::None;
		Shooting.Out = FMath::FInterpConstantTo(Shooting.Out, bOut ? 1.0f : 0.0f, DeltaTime, 2.2f);
		ShowWeapon(Shooting, GunnerWeapon);
		if (Shooting.WeaponRoot)
		{
			Shooting.WeaponRoot->SetVisibility(GunnerWeapon != EWSPC2Weapon::None, true);
		}

		TArray<FTransform> Seat;
		const bool bHaveSeat = BlendNamed(Shooting, WSPC2Crew::Seated, 0.0f, Seat);
		const float Out = FMath::SmoothStep(0.0f, 1.0f, Shooting.Out);
		const FName Hold = UWSPC2GunneryComponent::GetSpec(GunnerWeapon).bLongGun ? WSPC2Crew::Longgun : WSPC2Crew::Handgun;

		if (Out > 0.0f && BlendNamed(Shooting, Hold, GunnerAim.X, Pose))
		{
			// the chest bends to the pitch about a level line across the aim
			const float Yaw = FMath::DegreesToRadians(GunnerAim.X);
			const FVector Across = FVector::CrossProduct(FVector(FMath::Cos(Yaw), FMath::Sin(Yaw), 0.0f), FVector::UpVector);
			RotateSubtree(Shooting, Pose, Shooting.Spine, FQuat(Across, FMath::DegreesToRadians(GunnerAim.Y)));
			if (bHaveSeat && Out < 1.0f)
			{
				TArray<FTransform> Mixed;
				WSPC2Crew::Blend(Seat, Pose, Out, Mixed);
				Pose = MoveTemp(Mixed);
			}
		}
		else if (bHaveSeat)
		{
			Pose = MoveTemp(Seat);
		}

		if (Pose.Num() > 0 && Shooting.Body->BoneSpaceTransforms.Num() == Pose.Num())
		{
			Shooting.Body->BoneSpaceTransforms = Pose;
			Shooting.Body->RefreshBoneTransforms();
		}
	}
}

void UWSPC2CrewComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	if (bDirty)
	{
		bDirty = false;
		Rebuild();
	}

	if (GetSeatedCount() > 0)
	{
		Animate(DeltaTime);
	}
}

void UWSPC2CrewComponent::AddToHiddenList(int32 Slot, TSet<FPrimitiveComponentId>& HiddenComponents) const
{
	if (Slot < 0 || Slot > 1)
	{
		return;
	}

	const FOfficer& Officer = Officers[Slot];
	TArray<const UPrimitiveComponent*> All;
	All.Add(Officer.Body);
	All.Add(Officer.Face);
	All.Add(Officer.Hair);
	for (const USkeletalMeshComponent* Part : Officer.Outfit)
	{
		All.Add(Part);
	}
	for (const UStaticMeshComponent* Box : Officer.WeaponBoxes)
	{
		All.Add(Box);
	}

	for (const UPrimitiveComponent* Part : All)
	{
		if (Part)
		{
			HiddenComponents.Add(Part->GetPrimitiveSceneId());
		}
	}
}

bool UWSPC2CrewComponent::GetMuzzle(FVector& OutLocation, FVector& OutDirection) const
{
	const FOfficer& Officer = Officers[Gunner];
	if (!Officer.WeaponRoot || Officer.ShownWeapon == EWSPC2Weapon::None || Officer.ShownWeapon == EWSPC2Weapon::Count || Officer.Out < 0.9f)
	{
		return false;
	}

	const FTransform Weapon = Officer.WeaponRoot->GetComponentTransform();
	OutLocation = Weapon.TransformPosition(WSPC2Crew::Muzzle(Officer.ShownWeapon));
	OutDirection = Weapon.GetUnitAxis(EAxis::X);
	return true;
}
