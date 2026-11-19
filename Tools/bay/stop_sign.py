"""The stop sign of the Bay city: a post with an octagonal plate, made here because no pack in the project has one.

  python -P Tools/bay/stop_sign.py texture                                   (Pillow: the texture)
  blender -b --factory-startup --python Tools/bay/stop_sign.py -- mesh       (the mesh)

Output: Saved/Bay/props/T_Bay_StopSign.png   1024 x 512: the face (left half: red octagon, white border, STOP) and
                                             galvanised steel (right half: the post and the back of the plate)
        Saved/Bay/props/SM_Bay_StopSign.glb  metres, x forward (the face looks along +X), z up, origin at the foot of
                                             the post; one material slot, StopSign
build_bay.py stage "propassets" imports both into /Game/Bay/Props (texture, material instance, mesh); plan_props.py
places it at junctions that get stop signs instead of traffic signals.

Sizes: a 76 cm plate (30 in across the flats, the urban size), its bottom edge 2.15 m above the ground, on a 5 cm
square steel post. Letters about a third of the plate's height.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "Saved", "Bay", "props")
TEX_W, TEX_H = 1024, 512
FLATS_M = 0.762             # plate across the flats
PLATE_BOTTOM_M = 2.15
POST_M = 0.05               # square post, side
POST_TOP_M = PLATE_BOTTOM_M + FLATS_M + 0.04
FOOT_M = -0.25              # the post goes into the ground
PLATE_T = 0.004
FACE_FILL = 0.96            # the octagon's share of its square on the texture


def octagon(across_flats):
    """Vertices (y, z) of an octagon with a flat top, centred on 0, counter-clockwise."""
    r = across_flats / 2.0 / math.cos(math.radians(22.5))
    return [(r * math.cos(math.radians(22.5 + 45 * k)), r * math.sin(math.radians(22.5 + 45 * k))) for k in range(8)]


def texture():
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (TEX_W, TEX_H), (150, 152, 154))
    d = ImageDraw.Draw(img)
    side = TEX_H                                      # the face square, 512 px
    c = side / 2.0
    scale = side * FACE_FILL / FLATS_M                # px per metre on the face

    def poly(across, colour):
        pts = [(c + y * scale, c - z * scale) for y, z in octagon(across)]
        d.polygon(pts, fill=colour)

    poly(FLATS_M, (236, 236, 232))                    # white border
    poly(FLATS_M - 2 * 0.019, (178, 22, 30))          # red field
    font = None
    for path in (r"C:\Windows\Fonts\bahnschrift.ttf", r"C:\Windows\Fonts\arialbd.ttf"):
        if os.path.exists(path):
            font = ImageFont.truetype(path, int(side * 0.30))
            try:
                font.set_variation_by_name("Bold")
            except Exception:
                pass
            break
    box = d.textbbox((0, 0), "STOP", font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    d.text((c - tw / 2.0 - box[0], c - th / 2.0 - box[1]), "STOP", fill=(240, 240, 236), font=font)
    # galvanised steel on the right half: a little mottling so it does not read as flat paint
    a = np.asarray(img).astype(np.float32)
    rng = np.random.default_rng(7)
    noise = rng.normal(0.0, 6.0, (TEX_H, TEX_W // 2, 1))
    a[:, TEX_W // 2:, :] = np.clip(a[:, TEX_W // 2:, :] + noise, 0, 255)
    os.makedirs(OUT, exist_ok=True)
    Image.fromarray(a.astype(np.uint8)).save(os.path.join(OUT, "T_Bay_StopSign.png"))
    print("STOPSIGN texture -> %s" % os.path.join(OUT, "T_Bay_StopSign.png"))


def mesh():
    import bmesh
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    metal_u = (0.55, 0.95)

    def face(coords, uvs):
        f = bm.faces.new([bm.verts.new(p) for p in coords])
        for loop, t in zip(f.loops, uvs):
            loop[uv].uv = t
        return f

    # the post: four sides and a cap, steel
    h = POST_M / 2.0
    corners = [(-h, -h), (h, -h), (h, h), (-h, h)]
    for i in range(4):
        (x0, y0), (x1, y1) = corners[i], corners[(i + 1) % 4]
        face([(x0, y0, FOOT_M), (x1, y1, FOOT_M), (x1, y1, POST_TOP_M), (x0, y0, POST_TOP_M)],
             [(metal_u[0], 0.0), (metal_u[0] + 0.05, 0.0), (metal_u[0] + 0.05, 1.0), (metal_u[0], 1.0)])
    face([(x, y, POST_TOP_M) for x, y in corners], [(0.8, 0.5)] * 4)
    # the plate: front (the face, +X), back and edges (steel)
    zc = PLATE_BOTTOM_M + FLATS_M / 2.0
    x_front, x_back = h + 0.004 + PLATE_T, h + 0.004
    ring = octagon(FLATS_M)
    s = FLATS_M / FACE_FILL                            # metres across the face square of the texture
    front_uv = [((y / s + 0.5) * 0.5, 0.5 + z / s) for y, z in ring]
    face([(x_front, y, zc + z) for y, z in ring], front_uv)
    face([(x_back, y, zc + z) for y, z in reversed(ring)], [(0.9, 0.5)] * 8)
    for i in range(8):
        (y0, z0), (y1, z1) = ring[i], ring[(i + 1) % 8]
        face([(x_back, y0, zc + z0), (x_back, y1, zc + z1), (x_front, y1, zc + z1), (x_front, y0, zc + z0)], [(0.85, 0.5)] * 4)
    # two clamps holding the plate to the post, seen from behind (normal -X)
    for zz in (PLATE_BOTTOM_M + 0.12, PLATE_BOTTOM_M + FLATS_M - 0.12):
        q = [(x_back - 0.002, 0.05, zz - 0.02), (x_back - 0.002, -0.05, zz - 0.02), (x_back - 0.002, -0.05, zz + 0.02), (x_back - 0.002, 0.05, zz + 0.02)]
        face(q, [(0.7, 0.5)] * 4)
    # (every face above is wound to face outwards; bmesh's recalc_face_normals turned some of these loose faces
    # inwards, and the sign rendered black: 2026-11-17)
    me = bpy.data.meshes.new("SM_Bay_StopSign")
    bm.to_mesh(me)
    bm.free()
    mat = bpy.data.materials.new("StopSign")
    me.materials.append(mat)
    obj = bpy.data.objects.new("SM_Bay_StopSign", me)
    bpy.context.scene.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "SM_Bay_StopSign.glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_materials="EXPORT")
    print("STOPSIGN mesh: %d faces -> %s" % (len(me.polygons), path))


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    mode = args[0] if args else "texture"
    texture() if mode == "texture" else mesh()
