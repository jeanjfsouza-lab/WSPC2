"""Seats the patrol car's crew: poses the City Sample crowd officer at the wheel (the driver) or on the passenger
window's sill, half out of the car, aiming ahead (the gunner), and writes him as one static mesh.

  blender -b --factory-startup --python Tools/crew/pose_crew.py [-- [--role driver|gunner] [--preview]]
  blender -b --factory-startup --python Tools/crew/pose_crew.py -- --keys      (the key poses the game blends)

Input:  Saved/Crew/export/{body,top,bottom,shoes,car}.fbx and parts.json (Tools/crew/export_crew_parts.py)
Output: Saved/Crew/SM_Crew_<Role>.fbx    the officer's hands, shirt, trousers and shoes (and the gunner's pistol, a
                                         placeholder of three boxes), posed and joined, in the car's own space (Unreal:
                                         x forward, y right, z up, cm): placed at the car's origin with no transform, he
                                         is in his place in vehicle13 (the patrol body)
        Saved/Crew/crew_<role>.json      where the head went: the transform (Unreal car space, cm) that carries the
                                         face mesh and the hair cards from the character's own space to his place (they
                                         are not exported: they only follow the head, see export_crew_parts.py)
        Saved/Crew/preview_<role>_*.png  with --preview: the officer in the car, cut side view and two more (Blender
                                         workbench), for a first look
        Saved/Crew/crew_poses.json       with --keys: every bone of every key pose the game blends at run time
                                         (AWSPC2SportsCar's crew), as the move that carries the bone from its rest place
                                         in the character's own space (Unreal, cm) to its posed place in the car's space:
                                         driver "Steer" at five steering wheel angles (degrees, + = clockwise as the
                                         driver sees it), gunner "Seated" (in the passenger seat, hands on the thighs) and
                                         "Handgun" / "Longgun" (out of the window) at five aim yaws (degrees from the
                                         car's nose, + = to the right), each with the weapon's grip frame

How the driver's pose is made. The armature is turned to face the car's front and moved so the hip joints sit on
SEAT's hip point. The spine leans back a little, the thighs come forward to level, the shins go down to the floor in front of
the pedals and the feet tilt onto them. The hands reach the rim at twenty to two by a two-bone solution worked out on
the joints (reach()). Then the pose is applied to the meshes. All rotations are taken in the car's space about each
joint, so the bones' own axes do not matter.

The gunner (WINDOW) kneels on the passenger seat against the door, hips square to the window and the belt at the
sill's height; the trunk leans out of the window and turns towards the front, the head looks ahead, both hands on a
pistol held out at the height of the shoulders. Only the trunk is out of the car, not the waist. (The game's gunner rides there: AWSPC2GunnerPawn, "half out
of the window"; GunnerSeatLocation of the patrol body is (5, 78, 120) cm.)

Measures of vehicle13, read from cut views of its body (Blender: x forward, y = left, z up, metres): driver's seat
cushion top 0.55, backrest 0.23 behind the hip at hip height, driver centre line y = 0.415, steering wheel centre
(0.355, 0.415, 0.90), rim radius 0.18, its face turned 18 degrees up from upright, floor of the footwell 0.30.
Passenger window: sill 0.98 high, door skin at y = -0.87 to -0.93, opening from x = -0.2 (B pillar) to 0.45 (A
pillar, which slopes back to 0.3 at the top), roof edge 1.40 high at y = -0.69.
"""
import json
import math
import os
import sys

import bpy
import mathutils
from mathutils import Matrix, Vector

PROJECT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EXP = os.path.join(PROJECT, "Saved", "Crew", "export")
OUT = os.path.join(PROJECT, "Saved", "Crew")
PARTS = ["body", "top", "bottom", "shoes"]

