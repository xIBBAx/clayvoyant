"""The clay puppet. All solving is done with explicit matrices (no depsgraph updates), so it is fast and pure."""
import json, math, os
import bpy, numpy as np
from mathutils import Vector as V, Matrix, Euler
from claymat import *
import faceops
import handrig

RIG = os.path.join(os.environ.get('SASTUDIO_RIG', ''), '')  # folder with meta.json and one sub-folder per character
META = None
# the back of the neck twists with the head instead of swinging out of the collar: see Puppet._tuck_nape and set_face
NECKFIX = os.environ.get('SASTUDIO_NECKFIX', '1') == '1'

def nape_weights(co, z0=.30, z1=.04):
    """How much of each head-space vertex belongs to the neck rather than the skull: 0 from the skull down to z0, 1 below z1 at the
    back, and everything below the pivot. The throat side (y < 0) above the pivot stays with the jaw."""
    sm_ = lambda x: (lambda c: c * c * (3 - 2 * c))(np.clip(x, 0, 1))
    wz = sm_((z0 - co[:, 2]) / (z0 - z1))
    wy = sm_((co[:, 1] + .06) / .12)
    below = sm_((.04 - co[:, 2]) / .08)
    return np.maximum(wz * wy, below).astype(np.float32)

def twist(co, w, axis, ang):
    """Rotate each point about one axis by its own share of an angle (Rodrigues, vectorised)."""
    ph = (-w * ang)[:, None]
    c, s_ = np.cos(ph), np.sin(ph)
    a = np.asarray(axis, np.float32)
    return co * c + np.cross(a, co) * s_ + a * (co @ a)[:, None] * (1 - c)
MOUTHS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'warm', 'smile', 'grin', 'flat', 'frown', 'smirk', 'gasp', 'worry']
HANDS = ['relax', 'open', 'point', 'fist', 'grip', 'thumb']

def ik(a, c, l1, l2, pole):
    d = c - a
    L = max(.02, min(d.length, l1 + l2 - .002))
    u = d.normalized()
    x = (l1 * l1 - l2 * l2 + L * L) / (2 * L)
    y = math.sqrt(max(0, l1 * l1 - x * x))
    p = pole - u * pole.dot(u)
    p = p.normalized() if p.length > 1e-4 else V((0, 0, -1))
    return a + u * x + p * y, a + u * L

