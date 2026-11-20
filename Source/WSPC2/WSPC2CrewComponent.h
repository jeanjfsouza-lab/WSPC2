// The officers drawn in the car, posed every frame from key poses baked in Blender (Tools/crew/pose_crew.py --keys).

#pragma once

#include "CoreMinimal.h"
#include "Components/SceneComponent.h"
#include "PrimitiveComponentId.h"
#include "UObject/SoftObjectPath.h"
#include "WSPC2Gunnery.h"
#include "WSPC2CrewComponent.generated.h"

class UPoseableMeshComponent;
class USkeletalMeshComponent;
class UStaticMeshComponent;
class UWSPC2CrewProfile;
struct FWSPC2CrewMember;

/**
 * Cosmetic, on every machine but a dedicated server. Builds the driver and the gunner from a UWSPC2CrewProfile (the
 * crowd pack's skeletal body and outfit, a face and hair carried by the head) and poses them each frame:
 *  - the driver's hands go round with the steering wheel (keys "Steer"), his head turns a little into the corner;
 *  - the gunner sits in the passenger seat ("Seated") with nothing in his hands, leans out of the window when he holds
 *    a weapon ("Handgun" / "Longgun" keys at five aim yaws, the pitch added by bending the chest), and comes back in
 *    when the car rolls over. His weapon is a placeholder built of boxes in his right hand.
 * Without the profile (the crowd pack is optional and git-ignored) nothing is drawn.
 */
UCLASS(ClassGroup = (WSPC2))
class UWSPC2CrewComponent : public USceneComponent
{
	GENERATED_BODY()

public:

	UWSPC2CrewComponent();

	static constexpr int32 Driver = 0;
	static constexpr int32 Gunner = 1;

	/** The profile to draw (empty: nobody); built on the next tick */
	void SetProfile(const FSoftObjectPath& Path);

	/** What the officers do this frame: the steering wheel's angle (degrees, + = clockwise as the driver sees it), the
	 *  gunner's weapon, whether he is out of the window, and where he aims (yaw, pitch degrees relative to the car) */
	void SetDriveState(float SteeringWheelDeg, EWSPC2Weapon Weapon, bool bOut, const FVector2D& AimDeg);

	/** Adds one officer's parts to a view's hidden list (a camera inside his head) */
	void AddToHiddenList(int32 Slot, TSet<FPrimitiveComponentId>& HiddenComponents) const;

	/** The gunner's weapon muzzle and barrel direction (world), when he holds one and is drawn */
	bool GetMuzzle(FVector& OutLocation, FVector& OutDirection) const;

	/** How many officers are drawn */
	int32 GetSeatedCount() const;

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

private:

	/** One key pose, already turned into every bone's local (parent-relative) transform */
	struct FKey
	{
		FName Name;
		float Param = 0.0f;
		TArray<FTransform> Local;
		FTransform Grip;
		FTransform HandComponent;      // the right hand's place in this pose (component space)
	};

	struct FOfficer
	{
		UPoseableMeshComponent* Body = nullptr;
		TArray<USkeletalMeshComponent*> Outfit;
		USkeletalMeshComponent* Face = nullptr;
		UStaticMeshComponent* Hair = nullptr;
		USceneComponent* WeaponRoot = nullptr;
		TArray<UStaticMeshComponent*> WeaponBoxes;
		TArray<int32> Parent;
		TArray<FKey> Keys;
		int32 Neck = INDEX_NONE;
		int32 Spine = INDEX_NONE;
		FTransform HandgunGrip;        // the weapon relative to the right hand bone, per way of holding
		FTransform LonggunGrip;
		EWSPC2Weapon ShownWeapon = EWSPC2Weapon::Count;
		float Out = 0.0f;              // 0 seated .. 1 leaning out
	};

	void Rebuild();
	void Clear();
	bool BuildOfficer(int32 Slot, const FWSPC2CrewMember& Member, const UWSPC2CrewProfile& Profile);
	void Animate(float DeltaTime);
	void ShowWeapon(FOfficer& Officer, EWSPC2Weapon Weapon);

	/** Blends the keys named Name at Param into Out (between the two keys around Param) */
	static bool BlendNamed(const FOfficer& Officer, FName Name, float Param, TArray<FTransform>& Out, FTransform* OutGrip = nullptr);

	/** Turns the bone Bone and everything under it about its own joint by Rotation (component space) */
	static void RotateSubtree(const FOfficer& Officer, TArray<FTransform>& Local, int32 Bone, const FQuat& Rotation);

	FSoftObjectPath ProfilePath;
	FSoftObjectPath BuiltPath;
	bool bDirty = false;
	FOfficer Officers[2];

	float SteeringWheelDeg = 0.0f;
	EWSPC2Weapon GunnerWeapon = EWSPC2Weapon::None;
	bool bGunnerOut = false;
	FVector2D GunnerAim = FVector2D(20.0f, 0.0f);

	/** Every part made, kept from the garbage collector */
	UPROPERTY(Transient)
	TArray<TObjectPtr<USceneComponent>> Parts;
};
