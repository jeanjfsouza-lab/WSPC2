"""Builds the buildings of the campaign's named places (sectors.PLACES) as meshes (Blender): the courthouse, the two
hospitals, the two banks, the penitentiary, the air terminal, the power plant and the fire station.

  blender -b --factory-startup --python Tools/bay/place_mesh.py -- all
  blender -b --factory-startup --python Tools/bay/place_mesh.py -- TRB HLE          (the named places only)

Input:  Tools/bay/sectors.py   PLACES: each place's kind, site (centre, the way its front faces, size) and level
Output: Saved/Bay/structures/<name>/<name>.glb     meshes in metres, x east, y north, z up, in the map's own
                                                   coordinates; one mesh per kind of part (walls, glass, trim, ...)
        Saved/Bay/structures/<name>/views.txt      review cameras (Tools/bay/tour.ps1 -Structure <name>)
        Saved/Bay/structures/<name>/nanite         an empty file: build_bay.py turns Nanite on for the structure
        Saved/Bay/structures/<name>/place.json     what was built (parts, faces, height)
Material slots: Stone, Plaster, Brick, Concrete (walls), Glass (windows), Roof, Steel, Rail (dark doors and panels),
Red, PaintWhite (signs, bands, pad markings), Light (lamps).
build_bay.py places them with:  .\\Tools\\bay\\build.ps1 -Stages "materials,structures" -Structures "TRB,HLE,..."

Why buildings of our own: the project's building models (28 from the City Sample) are offices, towers and rows of
houses; none is a hospital, a prison, a power plant or a fire station, and a place the campaign names must be told
from its neighbours at a glance. They are plain: walls of one material, windows as dark glass set a hand proud of
the wall, fins, bands and cornices as raised strips, columns as drums. What makes each one itself is its outline:
a portico and pediment, a ward block over a podium with a cross and a helicopter pad, a wall with corner towers,
two chimneys and a row of tanks, engine bays with red doors and a hose tower, a control tower and a hangar.
How. Every building is drawn in its site's own coordinates (a across the front, b towards the front, z above the
site's ground) out of convex pieces: boxes, drums, prisms. Each face is turned away from the middle of its own
piece, so pieces may touch and overlap freely (solidkit's bodies must not: it finds the outside by flood).
"""
import json
import math
import os
import sys

import bmesh
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sectors
import solidkit
from common import CURB_M, DATA

SLOTS = ["Stone", "Plaster", "Brick", "Concrete", "Glass", "Roof", "Steel", "Rail", "Red", "PaintWhite", "Light", "Lot"]
UV_M = 4.0
FOOT = -1.5                 # walls reach this far below the site's ground
SIDES = ("front", "back", "a0", "a1")


