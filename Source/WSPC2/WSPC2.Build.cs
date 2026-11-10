// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class WSPC2 : ModuleRules
{
	public WSPC2(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[] {
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"EnhancedInput",
			"ChaosVehicles",
			"PhysicsCore",
			"UMG",
			"Slate",
			"SlateCore",
			"DeveloperSettings",
			"NetCore"
		});

		PublicIncludePaths.AddRange(new string[] {
			"WSPC2",
			"WSPC2/SportsCar",
			"WSPC2/OffroadCar",
			"WSPC2/Variant_OffRoad",
			"WSPC2/Variant_TimeTrial",
			"WSPC2/Variant_TimeTrial/UI"
		});

		PrivateDependencyModuleNames.AddRange(new string[] { });

		// Uncomment if you are using Slate UI
		// PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });

		// Uncomment if you are using online features
		// PrivateDependencyModuleNames.Add("OnlineSubsystem");

		// To include OnlineSubsystemSteam, add it to the plugins section in your uproject file with the Enabled attribute set to true
	}
}
