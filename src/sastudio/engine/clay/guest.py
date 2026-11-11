"""Guests: characters brought in as 3D models (glTF, GLB, FBX, OBJ) instead of sculpted here. Runs inside Blender.

A guest stands on its mark at the height of the rest of the cast, walks to where it is sent, turns to whoever
matters, looks with its head, talks with its mouth and blinks, and moves its arms through a small set of gestures:
as much as its rig and its shape keys allow, found by name (see sastudio.models for the names it knows). A model
with no rig still stands, moves and turns. Sculpted characters do far more (hands, faces, sitting, walking with
planted feet); a guest is for the character somebody already has.

Two things are done to every model on the way in: any animation stored in the file is removed, because it would
fight the acting, and the model is measured as it really stands (skinned, posed at rest) so its feet are on the floor.
"""
import math
import os
import re

import bpy
from mathutils import Euler
from mathutils import Vector as V

import acting as A

HEIGHT = 3.45           # a guest is fitted to the cast: this tall in set units
REST = {'left': {'shoulder': (0.0, 0.10, 0.0), 'elbow': (-0.12, 0.0, 0.0)}, 'right': {'shoulder': (0.0, -0.10, 0.0), 'elbow': (-0.12, 0.0, 0.0)}}
# arm poses for the engine's gestures (shoulder and elbow as Euler angles in the character's own space)
POSES = {
    'point': {'right': {'shoulder': (-1.25, -0.10, 0.0), 'elbow': (-0.15, 0.0, 0.0)}},
    'wave': {'right': {'shoulder': (-0.20, -2.30, 0.0), 'elbow': (0.0, -0.35, 0.0)}},
    'present': {'left': {'shoulder': (-0.25, 0.30, 0.0), 'elbow': (-1.35, 0.0, 0.0)}, 'right': {'shoulder': (-0.25, -0.30, 0.0), 'elbow': (-1.35, 0.0, 0.0)}},
    'shrug': {'left': {'shoulder': (-0.15, 0.55, 0.0), 'elbow': (-1.20, 0.0, 0.0)}, 'right': {'shoulder': (-0.15, -0.55, 0.0), 'elbow': (-1.20, 0.0, 0.0)}},
    'thumb': {'right': {'shoulder': (-0.55, -0.15, 0.0), 'elbow': (-1.45, 0.0, 0.0)}},
    'chin': {'right': {'shoulder': (-0.55, 0.25, 0.0), 'elbow': (-2.35, 0.0, 0.0)}},
    'cross': {'left': {'shoulder': (-0.35, -0.15, 0.0), 'elbow': (-1.85, 0.0, 0.0)}, 'right': {'shoulder': (-0.35, 0.15, 0.0), 'elbow': (-1.85, 0.0, 0.0)}},
    'phone': {'right': {'shoulder': (-0.45, -0.45, 0.0), 'elbow': (-2.45, 0.0, 0.0)}},
    'typing': {'left': {'shoulder': (-0.60, 0.05, 0.0), 'elbow': (-0.95, 0.0, 0.0)}, 'right': {'shoulder': (-0.60, -0.05, 0.0), 'elbow': (-0.95, 0.0, 0.0)}},
    'talk': {'left': {'shoulder': (-0.22, 0.16, 0.0), 'elbow': (-0.95, 0.0, 0.0)}, 'right': {'shoulder': (-0.22, -0.16, 0.0), 'elbow': (-1.05, 0.0, 0.0)}},
    'read': {'right': {'shoulder': (-0.40, -0.05, 0.0), 'elbow': (-1.70, 0.0, 0.0)}},
    'carry': {'right': {'shoulder': (-0.20, -0.05, 0.0), 'elbow': (-1.45, 0.0, 0.0)}},
}
for _a, _b in (('talkR', 'talk'), ('talkL', 'talk'), ('talkWide', 'present'), ('weigh', 'present'), ('palmsDown', 'talk'), ('presentR', 'present'),
               ('chest', 'talk'), ('index', 'point'), ('offer', 'present'), ('up', 'wave'), ('sip', 'chin'), ('hold', 'carry')):
    POSES[_a] = POSES[_b]


def _norm(name):
    return re.sub(r'[^a-z0-9]', '', re.split(r'[:|]', name)[-1].lower())


def _match(names, table):
    by = {}
    for n in names:
        by.setdefault(_norm(n), n)
    return {part: next((by[a] for a in aliases if a in by), None) for part, aliases in table.items()}


def _import(path):
    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.glb', '.gltf'):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == '.fbx':
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == '.obj':
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise SystemExit(f'FILM cannot import {ext}')
    return [o for o in bpy.data.objects if o not in before]


