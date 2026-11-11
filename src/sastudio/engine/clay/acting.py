"""Acting: how a clay puppet performs a scene. Runs inside Blender, next to puppet.py.

Every value is a pure function of the frame, so any frame of a scene can be rendered on its own, in any order, and a
shot that stopped half way picks up where it was. A performance is built from three things:

  lines   who speaks when, with the mouth shapes of the words: the body moves with what is said
  keys    what each actor is told to do at a frame: a gesture, a feeling, someone to look at, a seat
  walks   where each actor is told to go: feet plant, the pelvis rides over them, the arms swing against the legs

Conventions: an actor faces -Y, z is up, a character stands about 3.4 units tall, 24 frames a second.
"""
import math

import numpy as np
from mathutils import Euler, Matrix
from mathutils import Vector as V

import faceops
import handrig

CTRL, FI = faceops.CTRL, faceops.IDX
clamp = lambda v, a=0, b=1: max(a, min(b, v))
lerp = lambda a, b, t: a + (b - a) * t
sm = lambda t: t * t * (3 - 2 * t)
_h = lambda n: (math.sin(n * 127.1) * 43758.5453) % 1
WALKJ = (10, -5, -5)          # forearm roll and wrist of a walking arm


def noise(x, seed=0):
    i = math.floor(x)
    t = x - i
    u = t * t * (3 - 2 * t)
    return lerp(_h(i + seed * 57.3), _h(i + 1 + seed * 57.3), u) * 2 - 1


def blink_at(f, seed=0):
    at, i = int(_h(seed + .5) * 40), 0
    while at + 8 < f and i < 4000:
        at += 56 + int(_h(seed + i * 1.37) * 110)
        i += 1
    d = f - at
    return 0 if d < 0 or d > 5 else [.6, 1, 1, .6, .25, 0][d]


def anticipate(t):
    """Anticipation before the move, overshoot after it: the whole secret of weight."""
    t = clamp(t)
    return sm(t) - .09 * math.sin(2 * math.pi * t) * (1 - t)


def FV(**k):
    """A face as muscle positions. A name without L/R sets both sides."""
    v = np.zeros(len(CTRL))
    for a_, b_ in k.items():
        if a_ in FI:
            v[FI[a_]] = b_
        else:
            v[FI[a_ + 'L']] = b_
            v[FI[a_ + 'R']] = b_
    return v


# ---------------------------------------------------------------- speech
# Mouth shapes (the Rhubarb alphabet) as muscle positions. Modest on purpose: a real mouth barely opens to talk; clay
# speaks with its whole lower face, so they are scaled up a little.
VF = {k: v * 1.3 for k, v in dict(
    A=FV(), B=FV(jaw=.13, wide=.32, upLip=.22), C=FV(jaw=.38, wide=.22, upLip=.12), D=FV(jaw=.72, wide=.06),
    E=FV(jaw=.36, pucker=.34), F=FV(jaw=.15, pucker=.92), G=FV(jaw=.08, fv=1, upLip=.35),
    H=FV(jaw=.34, tongueUp=1, wide=.1), X=FV()).items()}
OPEN = dict(A=0, B=.25, C=.6, D=1, E=.7, F=.35, G=.2, H=.55, X=0)
KERNEL = np.array([.07, .22, .42, .22, .07])     # coarticulation: shapes melt into each other


class Line:
    """One spoken line: who, first and last frame, and mouth cues [[seconds, shape]] from the start of the line."""

    def __init__(s, who, start, end, cues, fps, to=None, manual=()):
        s.who, s.s, s.e, s.to, s.manual = who, int(start), int(end), to, set(manual)
        n = max(1, s.e - s.s)
        dur = n / fps
        st = np.zeros(n + 1)
        fc = np.zeros((n + 3, len(CTRL)))
        for i, (t0, m) in enumerate(cues or []):
            t1 = cues[i + 1][0] if i + 1 < len(cues) else dur
            st[int(t0 * fps):int(t1 * fps) + 1] = OPEN.get(m, .3)
            fc[max(0, int(t0 * fps) - 1):int(t1 * fps) + 1] = VF.get(m, VF['X'])   # the mouth leads the sound by a frame
        s.st = np.convolve(st, np.array([.1, .2, .4, .2, .1]), 'same')
        s.fc = np.apply_along_axis(lambda v: np.convolve(v, KERNEL, 'same'), 0, fc)


# ---------------------------------------------------------------- feelings
def M_(u, l, bL, bR, tL, tR, **c):
    return dict(u=u, l=l, bL=bL, bR=bR, tL=tL, tR=tR, c=FV(**c))


