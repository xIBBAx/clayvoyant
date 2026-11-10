"""Build and render one clay shot inside Blender (run by `blender -b -P blender_scene.py -- job.json`).

Original code for this project, written against Blender's public Python API. A job (JSON, made by
sastudio.stopmotion.job) describes the set, the light, the characters (from `look.design`), their
acting per frame and the camera. Everything is built from primitives, curves and modifiers at
miniature scale (a figure is about 30 cm tall), so real lens and f-stop values give the shallow
depth of field of photographed stop motion. Mouths are replacement pieces swapped frame by frame;
frames are rendered on twos.
"""

import json
import math
import os
import sys

import bpy
from mathutils import Vector

FIG = 0.30  # figure height in metres
JOB = json.loads(open(sys.argv[sys.argv.index("--") + 1], encoding="utf-8").read())


# --------------------------------------------------------------------------- helpers
def hex_rgb(h, a=1.0):
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]
    return (*lin, a)


def kelvin_rgb(k):
    t = k / 100.0
    r = 255 if t <= 66 else 329.698727446 * ((t - 60) ** -0.1332047592)
    g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * ((t - 60) ** -0.0755148492)
    b = 255 if t >= 66 else (0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307)
    return tuple(max(0.0, min(1.0, v / 255)) for v in (r, g, b))


MATS = {}


def clay(color, rough=0.62, bump=1.0, sss=0.06, name=None):
    key = (color, rough, bump, sss)
    if key in MATS:
        return MATS[key]
    m = bpy.data.materials.new(name or f"clay_{color}")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = hex_rgb(color)
    bsdf.inputs["Roughness"].default_value = rough
    for nm, v in (("Subsurface Weight", sss), ("Specular IOR Level", 0.35)):
        if nm in bsdf.inputs:
            bsdf.inputs[nm].default_value = v
    if bump > 0:
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.noise_dimensions = "4D"
        noise.inputs["Scale"].default_value = 220.0
        noise.inputs["Detail"].default_value = 6.0
        vor = nt.nodes.new("ShaderNodeTexVoronoi")
        vor.inputs["Scale"].default_value = 90.0
        mixn = nt.nodes.new("ShaderNodeMath")
        mixn.operation = "ADD"
        nt.links.new(noise.outputs["Fac"], mixn.inputs[0])
        nt.links.new(vor.outputs["Distance"], mixn.inputs[1])
        bmp = nt.nodes.new("ShaderNodeBump")
        bmp.inputs["Strength"].default_value = 0.18 * bump
        bmp.inputs["Distance"].default_value = 0.0015
        nt.links.new(mixn.outputs[0], bmp.inputs["Height"])
        nt.links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
        BOIL.append(noise)
    MATS[key] = m
    return m


BOIL = []  # noise nodes whose W changes per drawing: the hand-made shimmer of clay


def link(obj, parent=None):
    if obj.name not in bpy.context.scene.collection.objects:
        for c in obj.users_collection:
            c.objects.unlink(obj)
        bpy.context.scene.collection.objects.link(obj)
    obj.parent = parent
    return obj


def smooth(obj, levels=2):
    for p in obj.data.polygons:
        p.use_smooth = True
    if levels:
        mod = obj.modifiers.new("smooth", "SUBSURF")
        mod.levels, mod.render_levels = 1, levels
    return obj


def sphere(name, r, loc, scale=(1, 1, 1), mat=None, parent=None, levels=1):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=24, ring_count=12, location=(0, 0, 0))
    o = bpy.context.object
    o.name = name
    link(o, parent)
    o.location, o.scale = loc, scale
    if mat:
        o.data.materials.append(mat)
    return smooth(o, levels)


def box(name, size, loc, mat, parent=None, bevel=0.004):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    o = bpy.context.object
    o.name = name
    link(o, parent)
    o.location, o.scale = loc, size
    o.data.materials.append(mat)
    b = o.modifiers.new("bevel", "BEVEL")
    b.width, b.segments, b.affect = bevel, 3, "EDGES"
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def rounded_block(name, half, loc, mat, parent=None, taper=0.0):
    """A soft clay block: a cube, wider at the top when tapered, smoothed into a pillow."""
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
    o = bpy.context.object
    o.name = name
    link(o, parent)
    o.location, o.scale = loc, half
    o.data.materials.append(mat)
    if taper:
        t = o.modifiers.new("taper", "SIMPLE_DEFORM")
        t.deform_method, t.deform_axis, t.factor = "TAPER", "Z", taper
    b = o.modifiers.new("bevel", "BEVEL")
    b.width, b.segments = 0.35, 2
    return smooth(o, 2)