class Site:
    """A place's site and the pieces built on it: label -> faces, each with its slot and a point inside its piece."""

    def __init__(self, name):
        self.name, self.p = name, sectors.PLACES[name]
        self.cx, self.cy = self.p["centre"]
        t = math.radians(self.p["front"])
        self.fx, self.fy = math.cos(t), math.sin(t)
        self.z0 = self.p["z"] + CURB_M
        self.parts = {}
        self.top = 0.0

    def pt(self, a, b, z):
        return (self.cx - self.fy * a + self.fx * b, self.cy + self.fx * a + self.fy * b, self.z0 + z)

    def sweep(self, label, sections, slot):
        """Skin over cross-sections (loops of site points (a, b, z), the same count each), capped at both ends."""
        part = self.parts.setdefault(label, {"v": [], "f": [], "slot": [], "inside": []})
        base, m = len(part["v"]), len(sections[0])
        cents = []
        for sec in sections:
            part["v"].extend(self.pt(*q) for q in sec)
            c = [sum(q[i] for q in sec) / m for i in range(3)]
            cents.append(self.pt(*c))
            self.top = max(self.top, max(q[2] for q in sec))
        mids = [tuple((cents[j][i] + cents[j + 1][i]) / 2.0 for i in range(3)) for j in range(len(sections) - 1)]
        for j in range(len(sections) - 1):
            for k in range(m):
                part["f"].append((base + j * m + k, base + j * m + (k + 1) % m, base + (j + 1) * m + (k + 1) % m, base + (j + 1) * m + k))
                part["slot"].append(slot)
                part["inside"].append(mids[j])
        part["f"].append(tuple(base + k for k in range(m)))
        part["slot"].append(slot)
        part["inside"].append(mids[0])
        part["f"].append(tuple(base + (len(sections) - 1) * m + k for k in range(m)))
        part["slot"].append(slot)
        part["inside"].append(mids[-1])

    def box(self, label, a0, a1, b0, b1, z0, z1, slot, top=None):
        ta0, ta1, tb0, tb1 = top or (a0, a1, b0, b1)
        self.sweep(label, [[(a0, b0, z0), (a1, b0, z0), (a1, b1, z0), (a0, b1, z0)],
                           [(ta0, tb0, z1), (ta1, tb0, z1), (ta1, tb1, z1), (ta0, tb1, z1)]], slot)

    def drum(self, label, a, b, r0, r1, z0, z1, slot, sides=20):
        ring = [(math.cos(2.0 * math.pi * k / sides), math.sin(2.0 * math.pi * k / sides)) for k in range(sides)]
        self.sweep(label, [[(a + r0 * c, b + r0 * s, z0) for c, s in ring], [(a + r1 * c, b + r1 * s, z1) for c, s in ring]], slot)

    def gable(self, label, a0, a1, b0, b1, eave, ridge, slot, along="a"):
        """A roof of two slopes (or a pediment): its ridge runs along a, or along b."""
        if along == "a":
            mid = (b0 + b1) / 2.0
            self.sweep(label, [[(a, b0, eave), (a, b1, eave), (a, mid, ridge)] for a in (a0, a1)], slot)
        else:
            mid = (a0 + a1) / 2.0
            self.sweep(label, [[(a0, b, eave), (a1, b, eave), (mid, b, ridge)] for b in (b0, b1)], slot)

    def arc(self, label, a, b, radius, first_deg, last_deg, width, z0, z1, slot, per_turn=48):
        steps = max(2, int(round(abs(last_deg - first_deg) / 360.0 * per_turn)))
        secs = []
        for k in range(steps + 1):
            t = math.radians(first_deg + (last_deg - first_deg) * k / steps)
            c, s = math.cos(t), math.sin(t)
            r0, r1 = radius - width / 2.0, radius + width / 2.0
            secs.append([(a + r0 * c, b + r0 * s, z0), (a + r1 * c, b + r1 * s, z0), (a + r1 * c, b + r1 * s, z1), (a + r0 * c, b + r0 * s, z1)])
        self.sweep(label, secs, slot)

    # ---- walls of a rectangle (a0, a1, b0, b1): s along the wall, o outwards from it
    @staticmethod
    def run(side, rect):
        return rect[1] - rect[0] if side in ("front", "back") else rect[3] - rect[2]

    def wall(self, label, side, rect, s0, s1, o0, o1, z0, z1, slot):
        a0, a1, b0, b1 = rect
        if side == "front":
            self.box(label, a0 + s0, a0 + s1, b1 + o0, b1 + o1, z0, z1, slot)
        elif side == "back":
            self.box(label, a0 + s0, a0 + s1, b0 - o1, b0 - o0, z0, z1, slot)
        elif side == "a0":
            self.box(label, a0 - o1, a0 - o0, b0 + s0, b0 + s1, z0, z1, slot)
        else:
            self.box(label, a1 + o0, a1 + o1, b0 + s0, b0 + s1, z0, z1, slot)

    def block(self, rect, z0, z1, slot, parapet=0.9, roof="Roof", label="Walls"):
        """A volume with a flat roof behind a parapet."""
        a0, a1, b0, b1 = rect
        self.box(label, a0, a1, b0, b1, z0, z1, slot)
        if parapet:
            for side in SIDES:
                self.wall(label, side, rect, 0.0, self.run(side, rect), -0.3, 0.0, z1 - 0.1, z1 + parapet, slot)
        if roof:
            self.box("Roof", a0 + 0.3, a1 - 0.3, b0 + 0.3, b1 - 0.3, z1 - 0.2, z1 + 0.06, roof)

    def band(self, rect, z0, z1, proud, slot, sides=SIDES, label="Trim"):
        """A raised course round a volume (a cornice, a plinth, a string course)."""
        for side in sides:
            self.wall(label, side, rect, -proud, self.run(side, rect) + proud, -0.05, proud, z0, z1, slot)

    def ribbons(self, rect, base, floors, fh, sides=SIDES, sill=0.95, head=2.75, inset=1.2, fin=3.6, fin_proud=0.22, trim="Concrete"):
        """Windows in one strip per floor, with upright fins between the bays."""
        for side in sides:
            n = self.run(side, rect)
            if n < 2.0 * inset + 1.0:
                continue
            for k in range(floors):
                self.wall("Glass", side, rect, inset, n - inset, -0.15, 0.04, base + k * fh + sill, base + k * fh + head, "Glass")
            if fin:
                count = max(1, int(round((n - 2.0 * inset) / fin)))
                for j in range(count + 1):
                    s = inset + (n - 2.0 * inset) * j / count
                    self.wall("Trim", side, rect, s - 0.16, s + 0.16, -0.1, fin_proud, base + 0.25, base + floors * fh - 0.15, trim)

    def punched(self, rect, base, floors, fh, sides=SIDES, bay=3.4, width=1.5, sill=1.0, head=2.6, inset=1.6):
        """One window to a bay on every floor."""
        for side in sides:
            n = self.run(side, rect)
            count = int((n - 2.0 * inset) / bay)
            if count < 1:
                continue
            start = (n - count * bay) / 2.0
            for k in range(floors):
                for j in range(count):
                    s = start + (j + 0.5) * bay
                    self.wall("Glass", side, rect, s - width / 2.0, s + width / 2.0, -0.15, 0.04, base + k * fh + sill, base + k * fh + head, "Glass")

    def tall(self, rect, z_a, z_b, sides, bay, width, inset=2.0, pilaster=None, slot="Stone", mid=None):
        """Tall windows, one to a bay, with a pilaster between bays: pilaster = (width, proud, z0, z1). With `mid`
        (a height) each window is parted by a spandrel there."""
        for side in sides:
            n = self.run(side, rect)
            count = int((n - 2.0 * inset) / bay)
            if count < 1:
                continue
            start = (n - count * bay) / 2.0
            for j in range(count):
                s = start + (j + 0.5) * bay
                spans = [(z_a, z_b)] if mid is None else [(z_a, mid - 0.45), (mid + 0.45, z_b)]
                for lo, hi in spans:
                    self.wall("Glass", side, rect, s - width / 2.0, s + width / 2.0, -0.15, 0.04, lo, hi, "Glass")
            if pilaster:
                pw, proud, p0, p1 = pilaster
                for j in range(count + 1):
                    s = start + j * bay
                    self.wall("Trim", side, rect, s - pw / 2.0, s + pw / 2.0, -0.1, proud, p0, p1, slot)