SEAT = {
    "hip": Vector((-0.03, 0.415, 0.615)),         # the hip joints' midpoint (H-point): 6 cm over the cushion
    "wheel": Vector((0.355, 0.415, 0.90)),        # steering wheel centre
    "rim": 0.18,
    "wheel_tilt_deg": 18.0,                      # its face looks back at the driver and this far up
    "grip_deg": 62.0,                            # hands this far from the top of the rim: twenty to two
}
POSE_DEG = {                                     # rotations about the car's y axis (negative: the bone's far end goes
    "spine_01": -11.0, "spine_03": -6.0,         # forward and up for a leg, back for the spine)
    "neck_01": 9.0, "head": 8.0,
    "thigh": -90.0, "calf": 45.0, "foot": 18.0,
    "clavicle": 16.0,                            # shoulders brought forward towards the wheel (about the car's z)
    "finger": (38.0, 45.0, 30.0),                # each finger's three joints curled round the rim
}
WINDOW = {
    "hip": Vector((0.05, -0.70, 0.92)),          # kneeling on the passenger seat against the door: the belt at the sill
    "facing_deg": -90.0,                         # hips square to the window (Blender -y is the car's right)
    "aim": Vector((1.0, -0.10, -0.03)).normalized(),        # ahead, a little out from the car
}
GUNNER_DEG = {
    "calf": 90.0, "foot": 60.0,                  # thighs upright, shins back along the cushion, toes pointing back
    "lean": (15.0, 15.0, 10.0),                  # spine_01, _02, _03 out of the window (about the car's x)
    "twist": (15.0, 15.0, 15.0),                 # spine_03, _04, _05 about the spine: the chest turns towards the front
    "neck_twist": 25.0, "head_twist": 20.0,      # the head the rest of the way: it looks ahead
    "neck_roll": -18.0, "head_roll": -16.0,      # and stands up again out of the lean
    "head_nod": 4.0,                             # a nod down along the sights
    "clavicle": 10.0, "finger": (30.0, 42.0, 28.0),
}
# The crowd's men are 1.85 m tall and the patrol car's headliner is 1.43 m over the ground above the driver's seat,
# 0.87 m over the cushion: at full size his head went through the roof. Scaled to about 1.70 m he fits, with a hand's
# room to spare (the crowd blueprint scales its people too: a "ScaleFactor" per body and outfit)
SCALE = 0.92
HEAD_TOP_M = 0.20               # top of the head over the head bone at full size (MetaHuman)
CEILING_M = 1.43


def log(text):
    print("CREW " + text)


def import_parts():
    arms, meshes = {}, {}
    for part in PARTS:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=os.path.join(EXP, part + ".fbx"))
        new = [o for o in bpy.data.objects if o not in before]
        arms[part] = next(o for o in new if o.type == "ARMATURE")
        meshes[part] = [o for o in new if o.type == "MESH"]
    return arms, meshes


def rotate_about(arm, bone, axis_world, degrees):
    """Turns a posed bone about a world axis through its own head."""
    pb = arm.pose.bones[bone]
    axis = (arm.matrix_world.to_3x3().inverted() @ Vector(axis_world)).normalized()
    head = pb.matrix.translation.copy()
    pb.matrix = Matrix.Translation(head) @ Matrix.Rotation(math.radians(degrees), 4, axis) @ Matrix.Translation(-head) @ pb.matrix
    bpy.context.view_layer.update()


def world_head(arm, bone):
    return arm.matrix_world @ arm.pose.bones[bone].head


def angle_axis(a, b):
    """Rotation (axis, degrees) that turns direction a onto direction b."""
    a, b = a.normalized(), b.normalized()
    axis = a.cross(b)
    if axis.length < 1e-8:
        return Vector((0.0, 0.0, 1.0)), 0.0
    return axis.normalized(), math.degrees(math.atan2(axis.length, a.dot(b)))


def curl(arm, s, rim, angles):
    """Closes the four fingers of one hand towards the rim: each joint turns its bone towards the palm's side that
    faces the rim. The palm's normal comes from the knuckles: across them (index to little finger) and along the
    middle finger."""
    hand = world_head(arm, "hand_" + s)
    across = world_head(arm, "pinky_01_" + s) - world_head(arm, "index_01_" + s)
    along = world_head(arm, "middle_02_" + s) - world_head(arm, "middle_01_" + s)
    palm = across.cross(along).normalized()
    if palm.dot(rim - hand) < 0.0:
        palm = -palm
    for finger in ("index", "middle", "ring", "pinky"):
        for k, deg in enumerate(angles, start=1):
            bone = "%s_%02d_%s" % (finger, k, s)
            if bone not in arm.pose.bones:
                continue
            nxt = "%s_%02d_%s" % (finger, k + 1, s)
            tip = world_head(arm, nxt) if nxt in arm.pose.bones else arm.matrix_world @ arm.pose.bones[bone].tail
            direction = tip - world_head(arm, bone)
            axis = direction.cross(palm)
            if axis.length > 1e-6:
                rotate_about(arm, bone, axis.normalized(), deg)