def tube(name, pts, radius, mat, parent=None, taper_end=1.0):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions, cu.bevel_depth, cu.bevel_resolution, cu.use_fill_caps = "3D", radius, 4, True
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (*p, 1.0)
        sp.points[i].radius = 1.0 + (taper_end - 1.0) * i / max(1, len(pts) - 1)
    o = bpy.data.objects.new(name, cu)
    link(o, parent)
    o.data.materials.append(mat)
    return o


def empty(name, loc, parent=None):
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = 0.02
    link(e, parent)
    e.location = loc
    return e


def key(obj, path, frame, value=None, index=-1):
    if value is not None:
        setattr(obj, path, value) if index < 0 else getattr(obj, path).__setitem__(index, value)
    obj.keyframe_insert(data_path=path, frame=frame, index=index)


# --------------------------------------------------------------------------- characters
def shade(h, t):
    h = h.lstrip("#")
    return "#" + "".join(f"{round(int(h[i:i + 2], 16) * (1 - t)):02X}" for i in (0, 2, 4))


def build_character(c):
    d = c["design"]
    root = empty(f"{c['id']}_root", c["pos"])
    root.rotation_euler[2] = c["yaw"]
    skin, hair = clay(d["skin"], 0.55, 0.8, 0.12), clay(d["hair"]["color"], 0.7, 1.4)
    top, shirt = clay(d["outfit"]["color"], 0.7, 1.2), clay(d["outfit"].get("shirt", "#F1ECE4"), 0.66, 0.9)
    trousers, shoes = clay(d["trousers"], 0.72, 1.2), clay(d["shoes"]["color"], 0.45, 0.6)
    outfit, hs, extras = d["outfit"]["style"], d["hair"]["style"], set(d.get("extras") or [])
    long_top = outfit == "kurta"
    # legs and shoes
    for sx in (-1, 1):
        tube(f"{c['id']}_leg{sx}", [(sx * 0.026, 0, 0.014), (sx * 0.027, 0, 0.128)], 0.0175, trousers, root)
        sphere(f"{c['id']}_shoe{sx}", 0.024, (sx * 0.029, -0.012, 0.010), (0.85, 1.35, 0.55), shoes, root)
    # torso, a soft tapered lump
    torso = rounded_block(f"{c['id']}_torso", (0.056, 0.040, 0.072 if not long_top else 0.095),
                          (0, 0, 0.183 if not long_top else 0.160), top, root, taper=0.30)
    if long_top:  # a kurta: the tunic hangs past the hips, with a placket
        tube(f"{c['id']}_placket", [(0, -0.041, 0.255), (0, -0.0425, 0.215)], 0.0025, clay(shade(d["outfit"]["color"], 0.25), 0.6), root)
    if outfit in ("blazer", "suit", "jacket"):
        sphere(f"{c['id']}_shirt", 0.022, (0, -0.040, 0.205), (0.9, 0.35, 1.6), shirt, root)
        for sx in (-1, 1):
            lap = sphere(f"{c['id']}_lapel{sx}", 0.016, (sx * 0.020, -0.041, 0.207), (0.55, 0.25, 1.7),
                         clay(shade(d["outfit"]["color"], 0.18), 0.7), root)
            lap.rotation_euler[1] = sx * 0.35
    if "lapel_pin" in extras:
        sphere(f"{c['id']}_pin", 0.0035, (-0.034, -0.046, 0.222), mat=clay("#E2B856", 0.3, 0), parent=root)
    if "necklace" in extras:
        tube(f"{c['id']}_necklace", [(-0.012, -0.040, 0.238), (0, -0.044, 0.226), (0.012, -0.040, 0.238)], 0.0012,
             clay("#E2B856", 0.3, 0), root)
    # arms: shoulder and elbow joints that gestures rotate
    arms = {}
    for sx, side in ((-1, "left"), (1, "right")):
        sh = empty(f"{c['id']}_{side}_shoulder", (sx * 0.064, 0, 0.240), root)
        sphere(f"{c['id']}_{side}_cap", 0.0158, (0, 0, 0), mat=top, parent=sh)
        tube(f"{c['id']}_{side}_upper", [(0, 0, 0), (sx * 0.004, 0, -0.050)], 0.0145, top, sh)
        el = empty(f"{c['id']}_{side}_elbow", (sx * 0.004, 0, -0.050), sh)
        sphere(f"{c['id']}_{side}_elbowball", 0.0142, (0, 0, 0), mat=top, parent=el)
        tube(f"{c['id']}_{side}_fore", [(0, 0, 0), (0, 0, -0.046)], 0.0136, top, el)
        sphere(f"{c['id']}_{side}_hand", 0.0135, (0, -0.002, -0.056), (0.95, 0.8, 1.15), skin, el)
        arms[side] = (sh, el)
    # head on a neck pivot
    neck = empty(f"{c['id']}_neck", (0, 0, 0.262), root)
    tube(f"{c['id']}_neckpiece", [(0, 0, -0.012), (0, 0, 0.010)], 0.012, skin, neck)
    head = sphere(f"{c['id']}_head", 0.046, (0, 0, 0.050), (1.0, 0.92, 1.05), skin, neck, levels=2)
    sphere(f"{c['id']}_nose", 0.0085, (0, -0.044, 0.046), (1.0, 0.9, 0.85), clay(shade(d["skin"], 0.06), 0.5, 0.6), neck)
    for sx in (-1, 1):
        sphere(f"{c['id']}_ear{sx}", 0.010, (sx * 0.046, 0, 0.050), (0.5, 0.8, 1.0), skin, neck)
    eyes, lids = [], []
    for sx in (-1, 1):
        white = sphere(f"{c['id']}_eye{sx}", 0.0105, (sx * 0.0165, -0.038, 0.060), (1, 0.6, 1.1),
                       clay("#F7F3EA", 0.25, 0.1, 0.0), neck)
        sphere(f"{c['id']}_pupil{sx}", 0.0052, (sx * 0.0165, -0.0448, 0.0595), (1, 0.5, 1.15),
               clay(d.get("eyes", "#24160C"), 0.2, 0.0, 0.0), neck)
        lid = sphere(f"{c['id']}_lid{sx}", 0.0112, (sx * 0.0165, -0.0385, 0.0605), (1.08, 0.65, 0.05), skin, neck)
        eyes.append(white)
        lids.append(lid)
        brow = tube(f"{c['id']}_brow{sx}", [(sx * 0.008, -0.0435, 0.0752), (sx * 0.0170, -0.0452, 0.0778),
                                              (sx * 0.0255, -0.0425, 0.0750)], 0.0021, clay(shade(d["hair"]["color"], 0.1), 0.7),
                    neck)
        brow["side"] = sx
    if "glasses" in extras:
        for sx in (-1, 1):
            ring = bpy.data.curves.new(f"{c['id']}_lens{sx}", "CURVE")
            ring.dimensions, ring.bevel_depth = "3D", 0.0012
            sp = ring.splines.new("POLY")
            sp.points.add(23)
            for i in range(24):
                a = 2 * math.pi * i / 24
                sp.points[i].co = (sx * 0.0165 + 0.013 * math.cos(a), -0.047, 0.060 + 0.012 * math.sin(a), 1)
            sp.use_cyclic_u = True
            o = bpy.data.objects.new(ring.name, ring)
            link(o, neck)
            o.data.materials.append(clay("#1D1D20", 0.3, 0))
    # replacement mouths: closed smile, half open, open
    mouth_mat, dark = clay(shade(d["skin"], 0.45), 0.5, 0.2), clay("#3E1518", 0.4, 0.0, 0.0)
    m0 = tube(f"{c['id']}_mouth0", [(-0.011, -0.0435, 0.031), (0, -0.0455, 0.0265), (0.011, -0.0435, 0.031)], 0.0018,
              mouth_mat, neck)
    m1 = sphere(f"{c['id']}_mouth1", 0.0075, (0, -0.0435, 0.029), (1.25, 0.35, 0.55), dark, neck)
    m2 = sphere(f"{c['id']}_mouth2", 0.0095, (0, -0.0430, 0.028), (1.15, 0.35, 0.95), dark, neck)
    mouths = [m0, m1, m2]
    # hair
    if hs in ("short", "side_sweep", "swept_back", "curls", "bun", "long", "ponytail", "bob"):
        cap = sphere(f"{c['id']}_hair", 0.049, (0, 0.006, 0.062), (1.04, 1.0, 0.82), hair, neck, levels=2)
        if hs in ("bob", "long"):  # a cap over the crown, curtains at the sides, fullness at the back: the face stays clear
            cap.location, cap.scale = (0, 0.010, 0.066), (1.08, 1.0, 0.80)
            for sx in (-1, 1):
                sphere(f"{c['id']}_side{sx}", 0.030, (sx * 0.040, 0.004, 0.036 if hs == "bob" else 0.010),
                       (0.55, 1.05, 1.25 if hs == "bob" else 2.0), hair, neck)
            sphere(f"{c['id']}_hairback", 0.047, (0, 0.024, 0.036 if hs == "bob" else 0.004),
                   (1.10, 0.62, 0.95 if hs == "bob" else 1.7), hair, neck)
        if hs == "side_sweep":
            q = sphere(f"{c['id']}_quiff", 0.026, (0.010, -0.018, 0.095), (1.6, 1.0, 0.6), hair, neck)
            q.rotation_euler[1] = -0.35
        if hs == "swept_back":
            sphere(f"{c['id']}_pomp", 0.030, (0, -0.010, 0.100), (1.3, 1.1, 0.9), hair, neck)
        if hs == "curls":
            for i in range(16):
                a = math.pi * (0.1 + 0.8 * (i % 8) / 7)
                ring = 0 if i < 8 else 1
                sphere(f"{c['id']}_curl{i}", 0.012, (0.044 * math.cos(a) * (1 - 0.25 * ring), -0.010 + 0.02 * ring,
                                                     0.072 + 0.022 * math.sin(a) + 0.012 * ring), mat=hair, parent=neck)
        if hs == "bun":
            sphere(f"{c['id']}_bun", 0.020, (0.030, 0.034, 0.030), mat=hair, parent=neck)
        if hs == "ponytail":
            tube(f"{c['id']}_tail", [(0, 0.045, 0.075), (0, 0.065, 0.040), (0, 0.060, 0.000)], 0.010, hair, neck, 0.6)
    elif hs == "headscarf":
        sphere(f"{c['id']}_scarf", 0.054, (0, 0.006, 0.048), (1.1, 1.05, 1.15), hair, neck, levels=2)
        sphere(f"{c['id']}_scarfdrape", 0.05, (0, 0.010, -0.010), (1.25, 1.0, 0.9), hair, neck)
    if "beard" in extras:
        sphere(f"{c['id']}_beard", 0.040, (0, -0.012, 0.024), (1.0, 0.85, 0.75), hair, neck)
    if "moustache" in extras:
        sphere(f"{c['id']}_moustache", 0.008, (0, -0.045, 0.036), (1.6, 0.5, 0.45), hair, neck)
    if "bindi" in extras:
        sphere(f"{c['id']}_bindi", 0.0022, (0, -0.046, 0.071), mat=clay("#B8232E", 0.3, 0), parent=neck)
    if "earrings" in extras:
        for sx in (-1, 1):
            sphere(f"{c['id']}_earring{sx}", 0.0025, (sx * 0.047, -0.004, 0.038), mat=clay("#E2B856", 0.3, 0), parent=neck)
    return {"root": root, "neck": neck, "torso": torso, "torso_z": torso.scale[2], "arms": arms, "lids": lids,
            "mouths": mouths, "head": head}