def _bounds(objs):
    """The model as it really stands: every vertex after skinning and modifiers, in world space."""
    dg = bpy.context.evaluated_depsgraph_get()
    lo, hi = V((1e9, 1e9, 1e9)), V((-1e9, -1e9, -1e9))
    for o in objs:
        if o.type != 'MESH':
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = ev.matrix_world
        for v in me.vertices:
            w = mw @ v.co
            lo, hi = V(map(min, lo, w)), V(map(max, hi, w))
        ev.to_mesh_clear()
    return lo, hi


class Guest:
    guest = True

    def __init__(s, name, path, aliases, yaw_deg=0.0):
        s.name = name
        new = _import(path)
        # importers add helper objects (the shapes bones are drawn with): they are not part of the character
        helpers = {pb.custom_shape for o in new if o.type == 'ARMATURE' for pb in o.pose.bones if pb.custom_shape}
        new = [o for o in new if o not in helpers]
        for o in list(helpers):
            bpy.data.objects.remove(o, do_unlink=True)
        for o in new:
            o.animation_data_clear()                 # whatever the file was doing, it is not this film
            if o.type == 'MESH' and o.data.shape_keys:
                o.data.shape_keys.animation_data_clear()
                for kb in o.data.shape_keys.key_blocks:
                    kb.value = 0.0
            if o.type == 'ARMATURE':
                for pb in o.pose.bones:
                    pb.location, pb.rotation_quaternion, pb.rotation_euler, pb.scale = (0, 0, 0), (1, 0, 0, 0), (0, 0, 0), (1, 1, 1)
        s.root = bpy.data.objects.new(name, None)
        bpy.context.scene.collection.objects.link(s.root)
        turn = bpy.data.objects.new(name + '_turn', None)
        bpy.context.scene.collection.objects.link(turn)
        turn.parent = s.root
        turn.rotation_euler[2] = math.radians(yaw_deg) + math.pi      # models face +y or -y by their own convention; ours face -y
        fit = bpy.data.objects.new(name + '_fit', None)
        bpy.context.scene.collection.objects.link(fit)
        for o in new:
            if o.parent not in new:
                o.parent = fit
        bpy.context.view_layer.update()
        lo, hi = _bounds(new)
        height = max(1e-6, hi.z - lo.z)
        sc = HEIGHT / height
        fit.scale = (sc, sc, sc)
        fit.location = (-(lo.x + hi.x) / 2 * sc, -(lo.y + hi.y) / 2 * sc, -lo.z * sc)
        fit.parent = turn
        bpy.context.view_layer.update()
        lo2, _ = _bounds(new)                      # measured again where it now stands: the feet go exactly on the floor
        fit.location.z -= lo2.z
        s.parts = new + [s.root, turn, fit]
        s.arm = next((o for o in new if o.type == 'ARMATURE'), None)
        s.rig = {k: v for k, v in (_match([b.name for b in s.arm.data.bones], aliases.get('bones', {})) if s.arm else {}).items() if v}
        s.keys = {}
        for o in new:
            if o.type == 'MESH' and o.data.shape_keys:
                for part, kname in _match([k.name for k in o.data.shape_keys.key_blocks], aliases.get('shapes', {})).items():
                    if kname:
                        s.keys.setdefault(part, []).append(o.data.shape_keys.key_blocks[kname])
        s.vis = True
        s.head_world = V((0, 0, HEIGHT * .9))
        s.es = .17
        if s.arm:
            for n in s.rig.values():
                s.arm.pose.bones[n].rotation_mode = 'QUATERNION'
        print('FILM guest', name, 'height', round(height, 3), 'rig', sorted(s.rig), 'face', sorted(s.keys), flush=True)

    def show(s, on):
        if s.vis == on:
            return
        s.vis = on
        for o in s.parts:
            o.hide_render = o.hide_viewport = not on