# upper lid, lower lid (degrees), brow height L/R, brow tilt L/R, and the face
MOOD = dict(
    neutral=M_(-27, 40, .1, .1, 0, 0, smile=.14), happy=M_(-28, 31, .3, .3, 0, 0, smile=.62, squint=.3),
    grin=M_(-30, 26, .5, .5, 0, 0, smile=.86, jaw=.2, upLip=.6, wide=.55, squint=.65),
    worry=M_(-32, 40, .55, .55, -.45, -.45, frown=.36, pucker=.1, brow=.5),
    shock=M_(-40, 44, 1, 1, -.2, -.2, jaw=.42, pucker=.18, brow=1), sad=M_(-24, 38, .25, .25, -.6, -.6, frown=.8, brow=.3),
    smug=M_(-22, 35, .8, .1, .18, 0, smileR=.85, smileL=.06, jawSide=.22, squintR=.35, browL=.7),
    deadpan=M_(-22, 40, .05, .05, 0, 0), proud=M_(-27, 33, .4, .4, 0, 0, smile=.72, squint=.25),
    think=M_(-24, 38, .65, .0, -.1, .1, pucker=.2, frownL=.22, smileR=.12, browL=.6),
    annoyed=M_(-23, 37, -.15, -.15, .45, .45, frown=.5, sneer=.3, squint=.3), brow=M_(-27, 40, .95, .0, .1, 0, browL=.9),
    oops=M_(-34, 36, .8, .8, -.3, -.3, wide=.72, jaw=.06, upLip=.62, frown=.15, brow=.6),
    surprise=M_(-37, 42, .9, .9, -.12, -.12, jaw=.2, brow=.9),
    recognise=M_(-30, 37, .55, .35, 0, 0, smileR=.22, smileL=.1, browL=.4),
    concern=M_(-29, 38, .5, .5, -.4, -.4, frown=.28, press=.5, brow=.4),
    hesitate=M_(-26, 36, .3, .55, -.25, -.1, pucker=.16, frownL=.28, jawSide=-.15, browR=.5),
    relief=M_(-24, 32, .35, .35, -.15, -.15, smile=.5, squint=.2), warm=M_(-25, 32, .25, .25, -.1, -.1, smile=.5, squint=.35),
    wince=M_(-14, 28, -.05, -.05, .3, .3, wide=.6, upLip=.5, jaw=.05, sneer=.3, squint=.7),
    tender=M_(-23, 33, .4, .4, -.32, -.32, smile=.34, squint=.18, brow=.3),
)
# clay faces act big and hold it: the feeling has to reach the back of a meeting room
for _m in MOOD.values():
    _m['bL'] *= 1.45
    _m['bR'] *= 1.45
    _m['tL'] *= 1.4
    _m['tR'] *= 1.4
    _m['c'] = np.clip(_m['c'] * 1.38, -1.7, 1.7)
# how far the eyes open, and how the head carries each feeling
for _k, _v in dict(neutral=0, happy=-.15, grin=-.35, worry=.45, shock=1.15, sad=-.25, smug=-.6, deadpan=-.55, proud=.08, think=-.2,
                   annoyed=-.5, brow=.25, oops=.65, surprise=1, recognise=.35, concern=.3, hesitate=.12, relief=-.12, warm=-.15,
                   wince=-.8, tender=-.15).items():
    MOOD[_k]['c'][FI['openL']] = _v
    MOOD[_k]['c'][FI['openR']] = _v
MOOD['grin']['c'][FI['jaw']] = .46
MOOD['grin']['c'][FI['upLip']] = .86
MOOD['shock']['c'][FI['jaw']] = .95
MOOD['surprise']['c'][FI['jaw']] = .55
CARRY = dict(sad=.11, worry=.05, oops=.05, proud=-.07, shock=-.06, surprise=-.05, smug=-.04, annoyed=.03, happy=-.02, grin=-.03)

# ---------------------------------------------------------------- gestures
# Hand targets from the shoulder line in actor space (x side, y depth with -y forward, z up), finger shape, and what the
# body does with it. The forearm roll and the wrist of each gesture are in handrig.GJ.
GEST = dict(
    rest=dict(L=(-.54, -.03, -1.02), R=(.54, -.03, -1.02)),
    talk=dict(L=(-.60, -.36, -.58), R=(.60, -.36, -.52), pL='open', pR='open'),
    point=dict(L=(-.54, -.03, -1.02), R=(.95, -.55, -.02), pR='point', side=.03),
    pointL=dict(L=(-.95, -.55, -.02), R=(.54, -.03, -1.02), pL='point', side=-.03),
    shrug=dict(L=(-.84, -.28, -.28), R=(.84, -.28, -.28), pL='open', pR='open', squash=.035),
    # arms folded: each wrist stops at the opposite elbow, the hands lying along the arm
    cross=dict(L=(.13, -.40, -.31), R=(-.13, -.34, -.44), pL='relax', pR='relax', bend=-.015),
    chin=dict(L=(-.18, -.36, -.42), R=(.13, -.50, -.03), pR='relax', bend=.02),
    head=dict(L=(-.30, -.16, .60), R=(.30, -.16, .60), pL='open', pR='open', squash=.03),
    hips=dict(L=(-.46, -.02, -.74), R=(.46, -.02, -.74), pL='fist', pR='fist', bend=-.01),
    wave=dict(L=(-.54, -.03, -1.02), R=(.70, -.25, .42), pR='open', wave=1),
    up=dict(L=(-.76, -.30, .46), R=(.76, -.30, .46), pL='open', pR='open', bend=-.03),
    present=dict(L=(-.92, -.42, -.28), R=(.92, -.42, -.28), pL='open', pR='open'),
    presentR=dict(L=(-.54, -.03, -1.02), R=(1.0, -.42, -.2), pR='open', side=.025),
    presentL=dict(L=(-1.0, -.42, -.2), R=(.54, -.03, -1.02), pL='open', side=-.025),
    scared=dict(L=(-.24, -.46, -.12), R=(.24, -.46, -.12), pL='open', pR='open', bend=-.05, squash=.03),
    clasp=dict(L=(-.05, -.44, -.52), R=(.05, -.44, -.52), bend=.012),
    pockets=dict(L=(-.38, -.04, -1.02), R=(.38, -.04, -1.02), pL='fist', pR='fist'),
    oops=dict(L=(-.54, -.03, -1.02), R=(.10, -.56, .06), pR='open', bend=.03),
    facepalm=dict(L=(-.54, -.03, -1.02), R=(.17, -.60, .32), pR='open', bend=.05),
    desk=dict(L=(-.36, -.68, -.68), R=(.38, -.70, -.68), bend=.07),
    phone=dict(L=(-.54, -.03, -1.02), R=(.53, -.15, .33), pR='cradle'),
    hold=dict(L=(-.54, -.03, -1.02), R=(.38, -.62, -.48), pR='grip'),
    hold2=dict(L=(-.32, -.62, -.46), R=(.32, -.62, -.46), pL='grip', pR='grip'),
    thumb=dict(L=(-.54, -.03, -1.02), R=(.72, -.46, -.10), pR='thumb'),
    offer=dict(L=(-.54, -.03, -1.02), R=(.58, -.74, -.22), pR='open'),
    stop=dict(L=(-.54, -.03, -1.02), R=(.50, -.76, .02), pR='open'),
    slump=dict(L=(-.62, -.12, -1.06), R=(.62, -.12, -1.06), bend=.14, squash=.03),
    armsout=dict(L=(-.98, -.1, -.1), R=(.98, -.1, -.1), pL='open', pR='open'),
    typing=dict(L=(-.3, -.72, -.72), R=(.32, -.74, -.72), bend=.08),
    proud=dict(L=(-.46, -.02, -.74), R=(.46, -.02, -.74), pL='fist', pR='fist', bend=-.05),
    lean=dict(L=(-.62, -.3, -.7), R=(.62, -.3, -.7), bend=.12),
    recoil=dict(L=(-.5, -.3, -.2), R=(.5, -.3, -.2), pL='open', pR='open', bend=-.09),
    # the vocabulary of someone explaining something they care about
    talkR=dict(L=(-.54, -.03, -1.02), R=(.62, -.44, -.42), pR='open', side=.012),
    talkL=dict(L=(-.62, -.44, -.42), R=(.54, -.03, -1.02), pL='open', side=-.012),
    talkWide=dict(L=(-.78, -.40, -.44), R=(.78, -.40, -.44), pL='open', pR='open'),
    chest=dict(L=(-.54, -.03, -1.02), R=(.10, -.34, -.22), pR='open', bend=-.01),
    index=dict(L=(-.54, -.03, -1.02), R=(.56, -.46, .10), pR='point', bend=.012),
    palmsDown=dict(L=(-.48, -.54, -.5), R=(.48, -.54, -.5), pL='open', pR='open'),
    weigh=dict(L=(-.62, -.46, -.34), R=(.62, -.46, -.52), pL='open', pR='open'),
    namaste=dict(L=(-.085, -.46, -.34), R=(.085, -.46, -.34), pL='open', pR='open', bend=.05),
)
# what a speaker's hands do when nobody directed them: changed on the thought, not on a timer
TALK = ['talk', 'talkR', 'chest', 'talkWide', 'weigh', 'talkL', 'palmsDown', 'presentR']
# how a person carries themselves: how big and loose the acting is, posture, how they stand and walk
STYLE = dict(amp=1.0, loose=1.0, bend=0.0, stance=.24, speed=.075, step=.9, bob=.045, contra=.8)
KEYS = ('g', 'f', 'look', 'face', 'on', 'lean', 'seat', 'nod', 'turn', 'tilt', 'ly', 'hL', 'hR', 'pL', 'pR', 'bkL', 'bkR')
SEAT_H = .82      # an ordinary chair: where the top of the seat is


