"""Film one shot of a clay scene from a JSON job. Runs inside Blender:

    blender -b --factory-startup -P engine/clay/film.py -- job.json

The job is written by `sastudio` (src/sastudio/stopmotion). It holds only numbers, colours, names chosen from the
lists in this package and file paths chosen by sastudio; this script never evaluates code from it.

A job describes a whole scene (the set, the light, the cast, every line and every acting key) and the frames of it
to film with one camera. Acting is a pure function of the frame, so shots of one scene always agree with each other,
any shot can be re-filmed alone, and a shot that stopped half way resumes at the first missing frame.

Job keys: rig, out, width, height, samples, device (GPU|CPU), fps, frames [the scene frames to film],
set {name, palette, org, seed, time}, lighting {name, key_k, fill, rim, exposure, softness, practicals},
cast [{id, mark | pos, face, seat, style, feeling}], lines [{who, start, end, cues, to, manual}],
keys [{who, frame, g, f, look, seat, walk, speed, ...}], door [[open, close], ...], carry [{who, prop, start, end}],
camera {shot, who, focus, lens, fstop, move, height} or {shot: opening, style, thing, who}, font, transparent,
mode (film | portrait | export), export (file),
aliases {bones, shapes} (names a guest model's rig and face keys may go by).
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
s.cycles.debug_bvh_type = 'DYNAMIC_BVH'       # puppets change shape every frame: refit their structures, don't rebuild them
try:
    s.cycles.denoising_use_gpu = True
except (AttributeError, TypeError):
    pass
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
C = dict(palette=SET.get('palette') or {}, org=SET.get('org'), seed=int(SET.get('seed', 1)), time=TIME, clock=SET.get('clock'))
SKIES = dict(day=('#5e9bd6', '#dfeaf4', '#b9a98f', 1.0), morning=('#7fb0dc', '#f6e3c8', '#b9a98f', .9),
             evening=('#39507f', '#f2a66a', '#6f5a4a', .55), night=('#070b18', '#1a2440', '#0b0d14', .06))
top, hor, gnd, sky_st = SKIES.get(TIME, SKIES['day'])
# a still on a transparent ground needs no place at all
STG = SETS.stage(dict(centre=SETS.mark(0, 0)), [(0, 0)], back=7) if JOB.get('transparent') else SETS.build(SET.get('name', 'studio'), C)
K.sky((sky_st if STG['outdoor'] else sky_st * .55) * float((JOB.get('lighting') or {}).get('sky', 1)), top, hor, gnd)
PRACTICALS = [o for o in bpy.data.objects if o.type == 'LIGHT']


def _hex(h):
    h = str(h).lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _around(az, el, r):
    """A point r from the acting area, az degrees round from behind the camera (+90 camera right), el above it."""
    a, b = math.radians(az), math.radians(el)
    return (math.sin(a) * math.cos(b) * r, -math.cos(a) * math.cos(b) * r, math.sin(b) * r)


def light_stage(L):
    """Key, fill and rim from the lighting preset; the sun for daylight; the set's own lamps for the rest.
    A scene's `direction.light` turns the knobs: where the key and the sun come from, how strong, the tint, a bounce."""
    tint = _hex(L['tint']) if L.get('tint') else None
    kcol = K.kelvin(L.get('key_k', 4500))
    if tint:
        kcol = tuple(c * t for c, t in zip(kcol, tint, strict=False))
    soft = L.get('softness', .7)
    night = TIME == 'night'
    kE = 1700 * (.55 if STG['outdoor'] and not night else 1)
    turned = 'key_azimuth' in L or 'key_height' in L
    kpos = _around(L.get('key_azimuth', -39.8), L.get('key_height', 39.0), 15.09) if turned else (-7.5, -9, 9.5)
    key = K.aim(K.lamp(kpos, kE * float(L.get('key_strength', 1)), 3 + 9 * soft, kcol, shadow=True), (0, .8, 2.4))
    key.data.shadow_soft_size = .5
    fpos = _around(-L.get('key_azimuth', -39.8) * 1.3, 24, 12.45) if turned else (9, -7, 5)
    K.aim(K.lamp(fpos, kE * L.get('fill', .5) * .42, 8, tuple(c * f for c, f in zip(kcol, (.82, .9, 1.08))), shadow=False), (0, .8, 2.2))
    if L.get('bounce'):
        # a warm board on the floor in front of the people: it lifts faces when the light is behind them
        K.aim(K.lamp((0, -5.5, .35), kE * float(L['bounce']) * .32, 7, (1, .95, .88), shadow=False), (0, .8, 2.0))
    K.aim(K.lamp((3.5, STG['back'] - 1.3, 7.2), kE * L.get('rim', .3) * 1.5, 3, K.kelvin(L.get('key_k', 4500) - 900), shadow=False), (0, .5, 2.6))
    for o in PRACTICALS:
        o.data.energy *= 1.0 if L.get('practicals') or night else .3
    if TIME in ('day', 'morning', 'evening') and (STG['outdoor'] or STG['windows']):
        el, col, e = dict(day=(46, (1, .93, .8), 4.2), morning=(27, (1, .86, .68), 3.6), evening=(11, (1, .58, .3), 3.4))[TIME]
        e *= 1 - .45 * clamp((4500 - L.get('key_k', 4500)) / 2000)
        if L.get('name') in ('dramatic', 'suspense', 'night_practical'):
            e *= .45
        if not STG['outdoor'] and TIME == 'evening':
            e *= .45        # indoors at dusk the lamps do the work; the last sun only draws a warm bar across the wall
        el = L.get('sun_height', el)
        e *= float(L.get('sun_strength', 1))
        _, src = K.sun(L.get('sun_azimuth', -38 if STG['outdoor'] else -47), el, col, e * (1.0 if STG['outdoor'] else .9),
                       soft=.02 + .05 * soft)
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
        # a seat faces its table; on a standing mark nobody is pinned to the lens: they turn to whoever matters (acting.res_face)
        seat = m.get('seat') if c.get('seat', True) else None
        return m['pos'], c.get('face', m.get('face')), seat
    if c.get('pos'):
        return tuple(c['pos']), c.get('face', 0.0), (A.SEAT_H if c.get('seat') is True else None)
    return (spots.pop(0) if spots else (0, 0)), c.get('face', None), None


