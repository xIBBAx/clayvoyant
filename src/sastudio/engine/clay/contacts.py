"""What passes through what in a posed drawing. Runs inside Blender, next to film.py.

Measured on the meshes exactly as they are drawn (every modifier applied: bevels, lumps, a cushion pressed in), in
world space, triangle against triangle:

  set      every visible character against every solid thing of the set, the props in hands and the furniture
  cast     every character against every other
  self     each character against their own body: hands, arms and legs against the torso, the head and each other.
           Where two parts are joined by design (a sleeve into its shoulder, a thigh into its hip, a hand into its
           cuff, a shoe over its ankle) the join is not a contact; everything away from the join is.
  between  a hand or a foot whose path from the last drawing to this one runs through something solid, even though it
           is clear in both drawings

Touching is fine (a body rests a few millimetres above what holds it). Anything inside is reported with the frame,
the character, the part, what it is in, how many triangle pairs cross and how deep the deepest point is.

The probe never changes the scene. film.py uses it to refuse to draw a shot that would show a body inside
something (and to say exactly where), and tools/check_contacts.py uses it to check a filmed project.
"""
import math
import re

import bpy
import numpy as np
from mathutils import Vector as V
from mathutils.bvhtree import BVHTree

# what each part of a puppet is, in words (the suffix after the character's id in the object's name)
PARTS = {'torso': 'body', 'h': 'head', 'hair': 'hair', 'acc': 'glasses or earrings', 'aL': 'left arm', 'aR': 'right arm',
         'hL': 'left hand', 'hR': 'right hand', 'lL': 'left leg', 'lR': 'right leg', 'sL': 'left shoe', 'sR': 'right shoe',
         'eye': 'eye', 'lu': 'eyelid', 'll': 'eyelid', 'bL': 'brow', 'bR': 'brow', 'tU': 'teeth', 'tL': 'teeth', 'tg': 'tongue',
         'cape': 'cape', 'model': 'body'}
# parts that live inside or on another part of the same body by design, and are never measured against it
INSIDE = {'eye', 'lu', 'll', 'bL', 'bR', 'tU', 'tL', 'tg', 'acc', 'cape'}
# parts inside the head (eyes, lids, brows, teeth, tongue): nothing reaches them without going through the head first
WITHIN = {'eye', 'lu', 'll', 'bL', 'bR', 'tU', 'tL', 'tg'}
# pairs of one body's parts that are measured, and how near to the join between them a crossing is still the join
SELF = [('hL', 'torso'), ('hR', 'torso'), ('hL', 'h'), ('hR', 'h'), ('hL', 'hR'), ('hL', 'aR'), ('hR', 'aL'),
        ('hL', 'lL'), ('hL', 'lR'), ('hR', 'lL'), ('hR', 'lR'), ('aL', 'aR'), ('aL', 'torso'), ('aR', 'torso'),
        ('aL', 'lL'), ('aL', 'lR'), ('aR', 'lL'), ('aR', 'lR'), ('lL', 'lR'), ('lL', 'torso'), ('lR', 'torso'),
        ('sL', 'sR'), ('sL', 'lR'), ('sR', 'lL'), ('hL', 'hair'), ('hR', 'hair'), ('hL', 'sL'), ('hL', 'sR'),
        ('hR', 'sL'), ('hR', 'sR')]
# names of set objects that are not solid: vapour, birds in the sky, the cards that shape window light
NOT_SOLID = ('steam', 'wing', 'gob', 'vap')


def _suffix(actor, name):
    return re.sub(r'\.\d+$', '', name[len(actor) + 1:]) if name.startswith(actor + '_') else None


def _thing(name):
    """An object of the set, in words: its builder's name without Blender's numbering."""
    return re.sub(r'\.\d+$', '', name)


def _mesh_of(o, dg):
    """The mesh an object is drawn with: its own data when nothing modifies it (the puppet's parts, posed by moving
    their vertices), the evaluated copy otherwise. -> (mesh, release)"""
    if not o.modifiers and o.type == 'MESH':
        return o.data, None
    ev = o.evaluated_get(dg)
    return ev.to_mesh(), ev