def _wph(e, n):
    """Walking phase 0..n+1 for an eased walk fraction e over n plants: the first move is quick and short, then one per plant."""
    s = e * n
    r = min(1.5, n)
    x = clamp(s / r)
    return s + (1 - (1 - x) * (1 - x))


class Actor:
    def __init__(a, name, puppet, pos, style=None, **init):
        a.name, a.P = name, puppet
        a.st = dict(STYLE)
        a.st.update(style or {})
        a.seed = sum(map(ord, name)) % 97
        st = dict(g='rest', f='neutral', look=None, face=None, on=True, lean=0)
        st.update({k: v for k, v in init.items() if k in KEYS})
        a.init = st
        a.raw = []          # (frame, what changes), in the order they were given
        a.keys = [(-999, st)]
        a.walks = []        # (f0, f1, p0, p1, plants, distance)
        a.pos0 = tuple(pos) + ((0,) if len(pos) == 2 else ())
        a.last_yaw = None

    def key(a, f, d):
        """From frame f on: any of g (gesture), f (feeling), look, face, on, lean, seat, nod / turn / tilt (the head, added
        to where it already looks), ly, hL/hR (a hand sent to a place in the world), pL/pR (finger shape), bkL/bkR.
        Keys may be given in any order; a later call wins a tie."""
        a.raw.append((int(f), {k: v for k, v in d.items() if k in KEYS}))

    def walk(a, f, to, snap=False, speed=None):
        p0 = a.walks[-1][3] if a.walks else a.pos0
        if a.walks and f < a.walks[-1][1] and a.walks[-1][1] > a.walks[-1][0]:
            # told to go somewhere else before arriving: leave from where the feet actually are
            p0 = tuple(a.locate(f)[0])
        to = tuple(to) + ((p0[2],) if len(to) == 2 else ())
        d = math.hypot(to[0] - p0[0], to[1] - p0[1])
        if snap or d < .05:
            a.walks.append((f, f, to, to, 0, 1))
            return f
        rn_ = clamp(((speed or a.st['speed']) - .13) / .09)     # how much of this is a run
        n = max(1, math.ceil(d / (a.st['step'] * (1 + .85 * rn_))))
        dur = int(d / (speed or a.st['speed'])) + (8 if rn_ < .5 else 3)
        a.walks.append((f, f + dur, p0, to, n, d))
        return f + dur

    def finish(a):
        st = dict(a.init)
        a.keys = [(-999, dict(st))]
        for f, d in sorted(a.raw, key=lambda k: k[0]):
            st = dict(st)
            st.update(d)
            a.keys.append((f, st))
        a.walks.sort(key=lambda w: w[0])

    def steps(a):
        """Frames where a shoe lands: for footsteps in the mix."""
        out = []
        for w in a.walks:
            if w[1] > w[0] and w[4]:
                pv_ = 0
                for f_ in range(w[0], w[1] + 1):
                    t_ = (f_ - w[0]) / max(1, w[1] - w[0])
                    ph_ = _wph(sm(t_) * .5 + t_ * .5, w[4])
                    if int(ph_ + 1e-6) > pv_:
                        pv_ = int(ph_ + 1e-6)
                        out.append(f_)
        return out

    def locate(a, f):
        """-> pelvis position, feet (moving foot, standing foot, which, lift, phase) or None, walk heading, walk amount"""
        p = a.pos0
        cur = None
        for w in a.walks:
            if w[0] > f:
                break
            cur = w
        stance = a.st['stance']

        def stand(p_, side):
            return (p_[0] + stance * side, p_[1] + (.02 if side < 0 else -.03), 0)
        if cur is None or f >= cur[1]:
            if cur is not None:
                p = cur[3]
                f0, f1, p0, p1, n, dist = cur
                # the settling step: the trailing foot comes in beside the other, so nobody ever skates to a halt
                if f1 > f0 and n and f < f1 + 9:
                    moving = 1 if n % 2 == 0 else -1     # the foot that moved last
                    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
                    L = math.hypot(dx, dy) or 1
                    ux, uy = dx / L, dy / L
                    fr = (f - f1) / 9
                    dl_ = dist * (n - .5) / n
                    last = (p0[0] + ux * dl_ - uy * stance * -moving, p0[1] + uy * dl_ + ux * stance * -moving, 0)
                    mv = tuple(lerp(u_, v_, sm(fr)) for u_, v_ in zip(last, stand(p1, -moving)))
                    return p, (mv, stand(p1, moving), -moving, math.sin(math.pi * fr) * .09, fr), 0, 0
            return p, None, 0, 0
        f0, f1, p0, p1, n, dist = cur
        t = (f - f0) / max(1, f1 - f0)
        e = sm(t) * .5 + t * .5
        pos = tuple(lerp(u, v, e) for u, v in zip(p0, p1))
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy) or 1
        ux, uy = dx / L, dy / L
        px, py = -uy, ux          # the walker's own right
        # the foot lands AHEAD of the hips and the hips pass over it at mid-stance: n+1 foot moves, a half step to start,
        # full steps, and a closing step that lands beside the other foot
        nn = n + 1
        ph = _wph(e, n)
        i = min(nn - 1, int(ph))
        fr = ph - i

        def plant(k, side):
            d_ = dist * clamp((k - .5) / n)
            return (p0[0] + ux * d_ + px * stance * side, p0[1] + uy * d_ + py * stance * side, 0)
        moving = 1 if i % 2 == 0 else -1
        # the first steps leave from where the feet actually are; the last lands where it should stay
        A = stand(p0, moving) if i <= 1 else plant(i - 1, moving)
        B = stand(p1, moving) if i == nn - 1 else plant(i + 1, moving)
        st = stand(p0, -moving) if i == 0 else plant(i, -moving)
        a.runk = clamp((dist / max(1, f1 - f0) - .13) / .09)
        lift = math.sin(math.pi * fr) * (.11 + .3 * a.runk)
        mv = tuple(lerp(x, y, sm(fr)) for x, y in zip(A, B))
        # the arms and the torso go into the walk over a beat; a walk cut short by the next one carries the stride across
        ib_ = a.walks.index(cur)
        base_ = 0.
        if ib_ > 0 and a.walks[ib_ - 1][1] > f0 and a.walks[ib_ - 1][1] > a.walks[ib_ - 1][0]:
            pw_ = a.walks[ib_ - 1]
            base_ = sm(min(clamp((f0 - pw_[0]) / 16), clamp((pw_[1] - f0) / 16)))
        in_ = base_ + (1 - base_) * sm(clamp((f - f0) / 16))
        amt = min(in_, sm(clamp((f1 - f) / 16)))
        return pos, (mv, st, moving, lift, fr), math.atan2(dx, -dy), amt

    def heading(a, f, face):
        """Which way the body points. People turn at a person's speed: a half turn takes about a second, it starts just before
        the first step and finishes just after it, and a walk that runs into another walk turns from one direction to the next."""
        RATE = .125     # radians a frame at most, on average
        yaw = face
        W = [w for w in a.walks if w[1] > w[0] and math.hypot(w[3][0] - w[2][0], w[3][1] - w[2][1]) > 1e-3]
        for i_, w in enumerate(W):
            f0, f1 = w[0], w[1]
            if f0 - 30 > f:
                break
            Y = math.atan2(w[3][0] - w[2][0], -(w[3][1] - w[2][1]))
            Ti = clamp(abs(Y) / RATE, 8, 25) if clamp((f1 - f0) / 24.) >= .5 else 8
            wi = sm(clamp((f - (f0 - Ti * .34)) / Ti))
            yaw = yaw + (Y - yaw) * wi
            nxt = W[i_ + 1][0] if i_ + 1 < len(W) else 1e9
            To = clamp(abs(Y - face) / RATE, 8, 25)
            if nxt - f1 > To + 10:
                # the walk is over: come round to whatever the scene wants, as the last step settles
                wo = sm(clamp((f - (f1 - To * .2)) / To))
                yaw = yaw + (face - yaw) * wo
        return yaw

    def state(a, f):
        cur = prev = a.keys[0]
        for k in a.keys:
            if k[0] > f:
                break
            prev = cur
            cur = k
        return prev, cur

    def head_pos(a):
        return a.last_head if hasattr(a, 'last_head') else V(a.pos0) + V((0, 0, 3.4))