def offscreen(pos):
    """Out of sight, on the nearer side: where someone walks in from, or out to, when the set has no door."""
    return ((-13.5 if pos[0] < 0 else 13.5), pos[1] + .6)


TAKEN = {c.get('mark') for c in JOB.get('cast') or []}
DOORS = [list(d) for d in JOB.get('door') or []]     # [open, close] frames


def free_seat(a, f):
    """The nearest seat nobody is using."""
    here = a.locate(f)[0]
    seats = [(n, m) for n, m in MARKS.items() if m.get('seat') and n not in TAKEN]
    if not seats:
        return None
    n, m = min(seats, key=lambda q: (q[1]['pos'][0] - here[0]) ** 2 + (q[1]['pos'][1] - here[1]) ** 2)
    TAKEN.add(n)
    return m


for c in JOB.get('cast') or []:
    pos, face, seat = where(c)
    init = dict(f=c.get('feeling', 'neutral'), face=face)
    if seat:
        init['seat'] = seat
    start = c.get('enter_from')
    p0 = MARKS[start]['pos'] if start in MARKS else (offscreen(pos) if start else pos)
    if c.get('model'):
        import guest
        body = guest.Guest(c['id'], c['model'], JOB.get('aliases') or {}, c.get('model_yaw') or 0.0)
        init.pop('seat', None)          # a guest stands: sitting needs the sculpted legs
    else:
        body = Puppet(c.get('rig') or c['id'])
    a = PERF.add(A.Actor(c['id'], body, p0, c.get('style'), **init))
    a.home = pos
    a.mark = MARKS.get(c.get('mark') or '')
    if 'on' in c:
        a.init['on'] = bool(c['on'])
for ln in JOB.get('lines') or []:
    PERF.say(ln['who'], ln['start'], ln['end'], ln.get('cues') or [], ln.get('to'), ln.get('manual') or ())
for nm, t in STG['things'].items():
    PERF.things[nm] = t

# ------------------------------------------------------------------ solid contact: nothing passes through anything
# Everything built so far is the set: floors, rugs, furniture, props. Its surfaces are ray-cast to put feet on the floor
# (or the rug, or a table's base) and seated bodies on the seat, and hands that rest on a table on its top.
import numpy as _np  # noqa: E402
from mathutils.bvhtree import BVHTree as _BVH  # noqa: E402


def _solid_tree():
    global SOLID_OBJ
    verts, polys, n0, owner_ = [], [], 0, []
    door = STG.get('door')
    skip = {o.name for a in PERF.actors.values() for o in getattr(a.P, 'parts', [])}      # the cast is not the set
    for a in PERF.actors.values():
        root = getattr(a.P, 'root', None)
        if root is not None:
            skip |= {c.name for c in root.children_recursive}
    if door is not None:
        skip |= {door.name} | {c.name for c in door.children_recursive}
    for o in bpy.data.objects:
        if o.type != 'MESH' or o.name in skip or o.hide_render or not o.visible_camera or o.name.startswith('gob'):
            continue        # only what the camera can see is solid: not the cards that shape the window light
        me = o.data
        co = _np.empty(len(me.vertices) * 3, _np.float32)
        me.vertices.foreach_get('co', co)
        M = _np.array(o.matrix_world, dtype=_np.float32)
        co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
        verts.extend(map(tuple, co))
        polys.extend(tuple(v + n0 for v in p.vertices) for p in me.polygons)
        owner_.extend([o.name] * len(me.polygons))
        n0 += len(me.vertices)
    SOLID_OBJ = _np.array(owner_, dtype=object)
    global SOLID_BOX
    if polys:
        vv_ = _np.asarray(verts, _np.float32)
        SOLID_BOX = _np.array([_np.concatenate([vv_[list(p)].min(axis=0), vv_[list(p)].max(axis=0)]) for p in polys], _np.float32)
    global SOLID_C
    vv = _np.asarray(verts, _np.float32) if verts else _np.zeros((0, 3), _np.float32)
    SOLID_C = _np.array([vv[list(p)].mean(axis=0) for p in polys], _np.float32) if polys else _np.zeros((0, 3), _np.float32)
    return _BVH.FromPolygons(verts, polys) if polys else None


SOLID_C = SOLID_OBJ = SOLID_BOX = None
bpy.context.view_layer.update()
SOLID = _solid_tree()


def surface_under(x, y, z_from, reach, which=False):
    """The top of the first solid surface straight under (x, y, z_from), no further down than reach (with which=True,
    also the name of the object it belongs to)."""
    if SOLID is None:
        return (None, None) if which else None
    hit = SOLID.ray_cast(V((x, y, z_from)), V((0, 0, -1)), reach)
    if hit[0] is None:
        return (None, None) if which else None
    return (hit[0].z, SOLID_OBJ[hit[2]]) if which else hit[0].z


def _ground(x, y):
    z = surface_under(x, y, .35, .6)     # from below a seat: the floor, a rug, the foot of a table
    return z if z is not None else 0.0


PERF.ground = _ground

# ------------------------------------------------------------------ walking around things, not through them
CELL, BODY_R = .15, .55      # the route map's grain, and how far a walking body's centre keeps from anything solid
_ROUTE = {}


