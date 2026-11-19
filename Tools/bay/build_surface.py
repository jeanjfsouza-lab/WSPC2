"""Shapes the whole map's ground to the road network and writes it as an Unreal landscape.

  python -P Tools/bay/build_surface.py

Input:  Saved/Bay/terrain_base.npz (natural ground, water), Saved/Bay/network.json, Saved/Bay/masks.npz,
        Saved/Bay/sectors/*/ground.npz (the built sectors' meshes)
Output: Saved/Bay/landscape.r16     16-bit heightmap (Unreal's encoding, ScaleZ 100), 2 m between vertices
        Saved/Bay/layer_<name>.raw  8-bit paint weight per vertex, one file per layer (they sum to 255)
        Saved/Bay/paint_map.png     the natural layers as one picture over the whole landscape (red grass, green dry
                                    grass, blue bare earth, alpha sand; what is left is rock), PAINT_MAP_PX square:
                                    the sectors' own natural ground (their "wild") is painted from it, by world position
        Saved/Bay/landscape.json    size, placement, layers, the paint map; read by build_bay.py (stages "ground", "materials")
        Saved/Bay/surface.png       shaded relief with the roads, for checking
        Saved/Bay/paint.png         the paint layers as seen from afar, for checking

What the landscape is for. Streets, sidewalks and block ground are meshes built sector by sector; the
landscape is what lies around and under them: hills, parks, shores, the sea bed, and the ground of sectors
not built yet. So:
  * along every surface road the ground is graded to the road's own height, then eased into the natural
    ground over EASE_M, never steeper than the hillside it meets;
  * inside the city the ground between streets is carried by the streets around it;
  * under a built sector the landscape lies SINK_M below that sector's mesh, so it can never show through;
    where the sector drew its own shore, that shore replaces the map's, and the landscape drops to the sea
    bed behind the sea wall;
  * at a sector's own side with no sector beyond it, the landscape outside carries on from the mesh's edge and
    eases into its own height over SEAM_M: no step at the side, neither a bank against the sector nor the mesh's
    underside showing (not along a sector's retaining "walls", not into water, not onto a road);
  * sectors.COUNTRY: ground outside every sector that is country whatever the drawing's building marks say (the
    shore there is a beach, not a quay);
  * the sea bed deepens away from the shore; beyond the map's frame the land rises into hills or falls
    into the sea, as in the first city.
"""
import glob
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (CURB_M, M_PER_PX, PX_PER_M, ROAD_MIN_Z, SECTIONS, X_LEFT, Y_TOP, DATA, data_path, fbm, fill_holes, gauss,
                    load_json, nconv, save_json, to_pixel)
import sectors as sector_data
from sectors import SECTORS

QUAD_M = 2.0
COMPONENT_QUADS = 255
MARGIN_M = 1200.0
LAYERS = ["Grass", "Dirt", "Sand", "Rock", "Asphalt", "Pavement", "DryGrass"]
# what each layer looks like from afar (linear colour; build_bay.LAYER_SETUP's far colours), for paint.png
PREVIEW = {"Grass": (0.105, 0.107, 0.023), "Dirt": (0.262, 0.198, 0.102), "Sand": (0.290, 0.232, 0.132),
           "Rock": (0.195, 0.165, 0.107), "Asphalt": (0.068, 0.068, 0.066), "Pavement": (0.250, 0.229, 0.194),
           "DryGrass": (0.190, 0.145, 0.060)}
SINK_M = 0.45               # landscape below road and sector meshes
EASE_M = 45.0               # distance over which graded ground returns to natural ground
SEA_DEPTH_M = 12.0
RIVER_DEPTH_M = 7.0
SEAWALL_BED_M = 4.0         # depth at the foot of a built sea wall (the wall's face reaches -3 m)
QUAY_M = ROAD_MIN_Z         # top of a quay
SEAM_M = 36.0               # beyond a sector's open side the landscape returns to its own height over this distance
SEAM_DROP_M = 0.12          # ...starting this far below the mesh's edge (natural ground hangs an apron there)
WALL_REACH_M = 3.0          # ...but not within this distance of a sector's retaining "walls": the step there is built
COUNTRY_RIM_M = 30.0        # no town ground (the paint's greener grass) within this distance of a sector's natural ground
WILD_RIM_M = 4.0            # within this distance of ground that no sector covers the landscape stays WILD_SINK_M under a
WILD_DEEP_M = 8.0           # sector's natural ground; further in it goes down, 1 in 2, to this far below it
WILD_SINK_M = 0.12          # the landscape under a sector's natural ground lies this far below it, not SINK_M: the two
                            # look alike, so nothing shows where one cuts through the other, and at the sector's side
                            # the landscape then leaves from the mesh's own height. (At SINK_M it left from 0.6 m
                            # lower: a gutter ran along the side, the mesh's skirt standing in it like a kerb.)
PAINT_MAP_PX = 4096
NATURAL_LAYERS = ["Grass", "DryGrass", "Dirt", "Sand", "Rock"]    # the first four are the paint map's channels