def reach(arm, s, wrist, elbow_way):
    """Two-bone inverse kinematics by the joints themselves (shoulder = upperarm's head, elbow = lowerarm's head,
    wrist = hand's head): the elbow bends to the right length, the upper arm turns the wrist onto the target, and the
    arm swivels about the shoulder-wrist line until the elbow points as near `elbow_way` as it can. (Blender's IK
    constraint aims the forearm bone's tail, which in a skeleton from Unreal is not the wrist.)"""
    upper, lower = "upperarm_" + s, "lowerarm_" + s
    S, E, W = world_head(arm, upper), world_head(arm, lower), world_head(arm, "hand_" + s)
    a, b = (E - S).length, (W - E).length
    d = min(max((wrist - S).length, abs(a - b) + 1e-3), a + b - 1e-3)
    want = math.degrees(math.acos((a * a + b * b - d * d) / (2 * a * b)))
    now = math.degrees((S - E).angle(W - E))
    bend = (S - E).cross(W - E)
    if bend.length < 1e-6:
        bend = Vector((0.0, 0.0, 1.0)).cross(W - E)
    rotate_about(arm, lower, bend.normalized(), want - now)
    W = world_head(arm, "hand_" + s)
    axis, deg = angle_axis(W - S, wrist - S)
    rotate_about(arm, upper, axis, deg)
    # swivel: the elbow's offset from the shoulder-wrist line, turned towards elbow_way's
    E, W = world_head(arm, lower), world_head(arm, "hand_" + s)
    line = (W - S).normalized()
    off = (E - S) - line * (E - S).dot(line)
    way = elbow_way - line * elbow_way.dot(line)
    if off.length > 1e-6 and way.length > 1e-6:
        turn = math.degrees(math.atan2(off.cross(way).dot(line), off.dot(way)))
        rotate_about(arm, upper, line, turn)


def place(arms, meshes, master, hip, facing_deg):
    """Turns the armature to face `facing_deg` (from the car's +x towards +y) and puts its hip point on `hip`."""
    hip_rest = (master.matrix_world @ ((master.data.bones["thigh_l"].head_local + master.data.bones["thigh_r"].head_local) / 2.0))
    turn = Matrix.Rotation(math.radians(90.0 + facing_deg), 4, "Z") @ Matrix.Scale(SCALE, 4)
    placed = Matrix.Translation(hip - (turn @ hip_rest)) @ turn @ master.matrix_world
    for part, arm in arms.items():
        arm.matrix_world = placed
        for o in meshes[part]:
            for mod in o.modifiers:
                if mod.type == "ARMATURE":
                    mod.object = master
    bpy.context.view_layer.update()
    return placed


def seat_legs(master):
    """Sitting: back a little reclined, thighs level, shins down to the floor, feet tilted (driver and passenger)."""
    side = (0.0, 1.0, 0.0)
    for bone in ("spine_01", "spine_03", "neck_01", "head"):
        rotate_about(master, bone, side, POSE_DEG[bone])
    for s in ("l", "r"):
        rotate_about(master, "thigh_" + s, side, POSE_DEG["thigh"])
        rotate_about(master, "calf_" + s, side, POSE_DEG["calf"])
        rotate_about(master, "foot_" + s, side, POSE_DEG["foot"])