def _blocked():
    """A top-down map of what a walking body cannot pass: every face of the set between the knee and the head."""
    if 'grid' in _ROUTE:
        return _ROUTE['grid']
    x0, x1, y0, y1 = -13.0, 13.0, -14.0, STG['back'] + 2.0
    nx, ny = int((x1 - x0) / CELL) + 1, int((y1 - y0) / CELL) + 1
    grid = _np.zeros((nx, ny), bool)
    if SOLID_BOX is not None:
        band = (SOLID_BOX[:, 5] > .2) & (SOLID_BOX[:, 2] < 2.6)
        for bx0, by0, _, bx1, by1, _ in SOLID_BOX[band]:
            i0, i1 = int((bx0 - x0) / CELL), int((bx1 - x0) / CELL) + 1
            j0, j1 = int((by0 - y0) / CELL), int((by1 - y0) / CELL) + 1
            grid[max(0, i0):max(0, min(nx, i1)), max(0, j0):max(0, min(ny, j1))] = True
    # widen everything by a body's half-width, so the path is for the body's centre
    r = int(math.ceil(BODY_R / CELL))
    wide = grid.copy()
    for di in range(-r, r + 1):
        for dj in range(-r, r + 1):
            if di * di + dj * dj <= r * r:
                wide |= _np.roll(_np.roll(grid, di, 0), dj, 1)
    _ROUTE['grid'] = (wide, x0, y0, nx, ny)
    return _ROUTE['grid']


def route(p0, p1):
    """Waypoints from p0 to p1 (x, y) that keep a walking body clear of the furniture: the shortest path on the map,
    pulled straight wherever there is a clear line of sight. Just [p1] when the straight line is already clear or no
    route exists (the log says so)."""
    import heapq
    wide, x0, y0, nx, ny = _blocked()
    cell = lambda p: (min(nx - 1, max(0, int(round((p[0] - x0) / CELL)))), min(ny - 1, max(0, int(round((p[1] - y0) / CELL)))))
    a_, b_ = cell(p0), cell(p1)
    free = wide.copy()
    r = int(math.ceil(.5 / CELL))      # where they start and where they are going are allowed, even beside a desk
    for c in (a_, b_):
        free[max(0, c[0] - r):c[0] + r + 1, max(0, c[1] - r):c[1] + r + 1] = False

    def clear(c, d):
        n = max(abs(d[0] - c[0]), abs(d[1] - c[1]), 1)
        return not any(free[int(round(c[0] + (d[0] - c[0]) * t / n)), int(round(c[1] + (d[1] - c[1]) * t / n))] for t in range(n + 1))
    if clear(a_, b_):
        return [tuple(p1)]
    best, prev, todo = {a_: 0.0}, {}, [(0.0, a_)]
    while todo:
        _, c = heapq.heappop(todo)
        if c == b_:
            break
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                d = (c[0] + di, c[1] + dj)
                if (di or dj) and 0 <= d[0] < nx and 0 <= d[1] < ny and not free[d]:
                    g_ = best[c] + math.hypot(di, dj)
                    if g_ < best.get(d, 1e9):
                        best[d], prev[d] = g_, c
                        heapq.heappush(todo, (g_ + math.hypot(b_[0] - d[0], b_[1] - d[1]), d))
    if b_ not in prev:
        print(f'FILM no clear route from {tuple(round(v, 2) for v in p0)} to {tuple(round(v, 2) for v in p1)}: walking straight', flush=True)
        return [tuple(p1)]
    path = [b_]
    while path[-1] != a_:
        path.append(prev[path[-1]])
    path.reverse()
    keep, i = [], 0
    while i < len(path) - 1:
        j = len(path) - 1
        while j > i + 1 and not clear(path[i], path[j]):
            j -= 1
        keep.append(path[j])
        i = j
    pts = [(x0 + c[0] * CELL, y0 + c[1] * CELL) for c in keep[:-1]] + [tuple(p1)]
    print(f'FILM route around the furniture: {len(pts)} legs', flush=True)
    return pts


def walk_route(a, f, dest, speed=None):
    """Walk to dest around whatever is in the way: one walk per leg, each turning into the next."""
    here = a.locate(f)[0]
    t = f
    for wp in route((here[0], here[1]), dest):
        t = a.walk(t, wp, speed=speed)
    return t


def route_length(a, f, dest):
    here = a.locate(f)[0]
    pts = [(here[0], here[1])] + route((here[0], here[1]), dest)
    return sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(pts, pts[1:]))
CLEAR = .004      # how far above a surface a resting body or hand sits: touching, never inside


def _lowest(o):
    """The lowest point of one of a puppet's parts, as it is posed now (world space)."""
    ev = o.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    try:
        if not len(me.vertices):
            return None
        co = _np.empty(len(me.vertices) * 3, _np.float32)
        me.vertices.foreach_get('co', co)
    finally:
        ev.to_mesh_clear()
    M = _np.array(o.matrix_world, dtype=_np.float32)
    co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    return V(co[int(_np.argmin(co[:, 2]))])


def _part_tree(o):
    ev = o.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    try:
        co = _np.empty(len(me.vertices) * 3, _np.float32)
        me.vertices.foreach_get('co', co)
        polys = [tuple(p.vertices) for p in me.polygons]
    finally:
        ev.to_mesh_clear()
    M = _np.array(o.matrix_world, dtype=_np.float32)
    co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    return (_BVH.FromPolygons(list(map(tuple, co)), polys) if polys else None), co


