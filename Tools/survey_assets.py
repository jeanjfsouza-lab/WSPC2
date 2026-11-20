"""Lists what kinds of assets exist under a content path: counts per class, and the names of everything
that is not a texture/material (those are the placeable building blocks).

UnrealEditor-Cmd.exe WSPC2.uproject -run=pythonscript -script="Tools/survey_assets.py"
"""
import unreal

ROOTS = ["/Game/CitySampleBuildings", "/Game/CitySampleVehicles"]
SKIP = {"Texture2D", "MaterialInstanceConstant", "Material", "MaterialFunction", "MaterialFunctionMaterialLayer",
        "MaterialFunctionMaterialLayerBlend", "TextureCube", "VirtualTexture2D"}

registry = unreal.AssetRegistryHelpers.get_asset_registry()

for root in ROOTS:
    assets = registry.get_assets_by_path(root, recursive=True)
    counts = {}
    by_folder = {}
    for a in assets:
        cls = str(a.asset_class_path.asset_name)
        counts[cls] = counts.get(cls, 0) + 1
        if cls in SKIP:
            continue
        folder = str(a.package_path)
        by_folder.setdefault((folder, cls), []).append(str(a.asset_name))
    unreal.log("SURVEY %s counts %s" % (root, counts))
    for (folder, cls), names in sorted(by_folder.items()):
        names.sort()
        shown = ", ".join(names[:6]) + (" ... (+%d)" % (len(names) - 6) if len(names) > 6 else "")
        unreal.log("SURVEY   %s [%s x%d] %s" % (folder.replace(root, ""), cls, len(names), shown))