def pose_driver(master, steer_deg=0.0):
    """At the wheel. steer_deg turns the wheel clockwise as the driver sees it (a right turn): the hands go round with
    the rim from twenty to two, the wrists keep their place by the grip (a hand's breadth off it, turned with it)."""
    seat_legs(master)
    # hands to the rim: inverse kinematics from the shoulders, wrists a hand's breadth off the grip
    tilt = math.radians(SEAT["wheel_tilt_deg"])
    normal = Vector((-math.cos(tilt), 0.0, math.sin(tilt)))          # the wheel's face, towards the driver
    up = Vector((math.sin(tilt), 0.0, math.cos(tilt)))               # the wheel's own "up"
    left = Vector((0.0, 1.0, 0.0))
    targets = {}
    for s, sign in (("l", 1.0), ("r", -1.0)):
        rotate_about(master, "clavicle_" + s, (0.0, 0.0, 1.0), -sign * POSE_DEG["clavicle"])
        # angle on the rim from its top towards the left; a clockwise turn takes it down on the left
        theta = math.radians(sign * SEAT["grip_deg"] - steer_deg)
        radial = math.sin(theta) * left + math.cos(theta) * up
        tangent = math.cos(theta) * left - math.sin(theta) * up
        rim = SEAT["wheel"] + SEAT["rim"] * radial
        wrist = rim + 0.035 * normal + 0.0345 * radial + sign * 0.0523 * tangent
        targets[s] = (rim, wrist)
        reach(master, s, wrist, Vector((-0.15, sign * 0.55, -1.0)))
        rotate_about(master, "hand_" + s, normal, -0.6 * steer_deg)    # the hand rolls with the rim
        curl(master, s, rim, POSE_DEG["finger"])
    return targets, []


def pose_passenger(master):
    """Sitting in the passenger seat, hands resting on the thighs: the gunner when he is not out of the window."""
    seat_legs(master)
    targets = {}
    for s, sign in (("l", 1.0), ("r", -1.0)):
        knee = world_head(master, "calf_" + s)
        hip = world_head(master, "thigh_" + s)
        rest = hip + (knee - hip) * 0.62 + Vector((0.0, 0.0, 0.09))
        wrist = rest + Vector((-0.06, -sign * 0.02, 0.0))
        targets[s] = (rest, wrist)
        reach(master, s, wrist, Vector((-0.3, sign * 0.5, -1.0)))
        curl(master, s, rest - Vector((0.0, 0.0, 0.08)), (12.0, 18.0, 12.0))
    return targets, []


def aim_vector(yaw_deg):
    """The aim at a yaw from the car's nose (Unreal sense: + = to the right, which is Blender's -y), a little down
    along the sights like WINDOW's."""
    y = math.radians(yaw_deg)
    return Vector((math.cos(y), -math.sin(y), -0.03)).normalized()


def grip_frame(grip, aim):
    """The weapon's frame at its grip: x along the aim, z up, y to the aim's left (Blender)."""
    up = Vector((0.0, 0.0, 1.0))
    x = aim.normalized()
    y = up.cross(x).normalized()
    z = x.cross(y).normalized()
    return Matrix.Translation(grip) @ Matrix((x, y, z)).transposed().to_4x4()


def hand_rotation(master, side):
    pb = master.pose.bones["hand_" + side]
    return (master.matrix_world @ pb.matrix).to_3x3().normalized()


def turn_hand(master, side, want):
    """Turns a hand about its wrist so its rotation becomes `want` (world, 3x3)."""
    delta = (want @ hand_rotation(master, side).inverted()).to_quaternion()
    axis, angle = delta.to_axis_angle()
    if abs(angle) > 1e-5:
        rotate_about(master, "hand_" + side, axis, math.degrees(angle))


