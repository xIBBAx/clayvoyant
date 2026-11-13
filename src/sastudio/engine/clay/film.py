"""Sultan, the clay engine of Clayvoyant, named after Ibrahim Sultan, who made it.

Film one shot of a clay scene from a JSON job. Runs inside Blender:

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
import contacts as CT  # noqa: E402  (what passes through what: settling and the check before filming both measure)
JOB = json.load(open(sys.argv[sys.argv.index('--') + 1], encoding='utf-8'))
os.environ['SASTUDIO_RIG'] = JOB['rig']

bpy.ops.wm.read_factory_settings(use_empty=True)
from mathutils import Matrix  # noqa: E402
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
PERF = A.Performance(FPS)
MARKS = STG['marks']

# ------------------------------------------------------------------ solid contact: nothing passes through anything
# Everything built so far is the set: floors, rugs, furniture, props. Its surfaces are ray-cast to put feet on the floor
# (or the rug, or a table's base) and seated bodies on the seat, and hands that rest on a table on its top.
import numpy as _np  # noqa: E402
from mathutils.bvhtree import BVHTree as _BVH  # noqa: E402


def _mesh_world(o):
    """One object of the set as contact needs it, exactly as it is drawn (bevels, lumps and every other modifier
    applied): vertices in the world, faces, and each face's box and centre. The bare mesh under the modifiers is not
    the surface anyone sees: a body measured against it can be inside the real one."""
    ev = o.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    try:
        if not len(me.polygons):
            return None
        co = _np.empty(len(me.vertices) * 3, _np.float32)
        me.vertices.foreach_get('co', co)
        lv = _np.empty(len(me.loops), _np.int32)
        me.loops.foreach_get('vertex_index', lv)
        ls = _np.empty(len(me.polygons), _np.int32)
        me.polygons.foreach_get('loop_start', ls)
        lt = _np.empty(len(me.polygons), _np.int32)
        me.polygons.foreach_get('loop_total', lt)
    finally:
        ev.to_mesh_clear()
    M = _np.array(o.matrix_world, dtype=_np.float32)
    co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    polys = lv.reshape(-1, int(lt[0])).tolist() if (lt == lt[0]).all() else [lv[a:a + b].tolist() for a, b in zip(ls, lt)]
    pc = co[lv]
    box = _np.concatenate([_np.minimum.reduceat(pc, ls, axis=0), _np.maximum.reduceat(pc, ls, axis=0)], axis=1)
    cen = _np.add.reduceat(pc, ls, axis=0) / lt[:, None]
    return co, polys, box, cen


def _in_room(o):
    """Inside the room or on its walls: what a body could ever touch. The city through the window, the clouds and the
    lawn outside are left out of contact."""
    bb = [o.matrix_world @ V(c) for c in o.bound_box]
    lo = [min(p[i] for p in bb) for i in range(3)]
    hi = [max(p[i] for p in bb) for i in range(3)]
    return lo[2] < 8 and hi[0] > -15 and lo[0] < 15 and hi[1] > -17 and lo[1] < STG['back'] + .8


CHAIRS = []       # chairs somebody stands up from or walks to: they move (see chairs_at), so they are measured apart
_STATIC = None    # everything else on the set, measured once


def _gather(objs):
    verts, polys, owner_, boxes, cens, n0 = [], [], [], [], [], 0
    for o in objs:
        got = _mesh_world(o)
        if got is None:
            continue
        co, ps, box, cen = got
        verts.extend(co.tolist())
        polys.extend([[v + n0 for v in p] for p in ps] if n0 else ps)
        owner_.extend([o.name] * len(ps))
        boxes.append(box)
        cens.append(cen)
        n0 += len(co)
    return verts, polys, owner_, boxes, cens


def _solid_tree():
    """The set as one tree of faces. What never moves is gathered once; a chair in use is gathered where it stands now."""
    global SOLID_OBJ, SOLID_BOX, SOLID_C, _STATIC
    if _STATIC is None:
        door = STG.get('door')
        skip = {o.name for a in PERF.actors.values() for o in getattr(a.P, 'parts', [])}      # the cast is not the set
        for a in PERF.actors.values():
            root = getattr(a.P, 'root', None)
            if root is not None:
                skip |= {c.name for c in root.children_recursive}
        if door is not None:
            skip |= {door.name} | {c.name for c in door.children_recursive}
        for ch in CHAIRS:
            skip |= {o.name for o in ch['meshes']}
        # only what the camera can see is solid: not the cards that shape the window light
        _STATIC = _gather(o for o in bpy.data.objects if o.type == 'MESH' and o.name not in skip and not o.hide_render
                          and o.visible_camera and not o.name.startswith('gob') and _in_room(o))
    verts, polys, owner_, boxes, cens = _STATIC
    if CHAIRS:
        n0 = len(verts)
        v2, p2, o2, b2, c2 = _gather(o for ch in CHAIRS for o in ch['meshes'])
        verts, polys = verts + v2, polys + [tuple(v + n0 for v in p) for p in p2]
        owner_, boxes, cens = owner_ + o2, boxes + b2, cens + c2
    SOLID_OBJ = _np.array(owner_, dtype=object)
    SOLID_BOX = _np.concatenate(boxes) if boxes else None
    SOLID_C = _np.concatenate(cens) if cens else _np.zeros((0, 3), _np.float32)
    return _BVH.FromPolygons(verts, polys) if polys else None


# ------------------------------------------------------------------ set dressing: everything rests on something, nothing in anything
# A set gives each loose thing (a mug, a laptop, papers, a plant) a place by numbers. Here each is put down on the surface
# under it (its lowest point on the highest point beneath it), and things that share a surface are moved the least
# distance that keeps them out of each other and still on it (the smallest push that separates two footprints, found
# on the axes of their edges; failing that, the nearest free place on the surface). What still overlaps is reported.
DRESS_CLEAR = .015      # the least gap between two things standing side by side on a surface


def _footprint(g):
    """A loose thing's outline on the floor plan, as a box turned the way it is turned: centre, axes, half sizes;
    and its lowest point and every vertex (world)."""
    bits = [c for c in [g] + list(g.children_recursive) if c.type == 'MESH']
    pts = [_mesh_world(c) for c in bits]
    V_ = _np.concatenate([q[0] for q in pts if q is not None]) if any(q is not None for q in pts) else None
    if V_ is None:
        return None
    yaw = g.matrix_world.to_euler('XYZ').z
    u = _np.array((math.cos(yaw), math.sin(yaw)))
    v = _np.array((-math.sin(yaw), math.cos(yaw)))
    pu, pv = V_[:, :2] @ u, V_[:, :2] @ v
    c = u * (pu.min() + pu.max()) / 2 + v * (pv.min() + pv.max()) / 2
    return dict(c=c, ax=(u, v), h=_np.array(((pu.max() - pu.min()) / 2, (pv.max() - pv.min()) / 2)), low=float(V_[:, 2].min()),
                high=float(V_[:, 2].max()), V=V_)


def _corners(fp, pad=0.0):
    u, v = fp['ax']
    hu, hv = fp['h'] + pad
    return _np.array([fp['c'] + su * hu * u + sv * hv * v for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))])


def _mtv(a, b, pad):
    """The smallest push that takes footprint a out of footprint b (the separating axis test on the edges' axes), or
    None when they are already apart by pad."""
    A, B = _corners(a, pad / 2), _corners(b, pad / 2)
    best = None
    for ax in (a['ax'][0], a['ax'][1], b['ax'][0], b['ax'][1]):
        pa, pb = A @ ax, B @ ax
        o = min(pa.max(), pb.max()) - max(pa.min(), pb.min())
        if o <= 0:
            return None
        if best is None or o < best[0]:
            sgn = 1.0 if (a['c'] - b['c']) @ ax >= 0 else -1.0
            best = (o, ax * sgn)
    return best[1] * (best[0] + 1e-4)


def _hull(P):
    """The convex outline of points on the plan (monotone chain)."""
    P = sorted(map(tuple, _np.round(P, 4)))
    if len(P) < 3:
        return _np.array(P)
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])  # noqa: E731
    lo, hi = [], []
    for p_ in P:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p_) <= 0:
            lo.pop()
        lo.append(p_)
    for p_ in reversed(P):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p_) <= 0:
            hi.pop()
        hi.append(p_)
    return _np.array(lo[:-1] + hi[:-1])


def _inside_hull(H, pts, margin):
    """True when every point lies inside the convex outline H, at least margin in from its edges."""
    if len(H) < 3:
        return False
    for i in range(len(H)):
        a, b = H[i], H[(i + 1) % len(H)]
        e = b - a
        n = _np.array((-e[1], e[0])) / (float(_np.hypot(*e)) or 1.0)       # inward for a counter-clockwise outline
        if ((pts - a) @ n < margin).any():
            return False
    return True


def _dress_tree(objs):
    v_, p_, own_, box_, _c = _gather(objs)
    if not p_:
        return None, None, None
    sizes = {len(q) for q in p_}
    tree = _BVH.FromPolygons(_np.array(v_, _np.float32), _np.array(p_, _np.int32) if len(sizes) == 1 else p_)
    return tree, _np.array(own_, dtype=object), _np.concatenate(box_)


def _rest(d, tree, own_, mine):
    """Put a thing down on the highest point under its outline (its own faces do not hold it up): -> what holds it."""
    fp = _footprint(d['group'])
    if fp is None:
        return None
    hits = []
    for q in list(_corners(fp, -.01)) + [fp['c']]:
        o_ = V((q[0], q[1], fp['high'] + .05))
        for _ in range(64):
            h = tree.ray_cast(o_, V((0, 0, -1)), 10.0)
            if h[0] is None:
                break
            if own_[h[2]] in mine or h[0].z > fp['low'] + .3:
                o_ = h[0] - V((0, 0, 1e-4))          # through its own body, or something above it: look further down
                continue
            hits.append((h[0].z, own_[h[2]]))
            break
    if not hits:
        return None
    z, under = max(hits)
    dz = z + .001 - fp['low']
    if abs(dz) > 1e-4:
        M = d['group'].matrix_world.copy()
        M.translation.z += dz
        d['group'].matrix_world = M
    d['fp'] = dict(fp, low=fp['low'] + dz, high=fp['high'] + dz)
    return under


def settle_dressing():
    """Put every loose thing down on what is under it, and out of everything else on that surface."""
    props = [d for d in K.SETS_PROPS() if d['group'].parent is None or d['group'].parent.type == 'EMPTY']
    for d in props:
        d['own'] = {c.name for c in [d['group']] + list(d['group'].children_recursive)}
    every = [o for o in bpy.data.objects if o.type == 'MESH' and not o.hide_render and o.visible_camera
             and not o.name.startswith(('gob', 'steam', 'wing')) and _in_room(o)]
    # furniture first, on the floor; then the loose things on whatever holds them now
    tree, own_, boxes = _dress_tree(every)
    if tree is None:
        return
    for d in props:
        if d['kind'] == 'furniture':
            d['under'] = _rest(d, tree, own_, d['own'])
    bpy.context.view_layer.update()
    tree, own_, boxes = _dress_tree(every)
    loose = [d for d in props if d['kind'] != 'furniture']
    loose_all = set().union(*[d['own'] for d in loose]) if loose else set()
    for d in loose:
        # a loose thing is held up by furniture or the floor, never by another loose thing it overlaps
        d['under'] = _rest(d, tree, own_, loose_all)
    bpy.context.view_layer.update()
    tree, own_, boxes = _dress_tree(every)
    v_all = None
    tops = {}
    for d in loose:
        under = d.get('under')
        if under is None or under in tops:
            continue
        sel = own_ == under
        if boxes[sel][:, 5].max() < .15:
            tops[under] = None             # the floor (many boards or tiles): anywhere in the room will do
            continue
        if v_all is None:
            v_all = {o.name: _mesh_world(o) for o in every}
        got = v_all.get(under)
        Vt = got[0] if got else _np.zeros((0, 3))
        tops[under] = _hull(Vt[Vt[:, 2] > Vt[:, 2].max() - .03][:, :2]) if len(Vt) else None
    # what a loose thing must keep out of: everything at its height that is not itself, what holds it, or another
    # loose thing (those are placed against each other below)
    loose_names = set().union(*[d['own'] for d in loose]) if loose else set()
    for d in loose:
        if 'fp' not in d:
            continue
        fp = d['fp']
        lo_, hi_ = fp['c'] - fp['h'].max() - .4, fp['c'] + fp['h'].max() + .4
        keep = ((boxes[:, 0] < hi_[0]) & (boxes[:, 3] > lo_[0]) & (boxes[:, 1] < hi_[1]) & (boxes[:, 4] > lo_[1])
                & (boxes[:, 5] > fp['low'] + .02) & (boxes[:, 2] < fp['high']))
        keep &= _np.array([o != d.get('under') and o not in loose_names for o in own_])
        d['walls'] = [dict(c=_np.array(((b[0] + b[3]) / 2, (b[1] + b[4]) / 2)), ax=(_np.array((1.0, 0)), _np.array((0, 1.0))),
                           h=_np.array(((b[3] - b[0]) / 2, (b[4] - b[1]) / 2))) for b in boxes[keep]]
    half = STG.get('half') or 13.0

    def room_ok(fp_):
        cs = _corners(fp_)
        return (_np.abs(cs[:, 0]) < half - .15).all() and (cs[:, 1] < STG['back'] - .05).all()
    order = sorted([d for d in loose if 'fp' in d], key=lambda d: -float(d['fp']['h'].prod()))      # the big ones stay put
    for i, d in enumerate(order):
        same = [e for e in order[:i] if e.get('under') == d.get('under')]
        fp, start = d['fp'], d['fp']['c'].copy()
        H = tops.get(d.get('under'))
        # standing on the surface: its middle (where its weight is) well inside the surface's edge; a printer's paper
        # tray may overhang, the way it does on a real cabinet
        fits = (lambda t_: room_ok(t_)) if H is None else (lambda t_: _inside_hull(H, t_['c'][None, :], .04 + .3 * float(t_['h'].min())))

        def clear(t_):
            return all(_mtv(t_, e['fp'], DRESS_CLEAR) is None for e in same) and all(_mtv(t_, w, DRESS_CLEAR) is None for w in d['walls'])
        for _ in range(40):
            push = next((m for m in (_mtv(fp, e['fp'], DRESS_CLEAR) for e in same) if m is not None), None)
            push = push if push is not None else next((m for m in (_mtv(fp, w, DRESS_CLEAR) for w in d['walls']) if m is not None), None)
            if push is None:
                break
            fp = dict(fp, c=fp['c'] + push)
        ok = clear(fp) and fits(fp)
        if not ok:
            # the nearest free place on the same surface, searched outward from where the set put it
            g_ = _np.arange(-.6, .61, .02)
            cand = _np.stack(_np.meshgrid(g_, g_), -1).reshape(-1, 2)
            for off in cand[_np.argsort((cand ** 2).sum(1), kind='stable')]:
                t_ = dict(fp, c=start + off)
                if fits(t_) and clear(t_):
                    fp, ok = t_, True
                    break
        if not ok:
            # no room on its own: the bigger thing in the way makes room, if it can without leaving its surface
            for e in same:
                m = _mtv(d['fp'], e['fp'], DRESS_CLEAR)
                if m is None:
                    continue
                t_ = dict(e['fp'], c=e['fp']['c'] - m)
                others_e = [x for x in order[:i] if x is not e and x.get('under') == e.get('under')]
                if fits(t_) and all(_mtv(t_, x['fp'], DRESS_CLEAR) is None for x in others_e) \
                        and all(_mtv(t_, w, DRESS_CLEAR) is None for w in e.get('walls', [])):
                    M = e['group'].matrix_world.copy()
                    M.translation.x -= float(m[0])
                    M.translation.y -= float(m[1])
                    e['group'].matrix_world = M
                    e['fp'] = t_
                    print(f"FILM set dressing: the {e['kind']} on {e.get('under')} moved {_np.hypot(*m):.2f} to make room for the "
                          f"{d['kind']}", flush=True)
                    fp, ok = d['fp'], clear(d['fp']) and fits(d['fp'])
                    break
        if not ok:
            print(f"FILM set dressing: no free place for the {d['kind']} on {d.get('under')}: left where it was", flush=True)
            continue
        shift = fp['c'] - start
        if _np.hypot(*shift) > 1e-4:
            M = d['group'].matrix_world.copy()
            M.translation.x += float(shift[0])
            M.translation.y += float(shift[1])
            d['group'].matrix_world = M
            print(f"FILM set dressing: the {d['kind']} on {d.get('under')} moved {_np.hypot(*shift):.2f} out of what was there",
                  flush=True)
        d['fp'] = fp
    bpy.context.view_layer.update()


settle_dressing()
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
# the route map's grain; how far a walking body's centre likes to keep from anything solid; the least it can pass with
CELL, BODY_R, BODY_MIN = .15, .6, .42
_ROUTE = {}


def _near_map(grid):
    """For every cell, how many cells away the nearest solid thing is (0 in it), counted up to a body's comfort."""
    R = int(math.ceil(BODY_R / CELL))
    near = _np.full(grid.shape, R + 1, _np.int8)
    for r in range(R, -1, -1):
        wide = grid.copy()
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                if (di or dj) and di * di + dj * dj <= r * r:
                    wide |= _np.roll(_np.roll(grid, di, 0), dj, 1)
        near[wide] = r
    return near


def _blocked():
    """A top-down map of what a walking body cannot pass: every face of the set between the knee and the head."""
    if 'grid' in _ROUTE:
        return _ROUTE['grid']
    x0, x1, y0, y1 = -13.0, 13.0, -14.0, STG['back'] + 2.0
    nx, ny = int((x1 - x0) / CELL) + 1, int((y1 - y0) / CELL) + 1
    grid = _np.zeros((nx, ny), bool)
    if SOLID_BOX is not None:
        band = SOLID_BOX[(SOLID_BOX[:, 5] > .2) & (SOLID_BOX[:, 2] < 2.6)]
        rng = _np.stack([(band[:, 0] - x0) / CELL, (band[:, 3] - x0) / CELL + 1, (band[:, 1] - y0) / CELL,
                         (band[:, 4] - y0) / CELL + 1], 1).astype(int)
        for i0, i1, j0, j1 in _np.unique(rng, axis=0):
            grid[max(0, i0):max(0, min(nx, i1)), max(0, j0):max(0, min(ny, j1))] = True
    _ROUTE['hard'] = grid
    _ROUTE['grid'] = (_near_map(grid), x0, y0, nx, ny)
    return _ROUTE['grid']


def _low():
    """Where something stands on the floor below the shins (a sofa's base, a table's foot, chair legs): a turning shoe
    must not sweep into it. Cell centres, (n, 2)."""
    if 'low' not in _ROUTE:
        _, x0, y0, nx, ny = _blocked()
        grid = _np.zeros((nx, ny), bool)
        if SOLID_BOX is not None:
            band = SOLID_BOX[(SOLID_BOX[:, 2] < .25) & (SOLID_BOX[:, 5] > .045)]
            rng = _np.stack([(band[:, 0] - x0) / CELL, (band[:, 3] - x0) / CELL + 1, (band[:, 1] - y0) / CELL,
                             (band[:, 4] - y0) / CELL + 1], 1).astype(int)
            for i0, i1, j0, j1 in _np.unique(rng, axis=0):
                grid[max(0, i0):max(0, min(nx, i1)), max(0, j0):max(0, min(ny, j1))] = True
        _ROUTE['low'] = _np.argwhere(grid) * CELL + _np.array((x0, y0))
    return _ROUTE['low']


def turn_spot(a, p, S, f=0):
    """Where to stand to turn round and sit on S, near p (the place right in front of it): clear of the furniture by a
    body's width, of anything at floor level by a turning shoe's sweep, and of everyone else. p when it already is;
    the nearest such place within a step's reach otherwise (they back onto the seat from there)."""
    r = a.body.footprint() if getattr(a, 'body', None) else .42
    fw, rg = _np.array(S['fwd']), _np.array(S['right'])
    g = _np.arange(-.75, .76, .05)
    off = _np.stack(_np.meshgrid(_np.arange(0, 1.01, .05), g), -1).reshape(-1, 2)
    q = _np.array(p) + off[:, :1] * fw + off[:, 1:] * rg
    cost = off[:, 0] + 1.6 * _np.abs(off[:, 1])          # a straight step back beats a sideways one
    q = q[_np.argsort(cost, kind='stable')]
    ok = (_clear('high').at(q) >= r) & (_clear('low').at(q) >= BODY.TURN_ROOM) & (_people_gap(a, f, q, 0.0) >= r)
    i = _np.nonzero(ok)[0]
    if not len(i):
        print(f"FILM {a.name}: no room to turn round in front of {S['name']}: turning where they stand", flush=True)
        return tuple(p)
    return (float(q[i[0], 0]), float(q[i[0], 1]))


def _block(bx0, by0, bx1, by1):
    """Something else now stands on the floor (a chair pulled out for whoever is coming): walks go round it too."""
    _, x0, y0, nx, ny = _blocked()
    g = _ROUTE['hard']
    g[max(0, int((bx0 - x0) / CELL)):max(0, min(nx, int((bx1 - x0) / CELL) + 1)),
      max(0, int((by0 - y0) / CELL)):max(0, min(ny, int((by1 - y0) / CELL) + 1))] = True
    _ROUTE['grid'] = (_near_map(g), x0, y0, nx, ny)
    _ROUTE.pop('cells', None)


def route(p0, p1):
    """Waypoints from p0 to p1 (x, y) that keep a walking body clear of the furniture: the cheapest path on the map
    (a body's width of room wherever there is that much, never less than the body itself), pulled straight wherever
    that costs no clearance. Just [p1] when the straight line is already clear or no route exists (the log says so)."""
    import heapq
    half = STG.get('half')
    if half and (abs(p0[0]) > half - .35 or abs(p1[0]) > half - .35):
        # coming in from off the set, or going off it: straight to (or from) just inside the side wall, round the
        # furniture in the room
        lim = half - .8
        e0 = (math.copysign(lim, p0[0]), p0[1]) if abs(p0[0]) > half - .35 else tuple(p0[:2])
        e1 = (math.copysign(lim, p1[0]), p1[1]) if abs(p1[0]) > half - .35 else tuple(p1[:2])
        inner = route(e0, e1) if math.hypot(e1[0] - e0[0], e1[1] - e0[1]) > .05 else []
        return ([e0] if e0 != tuple(p0[:2]) else []) + inner + ([tuple(p1)] if e1 != tuple(p1[:2]) else [])
    near, x0, y0, nx, ny = _blocked()
    R = int(near.max())
    cell = lambda p: (min(nx - 1, max(0, int(round((p[0] - x0) / CELL)))), min(ny - 1, max(0, int(round((p[1] - y0) / CELL)))))
    a_, b_ = cell(p0), cell(p1)
    r = int(math.ceil(.5 / CELL))      # where they start and where they are going are allowed, even beside a desk

    def ends(c):
        return any(abs(c[0] - e[0]) <= r and abs(c[1] - e[1]) <= r for e in (a_, b_))

    def line(c, d):
        n = max(abs(d[0] - c[0]), abs(d[1] - c[1]), 1)
        return [(int(round(c[0] + (d[0] - c[0]) * t / n)), int(round(c[1] + (d[1] - c[1]) * t / n))) for t in range(n + 1)]

    def clear(c, d, level):
        return all(near[q] >= level or ends(q) for q in line(c, d))
    if clear(a_, b_, R):
        return [tuple(p1)]
    path = None
    for hard in (int(math.ceil(BODY_MIN / CELL)), 1):
        best, prev, todo = {a_: 0.0}, {}, [(0.0, a_)]
        while todo:
            _, c = heapq.heappop(todo)
            if c == b_:
                break
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    d = (c[0] + di, c[1] + dj)
                    if not (di or dj) or not (0 <= d[0] < nx and 0 <= d[1] < ny):
                        continue
                    lv = int(near[d])
                    if lv <= hard and not ends(d):
                        continue
                    # squeezing past something costs more than going round with room to spare
                    g_ = best[c] + math.hypot(di, dj) * (1.0 + 1.2 * max(0, R - lv))
                    if g_ < best.get(d, 1e9):
                        best[d], prev[d] = g_, c
                        heapq.heappush(todo, (g_ + math.hypot(b_[0] - d[0], b_[1] - d[1]), d))
        if b_ in prev:
            path = [b_]
            while path[-1] != a_:
                path.append(prev[path[-1]])
            path.reverse()
            break
    if path is None:
        print(f'FILM no clear route from {tuple(round(v, 2) for v in p0)} to {tuple(round(v, 2) for v in p1)}: walking straight', flush=True)
        return [tuple(p1)]
    keep, i = [], 0
    while i < len(path) - 1:
        j = len(path) - 1
        # a corner is cut only when the straight line keeps as much room as the path it replaces
        while j > i + 1 and not clear(path[i], path[j], min([int(near[q]) for q in path[i:j + 1] if not ends(q)] or [0])):
            j -= 1
        keep.append(path[j])
        i = j
    pts = [(x0 + c[0] * CELL, y0 + c[1] * CELL) for c in keep[:-1]] + [tuple(p1)]
    print(f'FILM route around the furniture: {len(pts)} legs', flush=True)
    return pts


def occupied(a, f):
    """The floor other people take up at frame f, as discs (x, y, r): a standing body's footprint; a seated body's
    pelvis, knees and feet."""
    out = []
    for b in PERF.actors.values():
        if b is a or not b.P.vis and not b.init.get('on', True):
            continue
        b.finish()
        S = b.seat_info(f) if getattr(b, 'body', None) and b.seat_amt(f) > .5 else None
        if S is not None:
            sol = b.sit_solution(S)
            (ox, oy), fw, rg = S['origin'], S['fwd'], S['right']
            hw = b.body['hipw'] + .035
            for u, l_, r in ((sol['u'], 0, .36), (sol['knee'][0], -hw, .2), (sol['knee'][0], hw, .2),
                             (sol['ankle'][0] + .1, -hw, .24), (sol['ankle'][0] + .1, hw, .24)):
                ll = S['lat'] + l_
                out.append((ox + fw[0] * u + rg[0] * ll, oy + fw[1] * u + rg[1] * ll, r))
        else:
            p = b.locate(f)[0] if b.walks else b.pos0
            out.append((p[0], p[1], b.body.footprint() if getattr(b, 'body', None) else .42))
    return out


class _Clear:
    """How far every point of the floor is from the nearest solid thing in a height band, on a 5 cm grid: built once
    from the faces of the set (as drawn), then read in constant time. 'high' is what a standing body's legs, hips and
    arms meet (knee to head); 'low' is what a turning shoe sweeps into (below the shins)."""
    G = .05
    REACH = 1.6

    def __init__(s, lo_z, hi_z, min_top=0.0):
        s.x0, s.y0 = -14.0, -16.0
        s.nx, s.ny = int(28 / s.G) + 1, int((STG['back'] + 3 - s.y0) / s.G) + 1
        hard = _np.zeros((s.nx, s.ny), bool)
        if SOLID_BOX is not None:
            B = SOLID_BOX[(SOLID_BOX[:, 2] < hi_z) & (SOLID_BOX[:, 5] > lo_z) & (SOLID_BOX[:, 5] > min_top)]
            rng = _np.stack([(B[:, 0] - s.x0) / s.G, (B[:, 3] - s.x0) / s.G + 1, (B[:, 1] - s.y0) / s.G,
                             (B[:, 4] - s.y0) / s.G + 1], 1).astype(int)
            for i0, i1, j0, j1 in _np.unique(rng, axis=0):
                hard[max(0, i0):max(0, min(s.nx, i1)), max(0, j0):max(0, min(s.ny, j1))] = True
        s.hard = hard
        steps = int(s.REACH / s.G)
        dist = _np.full(hard.shape, s.REACH, _np.float32)
        dist[hard] = 0.0
        grow = hard.copy()
        for k in range(1, steps + 1):
            # one more ring, as a disc: a cell is k steps away when it touches a cell k-1 steps away
            nxt = grow.copy()
            nxt[1:, :] |= grow[:-1, :]
            nxt[:-1, :] |= grow[1:, :]
            nxt[:, 1:] |= grow[:, :-1]
            nxt[:, :-1] |= grow[:, 1:]
            if k % 3 == 0:          # the diagonals now and then: the rings stay round, not square
                nxt[1:, 1:] |= grow[:-1, :-1]
                nxt[:-1, :-1] |= grow[1:, 1:]
                nxt[1:, :-1] |= grow[:-1, 1:]
                nxt[:-1, 1:] |= grow[1:, :-1]
            new = nxt & ~grow
            dist[new] = k * s.G
            grow = nxt
        s.dist = dist

    def at(s, q):
        """Clearance at each point of q (n, 2), less half a cell for the grid."""
        i = _np.clip(((q[:, 0] - s.x0) / s.G).round().astype(int), 0, s.nx - 1)
        j = _np.clip(((q[:, 1] - s.y0) / s.G).round().astype(int), 0, s.ny - 1)
        return s.dist[i, j] - s.G * .71

    def crosses(s, p, q):
        """True for each point of q whose straight way from p runs through something solid (a counter, a wall)."""
        t = _np.linspace(0, 1, 32)[None, :, None]
        pts = (_np.array(p)[None, None, :] + (q[:, None, :] - _np.array(p)[None, None, :]) * t).reshape(-1, 2)
        i = _np.clip(((pts[:, 0] - s.x0) / s.G).round().astype(int), 0, s.nx - 1)
        j = _np.clip(((pts[:, 1] - s.y0) / s.G).round().astype(int), 0, s.ny - 1)
        return s.hard[i, j].reshape(len(q), -1)[:, 1:].any(1)


_CLEAR = {}


def _clear(kind):
    if kind not in _CLEAR:
        _CLEAR[kind] = _Clear(.2, 2.6) if kind == 'high' else _Clear(-1.0, .25, .045)
    return _CLEAR[kind]


def _people_gap(a, f, q, r):
    """How far each point of q is from everyone else's floor space, less r."""
    people = _np.array([(x, y, rr + .06) for x, y, rr in occupied(a, f)]).reshape(-1, 3)
    if not len(people):
        return _np.full(len(q), 9.0)
    return (_np.sqrt(((q[:, None, :] - people[None, :, :2]) ** 2).sum(-1)) - people[None, :, 2]).min(1)


def clear_spot(a, p, f=0, what='a mark'):
    """The nearest place to p where this body stands clear of the furniture (everything between knee and head height,
    as drawn) and of everyone else: p itself when it already is. Never through a wall or a counter, never out of the
    room. Logged when it moves."""
    p = (float(p[0]), float(p[1]))
    r = a.body.footprint() if getattr(a, 'body', None) else .42
    C_ = _clear('high')

    def room(q):
        return _np.minimum(C_.at(q), _people_gap(a, f, q, 0.0))
    if room(_np.array([p]))[0] >= r:
        return p
    g = _np.arange(-2.4, 2.41, .05)
    off = _np.stack(_np.meshgrid(g, g), -1).reshape(-1, 2)
    off = off[_np.argsort((off ** 2).sum(1), kind='stable')]
    q = off + _np.array(p)
    ok = room(q) >= r
    half = STG.get('half')
    if half:
        ok &= (_np.abs(q[:, 0]) < half - .3) & (q[:, 1] < STG['back'] - .3)
    idx = _np.nonzero(ok)[0][:400]
    if len(idx):
        idx = idx[~C_.crosses(p, q[idx])]
    if not len(idx):
        print(f'FILM {a.name}: no clear place to stand near {what} {tuple(round(v, 2) for v in p)}: left there', flush=True)
        return p
    best = (float(q[idx[0], 0]), float(q[idx[0], 1]))
    print(f'FILM {a.name} stands clear of the furniture and the others: {what} moved {math.hypot(best[0] - p[0], best[1] - p[1]):.2f} '
          f'to {tuple(round(v, 2) for v in best)}', flush=True)
    return best


# ------------------------------------------------------------------ seats: measured, not assumed
# A seat is whatever the set built to sit on (setkit.SEATS): a chair, a sofa, a bench, a stool. Where a body rests on
# it is measured from its own geometry as drawn: the real height of the cushion where this person sits, its front
# edge, what stands under it, the backrest, the floor in front of it, a table above the knees. body.seated then works
# out how this body, with its own legs, sits there.
import body as BODY  # noqa: E402


def _seat_frame(g):
    """(origin x, y), forward, right and yaw of the seat group g: a sitter faces its local -y."""
    rz = g.matrix_world.to_euler('XYZ').z
    o = g.matrix_world.translation
    return (o.x, o.y), (math.sin(rz), -math.cos(rz)), (math.cos(rz), math.sin(rz)), rz


def seat_at(pos):
    """The seat of the set whose sitting area holds pos -> (seat, u, lateral) or None."""
    best = None
    for sd in K.SEATS:
        (ox, oy), fw, rg, _ = _seat_frame(sd['group'])
        dx, dy = pos[0] - ox, pos[1] - oy
        u, lat = dx * fw[0] + dy * fw[1], dx * rg[0] + dy * rg[1]
        if -1.0 < u < 1.0 and abs(lat) < sd['half_width'] + .3:
            d = abs(u) + max(0.0, abs(lat) - sd['half_width'])
            if best is None or d < best[0]:
                best = (d, sd, u, lat)
    return best[1:] if best else None


def _ray_past(o, d, dist, skip):
    """The first solid thing along a ray that is not one of `skip` (names): a seat's own legs and frame are never in
    the way of its own sitter. -> (hit, normal, index, distance) as BVHTree.ray_cast"""
    if SOLID is None:
        return (None, None, None, None)
    o, d, gone = V(o), V(d).normalized(), 0.0
    for _ in range(8):
        h = SOLID.ray_cast(o, d, dist - gone)
        if h[0] is None or SOLID_OBJ[h[2]] not in skip:
            return h if h[0] is None else (h[0], h[1], h[2], gone + h[3])
        gone += h[3] + .002
        o = h[0] + d * .002
    return (None, None, None, None)


def measure_seat(sd, u0=0.0, lat=0.0, name='seat'):
    """One place to sit, as body.seated needs it (see body.py for what each number is)."""
    g = sd['group']
    own = {c.name for c in g.children_recursive} | {g.name}
    if 'tree' not in sd:
        v_, p_, _o, _b, _c = _gather([c for c in g.children_recursive if c.type == 'MESH'])
        sd['tree'] = _BVH.FromPolygons(v_, p_) if p_ else None
    T = sd['tree']
    (ox, oy), fw, rg, yaw = _seat_frame(g)
    lat = max(-sd['half_width'], min(sd['half_width'], lat))

    def at(u, l_):
        return ox + fw[0] * u + rg[0] * l_, oy + fw[1] * u + rg[1] * l_

    def down(u, l_):
        x, y = at(u, l_)
        h = T.ray_cast(V((x, y, 5.0)), V((0, 0, -1)), 6.0) if T else (None,)
        return None if h[0] is None else h[0].z

    def along(z, l_, u_from, d):
        x, y = at(u_from, l_)
        h = T.ray_cast(V((x, y, z)), V((fw[0] * d, fw[1] * d, 0)), 8.0) if T else (None,)
        return None if h[0] is None else u_from + d * h[3]
    tops = [t for t in (down(u0 + du, lat + dl) for du in (-.14, -.07, 0, .07, .14) for dl in (-.14, 0, .14)) if t is not None]
    if not tops:
        print(f'FILM {name}: nothing to sit on under the mark: sat at its height', flush=True)
        return None
    mid = sorted(tops)[len(tops) // 2]
    top = max(t for t in tops if abs(t - mid) < .08)       # the bumps of a cushion count; an armrest does not
    fronts = [h for h in (along(top - dz, lat + dl, u0 + 4, -1) for dz in (.015, .05, .09) for dl in (-.14, 0, .14)) if h is not None]
    front = max(fronts) if fronts else u0 + .3
    # what stands under the seat where heels and calves go (a sofa's base, a stool's foot), lane by lane across where
    # feet can be, at the height of a heel and a calf: a chair's seat box is above them and its legs stand out at the
    # sides, so a chair leaves room to draw the feet in under it
    lanes = []
    for dl in (-.32, -.24, -.16, -.08, 0.0, .08, .16, .24, .32):
        hs = [h for h in (along(z, lat + dl, u0 + 4, -1) for z in (.04, .1, .18, .26, .34)) if h is not None]
        if hs:
            lanes.append((round(dl, 2), max(hs)))
    base_front = max(u_ for _d, u_ in lanes) if lanes else front - .1
    backs = [h for h in (along(top + dz, lat + dl, u0 + .02, -1) for dz in (.22, .4, .58, .76) for dl in (-.12, 0, .12)) if h is not None]
    back = max(backs) if backs else None
    fx, fy = at(front + .45, lat)
    floor = surface_under(fx, fy, .35, .6)
    kx, ky = at(front + .12, lat)
    up = SOLID.ray_cast(V((kx, ky, top + .08)), V((0, 0, 1)), 1.4) if SOLID else (None,)
    # the first solid thing ahead of the seat at the height of the thighs (a desk's panel, a table's edge): the knees
    # stop short of it
    ahead = []
    for dz in (.06, .18, .3):
        for dl in (-.14, 0, .14):
            sx, sy = at(front + .01, lat + dl)
            h = _ray_past((sx, sy, top + dz), (fw[0], fw[1], 0), 3.0, own)
            if h[0] is not None:
                ahead.append(front + .01 + h[3])
    # and at the height of the feet (a table's foot, a rail between a desk's legs), across where feet can go: the toes
    # stop short of it. [(sideways from the sitter's middle, u where it starts)]
    feet = []
    fz0 = floor if floor is not None else 0.0
    for dl in _np.arange(-.4, .41, .08):
        hit = []
        for dz in (.03, .1, .18):
            sx, sy = at(front + .01, lat + dl)
            h = _ray_past((sx, sy, fz0 + dz), (fw[0], fw[1], 0), 3.0, own)
            if h[0] is not None:
                hit.append(front + .01 + h[3])
        if hit:
            feet.append((round(float(dl), 2), min(hit)))
    S = dict(id=f'{name}@{g.name}:{lat:.2f}', name=name, kind=sd['kind'], group=g, origin=(ox, oy), fwd=fw, right=rg, yaw=yaw,
             lat=lat, prefer=u0, top=top, soft=sd['soft'], front=front, base_front=base_front, back=back,
             floor=fz0, under=None if up[0] is None else up[0].z, ahead=min(ahead) if ahead else None, feet_ahead=feet,
             base_front_at=lanes,
             movable=g.name.split('.')[0] in ('chair', 'taskchair'), cushions=sd['cushions'])
    bk_ = '-' if back is None else '%.2f' % back
    tb_ = '-' if S['under'] is None else '%.2f' % S['under']
    fa_ = '-' if not feet else '%.2f' % min(u_ for _d, u_ in feet)
    print(f"FILM seat {name}: {sd['kind']} top {top:.3f} front {front:.2f} under-front {base_front:.2f} back {bk_} table {tb_}"
          f" feet-room {fa_}", flush=True)
    return S


for _n, _m in MARKS.items():
    if _m.get('seat'):
        _f = seat_at(_m['pos'])
        if _f is None:
            print(f'FILM the {_n} mark is a seat with nothing to sit on: sat at its height, with nothing measured', flush=True)
            continue
        _m['seat_aff'] = measure_seat(_f[0], _f[1], _f[2], _n)


def seat_ground(S, body, actor=None):
    """Where someone stands to sit down on S, or stands after getting up: at a chair, where the chair was (it is pulled
    back out of the way); in front of anything that stays put, far enough out to turn round without a foot sweeping
    into it. Sitting down from there is a small step back and down (acting: the seated block)."""
    (ox, oy), fw, rg = S['origin'], S['fwd'], S['right']
    if S.get('movable'):
        u = S['prefer']
        return (ox + fw[0] * u + rg[0] * S['lat'], oy + fw[1] * u + rg[1] * S['lat'])
    u = BODY.stand_point(body, S, BODY.seated(body, S, prefer=S['prefer']))
    p = (ox + fw[0] * u + rg[0] * S['lat'], oy + fw[1] * u + rg[1] * S['lat'])
    return turn_spot(actor, p, S) if actor is not None else p


SEATED = {}     # seat mark -> the actors sitting on it now (a bench or a sofa has room for two)


def seat_for(a, name, m):
    """The measured seat for actor a at the seat mark `name`: the mark's own place, or beside whoever already sits there
    when the seat is long enough for two (a bench, a sofa), measured again at that place."""
    S = (m or {}).get('seat_aff')
    if not isinstance(S, dict):
        return (m or {}).get('seat')
    for k_ in list(SEATED):
        if a in SEATED[k_] and k_ != name:
            SEATED[k_].remove(a)
    here = SEATED.setdefault(name, [])
    there = [b for b in here if b is not a]
    if a not in here:
        here.append(a)
    if not there:
        return S
    if len(there) >= m.get('room', 1):
        print(f"FILM {a.name}: the {name} seat is taken by {there[0].name} and has no room beside them", flush=True)
        return S
    sd = next((x for x in K.SEATS if x['group'] is S['group']), None)
    if sd is None:
        return S
    used = [getattr(b, 'seat_lat', S['lat']) for b in there]
    step = (a.body.footprint() + max(b.body.footprint() for b in there if getattr(b, 'body', None))) * 1.1 if getattr(a, 'body', None) else 1.0
    for lat in sorted((u_ + sg * step for u_ in used for sg in (1, -1)), key=abs):
        if abs(lat) <= sd['half_width'] and all(abs(lat - u_) >= step - 1e-6 for u_ in used):
            a.seat_lat = lat
            print(f"FILM {a.name} sits beside {there[0].name} on the {name}", flush=True)
            return measure_seat(sd, S['prefer'], lat, f'{name}:{a.name}')
    print(f"FILM {a.name}: no room beside {there[0].name} on the {name}", flush=True)
    return S


def body_of(P):
    """A sculpted puppet's measurements for body.py; None for a model somebody brought (it does not sit)."""
    if getattr(P, 'guest', False):
        return None
    b = P.base
    hipzone = b[_np.abs(b[:, 2]) < .12]
    return BODY.Body.from_meta(P.m, torso_back=float(hipzone[:, 1].max()) if len(hipzone) else .24)


# ------------------------------------------------------------------ the cast
spots = list(STG['spots'])


def where(c):
    """-> (x, y), facing, seat (a measured seat, a height, or None)"""
    m = MARKS.get(c.get('mark') or '')
    if m:
        # a seat faces its table; on a standing mark nobody is pinned to the lens: they turn to whoever matters (acting.res_face)
        seat = (m.get('seat_aff') or m.get('seat')) if c.get('seat', True) and m.get('seat') else None
        return m['pos'], c.get('face', m.get('face')), seat
    if c.get('pos'):
        seat = None
        if c.get('seat') is True:
            f_ = seat_at(c['pos'])
            seat = (measure_seat(f_[0], f_[1], f_[2], c['id']) if f_ else None) or A.SEAT_H
        return tuple(c['pos']), c.get('face', 0.0), seat
    return (spots.pop(0) if spots else (0, 0)), c.get('face', None), None


def offscreen(pos):
    """Out of sight, on the nearer side: where someone walks in from, or out to, when the set has no door (through the
    opening in that side wall, when the room has one)."""
    ps = STG.get('passage')
    return ((-13.5 if pos[0] < 0 else 13.5), (ps[0] + ps[1]) / 2 if ps else pos[1] + .6)


TAKEN = {c.get('mark') for c in JOB.get('cast') or []}
DOORS = [list(d) for d in JOB.get('door') or []]     # [open, close] frames


def free_seat(a, f):
    """The nearest seat nobody is using."""
    here = a.locate(f)[0]
    seats = [(n, m) for n, m in MARKS.items() if m.get('seat') and (n not in TAKEN or len(SEATED.get(n, [])) < m.get('room', 1))]
    if not seats:
        return None
    n, m = min(seats, key=lambda q: (q[1]['pos'][0] - here[0]) ** 2 + (q[1]['pos'][1] - here[1]) ** 2)
    TAKEN.add(n)
    return m


for c in JOB.get('cast') or []:
    pos, face, seat = where(c)
    init = dict(f=c.get('feeling', 'neutral'), face=face)
    start = c.get('enter_from')
    if c.get('model'):
        import guest
        body = guest.Guest(c['id'], c['model'], JOB.get('aliases') or {}, c.get('model_yaw') or 0.0)
        seat = None                     # a guest stands: sitting needs the sculpted legs
    else:
        body = Puppet(c.get('rig') or c['id'])
    bd = body_of(body)
    a = PERF.add(A.Actor(c['id'], body, pos, c.get('style'), **init))
    a.body = bd
    if isinstance(seat, dict) and not start:
        seat = seat_for(a, c.get('mark'), MARKS.get(c.get('mark') or ''))
    if seat and not start:
        # somebody who walks in sits down when they get there (see the keys below), not before
        a.init['seat'] = seat
        a.keys = [(-999, dict(a.init))]
    if bd is not None:
        # a body's own proportions show in how it walks: longer legs take longer steps, a heavier build moves more
        a.st['step'] = round(a.st['step'] * max(.85, min(1.18, bd['thigh'] / .72)), 4)
        a.st['bob'] = round(a.st['bob'] * max(.85, min(1.2, (bd['hw'] / .33) ** .7)), 4)
    home = seat_ground(seat, bd, a) if isinstance(seat, dict) and bd is not None else pos
    p0 = MARKS[start]['pos'] if start in MARKS else (offscreen(home) if start else home)
    a.pos0 = tuple(p0) + ((0,) if len(p0) == 2 else ())
    a.home = home
    a.mark = MARKS.get(c.get('mark') or '')
    a.entering = bool(start)
    if 'on' in c:
        a.init['on'] = bool(c['on'])
_OWNER = {o.name: a.P for a in PERF.actors.values() for o in getattr(a.P, 'parts', [])}
for ln in JOB.get('lines') or []:
    PERF.say(ln['who'], ln['start'], ln['end'], ln.get('cues') or [], ln.get('to'), ln.get('manual') or (), ln.get('feeling'))
for nm, t in STG['things'].items():
    PERF.things[nm] = t


# ------------------------------------------------------------------ chairs: pushed back to stand, drawn in to sit
# how far a chair is pushed back from where it is sat in; how far behind where they sat someone who has stood up stands;
# how far to its side people step in
PULL, STAND_BACK, SIDE = .8, .22, .95
ALL_CHAIRS = []
for g_ in bpy.data.objects:
    if g_.type == 'EMPTY' and g_.parent is None and g_.name.split('.')[0] in ('chair', 'taskchair'):
        rz_ = g_.rotation_euler.z
        # an office chair rolls further: its five-star base is wider than its seat
        ALL_CHAIRS.append(dict(g=g_, pos=(g_.location.x, g_.location.y), z=g_.location.z, back=(-math.sin(rz_), math.cos(rz_)),
                               meshes=[c for c in g_.children_recursive if c.type == 'MESH'], users=[], off=0.0,
                               far=PULL + (.25 if g_.name.startswith('taskchair') else 0.0), pull=PULL, stand=0.0))


def _chair_at(pos, r=.5):
    return next((ch for ch in ALL_CHAIRS if math.hypot(ch['pos'][0] - pos[0], ch['pos'][1] - pos[1]) < r), None)


def _chair_room(ch):
    """How far this chair can be pushed back before it meets a wall or other furniture."""
    if SOLID_BOX is None:
        return ch['far'] + STAND_BACK
    own = _np.isin(SOLID_OBJ, [o.name for o in ch['meshes']])
    if not own.any():
        return ch['far'] + STAND_BACK
    mine, rest = SOLID_BOX[own], SOLID_BOX[~own & (SOLID_BOX[:, 5] > .15)]
    lo, hi = mine[:, :3].min(axis=0) + .02, mine[:, 3:].max(axis=0) - .02
    d = ch['far'] + STAND_BACK
    while d > 1e-3:
        l_, h_ = lo + (ch['back'][0] * d, ch['back'][1] * d, 0), hi + (ch['back'][0] * d, ch['back'][1] * d, 0)
        if not ((rest[:, 0] <= h_[0]) & (rest[:, 3] >= l_[0]) & (rest[:, 1] <= h_[1]) & (rest[:, 4] >= l_[1])
                & (rest[:, 2] <= h_[2]) & (rest[:, 5] >= l_[2])).any():
            return d
        d -= .05
    return 0.0


def _seat_side(m, other):
    """Where to step in beside the chair at seat mark m (or step out to), on the side nearer `other`: people get into
    a chair from its side, not through its back or over the table."""
    ch = _chair_at(m['pos']) if m and m.get('seat') else None
    if ch is None:
        return None
    near, x0, y0, nx, ny = _blocked()
    sx, sy = -ch['back'][1], ch['back'][0]
    best = None
    for sg in (1, -1):
        q = (m['pos'][0] + sg * sx * SIDE, m['pos'][1] + sg * sy * SIDE)
        i, j = int(round((q[0] - x0) / CELL)), int(round((q[1] - y0) / CELL))
        if 0 <= i < nx and 0 <= j < ny and near[i, j] >= int(math.ceil(BODY_MIN / CELL)):
            d = math.hypot(q[0] - other[0], q[1] - other[1])
            if best is None or d < best[0]:
                best = (d, q)
    return best[1] if best else None


def route_to(a, f, dest, m=None):
    """Every waypoint of a walk from where the actor is at f: out by the side of the chair they are leaving, round the
    furniture, and in by the side of the chair they are going to."""
    here = a.locate(f)[0]
    start, pts = (here[0], here[1]), []
    if math.hypot(dest[0] - start[0], dest[1] - start[1]) < .3:
        return [tuple(dest)]        # already there (someone who stands up where they sat): no way round to find
    m0 = getattr(a, 'mark', None)
    if (m or {}).get('seat_aff') is not None and not m['seat_aff'].get('movable'):
        return pts + route(start, dest)       # a sofa or a bench: its standing place has room to turn round in
    if m0 and m0.get('seat') and math.hypot(m0['pos'][0] - start[0], m0['pos'][1] - start[1]) < .3:
        out = _seat_side(m0, dest)
        if out is not None:
            pts.append(out)
            start = out
    side = _seat_side(m, start)
    if side is not None:
        ch = _chair_at(m['pos'])
        if not ch.get('waits'):
            # the chair stands pushed back until they sit: nobody walks through where it waits
            ch['waits'] = True
            room = min(ch['far'], _chair_room(ch))
            bx, by = ch['pos'][0] + ch['back'][0] * (room + .12), ch['pos'][1] + ch['back'][1] * (room + .12)
            _block(bx - .5, by - .5, bx + .5, by + .5)
            side = _seat_side(m, start) or side
        pts += route(start, side)
        pts.append(tuple(dest))
    else:
        pts += route(start, dest)
    return pts


def walk_route(a, f, dest, speed=None, m=None):
    """Walk to dest around whatever is in the way: one walk per leg, each turning into the next."""
    t = f
    for wp in route_to(a, f, dest, m):
        t = a.walk(t, wp, speed=speed)
    return t


def route_length(a, f, dest, m=None):
    here = a.locate(f)[0]
    pts = [(here[0], here[1])] + route_to(a, f, dest, m)
    return sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(pts, pts[1:]))


def chairs_at(f):
    """A chair somebody uses is where their body needs it: pushed back while they stand at it (and left there when they
    go, and waiting there before they come), drawn in under them as they sit."""
    global SOLID
    moved = False
    for ch in CHAIRS:
        s_ = 0.0
        for a in ch['users']:
            p = a.locate(f)[0]
            if math.hypot(p[0] - ch['pos'][0], p[1] - ch['pos'][1]) < .7:
                s_ = max(s_, a.seat_amt(f))
        # it stays out until they have turned to it, stepped their feet where they will sit (acting: one foot and then
        # the other, done by .54 of the way) and begun to lower, and is home before they are all the way down
        off = ch['pull'] * A.clamp(1 - (s_ - .55) / .35) + ch['stand'] * max((a.stood_up(f) for a in ch['users']), default=0.0)
        if abs(off - ch['off']) > 1e-4:
            ch['off'] = off
            ch['g'].location = (ch['pos'][0] + ch['back'][0] * off, ch['pos'][1] + ch['back'][1] * off, ch['z'])
            moved = True
    if moved:
        bpy.context.view_layer.update()
        SOLID = _solid_tree()


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


_PT = {}       # part name -> (its puppet's pose count, tree, vertices): a part is measured once per pose, not per question


def _faces_of(me, key):
    import contacts as _ct
    return _ct.faces_of(me, key)


def _part_tree(o):
    """A part of a puppet as it is posed now: a tree of its faces, and its vertices (world). Puppet parts carry no
    modifiers (they are posed by moving their vertices), so their own mesh is what is drawn."""
    P = _OWNER.get(o.name)
    ver = getattr(P, 'ver', None)
    got = _PT.get(o.name)
    if got is not None and ver is not None and got[0] == ver:
        return got[1], got[2]
    ev = None
    me = o.data
    if o.modifiers:
        ev = o.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = ev.to_mesh()
    try:
        co = _np.empty(len(me.vertices) * 3, _np.float64)
        me.vertices.foreach_get('co', co)
        polys = _faces_of(me, o.name) if len(me.polygons) else []
    finally:
        if ev is not None:
            ev.to_mesh_clear()
    M = _np.array(o.matrix_world, dtype=_np.float64)
    co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    t = _BVH.FromPolygons(co.tolist(), polys) if polys else None
    if ver is not None:
        _PT[o.name] = (ver, t, co)
    return t, co


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


def _closest(p0, p1, q0, q1):
    """The closest points of segments p0-p1 and q0-q1: (point on p, point on q, how far along p, how far along q)."""
    d1, d2, r = p1 - p0, q1 - q0, p0 - q0
    a, e, f_ = float(d1 @ d1), float(d2 @ d2), float(d2 @ r)
    c, b = float(d1 @ r), float(d1 @ d2)
    den = a * e - b * b
    s_ = min(1.0, max(0.0, (b * f_ - c * e) / den)) if den > 1e-12 else 0.0
    t_ = (b * s_ + f_) / e if e > 1e-12 else 0.0
    if t_ < 0 or t_ > 1:
        t_ = min(1.0, max(0.0, t_))
        s_ = min(1.0, max(0.0, (b * t_ - c) / a)) if a > 1e-12 else 0.0
    return p0 + d1 * s_, q0 + d2 * t_, s_, t_


def _seat_contact_gap(a):
    """How far the lowest of what a seated body rests on (the bottom of its torso, the undersides of its thighs: PROX's
    contact regions, as contacts._seat_gap measures them) is above the seat straight under it, less CLEAR; negative when
    it is in the seat, None when nothing is under it."""
    def lowest(co, k=48):
        # the k lowest points of a part: wherever it rests, it rests on one of them
        return co[_np.argpartition(co[:, 2], k)[:k]] if len(co) > k else co

    pts = []
    to_ = _part(a, '_torso')
    if to_ is not None:
        co_ = _part_tree(to_)[1]
        if co_ is not None and len(co_):
            pts.append(lowest(co_))
    for sd in ('L', 'R'):
        lo_, lb_ = _part(a, '_l' + sd), getattr(a.P, 'legLt' if sd == 'L' else 'legRt', None)
        if lo_ is None or lb_ is None:
            continue
        co_ = _part_tree(lo_)[1]
        th_ = co_[:lb_.seg * lb_.n1] if co_ is not None else None
        if th_ is not None and len(th_):
            pts.append(lowest(th_))
    best = None
    for p_ in (_np.concatenate(pts) if pts else ()):
        top_ = surface_under(float(p_[0]), float(p_[1]), float(p_[2]) + .3, .6)
        if top_ is not None:
            g_ = float(p_[2]) - top_ - CLEAR
            best = g_ if best is None else min(best, g_)
    return best


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
    if depth == 0:
        chairs_at(f)
    bpy.context.view_layer.update()
    again = []
    for a in PERF.actors.values():
        if getattr(a.P, 'guest', False) or getattr(a, 'cull', False) or not a.P.vis:
            continue
        cur = a.state(f)[1][1]
        moved = False
        # half way into a chair or out of it nothing is learnt for later: what is measured then is true of that
        # drawing only, and would be carried into the sitting or the standing that follows
        mid = .02 < a.seat_amt(f) < .98
        if cur.get('seat') and not mid and not isinstance(cur.get('seat'), dict):
            # (a seat measured from the set is solved, body.seated: this learning is for a seat given by height only)
            # the thighs rest on the seat too: while either is in it, the body comes up a centimetre at a time
            rx, ry = a.P.root.matrix_world.translation.xy
            top, seat_o = surface_under(rx, ry, 1.2, 1.2, which=True)     # from under a table top, down to the seat
            top = top or 0.0
            legs = [_inside(_part(a, '_l' + sd), top - .3, top + .1, only=seat_o)[0] for sd in ('L', 'R')]
            # a thigh in the top of the seat: the body comes up a centimetre at a time
            thighs_in = any(len(p_) and (p_[:, 2] >= top - .02).any() for p_ in legs)
            # a knee against the underside of the table they sit at: that foot goes forward, and the knee comes down
            yw_ = a.last_yaw or 0.0
            for sd, in_seat in zip(('L', 'R'), legs):
                # ...and a calf against the front edge or the corner of the seat: the same, and the shin swings clear
                edge = len(in_seat) and not (in_seat[:, 2] >= top - .02).any()
                if edge or len(_inside(_part(a, '_l' + sd), top + .3, top + 1.0)[0]):
                    push = getattr(a, 'foot_push', {})
                    px, py = push.get((a.spot, sd), (0.0, 0.0))
                    if math.hypot(px, py) < .45:
                        push[(a.spot, sd)] = (px + .05 * math.sin(yw_), py - .05 * math.cos(yw_))
                        a.foot_push = push
                        moved = True
            g_ = _gap(_part(a, '_torso'), .3)
            if thighs_in and getattr(a, 'seat_lift', 0.0) < .3:
                a.seat_lift = getattr(a, 'seat_lift', 0.0) + .01
                moved = True
            # up out of the seat at any time; down onto it only once they have been sitting a second (sitting down
            # passes above the seat, and that is not hovering) and only while the thighs are clear of it
            elif g_ is not None and (g_ < -.002 or (g_ > .003 and not thighs_in and _seated_for(a, f) > 24)):
                a.seat_lift = getattr(a, 'seat_lift', 0.0) - g_
                moved = True
        if isinstance(cur.get('seat'), dict) and a.seat_amt(f) > .98 and not cur['seat'].get('soft'):
            # a measured hard seat: the body rests on it exactly, not above it and not in it. The seat is solved from the
            # body's average shape (body.seated); the trousers' real thickness, a tunic's pressed hem and the clay's own
            # lumps are measured here, where the body rests, and it comes down onto the seat (or up out of it) by what is
            # found, for as long as it sits on that seat. (A cushion is pressed to meet the body instead: press_cushions.)
            g_ = _seat_contact_gap(a)
            sid_ = cur['seat'].get('id')
            rise_ = getattr(a, 'seat_rise', {})
            if g_ is not None and abs(g_) > .002 and abs(rise_.get(sid_, 0.0) - g_) < .25:
                rise_[sid_] = rise_.get(sid_, 0.0) - g_
                a.seat_rise = rise_
                moved = True
        if isinstance(cur.get('seat'), dict) and a.seat_amt(f) > .98:
            # the head and the hair stay off the backrest: found in it (a ponytail against a chair's back), the body sits
            # a little further forward, for as long as it sits there
            sid_ = cur['seat'].get('id')
            for p_ in ('_hair', '_h'):
                o_ = _part(a, p_)
                if o_ is not None and len(_inside(o_)[0]):
                    sf_ = getattr(a, 'sit_fwd', {})
                    if sf_.get(sid_, 0.0) < .15:
                        sf_[sid_] = sf_.get(sid_, 0.0) + .015
                        a.sit_fwd = sf_
                        moved = True
                    break
        if cur.get('hL') is not None or cur.get('hR') is not None:
            lifts = getattr(a, 'hand_lift', {})
            for side in ('L', 'R'):
                g_ = _gap(_part(a, '_h' + side), .25)
                if g_ is not None and g_ < -.002:
                    lifts[side] = lifts.get(side, 0.0) - g_
                    moved = True
                # a forearm lying across the table's edge goes through it, or the hand itself overhangs the edge
                # and cuts into it: the hands come up until both clear
                elif (len(_inside(_part(a, '_a' + side), .9, 2.2)[0]) or len(_inside(_part(a, '_h' + side), .9, 2.2)[0])) \
                        and lifts.get(side, 0.0) < .25:
                    lifts[side] = lifts.get(side, 0.0) + .01
                    moved = True
            a.hand_lift = lifts
        # a hand in a gesture that ends inside something on the set (a mug, a machine, a screen) is nudged clear of it,
        # for that gesture only
        nudges = getattr(a, 'hand_nudge', {})
        # ...and a hand still on its way to the gesture goes round what it meets, for this drawing only (carried on, a
        # little less, into the next, so it never jumps)
        now = getattr(a, 'hand_now', None)
        if not now or now.get('f') != f:
            last = now if now and 0 < f - now.get('f', -99) <= 2 else {}
            now = {'f': f, 'L': tuple(.6 * v for v in last.get('L', (0.0, 0.0, 0.0))), 'R': tuple(.6 * v for v in last.get('R', (0.0, 0.0, 0.0)))}
            if any(now['L']) or any(now['R']):
                moved = True
        for side in ('L', 'R'):
            if cur.get('h' + side) is not None:
                continue
            pts, co = _inside(_part(a, '_h' + side), .3, 9.0)
            if not len(pts):
                pts, co = _inside(_part(a, '_a' + side), .9, 9.0)      # the forearm behind it counts too
            if len(pts) and co is not None:
                # out of it the shortest way: along the face of whatever is nearest the hand (a wall, a machine's side),
                # not away from the middle of a big face that may be a room away
                c_ = co.mean(axis=0)
                near_ = SOLID.find_nearest(V((float(c_[0]), float(c_[1]), float(c_[2]))))
                d = _np.array(near_[1]) if near_[1] is not None else c_ - pts.mean(axis=0)
                n = float(_np.linalg.norm(d))
                d, n = (d, n) if n > 1e-4 else (_np.array([0.0, 0.0, 1.0]), 1.0)
                kf = a.state(f)[1][0]
                # in a counter or a table from the side: straight up onto its top, in one measured step
                lo_ = co[int(_np.argmin(co[:, 2]))]
                top_ = surface_under(float(lo_[0]), float(lo_[1]), float(lo_[2]) + .5, .5)
                if top_ is not None and top_ > float(lo_[2]) + .002:
                    d, n = _np.array([0.0, 0.0, (top_ - float(lo_[2]) + CLEAR) / .04]), 1.0
                key = (side, kf)
                spent = math.sqrt(sum(v * v for v in nudges.get(key, (0.0, 0.0, 0.0)))) >= .6 or depth >= 12
                if f - kf < 30 or spent:
                    # (also a hand at rest that a turn of the body swings into something: a gesture's own nudge can
                    # only do so much, and then the hand goes round for this drawing)
                    nx, ny, nz = now[side]
                    if math.sqrt(nx * nx + ny * ny + nz * nz) < .6:
                        # up and out: over the edge of a table rather than through it
                        now[side] = (nx + .04 * d[0] / n, ny + .04 * d[1] / n, nz + .04 * max(d[2] / n, .5))
                        moved = True
                else:
                    nx, ny, nz = nudges.get(key, (0.0, 0.0, 0.0))
                    if math.sqrt(nx * nx + ny * ny + nz * nz) < .6:
                        nudges[key] = (nx + .04 * d[0] / n, ny + .04 * d[1] / n, nz + .04 * d[2] / n)
                        moved = True
        a.hand_nudge = nudges
        a.hand_now = now
        # seated, a hand resting on a thigh rests on it: found inside it, it comes up a little; and two hands that rest
        # side by side do not grow into each other: each moves away from the other, for that pose only
        if a.seat_amt(f) > .98 and getattr(a, 'body', None) is not None:
            ll = getattr(a, 'lap_lift', {})
            for side in ('L', 'R'):
                hnd = _part(a, '_h' + side)
                if hnd is None or cur.get('h' + side) is not None:
                    continue
                th_, _ = _part_tree(hnd)
                for leg in ('_lL', '_lR'):
                    tl_, _ = _part_tree(_part(a, leg))
                    if th_ is not None and tl_ is not None and th_.overlap(tl_) and ll.get(side, 0.0) < .12:
                        ll[side] = ll.get(side, 0.0) + .008
                        moved = True
                        break
            a.lap_lift = ll
        tL_, cL_ = _part_tree(_part(a, '_hL')) if _part(a, '_hL') is not None else (None, None)
        tR_, cR_ = _part_tree(_part(a, '_hR')) if _part(a, '_hR') is not None else (None, None)
        # (hands that meet by design, palms together or clasped, meet: they end touching, never one inside the other)
        if tL_ is not None and tR_ is not None and tL_.overlap(tR_):
            kf_ = a.state(f)[1][0]
            d_ = cR_.mean(axis=0) - cL_.mean(axis=0)
            d_ = d_ / (float(_np.linalg.norm(d_)) or 1.0)
            for side, sg_ in (('L', -1), ('R', 1)):
                if f - kf_ < 30:
                    # on their way from one gesture to the next it is the last gesture's hands that are still together:
                    # apart for this drawing (and a little less into the next), not for the whole of the new gesture
                    nx, ny, nz = now[side]
                    if math.sqrt(nx * nx + ny * ny + nz * nz) < .45:
                        now[side] = (nx + .015 * sg_ * d_[0], ny + .015 * sg_ * d_[1], nz)
                        moved = True
                    continue
                nx, ny, nz = nudges.get((side, kf_), (0.0, 0.0, 0.0))
                if math.sqrt(nx * nx + ny * ny + nz * nz) < .3:
                    nudges[(side, kf_)] = (nx + .015 * sg_ * d_[0], ny + .015 * sg_ * d_[1], nz)
                    moved = True
        # ...and a hand never sinks into the other arm (hands resting close together in a lap, a hand laid on a forearm):
        # it goes out of that sleeve the shortest way, from the nearest point of its surface
        for side, other in (('L', 'R'), ('R', 'L')):
            th_, hco_ = (tL_, cL_) if side == 'L' else (tR_, cR_)
            ao_ = _part(a, '_a' + other)
            if th_ is None or ao_ is None or cur.get('h' + side) is not None:
                continue
            ta_ = _part_tree(ao_)[0]
            if ta_ is None or not th_.overlap(ta_):
                continue
            c_ = hco_.mean(axis=0)
            near_ = ta_.find_nearest(V((float(c_[0]), float(c_[1]), float(c_[2]))))
            if near_[0] is None:
                continue
            d_ = c_ - _np.array(near_[0])
            if float(_np.dot(d_, _np.array(near_[1]))) <= 0 or float(_np.linalg.norm(d_)) < 1e-4:
                d_ = _np.array(near_[1])          # the middle of the hand is inside the sleeve: out along its face
            d_ = d_ / (float(_np.linalg.norm(d_)) or 1.0)
            kf_ = a.state(f)[1][0]
            if f - kf_ < 30:
                nx, ny, nz = now[side]
                if math.sqrt(nx * nx + ny * ny + nz * nz) < .45:
                    now[side] = (nx + .012 * d_[0], ny + .012 * d_[1], nz + .012 * d_[2])
                    moved = True
                continue
            nx, ny, nz = nudges.get((side, kf_), (0.0, 0.0, 0.0))
            if math.sqrt(nx * nx + ny * ny + nz * nz) < .3:
                nudges[(side, kf_)] = (nx + .012 * d_[0], ny + .012 * d_[1], nz + .012 * d_[2])
                moved = True
        # ...and two forearms that cross (arms folded, a hand on the other arm) lie one on the other, never through it: the
        # arm in front, where the two come closest, moves off the other along the line between them, a little at a time
        aoL_, aoR_ = _part(a, '_aL'), _part(a, '_aR')
        pl_ = getattr(a.P, 'palm', None)
        if aoL_ is not None and aoR_ is not None and pl_ and hasattr(a.P, 'armlog') and cur.get('hL') is None and cur.get('hR') is None:
            tLa_, tRa_ = _part_tree(aoL_)[0], _part_tree(aoR_)[0]
            if tLa_ is not None and tRa_ is not None and tLa_.overlap(tRa_) and all(sd in a.P.armlog for sd in 'LR'):
                seg_ = {sd: (_np.array(a.P.armlog[sd][0]), _np.array(pl_[sd].matrix_world.translation)) for sd in 'LR'}
                c1_, c2_, s1_, s2_ = _closest(*seg_['L'], *seg_['R'])
                yw_ = a.last_yaw or 0.0
                fwd_ = _np.array((math.sin(yw_), -math.cos(yw_), 0.0))
                front_ = 'L' if float((c1_ - c2_) @ fwd_) >= 0 else 'R'
                d_ = (c1_ - c2_) if front_ == 'L' else (c2_ - c1_)
                if float(_np.linalg.norm(d_)) < 1e-4:
                    d_ = fwd_ + _np.array((0.0, 0.0, .5))
                d_ = d_ / float(_np.linalg.norm(d_))
                along_ = max(.35, s1_ if front_ == 'L' else s2_)       # moving the hand moves the crossing this much less
                kf_ = a.state(f)[1][0]
                step_ = .012 / along_
                if f - kf_ < 30:
                    nx, ny, nz = now[front_]
                    if math.sqrt(nx * nx + ny * ny + nz * nz) < .45:
                        now[front_] = (nx + step_ * d_[0], ny + step_ * d_[1], nz + step_ * d_[2])
                        moved = True
                else:
                    nx, ny, nz = nudges.get((front_, kf_), (0.0, 0.0, 0.0))
                    if math.sqrt(nx * nx + ny * ny + nz * nz) < .3:
                        nudges[(front_, kf_)] = (nx + step_ * d_[0], ny + step_ * d_[1], nz + step_ * d_[2])
                        moved = True
        a.hand_nudge = nudges
        # a hand is never inside its own body: found in the chest, the belly or a hip (fingers that point at the body
        # while the wrist is clear, an arm swinging past the hip), it goes out from the middle of the body, for this
        # drawing, and a little less into the next
        tt_, _tco = _part_tree(_part(a, '_torso')) if _part(a, '_torso') is not None else (None, None)
        if tt_ is not None:
            rt_ = a.P.root.matrix_world.translation
            for side in ('L', 'R'):
                if cur.get('h' + side) is not None or _part(a, '_h' + side) is None:
                    continue
                th_, hco_ = _part_tree(_part(a, '_h' + side))
                if th_ is not None and th_.overlap(tt_):
                    c_ = hco_.mean(axis=0)
                    d_ = _np.array((c_[0] - rt_.x, c_[1] - rt_.y))
                    d_ = d_ / (float(_np.linalg.norm(d_)) or 1.0)
                    nx, ny, nz = now[side]
                    if math.sqrt(nx * nx + ny * ny + nz * nz) < .45:
                        now[side] = (nx + .025 * d_[0], ny + .025 * d_[1], nz)
                        moved = True
                # ...nor in its own legs: sitting down, a hand on its way to the lap comes down onto a thigh, not into
                # it; standing, a hand passing a thigh goes out round it
                for leg_ in ('_lL', '_lR'):
                    lo_ = _part(a, leg_)
                    tl_ = _part_tree(lo_)[0] if lo_ is not None else None
                    if th_ is None or tl_ is None or not th_.overlap(tl_):
                        continue
                    nx, ny, nz = now[side]
                    if math.sqrt(nx * nx + ny * ny + nz * nz) < .45:
                        if a.seat_amt(f) > .5:
                            now[side] = (nx, ny, nz + .015)
                        else:
                            c_ = hco_.mean(axis=0)
                            d_ = _np.array((c_[0] - rt_.x, c_[1] - rt_.y))
                            d_ = d_ / (float(_np.linalg.norm(d_)) or 1.0)
                            now[side] = (nx + .02 * d_[0], ny + .02 * d_[1], nz)
                        moved = True
                    break
        # ...and no forearm or elbow in its own body past the shoulder (a forearm across a stomach, resting hands on the
        # thighs of a broad body): the hand goes out from the middle of the body, for that pose (for the drawing only
        # on the way from one gesture to the next)
        if tt_ is not None:
            kfa_ = a.state(f)[1][0]
            for side in ('L', 'R'):
                ao_ = _part(a, '_a' + side)
                if ao_ is None or cur.get('h' + side) is not None:
                    continue
                ta_ = _part_tree(ao_)[0]
                lb_ = CT._limb(a, 'a' + side)
                pr_ = ta_.overlap(tt_) if ta_ is not None else []
                if not pr_ or lb_ is None or not CT._past_join(pr_, *lb_):
                    continue
                hco_ = _part_tree(_part(a, '_h' + side))[1] if _part(a, '_h' + side) is not None else None
                if hco_ is None:
                    continue
                c_ = hco_.mean(axis=0)
                d_ = _np.array((c_[0] - rt_.x, c_[1] - rt_.y))
                d_ = d_ / (float(_np.linalg.norm(d_)) or 1.0)
                if f - kfa_ < 30:
                    nx, ny, nz = now[side]
                    if math.sqrt(nx * nx + ny * ny + nz * nz) < .45:
                        now[side] = (nx + .02 * d_[0], ny + .02 * d_[1], nz)
                        moved = True
                else:
                    nx, ny, nz = nudges.get((side, kfa_), (0.0, 0.0, 0.0))
                    if math.sqrt(nx * nx + ny * ny + nz * nz) < .3:
                        nudges[(side, kfa_)] = (nx + .02 * d_[0], ny + .02 * d_[1], nz)
                        moved = True
        # a thing carried in a hand never goes into the body that carries it (a mug lowered past a thigh): that hand
        # comes up, for this drawing, and a little less into the next
        own_ = [t_ for t_ in (_part_tree(_part(a, s_))[0] for s_ in ('_lL', '_lR', '_torso') if _part(a, s_) is not None)
                if t_ is not None]
        for o_, f0_, f1_, who_ in HELD:
            if who_ != a.name or not f0_ <= f < f1_ or not own_:
                continue
            for b_ in [o_] + list(o_.children_recursive):
                tb_ = _part_tree(b_)[0] if b_.type == 'MESH' else None
                if tb_ is not None and any(tb_.overlap(t_) for t_ in own_):
                    nx, ny, nz = now['R']
                    if nz < .3:
                        now['R'] = (nx, ny, nz + .015)
                        moved = True
                    break
        # a hand laid on the face rests on it, never in it: found inside the head, its hair or its glasses, that hand
        # goes further out, for as long as it is on that part of this face (puppet.on_face)
        for side in ('L', 'R'):
            fk_ = getattr(a.P, 'face_now', {}).get(side)
            if fk_ is None:
                continue
            d_ = a.P.hand_in_head(side)
            if d_ > 0 and a.P.face_more.get(fk_, 0.0) < .25:
                a.P.face_more[fk_] = a.P.face_more.get(fk_, 0.0) + d_ + .006
                moved = True
        # feet are pushed sideways out of whatever they stand in (a chair's base, a table's foot), remembered for the
        # spot the person stands or sits at, and never mid-stride
        if not a.walking(f) and not mid:
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
        if depth < 24:
            settle(f, depth + 1)     # measure again: one correction can need a few small steps (a shot's first drawing most)


def press_cushions(f):
    """A cushion gives under whoever sits on it: its top is pressed down to just under their body, and eases back
    around them, so a seated body rests in the cushion, never through it. The pressed shape is what is drawn and what
    the contact checks measure."""
    for sd in K.SEATS:
        if not sd['cushions']:
            continue
        on = [a for a in PERF.actors.values() if a.P.vis and not getattr(a, 'cull', False) and getattr(a, 'body', None)
              and a.seat_amt(f) > .01 and (a.seat_info(f) or {}).get('group') is sd['group']]
        for o in sd['cushions']:
            _press(o, on, sd['soft'])


def _press(o, sitters, soft):
    rest = _PRESS_REST.get(o.name)
    if rest is None:
        rest = _PRESS_REST[o.name] = _np.array(o['rest'], _np.float64).reshape(-1, 3)
    if not sitters:
        if o.get('pressed'):
            o.data.vertices.foreach_set('co', rest.astype(_np.float32).ravel())
            o.data.update()
            o['pressed'] = 0
        return
    hz = o['half'][2]
    M = _np.array(o.matrix_world)
    world = rest @ M[:3, :3].T + M[:3, 3]
    upper = _np.nonzero(rest[:, 2] > -hz * .3)[0]
    trees = []
    for a in sitters:
        for sfx in ('_torso', '_lL', '_lR'):
            t, co = _part_tree(_part(a, sfx))
            if t is not None:
                trees.append((t, co.min(axis=0), co.max(axis=0)))
    dent = _np.zeros(len(rest))
    for t, lo, hi in trees:
        under = upper[(world[upper, 0] >= lo[0] - .05) & (world[upper, 0] <= hi[0] + .05) & (world[upper, 1] >= lo[1] - .05)
                      & (world[upper, 1] <= hi[1] + .05) & (world[upper, 2] + .2 >= lo[2])]
        for i in under:
            x, y, z = world[i]
            h = t.ray_cast(V((x, y, z - .9)), V((0, 0, 1)), 1.4)
            if h[0] is not None and h[0].z < z + CLEAR + .006:
                dent[i] = max(dent[i], z + CLEAR + .006 - h[0].z)
    hit = _np.nonzero(dent > 0)[0]
    if len(hit):
        # between two vertices the body can dip lower than at either, and its sides curve down past its footprint:
        # every vertex takes the deepest press found within a diagonal of the vertex spacing, before easing back up
        near_ = ((world[upper, None, :2] - world[None, hit, :2]) ** 2).sum(-1) < .088 ** 2
        dent[upper] = _np.maximum(dent[upper], _np.where(near_, dent[hit][None, :], 0).max(1))
        hit = _np.nonzero(dent > 0)[0]
    if not len(hit):
        if o.get('pressed'):
            o.data.vertices.foreach_set('co', rest.astype(_np.float32).ravel())
            o.data.update()
            o['pressed'] = 0
        return
    # the cushion eases back up around the body (a soft falloff), never deeper than it can give
    d2 = ((world[upper, None, :2] - world[None, hit, :2]) ** 2).sum(-1)
    spread = (dent[hit][None, :] * _np.exp(-d2 / (.11 ** 2))).max(1)
    full = _np.zeros(len(rest))
    full[upper] = _np.maximum(spread, dent[upper])
    full = _np.minimum(full, soft * 2.2 + .02)
    w = _np.clip((rest[:, 2] + hz * .3) / (hz * 1.0), 0, 1)
    w = w * w * (3 - 2 * w)
    co = rest.copy()
    co[:, 2] -= full * w
    o.data.vertices.foreach_set('co', co.astype(_np.float32).ravel())
    o.data.update()
    o['pressed'] = f + 1


_PRESS_REST = {}


def settle_frame(f):
    # what is carried is put where it will be drawn first, so that settling sees it (a mug against a thigh lifts the
    # hand that holds it), and again after, where the hands ended up
    held_at(f)
    fit_grips(f)
    settle(f)
    press_cushions(f)
    held_at(f)
    fit_grips(f)


PERF.settle = settle_frame

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


# where everyone stands: clear of the furniture and of each other. A mark a little too close to a sofa's arm, or two
# people given the same spot, is moved the least distance that clears it, and the log says so.
for a in sorted(PERF.actors.values(), key=lambda a: 0 if a.init.get('seat') else 1):
    if a.init.get('seat'):
        continue
    spot = clear_spot(a, a.home, 0, 'their mark')
    if spot != tuple(a.home[:2]):
        if not getattr(a, 'entering', False):
            a.pos0 = (spot[0], spot[1]) + tuple(a.pos0[2:])
        a.home = spot


def stand_first(a, f):
    """Someone seated who is told to walk stands up first: -> the frame the walk can start."""
    a.finish()
    if a.state(f)[1][1].get('seat'):
        a.key(f, dict(seat=False))
        a.finish()
    for k_ in list(SEATED):
        if a in SEATED[k_]:
            SEATED[k_].remove(a)        # up: the seat is free for somebody else
    n = 0
    while a.seat_amt(f) > .02 and n < 400:
        f += 1
        n += 1
    return f


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
        sit = k.pop('sit', True)
        guest_ = getattr(a.P, 'guest', False)
        m = free_seat(a, f) if to == 'seat' else (MARKS.get(to) if isinstance(to, str) else None)
        if to == 'seat' and m is None:
            continue
        mname = next((n_ for n_, v_ in MARKS.items() if v_ is m), None)
        if to == 'home' and sit and getattr(a, 'entering', False) and a.mark is not None and a.mark.get('seat'):
            m = a.mark          # walking in to where they sit: they sit down when they get there
            mname = next((n_ for n_, v_ in MARKS.items() if v_ is m), None)
        a.entering = False
        if not guest_:
            f = stand_first(a, f)
        S = (seat_for(a, mname, m) if m and m.get('seat') and sit and not guest_ else m.get('seat_aff')) if m else None
        if not isinstance(S, dict):
            S = None
        if S is not None and getattr(a, 'body', None) is not None:
            dest = seat_ground(S, a.body, a)    # in front of the seat with room to turn, or where a chair was
        elif m:
            dest = clear_spot(a, m['pos'], f, to)
        elif to == 'home':
            dest = a.home
        else:
            dest = offscreen(a.home) if isinstance(to, str) else clear_spot(a, tuple(to), f, 'where they were sent')
        speed = k.pop('speed', None)
        if k.pop('enter', False):
            # f is when they should have arrived: leave early enough, and stay unseen until then. Somebody who comes
            # in is already walking: the feet start out pointing the way they go
            here = a.locate(f)[0]
            wp0 = route_to(a, f, dest, m)[0]
            if math.hypot(wp0[0] - here[0], wp0[1] - here[1]) > .05:
                a.psi0 = math.atan2(wp0[0] - here[0], -(wp0[1] - here[1]))
            f = f - int(route_length(a, f, dest, m) / (speed or a.st['speed'])) - 8
            a.key(-900, dict(on=False))
            a.key(f, dict(on=True))
            if 'door' in MARKS and math.hypot(here[0] - MARKS['door']['pos'][0], here[1] - MARKS['door']['pos'][1]) < .5:
                DOORS.append([f - 8, f + 46])
        end = walk_route(a, f, dest, speed=speed, m=m)
        if to == 'door':
            DOORS.append([end - 34, end + 12])
        to_mark = m if m else dict(pos=dest)
        if leave:
            a.key(end + 6, dict(on=False))
        if m and m.get('seat') and sit and not guest_:
            # turn round first, stepping, then sit: the hips go back and down over feet that are already in place
            yaw_s = S['yaw'] if S else (m.get('face') or 0.0)
            face_ = m.get('face', yaw_s)
            done = a.turn(end + 2, yaw_s)
            a.key(end - 10, dict(face=face_))
            # once the feet are still: after the turn, or after the closing step when there was nothing to turn
            a.key(max(end + 9, done), dict(seat=S or m['seat'], face=face_))
        elif m:
            fc_ = m.get('face')
            if not leave and not guest_:
                a.turn(end + 2, fc_ if isinstance(fc_, (int, float)) else 0.0)
            a.key(end - 10, dict(face=fc_))     # arrived on a standing mark: free to turn to whoever matters
        elif not leave and not guest_ and to == 'home':
            fc_ = (a.mark or {}).get('face')
            a.turn(end + 2, fc_ if isinstance(fc_, (int, float)) else 0.0)
    if to_mark is not None:
        a.mark = to_mark
    if k.get('g') in ('typing', 'desk'):
        h = desk_hands(a)
        if h:
            k.update(hL=h[0], hR=h[1])
            a.at_desk = True
    elif ('g' in k or k.get('seat') is False) and getattr(a, 'at_desk', False):
        # a new gesture, or getting up: the hands leave the keys (nobody types standing, bent over a desk)
        k.update(hL=None, hR=None)
        k.setdefault('g', 'rest')
        a.at_desk = False
    if isinstance(k.get('seat'), str):
        k['seat'] = (MARKS.get(k['seat']) or {}).get('seat') or A.SEAT_H
    if isinstance(k.get('look'), list):
        k['look'] = tuple(k['look'])
    a.key(f, k)
# a laptop that is closed, moved or taken away while somebody types on it: their hands come off it first, and go back
# to the keys once it is open again (direction.props); a lid never comes down through fingers
for name_, (o_, lid_, loc_, _r, _l, moves_) in TRACKS.items():
    if not name_.startswith('laptop'):
        continue
    w_ = o_.matrix_world.translation
    for mv in moves_:
        if mv['do'] not in ('close', 'slide', 'turn', 'hide'):
            continue
        for a in PERF.actors.values():
            a.finish()
            st_ = a.state(mv['frame'])[1][1]
            hs_ = [st_.get('hL'), st_.get('hR')]
            if st_.get('g') in ('typing', 'desk') and any(h is not None and math.hypot(h[0] - w_.x, h[1] - w_.y) < 1.0 for h in hs_):
                a.key(mv['frame'] - 12, dict(g='rest', hL=None, hR=None))
                print(f"FILM {a.name} takes the hands off the {name_} before it {mv['do']}s", flush=True)
                again_ = next((m for m in moves_ if m['do'] == 'open' and m['frame'] > mv['frame']), None)
                if again_ is not None and mv['do'] == 'close':
                    a.key(again_['frame'] + again_.get('frames', 14) + 4, {k: v for k, v in st_.items() if k in ('g', 'hL', 'hR')})
PERF.finish()

# whoever sits at some point uses the chair at that place: those chairs move with them, and are measured as they stand
for a in PERF.actors.values():
    if getattr(a.P, 'guest', False):
        continue
    for fk, st_k in a.keys:
        if st_k.get('seat'):
            ch = _chair_at(a.locate(fk + 9)[0])
            if ch is not None and a not in ch['users']:
                ch['users'].append(a)
for ch in ALL_CHAIRS:
    if ch['users']:
        room = _chair_room(ch)
        ch['pull'], ch['stand'] = min(ch['far'], room), max(0.0, min(STAND_BACK, room - ch['far']))
        if room < ch['far'] + STAND_BACK - 1e-3:
            print(f"FILM the chair at {tuple(round(v, 2) for v in ch['pos'])} can only be pushed back {room:.2f}", flush=True)
        for a in ch['users']:
            a.chairs = getattr(a, 'chairs', []) + [(ch['pos'], ch['back'], ch['stand'])]
        CHAIRS.append(ch)
if CHAIRS:
    _STATIC = None
    SOLID = _solid_tree()

# things carried in a hand: made once, shown while they are held
HELD = []
for c in JOB.get('carry') or []:
    a = PERF.actors.get(c.get('who'))
    if a is None or not hasattr(a.P, 'palm'):
        continue
    palm = a.P.palm['R']
    hs = a.P.m.get('hs', 1.0)
    if c.get('prop') == 'mug':
        # in the cupped hand (handrig 'cup'): its wall against the palm and inside the fingers, the rim above the
        # index finger, the handle turned away from the fingertips
        o = K.mug(.135 * hs, -.135 * hs, -.09 * hs, palm, hex_=c.get('color') or '#c1553f')
        o.rotation_euler = (0, 0, math.radians(-120))
        o.scale = (.78 * hs,) * 3
    elif c.get('prop') == 'phone':
        if c.get('use') == 'phone_to_ear':
            # across the cradling fingers (handrig 'cradle'), its long edge under the thumb, the screen to the ear
            o = K.phone(.089 * hs, -.042 * hs, -.1225 * hs, palm)
            o.rotation_euler = (math.pi / 2, 0, 0)
        else:
            # being read: its back on the palm and along the fingers (handrig 'tray'), the screen facing out of the palm
            o = K.phone(.2225 * hs, -.042 * hs, -.036 * hs, palm)
            o.rotation_euler = Matrix(((0, 1, 0), (0, 0, -1), (-1, 0, 0))).to_euler()
        o.scale = (1.15 * hs,) * 3
    else:
        continue
    HELD.append((o, int(c.get('start', -10 ** 6)), int(c.get('end', 10 ** 6)), a.name))


def show_tree(o, on):
    o.hide_render = o.hide_viewport = not on
    for ch in o.children:
        show_tree(ch, on)


def held_at(f):
    for o, f0, f1, _who in HELD:
        show_tree(o, f0 <= f < f1)
        if o.name in GRIP:
            o.location = GRIP[o.name][0] + GRIP[o.name][1]


GRIP = {}     # held thing -> (where it was put in the palm, how far it has been moved out of the fingers)


def fit_grips(f):
    """A thing carried in a hand sits against the fingers and the palm, never in them: where the hand is found inside it,
    it moves out of the hand a few millimetres at a time, and stays there for as long as it is held (every hand and
    every thing has its own size). -> True when something moved."""
    moved = False
    for o, f0, f1, who in HELD:
        if not f0 <= f < f1:
            continue
        a = PERF.actors.get(who)
        if a is None or not a.P.vis or getattr(a, 'cull', False):
            continue
        base, off = GRIP.setdefault(o.name, (o.location.copy(), V((0, 0, 0))))
        hand = _part(a, '_hR')
        if hand is None:
            continue
        th, hco = _part_tree(hand)
        bpy.context.view_layer.update()
        for _ in range(16):
            bits = [c for c in [o] + list(o.children_recursive) if c.type == 'MESH']
            inside = False
            for b in bits:
                tb, bco = _part_tree(b)
                if tb is not None and th is not None and th.overlap(tb):
                    inside = True
                    d = V(tuple(bco.mean(axis=0) - hco.mean(axis=0)))
                    break
            if not inside or off.length > .08:
                break
            loc = o.parent.matrix_world.inverted().to_3x3() @ d.normalized()
            off = off + loc * .004
            GRIP[o.name] = (base, off)
            o.location = base + off
            bpy.context.view_layer.update()
            moved = True
    return moved


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


if MODE in ('film', 'check') and CAM.get('shot') != 'opening' and CAM.get('move', 'static') in ('static', 'push_in'):
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
# ------------------------------------------------------------------ what makes a sound (sastudio.sound), for the scene
if MODE == 'events':
    import sounds as _SND
    for _e in _SND.scene_events(globals()):
        print('EVENT ' + json.dumps(_e), flush=True)
    print(f'EVENTS done {len(FRAMES)} frames', flush=True)
    sys.exit(0)

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

# ------------------------------------------------------------------ contact: measured before anything is drawn

_CAST = {o.name for a in PERF.actors.values() for o in getattr(a.P, 'parts', [])}


def offstage(a):
    """Waiting beyond the side walls to walk in, or gone out through them: where the set has no floor."""
    half = STG.get('half')
    return half is not None and abs(a.P.root.matrix_world.translation.x) > half


PROBE = CT.Probe(PERF, lambda: [o for o in bpy.data.objects if o.type == 'MESH' and o.name not in _CAST and o.visible_camera
                                and _in_room(o)], held=[(c, who) for o, _a, _b, who in HELD for c in [o] + list(o.children_recursive)],
                 offstage=offstage)
LEARNT = ('seat_lift', 'seat_rise', 'foot_push', 'foot_lift', 'hand_lift', 'hand_nudge', 'hand_now', 'walk_lift', 'last_head', 'last_yaw',
          'last_hand', 'lap_lift', 'sit_fwd')


def forget():
    """Drop everything settling has learnt, so a second pass over the same drawings poses them as the first one did."""
    for a in PERF.actors.values():
        for k in LEARNT:
            a.__dict__.pop(k, None)
        if hasattr(a.P, 'face_more'):
            a.P.face_more = {}
    # a carried thing goes back to where it was first put in the hand: the next pass fits it from there, as the first did
    for o, _f0, _f1, _who in HELD:
        if o.name in GRIP:
            o.location = GRIP[o.name][0]
    GRIP.clear()
    PERF._primed = False
    PROBE.reset()


def frame_at(f):
    """Everything in its place for scene frame f, in the order filming does it."""
    PERF.pose(f)
    door_at(f)
    held_at(f)
    dress_at(f)
    bpy.context.view_layer.update()
    camera_at(f)


def said(c):
    """One contact, in words (one unit of the set is 50 cm)."""
    cm = c['depth'] * 50
    if c['kind'] == 'float' and c['what'] == 'seat':
        return f"frame {c['frame']}: {c['actor']} sits {cm:.1f} cm above {c['other']}, held up by nothing (float)"
    if c['kind'] == 'float':
        return f"frame {c['frame']}: {c['actor']}'s feet are {cm:.1f} cm above {c['other']} and nothing else holds them up (float)"
    if c['kind'] == 'skate':
        return f"frame {c['frame']}: {c['actor']}'s {c['what']} slid {cm:.1f} cm on {c['other']} while standing on it (skate)"
    deep = f", {cm:.1f} cm deep" if c['depth'] else ''
    where = {'set': 'inside', 'cast': 'inside', 'self': 'inside', 'between': 'passed through', 'dressing': 'inside'}[c['kind']]
    return f"frame {c['frame']}: {c['actor']}'s {c['what']} {where} {c['other']} ({c['kind']}, {c['pairs']} crossing faces{deep})"


def dressing_contacts():
    """The set measured against itself: what the dressing could not place apart, and anything else that overlaps."""
    objs = [o for o in bpy.data.objects if o.type == 'MESH' and o.name not in _CAST and o.visible_camera and not o.hide_render
            and _in_room(o) and not o.name.startswith(CT.NOT_SOLID) and not any(o.name == c.name for c, _w in PROBE.held)]
    return CT.set_check(objs)


if MODE == 'check':
    # measure every drawing of the shot as filming would pose it, and draw nothing (tools/check_contacts.py)
    for c in dressing_contacts():
        print('CONTACT ' + json.dumps(c), flush=True)
    every = max(1, int(JOB.get('check_every', 1)))
    n = 0
    t0 = time.time()
    tp = tm = 0.0
    if os.environ.get('SASTUDIO_DEBUG_MEM'):
        import resource
        print('MEM setup', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024, 'MB', flush=True)
    for i, f in enumerate(FRAMES):
        t1 = time.time()
        frame_at(f)
        if os.environ.get('SASTUDIO_DEBUG_MEM') and i in (0, 1, 5, 15):
            print('MEM frame', i, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024, 'MB', flush=True)
        tp += time.time() - t1
        if JOB.get('trace_feet'):
            # (for the engine's own tests: where each shoe is, which way it points, how high its lowest point is)
            for a in PERF.actors.values():
                if getattr(a.P, 'guest', False) or not a.P.vis or getattr(a, 'cull', False) or not hasattr(a.P, 'shoeL'):
                    continue
                row = dict(f=f, who=a.name, seat=round(a.seat_amt(f), 4))
                for nm, o in (('L', a.P.shoeL), ('R', a.P.shoeR)):
                    M = o.matrix_world
                    co = _np.empty(len(o.data.vertices) * 3)
                    o.data.vertices.foreach_get('co', co)
                    low = float((co.reshape(-1, 3) @ _np.array(M)[:3, :3].T + _np.array(M)[:3, 3])[:, 2].min())
                    row[nm] = [round(M.translation.x, 5), round(M.translation.y, 5), round(low, 5), round(M.to_euler().z, 5)]
                print('FEET ' + json.dumps(row), flush=True)
        if i % every:
            continue
        n += 1
        t1 = time.time()
        for c in PROBE.measure(f):
            print('CONTACT ' + json.dumps(c), flush=True)
        tm += time.time() - t1
    print(f'CHECKED {n} {time.time() - t0:.1f}s (posing {tp:.1f}s, measuring {tm:.1f}s)', flush=True)
    sys.exit(0)

# ------------------------------------------------------------------ film it
out = JOB['out']
os.makedirs(out, exist_ok=True)
frames = [f for f in FRAMES if not os.path.exists(os.path.join(out, f'{f:06d}.png'))]
print(f'FILM frames {len(frames)} of {len(FRAMES)} to do', flush=True)
if frames:
    # Before anything is drawn: every drawing of the shot is posed as it will be filmed and measured. A shot that would
    # show a body inside something is not filmed; the log says who, which part, in what and when. Allowed by the film
    # command (--allow-intersections), it is filmed, and every contact is still measured and listed.
    tc = time.time()
    found = dressing_contacts()
    for f in FRAMES:
        frame_at(f)
        found += PROBE.measure(f)
    json.dump(found, open(os.path.join(out, 'contacts.json'), 'w'), indent=1)
    print(f'FILM contacts checked in {time.time() - tc:.1f}s: {len(found)}', flush=True)
    if found:
        for c in found[:30]:
            print('FILM contact ' + said(c), flush=True)
        where_ = os.path.join(out, 'contacts.json')
        if JOB.get('contacts', 'refuse') != 'allow':
            print(f'FILM refused: {len(found)} contact(s) in {len(FRAMES)} drawings; every one is in {where_}', flush=True)
            sys.exit(3)
        print(f'FILM filming anyway (--allow-intersections): {len(found)} contact(s) in {len(FRAMES)} drawings; every one is in {where_}',
              flush=True)
    forget()
t0 = time.time()
steps = sorted({f for a in PERF.actors.values() for f in a.steps()})
json.dump(dict(steps=steps), open(os.path.join(out, 'events.json'), 'w'))
t_pose = t_draw = 0.0
todo, n = set(frames), 0
for f in FRAMES:
    if f not in todo:
        # A drawing kept from an interrupted run is still posed: contact is learnt drawing by drawing (a table, a spot
        # remember how far a hand or a foot pushed clear), so a resumed shot draws what an uninterrupted one would.
        frame_at(f)
        continue
    t1 = time.time()
    frame_at(f)
    t2 = time.time()
    path = os.path.join(out, f'{f:06d}.png')
    s.render.filepath = path + '.part.png'
    bpy.ops.render.render(write_still=True)
    os.replace(path + '.part.png', path)
    t_pose += t2 - t1
    t_draw += time.time() - t2
    n += 1
    print(f'FILM frame {n}/{len(frames)} f{f} {time.time() - t0:.1f}s', flush=True)
print(f'FILM timing pose {t_pose:.1f}s draw {t_draw:.1f}s', flush=True)
print('FILM done', len(frames), 'frames', round(time.time() - t0, 1), 's', flush=True)