# --------------------------------------------------------------------------- set
def build_set(job):
    pal = job["palette"]
    box("floor", (1.6, 1.2, 0.02), (0, 0.2, -0.01), clay("#8A6A50", 0.6, 1.6, 0), bevel=0.002)
    box("wall_back", (1.6, 0.02, 0.75), (0, 0.55, 0.375), clay(pal.get("background", "#E9E1D2"), 0.85, 0.7, 0))
    box("wall_side", (0.02, 1.0, 0.75), (-0.62, 0.1, 0.375), clay(shade(pal.get("background", "#E9E1D2"), 0.08), 0.85, 0.7, 0))
    box("skirting", (1.6, 0.012, 0.03), (0, 0.535, 0.015), clay(pal.get("primary", "#2E5B4F"), 0.6, 0.5))
    props = set(job["props"])
    if "desk" in job["furniture"]:
        box("desk_top", (0.34, 0.16, 0.012), (0.18, 0.30, 0.150), clay("#B98A5E", 0.55, 1.0, 0))
        for x in (0.03, 0.33):
            box(f"desk_leg{x}", (0.012, 0.14, 0.145), (x, 0.30, 0.072), clay("#6E5038", 0.6, 0.6, 0))
        if "laptop" in props:
            box("laptop_base", (0.09, 0.06, 0.004), (0.20, 0.28, 0.158), clay("#3A3D42", 0.4, 0.2, 0))
            scr = box("laptop_screen", (0.09, 0.004, 0.055), (0.20, 0.312, 0.186), clay("#2B2E33", 0.4, 0.2, 0))
            scr.rotation_euler[0] = -0.18
        if "mug" in props:
            bpy.ops.mesh.primitive_cylinder_add(radius=0.012, depth=0.026, location=(0.30, 0.27, 0.169))
            mug = bpy.context.object
            mug.data.materials.append(clay(pal.get("accent", "#D9A441"), 0.5, 0.8))
    if "plant" in props:
        bpy.ops.mesh.primitive_cylinder_add(radius=0.03, depth=0.05, location=(-0.50, 0.45, 0.025))
        bpy.context.object.data.materials.append(clay("#B5654A", 0.6, 1.2))
        for i in range(7):
            a = i * 2.4
            sphere(f"leaf{i}", 0.022, (-0.50 + 0.025 * math.cos(a), 0.45 + 0.025 * math.sin(a), 0.07 + 0.012 * (i % 3)),
                   (0.7, 0.5, 1.3), clay("#4F7A4A", 0.6, 1.2))
    if job.get("logo"):  # the organisation's logo as a framed poster on the back wall
        img = bpy.data.images.load(job["logo"])
        m = bpy.data.materials.new("poster")
        m.use_nodes = True
        tex = m.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image = img
        bsdf = m.node_tree.nodes["Principled BSDF"]
        mixc = m.node_tree.nodes.new("ShaderNodeMix")
        mixc.data_type = "RGBA"
        mixc.inputs["A"].default_value = (0.93, 0.91, 0.86, 1)
        m.node_tree.links.new(tex.outputs["Alpha"], mixc.inputs["Factor"])
        m.node_tree.links.new(tex.outputs["Color"], mixc.inputs["B"])
        m.node_tree.links.new(mixc.outputs["Result"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.8
        ar = img.size[0] / max(1, img.size[1])
        w = 0.22
        box("poster_frame", (w + 0.024, 0.008, w / ar + 0.024), (-0.25, 0.538, 0.48), clay("#3B342C", 0.5, 0.4, 0))
        bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))  # a plane maps the whole image
        pl = bpy.context.object
        pl.name = "poster"
        link(pl)
        pl.location, pl.scale, pl.rotation_euler = (-0.25, 0.533, 0.48), (w, w / ar, 1), (math.pi / 2, 0, 0)
        pl.data.materials.append(m)
    win = box("window", (0.30, 0.006, 0.22), (0.30, 0.537, 0.46), clay("#DDE7EC", 0.3, 0, 0))
    frame = clay("#F2EEE6", 0.6, 0.5, 0)
    for nm, size, loc in (("mullion_v", (0.010, 0.012, 0.22), (0.30, 0.531, 0.46)),
                          ("mullion_h", (0.30, 0.012, 0.010), (0.30, 0.531, 0.46)),
                          ("sill", (0.33, 0.035, 0.012), (0.30, 0.52, 0.346))):
        box(nm, size, loc, frame)
    em = win.active_material.node_tree.nodes["Principled BSDF"]
    if "Emission Color" in em.inputs:
        em.inputs["Emission Color"].default_value = (0.85, 0.92, 1.0, 1)
        em.inputs["Emission Strength"].default_value = 1.2 if job["lighting"]["key_k"] >= 4500 else 0.15


