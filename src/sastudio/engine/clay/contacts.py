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
  float    a body that nothing holds up: standing, no sole within 5 mm of what is under it; seated, the seat of the body
           (the backs of the thighs, the bottom of the torso) not on the seat; getting up or down, neither
  skate    a foot standing on something that slides along it: every point of the sole that stood on it at the last
           drawing and still does has moved more than 5 mm a frame

Touching is fine (a body rests a few millimetres above what holds it). Anything inside is reported with the frame,
the character, the part, what it is in, how many triangle pairs cross and how deep the deepest point is.

The ground measures follow the physical plausibility measures of motion research: penetrate, float and skate with a
5 mm tolerance (PhysDiff, arXiv:2212.02500), the 2.5 cm skid of a foot in contact (GMD, arXiv:2305.12577, here held
to 5 mm a frame), and contact of the body's seat and feet with the scene (PROX, arXiv:1908.06963). One unit of the
set is 50 cm.

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
# what holds a body up (in set units: one is 50 cm)
FOOT = .01       # a sole this close to what is under it stands on it (5 mm, as PhysDiff allows)
SEATED = .02     # the seat of a seated body this close to its seat sits on it (1 cm: the cushion is pressed to meet it)
SKATE = .01      # a standing foot that moves along what it stands on by more than this a frame (5 mm) slides on it
SOLE = .03       # the lowest 1.5 cm of a shoe is its sole
REACH = .6       # how far under a sole or a seat to look for what holds it


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

    def __init__(s, perf, set_objects, held=(), offstage=None):
        s.perf = perf
        s.set_objects = set_objects
        s.held = held           # props carried in a hand: [(object, actor name)]
        s.offstage = offstage   # callable(actor) -> True while they wait off the set (beyond its walls: no floor there)
        s.static = {}           # set objects that never move: built once
        s.last = {}             # actor -> {part: centre} at the last drawing measured, for paths between drawings
        s.soles = {}            # actor -> (frame, {shoe: {vertex: where it stood}}) at the last drawing measured

    def reset(s):
        """Forget the last drawing measured: the next one starts a new run of drawings."""
        s.last, s.soles = {}, {}

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
            if 'model' in parts or not hasattr(a.P, 'hipw'):
                continue        # an imported model is measured whole, against everything else: it has no parts of its own
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
        # what holds each body up: its feet or its seat; and a foot standing on something does not slide along it
        supports = [w for w in world if w.o.name not in held_names]
        for name, parts in cast.items():
            a = s.perf.actors[name]
            if 'model' not in parts and not (s.offstage is not None and s.offstage(a)):
                out += s._held_up(f, name, a, parts, supports)
        return out

    def hovering(s, f, name):
        """(how far the lowest point of a walking body's soles is above what is under it, that shoe) when measure()
        would find the body held up by nothing, measured the same way; else None. It changes nothing it measures with:
        filming lowers that foot onto what is under it (film.settle), so that drawing is never refused for it."""
        a = s.perf.actors[name]
        if (getattr(a, 'cull', False) or not a.P.vis or getattr(a.P, 'guest', False)
                or (s.offstage is not None and s.offstage(a)) or (hasattr(a, 'seat_amt') and a.seat_amt(f) > .01)):
            return None
        dg = bpy.context.evaluated_depsgraph_get()
        shoes = []
        for sfx in ('sL', 'sR'):
            o = next((o for o in a.P.parts if o.type == 'MESH' and not o.hide_render and _suffix(name, o.name) == sfx), None)
            m = Mesh(o, dg) if o is not None else None
            if m is not None and len(m.v):
                shoes.append((sfx, m))
        if not shoes:
            return None
        held_names = {o.name for o, _ in s.held}
        _soles, low = _soles_low(shoes, [w for w in s._set_meshes(dg) if w.o.name not in held_names])
        return (low[0], low[1]) if FOOT < low[0] < REACH else None

    def _held_up(s, f, name, a, parts, world):
        shoes = [(sfx, parts[sfx][0]) for sfx in ('sL', 'sR') if parts.get(sfx) and len(parts[sfx][0].v)]
        if not shoes:
            return []
        out = []
        seated = a.seat_amt(f) if hasattr(a, 'seat_amt') else 0.0
        soles, low = _soles_low(shoes, world)
        seat, seat_on = _seat_gap(a, parts, world) if seated > .01 else (np.inf, None)
        if seated >= .99 and seat > SEATED:
            # sitting: the seat of the body is on the seat, whatever the feet do (they may hang)
            out.append(dict(frame=f, actor=name, part='torso', what='seat', other=_thing(seat_on) if seat_on else 'nothing',
                            kind='float', pairs=0, depth=round(min(seat, REACH), 4)))
        elif low[0] > FOOT and seat > SEATED:
            # standing, or on the way up or down: something has to carry the weight
            out.append(dict(frame=f, actor=name, part=low[1], what='feet', other=_thing(low[2]) if low[2] else 'nothing',
                            kind='float', pairs=0, depth=round(min(low[0], REACH), 4)))
        # every point of a sole that stood on something at the last drawing measured and still stands on it stays where it
        # was: a foot rolling onto its toe or its heel lifts the rest of the sole off the floor (up, not along it), but a
        # foot that slides or turns on the floor moves the points it stands on, and the one that moved furthest counts
        prev = s.soles.get(name)
        now = {}
        for sfx, (m, idx, gaps, under) in soles.items():
            on = gaps <= FOOT
            now[sfx] = dict(zip(idx[on].tolist(), m.v[idx[on], :2]))
            before = prev[1].get(sfx) if prev is not None else None
            if not before or not now[sfx]:
                continue
            both = [i for i in now[sfx] if i in before]
            if not both:
                continue
            df = max(1, f - prev[0])
            moved = max(float(np.hypot(*(now[sfx][i] - before[i]))) for i in both)
            if moved > SKATE * df:
                k = int(np.argmin(gaps))
                out.append(dict(frame=f, actor=name, part=sfx, what=PARTS[sfx], other=_thing(under[k]) if under[k] else 'nothing',
                                kind='skate', pairs=len(both), depth=round(moved, 4)))
        s.soles[name] = (f, now)
        return out


