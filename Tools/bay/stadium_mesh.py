"""Builds the stadium of the Bay city as meshes (Blender): the bowl of stands with its outer wall, the roof ring on
its pilasters, a floodlight tower behind the middle of each side, the pitch with its lines and goals, and the portal
of the main entrance.

  blender -b --factory-startup --python Tools/bay/stadium_mesh.py

Input:  Tools/bay/sectors.py   STADIUM: the bowl's footprint, the front of the stands, the pitch, the level it stands
                               on, the street corner its main entrance faces
Output: Saved/Bay/structures/EST/EST.glb       meshes in metres, x east, y north, z up, in the map's own coordinates;
                                               one mesh per part (solidkit.export_objects says why)
        Saved/Bay/structures/EST/views.txt     review cameras (Tools/bay/tour.ps1 -Structure EST)
        Saved/Bay/structures/EST/nanite        an empty file: build_bay.py turns Nanite on for this structure
        Saved/Bay/structures/EST/stadium.json  what came out: rows, heights, seats (for the notes)
Material slots: Concrete (structure, walls, stair aisles), Seat and SeatAlt (the rows, in blocks of two colours:
tread and riser alike, the riser standing for the seats' backs), Roof, Steel (roof underside, towers' heads), Rail
(dark panels: the doors, the sign), Light (floodlights), Pitch and PitchAlt (the grass, mown in stripes), PaintWhite
(lines, goals), Lot (the paved margin round the pitch).
build_bay.py places it with:  .\\Tools\\bay\\build.ps1 -Stages structures -Structures EST

What it is. The campaign's own model has here a ring of stands with four towers at the middle of its sides; the
map's drawing has a walled compound. A bowl on that footprint: a rectangle with round corners, the pitch's long axis
east-west. The stands are one continuous terrace round the pitch: a lower tier of LOWER_ROWS rows, a walkway, and an
upper tier that runs back to the outer wall. The wall is nearer the pitch behind the goals than along the touch
lines, so the upper tier is 8 rows deep at the ends and 28 at the sides, and the bowl's rim and its roof sweep up
from the ends to the middle of the sides.
How. Stations every STATION_M along the front of the stands, each with its outward direction; at each, the depth to
the outer wall (found by bisection) gives the terrace's profile, always with the same number of points (rows a
station has no room for are folded flat against the back wall), so neighbouring profiles skin into one body. Every
part is a closed body (solidkit), in pieces of a quarter of the ring, so each mesh stays small enough for Lumen.
"""
import json
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sectors
import solidkit
from common import CURB_M, DATA

NAME = "EST"
SLOTS = ["Concrete", "Seat", "SeatAlt", "Roof", "Steel", "Rail", "Light", "Pitch", "PitchAlt", "PaintWhite", "Lot"]
UV_M = 4.0
ST = sectors.STADIUM
CX, CY = ST["centre"]
AO, BO = ST["half"]
RO = ST["corner"]
AI, BI = ST["inner_half"]
RI = ST["inner_corner"]
PITCH_L, PITCH_W = ST["pitch"]
Z0 = ST["z"] + CURB_M           # the level ground the bowl stands on (block ground: a kerb above the street surface)

STATION_M = 1.6                 # stations along the front of the stands
STRIPE_M = 5.65                 # the pitch is mown in stripes about this wide, across its length
PIECES = 4                      # the ring is built in this many bodies
FOOT = -1.0                     # every body reaches this far below Z0
FLOOR = 0.15                    # the paved floor inside the bowl, above Z0 (clear of the sector's ground under it)
TREAD = 0.80                    # a row
FRONT_H = 1.30                  # the front wall, above the floor
LOWER_ROWS, LOWER_RISE = 20, 0.38
WALK_W = 2.4                    # the walkway between the tiers
UPPER_FRONT, UPPER_RISE = 1.10, 0.50
BACK_W, PARAPET = 1.0, 1.10     # the outer wall's top, and its parapet above the last row
AISLE_EVERY = 14                # a stair aisle every so many stations; between two aisles, one block of seats
ROOF_CLEAR = 4.2                # the roof's underside above the parapet, at the back
ROOF_BACK_T, ROOF_TIP_T = 1.9, 0.35
ROOF_OUT = 0.8                  # the roof's back edge beyond the outer wall
PILASTER_EVERY = 8.7            # along the outer wall
TOWER_H = 52.0                  # a floodlight tower's shaft; its head stands above
GATE_OUT = 12.0                 # the portal of the main entrance, from the bowl's corner towards the street corner