# ---- the buildings ------------------------------------------------------------------------------------------------

def hospital(S):
    """A ward block over a podium, white, with ribbon windows; an ambulance canopy at the door, a red cross on the
    ward block's front, a helicopter pad and plant on its roof."""
    w, d = S.p["size"]
    hw, hd = w / 2.0, d / 2.0
    floors, pf, fh, ph = S.p["floors"], S.p["podium_floors"], 3.9, 4.2
    pod_h = pf * ph
    ward_d = min(18.0, d - 5.0)
    top = pod_h + (floors - pf) * fh
    pod = (-hw, hw, -hd, hd)
    ward = (-hw + 3.0, hw - 3.0, -hd, -hd + ward_d)
    S.block(pod, FOOT, pod_h, "Plaster")
    S.block(ward, FOOT, top, "Plaster")
    S.ribbons(pod, 0.0, pf, ph, sides=("front", "a0", "a1"), sill=1.0, head=3.2)
    S.ribbons(pod, 0.0, pf, ph, sides=("back",), sill=1.0, head=3.2)
    S.ribbons(ward, pod_h, floors - pf, fh)
    S.band(pod, pod_h + 0.55, pod_h + 0.9, 0.18, "Concrete")
    S.band(ward, top + 0.55, top + 0.9, 0.18, "Concrete")
    # the door and the ambulance canopy
    S.wall("Glass", "front", pod, hw - 6.0, hw + 6.0, -0.1, 0.07, 0.1, 3.3, "Glass")
    S.box("Trim", -12.0, 12.0, hd - 0.2, hd + 7.0, 4.0, 4.45, "Concrete")
    S.box("Signs", -12.05, 12.05, hd + 6.9, hd + 7.06, 4.02, 4.43, "Red")
    for a in (-11.0, -3.7, 3.7, 11.0):
        S.drum("Trim", a, hd + 6.2, 0.3, 0.3, FOOT, 4.0, "Concrete", 12)
    # the cross, on a white plate at the top of the ward block's front, and again over the door
    bw = -hd + ward_d
    for c, zc in ((-hw + 13.0, top - 4.2), (hw - 13.0, top - 4.2)):
        S.box("Signs", c - 3.1, c + 3.1, bw - 0.1, bw + 0.12, zc - 3.1, zc + 3.1, "PaintWhite")
        S.box("Signs", c - 0.8, c + 0.8, bw - 0.1, bw + 0.24, zc - 2.4, zc + 2.4, "Red")
        S.box("Signs", c - 2.4, c + 2.4, bw - 0.1, bw + 0.24, zc - 0.8, zc + 0.8, "Red")
    # the roof: a helicopter pad on a deck at one end, plant at the other
    pad_a, pad_b = hw - 3.0 - 10.5, -hd + ward_d / 2.0
    half = min(8.5, ward_d / 2.0 - 1.0)
    S.box("Trim", pad_a - half - 1.0, pad_a + half + 1.0, pad_b - half, pad_b + half, top + 0.3, top + 1.5, "Concrete")
    S.arc("Signs", pad_a, pad_b, half - 1.2, 0.0, 180.0, 0.4, top + 1.45, top + 1.53, "PaintWhite")
    S.arc("Signs", pad_a, pad_b, half - 1.2, 180.0, 360.0, 0.4, top + 1.45, top + 1.53, "PaintWhite")
    for da in (-1.6, 1.6):
        S.box("Signs", pad_a + da - 0.3, pad_a + da + 0.3, pad_b - 2.4, pad_b + 2.4, top + 1.45, top + 1.54, "Red")
    S.box("Signs", pad_a - 1.6, pad_a + 1.6, pad_b - 0.3, pad_b + 0.3, top + 1.45, top + 1.54, "Red")
    plant_end = min(-hw + 19.0, pad_a - half - 3.0)                                      # (a short ward block has room for less)
    S.box("Roof", -hw + 7.0, plant_end, pad_b - 4.5, pad_b + 4.5, top, top + 3.2, "Steel")
    if w >= 70.0:
        S.box("Walls", -hw + 22.0, -hw + 28.0, pad_b - 3.0, pad_b + 3.0, top, top + 4.2, "Plaster")


