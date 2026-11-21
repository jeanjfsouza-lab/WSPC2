"""Zoning of the Bay city after the campaign model: which kind of architecture each sector gets.

  python -P Tools/bay/plan_zones.py            (writes the table and the plan)
  python -P Tools/bay/plan_zones.py --dry      (prints and draws, writes no table)

The campaign model (ASSETS TO USE/bay_city_3d) is the reference for the whole city (user, 2026-11-21: "o mais fiel
possivel"). It has no zone labels: its blocks are street facades only, with no roofs. Two things in it say what a
neighbourhood is:
  facades    how tall the street walls stand above their street (the model's UrbanBlocks mesh drawn top-down on a
             4 m grid; the street level is the lowest top within 36 m). Per sector: the 90th percentile of the
             wall heights, and how much of the sector the model covers at all
  operations the district each of the twenty operations names ("Zona Industrial", "Bairro Oriental", ...), placed
             where its key markers (start, objective, end, suspect start, checkpoints) crowd most, in Bay metres
             (Saved/Bay/campaign/operations.json, plan_campaign.py)
The rules, in order (first match wins):
  1. sectors with a role of their own keep their kind: downtown, shoulder, midtown, hilltop and estate districts,
     sectors with landmarks or ranks, and those named in KEEP (roads, the training ground, the plant, the airfield)
  2. named areas: a sector within an area's radius of the centre of that district's markers takes the area's kind
     (AREAS); the north coast is the model's harbour (prefixes in HARBOUR)
  3. by facade height: no facades -> unchanged; p90 < 10 m -> suburb; < 18 m -> victorian; otherwise unchanged
     (the old walk-up neighbourhood, "midrise", is what the model's 20-35 m streets already are)

Input:  ASSETS TO USE/bay_city_3d/dados/malha_urbana.glb; Saved/Bay/campaign/operations.json; Tools/bay/sectors.py
Output: Tools/bay/zoning.py          ZONES = {sector: kind}, read by sectors.py (only sectors whose kind changes)
        Saved/Bay/zones.json         per sector: kind before and after, the measures and the reason
        Saved/Bay/zones.png          plan of the city coloured by kind
"""
import json
import math
import os
import struct
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, PROJECT
import sectors as S

MODEL = os.path.join(PROJECT, "ASSETS TO USE", "bay_city_3d", "dados", "malha_urbana.glb")
TABLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zoning.py")
SCALE, SHIFT_X, SHIFT_Y = 0.970, 856.0, -292.0      # model to Bay frame (plan_campaign.py)
CELL = 4.0
STREET_WINDOW = 19                                    # cells: the lowest top within ~36 m is the street
WALL_MIN_M = 2.0
FEW_WALLS = 60                                        # fewer facade cells than this: the model has nothing here
SUBURB_BELOW_M = 10.0
VICTORIAN_BELOW_M = 18.0
FIXED = ("downtown", "shoulder", "midtown", "hilltop", "estate")
KEEP = ("PF1", "PT1", "NH3", "SE1", "SE2", "SE3", "TR1", "TR2", "FW1", "FW2", "FW4", "FW5", "CB1", "CB2", "CB3", "FE1")
HARBOUR = ("FN", "DN", "CN", "NH", "PN", "PP")        # the model's "Zona Portuaria Norte" (viewer preset "harbor")
# district named by the operations -> (kind, radius in metres around the centre of its key markers)
AREAS = {
    "Zona Industrial": ("industrial", 520.0),
    "Bairro Oriental": ("chinatown", 330.0),
    "Bairro Residencial": ("victorian", 420.0),
    "Praça Comercial": ("midtown", 650.0),
}
KINDS = {   # colour on the plan
    "downtown": (200, 40, 60), "shoulder": (235, 110, 70), "midtown": (240, 170, 60), "midrise": (90, 140, 210),
    "hilltop": (150, 110, 200), "port": (70, 170, 140), "estate": (210, 90, 170), "suburb": (120, 200, 110),
    "victorian": (230, 200, 120), "industrial": (130, 130, 140), "chinatown": (220, 60, 160),
}
CROWD_M = 350.0                                       # markers this close count as one place
KEY_ROLES = {"start_player": 3, "objective": 3, "end": 3, "start_suspect": 2, "checkpoint": 1}