_TOPO = {}     # object name -> (vertex count, faces as lists): a part's faces never change, only where its vertices are


def faces_of(me, key):
    """The faces of a mesh as lists of vertex indices, read once per object."""
    got = _TOPO.get(key)
    if got is not None and got[0] == len(me.vertices) and got[2] == len(me.polygons):
        return got[1]
    lv = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get('vertex_index', lv)
    lt = np.empty(len(me.polygons), np.int64)
    me.polygons.foreach_get('loop_total', lt)
    if len(lt) and (lt == lt[0]).all():
        polys = lv.reshape(-1, int(lt[0])).tolist()
    else:
        ls = np.empty(len(me.polygons), np.int64)
        me.polygons.foreach_get('loop_start', ls)
        polys = [lv[a:a + b].tolist() for a, b in zip(ls, lt)]
    _TOPO[key] = (len(me.vertices), polys, len(me.polygons))
    return polys


class Mesh:
    """One object as drawn this drawing: its vertices in the world and a box at once; its faces and a tree only when
    something near it needs them."""
    __slots__ = ('o', 'v', 'lo', 'hi', '_p', '_t', 'dg')

    def __init__(s, o, dg):
        s.o, s.dg, s._p, s._t = o, dg, None, None
        me, ev = _mesh_of(o, dg)
        try:
            n = len(me.vertices)
            co = np.empty(n * 3, np.float64)
            me.vertices.foreach_get('co', co)
            if n and len(me.polygons):
                s._p = faces_of(me, o.name)
        finally:
            if ev is not None:
                ev.to_mesh_clear()
        M = np.array(o.matrix_world, np.float64)
        s.v = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3] if n else np.zeros((0, 3))
        s.lo = s.v.min(axis=0) if len(s.v) else np.full(3, 1e9)
        s.hi = s.v.max(axis=0) if len(s.v) else np.full(3, -1e9)

    @property
    def p(s):
        return s._p or []

    def tree(s):
        if s._t is None and s._p:
            s._t = BVHTree.FromPolygons(s.v.tolist(), s.p)
        return s._t

    def centre(s, i):
        """The middle of polygon i."""
        return s.v[s.p[i]].mean(axis=0)

    def near(s, other, pad=0.0):
        return bool((s.lo - pad <= other.hi).all() and (other.lo - pad <= s.hi).all())