def bank(S):
    """A block of stone behind a colonnade the whole width of its front, on a base with steps; pilasters and tall
    windows round the sides, an attic above the cornice."""
    w, d = S.p["size"]
    hw, hd = w / 2.0, d / 2.0
    height, columns = S.p["height"], S.p["columns"]
    base, porch = 1.4, 5.5
    shaft_top = height - 4.6
    body = (-hw, hw, -hd, hd - porch)
    S.box("Walls", -hw - 0.5, hw + 0.5, -hd - 0.5, hd - 0.6, FOOT, base, "Stone")                 # the base
    S.block(body, base, height, "Stone", parapet=0.0)
    S.box("Walls", -hw, hw, hd - porch, hd - 0.5, shaft_top, height, "Stone")                     # the entablature over the columns
    S.band((-hw, hw, -hd, hd - 0.5), height - 1.3, height - 0.5, 0.7, "Stone")                    # the cornice
    S.block((-hw + 2.0, hw - 2.0, -hd + 2.0, hd - porch - 1.0), height - 0.5, height + 2.6, "Stone", parapet=0.6)   # the attic
    # the colonnade, between two end piers
    S.box("Walls", -hw, -hw + 2.6, hd - porch, hd - 0.5, base, shaft_top, "Stone")
    S.box("Walls", hw - 2.6, hw, hd - porch, hd - 0.5, base, shaft_top, "Stone")
    span = w - 2.0 * 2.6
    for k in range(columns):
        a = -span / 2.0 + span * (k + 0.5) / columns
        S.drum("Columns", a, hd - 2.3, 1.0, 0.88, base + 0.5, shaft_top - 0.6, "Stone", 18)
        S.box("Columns", a - 1.25, a + 1.25, hd - 3.55, hd - 1.05, base, base + 0.5, "Stone")
        S.box("Columns", a - 1.2, a + 1.2, hd - 3.5, hd - 1.1, shaft_top - 0.6, shaft_top, "Stone")
    for k in range(4):                                                                               # the steps
        S.box("Walls", -hw + 1.0, hw - 1.0, hd - 0.6, hd + 0.5 + 0.55 * k, FOOT, base - 0.35 * (k + 1), "Stone")
    # behind the columns: tall windows and the door; round the sides and the back: pilasters and windows in two tiers
    front = (-hw + 2.6, hw - 2.6, -hd, hd - porch)
    bay = span / columns
    S.tall(front, base + 1.6, shaft_top - 2.0, ("front",), bay, bay * 0.42, inset=0.0, mid=base + 0.45 * (shaft_top - base))
    S.box("Signs", -2.4, 2.4, hd - porch - 0.1, hd - porch + 0.12, base, base + 6.4, "Rail")
    side_bay = 5.2
    S.tall(body, base + 1.6, shaft_top - 2.0, ("back", "a0", "a1"), side_bay, 1.9, inset=1.5,
           pilaster=(1.1, 0.32, base, shaft_top), mid=base + 0.45 * (shaft_top - base))
    S.band(body, shaft_top, shaft_top + 0.5, 0.25, "Stone", sides=("back", "a0", "a1"))


def courthouse(S):
    """A long stone front with a portico of eight columns under a pediment at its middle, up a flight of steps; two
    wings of tall windows between pilasters; an attic, and a higher middle block behind the pediment."""
    w, d = S.p["size"]
    hw, hd = w / 2.0, d / 2.0
    base, porch = 2.0, 8.0
    eave, shaft_top = 20.0, 15.4
    pw = 34.0
    body = (-hw, hw, -hd, hd - porch)
    S.box("Walls", -hw - 0.6, hw + 0.6, -hd - 0.6, hd - porch + 0.6, FOOT, base, "Stone")
    S.block(body, base, eave, "Stone", parapet=0.0)
    S.band(body, eave - 1.2, eave - 0.4, 0.7, "Stone")
    S.block((-hw + 3.0, hw - 3.0, -hd + 3.0, hd - porch - 3.0), eave - 0.4, eave + 3.4, "Stone", parapet=0.6)       # the attic
    S.block((-pw / 2.0 - 1.0, pw / 2.0 + 1.0, -hd + 5.0, hd - porch), eave - 0.4, eave + 7.0, "Stone", parapet=0.8)  # the middle block
    # the portico
    S.box("Walls", -pw / 2.0, pw / 2.0, hd - porch, hd - 0.6, FOOT, base, "Stone")
    S.box("Walls", -pw / 2.0, pw / 2.0, hd - porch, hd - 0.6, shaft_top, shaft_top + 2.6, "Stone")
    S.gable("Walls", -pw / 2.0 - 0.6, pw / 2.0 + 0.6, hd - porch, hd - 0.3, shaft_top + 2.6, shaft_top + 8.2, "Stone", along="b")
    for k in range(8):
        a = -pw / 2.0 + 1.6 + (pw - 3.2) * k / 7.0
        S.drum("Columns", a, hd - 2.2, 0.95, 0.82, base + 0.5, shaft_top - 0.6, "Stone", 18)
        S.box("Columns", a - 1.2, a + 1.2, hd - 3.4, hd - 1.0, base, base + 0.5, "Stone")
        S.box("Columns", a - 1.15, a + 1.15, hd - 3.35, hd - 1.05, shaft_top - 0.6, shaft_top, "Stone")
    for k in range(5):
        S.box("Walls", -pw / 2.0, pw / 2.0, hd - 0.6, hd + 0.3 + 0.75 * k, FOOT, base - 0.36 * (k + 1), "Stone")
    for a in (-8.0, 0.0, 8.0):                                                                       # three doors behind the columns
        S.box("Signs", a - 1.7, a + 1.7, hd - porch - 0.1, hd - porch + 0.12, base, base + 5.6, "Rail")
        S.box("Glass", a - 1.7, a + 1.7, hd - porch - 0.1, hd - porch + 0.05, base + 6.4, base + 10.5, "Glass")
    # the wings' fronts, the ends and the back: a tall order of pilasters, windows in two tiers
    for wing in ((-hw, -pw / 2.0, -hd, hd - porch), (pw / 2.0, hw, -hd, hd - porch)):
        S.tall(wing, base + 1.4, eave - 3.0, ("front",), 4.6, 1.9, inset=0.6, pilaster=(1.0, 0.34, base, eave - 1.2), mid=base + 7.4)
    S.tall(body, base + 1.4, eave - 3.0, ("back", "a0", "a1"), 4.6, 1.9, inset=1.4, pilaster=(1.0, 0.34, base, eave - 1.2), mid=base + 7.4)
    S.punched((-hw + 3.0, hw - 3.0, -hd + 3.0, hd - porch - 3.0), eave - 0.4, 1, 3.8, bay=4.6, width=1.6, sill=1.1, head=2.9, inset=1.5)