# --------------------------------------------------------------------------- light and camera
def build_light(lt):
    def area(name, loc, energy, kelvin, size, aim=(0, 0.25, 0.2)):
        data = bpy.data.lights.new(name, "AREA")
        data.energy, data.color, data.size = energy, kelvin_rgb(kelvin), size
        o = bpy.data.objects.new(name, data)
        link(o)
        o.location = loc
        d = Vector(aim) - Vector(loc)
        o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        return o
    soft = 0.15 + 0.85 * lt["softness"]
    area("key", (-0.55, -0.55, 0.75), 38.0, lt["key_k"], 0.15 + 0.6 * soft)
    area("fill", (0.65, -0.65, 0.35), 38.0 * lt["fill"], lt["key_k"] + 1200, 0.9)
    area("rim", (0.35, 0.9, 0.6), 38.0 * lt["rim"] * 1.4, lt["key_k"] + 2500, 0.25)
    if lt.get("practicals"):
        data = bpy.data.lights.new("practical", "POINT")
        data.energy, data.color, data.shadow_soft_size = 2.5, kelvin_rgb(2600), 0.03
        o = bpy.data.objects.new("practical", data)
        link(o)
        o.location = (0.05, 0.32, 0.30)
    world = bpy.data.worlds.new("world")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*kelvin_rgb(lt["key_k"] + 1500), 1)
    bg.inputs["Strength"].default_value = 0.10 + 0.25 * lt["fill"]
    bpy.context.scene.world = world
    vs = bpy.context.scene.view_settings
    try:
        vs.view_transform, vs.look = "AgX", "AgX - Medium High Contrast"
    except TypeError:
        pass
    vs.exposure = lt["exposure"]


