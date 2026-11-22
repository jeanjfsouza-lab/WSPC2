"""Reads the land and water round the city from the campaign model (Blender), for the outskirts beyond the map.

  blender -b --factory-startup --python Tools/bay/campaign_ground.py

The campaign model (bay_city_3d/dados/malha_urbana.glb, the user's 3D city, 2026-11-21: "the reference for the whole
city") has ground far beyond the Bay's playable frame: the bay to the west and north, land, a river and low hills on the
other sides. This renders it from above in colour over OUTSKIRTS_KM on a side and ray-casts its height at every pixel;
water is told by its blue. The model is carried into Bay metres by the global fit of plan_campaign.py (the local fit
only covers the city).

Input:  bay_city_3d/dados/malha_urbana.glb (or ASSETS TO USE/bay_city_3d/dados/), Tools/bay/plan_campaign.py (fit)
Output: Saved/Bay/outskirts/model_ground.npz   water (uint8 0/1), height (float32, model metres), x0, y0, step:
                                               row 0 is the north edge, Bay metres (x east, y north)
        Saved/Bay/outskirts/model_ground.png   the render, for checking
"""
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(PROJECT, "Saved", "Bay", "outskirts")
SCALE, SHIFT_X, SHIFT_Y = 0.970, 856.0, -292.0      # plan_campaign.py: x_bay = 0.970 X + 856, y_bay = -0.970 Z - 292
CENTRE_BAY = (800.0, 275.0)                         # the middle of the Bay's map frame
OUTSKIRTS_KM = 48.0
PX = 960                                            # 50 m a pixel


def main():
    glb = os.path.join(PROJECT, "bay_city_3d", "dados", "malha_urbana.glb")
    if not os.path.exists(glb):
        glb = os.path.join(PROJECT, "ASSETS TO USE", "bay_city_3d", "dados", "malha_urbana.glb")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb)
    dg = bpy.context.evaluated_depsgraph_get()

    # Bay -> model: X = (x - SHIFT_X) / SCALE, Z = -(y - SHIFT_Y) / SCALE; Blender's y is -Z
    size_model = OUTSKIRTS_KM * 1000.0 / SCALE
    cx = (CENTRE_BAY[0] - SHIFT_X) / SCALE
    cy_blender = (CENTRE_BAY[1] - SHIFT_Y) / SCALE        # = -Z
    trees = []
    for ob in bpy.context.scene.objects:
        if ob.type == "MESH":
            mesh = ob.evaluated_get(dg).to_mesh()
            trees.append(BVHTree.FromPolygons([ob.matrix_world @ v.co for v in mesh.vertices],
                                              [tuple(p.vertices) for p in mesh.polygons]))
    height = np.full((PX, PX), np.nan, np.float32)
    step = size_model / PX
    for r in range(PX):
        y = cy_blender + size_model / 2 - (r + 0.5) * step
        for c in range(PX):
            x = cx - size_model / 2 + (c + 0.5) * step
            best = None
            for t in trees:
                hit = t.ray_cast(Vector((x, y, 2000.0)), Vector((0, 0, -1)), 5000.0)
                if hit[0] is not None and (best is None or hit[0].z > best):
                    best = hit[0].z
            if best is not None:
                height[r, c] = best

    scene = bpy.context.scene
    cam = bpy.data.cameras.new("top")
    cam.type, cam.ortho_scale, cam.clip_end = "ORTHO", size_model, 10000
    co = bpy.data.objects.new("top", cam)
    co.location = (cx, cy_blender, 3000)
    scene.collection.objects.link(co)
    scene.camera = co
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    scene.world = world
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    scene.render.resolution_x = scene.render.resolution_y = PX
    os.makedirs(OUT, exist_ok=True)
    png = os.path.join(OUT, "model_ground.png")
    scene.render.filepath = png
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(png)
    rgba = np.array(img.pixels[:], np.float32).reshape(PX, PX, 4)[::-1]       # Blender rows run from the bottom
    # the render comes out dark: judge by hue (blue water against green land), not by brightness
    r, g, b = rgba[..., 0], rgba[..., 1], rgba[..., 2]
    lit = np.maximum(np.maximum(r, g), b)
    water = ((b > g * 1.15) & (b > r * 1.6) & (lit > 0.01) & (height == height)).astype(np.uint8)

    half = OUTSKIRTS_KM * 1000.0 / 2.0
    np.savez_compressed(os.path.join(OUT, "model_ground.npz"), water=water, height=np.nan_to_num(height, nan=0.0),
                        x0=CENTRE_BAY[0] - half, y0=CENTRE_BAY[1] + half, step=OUTSKIRTS_KM * 1000.0 / PX)
    print("CAMPAIGN_GROUND %d x %d px, %.0f m a pixel, water %.0f%%, height %.1f..%.1f m -> %s" % (
        PX, PX, OUTSKIRTS_KM * 1000.0 / PX, 100.0 * water.mean(), np.nanmin(height), np.nanmax(height), OUT))


main()