def firestation(S):
    """An engine house with five red doors on a forecourt, an office wing beside it, a hose tower behind, and a low
    workshop across the drill yard."""
    # (a grows away from the street corner's far end: the engine house stands at the corner end of the site)
    eng = (11.0, 44.0, -14.5, 6.5)
    S.block(eng, FOOT, 8.2, "Brick")
    S.band(eng, 5.2, 5.75, 0.14, "Concrete", sides=("front",))
    S.band(eng, 8.3, 9.0, 0.2, "Concrete")
    for k in range(5):
        s = 2.4 + 6.2 * k
        S.wall("Signs", "front", eng, s, s + 4.4, -0.1, 0.09, 0.05, 4.8, "Red")
        for row in range(3):                                                            # a strip of glass in each door
            if row == 1:
                S.wall("Glass", "front", eng, s + 0.4, s + 4.0, -0.1, 0.13, 2.6, 3.4, "Glass")
    S.wall("Signs", "front", eng, 9.0, 24.0, -0.1, 0.1, 6.2, 7.6, "PaintWhite")
    S.punched(eng, 0.0, 1, 4.0, sides=("back", "a1"), bay=5.0, width=2.0, sill=4.6, head=6.6, inset=2.0)
    off = (-4.0, 11.0, -14.5, 6.5)
    S.block(off, FOOT, 11.8, "Brick")
    S.punched(off, 0.0, 3, 3.8, sides=("front", "back", "a0"), bay=3.6, width=1.6, sill=1.0, head=2.7, inset=1.3)
    S.band(off, 11.9, 12.6, 0.2, "Concrete")
    S.wall("Signs", "front", off, 5.9, 9.1, -0.1, 0.09, 0.05, 3.0, "Rail")
    tower = (-11.5, -5.5, -16.5, -10.5)
    S.block(tower, FOOT, 22.0, "Brick", parapet=0.6)
    for z in (15.0, 17.6, 20.2):
        for side in SIDES:
            S.wall("Signs", side, tower, 1.2, 4.8, -0.1, 0.06, z - 0.9, z + 0.9, "Rail")
    S.band(tower, 21.6, 22.6, 0.25, "Concrete")
    shop = (-43.0, -20.0, -16.5, -6.5)
    S.block(shop, FOOT, 5.2, "Brick")
    for s in (2.5, 12.5):
        S.wall("Signs", "front", shop, s, s + 8.0, -0.1, 0.08, 0.05, 4.0, "Steel")