def build_camera(cam_job, chars):
    data = bpy.data.cameras.new("cam")
    data.lens, data.sensor_width = cam_job["lens"], 36.0
    data.dof.use_dof, data.dof.aperture_fstop = True, cam_job["fstop"]
    cam = bpy.data.objects.new("cam", data)
    link(cam)
    bpy.context.scene.camera = cam
    target = empty("cam_target", (0, 0, 0))
    con = cam.constraints.new("TRACK_TO")
    con.target, con.track_axis, con.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
    focus = chars.get(cam_job.get("focus") or "")
    data.dof.focus_object = focus["head"] if focus else target
    for f, (pos, aim) in cam_job["keys"].items():
        cam.location = pos
        cam.keyframe_insert("location", frame=int(f))
        target.location = aim
        target.keyframe_insert("location", frame=int(f))


# --------------------------------------------------------------------------- acting
def act(chars, tracks, step):
    for cid, tr in tracks.items():
        ch = chars[cid]
        for f, st in tr.items():
            f = int(f)
            for i, m in enumerate(ch["mouths"]):
                key(m, "hide_render", f, i != st["mouth"])
                key(m, "hide_viewport", f, i != st["mouth"])
            for lid in ch["lids"]:
                lid.scale[2] = 1.0 if st["blink"] else 0.05
                lid.keyframe_insert("scale", frame=f, index=2)
            ch["neck"].rotation_euler = (st["head"][0], st["head"][2], st["head"][1])
            ch["neck"].keyframe_insert("rotation_euler", frame=f)
            ch["torso"].scale[2] = ch["torso_z"] * st["breath"]  # breathing scales the rest size
            ch["torso"].keyframe_insert("scale", frame=f, index=2)
            for side in ("left", "right"):
                sh, el = ch["arms"][side]
                sh.rotation_euler = st["arms"][side]["shoulder"]
                sh.keyframe_insert("rotation_euler", frame=f)
                el.rotation_euler = st["arms"][side]["elbow"]
                el.keyframe_insert("rotation_euler", frame=f)
    for n in BOIL:  # the surface shimmer changes once per drawing
        for f in range(JOB["frame_start"], JOB["frame_end"] + 1, step):
            n.inputs["W"].default_value = (f // step) * 0.37
            n.inputs["W"].keyframe_insert("default_value", frame=f)


# --------------------------------------------------------------------------- run
def main():
    sc = bpy.context.scene
    for o in list(sc.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    build_set(JOB)
    build_light(JOB["lighting"])
    chars = {c["id"]: build_character(c) for c in JOB["characters"]}
    build_camera(JOB["camera"], chars)
    act(chars, JOB["tracks"], JOB["step"])
    if os.environ.get("SASTUDIO_SM_DUMP"):  # diagnostics: every object's evaluated size, no render
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        for o in sorted(sc.objects, key=lambda o: o.name):
            if o.type in ("MESH", "CURVE"):
                print("DUMP", o.name, [round(v, 3) for v in o.evaluated_get(dg).dimensions],
                      [round(v, 3) for v in o.matrix_world.translation])
        return
    for o in bpy.data.objects:  # stop motion: no in-betweens
        ad = o.animation_data
        if ad and ad.action and hasattr(ad.action, "fcurves"):
            for fc in ad.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "CONSTANT" if fc.data_path.startswith("hide") else "BEZIER"
    sc.render.engine = "BLENDER_EEVEE"
    try:
        sc.eevee.taa_render_samples = JOB["samples"]
    except AttributeError:
        pass
    sc.render.resolution_x, sc.render.resolution_y = JOB["width"], JOB["height"]
    sc.render.fps = 24
    sc.frame_start, sc.frame_end, sc.frame_step = JOB["frame_start"], JOB["frame_end"], JOB["step"]
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = JOB["out"] + "/"
    bpy.ops.render.render(animation=True)
    print("STOPMOTION done", JOB["frame_start"], JOB["frame_end"])


main()