def pose_gunner(master, aim_yaw_deg=0.0, gun="handgun", grip_in_hand=None):
    """Kneeling on the passenger seat, the trunk leant out of the window and turned towards the aim (the waist stays in
    the car: the user, 2026-11-19, "ele deve expor somente o tronco, a cintura nao"; a first try sat him on the sill
    with his whole body out). aim_yaw_deg: 0 ahead, 90 straight out of the window, more is behind. A handgun is held
    in both hands at the height of the shoulders; a long gun (shotgun, rifle) has its stock at the right shoulder,
    the right hand on the grip and the left forward on the fore-end. Returns the grip's frame with the targets."""
    out = (1.0, 0.0, 0.0)                                             # about the car's x: positive leans out to -y
    for s in ("l", "r"):
        rotate_about(master, "calf_" + s, out, GUNNER_DEG["calf"])
        rotate_about(master, "foot_" + s, out, GUNNER_DEG["foot"])
    for bone, deg in zip(("spine_01", "spine_02", "spine_03"), GUNNER_DEG["lean"]):
        rotate_about(master, bone, out, deg)

    def along(a, b):
        return (world_head(master, b) - world_head(master, a)).normalized()

    # the hips face the window (90 degrees right of the nose): the trunk, neck and head share the turn to the aim
    turn = (90.0 - aim_yaw_deg) / 90.0
    for bone, deg in zip(("spine_03", "spine_04", "spine_05"), GUNNER_DEG["twist"]):
        rotate_about(master, bone, along(bone, "neck_01"), deg * turn)
    rotate_about(master, "neck_01", along("neck_01", "head"), GUNNER_DEG["neck_twist"] * turn)
    rotate_about(master, "head", along("neck_01", "head"), GUNNER_DEG["head_twist"] * turn)
    rotate_about(master, "neck_01", out, GUNNER_DEG["neck_roll"])
    rotate_about(master, "head", out, GUNNER_DEG["head_roll"])
    rotate_about(master, "head", (0.0, 1.0, 0.0), GUNNER_DEG["head_nod"])
    for s, sign in (("l", 1.0), ("r", -1.0)):
        rotate_about(master, "clavicle_" + s, (0.0, 0.0, 1.0), -sign * GUNNER_DEG["clavicle"])
    aim = aim_vector(aim_yaw_deg)
    up = Vector((0.0, 0.0, 1.0))
    side = up.cross(aim).normalized()                                 # the aim's left
    if gun == "longgun":
        shoulder = world_head(master, "upperarm_r")
        grip = shoulder + aim * 0.20 - up * 0.07 + side * 0.03       # right hand on the grip, stock in the shoulder
        fore = shoulder + aim * 0.50 - up * 0.05 + side * 0.04       # left hand on the fore-end
        wrists = {"r": grip - aim * 0.04, "l": fore - aim * 0.04 - up * 0.02}
        holds = {"r": grip, "l": fore}
    else:
        middle = (world_head(master, "upperarm_l") + world_head(master, "upperarm_r")) / 2.0
        # arms out (the right one nearly straight), the sights a hand under the eyes, the hands outboard of the A
        # pillar (straight ahead of the chest the pistol went through the pillar's top, x 0.4, y -0.88)
        grip = middle + aim * 0.44 + Vector((0.0, -0.12, 0.04))
        wrists = {"r": grip - aim * 0.07 - side * 0.01, "l": grip - aim * 0.10 + side * 0.035 - up * 0.035}
        holds = {"r": grip, "l": grip}
    frame = grip_frame(grip, aim)
    targets = {}
    for s in ("l", "r"):
        targets[s] = (holds[s], wrists[s])
        reach(master, s, wrists[s], Vector((0.0, -0.4, -1.0)))     # both elbows down and out: the roof's edge is inboard
        if s == "r" and grip_in_hand is not None:
            # the weapon rides the right hand: the hand turns so the weapon lies along this aim (the game puts the
            # weapon on the hand with one fixed grip, grip_in_hand, taken from the reference aim)
            turn_hand(master, "r", frame.to_3x3() @ grip_in_hand.inverted())
        curl(master, s, holds[s], GUNNER_DEG["finger"])
    return targets, frame


def pistol(grip, aim):
    """A placeholder pistol (the project has no weapon models yet): slide, frame and grip as three boxes along the
    aim, the grip where the hands close. Material slot MI_Crew_Gun."""
    import bmesh
    up = Vector((0.0, 0.0, 1.0))
    x = aim.normalized()
    y = up.cross(x).normalized()
    z = x.cross(y).normalized()
    frame = Matrix((x, y, z)).transposed().to_4x4()
    material = bpy.data.materials.new("MI_Crew_Gun")
    parts = []
    for centre, size, tilt in ((grip + x * 0.060 + z * 0.045, (0.19, 0.026, 0.032), 0.0),
                               (grip + x * 0.055 + z * 0.022, (0.17, 0.028, 0.020), 0.0),
                               (grip - x * 0.005 - z * 0.020, (0.032, 0.030, 0.10), -15.0)):
        me = bpy.data.meshes.new("gun")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new("gun", me)
        bpy.context.scene.collection.objects.link(o)
        o.matrix_world = Matrix.Translation(centre) @ frame @ Matrix.Rotation(math.radians(tilt), 4, "Y") @ Matrix.Diagonal(Vector(size + (1.0,)))
        me.materials.append(material)
        parts.append(o)
    return parts