def prison(S):
    """A walled compound with a watch tower at each corner and a gatehouse in the middle of its front; inside, two
    cell blocks side by side, joined by a hall, and an office by the gate."""
    w, d = S.p["size"]
    hw, hd = w / 2.0, d / 2.0
    deep = -10.0                                # the wall goes down past the bank the compound stands on
    yard = (-hw, hw, -hd, hd)
    for side in SIDES:
        S.wall("Walls", side, yard, 0.0, S.run(side, yard), -0.8, 0.0, deep, 6.5, "Concrete")
        S.wall("Trim", side, yard, -0.1, S.run(side, yard) + 0.1, -0.95, 0.15, 6.5, 6.85, "Concrete")
    for a in (-hw, hw):
        for b in (-hd, hd):
            S.box("Walls", a - 2.3, a + 2.3, b - 2.3, b + 2.3, deep, 9.6, "Concrete")
            cab = (a - 2.9, a + 2.9, b - 2.9, b + 2.9)
            S.box("Walls", cab[0], cab[1], cab[2], cab[3], 9.6, 12.4, "Concrete")
            for side in SIDES:
                S.wall("Glass", side, cab, 0.5, 5.3, -0.1, 0.05, 10.4, 11.9, "Glass")
            S.box("Roof", a - 3.5, a + 3.5, b - 3.5, b + 3.5, 12.4, 12.8, "Roof")
    gate = (-8.0, 8.0, hd - 6.0, hd + 2.5)
    S.block(gate, FOOT, 9.0, "Stone")
    S.wall("Signs", "front", gate, 5.4, 10.6, -0.1, 0.1, 0.05, 5.2, "Rail")
    S.punched(gate, 5.4, 1, 3.4, sides=("front",), bay=3.2, width=1.2, sill=0.9, head=2.4, inset=0.8)
    S.band(gate, 9.1, 9.8, 0.2, "Concrete")
    for a0, a1 in ((6.0, 17.0), (-17.0, -6.0)):
        cells = (a0, a1, -hd + 6.0, hd - 14.0)
        S.block(cells, FOOT, 13.2, "Stone", parapet=0.5)
        S.punched(cells, 0.0, 4, 3.3, sides=("a0", "a1"), bay=2.8, width=0.55, sill=1.5, head=2.7, inset=1.2)
        S.punched(cells, 0.0, 4, 3.3, sides=("front", "back"), bay=3.4, width=0.55, sill=1.5, head=2.7, inset=1.6)
    S.block((-6.0, 6.0, -8.0, 4.0), FOOT, 9.0, "Stone", parapet=0.5)
    office = (-18.0, -6.0, hd - 12.0, hd - 4.0)
    S.block(office, FOOT, 7.0, "Stone", parapet=0.5)
    S.punched(office, 0.0, 2, 3.3, sides=("back", "a1"), bay=3.2, width=1.3, sill=1.0, head=2.5, inset=1.0)
    for a, b in ((hw - 6.0, -hd + 5.0), (-hw + 6.0, hd - 16.0)):                         # two masts of lamps over the yards
        S.drum("Trim", a, b, 0.22, 0.16, 0.0, 16.0, "Steel", 8)
        S.box("Signs", a - 1.4, a + 1.4, b - 0.25, b + 0.25, 15.6, 16.4, "Light")


def powerplant(S):
    """A turbine hall with a band of glass under its eaves, a boiler house twice as high beside it, two chimneys
    with red and white bands at the top, a row of three tanks, and a switchyard by the gate."""
    hall = (-32.0, -6.0, -42.0, 22.0)
    S.block(hall, FOOT, 20.0, "Plaster", parapet=0.6)
    S.band(hall, 0.0, 3.6, 0.2, "Concrete")
    for side in SIDES:
        n = S.run(side, hall)
        S.wall("Glass", side, hall, 2.0, n - 2.0, -0.15, 0.05, 13.6, 17.6, "Glass")
        count = max(1, int(round((n - 4.0) / 6.4)))
        for j in range(count + 1):
            s = 2.0 + (n - 4.0) * j / count
            S.wall("Trim", side, hall, s - 0.3, s + 0.3, -0.1, 0.3, 0.0, 20.4, "Concrete")
    S.wall("Signs", "front", hall, 9.0, 17.0, -0.1, 0.1, 0.05, 6.5, "Steel")
    boiler = (-6.0, 22.0, -30.0, -2.0)
    S.block(boiler, FOOT, 38.0, "Plaster", parapet=0.8)
    S.band(boiler, 0.0, 3.6, 0.2, "Concrete")
    for side in SIDES:
        n = S.run(side, boiler)
        count = max(1, int(round(n / 4.6)))
        for j in range(count + 1):
            S.wall("Trim", side, boiler, n * j / count - 0.25, n * j / count + 0.25, -0.1, 0.35, 3.6, 38.4, "Concrete")
        S.wall("Glass", side, boiler, 2.0, n - 2.0, -0.15, 0.05, 30.0, 33.0, "Glass")
    S.box("Roof", 2.0, 14.0, -24.0, -8.0, 38.0, 42.0, "Steel")
    for a in (4.0, 16.0):                                                               # the chimneys, east of the boilers
        b = -41.0
        S.drum("Columns", a, b, 3.5, 2.3, FOOT, 76.0, "Concrete", 24)
        for k, slot in enumerate(("Red", "PaintWhite", "Red", "PaintWhite")):
            z0 = 60.0 + 4.0 * k
            r0 = 3.5 - 1.2 * (z0 + 1.5) / 77.5 + 0.06
            r1 = 3.5 - 1.2 * (z0 + 5.5) / 77.5 + 0.06
            S.drum("Signs", a, b, r0, r1, z0, z0 + 4.0, slot, 24)
        S.box("Walls", a - 1.6, a + 1.6, b + 2.5, -30.0, 6.0, 9.5, "Steel")             # the flue from the boiler house
    for b in (34.0, 12.0, -10.0):                                                       # the tanks
        S.drum("Columns", 33.0, b, 8.5, 8.5, FOOT, 11.0, "PaintWhite", 28)
        S.drum("Roof", 33.0, b, 8.7, 0.6, 11.0, 13.0, "Steel", 28)
        S.arc("Trim", 33.0, b, 8.55, 0.0, 360.0, 0.2, 5.4, 5.7, "Steel", per_turn=28)
    S.box("Walls", 22.0, 26.0, -6.0, 38.0, 4.0, 5.2, "Steel")                           # the pipe bridge along them
    for b in (-4.0, 16.0, 36.0):
        S.box("Trim", 23.5, 24.5, b - 0.3, b + 0.3, FOOT, 4.0, "Steel")
    # the switchyard: three transformers behind their gantries
    for k in range(3):
        a = -28.0 + 9.0 * k
        S.box("Walls", a - 2.2, a + 2.2, 31.0, 35.5, FOOT, 3.6, "Steel")
        S.box("Trim", a - 2.8, a + 2.8, 30.6, 31.0, 0.6, 3.0, "Rail")
        for da in (-1.2, 0.0, 1.2):
            S.drum("Trim", a + da, 33.2, 0.18, 0.12, 3.6, 5.6, "PaintWhite", 8)
    for b in (40.0, 47.0):
        for a in (-33.0, -19.0, -5.0):
            S.box("Trim", a - 0.25, a + 0.25, b - 0.25, b + 0.25, FOOT, 10.0, "Steel")
        S.box("Trim", -33.5, -4.5, b - 0.3, b + 0.3, 9.4, 10.0, "Steel")
        for a in (-28.0, -19.0, -10.0):
            S.drum("Trim", a, b, 0.14, 0.1, 7.6, 9.4, "PaintWhite", 8)
    lodge = (4.0, 12.0, 44.0, 50.0)
    S.block(lodge, FOOT, 3.6, "Plaster", parapet=0.4)
    S.wall("Glass", "front", lodge, 1.0, 7.0, -0.1, 0.05, 1.0, 2.6, "Glass")
    S.wall("Glass", "a0", lodge, 1.0, 5.0, -0.1, 0.05, 1.0, 2.6, "Glass")