def inner_stations():
    """(x, y, nx, ny) along the front of the stands, counter-clockwise from the south end of the east side, in
    metres from the bowl's centre; (nx, ny) points away from the pitch."""
    out = []
    sx, sy = AI - RI, BI - RI

    def straight(p, q, n):
        count = max(1, int(round(math.hypot(q[0] - p[0], q[1] - p[1]) / STATION_M)))
        for k in range(count):
            t = k / count
            out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, n[0], n[1]))

    def arc(c, first_deg):
        count = max(2, int(round(RI * math.pi / 2.0 / STATION_M)))
        for k in range(count):
            a = math.radians(first_deg + 90.0 * k / count)
            out.append((c[0] + RI * math.cos(a), c[1] + RI * math.sin(a), math.cos(a), math.sin(a)))

    straight((AI, -sy), (AI, sy), (1.0, 0.0))
    arc((sx, sy), 0.0)
    straight((sx, BI), (-sx, BI), (0.0, 1.0))
    arc((-sx, sy), 90.0)
    straight((-AI, sy), (-AI, -sy), (-1.0, 0.0))
    arc((-sx, -sy), 180.0)
    straight((-sx, -BI), (sx, -BI), (0.0, -1.0))
    arc((sx, -sy), 270.0)
    return out


def inside_outer(x, y):
    ax, ay = abs(x), abs(y)
    if ax > AO or ay > BO:
        return False
    if ax > AO - RO and ay > BO - RO:
        return math.hypot(ax - (AO - RO), ay - (BO - RO)) <= RO
    return True


def depth(px, py, nx, ny):
    """Metres from the front of the stands to the outer wall, along the station's own direction."""
    lo, hi = 0.0, 200.0
    for _ in range(44):
        mid = (lo + hi) / 2.0
        if inside_outer(px + nx * mid, py + ny * mid):
            lo = mid
        else:
            hi = mid
    return lo


def upper_rows(d):
    return max(1, int((d - BACK_W - LOWER_ROWS * TREAD - WALK_W) / TREAD + 1e-6))


def profile(d, most_rows):
    """The terrace at a station whose outer wall is d metres back: points (distance from the front, height above the
    floor) from the foot of the front wall round the body and back, the kind of the surface after each point, and
    the height of the last row."""
    back = d - BACK_W
    pts, kinds = [(0.0, 0.0), (0.0, FRONT_H)], ["wall"]
    h = FRONT_H
    for k in range(LOWER_ROWS):
        pts.append(((k + 1) * TREAD, h))
        kinds.append("seat0")
        h = FRONT_H + (k + 1) * LOWER_RISE
        pts.append(((k + 1) * TREAD, h))
        kinds.append("seat0" if k < LOWER_ROWS - 1 else "riser")       # the riser behind a row: the next row's seat backs
    walk = LOWER_ROWS * TREAD + WALK_W
    pts.append((walk, h))
    kinds.append("walk")
    h += UPPER_FRONT
    pts.append((walk, h))
    kinds.append("wall")
    rows = upper_rows(d)
    for j in range(most_rows):
        if j < rows - 1:
            pts.append((walk + (j + 1) * TREAD, h))
            kinds.append("seat1")
            h += UPPER_RISE
            pts.append((walk + (j + 1) * TREAD, h))
            kinds.append("seat1")
        else:                                           # the last row runs to the back wall; the rest are folded there
            pts += [(back, h), (back, h)]
            kinds += ["seat1", "riser"]
    top = h
    pts += [(back, top + PARAPET), (d, top + PARAPET), (d, FOOT), (0.0, FOOT)]
    kinds += ["wall", "wall", "facade", "under", "wall"]
    return pts, kinds, top


def pieces_of(count):
    """Station ranges (first, last) of the ring's bodies; the last one closes the ring on station 0."""
    size = count // PIECES
    return [(p * size, (p + 1) * size if p < PIECES - 1 else count) for p in range(PIECES)]


def ring_bodies(count, section, slot_of, cap="Concrete"):
    """One body per piece of the ring: `section(i)` is the closed loop of 3D points at station i (the same number of
    points at every station), `slot_of(i, k)` the slot of the strip after loop point k between stations i and i + 1."""
    out = []
    for first, last in pieces_of(count):
        body = solidkit.Solid()
        index = list(range(first, last + 1))
        body.sweep([section(i % count) for i in index], lambda k, j, index=index: slot_of(index[j] % count, k), cap)
        out.append(body)
    return out