_rng = np.random.default_rng(7)
class Limb:
    """One continuous sleeve or trouser leg, swept along the bone every frame: no separate parts, and no elbow gap.
    The cloth bunches where it bends, and it never slides, because its weave is pinned to its own surface."""
    def __init__(s, name, mat, prof, n1=13, n2=9, n3=13, seg=18, over=0.0):
        s.n1, s.n2, s.n3, s.seg = n1, n2, n3, seg
        rings = n1 + n2 + n3
        s.rings = rings
        s.over = over
        s.prof = np.array([np.interp(i / (rings - 1), [q[0] for q in prof], [q[1] for q in prof]) for i in range(rings)], np.float32)
        s.th = np.linspace(0, 2 * np.pi, seg, endpoint=False)
        s.ct, s.st = np.cos(s.th), np.sin(s.th)
        s.lump = 1 + .014 * _rng.normal(size=(rings, seg))
        s.lump = (s.lump + np.roll(s.lump, 1, 0) + np.roll(s.lump, 1, 1)) / 3
        vs = np.zeros((rings * seg + 2, 3))
        fs = []
        for i in range(rings - 1):
            for j in range(seg):
                a, b = i * seg + j, i * seg + (j + 1) % seg
                c, d = (i + 1) * seg + (j + 1) % seg, (i + 1) * seg + j
                fs.append((a, b, c, d))
        c0, c1 = rings * seg, rings * seg + 1
        for j in range(seg):
            fs.append((c0, (j + 1) % seg, j))
            fs.append((c1, (rings - 1) * seg + j, (rings - 1) * seg + (j + 1) % seg))
        me = bpy.data.meshes.new(name)
        me.from_pydata(vs.tolist(), [], fs)
        me.update()
        me.shade_smooth()
        uv = me.uv_layers.new(name='UVMap')
        cir = 2 * np.pi * float(s.prof.mean())
        ln = 1.05
        L = []
        for p_ in me.polygons:
            for li in p_.loop_indices:
                vi = me.loops[li].vertex_index
                if vi >= rings * seg:
                    L += [0, 0]
                else:
                    i, j = vi // seg, vi % seg
                    L += [j / seg * cir, i / (rings - 1) * ln]
        uv.data.foreach_set('uv', np.array(L, np.float32))
        me.materials.append(mat)
        s.me = me
        s.o = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(s.o)

    def set(s, A, E, C, pole):
        A, E, C = np.array(A, float), np.array(E, float), np.array(C, float)
        la, lb = np.linalg.norm(E - A) + 1e-6, np.linalg.norm(C - E) + 1e-6
        ua, ub = (E - A) / la, (C - E) / lb
        r = min(.17, .4 * min(la, lb))
        P1, P2 = E - ua * r, E + ub * r
        t1 = np.linspace(0, 1, s.n1, endpoint=False)[:, None]
        t2 = np.linspace(0, 1, s.n2, endpoint=False)[:, None]
        t3 = np.linspace(0, 1, s.n3)[:, None]
        pts = np.r_[A + (P1 - A) * t1, (1 - t2) ** 2 * P1 + 2 * t2 * (1 - t2) * E + t2 ** 2 * P2, P2 + (C + ub * s.over - P2) * t3]
        tan = np.gradient(pts, axis=0)
        tan /= np.linalg.norm(tan, axis=1, keepdims=True) + 1e-9
        n = np.array(pole, float)
        n = n - tan[0] * n.dot(tan[0])
        n /= np.linalg.norm(n) + 1e-9
        N = np.zeros_like(pts)
        for i in range(len(pts)):
            n = n - tan[i] * n.dot(tan[i])
            n /= np.linalg.norm(n) + 1e-9
            N[i] = n
        B = np.cross(tan, N)
        # bunching: cloth only folds where it bends, and only as much as it bends
        bendv = float(np.clip((1 - ua.dot(ub)) * .9, 0, 1))
        cen = (s.n1 + s.n2 * .5)
        I = np.arange(s.rings)[:, None]
        fold = 1 + bendv * .085 * np.exp(-((I - cen) / 5.0) ** 2) * np.sin(I * 1.55 + 2 * s.th[None, :] + 1.1 * np.sin(s.th[None, :]))
        R = s.prof[:, None] * s.lump * fold
        v = pts[:, None, :] + R[:, :, None] * (s.ct[None, :, None] * N[:, None, :] + s.st[None, :, None] * B[:, None, :])
        allv = np.r_[v.reshape(-1, 3), pts[0][None], pts[-1][None]]
        s.me.vertices.foreach_set('co', allv.astype(np.float32).ravel())
        s.me.update()

class Hand:
    """One hand: a single sculpted skin, posed every frame through the bones in handrig.py."""
    skip = False   # audits that only need the skeleton leave the skin alone
    def __init__(s, path, mat, size, side):
        d = np.load(path)
        s.v0 = d['v'].astype(np.float64)
        s.bi = d['bi'].astype(np.intp)
        s.bw = d['bw'].astype(np.float64)
        q = np.clip((s.v0[:, 0] + .05 * size) / (.085 * size), 0, 1)
        s.wz = q * q * (3 - 2 * q)
        s.bones = handrig.Bones(size, side)
        s.me = load(path, mat).copy()
        s.last = None

    def set(s, shape, sw):
        key = (np.round(shape, 4).tobytes(), np.round(sw, 4).tobytes())
        if key == s.last or s.skip:
            return
        s.last = key
        R, T = s.bones.pose(shape)
        v = handrig.deform(s.v0, s.bi, s.bw, R, T, s.wz, sw)
        s.me.vertices.foreach_set('co', v.astype(np.float32).ravel())
        s.me.update()

