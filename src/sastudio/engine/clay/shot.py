"""Render one clay shot from a JSON spec. Runs inside Blender:

    blender -b --factory-startup -P engine/clay/shot.py -- spec.json

The spec is written by `sastudio` (see src/sastudio/render/clay.py). It only contains numbers,
colours, character ids and file paths chosen by sastudio; this script never evaluates code
from it.

Spec keys: rig, out (folder for numbered PNGs), width, height, fps, frames, step (render every
Nth frame and hold it: 2 = "on twos", the stop-motion cadence), samples, device (GPU|CPU),
transparent, set {wall, floor}, cast [{id, x, y, yaw}], camera {target, shot}, speech
[{who, start, end, cues: [[seconds, shape]], env: [0..1 per frame]}], mood {id: smile}.
"""

import json
import math
import os
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SPEC = json.load(open(sys.argv[sys.argv.index("--") + 1], encoding="utf-8"))
os.environ["SASTUDIO_RIG"] = SPEC["rig"]

bpy.ops.wm.read_factory_settings(use_empty=True)
import numpy as np  # noqa: E402  (Blender ships numpy)
import faceops  # noqa: E402
from claymat import clay_rgb  # noqa: E402
from puppet import Puppet  # noqa: E402

CTRL, FI = faceops.CTRL, faceops.IDX
FPS = int(SPEC.get("fps", 24))


def FV(**k):
    v = np.zeros(len(CTRL))
    for a, b in k.items():
        if a in FI:
            v[FI[a]] = b
        else:
            v[FI[a + "L"]] = b
            v[FI[a + "R"]] = b
    return v


# Rhubarb mouth shapes as muscle positions (modest: a real mouth barely opens to talk), scaled for clay.
VF = {k: v * 1.3 for k, v in dict(
    A=FV(), B=FV(jaw=.13, wide=.32, upLip=.22), C=FV(jaw=.38, wide=.22, upLip=.12), D=FV(jaw=.72, wide=.06),
    E=FV(jaw=.36, pucker=.34), F=FV(jaw=.15, pucker=.92), G=FV(jaw=.08, fv=1, upLip=.35),
    H=FV(jaw=.34, tongueUp=1, wide=.1), X=FV()).items()}
KERNEL = np.array([.07, .22, .42, .22, .07])  # coarticulation: shapes melt into each other


def visemes(line, n):
    a = np.zeros((n, len(CTRL)))
    cues = line.get("cues") or []
    if cues:
        for i, (st, m) in enumerate(cues):
            en = cues[i + 1][0] if i + 1 < len(cues) else (line["end"] - line["start"]) / FPS
            a[max(0, int(st * FPS) - 1):int(en * FPS) + 1] = VF.get(m, VF["X"])  # mouth leads the sound by a frame
    else:  # no Rhubarb: open the jaw with the loudness of the voice
        for f, e in enumerate(line.get("env") or []):
            if f < n:
                a[f] = VF["C"] * min(1.0, e * 1.2)
    return np.apply_along_axis(lambda v: np.convolve(v, KERNEL, "same"), 0, a)


_h = lambda n: (math.sin(n * 127.1) * 43758.5453) % 1  # noqa: E731


def blink_at(f, seed=0):
    at, i = int(_h(seed + .5) * 40), 0
    while at + 8 < f and i < 4000:
        at += 56 + int(_h(seed + i * 1.37) * 110)
        i += 1
    d = f - at
    return 0 if d < 0 or d > 5 else [.6, 1, 1, .6, .25, 0][d]


# ------------------------------------------------------------------ scene
s = bpy.context.scene
s.render.engine = "CYCLES"
s.cycles.samples = int(SPEC.get("samples", 32))
s.cycles.use_denoising = True
if SPEC.get("device", "GPU") == "GPU":
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            gpus = [d for d in prefs.devices if d.type == kind]
            if gpus:
                for d in prefs.devices:
                    d.use = d.type == kind
                s.cycles.device = "GPU"
                print("SHOT device", kind, [d.name for d in gpus])
                break
        except (TypeError, ValueError):
            continue
    else:
        s.cycles.device = "CPU"
        print("SHOT device CPU (no GPU backend available)")