def pose(S_, a, f):
    """Put a guest where frame f has it."""
    G = a.P
    prev, cur = a.state(f)
    on = cur[1].get('on', True) and not getattr(a, 'cull', False)
    G.show(bool(on))
    if not on:
        return
    pos, feet, _yaw_w, walk_amt = a.locate(f)
    look = cur[1].get('look')
    face = cur[1].get('face')
    tp = S_.target_pos(look, a) if look else None
    if face is None:
        face = A.clamp(math.atan2(tp.x - pos[0], -(tp.y - pos[1])) * .62, -.68, .68) if tp is not None and look in S_.actors else 0
    elif isinstance(face, str):
        t2 = S_.actors[face].head_pos() if face in S_.actors else None
        face = A.clamp(math.atan2(t2.x - pos[0], -(t2.y - pos[1])) * .62, -.68, .68) if t2 is not None else 0
    k = A.sm(A.clamp((f - cur[0]) / 13))
    face = A.lerp(getattr(a, '_face0', face) if k < 1 else face, face, k)
    if k >= 1:
        a._face0 = face
    yaw = a.heading(f, face)
    bob = .05 * abs(math.sin(math.pi * feet[4])) * walk_amt if feet else 0
    seed = a.seed
    G.root.location = (pos[0], pos[1], pos[2] + S_.floor + bob + .012 * math.sin(f / 18 + seed))
    G.root.rotation_euler = (0, 0, yaw)
    G.head_world = V(G.root.location) + V((0, 0, HEIGHT * .9))
    a.last_head, a.last_yaw = G.head_world.copy(), yaw
    # the face: jaw from the words, blinks
    S = S_.speaking(a.name, f)
    sp = S_.face_speech(a.name, f)
    jaw = float(sp[A.FI['jaw']]) / .95 if sp is not None else 0.0
    bl = A.blink_at(f, seed)
    for part, blocks in G.keys.items():
        v = A.clamp(jaw * 1.1) if part == 'mouth_open' else bl
        for kb in blocks:
            kb.value = v
    if not G.arm:
        return
    Aw = (G.root.matrix_world.inverted() @ G.arm.matrix_world).to_3x3().normalized()
    Ai = Aw.inverted()
    rest = {part: G.arm.data.bones[n].matrix_local.to_3x3() for part, n in G.rig.items()}
    rot = lambda e: Euler(e, 'XYZ').to_matrix()   # noqa: E731
    # the head: toward what they look at, with the small life a head always has
    hy = hp = 0.0
    if tp is not None:
        v = tp - G.head_world
        hy = A.clamp(((math.atan2(v.x, -v.y) - yaw + math.pi) % (2 * math.pi) - math.pi) * .55, -.5, .5)
        hp = A.clamp(math.atan2(-v.z, math.hypot(v.x, v.y)) * .5, -.3, .3)
    pitch = hp + .05 * S * A.noise(f / 9, seed) + cur[1].get('nod', 0) * k
    roll = .03 * math.sin(f / 31 + seed) + cur[1].get('tilt', 0) * k
    yawh = hy + cur[1].get('turn', 0) * k
    for part in ('head', 'neck'):
        if part in G.rig:
            share = 1.0 if part == 'head' and 'neck' not in G.rig else .6 if part == 'head' else .4
            R = Ai @ rot((pitch * share, roll * share, yawh * share)) @ Aw
            G.arm.pose.bones[G.rig[part]].rotation_quaternion = (rest[part].inverted() @ R @ rest[part]).to_quaternion()
    # the arms: from wherever the last gesture left them to this one; arms modelled in a T-pose come down first
    def arms(g):
        out = {s_: dict(REST[s_]) for s_ in REST}
        for s_, p in POSES.get(g, {}).items():
            out[s_] = p
        return out
    a0, a1 = arms(prev[1]['g']), arms(cur[1]['g'])
    e = A.anticipate(A.clamp((f - cur[0]) / 14))
    swing = .5 * math.sin(2 * math.pi * feet[4]) * walk_amt if feet else 0
    # the character's own left is screen right: gestures written for "the right hand" use the model's right arm
    for side, upper, fore, sg in (('right', 'right_upper_arm', 'right_forearm', -1), ('left', 'left_upper_arm', 'left_forearm', 1)):
        if upper not in G.rig:
            continue
        sh = [A.lerp(p, q, e) for p, q in zip(a0[side]['shoulder'], a1[side]['shoulder'])]
        el = [A.lerp(p, q, e) for p, q in zip(a0[side]['elbow'], a1[side]['elbow'])]
        sh[0] += sg * swing * (1 if side == 'left' else -1) * .6 + .04 * S * A.noise(f / 13, seed + sg)
        b = G.arm.data.bones[G.rig[upper]]
        d = (b.tail_local - b.head_local).normalized()
        want = (Ai @ V(((1.0 if (Aw @ d).x >= 0 else -1.0) * .18, 0.0, -.98))).normalized()
        down_u = d.rotation_difference(want).to_matrix()
        Rs, Re = Ai @ rot(sh) @ Aw, Ai @ rot(el) @ Aw
        want_u = Rs @ down_u @ rest[upper]
        G.arm.pose.bones[G.rig[upper]].rotation_quaternion = (rest[upper].inverted() @ want_u).to_quaternion()
        if fore in G.rig:
            bf = G.arm.data.bones[G.rig[fore]]
            df = (bf.tail_local - bf.head_local).normalized()
            down_f = df.rotation_difference((Ai @ V(((1.0 if (Aw @ df).x >= 0 else -1.0) * .18, 0.0, -.98))).normalized()).to_matrix()
            want_f = Rs @ Re @ down_f @ rest[fore]
            rel_rest = rest[upper].inverted() @ rest[fore]
            G.arm.pose.bones[G.rig[fore]].rotation_quaternion = (rel_rest.inverted() @ want_u.inverted() @ want_f).to_quaternion()