def slab(body, ring, low, high, slot):
    """An upright prism over a ring of (x, y) points."""
    body.sweep([[(x, y, low) for x, y in ring], [(x, y, high) for x, y in ring]], lambda k, j: slot, slot)


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def arc_strip(body, centre, radius, first_deg, last_deg, width, low, high, slot, steps_per_turn=64):
    """A flat band along an arc (a painted line), as a body with a rectangular cross-section."""
    steps = max(2, int(round(abs(last_deg - first_deg) / 360.0 * steps_per_turn)))
    sections = []
    for k in range(steps + 1):
        a = math.radians(first_deg + (last_deg - first_deg) * k / steps)
        ca, sa = math.cos(a), math.sin(a)
        inner, outer = radius - width / 2.0, radius + width / 2.0
        sections.append([(centre[0] + inner * ca, centre[1] + inner * sa, low), (centre[0] + outer * ca, centre[1] + outer * sa, low),
                         (centre[0] + outer * ca, centre[1] + outer * sa, high), (centre[0] + inner * ca, centre[1] + inner * sa, high)])
    body.sweep(sections, lambda k, j: slot, slot)


def oriented_box(body, centre, along, half_along, half_across, low, high, slot, top_scale=1.0):
    """A box whose plan is turned: `along` is a unit (x, y); its top can be smaller than its foot (a taper)."""
    ax, ay = along
    px, py = -ay, ax

    def loop(z, scale):
        return [(centre[0] + (ax * u * half_along + px * v * half_across) * scale,
                 centre[1] + (ay * u * half_along + py * v * half_across) * scale, z) for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1))]

    body.sweep([loop(low, 1.0), loop(high, top_scale)], lambda k, j: slot, slot)