class Puppet:
    def __init__(s, name):
        global META
        if META is None:
            META = json.load(open(RIG + 'meta.json'))
        s.name = name
        m = s.m = META[name]
        D = RIG + name + '/'
        s.parts = []
        def add(o):
            s.parts.append(o)
            return o
        s.root = add(bpy.data.objects.new(name, None))
        bpy.context.scene.collection.objects.link(s.root)
        s.hip = m['hip']
        s.L = m['L']
        s.zT = s.L + .10
        s.z0 = .03
        # the torso mesh deforms: a real spine, not a rigid can
        s.torso_mesh = load(D + 'torso.npz', clayv('cloth_' + name, .7, .02, .35, 0, m.get('fabric')))
        s.torso = add(obj(name + '_torso', s.torso_mesh, s.root, (0, 0, s.hip)))
        s.base = np.zeros(len(s.torso_mesh.vertices) * 3, np.float32)
        s.torso_mesh.vertices.foreach_get('co', s.base)
        s.base = s.base.reshape(-1, 3)
        s.chest = add(bpy.data.objects.new(name + '_chest', None))
        bpy.context.scene.collection.objects.link(s.chest)
        s.chest.parent = s.torso
        s.head = add(bpy.data.objects.new(name + '_head', None))
        bpy.context.scene.collection.objects.link(s.head)
        s.head.parent = s.chest
        s.head.location = (0, .0, (s.L + .065) - s.zT)
        hsc = m.get('hscale', 1.0)
        s.head.scale = (hsc, hsc, hsc)
        F = s.F = m['face']
        skin = clayv('skin', .55, .4, .35, .02, cgrain=.02)
        s.head_mesh = load(D + 'head.npz', skin)
        add(obj(name + '_h', s.head_mesh, s.head))
        s.head0 = np.zeros(len(s.head_mesh.vertices) * 3, np.float32)
        s.head_mesh.vertices.foreach_get('co', s.head0)
        s.head0 = s.head0.reshape(-1, 3)
        if NECKFIX:
            s._tuck_nape(hsc)
        s.fields = faceops.fields(s.head0, F)
        s.last_fc = None
        hmat = clayv('hair_' + name, .62, 0, .25, 0, cgrain=.02)
        if m.get('headwear'):   # a turban or a headscarf is matte woven cloth, not glossy hair
            hmat = clayv('hw_' + name, .86, .02, .35, 0, m.get('hwfabric', 'jersey'))
        s.hair = add(obj(name + '_hair', load(D + 'hair.npz', hmat), s.head))
        s._hrot = (0.0, 0.0, 0.0)
        if NECKFIX:
            # The head mesh runs on down inside the collar to an open ring cut flat at z=-.14 (the sculpt grid's floor). It was rigid with the
            # skull, so every turn or nod swung that flat-cut tube out of the collar behind the neck. A real neck twists: its foot stays with
            # the chest and its top goes with the skull. The same share of the turn is taken off the lowest hair, which lies on the nape.
            w_ = nape_weights(s.head0)
            s.nape_i = np.nonzero(w_ > 1e-4)[0]
            s.nape_w = w_[s.nape_i]
            s.hair0 = np.zeros(len(s.hair.data.vertices) * 3, np.float32)
            s.hair.data.vertices.foreach_get('co', s.hair0)
            s.hair0 = s.hair0.reshape(-1, 3)
            wh_ = nape_weights(s.hair0)
            s.hnape_i = np.nonzero(wh_ > 1e-4)[0]
            s.hnape_w = wh_[s.hnape_i]
            s.last_hr = None
        if os.path.exists(D + 'acc.npz'):
            add(obj(name + '_acc', load(D + 'acc.npz', clayv('hard', .3, 0, .15, .3)), s.head))
        # teeth and tongue live inside the mouth; the lower set rides the jaw hinge
        mouthm = clayv('teeth', .3, 0, 0, .3, cgrain=0)
        tm = clayv('tongue', .42, .3, 0, .2, cgrain=0)
        add(obj(name + '_tU', load(D + 'teethU.npz', mouthm), s.head))
        s.jawp = add(bpy.data.objects.new(name + '_jaw', None))
        bpy.context.scene.collection.objects.link(s.jawp)
        s.jawp.parent = s.head
        s.jawp.location = faceops.HINGE
        inv = (-faceops.HINGE[0], -faceops.HINGE[1], -faceops.HINGE[2])
        add(obj(name + '_tL', load(D + 'teethL.npz', mouthm), s.jawp, inv))
        s.tongue = add(obj(name + '_tg', load(D + 'tongue.npz', tm), s.jawp, inv))
        s.tinv = inv
        s.es = F['es']
        s.ez = F['ez']
        s.eyes = []
        emat = gloss_eye()
        for sg in (-1, 1):
            e = bpy.data.objects.new(name + '_es', None)
            bpy.context.scene.collection.objects.link(e)
            add(e)
            e.parent = s.head
            e.location = (sg * s.es, F['eyey'], s.ez)
            # on a round head the sockets look a little outward: eyes set dead parallel read as crossed
            e.rotation_euler = (0, 0, sg * F.get('toe', 0))
            ball = add(obj(name + '_eye', load(D + 'eye.npz', emat), e))
            lidm = clayv('lid', .55, 0, .1, .02, cgrain=.008)
            lu = add(obj(name + '_lu', load(D + 'lidu.npz', lidm), e))
            ll = add(obj(name + '_ll', load(D + 'lidl.npz', lidm), e))
            s.eyes.append((ball, lu, ll))
        bmat = clayv('brow_' + name, .7, 0, .1, 0, cgrain=.02)
        s.browL = add(obj(name + '_bL', load(D + 'browL.npz', bmat), s.head))
        s.browR = add(obj(name + '_bR', load(D + 'browR.npz', bmat), s.head))
        s.browz = F['browz']
        s.browy = F['browy']
        s.sl = m['sleeve']
        hs = {}
        hm_ = clayv('hand', .55, .3, .35, .02, cgrain=.02)
        s.rig = os.path.exists(D + 'hand_R.npz')
        if s.rig:
            s.hand = {k: Hand(D + f'hand_{k}.npz', hm_, m.get('hs', 1.0), 1 if k == 'R' else -1) for k in 'LR'}
            s.handL = add(obj(name + '_hL', s.hand['L'].me, None))
            s.handR = add(obj(name + '_hR', s.hand['R'].me, None))
            # what a held prop sits in: the palm, wherever the wrist has put it
            s.palm = {}
            s.armlog = {}
            for k in 'LR':
                s.palm[k] = add(bpy.data.objects.new(name + '_palm' + k, None))
                bpy.context.scene.collection.objects.link(s.palm[k])
            s._j = {}
        else:
            for side in 'LR':
                hs[side] = {k: load(D + f'h_{k}_{side}.npz', hm_) for k in HANDS}
            s.hmesh = hs
            s.handL = add(obj(name + '_hL', hs['L']['relax'], None))
            s.handR = add(obj(name + '_hR', hs['R']['relax'], None))
        s.armLen = m.get('armL', .5)
        s.sx = m['sw'] - .07
        wr = (m['sw'] / .47) ** .75
        lr = (m['hw'] / .35) ** .8
        fab = m.get('fabric')
        pfab = m.get('pfabric')
        sleevem = clay_rgb(s.sl, .7, .02, 0, fab, 'UV')
        pantm = clay_rgb(m['pant'], .72, .02, 0, pfab, 'UV')
        aprof = [(0, .085 * wr), (.04, .118 * wr), (.25, .112 * wr), (.48, .098 * wr), (.7, .092 * wr), (.92, .082 * wr), (1, .08 * wr)]
        lprof = [(0, .13 * lr), (.05, .178 * lr), (.25, .155 * lr), (.5, .124 * lr), (.72, .118 * lr), (.92, .116 * lr), (1, .118 * lr)]
        s.armLt = Limb(name + '_aL', sleevem, aprof)
        s.armRt = Limb(name + '_aR', sleevem, aprof)
        s.legLt = Limb(name + '_lL', pantm, lprof, over=.075)
        s.legRt = Limb(name + '_lR', pantm, lprof, over=.075)
        for l_ in (s.armLt, s.armRt, s.legLt, s.legRt):
            add(l_.o)
        shoem = clayv('shoe_' + name, .45, 0, .3, .12, cgrain=.02)
        s.shoeL = add(obj(name + '_sL', load(D + 'shoe.npz', shoem), None))
        s.shoeR = add(obj(name + '_sR', load(D + 'shoe.npz', shoem), None))
        s.hipw = .178 if m['hw'] > .34 else .16
        s.legl = (s.hip - .13) / 2 * 1.015
        s.cape = None
        if os.path.exists(D + 'cape.npz'):
            s.cape = add(obj(name + '_cape', load(D + 'cape.npz', clayv('cape', .75, .02, .2, 0, 'velvet')), s.chest, (0, .02, (s.L - .06) - s.zT)))
        s.vis = True
        s._mesh_dirty = True
        s.last_bend = None

    def show(s, on):
        if s.vis == on:
            return
        s.vis = on
        for o in s.parts:
            o.hide_render = not on
            o.hide_viewport = not on

    def _deform(s, af, as_, tw, q):
        k = (round(af, 3), round(as_, 3), round(tw, 3), round(q, 3))
        if k == s.last_bend:
            return
        s.last_bend = k
        b = s.base
        z0, zT = s.z0, s.zT
        Lb = zT - z0
        t = np.clip((b[:, 2] - z0) / Lb, 0, 1)
        x, y, z = b[:, 0].copy(), b[:, 1].copy(), b[:, 2].copy()
        if tw:
            ca, sa = np.cos(tw * t), np.sin(tw * t)
            x, y = x * ca - y * sa, x * sa + y * ca
        wob = 1 + q * .55 * np.sin(np.pi * t)
        x, y = x * wob, y * wob
        z = z0 + (z - z0) * (1 - q)
        as_t, af_t = as_ * t, af * t
        nx = x * np.cos(as_t) + Lb * as_ * t * t / 2
        ny = y * np.cos(af_t) - Lb * af * t * t / 2
        nz = z - x * np.sin(as_t) + y * np.sin(af_t) - Lb * (as_ * as_ + af * af) * t ** 3 / 6
        out = np.c_[nx, ny, nz].astype(np.float32).ravel()
        s.torso_mesh.vertices.foreach_set('co', out)
        s.torso_mesh.update()

    def pose(s, loc=(0, 0, 0), yaw=0, bend=(0, 0), twist=0, squash=0, head=(0, 0, 0), look=(0, 0), upper=-30, lower=50,
             blink=0, browL=0, browR=0, tiltL=0, tiltR=0, fc=None, handL=None, handR=None, poseL='relax', poseR='relax',
             backL=None, backR=None, footL=None, footR=None, roll=(0, 0), lift=(0, 0), capeSway=0, hairJ=(0, 0), dirL=None, dirR=None,
             jL=None, jR=None, shapeL=None, shapeR=None, faceL=None, faceR=None, elL=None, elR=None):
        """handX/footX are world positions. Feet stay planted because the pelvis moves, not the feet."""
        loc = V(loc)
        Ry = Matrix.Rotation(yaw, 4, 'Z')
        Mroot = Matrix.Translation(loc) @ Ry
        s.root.location = loc
        s.root.rotation_euler = (0, 0, yaw)
        af, as_ = bend
        s._deform(af, as_, twist, squash)
        Lb = s.zT - s.z0
        q = (1 - squash)
        cp = V((Lb * as_ / 2, -Lb * af / 2, s.z0 + Lb * q - Lb * (af * af + as_ * as_) / 6))
        s.chest.location = cp
        R = Euler((af, as_, twist)).to_matrix().to_4x4()
        s.chest.rotation_euler = (af, as_, twist)
        Mtorso = Mroot @ Matrix.Translation((0, 0, s.hip))
        Mc = Mtorso @ Matrix.Translation(cp) @ R
        if s.cape:
            s.cape.rotation_euler = (capeSway - af * .6, 0, 0)
        # head
        s.head.rotation_euler = (head[0], head[1], head[2])
        # where the face really is, leaning and all: the camera and everyone's eyes need this
        s.head_world = Mc @ V((0, -.06, (s.L + .065) - s.zT + .54 * s.m.get('hscale', 1.0)))
        lx, ly = look
        b = max(0, min(1, blink))
        # rig-level lid rest; expressions stay relative to it
        ang_u = lerp_(upper + s.F.get('lidU', 0), 28, b)
        ang_l = lerp_(lower + s.F.get('lidL', 0), 28, b)
        for sg_, (ball, lu, ll) in zip((-1, 1), s.eyes):
            # the socket and lids toe out with the curve of the head, but the ball looks where the person looks: left to inherit the toe, the two eyes split by 20 degrees and read wall-eyed.
            # A little divergence stays on purpose (dead parallel reads as crossed on a round head).
            # and the two eyes meet on what they look at: the nearer the thing, the more they turn in (vergence), a few degrees at most
            ball.rotation_euler = (ly * .42, 0, lx * .55 - sg_ * (s.F.get('toe', 0) * .88 + getattr(s, 'verg', 0.0)))
            # the lid rides a little with the eye, which is why eyes feel alive
            lu.rotation_euler = (math.radians(ang_u + ly * 10), 0, lx * .1)
            ll.rotation_euler = (math.radians(ang_l + ly * 5), 0, lx * .08)
        # a raised brow slides up AND back with the forehead (face bslope = dy/dz behind the brow);
        # it used to rise straight up and float 1.5-3.4 cm off the skin at full raise. braise caps the travel (for low fringes).
        # The face rig already lifts the forehead skin .032 and brings it .005 forward at full raise (faceops 'brow' field), so the
        # brow slides back only for the part of its rise above the skin's own (a full-slope slide sinks the brows).
        rz_, sl_ = s.F.get('braise', .072), s.F.get('bslope', 0.0)
        cl_ = max(0.0, rz_ - .032)
        s.browL.location = (-s.es, s.browy - .005 * browL + sl_ * browL * cl_, s.browz + browL * rz_)
        s.browR.location = (s.es, s.browy - .005 * browR + sl_ * browR * cl_, s.browz + browR * rz_)
        s.browL.rotation_euler = (0, tiltL * .62, 0)
        s.browR.rotation_euler = (0, -tiltR * .62, 0)
        s._hrot = (float(head[0]), float(head[1]), float(head[2]))
        s.set_face(fc)
        # hair has weight: it settles after the head has moved
        if not s.m.get('rigidhair'):   # a wrapped turban is firm: it never lags like hair
            s.hair.rotation_euler = (hairJ[0], 0, hairJ[1])
        # arms
        for side, ob, hnd, tgt, ps, back, sg in (('L', s.armLt, s.handL, handL, poseL, backL, -1), ('R', s.armRt, s.handR, handR, poseR, backR, 1)):
            A = Mc @ V((sg * (s.sx - .045), .012, (s.L - .10) - s.zT))
            T = V(tgt) if tgt is not None else Mroot @ V((sg * (s.sx + .13), -.03, s.hip + .02))
            # the shoulder goes with the arm: reaching up lifts it, reaching out draws it forward
            A = A + V((0, 0, .055 * max(0, min(1, (T.z - A.z + .45) / .8))))
            s.shw = getattr(s, 'shw', {}); s.shw[side] = A.copy()     # where each shoulder is this frame (POSDBG, contact staging)
            if s.rig:
                # a hand on the face is placed in the head's own space: it meets this character's face, and stays there when the head moves
                fp = faceL if side == 'L' else faceR
                if fp is not None:
                    hsc = s.m.get('hscale', 1.0)
                    Mh = Mc @ Matrix.Translation(s.head.location) @ Euler(head).to_matrix().to_4x4() @ Matrix.Diagonal((hsc, hsc, hsc, 1))
                    T = T.lerp(Mh @ V(fp[0]), fp[1])
                Mi = Mroot.inverted()
                Tl = handrig.round_shoulder(sg, np.array(Mi @ A), np.array(Mi @ T))
                T = Mroot @ V(Tl.tolist())
                pole = Mroot.to_3x3() @ V(handrig.pole_for(sg, np.array(Mi @ A), Tl, elL if side == 'L' else elR).tolist())
            else:
                pole = (Mroot.to_3x3() @ V((sg * .55, .35, -1)))
            E, Cc = ik(A, T, s.armLen - .005, s.armLen - .005, pole)
            ob.set(A, E, Cc, pole)
            if s.rig:
                j = (jL if side == 'L' else jR) or handrig.REST
                d_, t0 = handrig.neutral(np.array(A), np.array(E), np.array(Cc), np.array(pole), sg, np.array(Mroot.to_3x3()))
                F = handrig.forearm(d_, t0, sg, j[0])
                sw = handrig.swing_vec(sg, j[1], j[2])
                hnd.matrix_world = Matrix.Translation(Cc) @ Matrix(F.tolist()).to_4x4()
                sh = shapeL if side == 'L' else shapeR
                s.hand[side].set(handrig.fvec(ps) if sh is None else sh, sw)
                s.palm[side].matrix_world = Matrix.Translation(Cc) @ Matrix((F @ handrig.rotvec(sw)).tolist()).to_4x4()
                s.armlog[side] = (E, j, (T - A).length / (2 * (s.armLen - .005)))
                continue
            d = (Cc - E).normalized()
            # a wrist: a hand at the face or pressed to the other hand does not simply continue the forearm
            hd = dirL if side == 'L' else dirR
            if hd is not None:
                d = d.lerp(V(hd[0]), hd[1]).normalized()
            bk = V(back) if back is not None else (Mroot.to_3x3() @ V((sg, 0, 0)))
            Yv = bk - d * bk.dot(d)
            Yv = Yv.normalized() if Yv.length > 1e-3 else V((0, 0, 1))
            Zv = d.cross(Yv)
            hnd.matrix_world = Matrix.Translation(Cc) @ Matrix((d, Yv, Zv)).transposed().to_4x4()
            hnd.data = s.hmesh[side].get(ps, s.hmesh[side]['relax'])
        # legs: IK down to the ankle above a planted shoe
        for side, ob, sh, ft, sg, rl, lf in (('L', s.legLt, s.shoeL, footL, -1, roll[0], lift[0]), ('R', s.legRt, s.shoeR, footR, 1, roll[1], lift[1])):
            F = V(ft) if ft is not None else Mroot @ V((sg * .22, 0, 0))
            sh.location = F + V((0, 0, lf))
            sh.rotation_euler = (rl, 0, yaw)
            A = Mtorso @ V((sg * s.hipw, 0, .09))
            Ank = F + V((0, 0, .27 + lf))
            pole = Mroot.to_3x3() @ V((sg * .10, -1, .1))
            K, Cc = ik(A, Ank, s.legl, s.legl, pole)
            ob.set(A, K, Cc, pole)

    def shoulder(s, sg, T):
        """Where the shoulder sits for a hand at T, in actor space, standing straight."""
        A = np.array((sg * (s.sx - .045), .012, s.hip + s.L - .10))
        A[2] += .055 * max(0, min(1, (T[2] - A[2] + .45) / .8))
        return A

    def _aim(s, sg, T, h, el=None):
        A = s.shoulder(sg, T)
        T = handrig.round_shoulder(sg, A, T)
        pl = handrig.pole_for(sg, A, T, (el, 1) if el else None)
        E, C = handrig.ik(A, np.asarray(T, float), s.armLen - .005, s.armLen - .005, pl)
        d_, t0 = handrig.neutral(A, E, C, pl, sg)
        return handrig.clamp_joint(*handrig.aim(d_, t0, sg, h.get('f'), h['b']))

    def joint(s, g, side, q):
        """The forearm roll and wrist of a gesture for this character, once. q: where the gesture puts the hand, from the shoulder line."""
        k = (g, side)
        if k not in s._j:
            sg = -1 if side == 'L' else 1
            h = handrig.gesture_hand(g, side)
            if isinstance(h, dict):
                fp = handrig.FACE.get(g, {}).get(side)
                if fp is not None:
                    hsc = s.m.get('hscale', 1.0)
                    T = np.array((0, 0, s.hip + s.L + .065)) + hsc * np.array(fp)
                else:
                    T = np.array(s.place(g, side, q), float) + (0, 0, s.hip + s.L)
                h = s._aim(sg, T, h, handrig.elbow(g, side))
            s._j[k] = tuple(h)
        return s._j[k]

    def place(s, g, side, q):
        """Where a gesture puts the hand on this body: a hand at rest hangs clear of these hips, a hand on the hip finds this waist."""
        sg = -1 if side == 'L' else 1
        if g == 'rest' or tuple(q) == tuple(handrig.REST_AT[side]):
            # hanging, with the small bend a relaxed elbow keeps, at whatever length this arm is
            x = sg * max(s.m['hw'] + .20, s.sx + .12)
            dx = x - sg * (s.sx - .045)
            return (x, q[1], -.10 - math.sqrt(max(.04, (1.91 * (s.armLen - .005)) ** 2 - dx * dx - .002)))
        if g in ('hips', 'proud'):
            return (sg * (s.m['ww'] + .11), q[1], q[2])
        if g == 'pockets':
            return (sg * (s.m['hw'] + .03), q[1], q[2])
        return tuple(q)

    def joint_at(s, side, M, w, bk, base):
        """The same for a hand sent to a place in the world, with the back of the hand facing bk (world), or left as it was."""
        if bk is None:
            return base
        Mi = M.inverted()
        sg = -1 if side == 'L' else 1
        return s._aim(sg, np.array(Mi @ V(w)), dict(b=np.array(Mi.to_3x3() @ V(bk))))

    def _tuck_nape(s, hsc):
        """The nape tube of every head stood 7 to 9 cm behind the shirt's back all the way down to its flat-cut ring (measured),
        so it sat on the collar like a tab. Below this character's own shirt line its back is drawn forward under the shirt; above the shirt
        line nothing moves, so the torso's neck stays inside the head and no second skin shows. Head space: z from the neck pivot, y back."""
        if s.head_mesh.get('nape_tucked'):
            # meshes are shared by path (claymat.load): another instance of this rig already tucked it, and head0 was read from it
            s.nape_tuck, s.nape_top = s.head_mesh['nape_tucked'], s.head_mesh.get('nape_top', 0.0)
            return
        b = s.base
        zh_t = lambda zh: s.L + .065 + hsc * zh
        rows = []
        for zh in np.arange(-.12, .14, .01):
            sl = b[(np.abs(b[:, 2] - zh_t(zh)) < .009) & (b[:, 1] > 0)]
            bk = sl[np.abs(sl[:, 0]) < .05]
            if len(bk) >= 8:
                rows.append((zh, np.abs(sl[:, 0]).max(), bk[:, 1].max()))
        shirt = [r for r in rows if r[1] > .22]
        if not shirt:
            return
        top = max(r[0] for r in shirt)                      # the shirt's top edge at the back
        under = [r[2] for r in rows if top - .08 <= r[0] <= top - .01]
        if not under:
            return
        target = (float(np.percentile(under, 25)) - .018) / hsc
        h = s.head0
        z_s, z_e = top + .015, top - .035
        low = (h[:, 2] < z_s) & (h[:, 2] > -.15)
        hb = float(h[low, 1].max())
        D0 = max(0.0, hb - target)
        s.nape_tuck, s.nape_top = D0, float(top)
        if D0 <= 0:
            return
        c_ = np.clip((z_s - h[:, 2]) / (z_s - z_e), 0, 1)
        c_ = c_ * c_ * (3 - 2 * c_)
        yk = np.clip(h[:, 1] / max(hb, 1e-3), 0, 1)
        h[:, 1] -= D0 * c_ * yk
        s.head_mesh.vertices.foreach_set('co', h.ravel())
        s.head_mesh.update()
        s.head_mesh['nape_tucked'], s.head_mesh['nape_top'] = float(D0), float(top)

    def set_face(s, fc):
        if fc is None:
            fc = np.zeros(len(faceops.CTRL))
        k = tuple(np.round(fc, 3))
        hr = tuple(round(x, 4) for x in getattr(s, '_hrot', (0, 0, 0))) if NECKFIX else None
        if k == s.last_fc and hr == getattr(s, 'last_hr', None):
            return
        s.last_fc = k
        co = s.head0.copy()
        for nm, i in faceops.IDX.items():
            c = float(fc[i])
            if abs(c) > .002 and nm in s.fields:
                idx, D = s.fields[nm]
                co[idx] += c * D
        if NECKFIX and hr != getattr(s, 'last_hr', None) or NECKFIX and s.last_hr is None:
            s.last_hr = hr
            q_ = Euler(hr).to_quaternion()
            ax_, an_ = q_.to_axis_angle()
            if abs(an_) > 1e-5:
                co[s.nape_i] = twist(co[s.nape_i], s.nape_w, tuple(ax_), an_)
                hc_ = s.hair0.copy()
                hc_[s.hnape_i] = twist(hc_[s.hnape_i], s.hnape_w, tuple(ax_), an_)
            else:
                hc_ = s.hair0
            s.hair.data.vertices.foreach_set('co', hc_.ravel())
            s.hair.data.update()
        elif NECKFIX:
            q_ = Euler(hr).to_quaternion()
            ax_, an_ = q_.to_axis_angle()
            if abs(an_) > 1e-5:
                co[s.nape_i] = twist(co[s.nape_i], s.nape_w, tuple(ax_), an_)
        s.head_mesh.vertices.foreach_set('co', co.ravel())
        s.head_mesh.update()
        s.jawp.rotation_euler = (faceops.THETA * float(fc[faceops.IDX['jaw']]), 0, float(fc[faceops.IDX['jawSide']]) * .05)
        s.tongue.location = (s.tinv[0], s.tinv[1] - .02 * float(fc[faceops.IDX['tongueUp']]), s.tinv[2] + .05 * float(fc[faceops.IDX['tongueUp']]))

def lerp_(a, b, t):
    return a + (b - a) * t
