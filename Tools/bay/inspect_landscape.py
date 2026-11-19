"""Lists what the Bay landscape's material does besides its numbered layers, to compare with M_BayWild.

  .\\Tools\\bay\\build.ps1 -Script inspect_landscape.py -Commandlet

Input:  /Game/Bay/Materials/MI_BayLandscape and its parents; /Game/Bay/Materials/M_BayWild; the layer function
        /Game/CityPark/Materials/BaseMaterial/MaterialFunction/MF_LandscapeLayer1
Output: log lines tagged BAY: every scalar and vector parameter of the landscape instance that is not one of a
        numbered layer's (with its value), the chain of parents, the base material's shading settings, and for the
        base material and the layer function the count of expressions by class and the names of the functions
        they call, and how each landscape layer blend mixes its layers (weight, alpha or height). Writes nothing.
"""
import collections
import re

import unreal

assets = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
LANDSCAPE = "/Game/Bay/Materials/MI_BayLandscape"
WILD = "/Game/Bay/Materials/M_BayWild"
FUNCTION = "/Game/CityPark/Materials/BaseMaterial/MaterialFunction/MF_LandscapeLayer1"


def log(text):
    unreal.log("BAY " + text)


def describe(material, label):
    for prop in ("blend_mode", "two_sided", "shading_model", "use_material_attributes", "tangent_space_normal",
                 "fully_rough", "is_sky", "dithered_lod_transition"):
        try:
            log("%s %s = %s" % (label, prop, material.get_editor_property(prop)))
        except Exception:
            pass
    for prop in ("base_color", "specular", "roughness", "metallic", "normal", "ambient_occlusion", "emissive_color",
                 "world_position_offset", "subsurface_color"):
        try:
            node = mel.get_material_property_input_node(material, getattr(unreal.MaterialProperty, "MP_" + prop.upper()))
            log("%s %s <- %s" % (label, prop, (node.get_class().get_name() + " " + node.get_name()) if node else "nothing"))
        except Exception as error:
            log("%s %s: %s" % (label, prop, error))


def main():
    mi = assets.load_asset(LANDSCAPE)
    chain, parent = [], mi
    while parent is not None:
        chain.append(parent.get_path_name())
        parent = parent.get_editor_property("parent") if isinstance(parent, unreal.MaterialInstance) else None
    log("parents: " + " -> ".join(chain))
    base = assets.load_asset(chain[-1].split(".")[0])
    numbered = re.compile(r"\d+\s*$")
    for kind, names, read in (("scalar", mel.get_scalar_parameter_names(mi), mel.get_material_instance_scalar_parameter_value),
                              ("vector", mel.get_vector_parameter_names(mi), mel.get_material_instance_vector_parameter_value),
                              ("texture", mel.get_texture_parameter_names(mi), mel.get_material_instance_texture_parameter_value),
                              ("switch", mel.get_static_switch_parameter_names(mi), mel.get_material_instance_static_switch_parameter_value)):
        plain = [str(n) for n in names if not numbered.search(str(n))]
        log("%s parameters: %d in all, %d not of a numbered layer" % (kind, len(names), len(plain)))
        for name in sorted(plain):
            value = read(mi, name)
            if kind == "vector":
                value = "(%.3f, %.3f, %.3f, %.3f)" % (value.r, value.g, value.b, value.a)
            elif kind == "texture":
                value = value.get_path_name() if value else None
            log("  %s %s = %s" % (kind, name, value))
    # the layers the instance uses, as the wild material reads them
    for n in (1, 2, 3, 4, 7):
        names = [str(x) for x in mel.get_scalar_parameter_names(mi) if re.search(r"\D%d\s*$" % n, str(x))]
        log("layer %d scalars: %s" % (n, ", ".join("%s=%.3f" % (x, mel.get_material_instance_scalar_parameter_value(mi, x)) for x in sorted(names))))
        names = [str(x) for x in mel.get_vector_parameter_names(mi) if re.search(r"\D%d\s*$" % n, str(x))]
        for x in sorted(names):
            v = mel.get_material_instance_vector_parameter_value(mi, x)
            log("layer %d vector %s = (%.3f, %.3f, %.3f)" % (n, x, v.r, v.g, v.b))
    describe(base, "base")
    wild = assets.load_asset(WILD)
    if wild:
        describe(wild, "wild")
    for label, owner, count in (("base", base, mel.get_num_material_expressions(base)),):
        log("%s: %d expressions" % (label, count))
    function = assets.load_asset(FUNCTION)
    log("layer function %s: %d expressions" % (FUNCTION, mel.get_num_material_expressions_in_function(function)))
    # the expressions themselves are not listed by the editing library; the object iterator reaches them
    for label, owner in (("base", base), ("function", function)):
        classes, calls, params = collections.Counter(), collections.Counter(), []
        for obj in unreal.ObjectIterator(unreal.MaterialExpression) if hasattr(unreal, "ObjectIterator") else []:
            try:
                if obj.get_outer() != owner and obj.get_outer().get_outer() != owner:
                    continue
            except Exception:
                continue
            classes[obj.get_class().get_name()] += 1
            if isinstance(obj, unreal.MaterialExpressionLandscapeLayerBlend):
                rows = []
                for layer in obj.get_editor_property("layers"):
                    rows.append("%s %s" % (layer.get_editor_property("layer_name"), str(layer.get_editor_property("blend_type")).split(".")[-1].split(":")[0]))
                log("%s %s layers: %s" % (label, obj.get_name(), ", ".join(rows)))
            if isinstance(obj, unreal.MaterialExpressionConstant) and label == "base":
                log("%s %s = %.3f" % (label, obj.get_name(), obj.get_editor_property("r")))
            if isinstance(obj, unreal.MaterialExpressionMaterialFunctionCall):
                f = obj.get_editor_property("material_function")
                calls[f.get_name() if f else "None"] += 1
            if isinstance(obj, (unreal.MaterialExpressionScalarParameter, unreal.MaterialExpressionVectorParameter)):
                name = str(obj.get_editor_property("parameter_name"))
                if not numbered.search(name):
                    params.append(name)
        log("%s expressions by class: %s" % (label, ", ".join("%s %d" % kv for kv in classes.most_common(40))))
        log("%s calls: %s" % (label, ", ".join("%s x%d" % kv for kv in calls.most_common(30))))
        log("%s plain parameters: %s" % (label, ", ".join(sorted(set(params)))))
    log("DONE")


main()