def main():
    stations = inner_stations()
    count = len(stations)
    depths = [depth(*s) for s in stations]
    most_rows = max(upper_rows(d) for d in depths)
    profiles = [profile(d, most_rows) for d in depths]
    tops = [p[2] for p in profiles]
    points = len(profiles[0][0])
    assert all(len(p[0]) == points for p in profiles)

    def world(i, d, h):
        px, py, nx, ny = stations[i]
        return (CX + px + nx * d, CY + py + ny * d, Z0 + FLOOR + h)

    # ---- the bowl
    def bowl_section(i):
        return [world(i, d, h) for d, h in profiles[i][0]]

    def bowl_slot(i, k):
        kind = profiles[i][1][k]
        if kind.startswith("seat"):
            if i % AISLE_EVERY == 0:
                return "Concrete"                       # a stair aisle
            return "Seat" if (i // AISLE_EVERY + int(kind[-1])) % 2 == 0 else "SeatAlt"
        return "Concrete"

    bodies = [("Bowl%d" % k, b) for k, b in enumerate(ring_bodies(count, bowl_section, bowl_slot))]

    # ---- the roof: a wedge that reaches from behind the outer wall out over the back rows, a little higher at its
    # tip. Its height follows the rim, smoothed over 9 stations (the rim itself climbs a row at a time)
    rim = [t + PARAPET for t in tops]
    smooth = [sum(rim[(i + k) % count] for k in range(-4, 5)) / 9.0 for i in range(count)]

    def roof_reach(i):
        return min(25.0, max(14.0, 0.6 * depths[i]))

    def roof_section(i):
        d, under = depths[i], smooth[i] + ROOF_CLEAR
        reach = roof_reach(i)
        tip = under + 0.05 * reach
        return [world(i, d + ROOF_OUT, under), world(i, d - reach, tip), world(i, d - reach, tip + ROOF_TIP_T),
                world(i, d + ROOF_OUT, under + ROOF_BACK_T)]

    bodies += [("Roof%d" % k, b) for k, b in enumerate(ring_bodies(
        count, roof_section, lambda i, k: "Roof" if k == 2 else "Steel", "Steel"))]

    # ---- a ledge round the outer wall, over the doors
    def ledge_section(i):
        d = depths[i]
        return [world(i, d, 4.6), world(i, d + 1.5, 4.6), world(i, d + 1.5, 5.1), world(i, d, 5.1)]

    bodies += [("Ledge%d" % k, b) for k, b in enumerate(ring_bodies(count, ledge_section, lambda i, k: "Concrete"))]

    # ---- pilasters up the outer wall to the roof, and dark doors in every other bay of the straight sides
    outer = [world(i, depths[i], 0.0) for i in range(count)]
    run = [0.0]
    for i in range(count):
        a, b = outer[i], outer[(i + 1) % count]
        run.append(run[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    bays = max(8, int(round(run[-1] / PILASTER_EVERY)))
    posts = []
    for b in range(bays):
        s = run[-1] * b / bays
        i = max(k for k in range(count) if run[k] <= s + 1e-9)
        t = (s - run[i]) / max(run[i + 1] - run[i], 1e-9)
        j = (i + 1) % count
        x, y = outer[i][0] + (outer[j][0] - outer[i][0]) * t, outer[i][1] + (outer[j][1] - outer[i][1]) * t
        nx, ny = stations[i][2] + (stations[j][2] - stations[i][2]) * t, stations[i][3] + (stations[j][3] - stations[i][3]) * t
        size = math.hypot(nx, ny)
        posts.append((x, y, nx / size, ny / size, smooth[i] + (smooth[j] - smooth[i]) * t + ROOF_CLEAR))
    pilasters, doors = solidkit.Solid(), solidkit.Solid()
    for x, y, nx, ny, under in posts:
        oriented_box(pilasters, (x + nx * 0.35, y + ny * 0.35), (-ny, nx), 0.6, 0.55, Z0 + FOOT, Z0 + FLOOR + under, "Concrete")
    for b in range(0, bays, 2):
        (x0, y0, nx0, ny0, _), (x1, y1, nx1, ny1, _) = posts[b], posts[(b + 1) % bays]
        if abs(nx0 - nx1) + abs(ny0 - ny1) > 1e-6:
            continue                                    # not in a bend
        mx, my = (x0 + x1) / 2.0 + nx0 * 0.08, (y0 + y1) / 2.0 + ny0 * 0.08
        oriented_box(doors, (mx, my), (-ny0, nx0), math.hypot(x1 - x0, y1 - y0) / 2.0 - 1.3, 0.10, Z0 + 0.05, Z0 + 3.7, "Rail")
    bodies += [("Pilasters", pilasters), ("Doors", doors)]

    # ---- floodlight towers behind the middle of each side: a tapering shaft, a frame on top leaning towards the
    # pitch, and the lamps as a plate on the frame's face
    for label, (ox, oy) in (("E", (1.0, 0.0)), ("N", (0.0, 1.0)), ("W", (-1.0, 0.0)), ("S", (0.0, -1.0))):
        tower = solidkit.Solid()
        out = (AO if ox else BO) + 4.2
        centre = (CX + ox * out, CY + oy * out)
        oriented_box(tower, centre, (-oy, ox), 3.4, 3.4, Z0 + FOOT, Z0 + TOWER_H, "Concrete", top_scale=0.62)
        lean = math.radians(16.0)

        def head(u, v, w, centre=centre, ox=ox, oy=oy, lean=lean):
            # u along the side, v towards the pitch, w up from the head's own foot; the head leans towards the pitch
            v2, w2 = v * math.cos(lean) + w * math.sin(lean), -v * math.sin(lean) + w * math.cos(lean)
            return (centre[0] - oy * u - ox * v2, centre[1] + ox * u - oy * v2, Z0 + TOWER_H - 1.0 + w2)

        tower.sweep([[head(-8.0, 0.0, 0.0), head(8.0, 0.0, 0.0), head(8.0, 0.0, 10.0), head(-8.0, 0.0, 10.0)],
                     [head(-8.0, 1.3, 0.0), head(8.0, 1.3, 0.0), head(8.0, 1.3, 10.0), head(-8.0, 1.3, 10.0)]],
                    lambda k, j: "Steel", "Steel")
        tower.sweep([[head(-7.5, 1.3, 0.5), head(7.5, 1.3, 0.5), head(7.5, 1.3, 9.5), head(-7.5, 1.3, 9.5)],
                     [head(-7.5, 1.5, 0.5), head(7.5, 1.5, 0.5), head(7.5, 1.5, 9.5), head(-7.5, 1.5, 9.5)]],
                    lambda k, j: "Light", "Light")
        bodies.append(("Tower" + label, tower))

    # ---- the floor inside the bowl, the grass, the lines, the goals
    floor = solidkit.Solid()
    slab(floor, [(CX + s[0], CY + s[1]) for s in stations], Z0 + FOOT, Z0 + FLOOR, "Lot")
    grass_top = Z0 + FLOOR + 0.10
    grass = solidkit.Solid()
    half_l, half_w = PITCH_L / 2.0, PITCH_W / 2.0
    stripes = int(round((PITCH_L + 8.0) / STRIPE_M))
    for k in range(stripes):
        x0 = CX - half_l - 4.0 + (PITCH_L + 8.0) * k / stripes
        x1 = CX - half_l - 4.0 + (PITCH_L + 8.0) * (k + 1) / stripes
        slab(grass, rect(x0, CY - half_w - 4.0, x1, CY + half_w + 4.0), Z0, grass_top, "Pitch" if k % 2 == 0 else "PitchAlt")
    lines = solidkit.Solid()
    lw, lo, hi = 0.12, grass_top - 0.05, grass_top + 0.025

    def line(x0, y0, x1, y1):
        slab(lines, rect(CX + min(x0, x1) - lw / 2.0, CY + min(y0, y1) - lw / 2.0, CX + max(x0, x1) + lw / 2.0, CY + max(y0, y1) + lw / 2.0),
             lo, hi, "PaintWhite")

    for y in (-half_w, half_w):
        line(-half_l, y, half_l, y)
    for x in (-half_l, 0.0, half_l):
        line(x, -half_w, x, half_w)
    arc_strip(lines, (CX, CY), 9.15, 0.0, 180.0, lw, lo, hi, "PaintWhite")
    arc_strip(lines, (CX, CY), 9.15, 180.0, 360.0, lw, lo, hi, "PaintWhite")
    slab(lines, rect(CX - 0.15, CY - 0.15, CX + 0.15, CY + 0.15), lo, hi, "PaintWhite")
    for side in (-1.0, 1.0):
        gx = side * half_l
        for reach, half in ((16.5, 20.16), (5.5, 9.16)):            # the penalty area, the goal area
            line(gx, -half, gx - side * reach, -half)
            line(gx, half, gx - side * reach, half)
            line(gx - side * reach, -half, gx - side * reach, half)
        spot = gx - side * 11.0
        slab(lines, rect(CX + spot - 0.12, CY - 0.12, CX + spot + 0.12, CY + 0.12), lo, hi, "PaintWhite")
        open_deg = math.degrees(math.acos(5.5 / 9.15))                # the arc outside the penalty area
        middle = 180.0 if side > 0 else 0.0
        arc_strip(lines, (CX + spot, CY), 9.15, middle - open_deg, middle + open_deg, lw, lo, hi, "PaintWhite")
        for cy, first in ((-half_w, 90.0 if side > 0 else 0.0), (half_w, 180.0 if side > 0 else 270.0)):
            arc_strip(lines, (CX + gx, CY + cy), 1.0, first, first + 90.0, lw, lo, hi, "PaintWhite")
    goals = solidkit.Solid()
    for side in (-1.0, 1.0):
        gx = CX + side * half_l
        for y in (-3.66, 3.66):
            slab(goals, rect(gx - 0.06, CY + y - 0.06, gx + 0.06, CY + y + 0.06), grass_top - 0.1, grass_top + 2.50, "PaintWhite")
            slab(goals, rect(gx + side * 2.0 - 0.04, CY + y - 0.04, gx + side * 2.0 + 0.04, CY + y + 0.04), grass_top - 0.1, grass_top + 2.0, "PaintWhite")
        slab(goals, rect(gx - 0.06, CY - 3.72, gx + 0.06, CY + 3.72), grass_top + 2.44, grass_top + 2.56, "PaintWhite")
    bodies += [("Floor", floor), ("Grass", grass), ("Lines", lines), ("Goals", goals)]

    # ---- the portal of the main entrance, on the line from the bowl's north-east corner to the street corner
    corner = (CX + AO - RO, CY + BO - RO)
    gx, gy = ST["gate"][0] - corner[0], ST["gate"][1] - corner[1]
    size = math.hypot(gx, gy)
    ux, uy = gx / size, gy / size
    at = (corner[0] + ux * (RO + GATE_OUT), corner[1] + uy * (RO + GATE_OUT))
    gate = solidkit.Solid()
    for side in (-1.0, 1.0):
        oriented_box(gate, (at[0] - uy * side * 13.0, at[1] + ux * side * 13.0), (-uy, ux), 1.6, 1.6, Z0 + FOOT, Z0 + 16.0, "Concrete")
    oriented_box(gate, at, (-uy, ux), 16.0, 1.1, Z0 + 11.0, Z0 + 13.2, "Concrete")
    oriented_box(gate, (at[0] + ux * 1.2, at[1] + uy * 1.2), (-uy, ux), 11.0, 0.12, Z0 + 11.3, Z0 + 12.9, "Rail")
    bodies.append(("Gate", gate))

    # ---- export
    bpy.ops.wm.read_factory_settings(use_empty=True)
    out_dir = os.path.join(DATA, "structures", NAME)
    os.makedirs(out_dir, exist_ok=True)
    objects = [solidkit.build_object("%s_%s" % (NAME, label), body, SLOTS, UV_M) for label, body in bodies if body.f]
    faces = solidkit.export_objects(objects, os.path.join(out_dir, NAME + ".glb"))
    open(os.path.join(out_dir, "nanite"), "w").close()

    # ---- review cameras (Unreal cm: x east, y south, z up)
    def cm(p):
        return "%d,%d,%d" % (round(p[0] * 100), round(-p[1] * 100), round(p[2] * 100))

    high = Z0 + FLOOR + max(tops)
    views = [("air_ne", (CX + 190.0, CY + 170.0, 120.0), (CX, CY, 15.0)),
             ("air_sw", (CX - 190.0, CY - 170.0, 120.0), (CX, CY, 15.0)),
             ("air_se", (CX + 200.0, CY - 150.0, 70.0), (CX, CY, 18.0)),
             ("top", (CX, CY - 0.1, 330.0), (CX, CY, 0.0)),
             ("gate", (ST["gate"][0] - 4.0, ST["gate"][1] - 3.0, 9.6), (at[0], at[1], Z0 + 9.0)),
             ("stand_n", (CX + 25.0, CY + BO - 5.0, high + 1.5), (CX - 30.0, CY - 25.0, Z0)),
             ("stand_w", (CX - AO + 5.0, CY + 10.0, Z0 + FLOOR + min(tops) + 1.5), (CX + 40.0, CY - 10.0, Z0 + 4.0)),
             ("pitch", (CX - 45.0, CY - 6.0, Z0 + FLOOR + 1.9), (CX + 50.0, CY + 14.0, Z0 + 9.0)),
             ("south", (CX - 30.0, CY - BO - 26.0, 6.6), (CX + 20.0, CY - BO + 20.0, 18.0)),
             ("west", (CX - AO - 21.0, CY - 20.0, 6.6), (CX - AO + 20.0, CY + 10.0, 14.0)),
             ("tower_n", (CX + 70.0, CY + BO + 55.0, 34.0), (CX, CY + BO + 4.0, 44.0))]
    with open(os.path.join(out_dir, "views.txt"), "w") as f:
        for label, cam, look in views:
            f.write("%s_%s;%s;%s\n" % (NAME, label, cm(cam), cm(look)))

    # ---- what came out
    seats = 0.0
    for i in range(count):
        j = (i + 1) % count
        rows = LOWER_ROWS + upper_rows(depths[i])
        a, b = world(i, depths[i] / 2.0, 0.0), world(j, depths[j] / 2.0, 0.0)
        if i % AISLE_EVERY:
            seats += rows * math.hypot(b[0] - a[0], b[1] - a[1]) / 0.5
    info = {"stations": count, "depth_m": [round(min(depths), 2), round(max(depths), 2)],
            "upper_rows": [min(upper_rows(d) for d in depths), most_rows],
            "rim_m": [round(min(tops) + PARAPET + FLOOR, 2), round(max(tops) + PARAPET + FLOOR, 2)],
            "roof_top_m": round(max(smooth) + ROOF_CLEAR + ROOF_BACK_T + FLOOR, 2), "tower_top_m": round(TOWER_H + 9.0, 1),
            "seats": int(round(seats / 100.0) * 100), "faces": faces, "meshes": len(objects), "ground_z": round(Z0, 2),
            "gate_at": [round(at[0], 1), round(at[1], 1)]}
    with open(os.path.join(out_dir, "stadium.json"), "w") as f:
        json.dump(info, f, indent=1)
    print("STADIUM %s: %d meshes, %d faces; %d stations, stands %.1f to %.1f m deep, rim %.1f to %.1f m above the ground, "
          "roof to %.1f m, towers to %.1f m, about %d seats" % (
              NAME, len(objects), faces, count, min(depths), max(depths), info["rim_m"][0], info["rim_m"][1], info["roof_top_m"],
              info["tower_top_m"], info["seats"]))


if __name__ == "__main__":
    main()