def main(role, preview):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arms, meshes = import_parts()
    master = arms["body"]
    names = {b.name for b in master.data.bones}
    for part, objs in meshes.items():
        for o in objs:
            missing = sorted({g.name for g in o.vertex_groups} - names)
            if missing:
                log("%s: %d vertex groups with no bone in the body's skeleton: %s" % (part, len(missing), missing[:8]))
    if role == "gunner":
        placed = place(arms, meshes, master, WINDOW["hip"], WINDOW["facing_deg"])
        targets, frame = pose_gunner(master)
        extra = pistol(frame.translation, frame.col[0].xyz)
    else:
        placed = place(arms, meshes, master, SEAT["hip"], 0.0)
        targets, extra = pose_driver(master)
    for s in ("l", "r"):
        got = world_head(master, "hand_" + s)
        log("hand_%s: wrist at %s, wanted %s (%.1f cm off)" % (s, tuple(round(v, 3) for v in got), tuple(round(v, 3) for v in targets[s][1]),
                                                              (got - targets[s][1]).length * 100))
    for bone in ("head", "thigh_l", "calf_l", "foot_l", "ball_l", "upperarm_l", "upperarm_r", "lowerarm_l"):
        log("%-10s at %s" % (bone, tuple(round(v, 3) for v in world_head(master, bone))))
    if role == "driver":
        top = world_head(master, "head").z + HEAD_TOP_M * SCALE
        log("top of the head about %.3f m, headliner %.2f m: %s" % (top, CEILING_M, "clear by %.0f cm" % ((CEILING_M - top) * 100) if top < CEILING_M else "THROUGH THE ROOF"))
    # where the head went: carries the face and the hair cards, which stay in Unreal (see the docstring)
    posed_head = master.matrix_world @ master.pose.bones["head"].matrix
    rest_head = placed @ master.data.bones["head"].matrix_local
    move = posed_head @ rest_head.inverted()                                  # car space (Blender), metres
    flip = Matrix.Diagonal((1.0, -1.0, 1.0, 1.0))
    to_car = flip @ Matrix.Scale(100.0, 4) @ move @ placed @ flip            # character space (Unreal, cm) -> car space (Unreal, cm)
    loc, rot, scale = to_car.decompose()
    m3 = to_car.to_3x3().normalized()
    record = {"role": role, "origin_cm": [round(v, 3) for v in loc], "x_axis": [round(v, 5) for v in m3.col[0]],
              "y_axis": [round(v, 5) for v in m3.col[1]], "z_axis": [round(v, 5) for v in m3.col[2]], "scale": [round(v, 4) for v in scale],
              "place": {k: (list(v) if isinstance(v, Vector) else v) for k, v in (WINDOW if role == "gunner" else SEAT).items()},
              "pose_deg": GUNNER_DEG if role == "gunner" else POSE_DEG}
    with open(os.path.join(OUT, "crew_%s.json" % role), "w") as f:
        json.dump(record, f, indent=1)
    log("face and hair: character space -> car space: origin %s cm, scale %s" % (record["origin_cm"], record["scale"]))
    # the pose into the meshes, the meshes into one, out
    bpy.ops.object.select_all(action="DESELECT")
    posed = list(extra)
    for part, objs in meshes.items():
        for o in objs:
            bpy.context.view_layer.objects.active = o
            for mod in list(o.modifiers):
                if mod.type == "ARMATURE":
                    bpy.ops.object.modifier_apply(modifier=mod.name)
            mw = o.matrix_world.copy()
            o.parent = None
            o.matrix_world = mw
            posed.append(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in posed:
        o.select_set(True)
    bpy.context.view_layer.objects.active = posed[-1]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.join()
    officer = bpy.context.active_object
    name = "SM_Crew_" + role.capitalize()
    officer.name = name
    for o in list(bpy.data.objects):
        if o.type in ("ARMATURE", "EMPTY") or (o.type == "MESH" and o is not officer):
            bpy.data.objects.remove(o, do_unlink=True)
    log("officer: %d vertices, materials %s" % (len(officer.data.vertices), [m.name for m in officer.data.materials]))
    bpy.ops.object.select_all(action="DESELECT")
    officer.select_set(True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, name + ".fbx"), use_selection=True, object_types={"MESH"},
                             apply_unit_scale=True, use_mesh_modifiers=True, mesh_smooth_type="FACE", add_leaf_bones=False,
                             bake_anim=False)
    log("wrote %s" % os.path.join(OUT, name + ".fbx"))
    if preview:
        render_preview(officer, targets, role)


