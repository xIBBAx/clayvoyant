"""Film one shot of a clay scene from a JSON job. Runs inside Blender:

    blender -b --factory-startup -P engine/clay/film.py -- job.json

The job is written by `sastudio` (src/sastudio/stopmotion). It holds only numbers, colours, names chosen from the
lists in this package and file paths chosen by sastudio; this script never evaluates code from it.

A job describes a whole scene (the set, the light, the cast, every line and every acting key) and the frames of it
to film with one camera. Acting is a pure function of the frame, so shots of one scene always agree with each other,
any shot can be re-filmed alone, and a shot that stopped half way resumes at the first missing frame.

Job keys: rig, out, width, height, samples, device (GPU|CPU), fps, step (2 = on twos), frames [first, last),
set {name, palette, org, seed, time}, lighting {name, key_k, fill, rim, exposure, softness, practicals},
cast [{id, mark | pos, face, seat, style, feeling}], lines [{who, start, end, cues, to, manual}],
keys [{who, frame, g, f, look, seat, walk, speed, ...}], door [[open, close], ...],
camera {shot, who, focus, lens, fstop, move, height}, font, transparent, mode (film | portrait | sheet).
"""
import json
import math
import os
import sys
import time

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
JOB = json.load(open(sys.argv[sys.argv.index('--') + 1], encoding='utf-8'))
os.environ['SASTUDIO_RIG'] = JOB['rig']

bpy.ops.wm.read_factory_settings(use_empty=True)
from mathutils import Vector as V  # noqa: E402

import acting as A  # noqa: E402
import sets as SETS  # noqa: E402
import setkit as K  # noqa: E402
from puppet import Puppet  # noqa: E402

FPS = int(JOB.get('fps', 24))
MODE = JOB.get('mode', 'film')
K.FONT = JOB.get('font')
sm = A.sm
clamp = A.clamp

# ------------------------------------------------------------------ render settings
s = bpy.context.scene
s.render.engine = 'CYCLES'
s.cycles.samples = int(JOB.get('samples', 16))
s.cycles.use_denoising = True
s.cycles.max_bounces = 4
s.cycles.diffuse_bounces = 2
s.cycles.glossy_bounces = 2
s.cycles.transmission_bounces = 4
s.cycles.transparent_max_bounces = 6
s.cycles.caustics_reflective = s.cycles.caustics_refractive = False
s.render.use_persistent_data = True          # the set is built once; only what moves is sent to the renderer again
if JOB.get('device', 'GPU') == 'GPU':
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for kind in ('OPTIX', 'CUDA', 'HIP', 'METAL', 'ONEAPI'):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            gpus = [d for d in prefs.devices if d.type == kind]
            if gpus:
                for d in prefs.devices:
                    d.use = d.type == kind
                s.cycles.device = 'GPU'
                print('FILM device', kind, [d.name for d in gpus], flush=True)
                break
        except (TypeError, ValueError):
            continue
    else:
        s.cycles.device = 'CPU'
        print('FILM device CPU (no GPU backend available)', flush=True)
else:
    print('FILM device CPU', flush=True)
s.render.resolution_x, s.render.resolution_y = int(JOB['width']), int(JOB['height'])
s.render.resolution_percentage = 100
s.view_settings.view_transform = 'AgX'
s.view_settings.look = 'AgX - Medium High Contrast'
s.render.film_transparent = bool(JOB.get('transparent'))
s.render.image_settings.file_format = 'PNG'
s.render.image_settings.color_mode = 'RGBA' if JOB.get('transparent') else 'RGB'
s.render.image_settings.compression = 30

# ------------------------------------------------------------------ the place
SET = JOB.get('set') or {}
TIME = SET.get('time', 'day')
C = dict(palette=SET.get('palette') or {}, org=SET.get('org'), seed=int(SET.get('seed', 1)), time=TIME)
SKIES = dict(day=('#5e9bd6', '#dfeaf4', '#b9a98f', 1.0), morning=('#7fb0dc', '#f6e3c8', '#b9a98f', .9),
             evening=('#39507f', '#f2a66a', '#6f5a4a', .55), night=('#070b18', '#1a2440', '#0b0d14', .06))
