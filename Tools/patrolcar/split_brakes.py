"""Cuts the front brakes (disc, caliper, hub parts) and the steering wheel out of the City Sample patrol car body, so
they can move: the brakes steer with the front wheels, the steering wheel turns with the steering (commandlet).

  UnrealEditor-Cmd.exe D:/Github/WSPC2/WSPC2.uproject -run=pythonscript -script="D:/Github/WSPC2/Tools/patrolcar/split_brakes.py"

In the pack the front brakes and the steering wheel are part of the body mesh, so they stood still.
Writes, next to the pack's own meshes (git-ignored like the pack):
  /Game/CitySampleVehicles/vehicle13_Car/WSPC2/SM_Body_NoFrontBrakes   the body without them
  /Game/CitySampleVehicles/vehicle13_Car/WSPC2/SM_Brake_FL, SM_Brake_FR  the brake parts, still in car space
  /Game/CitySampleVehicles/vehicle13_Car/WSPC2/SM_SteeringWheel        the steering wheel (rim, spokes, hub), car space
AWSPC2SportsCar uses them when present (the Patrol preset: SplitBodyNoFrontBrakesMesh, FrontBrakeMeshes,
SteeringWheelMesh/Centre/Axis); without them it uses the pack's body.
The cut is done on the original meshes (hi-res Nanite source and LOD 0) by UWSPC2CityTools::KeepTrianglesInCylinder and
KeepTrianglesInAxisCylinder. A triangle is a brake part when its centre lies inside the wheel's cylinder: within 92% of
the tyre radius around the hub, from the tyre's outer face to 10 cm inboard of its inner face. It is the steering wheel
when its centre lies within STEERING_RADIUS_CM of the steering axis and from STEERING_BEHIND_CM to STEERING_FRONT_CM along
it (Tools/crew/pose_crew.py measured the wheel: centre (0.355, 0.415, 0.90) m in Blender, rim radius 0.18 m, its face
18 degrees up from upright). Logs lines starting with PATROLBRAKES.
"""
import unreal

PACK = "/Game/CitySampleVehicles/vehicle13_Car/Mesh/"
OUT = "/Game/CitySampleVehicles/vehicle13_Car/WSPC2/"
BODY = PACK + "SM_vehCar_vehicle13_No_Wheel"
WHEELS = {"FL": PACK + "SM_Wheel_Front_L_vehCar_vehicle13", "FR": PACK + "SM_Wheel_Front_R_vehCar_vehicle13"}
RADIUS_FRACTION = 0.92
INBOARD_CM = 10.0
STEERING_CENTRE = unreal.Vector(35.5, -41.5, 90.0)      # Unreal car space, cm (Blender y = 0.415 is Unreal y = -41.5)
STEERING_AXIS = unreal.Vector(-0.9511, 0.0, 0.3090)     # towards the driver: the face leans 18 degrees back
STEERING_RADIUS_CM = 21.0                               # the rim (18 cm) and its grip
STEERING_BEHIND_CM = -7.0                               # the hub reaches this far towards the dashboard
STEERING_FRONT_CM = 4.0                                 # the rim stands this far towards the driver

assets = unreal.EditorAssetLibrary


def log(text):
    unreal.log("PATROLBRAKES " + text)


def cylinder(path):
    """Hub centre, radius and the Y span of a wheel mesh (the wheels are baked in car space, axle along Y)."""
    bounds = assets.load_asset(path).get_bounds()
    o, e = bounds.origin, bounds.box_extent
    outer, inner = (o.y - e.y, o.y + e.y) if o.y < 0 else (o.y + e.y, o.y - e.y)
    inner += INBOARD_CM if o.y < 0 else -INBOARD_CM
    return unreal.Vector(o.x, o.y, o.z), max(e.x, e.z) * RADIUS_FRACTION, min(outer, inner), max(outer, inner)


def fresh_copy(name):
    path = OUT + name
    if assets.does_asset_exist(path):
        assets.delete_asset(path)
    return assets.duplicate_asset(BODY, path)


def cut_steering(mesh, keep_inside):
    return unreal.WSPC2CityTools.keep_triangles_in_axis_cylinder(mesh, STEERING_CENTRE, STEERING_AXIS, STEERING_RADIUS_CM,
                                                                STEERING_BEHIND_CM, STEERING_FRONT_CM, keep_inside)


def main():
    if not assets.does_asset_exist(BODY):
        log("pack body missing, nothing to do")
        return

    cylinders = {side: cylinder(path) for side, path in WHEELS.items()}
    for side, (centre, radius, y_min, y_max) in cylinders.items():
        log("%s hub (%.1f, %.1f, %.1f) radius %.1f, y %.1f .. %.1f" % (side, centre.x, centre.y, centre.z, radius, y_min, y_max))

    body = fresh_copy("SM_Body_NoFrontBrakes")
    for side, (centre, radius, y_min, y_max) in cylinders.items():
        removed = unreal.WSPC2CityTools.keep_triangles_in_cylinder(body, centre, radius, y_min, y_max, False)
        log("body: %d triangles of the %s brake removed" % (removed, side))
    log("body: %d triangles of the steering wheel removed" % cut_steering(body, False))
    assets.save_asset(OUT + "SM_Body_NoFrontBrakes", only_if_is_dirty=False)

    for side, (centre, radius, y_min, y_max) in cylinders.items():
        part = fresh_copy("SM_Brake_" + side)
        removed = unreal.WSPC2CityTools.keep_triangles_in_cylinder(part, centre, radius, y_min, y_max, True)
        log("SM_Brake_%s: %d triangles kept" % (side, part.get_num_triangles(0)))
        assets.save_asset(OUT + "SM_Brake_" + side, only_if_is_dirty=False)

    wheel = fresh_copy("SM_SteeringWheel")
    cut_steering(wheel, True)
    b = wheel.get_bounds()
    log("SM_SteeringWheel: %d triangles kept, bounds centre (%.1f, %.1f, %.1f) half size (%.1f, %.1f, %.1f)" % (
        wheel.get_num_triangles(0), b.origin.x, b.origin.y, b.origin.z, b.box_extent.x, b.box_extent.y, b.box_extent.z))
    assets.save_asset(OUT + "SM_SteeringWheel", only_if_is_dirty=False)

    log("done")


main()