def render_preview(officer, targets, role):
    bpy.ops.import_scene.fbx(filepath=os.path.join(EXP, "car.fbx"))
    car = next(o for o in bpy.data.objects if o.type == "MESH" and o is not officer)
    for i, m in enumerate(car.data.materials):
        m.diffuse_color = [(0.62, 0.6, 0.55, 1), (0.25, 0.25, 0.3, 1), (0.15, 0.25, 0.6, 1), (0.75, 0.55, 0.35, 1)][i % 4]
    colours = {"M_BodySynthesized": (0.75, 0.55, 0.45, 1), "MI_m_nrw_buttonDown": (0.08, 0.12, 0.3, 1), "MI_m_nrw_slacks": (0.05, 0.07, 0.15, 1),
               "MI_Crew_Gun": (0.9, 0.1, 0.1, 1)}
    for m in officer.data.materials:
        m.diffuse_color = colours.get(m.name, (0.1, 0.1, 0.1, 1))
    for s, (rim, _) in targets.items():
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.015, location=rim)
        bpy.context.active_object.data.materials.append(bpy.data.materials.new("mark"))
        bpy.context.active_object.data.materials[0].diffuse_color = (1, 0, 0, 1)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.render.resolution_x, scene.render.resolution_y = 1100, 700
    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    focus = Vector((0.0, 0.415, 0.95)) if role == "driver" else Vector((0.1, -0.85, 1.3))
    views = (("side", True, (0.0, -3.0, 0.9), (math.radians(90), 0, 0), 3.18, 0),
             ("front", False, (2.6, 0.415, 1.45), None, 0.1, 30),
             ("door", False, (0.05, 1.9, 1.05), None, 0.1, 24)) if role == "driver" else (
             ("side", True, (0.0, -3.0, 1.2), (math.radians(90), 0, 0), 0.1, 0),
             ("front", False, (3.0, -1.2, 1.6), None, 0.1, 30),
             ("rear", False, (-2.6, -2.2, 2.0), None, 0.1, 30),
             ("top", False, (0.3, -0.6, 4.0), None, 0.1, 30))
    for label, ortho, loc, rot, clip, lens in views:
        cam_data.type = "ORTHO" if ortho else "PERSP"
        if ortho:
            cam_data.ortho_scale = 2.2
        else:
            cam_data.lens = lens
        cam.location = loc
        if rot:
            cam.rotation_euler = rot
        else:
            cam.rotation_euler = (focus - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        cam_data.clip_start = clip
        cam_data.clip_end = 30.0
        scene.render.filepath = os.path.join(OUT, "preview_%s_%s.png" % (role, label))
        bpy.ops.render.render(write_still=True)
    log("previews in %s" % OUT)


DRIVER_STEER_KEYS = (-110.0, -55.0, 0.0, 55.0, 110.0)   # steering wheel degrees; past these the hands stay
GUNNER_YAW_KEYS = (-25.0, 20.0, 65.0, 110.0, 155.0)      # the gunner's aim arc (AWSPC2GunnerPawn MinYaw..MaxYaw)
GUNNER_REFERENCE_YAW = 20.0                              # the aim whose grip-in-hand every key keeps
PASSENGER = {"hip": Vector((-0.03, -0.415, 0.615)), "facing_deg": 0.0}    # the driver's seat mirrored
FLIP = Matrix.Diagonal((1.0, -1.0, 1.0, 1.0))


SCALES = []    # every scale seen while baking: the game's transforms take one uniform scale, this checks they are


def unreal_record(m):
    """A transform (Unreal car space, cm) as [x, y, z, qx, qy, qz, qw, scale]."""
    loc, rot, scale = m.decompose()
    SCALES.append(tuple(scale))
    return [round(v, 4) for v in loc] + [round(rot.x, 6), round(rot.y, 6), round(rot.z, 6), round(rot.w, 6), round(scale.x, 5)]


def bone_moves(master):
    """For every bone: the move from its rest place in the character's own space (Unreal, cm) to its posed place in
    the car's space (Unreal, cm). The same chain as the face's in main(): flip, metres to cm, the pose, the placing."""
    placed = master.matrix_world
    to_cm = Matrix.Scale(100.0, 4)
    out = []
    for bone in master.data.bones:
        pb = master.pose.bones[bone.name]
        out.append(unreal_record(FLIP @ to_cm @ placed @ pb.matrix @ bone.matrix_local.inverted() @ FLIP))
    return out


IMPORTED_POSE = {}
IMPORTED_PLACE = {}


def reset_pose(master, arms):
    """Back to the pose and place the import left (not Blender's rest: the FBX importer leaves every bone a basis of
    its own, and the poses above were measured from it, like the static officers of main(); and place() builds on the
    armatures' own matrices, so they must be the imported ones again)."""
    if not IMPORTED_POSE:
        IMPORTED_POSE.update({pb.name: pb.matrix_basis.copy() for pb in master.pose.bones})
        IMPORTED_PLACE.update({part: arm.matrix_world.copy() for part, arm in arms.items()})
    for part, arm in arms.items():
        arm.matrix_world = IMPORTED_PLACE[part]
    for pb in master.pose.bones:
        pb.matrix_basis = IMPORTED_POSE[pb.name]
    bpy.context.view_layer.update()


def bake_keys():
    """Every key pose the game blends, written to crew_poses.json (see the docstring)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arms, meshes = import_parts()
    master = arms["body"]
    reset_pose(master, arms)                             # remembers the imported pose
    to_cm, to_m = Matrix.Scale(100.0, 4), Matrix.Scale(0.01, 4)
    result = {"bones": [b.name for b in master.data.bones], "scale": SCALE, "driver": [], "gunner": []}

    def check(label, targets):
        worst = max((world_head(master, "hand_" + s) - targets[s][1]).length for s in targets) * 100.0
        log("%-16s wrists %.1f cm off at worst" % (label, worst))

    for steer in DRIVER_STEER_KEYS:
        reset_pose(master, arms)
        place(arms, meshes, master, SEAT["hip"], 0.0)
        targets, _ = pose_driver(master, steer)
        check("Steer %+.0f" % steer, targets)
        result["driver"].append({"name": "Steer", "param": steer, "k": bone_moves(master)})
    reset_pose(master, arms)
    place(arms, meshes, master, PASSENGER["hip"], PASSENGER["facing_deg"])
    targets, _ = pose_passenger(master)
    check("Seated", targets)
    result["gunner"].append({"name": "Seated", "param": 0.0, "k": bone_moves(master)})
    for gun, name in (("handgun", "Handgun"), ("longgun", "Longgun")):
        # the grip in the hand as it falls at the reference aim (20 degrees, nearly ahead: the pose first made); every
        # key then turns the hand to hold the weapon the same way along its own aim
        reset_pose(master, arms)
        place(arms, meshes, master, WINDOW["hip"], WINDOW["facing_deg"])
        _, frame = pose_gunner(master, GUNNER_REFERENCE_YAW, gun)
        grip_in_hand = hand_rotation(master, "r").inverted() @ frame.to_3x3()
        for yaw in GUNNER_YAW_KEYS:
            reset_pose(master, arms)
            place(arms, meshes, master, WINDOW["hip"], WINDOW["facing_deg"])
            targets, frame = pose_gunner(master, yaw, gun, grip_in_hand)
            check("%s %+.0f" % (name, yaw), targets)
            grip = FLIP @ to_cm @ frame @ to_m @ FLIP                 # weapon space (Unreal: x barrel, z up, cm) -> car
            result["gunner"].append({"name": name, "param": yaw, "k": bone_moves(master), "grip": unreal_record(grip)})
    spread = max(max(s) - min(s) for s in SCALES)
    log("scales from %.4f to %.4f, worst spread between axes %.5f%s" % (min(min(s) for s in SCALES), max(max(s) for s in SCALES), spread,
                                                                       "" if spread < 1e-3 else "  NOT UNIFORM: the game keeps x only"))
    path = os.path.join(OUT, "crew_poses.json")
    with open(path, "w") as f:
        json.dump(result, f)
    log("wrote %s: %d bones, %d driver and %d gunner key poses" % (path, len(result["bones"]), len(result["driver"]), len(result["gunner"])))


ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if "--keys" in ARGS:
    bake_keys()
else:
    main(ARGS[ARGS.index("--role") + 1] if "--role" in ARGS else "driver", "--preview" in ARGS)
