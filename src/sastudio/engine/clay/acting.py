"""Acting: how a clay puppet performs a scene. Runs inside Blender, next to puppet.py.

Every value is a pure function of the frame, so any frame of a scene can be rendered on its own, in any order, and a
shot that stopped half way picks up where it was. A performance is built from three things:

  lines   who speaks when, with the mouth shapes of the words: the body moves with what is said
  keys    what each actor is told to do at a frame: a gesture, a feeling, someone to look at, a seat
  walks   where each actor is told to go: feet plant, the pelvis rides over them, the arms swing against the legs

Conventions: an actor faces -Y, z is up, a character stands about 3.4 units tall, 24 frames a second.
"""
import bisect
import math

import numpy as np
from mathutils import Euler, Matrix
from mathutils import Vector as V

import body as B
from body import swing as _swing
import faceops
import handrig

CTRL, FI = faceops.CTRL, faceops.IDX
clamp = lambda v, a=0, b=1: max(a, min(b, v))
lerp = lambda a, b, t: a + (b - a) * t
sm = lambda t: t * t * (3 - 2 * t)
_ang = lambda d: (d + math.pi) % (2 * math.pi) - math.pi      # an angle brought into -pi..pi
_h = lambda n: (math.sin(n * 127.1) * 43758.5453) % 1
WALKJ = (10, -5, -5)          # forearm roll and wrist of a walking arm


def noise(x, seed=0):
    i = math.floor(x)
    t = x - i
    u = t * t * (3 - 2 * t)
    return lerp(_h(i + seed * 57.3), _h(i + 1 + seed * 57.3), u) * 2 - 1


def blink_at(f, seed=0, rate=1.0):
    at, i = int(_h(seed + .5) * 40), 0
    while at + 8 < f and i < 4000:
        at += max(14, int((56 + int(_h(seed + i * 1.37) * 110)) / max(.3, rate)))
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

    def __init__(s, who, start, end, cues, fps, to=None, manual=(), feeling=None):
        s.who, s.s, s.e, s.to, s.manual = who, int(start), int(end), to, set(manual)
        s.feeling = feeling
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
    # things in the hand: a phone or a page being read, a mug being carried
    read=dict(L=(-.54, -.03, -1.02), R=(.36, -.60, -.36), pR='tray', bend=.03),
    carry=dict(L=(-.54, -.03, -1.02), R=(.40, -.56, -.56), pR='cup'),
    sip=dict(L=(-.54, -.03, -1.02), R=(.16, -.50, .02), pR='cup', bend=-.02),
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
STYLE = dict(amp=1.0, loose=1.0, bend=0.0, stance=.24, speed=.075, step=.9, bob=.045, contra=.8,
             # habits (claydesign.acting_style): how steady the eyes are, how often they blink, how far a pleasant face
             # smiles, frames between a speaker's changes of gesture, listening nods, frames before a face reacts,
             # frames to sit down or get up, frames for each step of a turn, arm swing
             gaze=.4, blink=1.0, smile=1.0, gest=62, nod=1.0, react=5, sit=22, turn_step=8, swing=1.0)
# What a speaker's hands do when nobody directed them, by how they feel: open and easy, firm, unsettled, or thinking.
TALKS = dict(open=['talk', 'talkR', 'chest', 'talkWide', 'weigh', 'talkL', 'palmsDown', 'presentR'],
             firm=['index', 'talkR', 'palmsDown', 'presentR', 'talk', 'chest'],
             unsettled=['chest', 'clasp', 'talk', 'weigh', 'talkL', 'clasp'],
             thinking=['chin', 'weigh', 'index', 'talkR'])
FEEL = dict(neutral='open', happy='open', grin='open', proud='firm', warm='open', relief='open', tender='open', surprise='open',
            smug='firm', annoyed='firm', deadpan='firm', worry='unsettled', concern='unsettled', hesitate='unsettled',
            oops='unsettled', sad='unsettled', wince='unsettled', shock='unsettled', brow='thinking', think='thinking',
            recognise='thinking')
# how big the hands and the speech beats are, how often they change, and how much a listener nods along, by feeling
FEEL_AMP = dict(open=1.0, firm=1.05, unsettled=.7, thinking=.85)
FEEL_EVERY = dict(open=1.0, firm=1.15, unsettled=.8, thinking=1.4)
FEEL_NOD = dict(open=1.0, firm=.3, unsettled=.25, thinking=.6)
KEYS = ('g', 'f', 'look', 'face', 'on', 'lean', 'seat', 'nod', 'turn', 'tilt', 'ly', 'hL', 'hR', 'pL', 'pR', 'bkL', 'bkR', 'cL', 'cR',
        'laugh')
SEAT_H = .82      # an ordinary chair: where the top of the seat is
LOW = ('rest', 'pockets', 'slump')    # hands that hang: on a seat they rest on the thighs instead
LAPJ = (80, 30, -24)                  # a hand resting on a thigh: palm down and flat on it, the fingers turned a little out
HAND_R = .085                         # from the wrist to the surface of the hand, near enough, at hs 1
SIT_FRAMES = 22      # how long sitting down or standing up takes
SOLE = .004       # the shoe's lowest point sits this far under the foot's target: lift it so the sole rests on top
# Blinks a minute at rest, talking and reading: 17, 26 and 4.5 across 150 people (Bentivoglio et al. 1997, Movement
# Disorders 12:1028). A habit (STYLE blink) scales all three; reading a page or a screen and typing count as reading
BLINK_REST, BLINK_TALK, BLINK_READ = 17.0, 26.0, 4.5
READING = ('read', 'typing')
BLINK = (.6, 1, 1, .6, .25, 0)      # one blink, a drawing at a time: down quickly, up more slowly


def _wph(e, n):
    """Walking phase 0..n+1 for an eased walk fraction e over n plants: the first move is quick and short, then one per plant."""
    s = e * n
    r = min(1.5, n)
    x = clamp(s / r)
    return s + (1 - (1 - x) * (1 - x))


def _pivot(P, r):
    """(along the shoe, up) that keeps the lowest part of a shoe tilted by r where the flat sole rested (puppet.foot_pivot);
    a puppet without a measured sole turns on the ends of a 0.373 + 0.159 sole."""
    if hasattr(P, 'foot_pivot'):
        return P.foot_pivot(r)
    yp = -.373 if r > 0 else .159
    return yp * (1 - math.cos(r)), -yp * math.sin(r)