s.render.resolution_x, s.render.resolution_y = int(SPEC["width"]), int(SPEC["height"])
s.render.resolution_percentage = 100
s.view_settings.view_transform = "AgX"
s.view_settings.look = "AgX - Medium High Contrast"
s.render.film_transparent = bool(SPEC.get("transparent"))
s.render.image_settings.file_format = "PNG"
s.render.image_settings.color_mode = "RGBA" if SPEC.get("transparent") else "RGB"
w = bpy.data.worlds.new("w")
s.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (.8, .68, .55, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = .35


def light(loc, energy, size, color, rot):
    bpy.ops.object.light_add(type="AREA", location=loc, rotation=rot)
    o = bpy.context.object
    o.data.energy, o.data.size, o.data.color = energy, size, color


light((-7, -9, 10), 1500, 8, (1, .87, .7), (.85, 0, -.6))     # warm key
light((9, -6, 5), 300, 7, (.65, .75, 1), (1.2, 0, .95))        # cool fill
light((2, 6, 8), 700, 4, (1, .78, .55), (-.7, .1, .2))         # rim
st = SPEC.get("set") or {}
if not SPEC.get("transparent"):
    bpy.ops.mesh.primitive_plane_add(size=60)
    bpy.context.object.data.materials.append(clay_rgb(st.get("floor", "#8a6a4a")))
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 4.5, 0), rotation=(1.5708, 0, 0))
    bpy.context.object.data.materials.append(clay_rgb(st.get("wall", "#d9cbb5")))

cast = {}
for c in SPEC["cast"]:
    P = Puppet(c["id"])
    cast[c["id"]] = (P, c)

N = int(SPEC["frames"])
speech = SPEC.get("speech") or []
fc_track = {}
for i, ln in enumerate(speech):
    fc_track[i] = visemes(ln, ln["end"] - ln["start"] + 3)
mood = SPEC.get("mood") or {}


def speaker_at(f):
    for i, ln in enumerate(speech):
        if ln["start"] <= f < ln["end"]:
            return i, ln
    return None, None


def pose_all(f):
    i, ln = speaker_at(f)
    talker = ln["who"] if ln else None
    for k, (cid, (P, c)) in enumerate(cast.items()):
        x, y, yaw = c.get("x", 0.0), c.get("y", 0.0), c.get("yaw", 0.0)
        seed = 7 + k * 13
        breathe = .012 * math.sin(f / FPS * 2 * math.pi / 3.6 + k)
        fc = FV(smile=float(mood.get(cid, .18)))
        if talker == cid:
            arr = fc_track[i]
            j = f - ln["start"]
            if 0 <= j < len(arr):
                fc = fc + arr[j]
        look = (0.0, 0.0)
        head = (0.0, .02 * math.sin(f / FPS * 1.3 + k), 0.0)
        if talker and talker != cid and talker in cast:
            tx = cast[talker][1].get("x", 0.0)
            turn = max(-.35, min(.35, (tx - x) * .18))
            head = (0.0, head[1], turn)
            look = (max(-.6, min(.6, (tx - x) * .3)), 0.0)
        P.pose(loc=(x, y, 0), yaw=yaw, bend=(breathe, 0), head=head, look=look, blink=blink_at(f, seed),
               fc=fc, footL=(x - .24, y + .05, 0), footR=(x + .24, y - .05, 0))


# camera
pose_all(0)
bpy.context.view_layer.update()
cam_spec = SPEC.get("camera") or {}
target = cam_spec.get("target") or next(iter(cast))
P, c = cast[target]
head_z = P.head.matrix_world.translation.z
tx = c.get("x", 0.0)
shot = cam_spec.get("shot", "medium")
dist, lens, aim = dict(portrait=(7.2, 50, head_z - .55), close=(5.6, 50, head_z - .25), medium=(8.5, 50, head_z - .9),
                       wide=(15.0, 40, head_z - 1.5))[shot]
others = [cc.get("x", 0.0) for _, (__, cc) in cast.items()]
cx = tx if shot in ("portrait", "close") else (min(others) + max(others)) / 2
bpy.ops.object.camera_add(location=(cx + cam_spec.get("offset", 0.0), -dist, aim + .35), rotation=(math.radians(86), 0, 0))
cam = bpy.context.object
cam.data.lens = lens
s.camera = cam

out = SPEC["out"]
os.makedirs(out, exist_ok=True)
step = max(1, int(SPEC.get("step", 2)))
t0 = time.time()
for f in range(0, N, step):
    path = os.path.join(out, f"{f + 1:05d}.png")
    if os.path.exists(path):
        continue
    pose_all(f)
    s.frame_set(f)
    s.render.filepath = path + ".part.png"
    bpy.ops.render.render(write_still=True)
    os.replace(path + ".part.png", path)
    print(f"SHOT frame {f + 1}/{N} {time.time() - t0:.1f}s", flush=True)
print("SHOT done", N, "frames", round(time.time() - t0, 1), "s")