def _inside(o, zmin=-9.0, zmax=99.0, only=None):
    """Where a part passes into the set: the centres of the set's faces it intersects (optionally within a height band),
    and the part's own vertices."""
    if o is None or SOLID is None:
        return _np.zeros((0, 3), _np.float32), None
    t, co = _part_tree(o)
    if t is None:
        return _np.zeros((0, 3), _np.float32), co
    idx = sorted({j for _, j in t.overlap(SOLID) if only is None or SOLID_OBJ[j] == only})
    pts = SOLID_C[idx] if idx else _np.zeros((0, 3), _np.float32)
    if len(pts):
        pts = pts[(pts[:, 2] >= zmin) & (pts[:, 2] <= zmax)]
    return pts, co


def _sole_depth(shoe):
    """How deep a shoe's sole is in the floor (0 when it is not): every sole vertex near the bottom ray-cast against
    the surface under it."""
    pts, co = _inside(shoe, -1.0, .08)
    if not len(pts) or co is None:
        return 0.0
    sole = co[co[:, 2] < co[:, 2].min() + .05]
    pen = 0.0
    for vx, vy, vz in sole[:: max(1, len(sole) // 400)]:
        sz_ = surface_under(float(vx), float(vy), float(vz) + .1, .2)
        if sz_ is not None:
            pen = max(pen, sz_ - float(vz))
    return pen


def _part(a, suffix):
    return next((o for o in getattr(a.P, 'parts', []) if o.type == 'MESH' and o.name.endswith(suffix)), None)


def _gap(o, up):
    """(how far the part's lowest point is above the surface under it, minus CLEAR) or None with nothing under it."""
    low = _lowest(o) if o is not None else None
    if low is None:
        return None
    surf = surface_under(low.x, low.y, low.z + up, up + .25)
    return None if surf is None else low.z - surf - CLEAR


def _seated_for(a, f):
    on, since = False, None
    for k in a.keys:
        if k[0] > f:
            break
        now = bool(k[1].get('seat'))
        if now and not on:
            since = k[0]
        on = now
    return (f - since) if on and since is not None else 0


def settle(f, depth=0):
    """After everyone is posed: a seated body rests on its seat (not in it, not above it) and a hand laid on a table rests
    on the top. What is measured is kept (seat_lift, hand_lift), so the next frames start right and seldom pose twice."""
    bpy.context.view_layer.update()
    again = []
    for a in PERF.actors.values():
        if getattr(a.P, 'guest', False) or getattr(a, 'cull', False) or not a.P.vis:
            continue
        cur = a.state(f)[1][1]
        moved = False
        if cur.get('seat'):
            # the thighs rest on the seat too: while either is in it, the body comes up a centimetre at a time
            rx, ry = a.P.root.matrix_world.translation.xy
            top, seat_o = surface_under(rx, ry, 1.2, 1.2, which=True)     # from under a table top, down to the seat
            top = top or 0.0
            legs = [_inside(_part(a, '_l' + sd), top - .3, top + .1, only=seat_o)[0] for sd in ('L', 'R')]
            # a thigh in the top of the seat: the body comes up a centimetre at a time
            thighs_in = any(len(p_) and (p_[:, 2] >= top - .02).any() for p_ in legs)
            g_ = _gap(_part(a, '_torso'), .3)
            if thighs_in and getattr(a, 'seat_lift', 0.0) < .3:
                a.seat_lift = getattr(a, 'seat_lift', 0.0) + .01
                moved = True
            # up out of the seat at any time; down onto it only once they have been sitting a second (sitting down
            # passes above the seat, and that is not hovering) and only while the thighs are clear of it
            elif g_ is not None and (g_ < -.002 or (g_ > .003 and not thighs_in and _seated_for(a, f) > 24)):
                a.seat_lift = getattr(a, 'seat_lift', 0.0) - g_
                moved = True
        if cur.get('hL') is not None or cur.get('hR') is not None:
            lifts = getattr(a, 'hand_lift', {})
            for side in ('L', 'R'):
                g_ = _gap(_part(a, '_h' + side), .25)
                if g_ is not None and g_ < -.002:
                    lifts[side] = lifts.get(side, 0.0) - g_
                    moved = True
                # a forearm lying across the table's edge goes through it: the hands come up until it clears
                elif len(_inside(_part(a, '_a' + side), .9, 2.2)[0]) and lifts.get(side, 0.0) < .25:
                    lifts[side] = lifts.get(side, 0.0) + .01
                    moved = True
            a.hand_lift = lifts
        # a hand in a gesture that ends inside something on the set (a mug, a machine, a screen) is nudged clear of it,
        # for that gesture only
        nudges = getattr(a, 'hand_nudge', {})
        for side in ('L', 'R'):
            if cur.get('h' + side) is not None:
                continue
            pts, co = _inside(_part(a, '_h' + side), .3, 9.0)
            if len(pts) and co is not None:
                d = co.mean(axis=0) - pts.mean(axis=0)
                n = float(_np.linalg.norm(d))
                d, n = (d, n) if n > 1e-4 else (_np.array([0.0, 0.0, 1.0]), 1.0)
                key = (side, a.state(f)[1][0])
                nx, ny, nz = nudges.get(key, (0.0, 0.0, 0.0))
                if math.sqrt(nx * nx + ny * ny + nz * nz) < .4:
                    nudges[key] = (nx + .04 * d[0] / n, ny + .04 * d[1] / n, nz + .04 * d[2] / n)
                    moved = True
        a.hand_nudge = nudges
        # feet are pushed sideways out of whatever they stand in (a chair's base, a table's foot), remembered for the
        # spot the person stands or sits at, and never mid-stride
        if not a.walking(f):
            here = getattr(a, 'spot', None)
            push = getattr(a, 'foot_push', {})
            flift = getattr(a, 'foot_lift', {})
            for side in ('L', 'R'):
                shoe = _part(a, '_s' + side)
                # in the floor (a plank standing proud, a bump in a rug): measured under its lowest points, and lifted
                low_pts, low_co = _inside(shoe, -1.0, .08)
                if len(low_pts) and low_co is not None and here is not None:
                    sole = low_co[low_co[:, 2] < low_co[:, 2].min() + .05]      # the whole sole, not just its lowest point
                    lows = sole[:: max(1, len(sole) // 400)]
                    pen = 0.0
                    for vx, vy, vz in lows:
                        sz_ = surface_under(float(vx), float(vy), float(vz) + .1, .2)
                        if sz_ is not None:
                            pen = max(pen, sz_ - float(vz))
                    if pen > 0 and flift.get((here, side), 0.0) < .1:
                        flift[(here, side)] = flift.get((here, side), 0.0) + pen + .002
                        moved = True
                        continue
                pts, co = _inside(shoe, .08, .6)
                if not len(pts):
                    # a shin through a chair's leg or a table's foot: the foot moves, and the shin with it
                    pts, _ = _inside(_part(a, '_l' + side), -1.0, .55)
                if len(pts) and co is not None:
                    d = co[:, :2].mean(axis=0) - pts[:, :2].mean(axis=0)
                    n = float(_np.hypot(*d))
                    if n < 1e-4:
                        yw = a.last_yaw or 0.0
                        d, n = _np.array([math.sin(yw), -math.cos(yw)]), 1.0
                    px, py = push.get((here, side), (0.0, 0.0))
                    if math.hypot(px, py) < .45:
                        push[(here, side)] = (px + .05 * d[0] / n, py + .05 * d[1] / n)
                        moved = True
            a.foot_push = push
            a.foot_lift = flift
        else:
            # walking: a stepping foot is where it is for one frame; measured there and lifted for that frame only
            wl = getattr(a, 'walk_lift', None)
            if not wl or wl.get('f') != f:
                wl = {'f': f, 'L': 0.0, 'R': 0.0}
            for side in ('L', 'R'):
                pen = _sole_depth(_part(a, '_s' + side))
                if pen > 0 and wl[side] < .15:
                    wl[side] += pen + .002
                    moved = True
            a.walk_lift = wl
        if moved:
            again.append(a)
    for a in again:
        PERF.pose_one(a, f)
    if again:
        bpy.context.view_layer.update()
        if depth < 8:
            settle(f, depth + 1)     # measure again: one correction can need a few small steps


PERF.settle = settle

# ------------------------------------------------------------------ dressing that moves (direction.dressing)
ANIMATORS = []
DRESS = set(SET.get('dressing') or [])


def _where(t):
    return tuple(t.matrix_world.translation) if hasattr(t, 'matrix_world') else tuple(t)


if 'steam' in DRESS:
    # every puff is two transparent surfaces and they overlap: past the bounce limit Cycles draws black, not vapour
    s.cycles.transparent_max_bounces = 32
    for nm, t in STG['things'].items():
        if nm == 'mug' or nm.startswith('mug_'):
            ANIMATORS.append(K.steam(_where(t), seed=7 + len(ANIMATORS)))
if 'birds' in DRESS and (STG['outdoor'] or STG['windows']):
    ANIMATORS.append(K.birds(STG['back'], outdoor=STG['outdoor'], seed=int(SET.get('seed', 1))))


def dress_at(f):
    for anim in ANIMATORS:
        anim(f)
    props_at(f)


# ------------------------------------------------------------------ props that move on a track (direction.props)
TRACKS = {}      # thing -> (object, its lid or None, rest location, rest rotation, rest lid angle, [moves])
for mv in JOB.get('props') or []:
    o = PERF.things.get(mv['thing'])
    if not hasattr(o, 'location'):
        print(f"FILM prop {mv['thing']} is not an object that can move: left where it is", flush=True)
        continue
    if mv['thing'] not in TRACKS:
        lid = next((c for c in o.children if c.name.startswith('lid')), None)
        TRACKS[mv['thing']] = (o, lid, o.location.copy(), o.rotation_euler.copy(), lid.rotation_euler.x if lid else 0.0, [])
    TRACKS[mv['thing']][5].append(mv)


def props_at(f):
    """Each thing that moves is put where its moves so far leave it: every move eases in over its own frames."""
    for o, lid, loc0, rot0, lid0, moves in TRACKS.values():
        loc, rz, shown, lid_a = loc0.copy(), rot0.z, True, lid0
        for mv in moves:
            k = sm(clamp((f - mv['frame']) / max(1, mv.get('frames', 14))))
            if k <= 0:
                continue
            do = mv['do']
            if do == 'slide':
                loc += V(mv['by']) * k
            elif do == 'turn':
                rz += math.radians(mv['deg']) * k
            elif do in ('open', 'close') and lid is not None:
                target = -.16 if do == 'open' else -.16 - 1.4
                lid_a = lid_a + (target - lid_a) * k
            elif do == 'hide' and k >= 1:
                shown = False
            elif do == 'show' and k > 0:
                shown = True
        o.location = loc
        o.rotation_euler.z = rz
        if lid is not None:
            lid.rotation_euler.x = lid_a
        show_tree(o, shown)


def desk_hands(a):
    """Where the hands rest on the table this actor sits at: world positions for the left and the right."""
    m = a.mark
    if not m or not m.get('table') or not m.get('seat'):
        return None
    (x, y), yaw = m['pos'], m.get('face', 0.0)
    fwd, rgt = (math.sin(yaw), -math.cos(yaw)), (math.cos(yaw), math.sin(yaw))
    z = m['table'] + .07 + STG.get('floor', 0)
    return [(x + fwd[0] * .64 + sg * rgt[0] * .27, y + fwd[1] * .64 + sg * rgt[1] * .27, z) for sg in (-1, 1)]


PERF.direct()
for k in JOB.get('keys') or []:
    a = PERF.actors.get(k.get('who'))
    if a is None:
        continue
    k = dict(k)
    f = int(k.pop('frame', 0))
    to_mark = None
    if 'walk' in k:
        to = k.pop('walk')
        leave = k.pop('leave', False)
        m = free_seat(a, f) if to == 'seat' else (MARKS.get(to) if isinstance(to, str) else None)
        if to == 'seat' and m is None:
            continue
        dest = m['pos'] if m else (a.home if to == 'home' else offscreen(a.home) if isinstance(to, str) else tuple(to))
        speed = k.pop('speed', None)
        if k.pop('enter', False):
            # f is when they should have arrived: leave early enough, and stay unseen until then
            here = a.locate(f)[0]
            f = f - int(route_length(a, f, dest) / (speed or a.st['speed'])) - 8
            a.key(-900, dict(on=False))
            a.key(f, dict(on=True))
            if 'door' in MARKS and math.hypot(here[0] - MARKS['door']['pos'][0], here[1] - MARKS['door']['pos'][1]) < .5:
                DOORS.append([f - 8, f + 46])
        end = walk_route(a, f, dest, speed=speed)
        if to == 'door':
            DOORS.append([end - 34, end + 12])
        to_mark = m if m else dict(pos=dest)
        if leave:
            a.key(end + 6, dict(on=False))
        if m and m.get('seat') and k.pop('sit', True) and not getattr(a.P, 'guest', False):
            a.key(end - 8, dict(seat=m['seat'], face=m.get('face', 0)))
        elif m:
            a.key(end - 10, dict(face=m.get('face')))     # arrived on a standing mark: free to turn to whoever matters
    if to_mark is not None:
        a.mark = to_mark
    if k.get('g') in ('typing', 'desk'):
        h = desk_hands(a)
        if h:
            k.update(hL=h[0], hR=h[1])
            a.at_desk = True
    elif 'g' in k and getattr(a, 'at_desk', False):
        k.update(hL=None, hR=None)
        a.at_desk = False
    if isinstance(k.get('seat'), str):
        k['seat'] = (MARKS.get(k['seat']) or {}).get('seat') or A.SEAT_H
    if isinstance(k.get('look'), list):
        k['look'] = tuple(k['look'])
    a.key(f, k)
PERF.finish()

# things carried in a hand: made once, shown while they are held
HELD = []
for c in JOB.get('carry') or []:
    a = PERF.actors.get(c.get('who'))
    if a is None or not hasattr(a.P, 'palm'):
        continue
    palm = a.P.palm['R']
    hs = a.P.m.get('hs', 1.0)
    if c.get('prop') == 'mug':
        o = K.mug(.085 * hs, -.105 * hs, -.1 * hs, palm, hex_=c.get('color') or '#c1553f')
        o.scale = (.78 * hs,) * 3
    elif c.get('prop') == 'phone':
        o = K.phone(.09 * hs, -.05 * hs, 0, palm)
        o.rotation_euler = (math.pi / 2, 0, math.pi / 2)
        o.scale = (1.15 * hs,) * 3
    else:
        continue
    HELD.append((o, int(c.get('start', -10 ** 6)), int(c.get('end', 10 ** 6))))


def show_tree(o, on):
    o.hide_render = o.hide_viewport = not on
    for ch in o.children:
        show_tree(ch, on)


def held_at(f):
    for o, f0, f1 in HELD:
        show_tree(o, f0 <= f < f1)


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
FRAME_H = dict(wide=5.9, medium=3.0, two_shot=3.3, over_shoulder=2.3, close_up=1.95, extreme_close_up=.95, reaction=1.95, insert=1.0, portrait=4.6)
AIM_DZ = dict(wide=-1.5, medium=-.62, two_shot=-.55, over_shoulder=-.08, close_up=-.2, extreme_close_up=-.06, reaction=-.2, portrait=-1.3)
FRAMES = sorted(int(x) for x in JOB.get('frames') or [0])      # the scene frames this shot films
F0, F1 = FRAMES[0], FRAMES[-1] + 1


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


def facing(name):
    """The horizontal direction a person's face points (yaw 0 faces the open front of the set, -y)."""
    y = PERF.actors[name].last_yaw or 0
    return V((math.sin(y), -math.cos(y), 0))


def fit(pos, aim, heads, margin=.84):
    """Back the camera away from its aim, keeping the angle, until every head (and its width) sits inside the frame.

    The framing distance comes from the people's spread across the stage, but whoever stands nearer the lens than the
    aim point is pushed outwards by perspective: a seated speaker in the foreground of a wide could lose half her face
    to the edge of the frame. Each head is projected through the real lens and the camera steps back until it fits."""
    tx, ty = math.tan(hfov() / 2) * margin, math.tan(vfov() / 2) * margin
    for _ in range(30):
        fwd = (aim - pos).normalized()
        right = fwd.cross(V((0, 0, 1))).normalized()
        up = right.cross(fwd)
        ok = True
        for h in heads:
            for p in (h + right * .42, h - right * .42, h + up * .5):
                r = p - pos
                depth = r.dot(fwd)
                if depth <= .2 or abs(r.dot(right) / depth) > tx or abs(r.dot(up) / depth) > ty:
                    ok = False
        if ok:
            return pos
        pos = aim + (pos - aim) * 1.06
    return pos


def frame_shot(shot=None, only=None):
    """Where the camera stands at the start of the shot and what it looks at, from the people as they really are."""
    shot = shot or CAM.get('shot', 'medium')
    who = [w for w in only or CAM.get('who') or [] if w in PERF.actors and PERF.actors[w].P.vis] or [n for n, a in PERF.actors.items() if a.P.vis][:1]
    if CAM.get('position') and CAM.get('aim'):
        # the director put the camera exactly here: it is not second-guessed
        return V(CAM['position']), V(CAM['aim']), (CAM.get('focus') if CAM.get('focus') in PERF.actors else (who[0] if who else None))
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
        pos = ls - d * 2.7 + side * 1.0 + V((0, 0, .34))     # behind and well to the side: the near head frames the shot, it does not fill it
        pos.y = min(pos.y, min(sp.y, ls.y) - 1.2) if abs(d.y) < .5 else pos.y
        # The point of the shot is the speaker's face. People are played towards the open front of the set, so when the
        # listener stands upstage of the speaker this camera would sit behind the listener looking out at the open side
        # of the set, and see the back of the speaker's head. Then the pair is filmed as a two-shot from the front.
        to_cam = V((pos.x - sp.x, pos.y - sp.y, 0))
        if to_cam.length > 1e-6 and to_cam.normalized().dot(facing(who[0])) < .26:
            fb = CAM.get('fallback') or 'two_shot'
            print(f'FILM over_shoulder would see {who[0]} from behind: filmed as a {fb.replace("_", "-")}', flush=True)
            return frame_shot(fb, only=[who[0]] if fb != 'two_shot' else None)
        return pos, V((sp.x, sp.y, sp.z - .1)), who[0]
    # stand on the side the subject is turned towards, for a three-quarter view of the face
    yaw = sum((PERF.actors[w].last_yaw or 0) for w in who) / len(who)
    ang = clamp(yaw * (.8 if len(who) == 1 else .3), -.6, .6)
    # a wide shot is seen from standing height, even when the people in it are sitting down
    pos = V((aim.x + math.sin(ang) * dist, aim.y - math.cos(ang) * dist, max(aim.z + .12, dict(wide=2.7, two_shot=2.0).get(shot, 0))))
    pos.z += dict(low=-.75, high=1.0).get(CAM.get('height', 'eye'), 0) * (dist / 6) ** .5
    if len(heads) > 1:
        pos = fit(pos, aim, heads)
    elif shot in LEAD_ROOM:
        # Lead room: a face sits on the far side of the frame from the person it is talking or listening to, with the
        # open space in front of it. The camera trucks sideways (its angle is kept), so the eyeline reads across the cut.
        partner = partner_of(who[0])
        if partner:
            right = (aim - pos).normalized().cross(V((0, 0, 1))).normalized()
            toward = clamp((eyes(partner) - aim).dot(right) / 1.5, -1, 1)
            width = FRAME_H.get(shot, 2.9) * s.render.resolution_x / s.render.resolution_y
            shift = right * (toward * LEAD_ROOM[shot] * width)
            pos, aim = pos + shift, aim + shift
    return pos, aim, (CAM.get('focus') if CAM.get('focus') in PERF.actors else who[0])


LEAD_ROOM = dict(close_up=.12, reaction=.12, medium=.10, extreme_close_up=.06)   # share of the frame's width


def partner_of(name):
    """Who this person is playing to during the shot: the line's listener if they speak, the speaker if they listen."""
    for ln in JOB.get('lines') or []:
        if ln.get('end', 0) <= F0 or ln.get('start', 0) >= F1:
            continue
        other = (ln.get('to') if ln.get('who') == name else ln.get('who'))
        if other and other != name and other in PERF.actors:
            return other
    return next((n for n, a in PERF.actors.items() if n != name and a.P.vis), None)


def look_through(pos, aim):
    cam.location = pos
    cam.rotation_euler = (aim - pos).to_track_quat('-Z', 'Y').to_euler()


PERF.pose(F0)
bpy.context.view_layer.update()
POS0, AIM0, FOCUS = frame_shot()
HEAD0 = eyes(FOCUS) if FOCUS else None


def out_of_frame(a):
    """True when no part of this actor can be seen from the camera as it stands at the start of the shot."""
    c = cam.matrix_world.inverted() @ (a.P.root.matrix_world.translation + V((0, 0, 1.9)))
    depth, r = -c.z, 2.4
    if depth < -r:
        return True
    d = max(depth, .5)
    return abs(c.x) > d * math.tan(hfov() / 2) + r or abs(c.y) > d * math.tan(vfov() / 2) + r


if MODE == 'film' and CAM.get('shot') != 'opening' and CAM.get('move', 'static') in ('static', 'push_in'):
    look_through(POS0, AIM0)
    bpy.context.view_layer.update()
    for a in PERF.actors.values():
        # someone the camera cannot see is not drawn at all for this shot (others still look at where they stand)
        a.cull = not any(w[0] <= F1 + 40 and w[1] >= F0 - 40 and w[1] > w[0] for w in a.walks) and out_of_frame(a)
    culled = [n for n, a in PERF.actors.items() if a.cull]
    if culled:
        print('FILM off camera', ', '.join(culled), flush=True)


def opening(style):
    """How a scene begins: the camera's first and last position and aim for the shot that opens it.

    establish  the whole place, drifting in             door    the door of the set, as it opens
    object     close on a thing, then back to the room  match   close on a face, easing away
    """
    back = STG['back']
    wide = (V((.5, -10.4, 3.5)), V((0, 2.2, 2.45)))
    if style == 'door' and 'door' in MARKS:
        dx, dy = MARKS['door']['pos']
        return (V((dx * .45, dy - 8.2, 2.9)), V((dx, back, 2.3))), (V((dx * .55, dy - 6.4, 2.8)), V((dx, back, 2.3)))
    if style == 'object':
        tp = thing_pos(CAM.get('thing') or '') or V((0, 2, 1.6))
        return (tp + V((.45, -1.5, .7)), tp), (V((tp.x * .5 + .4, -8.6, 3.3)), V((tp.x * .45, 2.4, 2.2)))
    who = [w for w in CAM.get('who') or [] if w in PERF.actors]
    if style == 'match' and who:
        h = eyes(who[0])
        d = (FRAME_H['close_up'] / 2) / math.tan(vfov() / 2)
        return (V((h.x + .25, h.y - d, h.z)), V((h.x, h.y, h.z - .1))), (V((h.x + .5, h.y - d * 1.9, h.z + .1)), V((h.x, h.y, h.z - .4)))
    return (V((1.3, -12.4, 3.9)), V((0, 2.2, 2.5))), wide


MOVES_IN_SHOT = False
if FOCUS and CAM.get('shot') in ('medium', 'close_up', 'reaction', 'extreme_close_up'):
    # does the subject end the shot somewhere else (a walk, standing up, sitting down)? Then the camera goes with them
    PERF.pose(F1 - 1)
    MOVES_IN_SHOT = (eyes(FOCUS) - HEAD0).length > .3 or any(w[1] > w[0] and w[0] <= F1 and w[1] + 9 >= F0 for w in PERF.actors[FOCUS].walks)
    PERF.pose(F0)
OPENING = opening(CAM.get('style', 'establish')) if CAM.get('shot') == 'opening' else None
if OPENING and CAM.get('style') != 'object':
    cam_data.dof.use_dof = False


def camera_at(f):
    t = sm(clamp((f - F0) / max(1, F1 - F0 - 1)))
    if CAM.get('shot') == 'opening':
        (p0, a0), (p1, a1) = OPENING
        pos, aim = p0.lerp(p1, t), a0.lerp(a1, t)
        look_through(pos, aim)
        if cam_data.dof.use_dof:
            cam_data.dof.focus_distance = max(.3, (aim - pos).length)
        return
    pos, aim = POS0.copy(), AIM0.copy()
    mv = CAM.get('move', 'static')
    if FOCUS and mv in ('static', 'push_in') and MOVES_IN_SHOT:
        mv = 'track'        # nobody walks out of their own shot: the camera goes with them
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
    for o, c_ in DOORS:
        a = max(a, sm(clamp((f - o) / 12)) * (1 - sm(clamp((f - c_) / 14))))
    leaf.rotation_euler = (0, 0, -1.45 * a * (1 if leaf.location.x < 0 else -1))


# ------------------------------------------------------------------ portraits and sheets (one still, no scene)
if MODE in ('portrait', 'sheet'):
    PERF.pose(FRAMES[0])
    PERF.pose(FRAMES[0])
    held_at(FRAMES[0])
    door_at(FRAMES[0])
    dress_at(FRAMES[0])
    bpy.context.view_layer.update()
    if OPENING:
        camera_at(FRAMES[0])
    else:
        P0, A0, _ = frame_shot()
        look_through(P0, A0)
    os.makedirs(JOB['out'], exist_ok=True)
    s.render.filepath = os.path.join(JOB['out'], '000001.png')
    bpy.ops.render.render(write_still=True)
    print('FILM done 1 frames', flush=True)
    sys.exit(0)

# ------------------------------------------------------------------ export (one character, to a file other tools open)
if MODE == 'export':
    PERF.pose(0)
    PERF.pose(0)
    bpy.context.view_layer.update()
    who = next(iter(PERF.actors.values()))
    keep = set(who.P.parts)
    for o in list(bpy.data.objects):
        if o not in keep:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    for o in keep:
        o.hide_viewport = o.hide_render = False
        o.select_set(True)
    dst = JOB['export']
    ext = os.path.splitext(dst)[1].lower()
    if ext == '.blend':
        bpy.ops.wm.save_as_mainfile(filepath=dst)
    elif ext == '.glb':
        bpy.ops.export_scene.gltf(filepath=dst, export_format='GLB', use_selection=True, export_apply=True)
    elif ext == '.fbx':
        bpy.ops.export_scene.fbx(filepath=dst, use_selection=True, use_mesh_modifiers=True)
    elif ext == '.obj':
        bpy.ops.wm.obj_export(filepath=dst, export_selected_objects=True, apply_modifiers=True)
    else:
        raise SystemExit(f'FILM cannot export {ext}')
    print('FILM done export', flush=True)
    sys.exit(0)

# ------------------------------------------------------------------ film it
out = JOB['out']
os.makedirs(out, exist_ok=True)
frames = [f for f in FRAMES if not os.path.exists(os.path.join(out, f'{f:06d}.png'))]
print(f'FILM frames {len(frames)} of {len(FRAMES)} to do', flush=True)
t0 = time.time()
steps = sorted({f for a in PERF.actors.values() for f in a.steps()})
json.dump(dict(steps=steps), open(os.path.join(out, 'events.json'), 'w'))
t_pose = t_draw = 0.0
for n, f in enumerate(frames):
    t1 = time.time()
    PERF.pose(f)
    door_at(f)
    held_at(f)
    dress_at(f)
    bpy.context.view_layer.update()
    camera_at(f)
    t2 = time.time()
    path = os.path.join(out, f'{f:06d}.png')
    s.render.filepath = path + '.part.png'
    bpy.ops.render.render(write_still=True)
    os.replace(path + '.part.png', path)
    t_pose += t2 - t1
    t_draw += time.time() - t2
    print(f'FILM frame {n + 1}/{len(frames)} f{f} {time.time() - t0:.1f}s', flush=True)
print(f'FILM timing pose {t_pose:.1f}s draw {t_draw:.1f}s', flush=True)
print('FILM done', len(frames), 'frames', round(time.time() - t0, 1), 's', flush=True)