def airfield(S):
    """An air terminal on an apron: a two-storey terminal with a glass front, a control tower beside it, and a
    hangar at the apron's other end (the helicopter pads between them are painted by the sector)."""
    term = (24.0, 54.0, 1.0, 14.0)
    S.block(term, FOOT, 8.4, "Plaster", parapet=0.7)
    S.ribbons(term, 0.0, 2, 4.2, sides=("front", "back", "a1"), sill=0.5, head=3.4, fin=3.0)
    S.band(term, 8.5, 9.2, 0.25, "Concrete")
    S.box("Trim", 30.0, 48.0, 14.0, 16.8, 3.6, 4.0, "Concrete")                         # a canopy on the landward side
    for a in (31.0, 39.0, 47.0):
        S.drum("Trim", a, 16.3, 0.22, 0.22, FOOT, 3.6, "Steel", 10)
    tower = (16.5, 22.5, 7.0, 13.0)
    S.box("Walls", tower[0], tower[1], tower[2], tower[3], FOOT, 23.0, "Concrete", top=(17.1, 21.9, 7.6, 12.4))
    ca, cb = 19.5, 10.0
    S.drum("Walls", ca, cb, 4.2, 5.6, 23.0, 24.6, "Concrete", 8)
    S.drum("Glass", ca, cb, 5.2, 5.9, 24.6, 27.4, "Glass", 8)
    S.drum("Roof", ca, cb, 6.4, 6.0, 27.4, 27.9, "Roof", 8)
    S.drum("Trim", ca, cb, 0.12, 0.06, 27.9, 33.0, "Steel", 6)
    S.box("Signs", ca - 0.5, ca + 0.5, cb - 0.5, cb + 0.5, 28.4, 29.0, "Red")
    hang = (-54.0, -26.0, -15.0, 11.0)
    S.box("Walls", hang[0], hang[1], hang[2], hang[3], FOOT, 9.0, "Steel")
    S.gable("Roof", hang[0] - 0.4, hang[1] + 0.4, hang[2] - 0.4, hang[3] + 0.4, 9.0, 13.2, "Roof", along="a")
    S.wall("Signs", "a1", hang, 3.0, 23.0, -0.1, 0.12, 0.05, 8.0, "Rail")              # the doors, towards the pads
    S.wall("Signs", "a1", hang, 12.85, 13.15, -0.1, 0.16, 0.05, 8.0, "Steel")
    S.band(hang, 0.0, 1.2, 0.12, "Concrete", sides=("front", "back", "a0"))
    S.drum("Trim", -4.0, 14.5, 0.12, 0.08, 0.0, 7.0, "Steel", 6)                        # the wind sock's mast
    S.box("Signs", -4.0, -1.8, 14.3, 14.7, 6.2, 6.9, "Red", top=(-4.0, -1.8, 14.4, 14.6))