def main():
    base = np.load(data_path("terrain_base.npz"))
    ground, water = base["ground"].astype(np.float32), base["water"]
    masks = np.load(data_path("masks.npz"))
    h, w = ground.shape
    net = load_json("network.json")

    # ---- roads on the map's grid: where they run, how wide, and their height
    road_z = np.zeros((h, w), np.float32)
    centre = np.zeros((h, w), np.uint8)
    half = np.zeros((h, w), np.float32)
    for e in net["edges"]:
        if e["level"] != 0 or e["cls"] == "tunnel" or e["wet"] > 0.5:
            continue
        sec = SECTIONS[e["cls"]]
        hw = sec["carriage"] / 2 + sec["sidewalk"]
        pts = np.array(e["pts"])
        u, v = to_pixel(pts[:, 0], pts[:, 1])
        for i in range(len(pts) - 1):
            # a road's profile has a point every 8 m: drawn in pieces about one pixel long, each at its own
            # height, so a street that climbs is a ramp. Drawn whole at its mean height it was a flight of
            # steps, 1.4 m each on a 17% street
            pieces = max(1, int(np.ceil(np.hypot(u[i + 1] - u[i], v[i + 1] - v[i]))))
            for k in range(pieces):
                t0, t1 = k / pieces, (k + 1) / pieces
                a = (int(round(u[i] + (u[i + 1] - u[i]) * t0)), int(round(v[i] + (v[i + 1] - v[i]) * t0)))
                b = (int(round(u[i] + (u[i + 1] - u[i]) * t1)), int(round(v[i] + (v[i + 1] - v[i]) * t1)))
                cv2.line(centre, a, b, 1, 1)
                cv2.line(road_z, a, b, float(pts[i][2] + (pts[i + 1][2] - pts[i][2]) * (t0 + t1) / 2), 1)
                cv2.line(half, a, b, float(hw), 1)
    # nearest centre-line pixel for every pixel: its height and half-width
    dist, labels = cv2.distanceTransformWithLabels((1 - centre).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(centre)
    index = np.zeros(labels.max() + 1, np.int64)
    index[labels[ys, xs]] = np.arange(len(ys))
    near = index[labels]
    z_near = road_z[ys, xs][near]
    hw_near = half[ys, xs][near]
    dist_m = dist * M_PER_PX
    on_road = dist_m <= hw_near

    # ---- the city's ground: carried by the streets around it
    built = masks["building"] | on_road
    urban = cv2.dilate(built.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))).astype(bool) & ~water
    urban = cv2.morphologyEx(urban.astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (45, 45))).astype(bool) & ~water
    # ...but not where sectors.py says the ground is country (the drawing has buildings there that stand in a sector
    # nearby, on streets of their own: what lies beyond that sector is hillside and beach)
    for ring in getattr(sector_data, "COUNTRY", []):
        ru, rv = to_pixel(np.array([p[0] for p in ring], dtype=np.float64), np.array([p[1] for p in ring], dtype=np.float64))
        country_mask = np.zeros((h, w), np.uint8)
        cv2.fillPoly(country_mask, [np.stack([ru, rv], axis=1).round().astype(np.int32)], 1)
        urban &= country_mask == 0
    # ...nor in a sector with natural ground (its "wild"), nor within COUNTRY_RIM_M of it: what is not street, sidewalk
    # or garden there is country. The drawing marks a village as a block of town, and the town's ground is painted
    # greener: a sector's natural ground came out green up to the straight edge of that block, golden beyond it (FN6,
    # SE2, 2026-11-18)
    country_mask = np.zeros((h, w), np.uint8)
    for name, spec in SECTORS.items():
        wild = spec.get("wild")
        for ring in ([sector_data.outline(name)] if wild is True else (wild or [])):
            ru, rv = to_pixel(np.array([p[0] for p in ring], dtype=np.float64), np.array([p[1] for p in ring], dtype=np.float64))
            cv2.fillPoly(country_mask, [np.stack([ru, rv], axis=1).round().astype(np.int32)], 1)
    if country_mask.any():
        rim = 2 * int(round(COUNTRY_RIM_M * PX_PER_M)) + 1
        urban &= cv2.dilate(country_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (rim, rim))) == 0
    # ---- everywhere else: natural ground eased into the roads that cross it
    t = np.clip((dist_m - hw_near - 2.0) / EASE_M, 0.0, 1.0)
    ease = t * t * (3 - 2 * t)
    country = z_near + (ground - z_near) * ease

    block_z, support = nconv(z_near, on_road, 24.0)
    # far from every street (support under 1e-3, some 80 m and more) the streets carry nothing: there the
    # city's ground is the natural ground. It used to take the height of the nearest street, wherever that
    # was, and a valley cleared of its streets stood as a flat shelf at the height of a hill street 150 m away
    far = np.clip(np.log10(np.maximum(support, 1e-9)) + 4.0, 0.0, 1.0)
    block_z = np.where(support > 1e-3, block_z, np.where(support > 1e-9, block_z, country) * far + country * (1 - far))
    urban_soft = np.clip(gauss(urban, 10.0) * 1.5 - 0.25, 0.0, 1.0)
    height = country * (1 - urban_soft) + block_z * urban_soft
    # where no sector is built yet the landscape is the street itself, at the street's exact height
    height = np.where(on_road, z_near, height)

    # ---- built sectors: the landscape lies under their meshes, and their shore is the shore
    stamped = np.zeros((h, w), bool)
    behind_wall = np.zeros((h, w), bool)
    designed_water = np.zeros((h, w), bool)
    wx_px = X_LEFT + (np.arange(w) + 0.5) * M_PER_PX
    wy_px = Y_TOP - (np.arange(h) + 0.5) * M_PER_PX
    def ring_mask(ring):
        ru, rv = to_pixel(np.array([p[0] for p in ring], dtype=np.float64), np.array([p[1] for p in ring], dtype=np.float64))
        mask = np.zeros((h, w), np.uint8)
        cv2.fillPoly(mask, [np.stack([ru, rv], axis=1).round().astype(np.int32)], 1)
        return mask.astype(bool)

    wet_by_design = np.zeros((h, w), bool)          # where some sector says: water, whatever the map shows
    wild_px = np.zeros((h, w), bool)                # under a sector's natural ground
    wild_own = np.zeros((h, w), bool)               # ...where that natural ground is what stands there in the end
    mesh_top = np.zeros((h, w), np.float32)         # ...and that ground's own height there
    seen = np.full((h, w), np.nan, np.float32)      # the surface one sees where a sector with natural ground stands
    edge_top = np.full((h, w), np.nan, np.float32)  # the surface's height along every sector's edge
    walled = np.zeros((h, w), np.uint8)             # along the sectors' retaining walls
    for spec in SECTORS.values():
        for seg in spec.get("walls", []):
            su, sv = to_pixel(np.array([p[0] for p in seg], dtype=np.float64), np.array([p[1] for p in seg], dtype=np.float64))
            cv2.polylines(walled, [np.stack([su, sv], axis=1).round().astype(np.int32)], False, 1,
                          max(3, 2 * int(round(WALL_REACH_M * PX_PER_M)) + 1))
    walled = walled.astype(bool)
    for path in sorted(glob.glob(os.path.join(DATA, "sectors", "*", "ground.npz"))):
        folder = os.path.dirname(path)
        name = os.path.basename(folder)
        d = np.load(path)
        pts, z, tris = d["pts"], d["z"], d["tris"]
        west, east, south, north = d["box"]
        u, v = to_pixel(pts[:, 0], pts[:, 1])
        layer = np.full((h, w), np.nan, np.float32)
        order = np.argsort(z[tris].min(axis=1))[::-1]                 # lowest drawn last: the landscape stays under all
        for tri in tris[order]:
            poly = np.stack([u[tri], v[tri]], axis=1).round().astype(np.int32)
            cv2.fillConvexPoly(layer, poly, float(z[tri].min()))
        # natural ground ("wild" triangles): the landscape follows it point by point instead of standing in a step
        # under each triangle. The paint is worked out from the landscape's slope: steps under triangles 20 m across
        # on a hillside would be painted as cliffs, and the sector's ground is painted from that same paint
        # (a sector with natural ground also leaves its whole surface, streets, sidewalks and gardens too, in `seen`:
        # the paint is worked out from what one sees, see below)
        kind_names = [str(k) for k in d["kind_names"]]
        seen[~np.isnan(layer)] = np.nan                               # what another sector showed there no longer counts
        if "wild" in kind_names:
            wild_kind = kind_names.index("wild")
            rise = d["tri_rise"] if "tri_rise" in d.files else np.zeros(tris.shape, np.float32)
            for t, tri in enumerate(tris):
                is_wild = d["kind"][t] == wild_kind
                tu, tv, tz = u[tri] - 0.5, v[tri] - 0.5, z[tri]       # pixel (c, r) has its centre at (c + 0.5, r + 0.5)
                c0, c1 = max(int(np.floor(tu.min())), 0), min(int(np.ceil(tu.max())), w - 1)
                r0, r1 = max(int(np.floor(tv.min())), 0), min(int(np.ceil(tv.max())), h - 1)
                if c1 < c0 or r1 < r0:
                    continue
                cc, rr = np.meshgrid(np.arange(c0, c1 + 1), np.arange(r0, r1 + 1))
                den = (tv[1] - tv[2]) * (tu[0] - tu[2]) + (tu[2] - tu[1]) * (tv[0] - tv[2])
                if abs(den) < 1e-9:
                    continue
                a = ((tv[1] - tv[2]) * (cc - tu[2]) + (tu[2] - tu[1]) * (rr - tv[2])) / den
                b = ((tv[2] - tv[0]) * (cc - tu[2]) + (tu[0] - tu[2]) * (rr - tv[2])) / den
                c = 1.0 - a - b
                hit = (a >= -0.02) & (b >= -0.02) & (c >= -0.02)
                if not hit.any():
                    continue
                if is_wild:
                    zz = (a * tz[0] + b * tz[1] + c * tz[2])[hit]
                    layer[rr[hit], cc[hit]] = zz
                    wild_px[rr[hit], cc[hit]] = True
                    mesh_top[rr[hit], cc[hit]] = zz + CURB_M
                    seen[rr[hit], cc[hit]] = zz + CURB_M
                else:
                    tz = tz + rise[t]                                 # a sidewalk or a garden stands a kerb above its street
                    seen[rr[hit], cc[hit]] = (a * tz[0] + b * tz[1] + c * tz[2])[hit]
        covered = ~np.isnan(layer)
        # the surface's height along this sector's edge (triangles with a corner on an edge that only one triangle
        # has), point by point: what the landscape beyond an open side carries on from. Each pixel takes the triangle
        # it lies in, or failing that the plane of the one it lies nearest to (the mesh is drawn a little wider than
        # its triangles: every pixel a triangle touches)
        edge_top[covered] = np.nan
        pair = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1).astype(np.int64)
        _, inverse, count = np.unique(pair[:, 0] * len(pts) + pair[:, 1], return_inverse=True, return_counts=True)
        on_rim = np.zeros(len(pts), bool)
        on_rim[pair[count[inverse.ravel()] == 1].ravel()] = True
        rise_all = d["tri_rise"] if "tri_rise" in d.files else np.zeros(tris.shape, np.float32)
        wild_kind = kind_names.index("wild") if "wild" in kind_names else -1
        cw0, cw1 = max(int(np.floor(u.min())) - 2, 0), min(int(np.ceil(u.max())) + 2, w - 1)
        rw0, rw1 = max(int(np.floor(v.min())) - 2, 0), min(int(np.ceil(v.max())) + 2, h - 1)
        fit = np.full((rw1 - rw0 + 1, cw1 - cw0 + 1), -1.0, np.float32)       # how well inside its triangle each pixel is
        top = np.full(fit.shape, np.nan, np.float32)
        for t in np.nonzero(on_rim[tris].any(axis=1))[0]:
            tri = tris[t]
            tu, tv = u[tri] - 0.5, v[tri] - 0.5
            tz = z[tri] + (CURB_M if d["kind"][t] == wild_kind else rise_all[t])
            c0, c1 = max(int(np.floor(tu.min())) - 1, cw0), min(int(np.ceil(tu.max())) + 1, cw1)
            r0, r1 = max(int(np.floor(tv.min())) - 1, rw0), min(int(np.ceil(tv.max())) + 1, rw1)
            den = (tv[1] - tv[2]) * (tu[0] - tu[2]) + (tu[2] - tu[1]) * (tv[0] - tv[2])
            if c1 < c0 or r1 < r0 or abs(den) < 1e-9:
                continue
            cc, rr = np.meshgrid(np.arange(c0, c1 + 1), np.arange(r0, r1 + 1))
            a = ((tv[1] - tv[2]) * (cc - tu[2]) + (tu[2] - tu[1]) * (rr - tv[2])) / den
            b = ((tv[2] - tv[0]) * (cc - tu[2]) + (tu[0] - tu[2]) * (rr - tv[2])) / den
            c = 1.0 - a - b
            inside = np.minimum(np.minimum(a, b), c)
            # (a pixel outside the triangle takes the triangle's plane at the triangle's nearest point, not the plane
            # carried on: a steep sliver's plane, carried two pixels on, is metres off)
            aa, bb, cc_ = np.clip(a, 0.0, 1.0), np.clip(b, 0.0, 1.0), np.clip(c, 0.0, 1.0)
            total = np.maximum(aa + bb + cc_, 1e-9)
            zz = (aa * tz[0] + bb * tz[1] + cc_ * tz[2]) / total
            wr, wc = rr - rw0, cc - cw0
            better = (inside > fit[wr, wc]) & (inside > -1.0)
            fit[wr[better], wc[better]] = np.minimum(inside[better], 0.0)     # all pixels inside a triangle fit alike
            top[wr[better], wc[better]] = zz[better]
        here = covered[rw0:rw1 + 1, cw0:cw1 + 1] & ~np.isnan(top)
        edge_top[rw0:rw1 + 1, cw0:cw1 + 1][here] = top[here]
        height[covered] = layer[covered] - SINK_M
        # ...and under the sector's edge the landscape follows that surface point by point: SINK_M under it inside the
        # mesh, SEAM_DROP_M under it on the pixels the mesh only touches (their centres lie outside it, in the open).
        # At the lowest corner of each triangle less SINK_M, as everywhere else under a mesh, the landscape stood in
        # a gutter along every open side whose ground slopes across it: 0.6 m deep beside ED38, 2.7 m under the
        # edge of ED34, seen from above as a dark line round the sector (2026-11-19)
        window = height[rw0:rw1 + 1, cw0:cw1 + 1]
        window[here & (fit >= 0.0)] = top[here & (fit >= 0.0)] - SINK_M
        window[here & (fit < 0.0)] = top[here & (fit < 0.0)] - SEAM_DROP_M
        wild_own[covered] = False
        if "wild" in kind_names:
            here = covered & wild_px & (np.abs(mesh_top - CURB_M - layer) < 1e-4)       # this sector's natural ground
            height[here] = mesh_top[here] - WILD_SINK_M
            wild_own[here] = True
        stamped |= covered
        if os.path.exists(os.path.join(folder, "prep.json")):
            # the sector drew its own shore: inside its outline, whatever its mesh does not cover is water;
            # and so is everything inside the polygons it lists as water, also beyond its outline (the bay in
            # front of a quay, the water round a terrace), unless some sector's ground stands there
            if "outline" in d.files:
                wet_by_design |= ring_mask(d["outline"])
            else:
                wet_by_design |= (wx_px[None, :] > west) & (wx_px[None, :] < east) & (wy_px[:, None] > south) & (wy_px[:, None] < north)
            for ring in SECTORS.get(name, {}).get("water", []):
                wet_by_design |= ring_mask(ring)
        print("SURFACE sector %s: %d pixels under its mesh" % (name, int(covered.sum())))
    # Natural ground far from any ground that no sector covers: the landscape goes well below it. A hand below the mesh
    # it showed through wherever the two part ways: from afar the landscape is drawn with fewer points and cuts the
    # corners the mesh keeps (a web of pale lines all over the cliff of the Falesia Norte, 2026-11-18). Only towards
    # open ground does it come up under the mesh's edge, where the landscape beyond carries on from it (see below).
    if wild_own.any():
        out_m = cv2.distanceTransform(stamped.astype(np.uint8), cv2.DIST_L2, 5) * M_PER_PX
        deep = np.clip(WILD_SINK_M + (out_m - WILD_RIM_M) * 0.5, WILD_SINK_M, WILD_DEEP_M)
        height[wild_own] = (mesh_top - deep)[wild_own]
    # ground a sector declares (its "fill") stays dry even where that sector's mesh ends at its outline
    for spec in SECTORS.values():
        if spec.get("water") or spec.get("fill"):
            for ring in spec.get("fill", []):
                wet_by_design &= ~ring_mask(ring)
    # (one pixel round every mesh is left out: two neighbouring meshes do not always cover the pixels of their
    # shared side, and the seam must not turn into a line of water)
    covered_wide = cv2.dilate(stamped.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    designed_water = wet_by_design & ~covered_wide
    # ...but where that one-pixel rim touches the water it is water too. Otherwise, wherever the map has land
    # beyond a quay that a sector drew, a bank of the old ground is left standing against the wall's face
    rim = wet_by_design & covered_wide & ~stamped & \
        cv2.dilate(designed_water.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    designed_water |= rim
    water = (water & ~stamped) | designed_water
    # the landscape drops to the sea bed a few metres before the sea wall, hidden under the mesh, so nothing of
    # it shows on the wall's face
    near = cv2.dilate(designed_water.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))).astype(bool)
    behind_wall = near & stamped

    # ---- shore and sea bed
    dist_shore = cv2.distanceTransform(water.astype(np.uint8), cv2.DIST_L2, 5) * M_PER_PX
    big_water = gauss(water, 60.0)
    depth = np.minimum(np.where(big_water > 0.6, SEA_DEPTH_M, RIVER_DEPTH_M), 0.6 + 0.2 * dist_shore)
    depth = np.where(designed_water, np.maximum(depth, SEAWALL_BED_M), depth)      # deep right at a sea wall
    height[water] = -depth[water]
    height[behind_wall] = -SEAWALL_BED_M
    land_dist = cv2.distanceTransform((~water).astype(np.uint8), cv2.DIST_L2, 5) * M_PER_PX
    quay = ~water & ~stamped & (land_dist < 5.0) & urban
    height[quay] = np.maximum(height[quay], QUAY_M)
    beach = ~water & ~urban & ~stamped & (land_dist < 22.0)
    tb = np.clip(land_dist / 22.0, 0, 1)
    height[beach] = np.minimum(height[beach], -0.4 + (height[beach] + 0.4) * tb[beach] + 1.4 * tb[beach])
    # (after the beach is graded: where a sector's side comes within reach of the shore, the beach would pull the ground
    # down from the mesh's edge and leave it standing as a bank)
    # a sector's own side with no sector beyond: the landscape carries on from the mesh's edge, a hand below it, and
    # eases into its own height over SEAM_M (never onto a road, which has its own height, and not along a retaining
    # wall, where the step is the design). It used to do so beyond natural ground only: elsewhere the mesh's edge,
    # a straight rail between the outline's corners, stood up to 10 m above the hillside or under it (6.4 km of the
    # 40 km of open sides more than 0.4 m off, 2026-11-18)
    if stamped.any():
        away, near_label = cv2.distanceTransformWithLabels((~stamped).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        sy_, sx_ = np.nonzero(stamped)
        lookup = np.zeros(near_label.max() + 1, np.int64)
        lookup[near_label[sy_, sx_]] = np.arange(len(sy_))
        nearest = lookup[near_label]
        edge_here = edge_top[sy_, sx_]
        from_edge = (~np.isnan(edge_here) & ~walled[sy_, sx_])[nearest]
        edge_z = np.nan_to_num(edge_here)[nearest] - SEAM_DROP_M
        away_m = away * M_PER_PX
        seam = ~stamped & ~water & ~on_road & from_edge & (away_m < SEAM_M)
        # ...and has returned to it three quarters of the way to the water, where the shore is nearer than SEAM_M: the
        # beach still comes down to the sea, it does not end in a bank at the water's edge
        reach = np.maximum(np.minimum(SEAM_M, 0.75 * (away_m + land_dist)), 1.0)
        t = np.clip(away_m / reach, 0.0, 1.0)
        t = t * t * (3 - 2 * t)
        height[seam] = (edge_z + (height - edge_z) * t)[seam]
        print("SURFACE seams: the landscape carries on from the sectors' open sides over %d pixels" % int(seam.sum()))
    # tunnels: the landscape goes below the floor all along each one (the strip tunnel_mesh.py wrote). The
    # sectors' ground meshes hide the trench from above; were the landscape left at ground level over the
    # covered part, it would have to climb through the tunnel's opening somewhere near each portal
    uncarved = height.copy()        # the ground as it is seen from above: what the paint is worked out from
    # ...which in a sector with natural ground is that sector's own surface. The landscape lies SINK_M and more under
    # its streets and gardens and metres under its natural ground: read from the landscape, every street and garden
    # was a hollow, and hollows are painted green: the sector's natural ground came out greener than the hill beyond
    # its side, along a straight line (FN6, SE2, 2026-11-18)
    shown = ~np.isnan(seen)
    uncarved[shown] = seen[shown]
    for path in sorted(glob.glob(os.path.join(DATA, "structures", "*", "carve.npz"))):
        d = np.load(path)
        u, v = to_pixel(d["pts"][:, 0], d["pts"][:, 1])
        layer = np.full((h, w), np.nan, np.float32)
        for tri in d["tris"][np.argsort(d["z"][d["tris"]].min(axis=1))[::-1]]:
            cv2.fillConvexPoly(layer, np.stack([u[tri], v[tri]], axis=1).round().astype(np.int32), float(d["z"][tri].min()))
        low = ~np.isnan(layer)
        height[low] = np.minimum(height[low], layer[low])
        print("SURFACE tunnel %s: landscape lowered under %d pixels, down to %.1f m" % (
            os.path.basename(os.path.dirname(path)), int(low.sum()), float(layer[low].min()) if low.any() else 0.0))
    # ...and a tunnel under a river lies buried in its bed: the bed is raised over the roof where it would be lower
    # (bury.npz: tunnel_mesh.py, for a tunnel marked "under_water")
    for path in sorted(glob.glob(os.path.join(DATA, "structures", "*", "bury.npz"))):
        d = np.load(path)
        u, v = to_pixel(d["pts"][:, 0], d["pts"][:, 1])
        layer = np.full((h, w), np.nan, np.float32)
        for tri in d["tris"][np.argsort(d["z"][d["tris"]].max(axis=1))]:
            cv2.fillConvexPoly(layer, np.stack([u[tri], v[tri]], axis=1).round().astype(np.int32), float(d["z"][tri].max()))
        up = ~np.isnan(layer) & (height < layer)
        height[up] = layer[up]
        print("SURFACE tunnel %s: river bed raised over the roof under %d pixels, up to %.1f m" % (
            os.path.basename(os.path.dirname(path)), int(up.sum()), float(layer[up].max()) if up.any() else 0.0))
    np.save(data_path("surface_height.npy"), height.astype(np.float32))

    # ---- landscape grid: 2 m quads, with natural land and sea beyond the frame
    frame_w_m, frame_h_m = w * M_PER_PX, h * M_PER_PX
    quads_x = int(np.ceil((frame_w_m + 2 * MARGIN_M) / QUAD_M / COMPONENT_QUADS)) * COMPONENT_QUADS
    quads_y = int(np.ceil((frame_h_m + 2 * MARGIN_M) / QUAD_M / COMPONENT_QUADS)) * COMPONENT_QUADS
    vx, vy = quads_x + 1, quads_y + 1
    size_x_m, size_y_m = quads_x * QUAD_M, quads_y * QUAD_M
    centre_x, centre_y = X_LEFT + frame_w_m / 2, Y_TOP - frame_h_m / 2
    origin_x, origin_y = centre_x - size_x_m / 2, centre_y + size_y_m / 2
    px = ((origin_x + np.arange(vx, dtype=np.float32) * QUAD_M) - X_LEFT) * PX_PER_M - 0.5
    py = (Y_TOP - (origin_y - np.arange(vy, dtype=np.float32) * QUAD_M)) * PX_PER_M - 0.5
    map_x, map_y = np.meshgrid(px, py)

    def sample(a, border=cv2.BORDER_CONSTANT):
        return cv2.remap(a.astype(np.float32), map_x, map_y, cv2.INTER_LINEAR, borderMode=border, borderValue=0)

    zs = sample(height, cv2.BORDER_REPLICATE)
    dx = np.maximum(np.maximum(-map_x, map_x - (w - 1)), 0) * M_PER_PX
    dy = np.maximum(np.maximum(-map_y, map_y - (h - 1)), 0) * M_PER_PX
    d = np.sqrt(dx * dx + dy * dy)
    outside = d > 0
    # beyond the frame the last row of the map would repeat as straight ridges: melt it into its own
    # broad shape within a couple of hundred metres
    broad = gauss(zs, 110.0)
    melt = np.clip(d / 220.0, 0, 1)
    melt = melt * melt * (3 - 2 * melt)
    zs = zs + (broad - zs) * melt
    t_out = np.clip(d / 200.0, 0, 1)
    warp = 260.0 * PX_PER_M
    wx_ = (map_x + fbm(zs.shape, 900 / QUAD_M, seed=21) * warp * t_out).astype(np.float32)
    wy_ = (map_y + fbm(zs.shape, 900 / QUAD_M, seed=22) * warp * t_out).astype(np.float32)
    wext = cv2.remap(water.astype(np.float32), wx_, wy_, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    sea = (wext + 0.25 * fbm(zs.shape, 260 / QUAD_M, seed=11) * t_out) > 0.5
    sea = np.where(outside, sea, sample(water) > 0.5)
    shore_dist = cv2.distanceTransform((~sea).astype(np.uint8), cv2.DIST_L2, 5) * QUAD_M
    sea_dist = cv2.distanceTransform(sea.astype(np.uint8), cv2.DIST_L2, 5) * QUAD_M
    town = sample(urban) > 0.3
    road_l = sample(on_road) > 0.3
    town_dist = cv2.distanceTransform((~town).astype(np.uint8), cv2.DIST_L2, 5) * QUAD_M
    road_dist = cv2.distanceTransform((~road_l).astype(np.uint8), cv2.DIST_L2, 5) * QUAD_M
    jitter = fbm(zs.shape, 1200 / QUAD_M, seed=17) * 350.0
    rise = np.clip((town_dist + jitter - 450.0) / 1300.0, 0, 1)
    rise = rise * rise * (3 - 2 * rise)
    hills = (0.55 + 0.45 * fbm(zs.shape, 700 / QUAD_M, seed=13)) * 130.0
    keep_clear = np.clip((road_dist - 40.0) / 160.0, 0, 1)
    # inside the frame the map's own relief stands; the extra hills only grow beyond it
    grow = np.clip(d / 500.0, 0, 1)
    land_z = zs + hills * rise * np.clip(shore_dist / 250.0, 0, 1) * keep_clear * grow
    sea_z = -np.minimum(SEA_DEPTH_M, 0.8 + 0.12 * sea_dist)
    z_new = np.where(sea, np.where(outside, sea_z, zs), land_z)
    blend = np.where(outside, np.clip(d / 150.0, 0, 1), 1.0)
    blend = blend * blend * (3 - 2 * blend)
    zs = zs + (z_new - zs) * blend
    ex = np.minimum(np.arange(vx), vx - 1 - np.arange(vx)) * QUAD_M
    ey = np.minimum(np.arange(vy), vy - 1 - np.arange(vy)) * QUAD_M
    edge = np.minimum(ex[None, :], ey[:, None]) + fbm(zs.shape, 800 / QUAD_M, seed=31) * 260.0
    rim = np.clip(1 - (edge - 60.0) / 380.0, 0, 1)
    rim = rim * rim * (3 - 2 * rim)
    zs = zs + (-SEA_DEPTH_M - zs) * rim
    sea |= rim > 0.6
    np.clip(np.round(32768 + zs * 128.0), 0, 65535).astype(np.uint16).tofile(data_path("landscape.r16"))

    # ---- paint layers (2026-11-17: the whole city is built, so what the landscape shows is the country round it,
    # painted the way the Bay Area's hills look in the dry season: golden grass on the slopes the sun bakes (facing
    # south and west) and on high ground, green on the slopes facing north and east, in the hollows and along the
    # shore, bare earth where the slope is steep and sunny, grey scree on the steepest faces, sand only on the beach.
    # Before, everything not built was one even green, the map's town ground still read as bare soil and all low
    # ground was sand.)
    # (the paint follows the ground one sees. Over a tunnel that is a sector's ground, and the landscape lies in a
    # trench under it: painted from the trench, the tunnel's line showed in the paint as a band of sand between two of
    # scree, which a sector's natural ground would then wear on its back. So: the heights without the trenches.)
    zl = zs
    zs = zs + sample(uncarved - height)
    # ...and under a sector's mesh, without the mesh's own grain: its ground is blended from rows of samples 16 m apart
    # and has ripples of a few centimetres along them, which the paint (by which way the ground faces, and by its
    # hollows) drew as stripes of green and dry grass across a hillside
    zs = np.where(sample(stamped) > 0.5, gauss(zs, 10.0 / QUAD_M), zs)
    gy, gx = np.gradient(zs, QUAD_M)            # gx: rise towards the east; gy: rise towards the south (rows run south)
    slope = np.sqrt(gx * gx + gy * gy)
    carriage = dist_m <= np.maximum(hw_near - 3.6, 3.0)
    s_road = sample(carriage & ~water)
    s_row = sample(on_road & ~water)
    s_urban = sample(urban)
    s_beach = sample(beach)
    s_water = (sea | (zl < 0.0)).astype(np.float32) * (zs < 0.0)
    weights = {}
    g = np.maximum(slope, 1e-6)
    # which way the ground faces: +1 down to the south-west (sun all afternoon), -1 down to the north-east
    facing = np.clip((-gy / g) * 0.8 + (gx / g) * 0.45, -1.0, 1.0) * np.clip(slope / 0.20, 0, 1)
    # valley floors and creeks, at two widths (a gully, a drainage): green follows them as it does on real hills,
    # instead of lying in round patches
    hollow = np.maximum(np.clip((gauss(zs, 20.0) - zs) / 2.0, 0, 1), np.clip((gauss(zs, 60.0) - zs) / 5.0, 0, 1))
    by_water = np.clip(1.0 - shore_dist / 90.0, 0, 1) * np.clip((9.0 - zs) / 5.0, 0, 1)
    wet = np.maximum(hollow, by_water)
    high = np.clip((zs - 6.0) / 45.0, 0, 1)
    patch = fbm(zs.shape, 340.0 / QUAD_M, seed=41)
    fine = fbm(zs.shape, 60.0 / QUAD_M, seed=43)
    dryness = 0.26 + 0.45 * high + 0.55 * facing + 0.16 * patch + 0.10 * fine - 0.95 * wet - 0.25 * s_urban
    dry = np.clip((dryness - 0.18) / 0.30, 0, 1)
    dry = dry * dry * (3 - 2 * dry)
    # BAY_PAINT_PROBE="x,y;x,y;...": what the paint is made of at those points (metres east, north), to find out why
    # two sides of a line are painted differently
    for item in [p for p in os.environ.get("BAY_PAINT_PROBE", "").split(";") if p.strip()]:
        ex_, ny_ = [float(v) for v in item.split(",")]
        c_, r_ = int(round((ex_ - origin_x) / QUAD_M)), int(round((origin_y - ny_) / QUAD_M))
        print("PROBE (%.0f, %.0f): z %.2f (landscape %.2f) slope %.3f | high %.2f facing %+.2f patch %+.2f fine %+.2f hollow %.2f "
              "by_water %.2f urban %.2f -> dryness %+.2f dry %.2f" % (
                  ex_, ny_, zs[r_, c_], zl[r_, c_], slope[r_, c_], high[r_, c_], facing[r_, c_], patch[r_, c_], fine[r_, c_],
                  hollow[r_, c_], by_water[r_, c_], s_urban[r_, c_], dryness[r_, c_], dry[r_, c_]))
    rock = np.clip((slope - 0.80) / 0.35, 0, 1)
    earth = np.clip((slope - 0.42) / 0.38, 0, 1) * np.clip(0.55 + 0.45 * facing + 0.35 * fine, 0, 1)
    sand = np.clip(np.maximum(s_beach, s_water) * 1.5 - 0.2, 0, 1)
    sand = np.maximum(sand, np.clip((1.2 - zs) / 1.5, 0, 1) * np.clip(1.0 - shore_dist / 30.0, 0, 1) * (1 - s_row))
    sand *= 1 - s_urban * 0.7
    asphalt = np.clip(s_road * 1.6 - 0.3, 0, 1)
    pavement = np.clip(s_row * 1.5 - 0.3, 0, 1)
    remaining = np.ones_like(zs)
    for name, wgt in (("Asphalt", asphalt), ("Pavement", pavement), ("Rock", rock), ("Sand", sand), ("Dirt", earth)):
        take = np.minimum(wgt, remaining)
        weights[name] = take
        remaining -= take
    weights["DryGrass"] = remaining * dry
    weights["Grass"] = remaining * (1 - dry)
    total = sum(weights.values())
    q = {name: np.round(weights[name] / total * 255.0) for name in LAYERS}
    q["Grass"] = 255.0 - sum(q[n] for n in LAYERS if n != "Grass")
    for name in LAYERS:
        np.clip(q[name], 0, 255).astype(np.uint8).tofile(data_path("layer_%s.raw" % name))

    # the natural layers as one picture: what the ground would be painted were there no street on it. Under a street
    # the paint is asphalt and pavement; a sector's natural ground beside that street reads this picture, so there the
    # natural layers are carried in from around
    natural = sum(q[n] for n in NATURAL_LAYERS) / 255.0
    # (not from under water either: the hole a sector's mesh leaves over a tunnel's open ramp counts as water, and its
    # sand would rim the ground beside the ramp's walls)
    known = (natural > 0.6) & (s_water < 0.5)
    chans = [np.clip(fill_holes(q[n] / 255.0 / np.maximum(natural, 1e-3), known), 0.0, 1.0) for n in NATURAL_LAYERS[:4]]
    over = np.maximum(sum(chans), 1.0)
    picture = np.stack([chans[2] / over, chans[1] / over, chans[0] / over, chans[3] / over], axis=2)     # B, G, R, A for OpenCV
    picture = cv2.resize((picture * 255.0).astype(np.float32), (PAINT_MAP_PX, PAINT_MAP_PX), interpolation=cv2.INTER_AREA)
    cv2.imwrite(data_path("paint_map.png"), np.clip(np.round(picture), 0, 255).astype(np.uint8))

    save_json("landscape.json", {
        "vertices": [vx, vy], "quad_m": QUAD_M, "component_quads": COMPONENT_QUADS,
        "components": [quads_x // COMPONENT_QUADS, quads_y // COMPONENT_QUADS],
        "location_cm": [origin_x * 100.0, -origin_y * 100.0, 0.0],
        "scale": [QUAD_M * 100.0, QUAD_M * 100.0, 100.0],
        "layers": LAYERS,
        # paint_map.png laid over the whole landscape: its corner and its size in Unreal cm (x east, y south)
        "paint_map": {"file": "paint_map.png", "origin_cm": [origin_x * 100.0, -origin_y * 100.0],
                      "size_cm": [size_x_m * 100.0, size_y_m * 100.0], "channels": NATURAL_LAYERS[:4]},
    }, indent=1)

    small = cv2.resize(zs, (vx // 4, vy // 4), interpolation=cv2.INTER_AREA)
    sy, sx = np.gradient(small, 4 * QUAD_M)
    shade = np.clip(0.8 + (sx * -0.8 + sy * 0.8) * 1.3, 0.3, 1.35)
    col = np.stack([60 + small * 0.6, 120 + small * 0.3, 70 + small * 1.0], axis=2)
    col[small < 0] = (150, 110, 60)
    road_small = cv2.resize(sample(on_road), (vx // 4, vy // 4), interpolation=cv2.INTER_AREA) > 0.4
    col[road_small] = (90, 90, 90)
    cv2.imwrite(data_path("surface.png"), np.clip(col * shade[:, :, None], 0, 255).astype(np.uint8))
    # the paint as seen from afar: each layer's far colour by its weight, shaded, sea in blue
    lin = np.zeros(small.shape + (3,), np.float32)
    for name in LAYERS:
        wsm = cv2.resize(q[name].astype(np.float32) / 255.0, (vx // 4, vy // 4), interpolation=cv2.INTER_AREA)
        lin += wsm[:, :, None] * np.array(PREVIEW[name], np.float32)[None, None, :]
    rgb = np.clip(lin * shade[:, :, None] * 1.6, 0, 1) ** (1 / 2.2) * 255.0
    sea_small = cv2.resize(sea.astype(np.float32), (vx // 4, vy // 4), interpolation=cv2.INTER_AREA) > 0.5
    rgb[sea_small] = (60, 95, 140)
    cv2.imwrite(data_path("paint.png"), rgb[:, :, ::-1].astype(np.uint8))
    land = ~water
    print("SURFACE height %.1f .. %.1f m inside the frame; landscape %d x %d vertices (%d x %d components), %.1f x %.1f km" % (
        height[land].min(), height[land].max(), vx, vy, quads_x // COMPONENT_QUADS, quads_y // COMPONENT_QUADS,
        size_x_m / 1000, size_y_m / 1000))


if __name__ == "__main__":
    main()