top, hor, gnd, sky_st = SKIES.get(TIME, SKIES['day'])
STG = SETS.build(SET.get('name', 'studio'), C)
K.sky(sky_st if STG['outdoor'] else sky_st * .55, top, hor, gnd)
PRACTICALS = [o for o in bpy.data.objects if o.type == 'LIGHT']


def light_stage(L):
    """Key, fill and rim from the lighting preset; the sun for daylight; the set's own lamps for the rest."""
    kcol = K.kelvin(L.get('key_k', 4500))
    soft = L.get('softness', .7)
    night = TIME == 'night'
    kE = 1700 * (.55 if STG['outdoor'] and not night else 1)
    key = K.aim(K.lamp((-7.5, -9, 9.5), kE, 3 + 9 * soft, kcol, shadow=True), (0, .8, 2.4))
    key.data.shadow_soft_size = .5
    K.aim(K.lamp((9, -7, 5), kE * L.get('fill', .5) * .42, 8, tuple(c * f for c, f in zip(kcol, (.82, .9, 1.08))), shadow=False), (0, .8, 2.2))
    K.aim(K.lamp((3.5, STG['back'] - 1.3, 7.2), kE * L.get('rim', .3) * 1.5, 3, K.kelvin(L.get('key_k', 4500) - 900), shadow=False), (0, .5, 2.6))
    for o in PRACTICALS:
        o.data.energy *= 1.0 if L.get('practicals') or night else .3
    if TIME in ('day', 'morning', 'evening') and (STG['outdoor'] or STG['windows']):
        el, col, e = dict(day=(46, (1, .93, .8), 4.2), morning=(27, (1, .86, .68), 3.6), evening=(11, (1, .58, .3), 3.4))[TIME]
        e *= 1 - .45 * clamp((4500 - L.get('key_k', 4500)) / 2000)
        if L.get('name') in ('dramatic', 'suspense', 'night_practical'):
            e *= .45
        _, src = K.sun(-38 if STG['outdoor'] else -47, el, col, e * (1.0 if STG['outdoor'] else .9), soft=.02 + .05 * soft)
        if not STG['outdoor']:
            # the sun reaches the room through a window nobody sees: its frame draws the light across the floor and the far wall
            K.gobo(src, (0, 1.4, 1.6), dist=18, w=20, h=13, cols=4, rows=3, bar=.4, blinds=L.get('name') == 'suspense')
    elif night:
        K.sun(-150, 38, (.55, .66, 1), .35, soft=.06)
    s.view_settings.exposure = float(L.get('exposure', 0)) + (.35 if not STG['outdoor'] else 0)


light_stage(JOB.get('lighting') or {})

# ------------------------------------------------------------------ the cast
PERF = A.Performance(FPS)
MARKS = STG['marks']
spots = list(STG['spots'])


def where(c):
    """-> (x, y), facing, seat height or None"""
    m = MARKS.get(c.get('mark') or '')
    if m:
        return m['pos'], c.get('face', m.get('face', 0.0)), (m.get('seat') if c.get('seat', True) else None)
    if c.get('pos'):
        return tuple(c['pos']), c.get('face', 0.0), (A.SEAT_H if c.get('seat') is True else None)
    return (spots.pop(0) if spots else (0, 0)), c.get('face', None), None


for c in JOB.get('cast') or []:
    pos, face, seat = where(c)
    init = dict(f=c.get('feeling', 'neutral'), face=face)
    if seat:
        init['seat'] = seat
    start = c.get('enter_from')
    p0 = MARKS[start]['pos'] if start in MARKS else pos
    a = PERF.add(A.Actor(c['id'], Puppet(c.get('rig') or c['id']), p0, c.get('style'), **init))
    a.home = pos
    if 'on' in c:
        a.init['on'] = bool(c['on'])
for ln in JOB.get('lines') or []:
    PERF.say(ln['who'], ln['start'], ln['end'], ln.get('cues') or [], ln.get('to'), ln.get('manual') or ())
for nm, t in STG['things'].items():
    PERF.things[nm] = t