KINDS = {"hospital": hospital, "bank": bank, "courthouse": courthouse, "firestation": firestation, "prison": prison,
         "powerplant": powerplant, "airfield": airfield}


def build_object(name, part, origin):
    """One Blender object out of a site's part: every face turned away from the middle of its own piece."""
    bm = bmesh.new()
    verts = [bm.verts.new(p) for p in part["v"]]
    bm.verts.ensure_lookup_table()
    for face, slot, inside in zip(part["f"], part["slot"], part["inside"]):
        pts = [part["v"][i] for i in face]
        n = [0.0, 0.0, 0.0]
        for k in range(len(pts)):                                                       # Newell's normal
            p, q = pts[k], pts[(k + 1) % len(pts)]
            n[0] += (p[1] - q[1]) * (p[2] + q[2])
            n[1] += (p[2] - q[2]) * (p[0] + q[0])
            n[2] += (p[0] - q[0]) * (p[1] + q[1])
        c = [sum(p[i] for p in pts) / len(pts) for i in range(3)]
        outwards = sum(n[i] * (c[i] - inside[i]) for i in range(3))
        if abs(n[0]) + abs(n[1]) + abs(n[2]) < 1e-9:
            continue
        order = face if outwards >= 0.0 else face[::-1]
        try:
            f = bm.faces.new([verts[i] for i in order])
        except ValueError:
            continue
        f.material_index = SLOTS.index(slot)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
    bm.normal_update()
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        n = f.normal
        flat = abs(n.z) > 0.6
        tx, ty = -n.y, n.x
        size = math.hypot(tx, ty) or 1.0
        tx, ty = tx / size, ty / size
        for loop in f.loops:
            co = loop.vert.co
            x, y = co.x - origin[0], co.y - origin[1]
            loop[uv].uv = (x / UV_M, y / UV_M) if flat else ((x * tx + y * ty) / UV_M, co.z / UV_M)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for slot in SLOTS:
        mesh.materials.append(bpy.data.materials.get(slot) or bpy.data.materials.new(slot))
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def make(name):
    S = Site(name)
    KINDS[S.p["kind"]](S)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    out_dir = os.path.join(DATA, "structures", name)
    os.makedirs(out_dir, exist_ok=True)
    objects = [build_object("%s_%s" % (name, label), part, (S.cx, S.cy)) for label, part in sorted(S.parts.items()) if part["f"]]
    faces = solidkit.export_objects(objects, os.path.join(out_dir, name + ".glb"), sharp_deg=40.0)
    open(os.path.join(out_dir, "nanite"), "w").close()
    w, d = S.p["size"]
    reach = max(w, d)
    top = S.top

    def cm(a, b, z):
        x, y, zz = S.pt(a, b, z)
        return "%d,%d,%d" % (round(x * 100), round(-y * 100), round(zz * 100))

    # review cameras: on the street in front, beyond each end of the front, at eye height; high over that street; and
    # straight down. (Cameras set by the site's size alone stood inside the towers next door, 2026-11-18.) A place with
    # no street in front (the air terminal, among the backs of two rows) has them on its own apron.
    st = S.p.get("street", 12.0)
    look_z = 0.35 * min(top, 40.0)
    if st > 0.0:
        views = [("street_l", (-(w / 2.0 + 12.0), d / 2.0 + st, 2.6), (w / 5.0, d / 2.0 - 3.0, look_z)),
                 ("street_r", (w / 2.0 + 12.0, d / 2.0 + st, 2.6), (-w / 5.0, d / 2.0 - 3.0, look_z)),
                 ("high", (0.1 * w, d / 2.0 + st, 0.75 * max(w, 50.0) + 0.4 * min(top, 40.0)), (0.0, 0.0, 0.25 * min(top, 40.0)))]
    else:
        views = [("apron_l", (-20.0, -10.0, 2.6), (36.0, 8.0, 6.0)), ("apron_r", (30.0, -12.0, 2.6), (-40.0, -2.0, 5.0)),
                 ("high", (0.0, d / 2.0 + 17.0, 62.0), (0.0, -2.0, 0.0))]
    views.append(("top", (0.0, -0.1, 1.5 * reach + top), (0.0, 0.0, 0.0)))
    with open(os.path.join(out_dir, "views.txt"), "w") as f:
        for label, cam, look in views:
            f.write("%s_%s;%s;%s\n" % (name, label, cm(*cam), cm(*look)))
    info = {"name": name, "kind": S.p["kind"], "sector": S.p["sector"], "title": S.p.get("title", ""), "meshes": len(objects),
            "faces": faces, "top_m": round(top, 1), "ground_z": round(S.z0, 2)}
    with open(os.path.join(out_dir, "place.json"), "w") as f:
        json.dump(info, f, indent=1)
    print("PLACE %s (%s, %s): %d meshes, %d faces, %.1f m high" % (name, S.p["kind"], S.p["sector"], len(objects), faces, top))


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    names = list(sectors.PLACES) if not args or args == ["all"] else args
    for name in names:
        make(name)


if __name__ == "__main__":
    main()