class Performance:
    """Everyone on the set, the lines they speak and the things they can look at."""

    def __init__(s, fps=24, floor=0.0):
        s.fps, s.floor = fps, floor
        s.actors, s.lines, s.things = {}, [], {}
        s.cam = None

    def add(s, actor):
        s.actors[actor.name] = actor
        return actor

    def say(s, who, start, end, cues, to=None, manual=()):
        """A spoken line. `to`: who it is said to. `manual`: actors whose hands the scene directs itself during it."""
        s.lines.append(Line(who, start, end, cues, s.fps, to, manual))

    def direct(s):
        """Acting nobody wrote down: the speaker gestures and meets someone's eye, everyone else listens to them.
        Call it before giving the scene's own keys: a key given later wins."""
        lines = sorted(s.lines, key=lambda q: q.s)
        for i, l in enumerate(lines):
            t0 = l.s - 8
            nxt = lines[i + 1] if i + 1 < len(lines) else None
            for nm, a in s.actors.items():
                o = {}
                if l.who != nm and l.who in s.actors:
                    o['look'] = l.who
                elif l.who == nm:
                    others = [q for q in s.actors if q != nm]
                    o['look'] = l.to if l.to in s.actors else (others[0] if others else 'cam')
                    if nm not in l.manual:
                        # someone explaining doesn't hold one pose: change on the thought, not on a timer
                        k_ = a.seed % len(TALK)
                        pal = TALK[k_:] + TALK[:k_]
                        dur_f = l.e - l.s
                        o['g'] = pal[i % len(pal)]
                        n_ = int(dur_f / 62)
                        for j in range(1, n_ + 1):
                            a.key(l.s + j * dur_f // (n_ + 1), dict(g=pal[(i + j) % len(pal)]))
                        if nxt is None or nxt.who != nm or nxt.s - l.e > 30:
                            a.key(l.e + 4, dict(g='rest'))
                if o:
                    a.key(t0, o)

    def finish(s):
        for a in s.actors.values():
            a.finish()

    # ---- what the words do to a body
    def face_speech(s, who, f):
        for l in s.lines:
            if l.who == who and l.s - 1 <= f < l.e:
                return l.fc[min(max(0, f - l.s + 1), len(l.fc) - 1)]
        return None

    def speaking(s, who, f):
        v = 0
        for l in s.lines:
            if l.who == who:
                v = max(v, min(clamp((f - l.s + 5) / 5), clamp((l.e + 6 - f) / 8)))
        return v

    def stress(s, who, f):
        for l in s.lines:
            if l.who == who and l.s <= f < l.e:
                return float(l.st[min(f - l.s, len(l.st) - 1)])
        return 0

    def target_pos(s, t):
        if t is None:
            return None
        if isinstance(t, str):
            if t == 'cam':
                return s.cam.matrix_world.translation.copy() if s.cam is not None else None
            if t in s.actors:
                return s.actors[t].head_pos()
            if t in s.things:
                o = s.things[t]
                return o.matrix_world.translation.copy() if hasattr(o, 'matrix_world') else V(o)
            return None
        return V(t)

    def pose(s, f):
        # two passes on the first frame, so that everyone knows where everyone's head is before they look at each other
        if not getattr(s, '_primed', False):
            s._primed = True
            for a in s.actors.values():
                pose_actor(s, a, f)
        for a in s.actors.values():
            pose_actor(s, a, f)


def pose_actor(S_, a, f):
    """Put one actor where frame f has them: feet, pelvis, spine, arms, hands, head, eyes and face."""
    prev, cur = a.state(f)
    K_ = a.keys
    ki = 0
    for i_, k_ in enumerate(K_):
        if k_[0] > f:
            break
        ki = i_

    def fold(val, dur, delay=0, ease=sm):
        """A value carried from key to key. Each new key blends from wherever the last blend had got to, not from where it
        was heading: a change of mind arriving mid-move never snaps a hand or a face to the old target."""
        k = ki
        while k > 0 and f - K_[k][0] - delay < (dur(k) if callable(dur) else dur):
            k -= 1
        v = val(k)
        for m_ in range(k + 1, ki + 1):
            d_ = dur(m_) if callable(dur) else dur
            v = lerp(v, val(m_), ease(clamp((f - K_[m_][0] - delay) / max(d_, 1e-3))))
        return v
    P = a.P
    on = cur[1].get('on', True) and not getattr(a, 'cull', False)
    P.show(bool(on))
    if not on:
        return
    st_ = a.st
    g1 = GEST[cur[1]['g']]
    Mo = {k: fold(lambda m_, k=k: MOOD[K_[m_][1]['f']][k], 13) for k in MOOD['neutral']}
    pos, feet, yaw_w, walk_amt = a.locate(f)
    pos = (pos[0], pos[1], pos[2] + S_.floor)
    S = S_.speaking(a.name, f)
    str_ = S_.stress(a.name, f)
    seed = a.seed

    # facing: turn a little toward whoever matters; a row of people facing the lens is a line-up, not a scene
    def res_face(k_):
        face = k_.get('face', None)
        if face is None:
            lk_ = k_.get('look')
            face = lk_ if isinstance(lk_, str) and lk_ in S_.actors and S_.actors[lk_].P.vis else 0
        if isinstance(face, str):
            tp = S_.actors[face].head_pos() if face in S_.actors else None
            face = clamp(math.atan2(tp.x - pos[0], -(tp.y - pos[1])) * .62, -.68, .68) if tp is not None else 0
        return face
    face = fold(lambda m_: res_face(K_[m_][1]), 13)
    yaw = a.heading(f, face)
    hip = P.hip
    sz = hip + P.L  # shoulder line, in actor space
    # standing: slow weight shift with planted feet
    sway = noise(f / 44, seed) * .014 * st_['loose'] * (1 - walk_amt)
    breath = math.sin(f / 18 + seed)
    db_ = 14
    eb_ = lambda t_: anticipate(t_) if t_ < 1 else 1
    bendf = fold(lambda m_: GEST[K_[m_][1]['g']].get('bend', 0) + K_[m_][1].get('lean', 0), db_, ease=eb_) + st_['bend']
    sides = fold(lambda m_: GEST[K_[m_][1]['g']].get('side', 0), db_, ease=eb_)
    squash = fold(lambda m_: GEST[K_[m_][1]['g']].get('squash', 0), db_, ease=eb_) + .005 * breath
    wave_ = g1.get('wave', 0)
    # speech drives the body: nods and small rises on the stressed sounds
    bendf += .022 * str_ * st_['amp'] * S
    sides += .006 * noise(f / 30, seed + 2) * S * st_['amp'] - .3 * sway
    twist = .05 * noise(f / 26, seed + 3) * S * st_['amp']
    x, y, z = pos
    wtw_ = 0.
    fz = S_.floor
    if feet:
        mv, stn, moving, lift, fr = feet
        z_b = st_['bob'] * (math.sin(math.pi * fr) - .55) * walk_amt
        fL = mv if moving < 0 else stn
        fR = mv if moving > 0 else stn
        lfL = lift if moving < 0 else 0
        lfR = lift if moving > 0 else 0
        # a foot rolls heel to toe through the whole stride, and the roll carries across from one step to the next:
        # the standing foot lands heel first, goes flat, then its heel rises as the other foot reaches forward; it leaves
        # the floor from the toe, swings level, and reaches forward toes up for the next heel strike
        pm_ = .5 * (1 - sm(clamp(fr / .35))) - .3 * sm(clamp((fr - .55) / .4))
        ps_ = -.3 * (1 - sm(clamp(fr / .12))) + .5 * sm(clamp((fr - .62) / .38))
        pm_, ps_ = pm_ * walk_amt, ps_ * walk_amt
        rollL = pm_ if moving < 0 else ps_
        rollR = pm_ if moving > 0 else ps_
        # the foot pivots on its toe or its heel, not its middle: lift it by what the tilt would sink into the floor
        lfL += .2 * abs(math.sin(rollL))
        lfR += .2 * abs(math.sin(rollR))
        bendf += (.055 + .13 * getattr(a, 'runk', 0)) * walk_amt
        # weight falls over the standing foot; shoulders turn against the hips
        sides += .03 * moving * -math.sin(math.pi * fr) * walk_amt
        wtw_ = -.17 * st_['loose'] * math.cos(math.pi * fr) * moving * walk_amt
        twist += wtw_
    else:
        z_b = 0
        ss = st_['stance']
        lfL = lfR = rollL = rollR = 0
        # contrapposto: the weight sits over one hip, the free foot eases ahead; every so often the weight changes
        # sides, slowly, the way people actually stand
        cw_ = math.tanh(3 * noise(f / 300, seed + 5)) * st_.get('contra', 0)
        fL = (x - ss * .8, y + .02 - .05 * max(0, cw_), 0)
        fR = (x + ss * .8, y - .03 - .05 * max(0, -cw_), 0)
        x = x - .025 * cw_
    seat_h = fold(lambda m_: float(K_[m_][1]['seat'] if isinstance(K_[m_][1].get('seat'), (int, float)) and not isinstance(K_[m_][1].get('seat'), bool) else SEAT_H), db_)
    seatA = fold(lambda m_: 1 if K_[m_][1].get('seat') else 0, db_ + 8, ease=eb_)
    # standing still: whatever the gestures add, the torso's side lean stays small (walking and sitting keep theirs)
    standA = (1 - clamp(seatA)) * (1 - walk_amt)
    sides = lerp(sides, .03 * math.tanh(sides / .03), standA)
    cy_, sy_ = math.cos(yaw), math.sin(yaw)
    if seatA > 0:
        # sit: the pelvis lowers onto the seat, the feet come forward of the knees and stay on the floor
        fwd = (sy_, -cy_)
        rgt = (cy_, sy_)
        for_ = .66
        sL = (x - rgt[0] * .27 + fwd[0] * for_, y - rgt[1] * .27 + fwd[1] * for_, 0)
        sR = (x + rgt[0] * .27 + fwd[0] * for_, y + rgt[1] * .27 + fwd[1] * for_, 0)
        fL = tuple(lerp(p_, q_, seatA) for p_, q_ in zip(fL, sL))
        fR = tuple(lerp(p_, q_, seatA) for p_, q_ in zip(fR, sR))
        z = z - seatA * max(0, (hip + .09) - (seat_h + .15))
        bendf += .03 * seatA
    if fz:
        fL = (fL[0], fL[1], fL[2] + fz)
        fR = (fR[0], fR[1], fR[2] + fz)
    # stand tall: the leg slack exists for the stride; standing, the knees are all but straight
    slack_ = 2 * P.legl - (hip + .09 - .27) - .012
    z = z + max(0, slack_) * (1 - seatA)
    zr_ = z + z_b - abs(sway) * .3
    if seatA < .99:
        # the pelvis can only be as high as both legs reach: with a real stride, it sinks at double support and rises over
        # the standing foot. This is the rise and fall of a real walk, and no leg is ever asked to stretch past its length
        Rr_ = 2 * P.legl * .985
        cz_ = []
        for sg_, F_, lf_ in ((-1, fL, lfL), (1, fR, lfR)):
            hx_ = x + cy_ * sg_ * P.hipw
            hy_ = y + sy_ * sg_ * P.hipw
            dxy_ = math.hypot(F_[0] - hx_, F_[1] - hy_)
            cz_.append(F_[2] + lf_ + math.sqrt(max(.01, Rr_ * Rr_ - dxy_ * dxy_)) - (hip - .18))
        zc_ = min(cz_)
        k_ = .03    # a smooth minimum: the cap eases in, so the body never stops dead on it
        zr_ = lerp(min(zr_, zc_) - k_ * math.log1p(math.exp(-abs(zr_ - zc_) / k_)), zr_, clamp(seatA))
    root = V((x + sway * (1 - seatA), y, zr_))
    M = Matrix.Translation(root) @ Euler((0, 0, yaw)).to_matrix().to_4x4()
    Mi_ = M.inverted()

    def tgt(side, m_):
        # where key m_ sends this hand, from the shoulder line
        k_ = K_[m_][1]
        A_ = k_.get('h' + side)
        if A_ is not None:
            return Mi_ @ V(A_) - V((0, 0, sz))
        return V(P.place(k_['g'], side, GEST[k_['g']][side]))

    def durh(side, m_):
        return 10 + (tgt(side, m_) - tgt(side, max(m_ - 1, 0))).length * 9

    def hand4(side):
        # arrive through every move still in progress; each move keeps its own arc and its own little settle past the mark
        late = 1 if side == 'L' else 2
        kk = 'h' + side
        k = ki
        while k > 0 and f - K_[k][0] - late < durh(side, k) + 8:
            k -= 1
        q = tgt(side, k)
        arc = V((0, 0, 0))
        for m_ in range(k + 1, ki + 1):
            a_, b_ = tgt(side, m_ - 1), tgt(side, m_)
            dist = (b_ - a_).length
            durn = 10 + dist * 9
            ee = eb_(clamp((f - K_[m_][0] - late) / durn))
            q = q.lerp(b_, ee)
            arc += V((0, -.08 * dist, .16 * dist)) * math.sin(math.pi * clamp(ee))    # hands travel in arcs
            over = clamp((f - K_[m_][0] - late - durn) / 8)
            if 0 < over < 1:
                arc += (b_ - a_) * .035 * math.sin(math.pi * over) * (1 - over)
        q = q + arc
        sg = -1 if side == 'L' else 1
        held = fold(lambda m_: 1. if K_[m_][1].get(kk) is not None else 0., 8)
        if not walk_amt > .5:
            rest_ = GEST['rest']
            amp_ = fold(lambda m_: (1 if GEST[K_[m_][1]['g']].get('L') != rest_['L'] or side == 'R' else .2) * (.15 if GEST[K_[m_][1]['g']][side] == rest_[side] else 1), 10)
            k_ = S * amp_ * (1 - held)
            # speech beats, breath, and the idle drift that keeps hands from looking stuck
            q += V((sg * .04 * noise(f / 16, seed + sg), -.03 * str_, .085 * str_ * st_['amp'] * (.7 if sg < 0 else 1))) * k_
            q += V((0, 0, .012 * breath)) * (1 - held)
            q += V((.014 * noise(f / 31, seed + 5 + sg), .014 * noise(f / 37, seed + 7 + sg), .016 * noise(f / 29, seed + 11 + sg))) * st_['loose'] * (1 - held)
        if wave_ and side == 'R':
            q += V((math.sin(f / 3.2) * .13, 0, math.cos(f / 6.4) * .03))
        if feet and walk_amt > 0:
            # arm swing while walking: forward swings bend the elbow more than back swings
            fr = feet[4]
            sw = math.sin(math.pi * (fr * 1.0 + (0 if feet[2] > 0 else 1)) - math.pi / 2) * .38 * sg * (.65 + .35 * st_['loose'])
            A_ = walk_amt * (1 - held)
            q = q.lerp(V((sg * .56, sw, -.97 + .16 * max(0, -sw))), A_)
            # from a raised gesture the straight line to the walking arm runs through the shoulder: go round it
            q += V((sg * .2, -.08, 0)) * math.sin(math.pi * A_)
        if held < .5:
            # no arm ever locks out straight on its way to a pose this body can't reach: the hand stops just short
            sh_ = V((sg * (P.sx - .045), 0, -.1))
            mx_ = 1.93 * (P.armLen - .005)
            dq_ = q - sh_
            if dq_.length > mx_:
                q = sh_ + dq_.normalized() * mx_
        return M @ (q + V((0, 0, sz)))
    hL, hR = hand4('L'), hand4('R')
    # the hand in joint terms: forearm roll and wrist blend from gesture to gesture, so a palm can only turn the way a palm
    # turns, and fingers close and open through every shape in between, a touch out of step with each other
    rig = {}
    for side in 'LR':
        kp, kk, kb = 'p' + side, 'h' + side, 'bk' + side
        late = 1 if side == 'L' else 2

        def jt(m_, side=side, kk=kk, kb=kb):
            k_ = K_[m_][1]
            j_ = P.joint(k_['g'], side, GEST[k_['g']][side])
            if k_.get(kk) is not None:
                j_ = P.joint_at(side, M, k_[kk], k_.get(kb), j_)
            return np.array(j_, float)

        def dj(m_, side=side, jt=jt):
            # the arm gets there first and the palm finishes turning just after: a forearm rolls at its own pace
            p_, n_ = jt(max(m_ - 1, 0)), jt(m_)
            return max(durh(side, m_), 9 + max(abs(n_[0] - p_[0]) / 6.5, abs(n_[1] - p_[1]) / 4.5))
        j = list(fold(jt, dj, delay=late))
        # nobody's wrist is a bolted joint: it drifts, and it answers the speech
        sg_ = -1 if side == 'L' else 1
        spk_ = fold(lambda m_, side=side: 1. if GEST[K_[m_][1]['g']][side] != GEST['rest'][side] else .15, 10)
        j[0] += 3.5 * noise(f / 37, seed + 31 + sg_) * st_['loose']
        j[1] += 3 * noise(f / 41, seed + 37 + sg_) * st_['loose'] + 5 * str_ * S * st_['amp'] * spk_
        j[2] += 2 * noise(f / 47, seed + 41 + sg_)
        if wave_ and side == 'R':
            j[2] += 16 * math.sin(f / 3.2)
        if walk_amt > 0:
            j = [lerp(p_, q_, walk_amt) for p_, q_ in zip(j, WALKJ)]

        def fs(m_, kp=kp):
            k_ = K_[m_][1]
            return handrig.fvec(k_.get(kp) or GEST[k_['g']].get(kp, 'relax'))
        dfs = lambda m_, side=side: 7 + (tgt(side, m_) - tgt(side, max(m_ - 1, 0))).length * 6
        sh = np.concatenate([fold(lambda m_, i_=i_: fs(m_)[i_ * 3:i_ * 3 + 3], dfs, delay=late + 1 + (3 - i_) * .7) for i_ in range(4)]
                            + [fold(lambda m_: fs(m_)[12:], dfs, delay=late + 1)])
        if K_[ki][1].get(kp) in (None, 'relax', 'open') and GEST[K_[ki][1]['g']].get(kp, 'relax') in ('relax', 'open'):
            sh[:12] += .035 * noise(f / 43, seed + 51 + sg_)

        # hands on the face and elbow hints come and go with the move
        def last_of(table, m_):
            for q_ in range(m_, -1, -1):
                v_ = table(K_[q_][1]['g'])
                if v_:
                    return np.array(v_, float)
            return None
        ftab = lambda g_, side=side: handrig.FACE.get(g_, {}).get(side)
        etab = lambda g_, side=side: handrig.elbow(g_, side)
        dh = lambda m_, side=side: durh(side, m_)
        fw_ = None
        w_ = fold(lambda m_: 1. if ftab(K_[m_][1]['g']) else 0., dh, delay=late)
        if w_ > 1e-3:
            dflt = last_of(ftab, ki)
            fw_ = (tuple(fold(lambda m_: last_of(ftab, m_) if last_of(ftab, m_) is not None else dflt, dh, delay=late)), w_)
        a.face_w = getattr(a, 'face_w', {})
        a.face_w[side] = fw_[1] if fw_ else 0.
        el_ = None
        w_ = fold(lambda m_: 1. if etab(K_[m_][1]['g']) else 0., dh, delay=late)
        if w_ > 1e-3:
            dflt = last_of(etab, ki)
            el_ = (tuple(fold(lambda m_: last_of(etab, m_) if last_of(etab, m_) is not None else dflt, dh, delay=late)), w_ * (1 - walk_amt))
        rig[side] = (tuple(j), sh, fw_, el_)
    # head and eyes: eyes lead, head follows, body last
    Lk = S_.target_pos(cur[1].get('look'))
    Lk0 = S_.target_pos(prev[1].get('look'))
    hp = root + V((0, 0, hip + P.L + .65))

    def aim(T):
        if T is None:
            return 0, 0
        v = T - hp
        ya = math.atan2(v.x, -v.y) - yaw
        ya = (ya + math.pi) % (2 * math.pi) - math.pi
        return ya, math.atan2(-v.z, math.hypot(v.x, v.y))
    y1 = aim(Lk)[0] if Lk is not None else 0
    y0 = aim(Lk0)[0] if Lk0 is not None else 0
    he = sm(clamp((f - cur[0] - 2) / 13))

    def lk(m_):
        T_ = S_.target_pos(K_[m_][1].get('look'))
        return np.array(aim(T_) if T_ is not None else (0., 0.))
    hy, hpi = fold(lk, 13, delay=2)
    # blink on a big head turn: exactly what real eyes do
    bl = max(blink_at(f, seed), (1 if abs(y1 - y0) > .5 and 0 <= f - cur[0] < 3 else 0))
    # micro saccades while listening
    sacc = _h(int(f / 26) + seed) - .5
    sacz = _h(int(f / 33) + seed + 3) - .5
    ey_y, ey_p = fold(lk, 5)
    nod = fold(lambda m_: K_[m_][1].get('nod', 0), 8)
    if S < .1:
        # listening: the small nods of someone following along
        others = max((S_.speaking(o_, f) for o_ in S_.actors if o_ != a.name), default=0)
        nod += .04 * others * max(0, math.sin(f / 13 + seed))
    if feet and walk_amt > 0:
        nod += .02 * math.sin(2 * math.pi * feet[4]) * walk_amt
    nod += fold(lambda m_: CARRY.get(K_[m_][1]['f'], 0), 14)
    head = (clamp(hpi * .5, -.3, .3) + .07 * str_ * st_['amp'] * S + .02 * math.sin(f / 23 + seed) + nod,
            .025 * S * noise(f / 17, seed + 6) * st_['amp'] + .012 * noise(f / 50, seed + 8) - .9 * sides + fold(lambda m_: K_[m_][1].get('tilt', 0), 9),
            clamp(hy * .55, -.4, .4) + .10 * S * noise(f / 21, seed + 4) * st_['amp'] - .85 * wtw_ + fold(lambda m_: K_[m_][1].get('turn', 0), 5))
    # eye target remaining after the head moved: clamp stays in a friendly range
    lx = clamp((ey_y - head[2]) * 1.4 + sacc * .10, -.6, .6)
    ly = clamp((ey_p - head[0]) * 1.2 + sacz * .08 + fold(lambda m_: K_[m_][1].get('ly', 0), 5), -.6, .6)
    # the face: mood underneath, words on top, and the mood never quite leaves while they talk
    mc = Mo['c']
    sp = S_.face_speech(a.name, f)
    if sp is not None:
        fc = mc * .98
        fc[FI['jaw']] = mc[FI['jaw']] * .25
        fc = fc + sp
    else:
        fc = mc.copy()
    fc[FI['jawSide']] += .10 * noise(f / 46, seed + 21) * (.4 + .6 * S)
    fc[FI['press']] = clamp(1 - 3.1 * fc[FI['jaw']] - 1.1 * fc[FI['upLip']] - .9 * fc[FI['lowLip']] - .5 * fc[FI['fv']])
    # brows rise on stress; a talker's brows are never still
    br = .55 * str_ * st_['amp'] * S
    # the two eyes meet on what they look at (no look target: a comfortable middle distance)
    dv_ = (Lk - hp).length if Lk is not None else 8.0
    P.verg = min(.07, math.atan2(P.es * .97, max(1.2, dv_)))
    P.pose(loc=root, yaw=yaw, bend=(bendf + .004 * breath, sides), twist=twist, squash=squash, head=head, look=(lx, ly),
           upper=Mo['u'], lower=Mo['l'], blink=bl, browL=Mo['bL'] + br, browR=Mo['bR'] + br * .9, tiltL=Mo['tL'], tiltR=Mo['tR'],
           fc=fc, handL=hL, handR=hR, jL=rig['L'][0], jR=rig['R'][0], shapeL=rig['L'][1], shapeR=rig['R'][1],
           faceL=rig['L'][2], faceR=rig['R'][2], elL=rig['L'][3], elR=rig['R'][3],
           footL=fL, footR=fR, roll=(rollL, rollR), lift=(lfL, lfR),
           capeSway=(.05 * noise(f / 30, 3) + .22 * walk_amt + .03 * S * noise(f / 11, 2)),
           hairJ=((.016 * math.sin(2 * math.pi * feet[4] - 1.1) * walk_amt if feet else 0) + .006 * str_ * S,
                  (y1 - y0) * -.035 * math.sin(math.pi * he)))
    a.last_head = P.head_world + V((0, 0, .04))
    a.last_yaw = yaw + head[2]
    a.last_hand = dict(L=hL, R=hR)