PERF.direct()
for k in JOB.get('keys') or []:
    a = PERF.actors.get(k.get('who'))
    if a is None:
        continue
    k = dict(k)
    f = int(k.pop('frame', 0))
    if 'walk' in k:
        to = k.pop('walk')
        m = MARKS.get(to) if isinstance(to, str) else None
        end = a.walk(f, m['pos'] if m else (a.home if to == 'home' else tuple(to)), speed=k.pop('speed', None))
        if m and m.get('seat') and k.pop('sit', True):
            a.key(end - 8, dict(seat=m['seat'], face=m.get('face', 0)))
        elif m:
            a.key(end - 10, dict(face=m.get('face', 0)))
    if isinstance(k.get('seat'), str):
        k['seat'] = (MARKS.get(k['seat']) or {}).get('seat') or A.SEAT_H
    if isinstance(k.get('look'), list):
        k['look'] = tuple(k['look'])
    a.key(f, k)
PERF.finish()

# ------------------------------------------------------------------ the camera
CAM = JOB.get('camera') or {}
cam_data = bpy.data.cameras.new('camera')
cam = bpy.data.objects.new('camera', cam_data)
bpy.context.scene.collection.objects.link(cam)
s.camera = cam
PERF.cam = cam
cam_data.sensor_width = 36
cam_data.clip_start, cam_data.clip_end = .1, 2000
cam_data.lens = float(CAM.get('lens') or 40)
cam_data.dof.use_dof = MODE == 'film' and CAM.get('shot') not in ('establishing',)
cam_data.dof.aperture_fstop = float(CAM.get('fstop') or 4.0) * .55      # a miniature: shallower than life
# how tall the frame is at the subject, and where it is centred from the eye line
FRAME_H = dict(wide=5.3, medium=2.9, two_shot=3.2, over_shoulder=2.2, close_up=1.55, extreme_close_up=.8, reaction=1.55, insert=1.0, portrait=4.6)
AIM_DZ = dict(wide=-1.45, medium=-.62, two_shot=-.55, over_shoulder=-.08, close_up=-.1, extreme_close_up=-.06, reaction=-.1, portrait=-1.3)
F0, F1 = (int(x) for x in JOB.get('frames') or (0, 1))
STEP = max(1, int(JOB.get('step', 2)))


def vfov():
    return 2 * math.atan((36 * s.render.resolution_y / s.render.resolution_x) / 2 / cam_data.lens)


def hfov():
    return 2 * math.atan(36 / 2 / cam_data.lens)


def eyes(name):
    a = PERF.actors[name]
    return a.P.head_world.copy()


def thing_pos(t):
    o = PERF.things.get(t)
    if o is None:
        return None
    return o.matrix_world.translation.copy() if hasattr(o, 'matrix_world') else V(o)


def frame_shot():
    """Where the camera stands at the start of the shot and what it looks at, from the people as they really are."""
    shot = CAM.get('shot', 'medium')
    who = [w for w in CAM.get('who') or [] if w in PERF.actors and PERF.actors[w].P.vis] or [n for n, a in PERF.actors.items() if a.P.vis][:1]
    if shot == 'insert':
        tp = thing_pos((CAM.get('who') or ['?'])[0]) or V((0, 2, 1.6))
        return tp + V((.5, -2.4, .9)), tp, None
    if shot == 'establishing' or not who:
        return V((CAM.get('x', .8), -11.5, 3.7)), V((0, 2.2, 2.5)), None
    heads = [eyes(w) for w in who]
    c = sum(heads, V((0, 0, 0))) / len(heads)
    aim = V((c.x, c.y, c.z + AIM_DZ.get(shot, -.5)))
    dist = (FRAME_H.get(shot, 2.9) / 2) / math.tan(vfov() / 2)
    if len(heads) > 1:
        span = max(h.x for h in heads) - min(h.x for h in heads)
        dist = max(dist, (span / 2 + 1.0) / math.tan(hfov() / 2))
    if shot == 'over_shoulder' and len(who) >= 2:
        sp, ls = heads[0], heads[1]
        d = V((sp.x - ls.x, sp.y - ls.y, 0))
        n = d.length or 1
        d /= n
        side = V((-d.y, d.x, 0)) * (1 if ls.x > sp.x else -1)
        pos = ls - d * 2.2 + side * .62 + V((0, 0, .22))
        pos.y = min(pos.y, min(sp.y, ls.y) - 1.2) if abs(d.y) < .5 else pos.y
        return pos, V((sp.x, sp.y, sp.z - .1)), who[0]
    # stand on the side the subject is turned towards, for a three-quarter view of the face
    yaw = sum((PERF.actors[w].last_yaw or 0) for w in who) / len(who)
    ang = clamp(yaw * (.8 if len(who) == 1 else .3), -.6, .6)
    pos = V((aim.x + math.sin(ang) * dist, aim.y - math.cos(ang) * dist, aim.z + .12))
    pos.z += dict(low=-.75, high=1.0).get(CAM.get('height', 'eye'), 0) * (dist / 6) ** .5
    return pos, aim, (CAM.get('focus') if CAM.get('focus') in PERF.actors else who[0])