def standing_foot(p, side, psi, stance, cw=0.0):
    """Where a foot rests for a body standing at p with its feet pointing psi (side -1 left, 1 right): a little apart, the
    left a touch ahead. cw (-1..1) puts the weight on one hip and eases the free foot ahead (contrapposto)."""
    back = (.02 - .05 * max(0.0, cw)) if side < 0 else (-.03 - .05 * max(0.0, -cw))
    return (p[0] + math.cos(psi) * stance * .8 * side - math.sin(psi) * back,
            p[1] + math.sin(psi) * stance * .8 * side + math.cos(psi) * back, 0)


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
        a.walks = []        # (f0, f1, p0, p1, plants, distance, stance before, stance after, 'walk' | 'turn')
        fc_ = st.get('face')
        a.psi0 = float(fc_) if isinstance(fc_, (int, float)) else 0.0     # the way the feet point before any walk
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
        psi = a.stance(f)
        a.__dict__.pop('_ents', None)
        a.__dict__.pop('_pl', None)
        if snap or d < .05:
            a.walks.append((f, f, to, to, 0, 1, psi, psi, 'walk'))
            return f
        hd_ = math.atan2(to[0] - p0[0], -(to[1] - p0[1]))
        lw_ = a.walks[-1] if a.walks else None
        still_ = lw_ is None or f >= lw_[1] + (9 if lw_[8] == 'walk' and lw_[4] else 0)
        if still_ and abs(_ang(hd_ - psi)) > 1.75:
            # setting off behind or well to one side: round on the spot first, then away (a first step that far round
            # would cross one foot over the other)
            f = a.turn(f, hd_)
            psi = a.stance(f)
        rn_ = clamp(((speed or a.st['speed']) - .13) / .09)     # how much of this is a run
        n = max(1, math.ceil(d / (a.st['step'] * (1 + .85 * rn_))))
        dur = int(d / (speed or a.st['speed'])) + (8 if rn_ < .5 else 3)
        # the closing step lands beside the other foot, both pointing the way they walked; a turn after is stepped too
        a.walks.append((f, f + dur, p0, to, n, d, psi, math.atan2(to[0] - p0[0], -(to[1] - p0[1])), 'walk'))
        return f + dur

    def turn(a, f, to):
        """Turn round on the spot to face `to` (radians), the feet stepping round with the body, not sliding:
        -> the frame the turn is over. Small turns are left to the hips and the shoulders."""
        psi = a.stance(f)
        d = _ang(to - psi)
        if abs(d) < .45:
            return f
        lw = a.walks[-1] if a.walks else None
        if lw is not None and lw[8] == 'walk' and lw[4] and lw[1] > lw[0]:
            f = max(f, lw[1] + 9)       # the feet come together after a walk first, then the turn steps round
        # in pairs, 60 degrees a pair at most: any more and the opening foot would land where the other one stands
        n = 2 * max(1, math.ceil(abs(d) / 1.05))
        a.__dict__.pop('_ents', None)
        a.__dict__.pop('_pl', None)
        dur = int(n * a.st.get('turn_step', 8) + 4)
        p = a.walks[-1][3] if a.walks else a.pos0
        a.walks.append((f, f + dur, p, p, n, 0.0, psi, psi + d, 'turn'))
        return f + dur

    def stance(a, f):
        """The way the planted feet point when standing still at f, as the last walk or turn left them."""
        psi = a.psi0
        for w in a.walks:
            if w[0] > f:
                break
            if w[1] <= f:
                psi = w[7]
        return psi

    def finish(a):
        st = dict(a.init)
        a.keys = [(-999, dict(st))]
        for f, d in sorted(a.raw, key=lambda k: k[0]):
            st = dict(st)
            st.update(d)
            a.keys.append((f, st))
        a.walks.sort(key=lambda w: w[0])
        a.__dict__.pop('_ents', None)
        a.__dict__.pop('_pl', None)
        a.__dict__.pop('_blinks', None)

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
        """-> pelvis position, feet (moving foot, standing foot, which, lift, phase[, yaws]) or None, walk heading, walk
        amount. Each walk or turn starts from where the one before left the feet: a foot is never put down anywhere but
        by a step."""
        k = -1
        for i_, w in enumerate(a.walks):
            if w[0] > f:
                break
            k = i_
        if k < 0:
            return a.pos0, None, 0, 0
        cur = a.walks[k]
        if cur[8] == 'turn' and cur[0] <= f < cur[1]:
            return a._turning(k, f)
        if f >= cur[1]:
            return a._after(k, f)
        return a._walking(k, f)

    def _stand(a, p_, side, psi):
        """A foot of a body standing at p_ with its feet pointing psi: exactly where the still pose puts it."""
        return standing_foot(p_, side, psi, a.st['stance'])

    def _plant(a, cur, k, side):
        """Where foot `side` lands for plant k of walk cur: ahead of the hips, on the line of the walk."""
        f0, f1, p0, p1, n, dist = cur[:6]
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy) or 1
        ux, uy = dx / L, dy / L
        d_ = dist * clamp((k - .5) / n)
        stance = a.st['stance']
        return (p0[0] + ux * d_ - uy * stance * side, p0[1] + uy * d_ + ux * stance * side, 0)

    def _falls(a, k):
        """Where each foot of walk k lands, worked out once and in order: [(where, pointing, which foot)] for every
        move (the plants along the way, then the closing step). Each lands clear of the foot standing beside it: at a
        corner, the first foot of the new way would otherwise come down on the toe of the one still pointing the old way."""
        got = a.__dict__.setdefault('_pl', {}).get(k)
        if got is not None:
            return got
        cur = a.walks[k]
        n = cur[4]
        ent = a._entry(k)
        first = ent['first']
        psi_w = math.atan2(cur[3][0] - cur[2][0], -(cur[3][1] - cur[2][1]))
        last = {s_: (ent['pos'][s_], ent['yaw'][s_]) for s_ in (-1, 1)}
        out = []
        for j in range(n + 1):
            side = first if j % 2 == 0 else -first
            pos, yw = (a._plant(cur, j + 1, side), psi_w) if j < n else (a._stand(cur[3], side, cur[7]), cur[7])
            for _ in range(4):
                g, nrm = B.feet_gap(pos, yw, last[-side][0], last[-side][1])
                if g >= .026 or nrm == (0.0, 0.0):
                    break
                # (1.5 cm apart: a little more than the centimetre they keep, for the next foot to turn as it lifts)
                pos = (pos[0] + nrm[0] * (.03 - g), pos[1] + nrm[1] * (.03 - g), 0)
            last[side] = (pos, yw)
            out.append((pos, yw, side))
        a._pl[k] = out
        return out

    def _entry(a, k):
        """Where each foot is and which way it points as walk or turn k begins, and which foot moves first: where the
        one before left them. A walk that follows another at once carries the stride on from the feet as they are; one
        given before the last was over leaves from mid-stride, the foot in the air carrying on."""
        ents = a.__dict__.setdefault('_ents', {})
        if k in ents:
            return ents[k]
        w = a.walks[k]
        psi = w[6]
        ent = dict(pos={s_: a._stand(w[2], s_, psi) for s_ in (-1, 1)}, yaw={-1: psi, 1: psi}, first=1, lift=0.0)
        if w[8] == 'walk' and w[1] > w[0]:
            # setting off to one side: the foot on that side steps out first, so the other never crosses it
            d_ = _ang(math.atan2(w[3][0] - w[2][0], -(w[3][1] - w[2][1])) - psi)
            if abs(d_) > .35:
                ent['first'] = 1 if d_ > 0 else -1
        pv = a.walks[k - 1] if k > 0 else None
        moved = pv is not None and pv[1] > pv[0] and (pv[8] == 'turn' or pv[4])
        feet = None
        if moved and w[0] < pv[1]:
            feet = (a._turning if pv[8] == 'turn' else a._walking)(k - 1, w[0])[1]
        elif moved and pv[8] == 'walk' and w[0] < pv[1] + 9:
            feet = a._walking(k - 1, pv[1])[1]
        if feet is not None:
            mv, st, side, lift = feet[:4]
            yaws = feet[5] if len(feet) > 5 else (pv[7], pv[7])
            ent['pos'] = {side: (mv[0], mv[1], 0), -side: (st[0], st[1], 0)}
            ent['yaw'] = {side: yaws[0], -side: yaws[1]}
            ent['lift'] = lift
            if lift > 1e-6:
                ent['first'] = side
            elif w[8] == 'walk':
                dx, dy = w[3][0] - w[2][0], w[3][1] - w[2][1]
                d_ = _ang(math.atan2(dx, -dy) - pv[7])
                if abs(d_) > .35:
                    # round a corner the way people do (a step turn): the foot on the side turned to steps out first and
                    # the other comes round outside it, so neither ever crosses the other
                    ent['first'] = 1 if d_ > 0 else -1
                else:
                    # straight on: the foot further behind goes first
                    pr = {s_: (ent['pos'][s_][0] - w[2][0]) * dx + (ent['pos'][s_][1] - w[2][1]) * dy for s_ in (-1, 1)}
                    if abs(pr[1] - pr[-1]) > .01 * (math.hypot(dx, dy) or 1):
                        ent['first'] = 1 if pr[1] < pr[-1] else -1
        ents[k] = ent
        return ent

    def _turning(a, k, f):
        """Turning on the spot, in pairs of steps: the foot on the side turned to opens out first, then the other
        comes round beside it, never past it (toes never cross); the other stays planted while one steps."""
        cur = a.walks[k]
        f0, f1, p0, p1, n = cur[:5]
        psi0, D = cur[6], _ang(cur[7] - cur[6])
        pairs = max(1, n // 2)
        ph = clamp((f - f0) / max(1, f1 - f0)) * n
        i = min(n - 1, int(ph))
        fr = ph - i
        first = 1 if D > 0 else -1
        ang = lambda j: psi0 + D * (j + 1) / pairs if j >= 0 else psi0
        j = i // 2
        frm, to = ang(j - 1), ang(j)
        side = first if i % 2 == 0 else -first
        if j == 0:
            # the first pair leaves from where the feet are
            ent = a._entry(k)
            A, yA = ent['pos'][side], ent['yaw'][side]
            other, yo = (ent['pos'][-side], ent['yaw'][-side]) if i % 2 == 0 else (a._stand(p0, -side, to), to)
        else:
            A, yA = a._stand(p0, side, frm), frm
            # the trailing foot waits where it was; the leading one where it opened to
            other, yo = (a._stand(p0, -side, frm), frm) if i % 2 == 0 else (a._stand(p0, -side, to), to)
        mv = _swing(A, a._stand(p0, side, to), yA, to, other, yo, sm(fr))
        return p0, (mv, other, side, math.sin(math.pi * fr) * .07, fr, (yA + _ang(to - yA) * sm(fr), yo)), 0, 0

    def _after(a, k, f):
        """Once walk or turn k is over: the trailing foot steps in beside the other, so nobody ever skates to a halt;
        if the next walk or turn starts before it would have, the feet wait where they are, mid-stride."""
        cur = a.walks[k]
        f0, f1, p0, p1, n, dist = cur[:6]
        if not (f1 > f0 and n and cur[8] == 'walk' and f < f1 + 9):
            return cur[3], None, 0, 0
        first = a._entry(k)['first']
        last_ = first if n % 2 == 0 else -first          # the foot that moved last
        falls = a._falls(k)
        trail, here = falls[n - 1][0], falls[n][0]
        psi_w = math.atan2(p1[0] - p0[0], -(p1[1] - p0[1]))
        if k + 1 < len(a.walks) and a.walks[k + 1][0] < f1 + 9:
            return p1, (trail, here, -last_, 0.0, 0.0, (falls[n - 1][1], falls[n][1])), 0, 0
        fr = (f - f1) / 9
        mv = _swing(trail, a._stand(p1, -last_, cur[7]), falls[n - 1][1], cur[7], here, falls[n][1], sm(fr))
        y0_ = falls[n - 1][1]
        return p1, (mv, here, -last_, math.sin(math.pi * fr) * .09, fr, (y0_ + _ang(cur[7] - y0_) * sm(fr), falls[n][1])), 0, 0

    def _walking(a, k, f):
        cur = a.walks[k]
        f0, f1, p0, p1, n, dist = cur[:6]
        t = (f - f0) / max(1, f1 - f0)
        e = sm(t) * .5 + t * .5
        pos = tuple(lerp(u, v, e) for u, v in zip(p0, p1))
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        # the foot lands AHEAD of the hips and the hips pass over it at mid-stance: n+1 foot moves, a half step to start,
        # full steps, and a closing step that lands beside the other foot
        nn = n + 1
        ph = _wph(e, n)
        i = min(nn - 1, int(ph))
        fr = ph - i
        ent = a._entry(k)
        falls = a._falls(k)
        first = ent['first']
        moving = first if i % 2 == 0 else -first
        # the first steps leave from where the feet actually are; each lands where the walk's plan puts it
        A = ent['pos'][moving] if i <= 1 else falls[i - 2][0]
        B, yb = falls[i][0], falls[i][1]
        st = ent['pos'][-moving] if i == 0 else falls[i - 1][0]
        a.runk = clamp((dist / max(1, f1 - f0) - .13) / .09)
        lift = math.sin(math.pi * fr) * (.11 + .3 * a.runk)
        if i == 0 and ent['lift']:
            lift = max(lift, ent['lift'] * (1 - sm(fr)))      # a foot already in the air when the way changed stays up
        # each foot keeps the way it landed pointing until it lifts, and turns in the air: a foot on the floor never
        # swivels under a body that turns at a corner; and the stepping foot goes round the standing one, never through
        psi_w = math.atan2(dx, -dy)
        ya = ent['yaw'][moving] if i <= 1 else falls[i - 2][1]
        yst = ent['yaw'][-moving] if i == 0 else falls[i - 1][1]
        mv = _swing(A, B, ya, yb, st, yst, sm(fr))
        yaws = (ya + _ang(yb - ya) * sm(fr), yst)
        # the arms and the torso go into the walk over a beat; a walk cut short by the next one carries the stride across
        base_ = 0.
        if k > 0 and a.walks[k - 1][1] > f0 and a.walks[k - 1][1] > a.walks[k - 1][0]:
            pw_ = a.walks[k - 1]
            base_ = sm(min(clamp((f0 - pw_[0]) / 16), clamp((pw_[1] - f0) / 16)))
        in_ = base_ + (1 - base_) * sm(clamp((f - f0) / 16))
        amt = min(in_, sm(clamp((f1 - f) / 16)))
        return pos, (mv, st, moving, lift, fr, yaws), psi_w, amt

    def settled(a, f):
        """0 the moment the feet stop moving, 1 a second and a quarter later, back to 0 as the next walk or turn nears:
        how far the stance may ease into its habits (the weight on one hip, the free foot ahead) without a slide."""
        last_end, nxt = -10 ** 9, 10 ** 9
        for w in a.walks:
            if w[1] <= w[0]:
                continue
            if w[0] > f:
                nxt = w[0]
                break
            last_end = max(last_end, w[1] + (9 if w[8] == 'walk' and w[4] else 0))
        return sm(clamp((f - last_end) / 30)) * sm(clamp((nxt - f) / 20))

    def heading(a, f, face):
        """Which way the body points. People turn at a person's speed: a half turn takes about a second, it starts just before
        the first step and finishes just after it, and a walk that runs into another walk turns from one direction to the next."""
        RATE = .125     # radians a frame at most, on average
        yaw = face
        W = [w for w in a.walks if w[1] > w[0] and math.hypot(w[3][0] - w[2][0], w[3][1] - w[2][1]) > 1e-3]
        TT = [w for w in a.walks if w[8] == 'turn']
        for i_, w in enumerate(W):
            f0, f1 = w[0], w[1]
            if f0 - 30 > f:
                break
            Y = math.atan2(w[3][0] - w[2][0], -(w[3][1] - w[2][1]))
            Ti = clamp(abs(_ang(Y - yaw)) / RATE, 8, 25) if clamp((f1 - f0) / 24.) >= .5 else 8
            wi = sm(clamp((f - (f0 - Ti * .34)) / Ti))
            Y = yaw + _ang(Y - yaw)                # always the short way round
            yaw = yaw + (Y - yaw) * wi
            nxt = W[i_ + 1][0] if i_ + 1 < len(W) else 1e9
            To = clamp(abs(_ang(Y - face)) / RATE, 8, 25)
            if nxt - f1 > To + 10 and not any(0 <= t_[0] - f1 <= 3 for t_ in TT):
                # the walk is over: come round to whatever the scene wants, as the last step settles
                wo = sm(clamp((f - (f1 - To * .2)) / To))
                yaw = yaw + _ang(face - yaw) * wo
        for t_ in TT:
            # a turn on the spot: the body goes round with its stepping feet, then settles on whatever the scene wants
            if t_[0] > f:
                break
            yt = t_[6] + _ang(t_[7] - t_[6]) * sm(clamp((f - t_[0]) / max(1, t_[1] - t_[0])))
            yaw = yt if f <= t_[1] else yt + _ang(face - yt) * sm(clamp((f - t_[1]) / 10))
        return yaw

    def seat_amt(a, f):
        """How far into sitting they are at frame f (0 standing, 1 seated): the same blend the pose uses, without posing."""
        K_, ki = a.keys, 0
        for i_, k_ in enumerate(K_):
            if k_[0] > f:
                break
            ki = i_
        k = ki
        dur = a.st.get('sit', SIT_FRAMES)
        while k > 0 and f - K_[k][0] < dur:
            k -= 1
        v = 1.0 if K_[k][1].get('seat') else 0.0
        for m_ in range(k + 1, ki + 1):
            t_ = clamp((f - K_[m_][0]) / dur)
            v = lerp(v, 1.0 if K_[m_][1].get('seat') else 0.0, anticipate(t_) if t_ < 1 else 1)
        return clamp(v)

    def laugh_at(a, f):
        """(frames since this laugh began, how strong it still is) or None: a laugh is bursts of breath that fade."""
        start = None
        for fk, st in a.keys:
            if fk > f:
                break
            if st.get('laugh') and start is None:
                start = fk
            elif not st.get('laugh'):
                start = None
        if start is None:
            return None
        t = f - start
        return t, clamp(t / 3) * clamp(1 - (t - 26) / 14)

    def blink(a, f, S_):
        """How far the eyes are shut at f (0..1). This person blinks as often as their habit says at rest, more while they
        talk, far less while they read or type, and once just after somebody they listen to finishes a line (listeners
        blink at the end of a turn: Hömke, Holler and Levinson 2017). Worked out once for the whole scene, so every shot
        of it blinks at the same moments, and the same scene always blinks the same way."""
        got = a.__dict__.get('_blinks')
        if got is None or f > got[0] - 600:
            # the same blinks from the same start, only further on (blinks a while before the end never change)
            got = a._blinks = a._blink_times(S_, max(f + 2400, got[0] if got else 0))
        ev = got[1]
        i = bisect.bisect_right(ev, f) - 1
        d = f - ev[i] if i >= 0 else -1
        return BLINK[d] if 0 <= d < len(BLINK) else 0

    def _blink_times(a, S_, upto):
        """-> (the last frame worked out, the frames where a blink starts)"""
        mine = [(l.s, l.e) for l in S_.lines if l.who == a.name]
        theirs = [l.e for l in S_.lines if l.who != a.name]
        frames = [k[0] for k in a.keys if k[0] > -999] + [l.s for l in S_.lines] + [l.e for l in S_.lines] + [0]
        lo, hi = min(frames) - 200, max(max(frames) + 900, upto)
        base = a.st.get('blink', 1.0) / (60.0 * S_.fps)
        keys = [k for k in a.keys if k[0] > -999]
        out, clock, i, ki, g = [], 0.0, 0, 0, a.keys[0][1].get('g')
        due = .2 + .8 * _h(a.seed + .5)
        for t in range(lo, hi):
            while ki < len(keys) and keys[ki][0] <= t:
                g = keys[ki][1].get('g', g)
                ki += 1
            per = BLINK_READ if g in READING else BLINK_TALK if any(s_ <= t < e_ for s_, e_ in mine) else BLINK_REST
            clock += per * base
            if clock >= due and (not out or t - out[-1] >= 14):
                out.append(t)
                clock, i = 0.0, i + 1
                due = .45 + 1.1 * _h(a.seed + i * 1.37)
        for e_ in theirs:
            # a listener's blink as the other one finishes, most of the time, when the eyes are not just back open
            at = e_ + 3 + int(6 * _h(a.seed * 3.1 + e_ * .73))
            if _h(a.seed * 5.3 + e_ * 1.17) < .7 and not any(abs(at - b_) < 14 for b_ in out):
                out.append(at)
        return hi, sorted(out)

    def aversion(a, f, S_):
        """A speaker's look away (0..1) and which way (-1/1, and up or down): as most lines begin, while the thought is
        put into words, and back on the listener well before the line ends to hand the turn over (Kendon 1967; Andrist,
        Mutlu and Gleicher 2013, who measured it in people and found agents that did it seemed to be thinking). Longer
        lines and wandering eyes make it likelier; no two lines do it alike."""
        for l in S_.lines:
            if l.who == a.name and l.s - 2 <= f < l.e:
                n = l.e - l.s
                if n < 24:
                    return 0.0, 1, 1
                h = _h(a.seed * 7.13 + l.s * .37)
                if h > .3 + .45 * a.st.get('gaze', .4) + .25 * clamp((n - 48) / 96):
                    return 0.0, 1, 1
                hold = min(int(10 + 22 * _h(a.seed + l.s * 1.91)), int(n * .45))
                t = f - l.s
                v = sm(clamp((t - 2) / 5)) * sm(clamp((2 + hold - t) / 7))
                return v, (1 if _h(a.seed + l.s * 2.71) > .5 else -1), (1 if _h(a.seed + l.s * 3.33) < .4 else -1)
        return 0.0, 1, 1

    def seat_info(a, f):
        """The measured seat (film.measure_seat) this actor sits on, is sitting down on or getting up from at f."""
        S = None
        for fk, st in a.keys:
            if fk > f:
                break
            if isinstance(st.get('seat'), dict):
                S = st['seat']
        return S

    def sit_solution(a, S):
        """How this body sits on that seat (body.seated), worked out once."""
        cache = a.__dict__.setdefault('_sol', {})
        if S['id'] not in cache:
            sol = B.seated(a.body, S, prefer=S.get('prefer'))
            cache[S['id']] = sol
            for n_ in sol['notes']:
                print(f"FILM {a.name} on {S['name']}: {n_}", flush=True)
        return cache[S['id']]

    def stood_up(a, f):
        """0..1: how much they are standing where they just got up from a chair. Someone who stands up pushes the
        chair back and stands a little behind where they sat; it fades as they sit again, or with their first step away."""
        m, was = None, bool(a.keys[0][1].get('seat'))
        for k in a.keys[1:]:
            if k[0] > f:
                break
            now = bool(k[1].get('seat'))
            if was and not now:
                m = k[0]
            was = now
        if m is None:
            return 0.0
        w = 1.0 - clamp(a.seat_amt(f)) ** 2       # back first, then up: the thighs come out from under the table
        for wk in a.walks:
            if wk[1] > wk[0] and m <= wk[0] <= f:
                w *= 1 - sm(clamp((f - wk[0]) / 12))
                break
        return w

    def walking(a, f):
        """True while a walk is under way at frame f."""
        return any(w[0] <= f <= w[1] and w[1] > w[0] for w in a.walks)

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
        s.ground = None     # f(x, y) -> the height of whatever solid surface is under that point (set by the film)
        s.settle = None     # f(frame): after everyone is posed, measure contacts and correct them (set by the film)
        s.actors, s.lines, s.things = {}, [], {}
        s.cam = None

    def add(s, actor):
        s.actors[actor.name] = actor
        return actor

    def say(s, who, start, end, cues, to=None, manual=(), feeling=None):
        """A spoken line. `to`: who it is said to. `manual`: actors whose hands the scene directs itself during it.
        `feeling`: how it is said, which decides what the speaker's hands do when the scene does not say."""
        s.lines.append(Line(who, start, end, cues, s.fps, to, manual, feeling))

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
                        # someone explaining doesn't hold one pose: change on the thought, not on a timer. What the hands
                        # do follows how the line is said: open and easy, firm, unsettled (close to the body), thinking
                        cls = FEEL.get(l.feeling or 'neutral', 'open')
                        talk = TALKS[cls]
                        k_ = a.seed % len(talk)
                        pal = talk[k_:] + talk[:k_]
                        dur_f = l.e - l.s
                        o['g'] = pal[i % len(pal)]
                        n_ = int(dur_f / (a.st.get('gest', 62) * FEEL_EVERY[cls]))
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

    def target_pos(s, t, me=None):
        if t is None:
            return None
        if isinstance(t, str):
            if t == 'hand':
                h = getattr(me, 'last_hand', None)
                return h['R'].copy() if h else None
            if t == 'cam':
                return s.cam.matrix_world.translation.copy() if s.cam is not None else None
            if t in s.actors:
                return s.actors[t].head_pos()
            if t in s.things:
                o = s.things[t]
                return o.matrix_world.translation.copy() if hasattr(o, 'matrix_world') else V(o)
            return None
        return V(t)

    def ground_at(s, x, y):
        """Where a foot set down at (x, y) comes to rest: the top of the floor, the rug or the base it stands on."""
        return s.floor if s.ground is None else s.ground(x, y)

    def ground_foot(s, x, y, yaw):
        """A foot is not a point: it rests on the highest thing under its heel, its middle or its toe."""
        if s.ground is None:
            return s.floor
        fx, fy = math.sin(yaw), -math.cos(yaw)
        rx, ry = -fy, fx
        return max(s.ground(x + fx * d + rx * w, y + fy * d + ry * w) for d in (-.16, 0.0, .12, .24) for w in (-.1, 0.0, .1))

    def pose(s, f):
        # two passes on the first frame, so that everyone knows where everyone's head is before they look at each other
        if not getattr(s, '_primed', False):
            s._primed = True
            for a in s.actors.values():
                s.pose_one(a, f)
        for a in s.actors.values():
            s.pose_one(a, f)
        if s.settle is not None:
            s.settle(f)     # nothing solid passes through anything else: measured, and put right

    def pose_one(s, a, f):
        if getattr(a.P, 'guest', False):
            import guest
            guest.pose(s, a, f)        # a model somebody brought: its own, simpler, way of acting
        else:
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
    Mo = {k: fold(lambda m_, k=k: MOOD[K_[m_][1]['f']][k], 13, delay=st_.get('react', 5)) for k in MOOD['neutral']}
    feel_ = FEEL.get(cur[1]['f'], 'open')
    ampf_ = st_['amp'] * FEEL_AMP[feel_]       # an unsettled body keeps its hands and its words smaller
    pos, feet, yaw_w, walk_amt = a.locate(f)
    for cp_, cb_, cd_ in getattr(a, 'chairs', ()):
        if cd_ and math.hypot(pos[0] - cp_[0], pos[1] - cp_[1]) < .3:
            # just stood up from this chair: they stand a little behind where they sat, clear of the table's edge
            w_ = a.stood_up(f) * cd_
            pos = (pos[0] + cb_[0] * w_, pos[1] + cb_[1] * w_, pos[2])
            break
    pos = (pos[0], pos[1], pos[2] + S_.ground_at(pos[0], pos[1]))
    S = S_.speaking(a.name, f)
    str_ = S_.stress(a.name, f)
    seed = a.seed

    # facing: turn a little toward whoever matters; a row of people facing the lens is a line-up, not a scene
    def res_face(k_):
        face = k_.get('face', None)
        if face is None:
            lk_ = k_.get('look')
            # someone the camera does not show in this shot (culled, not drawn) is still in the room: keep turning to them
            other = S_.actors.get(lk_) if isinstance(lk_, str) else None
            face = lk_ if other is not None and (other.P.vis or getattr(other, 'cull', False)) else 0
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
    lg_ = a.laugh_at(f)
    burst_ = 0.0
    if lg_ is not None:
        # a laugh: a breath in, then bursts that come quicker than speech and fade; the shoulders jump with each one
        lt_, lw_ = lg_
        burst_ = lw_ * abs(math.sin(math.pi * lt_ / 5.5)) * (1 - .5 * clamp(lt_ / 40))
        squash += (.022 * burst_ - (.012 if lt_ < 3 else 0.0)) * (.7 + .3 * st_['amp'])
    if cur[1]['g'] == 'read' and cur[1].get('look') == 'hand':
        squash -= .004        # reading something in the hand: a little forward and still
    wave_ = g1.get('wave', 0)
    # speech drives the body: nods and small rises on the stressed sounds
    bendf += .022 * str_ * ampf_ * S
    if lg_ is not None:
        bendf += .04 * burst_ - .05 * lg_[1] * clamp(1 - lg_[0] / 9)      # back on the first burst, forward on the rest
    if cur[1]['g'] == 'read' and cur[1].get('look') == 'hand':
        bendf += .03
    sides += .006 * noise(f / 30, seed + 2) * S * ampf_ - .3 * sway
    twist = .05 * noise(f / 26, seed + 3) * S * ampf_
    x, y, z = pos
    # where they stand or sit, for remembered corrections: what is learnt arriving on foot is not what holds sitting
    a.spot = (round(x, 1), round(y, 1), bool(cur[1].get('seat')))
    wtw_ = 0.
    fz = S_.floor
    shoeL = shoeR = None      # which way each shoe points: the stance's way when standing (the hips may turn further)
    if feet:
        mv, stn, moving, lift, fr = feet[:5]
        if len(feet) > 5:
            shoeL, shoeR = (feet[5][0], feet[5][1]) if moving < 0 else (feet[5][1], feet[5][0])
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
        # a tilted foot turns on whatever part of it is still on the floor: the ball of the foot when the heel is up, the
        # heel when the toes are up. Lifted, and moved along itself, by exactly what that takes, so that part stays put
        yL_ = yaw if shoeL is None else shoeL
        yR_ = yaw if shoeR is None else shoeR
        dh_, dz_ = _pivot(P, rollL)
        fL = (fL[0] - dh_ * math.sin(yL_), fL[1] + dh_ * math.cos(yL_), fL[2])
        lfL += dz_
        dh_, dz_ = _pivot(P, rollR)
        fR = (fR[0] - dh_ * math.sin(yR_), fR[1] + dh_ * math.cos(yR_), fR[2])
        lfR += dz_
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
        # (eased in once the feet have been still a while, and out before they move: the free foot never skates)
        cw_ = math.tanh(3 * noise(f / 300, seed + 5)) * st_.get('contra', 0) * a.settled(f)
        ps_ = a.stance(f)
        shoeL = shoeR = ps_
        fL = standing_foot((x, y), -1, ps_, ss, cw_)
        fR = standing_foot((x, y), 1, ps_, ss, cw_)
        x, y = x - math.cos(ps_) * .025 * cw_, y - math.sin(ps_) * .025 * cw_
    sitF = st_.get('sit', SIT_FRAMES)
    seatA = clamp(fold(lambda m_: 1. if K_[m_][1].get('seat') else 0., sitF, ease=eb_))
    ST = a.seat_info(f) if seatA > 0 and getattr(a, 'body', None) else None
    sol = a.sit_solution(ST) if ST is not None else None
    # standing still: whatever the gestures add, the torso's side lean stays small (walking and sitting keep theirs)
    standA = (1 - seatA) * (1 - walk_amt)
    sides = lerp(sides, .03 * math.tanh(sides / .03), standA)
    if shoeL is not None and not (feet and len(feet) > 5):
        # feet planted while the body turns to someone: the toes follow the hips a little, never across each other
        dy_ = clamp(_ang(yaw - shoeL), -.3, .3) * .5
        shoeL, shoeR = shoeL + dy_, shoeR + dy_
    if ST is not None:
        # which way each shoe pointed standing: a foot keeps it until it lifts to step to its seated place
        sy0_ = (yaw if shoeL is None else shoeL, yaw if shoeR is None else shoeR)
        shoeL = shoeR = None
        # a seated body faces the way its seat does: its legs are in the seat, so only its shoulders and head turn; with
        # the hands on a keyboard or a table the shoulders stay square to it and the head does the turning (a body that
        # turned with its hands left where they were would put an arm through its own chest)
        busy_ = fold(lambda m_: 1.0 if (K_[m_][1].get('hL') is not None or K_[m_][1].get('hR') is not None) else 0.0, 14)
        twist += clamp(_ang(yaw - ST['yaw']), -.6, .6) * .45 * seatA * (1 - .8 * busy_)
        yaw = ST['yaw'] + _ang(yaw - ST['yaw']) * (1 - sm(clamp(seatA * 1.6)))
    cy_, sy_ = math.cos(yaw), math.sin(yaw)
    if ST is not None:
        # the measured seat (film.measure_seat) and how this body sits on it (body.seated): the thighs on the seat,
        # the knees past its edge, the feet on the floor in front of whatever is under it
        (ox_, oy_), (fx_, fy_), (rx_, ry_) = ST['origin'], ST['fwd'], ST['right']
        au_ = sol['ankle'][0]
        # the foot on the side the body is moving to leads, so neither foot steps across the other. Decided from where
        # they stand (the feet as the stance puts them, without the weight shifts of standing still), so it is the same
        # foot at every drawing of the sit: never one foot starting and the other taking over half way
        ps0_ = a.stance(f)
        c0_ = {s_: standing_foot(pos, s_, ps0_, st_['stance']) for s_ in (-1, 1)}
        cx_, cyy_ = ox_ + fx_ * au_ + rx_ * ST['lat'], oy_ + fy_ * au_ + ry_ * ST['lat']
        mvl_ = ((c0_[-1][0] + c0_[1][0]) / 2 - cx_) * rx_ + ((c0_[-1][1] + c0_[1][1]) / 2 - cyy_) * ry_
        if abs(mvl_) > .01:
            lead_ = 'L' if mvl_ > 0 else 'R'
        else:
            # standing straight in front of where the feet go: the foot with further to go steps first
            far_ = {}
            for s_ in (-1, 1):
                lt0_ = ST['lat'] + s_ * (a.body['hipw'] + .035)
                far_[s_] = math.hypot(ox_ + fx_ * au_ + rx_ * lt0_ - c0_[s_][0], oy_ + fy_ * au_ + ry_ * lt0_ - c0_[s_][1])
            lead_ = 'L' if far_[-1] > far_[1] + 1e-6 else 'R'
        for side_, sg_ in (('L', -1), ('R', 1)):
            t0_ = 0.0 if side_ == lead_ else .27
            # a small step back to where the seated feet go, one foot and then the other (never both off the floor at
            # once), before the weight goes down; getting up, the same steps forward once the weight is over the feet
            fe_ = clamp((seatA - t0_) / .27)
            lat_ = ST['lat'] + sg_ * (a.body['hipw'] + .035)
            sf_ = (ox_ + fx_ * au_ + rx_ * lat_, oy_ + fy_ * au_ + ry_ * lat_, 0)
            # a foot on the floor keeps pointing the way it stood; it turns to the seat's way only while it is lifted
            yw0_ = sy0_[0 if side_ == 'L' else 1]
            yw_ = yw0_ + _ang(ST['yaw'] - yw0_) * sm(fe_)
            if side_ == 'L':
                shoeL = yw_
            else:
                shoeR = yw_
            if side_ == 'L':
                stepL_ = math.hypot(sf_[0] - fL[0], sf_[1] - fL[1])
                fL = tuple(lerp(p_, q_, sm(fe_)) for p_, q_ in zip(fL, sf_))
                lfL = lfL + math.sin(math.pi * fe_) * min(.07, .03 + stepL_ * .12)
            else:
                stepR_ = math.hypot(sf_[0] - fR[0], sf_[1] - fR[1])
                fR = tuple(lerp(p_, q_, sm(fe_)) for p_, q_ in zip(fR, sf_))
                lfR = lfR + math.sin(math.pi * fe_) * min(.07, .03 + stepR_ * .12)
        lfL = lerp(lfL, sol['lift'], seatA)
        lfR = lerp(lfR, sol['lift'], seatA)
        rollL = lerp(rollL, sol['toe'], seatA)
        rollR = lerp(rollR, sol['toe'], seatA)
    elif seatA > 0:
        # somewhere to sit with nothing measured under it (a seat given by height only): the pelvis lowers to that
        # height, the feet come forward of the knees and stay on the floor
        seat_h = fold(lambda m_: float(K_[m_][1]['seat'] if isinstance(K_[m_][1].get('seat'), (int, float)) and not isinstance(K_[m_][1].get('seat'), bool) else SEAT_H), db_)
        fwd = (sy_, -cy_)
        rgt = (cy_, sy_)
        for_ = .66
        sL = (x - rgt[0] * .27 + fwd[0] * for_, y - rgt[1] * .27 + fwd[1] * for_, 0)
        sR = (x + rgt[0] * .27 + fwd[0] * for_, y + rgt[1] * .27 + fwd[1] * for_, 0)
        fL = tuple(lerp(p_, q_, seatA) for p_, q_ in zip(fL, sL))
        fR = tuple(lerp(p_, q_, seatA) for p_, q_ in zip(fR, sR))
        z = z - seatA * max(0, (hip + .09) - (seat_h + .15)) + seatA * getattr(a, 'seat_lift', 0.0)
        bendf += .03 * seatA
    # a foot that was found standing in a chair's base or a table's foot is moved clear of it, at this spot only
    here_ = a.spot
    if walk_amt < .05 and getattr(a, 'foot_push', None):
        pl_, pr_ = a.foot_push.get((here_, 'L')), a.foot_push.get((here_, 'R'))
        if pl_:
            fL = (fL[0] + pl_[0], fL[1] + pl_[1], fL[2])
        if pr_:
            fR = (fR[0] + pr_[0], fR[1] + pr_[1], fR[2])
    if walk_amt < .05 and getattr(a, 'foot_lift', None):
        fL = (fL[0], fL[1], fL[2] + a.foot_lift.get((here_, 'L'), 0.0))
        fR = (fR[0], fR[1], fR[2] + a.foot_lift.get((here_, 'R'), 0.0))
    # each foot comes down on the solid surface under it (floor, rug, a table's base), not through it
    fL = (fL[0], fL[1], fL[2] + S_.ground_foot(fL[0], fL[1], yaw if shoeL is None else shoeL) - S_.floor + fz + SOLE)
    fR = (fR[0], fR[1], fR[2] + S_.ground_foot(fR[0], fR[1], yaw if shoeR is None else shoeR) - S_.floor + fz + SOLE)
    wl_ = getattr(a, 'walk_lift', None)
    if wl_ and wl_.get('f') == f:
        # mid-stride, a rolling heel or toe was measured in the floor this frame: lifted by exactly that, this frame only
        fL = (fL[0], fL[1], fL[2] + wl_.get('L', 0.0))
        fR = (fR[0], fR[1], fR[2] + wl_.get('R', 0.0))
    # stand tall: the leg slack exists for the stride; standing, the knees are all but straight
    slack_ = 2 * P.legl - (hip + .09 - .27) - .012
    stood_ = 1.0 if ST is not None else (1 - seatA)       # a measured seat blends the whole standing body below
    z = z + max(0, slack_) * stood_
    zr_ = z + z_b - abs(sway) * .3
    if seatA < .99 or ST is not None:
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
        zr_ = lerp(min(zr_, zc_) - k_ * math.log1p(math.exp(-abs(zr_ - zc_) / k_)), zr_, 0.0 if ST is not None else clamp(seatA))
    if ST is not None:
        # down onto the seat: the hips go back, then down, the chest comes forward over the feet (body.sit_path)
        (ox_, oy_), (fx_, fy_), (rx_, ry_) = ST['origin'], ST['fwd'], ST['right']
        us_ = (x - ox_) * fx_ + (y - oy_) * fy_
        ls_ = (x - ox_) * rx_ + (y - oy_) * ry_
        u_, zr_, lean_ = B.sit_path(seatA, (us_, zr_), (sol['u'], sol['z'] + ST.get('rise', 0.0)))
        lt_ = lerp(ls_, ST['lat'], sm(seatA))
        x, y = ox_ + fx_ * u_ + rx_ * lt_, oy_ + fy_ * u_ + ry_ * lt_
        bendf += lean_ * st_.get('sit_lean', 1.0) + (sol['lean'] + getattr(a, 'sit_fwd', {}).get(ST['id'], 0.0)) * seatA
        sway *= 1 - seatA
    root = V((x + sway * (1 - seatA), y, zr_))
    M = Matrix.Translation(root) @ Euler((0, 0, yaw)).to_matrix().to_4x4()
    Mi_ = M.inverted()
    # seated, hands that would hang at the sides rest on the thighs instead: a hanging hand would be in the seat
    lap_, lapw_ = None, 0.0
    if sol is not None:
        lapw_ = sm(clamp((seatA - .35) / .65))
        fw1_, z1_ = B.lap(a.body, sol, .45)
        lz_ = z1_ - sol['z'] + .085 + max(0.0, .2 * math.tan(sol['alpha']))
        ll_ = getattr(a, 'lap_lift', {})
        lap_ = {sd_: V((sg_ * (a.body['hipw'] + a.body['thigh_r'] * .8), -fw1_, lz_ - sz + ll_.get(sd_, 0.0))) for sd_, sg_ in (('L', -1), ('R', 1))}

    def tgt(side, m_):
        # where key m_ sends this hand, from the shoulder line
        k_ = K_[m_][1]
        A_ = k_.get('h' + side)
        if A_ is not None:
            # a hand laid on a table rests on it: lifted by what the last measurement found inside the top
            return Mi_ @ (V(A_) + V((0, 0, getattr(a, 'hand_lift', {}).get(side, 0.0)))) - V((0, 0, sz))
        base_ = V(P.place(k_['g'], side, GEST[k_['g']][side]))
        if lap_ is not None and k_['g'] in LOW:
            # resting on the thigh, held a little higher when it holds something (a phone, a mug) against it
            base_ = base_.lerp(lap_[side] + V((0, 0, .07 if k_.get('c' + side) else 0.0)), lapw_)
        nd_ = getattr(a, 'hand_nudge', {}).get((side, K_[m_][0]))
        if nd_ is not None:
            # this gesture's hand was found inside something on the set: it ends clear of it
            base_ = base_ + Mi_.to_3x3() @ V(nd_)
        return base_

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
            rampf_ = fold(lambda m_: (1 if GEST[K_[m_][1]['g']].get('L') != rest_['L'] or side == 'R' else .2) * (.15 if GEST[K_[m_][1]['g']][side] == rest_[side] else 1), 10)
            k_ = S * rampf_ * (1 - held)
            # speech beats, breath, and the idle drift that keeps hands from looking stuck
            q += V((sg * .04 * noise(f / 16, seed + sg), -.03 * str_, .085 * str_ * ampf_ * (.7 if sg < 0 else 1))) * k_
            q += V((0, 0, .012 * breath)) * (1 - held)
            q += V((.014 * noise(f / 31, seed + 5 + sg), .014 * noise(f / 37, seed + 7 + sg), .016 * noise(f / 29, seed + 11 + sg))) * st_['loose'] * (1 - held)
        if wave_ and side == 'R':
            q += V((math.sin(f / 3.2) * .13, 0, math.cos(f / 6.4) * .03))
        if feet and walk_amt > 0:
            # arm swing while walking: forward swings bend the elbow more than back swings
            fr = feet[4]
            sw = math.sin(math.pi * (fr * 1.0 + (0 if feet[2] > 0 else 1)) - math.pi / 2) * .38 * sg * (.65 + .35 * st_['loose']) * st_.get('swing', 1.0)
            A_ = walk_amt * (1 - held) * (1 - fold(lambda m_: 1. if K_[m_][1].get('c' + side) else 0., 8))
            q = q.lerp(V((sg * .56, sw, -.97 + .16 * max(0, -sw))), A_)
            # from a raised gesture the straight line to the walking arm runs through the shoulder: go round it
            q += V((sg * .2, -.08, 0)) * math.sin(math.pi * A_)
        if lap_ is not None and q.z < lap_[side].z and abs(q.x) < a.body['hipw'] + a.body['thigh_r'] + .12 \
                and -a.body['thigh'] * 1.05 < q.y < .15:
            q.z = q.z + (lap_[side].z - q.z) * lapw_      # never down into the thighs or the seat
        if getattr(P, 'tprof', None) is not None and fold(lambda m_: 0. if K_[m_][1].get('h' + side) is not None else 1., 8) > .5:
            # never through the chest or the belly: round them, or resting on them
            q = P.keep_out(q, bendf, sides, HAND_R * P.m.get('hs', 1.0))
        if held < .5:
            # no arm ever locks out straight on its way to a pose this body can't reach: the hand stops just short
            sh_ = V((sg * (P.sx - .045), 0, -.1))
            mx_ = 1.93 * (P.armLen - .005)
            dq_ = q - sh_
            if dq_.length > mx_:
                q = sh_ + dq_.normalized() * mx_
        hw_ = M @ (q + V((0, 0, sz)))
        hn_ = getattr(a, 'hand_now', None)
        if hn_ and hn_.get('f') == f and hn_.get(side):
            hw_ = hw_ + V(hn_[side])     # on its way between two poses this hand met something solid: it goes round it
        return hw_
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
            if lap_ is not None and k_['g'] in LOW:
                j_ = tuple(lerp(u_, v_, lapw_) for u_, v_ in zip(j_, LAPJ))
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
        j[1] += 3 * noise(f / 41, seed + 37 + sg_) * st_['loose'] + 5 * str_ * S * ampf_ * spk_
        j[2] += 2 * noise(f / 47, seed + 41 + sg_)
        if wave_ and side == 'R':
            j[2] += 16 * math.sin(f / 3.2)
        wk_ = walk_amt * (1 - fold(lambda m_, side=side: 1. if K_[m_][1].get('c' + side) else 0., 8))
        if wk_ > 0:
            j = [lerp(p_, q_, wk_) for p_, q_ in zip(j, WALKJ)]

        def fs(m_, kp=kp):
            k_ = K_[m_][1]
            v_ = handrig.fvec(k_.get(kp) or GEST[k_['g']].get(kp, 'relax'))
            if lap_ is not None and k_['g'] in LOW and not k_.get(kp):
                v_ = v_ + (handrig.fvec('lap') - v_) * lapw_
            return v_
        dfs = lambda m_, side=side: 7 + (tgt(side, m_) - tgt(side, max(m_ - 1, 0))).length * 6
        sh0_ = None
        if side == 'R' and K_[ki][1]['g'] == 'read':
            # a thumb that scrolls now and then while the eyes read: not a loop, a few strokes, then a pause
            sc_ = clamp((noise(f / 22, seed + 61) - .1) * 3)
            sh0_ = .35 * sc_ * math.sin(f / 2.6)
        sh = np.concatenate([fold(lambda m_, i_=i_: fs(m_)[i_ * 3:i_ * 3 + 3], dfs, delay=late + 1 + (3 - i_) * .7) for i_ in range(4)]
                            + [fold(lambda m_: fs(m_)[12:], dfs, delay=late + 1)])
        if K_[ki][1].get(kp) in (None, 'relax', 'open') and GEST[K_[ki][1]['g']].get(kp, 'relax') in ('relax', 'open'):
            sh[:12] += .035 * noise(f / 43, seed + 51 + sg_)
        if sh0_:
            sh[14] += sh0_

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
            # how far clear of the face the hand rests: a phone at the ear sits between the hand and the head
            th_ = .1 if K_[ki][1]['g'] == 'phone' else .06
            fw_ = (tuple(fold(lambda m_: last_of(ftab, m_) if last_of(ftab, m_) is not None else dflt, dh, delay=late)), w_, th_)
        a.face_w = getattr(a, 'face_w', {})
        a.face_w[side] = fw_[1] if fw_ else 0.
        el_ = None
        w_ = fold(lambda m_: 1. if etab(K_[m_][1]['g']) else 0., dh, delay=late)
        if w_ > 1e-3:
            dflt = last_of(etab, ki)
            el_ = (tuple(fold(lambda m_: last_of(etab, m_) if last_of(etab, m_) is not None else dflt, dh, delay=late)), w_ * (1 - walk_amt))
        rig[side] = (tuple(j), sh, fw_, el_)
    # head and eyes: eyes lead, head follows, body last
    Lk = S_.target_pos(cur[1].get('look'), a)
    Lk0 = S_.target_pos(prev[1].get('look'), a)
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
        T_ = S_.target_pos(K_[m_][1].get('look'), a)
        return np.array(aim(T_) if T_ is not None else (0., 0.))
    hy, hpi = fold(lk, 13, delay=2)
    # blink on a big head turn: exactly what real eyes do
    bl = max(a.blink(f, S_), (1 if abs(y1 - y0) > .5 and 0 <= f - cur[0] < 3 else 0))
    # micro saccades: steadier eyes move less and less often
    gz_ = st_.get('gaze', .4)
    sacc = (_h(int(f / (30 - 10 * gz_)) + seed) - .5) * (.6 + gz_)
    sacz = (_h(int(f / (36 - 10 * gz_)) + seed + 3) - .5) * (.6 + gz_)
    ey_y, ey_p = fold(lk, 5)
    nod = fold(lambda m_: K_[m_][1].get('nod', 0), 8)
    away_, awd_, awv_ = 0.0, (1 if seed % 2 else -1), 1
    if S >= .1:
        # speaking: a look away as the line begins, then back on whoever it is said to (the head goes a little with it)
        away_, awd_, awv_ = a.aversion(f, S_)
    if S < .1:
        # listening: the small nods of someone following along, as much as they agree and as is their habit
        others = max((S_.speaking(o_, f) for o_ in S_.actors if o_ != a.name), default=0)
        nod += .04 * others * max(0, math.sin(f / 13 + seed)) * st_.get('nod', 1.0) * FEEL_NOD[feel_]
        # a glance away now and then: more for someone whose eyes wander, or who is unsettled by what they hear
        lean_ = gz_ * .8 + (.35 if feel_ == 'unsettled' else 0.0)
        away_ = clamp((noise(f / 58, seed + 91) - (1 - lean_)) * 3.5) * others
    if feet and walk_amt > 0:
        nod += .02 * math.sin(2 * math.pi * feet[4]) * walk_amt
    nod += fold(lambda m_: CARRY.get(K_[m_][1]['f'], 0), 14)
    if lg_ is not None:
        nod += .05 * burst_ - .1 * lg_[1] * clamp(1 - lg_[0] / 10)      # the head goes back, then bobs with the breath
    head = (clamp(hpi * .5, -.3, .3) + .07 * str_ * ampf_ * S + .02 * math.sin(f / 23 + seed) + nod,
            .025 * S * noise(f / 17, seed + 6) * ampf_ + .012 * noise(f / 50, seed + 8) - .9 * sides + fold(lambda m_: K_[m_][1].get('tilt', 0), 9),
            clamp(hy * .55, -.4, .4) + .10 * S * noise(f / 21, seed + 4) * ampf_ - .85 * wtw_ + fold(lambda m_: K_[m_][1].get('turn', 0), 5)
            + (.07 * away_ * awd_ if S >= .1 else 0.0))
    # eye target remaining after the head moved: clamp stays in a friendly range
    lx = clamp((ey_y - head[2]) * 1.4 + sacc * .10 + away_ * .22 * awd_, -.6, .6)
    ly = clamp((ey_p - head[0]) * 1.2 + sacz * .08 + away_ * (.2 if awv_ > 0 else -.08) + fold(lambda m_: K_[m_][1].get('ly', 0), 5), -.6, .6)
    # the face: mood underneath, words on top, and the mood never quite leaves while they talk
    mc = Mo['c'].copy()
    for k_s in ('smileL', 'smileR'):
        if mc[FI[k_s]] > 0:
            mc[FI[k_s]] *= st_.get('smile', 1.0)        # how far a pleasant face smiles is their own
    sp = S_.face_speech(a.name, f)
    if sp is not None:
        fc = mc * .98
        fc[FI['jaw']] = mc[FI['jaw']] * .25
        fc = fc + sp
    else:
        fc = mc.copy()
    fc[FI['jawSide']] += .10 * noise(f / 46, seed + 21) * (.4 + .6 * S)
    if lg_ is not None and sp is None:
        fc[FI['jaw']] += (.22 + .18 * min(1.3, st_['amp'])) * burst_ + .12 * lg_[1]
        for k_s in ('squintL', 'squintR'):
            fc[FI[k_s]] += .35 * lg_[1]
    fc[FI['press']] = clamp(1 - 3.1 * fc[FI['jaw']] - 1.1 * fc[FI['upLip']] - .9 * fc[FI['lowLip']] - .5 * fc[FI['fv']])
    # brows rise on stress; a talker's brows are never still
    br = .55 * str_ * ampf_ * S
    # the two eyes meet on what they look at (no look target: a comfortable middle distance)
    dv_ = (Lk - hp).length if Lk is not None else 8.0
    P.verg = min(.07, math.atan2(P.es * .97, max(1.2, dv_)))
    P.pose(loc=root, yaw=yaw, bend=(bendf + .004 * breath, sides), twist=twist, squash=squash, head=head, look=(lx, ly),
           upper=Mo['u'], lower=Mo['l'], blink=bl, browL=Mo['bL'] + br, browR=Mo['bR'] + br * .9, tiltL=Mo['tL'], tiltR=Mo['tR'],
           fc=fc, handL=hL, handR=hR, jL=rig['L'][0], jR=rig['R'][0], shapeL=rig['L'][1], shapeR=rig['R'][1],
           faceL=rig['L'][2], faceR=rig['R'][2], elL=rig['L'][3], elR=rig['R'][3],
           footL=fL, footR=fR, roll=(rollL, rollR), lift=(lfL, lfR), shoeYaw=(shoeL, shoeR),
           sit=(.09 - a.body['seat_drop'] + .008, seatA) if sol is not None else None,
           capeSway=(.05 * noise(f / 30, 3) + .22 * walk_amt + .03 * S * noise(f / 11, 2)),
           hairJ=((.016 * math.sin(2 * math.pi * feet[4] - 1.1) * walk_amt if feet else 0) + .006 * str_ * S,
                  (y1 - y0) * -.035 * math.sin(math.pi * he)))
    a.last_head = P.head_world + V((0, 0, .04))
    a.last_yaw = yaw + head[2]
    a.last_hand = dict(L=hL, R=hR)