def read_glb(path):
    with open(path, "rb") as f:
        f.read(12)
        n, _ = struct.unpack("<II", f.read(8))
        j = json.loads(f.read(n))
        bn, _ = struct.unpack("<II", f.read(8))
        blob = f.read(bn)
    types = {5126: np.float32, 5125: np.uint32, 5123: np.uint16}
    comps = {"SCALAR": 1, "VEC3": 3}

    def acc(i):
        a = j["accessors"][i]
        bv = j["bufferViews"][a["bufferView"]]
        nc = comps[a["type"]]
        arr = np.frombuffer(blob, dtype=types[a["componentType"]], count=a["count"] * nc,
                            offset=bv.get("byteOffset", 0) + a.get("byteOffset", 0))
        return arr.reshape(a["count"], nc) if nc > 1 else arr
    return j, acc


def facade_heights(x0, y1, w, h):
    """Top of the model's urban geometry per cell (Bay metres, NaN where it has none) and wall height above the street."""
    j, acc = read_glb(MODEL)
    mesh = next(m for m in j["meshes"] if m["name"] == "UrbanBlocks") if any(m.get("name") == "UrbanBlocks" for m in j["meshes"]) else j["meshes"][0]
    pts, val = [], []
    for p in mesh["primitives"]:
        pos = acc(p["attributes"]["POSITION"]).astype(np.float64)
        tri = acc(p["indices"]).reshape(-1, 3)
        bx, by, bz = SCALE * pos[:, 0] + SHIFT_X, -SCALE * pos[:, 2] + SHIFT_Y, SCALE * pos[:, 1]
        pts.append(np.stack([(bx - x0) / CELL, (y1 - by) / CELL], -1)[tri])
        val.append(bz[tri].max(1))
    pts, val = np.concatenate(pts), np.concatenate(val)
    top = np.full((h, w), -9999.0, np.float32)
    for k in np.argsort(val):                       # higher triangles drawn last
        cv2.fillConvexPoly(top, np.round(pts[k] * 4).astype(np.int32), float(val[k]), lineType=cv2.LINE_8, shift=2)
    valid = top > -9000
    street = cv2.erode(np.where(valid, top, 1e6).astype(np.float32),
                       cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (STREET_WINDOW, STREET_WINDOW)))
    wall = np.where(valid & (street < 1e5), top - street, np.nan)
    return valid, wall


def district_centres():
    path = os.path.join(DATA, "campaign", "operations.json")
    with open(path, encoding="utf-8") as f:
        ops = json.load(f)["operations"]
    marks = {}
    for op in ops.values():
        for m in op.get("markers", []):
            w = KEY_ROLES.get(m.get("role"), 0)
            if w and "x" in m:
                marks.setdefault(op["district"], []).append((m["x"], m["y"], w))
    # An operation ranges over the city (Op 09 starts in the north and ends in the east): its district is where its
    # key markers crowd, not their mean. Mean shift from every marker; the densest end point wins.
    centres = {}
    for k, pts in marks.items():
        p = np.array(pts, np.float64)
        best = None
        for x, y, _ in pts:
            c = np.array([x, y])
            for _ in range(20):
                near = np.hypot(p[:, 0] - c[0], p[:, 1] - c[1]) <= CROWD_M
                c = (p[near, :2] * p[near, 2:3]).sum(0) / p[near, 2].sum()
            weight = p[np.hypot(p[:, 0] - c[0], p[:, 1] - c[1]) <= CROWD_M, 2].sum()
            if best is None or weight > best[0]:
                best = (weight, c)
        centres[k] = (float(best[1][0]), float(best[1][1]))
    return centres