def look_through(pos, aim):
    cam.location = pos
    cam.rotation_euler = (aim - pos).to_track_quat('-Z', 'Y').to_euler()


PERF.pose(F0)
bpy.context.view_layer.update()
POS0, AIM0, FOCUS = frame_shot()
HEAD0 = eyes(FOCUS) if FOCUS else None


def camera_at(f):
    t = sm(clamp((f - F0) / max(1, F1 - F0 - 1)))
    pos, aim = POS0.copy(), AIM0.copy()
    mv = CAM.get('move', 'static')
    if FOCUS and mv in ('pan', 'track', 'tilt'):
        d = eyes(FOCUS) - HEAD0
        if mv == 'track':
            pos += V((d.x, d.y * .5, 0))
            aim += V((d.x, d.y, d.z))
        else:
            aim += d
    elif mv == 'push_in':
        pos = aim + (pos - aim) * (1 - .16 * t)
    elif mv == 'pull_out':
        pos = aim + (pos - aim) * (1 + .22 * t)
    elif mv == 'orbit':
        ang = .2 * (t - .5)
        d = pos - aim
        pos = aim + V((d.x * math.cos(ang) - d.y * math.sin(ang), d.x * math.sin(ang) + d.y * math.cos(ang), d.z))
    look_through(pos, aim)
    if cam_data.dof.use_dof:
        tgt = eyes(FOCUS) if FOCUS else aim
        cam_data.dof.focus_distance = max(.3, (tgt - cam.location).dot((aim - pos).normalized()))


def door_at(f):
    leaf = STG.get('door')
    if leaf is None:
        return
    a = 0.0
    for o, c_ in JOB.get('door') or []:
        a = max(a, sm(clamp((f - o) / 12)) * (1 - sm(clamp((f - c_) / 14))))
    leaf.rotation_euler = (0, 0, -1.45 * a * (1 if leaf.location.x < 0 else -1))


# ------------------------------------------------------------------ portraits and sheets (one still, no scene)
if MODE in ('portrait', 'sheet'):
    PERF.pose(0)
    PERF.pose(0)
    bpy.context.view_layer.update()
    P0, A0, _ = frame_shot()
    look_through(P0, A0)
    os.makedirs(JOB['out'], exist_ok=True)
    s.render.filepath = os.path.join(JOB['out'], '000001.png')
    bpy.ops.render.render(write_still=True)
    print('FILM done 1 frames', flush=True)
    sys.exit(0)

# ------------------------------------------------------------------ film it
out = JOB['out']
os.makedirs(out, exist_ok=True)
frames = [f for f in range(F0, F1, STEP) if not os.path.exists(os.path.join(out, f'{f:06d}.png'))]
print(f'FILM frames {len(frames)} of {len(range(F0, F1, STEP))} to do', flush=True)
t0 = time.time()
steps = sorted({f for a in PERF.actors.values() for f in a.steps()})
json.dump(dict(steps=steps), open(os.path.join(out, 'events.json'), 'w'))
for n, f in enumerate(frames):
    PERF.pose(f)
    door_at(f)
    bpy.context.view_layer.update()
    camera_at(f)
    s.frame_set(f)
    path = os.path.join(out, f'{f:06d}.png')
    s.render.filepath = path + '.part.png'
    bpy.ops.render.render(write_still=True)
    os.replace(path + '.part.png', path)
    print(f'FILM frame {n + 1}/{len(frames)} f{f} {time.time() - t0:.1f}s', flush=True)
print('FILM done', len(frames), 'frames', round(time.time() - t0, 1), 's', flush=True)