def _depth(a, b, at=None, reach=.18):
    """How far the deepest point of mesh a is inside mesh b (0 when only edges cross): a's vertices inside b's box (and
    near the crossing, when `at` is given), tested against b's tree; a vertex is inside when the nearest surface of b
    faces away from it."""
    t = b.tree()
    if t is None:
        return 0.0
    m = ((a.v >= b.lo) & (a.v <= b.hi)).all(axis=1)
    if at is not None:
        m &= ((a.v - np.asarray(at)) ** 2).sum(1) < reach * reach
    deep = 0.0
    for p in a.v[m][:: max(1, int(m.sum()) // 600)]:
        loc, nrm, _i, d = t.find_nearest(V(p))
        if loc is not None and (V(p) - loc).dot(nrm) < 0:
            deep = max(deep, d)
    return deep


class Probe:
    """Measures one drawing at a time. perf: the Performance; set_objects: callable -> the set's solid objects now."""

    def __init__(s, perf, set_objects, held=()):
        s.perf = perf
        s.set_objects = set_objects
        s.held = held           # props carried in a hand: [(object, actor name)]
        s.static = {}           # set objects that never move: built once
        s.last = {}             # actor -> {part: centre} at the last drawing measured, for paths between drawings

    def _set_meshes(s, dg):
        out = []
        for o in s.set_objects():
            if o.type != 'MESH' or o.hide_render or not o.visible_get() or o.name.startswith(NOT_SOLID):
                continue
            key = (o.name, tuple(round(x, 5) for r in o.matrix_world for x in r), o.get('pressed', 0))
            m = s.static.get(o.name)
            if m is None or m[0] != key:
                m = (key, Mesh(o, dg))
                s.static[o.name] = m
            out.append(m[1])
        return out

    def measure(s, f):
        """-> [dict(frame, actor, part, what, other, kind, pairs, depth)] for drawing f, as it is posed now."""
        dg = bpy.context.evaluated_depsgraph_get()
        out = []
        cast = {}
        for name, a in s.perf.actors.items():
            if getattr(a, 'cull', False) or not a.P.vis:
                continue
            parts = {}
            if getattr(a.P, 'guest', False):
                # a model somebody brought: measured whole against the set and the others (its own parts are its own)
                cast[name] = {'model': [Mesh(o, dg) for o in a.P.parts if o.type == 'MESH' and not o.hide_render]}
                continue
            for o in a.P.parts:
                if o.type != 'MESH' or o.hide_render:
                    continue
                sfx = _suffix(name, o.name)
                if sfx is None or sfx in WITHIN:
                    continue
                parts.setdefault(sfx, []).append(Mesh(o, dg))
            cast[name] = parts
        world = s._set_meshes(dg)
        held_names = {o.name for o, _ in s.held}

        def hit(a, b):
            ta, tb = a.tree(), b.tree()
            if ta is None or tb is None:
                return []
            return ta.overlap(tb)

        def report(actor, part, other, kind, pairs, a, b):
            at = np.mean([a.centre(i) for i, _j in pairs[:200]], axis=0)
            out.append(dict(frame=f, actor=actor, part=part, what=PARTS.get(part, part), other=other, kind=kind,
                            pairs=len(pairs), depth=round(_depth(a, b, at if kind == 'self' else None), 4),
                            at=[round(float(x), 3) for x in at]))

        # each character against the set and the props
        for name, parts in cast.items():
            for sfx, meshes in parts.items():
                if sfx in INSIDE:
                    continue
                for m in meshes:
                    for w in world:
                        if not m.near(w):
                            continue
                        pairs = hit(m, w)
                        if pairs:
                            held_by = next((who for o, who in s.held if o.name == w.o.name), None) if w.o.name in held_names else None
                            report(name, sfx, _thing(w.o.name) + (' (held)' if held_by else ''), 'set', pairs, m, w)
        # characters against each other
        names = sorted(cast)
        for i, n1 in enumerate(names):
            for n2 in names[i + 1:]:
                for s1, ms1 in cast[n1].items():
                    for s2, ms2 in cast[n2].items():
                        for m1 in ms1:
                            for m2 in ms2:
                                if m1.near(m2):
                                    pairs = hit(m1, m2)
                                    if pairs:
                                        report(n1, s1, f'{n2} {PARTS.get(s2, s2)}', 'cast', pairs, m1, m2)
        # each body against itself, away from its joins
        for name, parts in cast.items():
            a = s.perf.actors[name]
            joins = _joins(a)
            for p1, p2 in SELF:
                for m1 in parts.get(p1, ()):
                    for m2 in parts.get(p2, ()):
                        if not m1.near(m2):
                            continue
                        pairs = hit(m1, m2)
                        if not pairs:
                            continue
                        limb = _limb(a, p1) if p2 == 'torso' else None
                        if limb is not None:
                            real = _past_join(pairs, *limb)
                        else:
                            real = [pq for pq in pairs if not _at_join(p1, p2, m1.centre(pq[0]), m2.centre(pq[1]), joins)]
                        if real:
                            report(name, p1, f'own {PARTS.get(p2, p2)}', 'self', real, m1, m2)
        # paths between drawings: a hand or a foot that went through something since the last drawing measured
        for name, parts in cast.items():
            now = {sfx: parts[sfx][0].v.mean(axis=0) for sfx in ('hL', 'hR', 'sL', 'sR') if sfx in parts and len(parts[sfx][0].v)}
            before = s.last.get(name)
            if before is not None:
                for sfx, p1 in now.items():
                    p0 = before.get(sfx)
                    if p0 is None:
                        continue
                    d = V(p1) - V(p0)
                    if d.length < .02:
                        continue
                    for w in world:
                        if any(o.name == w.o.name and who == name for o, who in s.held):
                            continue        # what this hand carries goes where the hand goes
                        lo, hi = np.minimum(p0, p1) - .05, np.maximum(p0, p1) + .05
                        if not ((lo <= w.hi).all() and (w.lo <= hi).all()):
                            continue
                        t = w.tree()
                        h1 = t.ray_cast(V(p0), d.normalized(), d.length) if t else (None,)
                        h2 = t.ray_cast(V(p1), -d.normalized(), d.length) if t else (None,)
                        if h1[0] is not None and h2[0] is not None and (h1[0] - h2[0]).length > .03:
                            # entered and left a solid between the two drawings
                            out.append(dict(frame=f, actor=name, part=sfx, what=PARTS.get(sfx, sfx), other=_thing(w.o.name),
                                            kind='between', pairs=0, depth=round((h1[0] - h2[0]).length, 4)))
            s.last[name] = now
        return out


def _limb(a, sfx):
    """(rings around, rings in the upper part) of a sleeve or a trouser leg (puppet.Limb), or None."""
    L = {'aL': 'armLt', 'aR': 'armRt', 'lL': 'legLt', 'lR': 'legRt'}.get(sfx)
    lb = getattr(a.P, L, None) if L else None
    return (lb.seg, lb.n1) if lb is not None else None


def _past_join(pairs, seg, n1):
    """The crossings of a sleeve or a trouser leg with its own torso that are not where it is joined to it. A limb starts
    inside the torso (a sleeve on a shoulder, a trouser leg under a jacket's hem) and comes out of it once, near its
    root: that first way out is the join. Anything after it, with clear limb in between, is the limb going back in."""
    ring = lambda p: p // seg
    rings = sorted({ring(p) for p, _q in pairs})
    if not rings or rings[0] > .55 * n1:
        return pairs                          # it never came out near the root: all of it is inside the body
    end = rings[0]
    for r in rings[1:]:
        if r - end > 2:
            break
        end = r
    return [pq for pq in pairs if ring(pq[0]) > end]


def _joins(a):
    """Where this body's parts are joined, this drawing: shoulders, hip joints, wrists, ankles (world)."""
    P = a.P
    j = {}
    for side in 'LR':
        sh = getattr(P, 'shw', {}).get(side)
        if sh is not None:
            j['sh' + side] = np.array(sh)
    M = P.root.matrix_world
    for sg, side in ((-1, 'L'), (1, 'R')):
        j['hip' + side] = np.array(M @ V((sg * P.hipw, 0, P.hip + .09)))
    j['pelvis'] = np.array(M @ V((0, 0, P.hip)))
    return j


def _at_join(p1, p2, c1, c2, j):
    """True when a crossing between two of one body's parts is where they are joined by design."""
    pair = {p1, p2}
    if 'torso' in pair and (p1[0] == 'a' or p2[0] == 'a'):
        side = (p1 if p1[0] == 'a' else p2)[1]
        sh = j.get('sh' + side)
        return sh is not None and np.linalg.norm(c1 - sh) < .3 and np.linalg.norm(c2 - sh) < .34
    if 'torso' in pair and (p1[0] == 'l' or p2[0] == 'l'):
        side = (p1 if p1[0] == 'l' else p2)[1]
        hp = j.get('hip' + side)
        return hp is not None and np.linalg.norm(c1 - hp) < .36 and np.linalg.norm(c2 - hp) < .4
    if pair == {'lL', 'lR'}:
        pv = j.get('pelvis')
        return pv is not None and np.linalg.norm(c1 - pv) < .42 and np.linalg.norm(c2 - pv) < .42
    return False


def summary(found):
    """Counts by what was inside what, for a log."""
    by = {}
    for c in found:
        k = (c['kind'], c['actor'], c['what'], c['other'])
        by[k] = by.get(k, 0) + 1
    return sorted(by.items(), key=lambda kv: -kv[1])