def main():
    dry = "--dry" in sys.argv
    rings = {n: np.array([p[:2] for p in S.outline(n)], np.float64) for n in S.SECTORS}
    allp = np.concatenate(list(rings.values()))
    x0, y0 = float(allp[:, 0].min()) - 100, float(allp[:, 1].min()) - 100
    x1, y1 = float(allp[:, 0].max()) + 100, float(allp[:, 1].max()) + 100
    w, h = int((x1 - x0) / CELL) + 1, int((y1 - y0) / CELL) + 1
    valid, wall = facade_heights(x0, y1, w, h)
    centres = district_centres()
    for k in AREAS:
        if k not in centres:
            print("ZONES: no operation names %s" % k)

    def px(ring):
        return np.round(np.stack([(ring[:, 0] - x0) / CELL, (y1 - ring[:, 1]) / CELL], -1)).astype(np.int32)

    records, zones = {}, {}
    for name, sec in S.SECTORS.items():
        ring = rings[name]
        mask = np.zeros((h, w), np.uint8)
        cv2.fillPoly(mask, [px(ring)], 1)
        m = mask.astype(bool)
        walls = wall[m & valid]
        walls = walls[walls > WALL_MIN_M]
        p90 = float(np.percentile(walls, 90)) if len(walls) >= FEW_WALLS else None
        cover = float((m & valid).sum()) / max(1, int(m.sum()))
        cx, cy = ring.mean(0)
        old = sec.get("drawn_district", sec.get("district"))       # the kind before any zoning
        kind, why = old, "facades %s" % ("none" if p90 is None else "%.0f m" % p90)
        if old in FIXED or name in KEEP or sec.get("landmarks") or sec.get("ranks"):
            why = "own role"
        else:
            named = [(math.hypot(cx - ax, cy - ay) / r, k, z) for k, (z, r) in AREAS.items()
                     for (ax, ay) in [centres.get(k, (1e9, 1e9))] if math.hypot(cx - ax, cy - ay) <= r]
            if named:
                _, area, kind = min(named)
                why = "area %s" % area
            elif name.rstrip("0123456789") in HARBOUR and p90 is not None:
                kind, why = "industrial", "harbour"
            elif p90 is not None and p90 < SUBURB_BELOW_M:
                kind = "suburb"
            elif p90 is not None and p90 < VICTORIAN_BELOW_M:
                kind = "victorian"
        records[name] = {"before": old, "after": kind, "why": why, "p90": None if p90 is None else round(p90, 1),
                         "cover": round(cover, 2), "centre": [round(cx, 1), round(cy, 1)]}
        if kind != old:
            zones[name] = kind

    counts = {}
    for r in records.values():
        counts[r["after"]] = counts.get(r["after"], 0) + 1
    print("ZONES: %d sectors change kind; kinds now %s" % (len(zones), dict(sorted(counts.items()))))
    print("ZONES: district centres %s" % {k: [round(v) for v in c] for k, c in centres.items() if k in AREAS})
    with open(os.path.join(DATA, "zones.json"), "w", encoding="utf-8") as f:
        json.dump(records, f, indent=1, ensure_ascii=False)
    draw(rings, records, centres, x0, y1)
    if dry:
        return
    lines = ['"""Kind of architecture per sector, after the campaign model. Written by plan_zones.py: do not edit by hand',
             '(change the rules there and run it again). sectors.py applies it over each sector\'s "district"."""', "",
             "ZONES = {"]
    for name in sorted(zones, key=lambda n: (n.rstrip("0123456789"), int("0" + "".join(c for c in n if c.isdigit())))):
        lines.append('    "%s": "%s",      # %s' % (name, zones[name], records[name]["why"]))
    lines.append("}")
    with open(TABLE, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("ZONES: wrote %s" % TABLE)


def draw(rings, records, centres, x0, y1):
    from PIL import Image, ImageDraw, ImageFont
    s = 0.3
    allp = np.concatenate(list(rings.values()))
    W, H = int((allp[:, 0].max() - x0 + 100) * s), int((y1 - allp[:, 1].min() + 100) * s)
    img = Image.new("RGB", (W, H + 260), (245, 243, 236))
    d = ImageDraw.Draw(img)
    try:
        f, fb = ImageFont.truetype("arial.ttf", 14), ImageFont.truetype("arial.ttf", 24)
    except OSError:
        f = fb = ImageFont.load_default()
    P = lambda x, y: ((x - x0) * s, (y1 - y) * s)
    for n, ring in rings.items():
        r = records[n]
        d.polygon([P(*p) for p in ring], fill=KINDS.get(r["after"], (160, 160, 160)),
                  outline=(0, 0, 0) if r["after"] != r["before"] else (255, 255, 255))
    for n, ring in rings.items():
        d.text(P(*ring.mean(0)), n, fill=(20, 20, 20), font=f, anchor="mm")
    for k, (cx, cy) in centres.items():
        if k in AREAS:
            X, Y = P(cx, cy)
            rr = AREAS[k][1] * s
            d.ellipse([X - rr, Y - rr, X + rr, Y + rr], outline=(0, 0, 0), width=2)
            d.text((X, Y - rr - 14), k.encode("ascii", "replace").decode(), fill=(0, 0, 0), font=fb, anchor="mm")
    y = H + 10
    for i, (k, c) in enumerate(KINDS.items()):
        X = 20 + (i % 4) * 330
        Y = y + (i // 4) * 40
        d.rectangle([X, Y, X + 30, Y + 26], fill=c)
        d.text((X + 40, Y + 13), "%s (%d)" % (k, sum(1 for r in records.values() if r["after"] == k)), fill=(0, 0, 0), font=fb, anchor="lm")
    img.save(os.path.join(DATA, "zones.png"))


if __name__ == "__main__":
    main()