def _limb(a, sfx):
    """(segments around, rings in the upper part, rings in all) of a sleeve or a trouser leg (puppet.Limb), or None."""
    L = {'aL': 'armLt', 'aR': 'armRt', 'lL': 'legLt', 'lR': 'legRt'}.get(sfx)
    lb = getattr(a.P, L, None) if L else None
    return (lb.seg, lb.n1, lb.n1 + lb.n2 + lb.n3) if lb is not None else None


def limb_ring(p, seg, rings):
    """Which ring of a limb (puppet.Limb) face p belongs to, 0 at the root. The side is (rings - 1) * seg quads, ring by
    ring; then the two end caps, one triangle of each in turn: the even ones close the root (ring 0, the shoulder or the
    hip, inside the body by design) and the odd ones the far end (the last ring, at the wrist or the ankle)."""
    side = (rings - 1) * seg
    if p < side:
        return p // seg
    return 0 if (p - side) % 2 == 0 else rings - 1


def _past_join(pairs, seg, n1, count=None):
    """The crossings of a sleeve or a trouser leg with its own torso that are not where it is joined to it. A limb starts
    inside the torso (a sleeve on a shoulder, a trouser leg under a jacket's hem) and comes out of it once, near its
    root: that first way out is the join. Anything after it, with clear limb in between, is the limb going back in.
    (The cap that closes the root belongs to the root: it is inside the body by design.)"""
    ring = (lambda p: p // seg) if count is None else (lambda p: limb_ring(p, seg, count))
    rings = sorted({ring(p) for p, _q in pairs})
    if not rings or rings[0] > .55 * n1:
        return pairs                          # it never came out near the root: all of it is inside the body
    end = rings[0]
    for r in rings[1:]:
        if r - end > 2:
            break
        end = r
    return [pq for pq in pairs if ring(pq[0]) > end]


def _soles_low(shoes, world):
    """Each shoe's sole (its points within SOLE of its lowest), how high each point is above what is under it, and the
    lowest of them all: ({shoe: (mesh, points, gaps, under)}, (gap, shoe, what is under it))."""
    soles, low = {}, (np.inf, 'sL', None)
    for sfx, m in shoes:
        idx = np.nonzero(m.v[:, 2] <= m.lo[2] + SOLE)[0]
        gaps, under = _below(world, m.v[idx])
        soles[sfx] = (m, idx, gaps, under)
        k = int(np.argmin(gaps))
        if gaps[k] < low[0]:
            low = (float(gaps[k]), sfx, under[k])
    return soles, low


def _below(world, pts):
    """How high each point is above the first solid surface under it (below zero: inside it), and which object that is.
    Looked for from 2.5 cm above the point, so a point a little inside a surface is measured as inside it.
    pts: (n, 3) -> (gaps (n,), names); a point with nothing under it within REACH is inf above nothing."""
    gaps = np.full(len(pts), np.inf)
    under = [None] * len(pts)
    if not len(pts):
        return gaps, under
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    down = V((0, 0, -1))
    for w in world:
        if (w.lo[0] > hi[0] or w.hi[0] < lo[0] or w.lo[1] > hi[1] or w.hi[1] < lo[1] or w.lo[2] > hi[2] + .05
                or w.hi[2] < lo[2] - REACH):
            continue
        t = w.tree()
        if t is None:
            continue
        inside = np.nonzero((pts[:, 0] >= w.lo[0]) & (pts[:, 0] <= w.hi[0]) & (pts[:, 1] >= w.lo[1]) & (pts[:, 1] <= w.hi[1]))[0]
        for i in inside:
            p = pts[i]
            loc = t.ray_cast(V((p[0], p[1], p[2] + .05)), down, REACH + .05)[0]
            if loc is not None and p[2] - loc.z < gaps[i]:
                gaps[i], under[i] = p[2] - loc.z, w.o.name
    return gaps, under


def _seat_gap(a, parts, world):
    """How far the seat of a body is above what is under it: the bottom of the torso and the backs of the thighs, the
    places a seated body rests on (PROX's contact regions). -> (gap, the object under it)"""
    pts = []
    for m in parts.get('torso', ())[:1]:
        pts.append(m.v[m.v[:, 2] <= m.lo[2] + SOLE])
    for sfx in ('lL', 'lR'):
        lb = _limb(a, sfx)
        for m in parts.get(sfx, ())[:1]:
            thigh = m.v[: lb[0] * lb[1]] if lb else m.v
            if len(thigh):
                pts.append(thigh[thigh[:, 2] <= thigh[:, 2].min() + SOLE])
    if not pts:
        return np.inf, None
    gaps, under = _below(world, np.concatenate(pts))
    k = int(np.argmin(gaps))
    return float(gaps[k]), under[k]


REST = .012     # how deep a thing may settle into what holds it (a table's foot into the lumps of a clay floor)
# The parts of a set that are built into each other on purpose, by the name its builder gives them (setkit): walls,
# their windows, doors and skirting are one construction; floors are laid edge to edge; posts, trees and buildings
# stand in the ground. Joins inside each of these are not contacts. Everything else is measured.
BUILT = ('back', 'side', 'skirt', 'ceiling', 'window', 'door', 'winband', 'winbar', 'wainL', 'wainR', 'brandpanel', 'slat',
         'feature', 'menu', 'menut', 'sign', 'label', 'bname')
GROUND = ('plank', 'tile', 'carpet', 'floor', 'road', 'kerb', 'lane', 'plaza', 'lawn', 'pit', 'rugb', 'rug', 'runner')
PLANTED = ('streetlamp', 'busstop', 'tree', 'building', 'skyline', 'cloud')


def _cls(name):
    n = re.sub(r'[\d.]+$', '', name.split('.')[0])
    return 'built' if n in BUILT else 'ground' if n in GROUND else 'planted' if n in PLANTED else 'thing'


def _top(o):
    """The thing an object belongs to: its outermost parent (a laptop's keys belong to the laptop)."""
    while o.parent is not None:
        o = o.parent
    return o


def set_check(objects, dg=None, moving=()):
    """Every pair of separate things of the set measured against each other, exactly: a mug inside a laptop, a chair in
    a table, a plant in a bookcase. A thing resting on another (its lowest part in the top of what holds it) or hung
    flat on a wall may settle into it by REST at most, as clay does under weight; anything else is reported.
    moving: names of things that move (a chair being pulled out, a door, a prop on a track): only their pairs are
    measured when given, for the drawings after the first. -> [dict(frame, actor='set', part, what, other, kind, pairs,
    depth)]."""
    dg = dg or bpy.context.evaluated_depsgraph_get()
    ms = [Mesh(o, dg) for o in objects]
    ms = [m for m in ms if len(m.v)]
    tops = [_top(m.o).name for m in ms]
    cls = [_cls(t) for t in tops]
    out = []
    lo = np.array([m.lo for m in ms])
    hi = np.array([m.hi for m in ms])
    for i, a in enumerate(ms):
        cand = np.nonzero((lo[i + 1:] <= hi[i]).all(1) & (lo[i] <= hi[i + 1:]).all(1))[0] + i + 1
        for j in cand:
            b = ms[j]
            if tops[i] == tops[j]:
                continue
            pair = {cls[i], cls[j]}
            if pair <= {'built', 'ground'} or pair == {'planted', 'ground'} or pair == {'planted'}:
                continue        # one construction, or something that stands in the ground
            if moving and a.o.name not in moving and b.o.name not in moving:
                continue
            ta, tb = a.tree(), b.tree()
            if ta is None or tb is None:
                continue
            pairs = ta.overlap(tb)
            if not pairs:
                continue
            da, db = _depth(a, b), _depth(b, a)
            deep = max(da, db)
            # resting: the crossing is at the bottom of one of them, in the top of the other, and shallow. Where a face
            # crosses is its lowest corner at most: a long face down a chair's leg still crosses only at its foot
            za = np.array([a.v[a.p[p], 2].min() for p, _q in pairs[:200]])
            zb = np.array([b.v[b.p[q], 2].min() for _p, q in pairs[:200]])
            resting = deep <= REST and ((za <= a.lo[2] + .03).all() or (zb <= b.lo[2] + .03).all())
            # hung on a wall: shallow, and one of them is a wall
            walled = deep <= REST and any(_thing(n).split('.')[0] in ('back', 'side', 'skirt', 'wall') for n in (a.o.name, b.o.name))
            if resting or walled:
                continue
            out.append(dict(frame=0, actor='set', part=_thing(a.o.name), what=_thing(tops[i]), other=_thing(tops[j]) + ' ' + _thing(b.o.name),
                            kind='dressing', pairs=len(pairs), depth=round(deep, 4),
                            at=[round(float(x), 3) for x in np.mean([a.centre(p) for p, _q in pairs[:50]], axis=0)]))
    return out


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
