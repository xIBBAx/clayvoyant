"""handrig.py: the arm below the shoulder, as anatomy has it, for every human character. No bpy here: the sculpt, the rig, the
director and the audits all share this one definition, so a hand cannot mean one thing to the sculpt and another to the animation.

What it replaces: the hand was a rigid continuation of the forearm, its roll set by projecting a fixed world vector, the elbow always
flared the same way, and fingers swapped between six separate meshes. So a palm-up gesture asked the forearm for 125 degrees of roll
(people have about 85), a palm-forward hand on a forward forearm had no defined roll at all, a change of gesture blended that world
vector through zero and flipped the hand in two frames, and fingers popped.

The model:
  elbow    pole_for(): swings with where the hand is going. Tucked for a hand in front, out to the side for a hand raised high.
  forearm  one roll, measured from thumb-toward-the-inside-of-the-elbow: pronation (palm turns down) is positive, supination negative.
  wrist    extension (toward the back of the hand) and radial deviation (toward the thumb), inside real limits.
  fingers  three curls each, a spread, and a thumb, all continuous: any pose blends into any other through the joints.

Conventions. An actor faces -Y. 'R' is the hand at +X, sg=+1; 'L' is the hand at -X, sg=-1. Hand space: +X along the fingers, +Y out of the
back of the hand (so the palm is -Y and fingers curl to -Y), and the thumb on +Z for sg=+1, on -Z for sg=-1.
A joint state J is (pro, ext, rad) in degrees."""
import math
import numpy as np

# how far a forearm rolls and a wrist bends, in degrees, from neutral
PRO_MAX, SUP_MAX = 88, 88
EXT_MAX, FLEX_MAX = 72, 72
RAD_MAX, ULN_MAX = 20, 32

# finger shapes: curl of each joint for pinky, ring, middle, index (toward the palm is negative), spread, thumb (abduct, flex)
HAND = dict(
    relax=dict(c=[(-.28, -.5, -.55)] * 4, spread=.07, th=(.5, .7)),
    open=dict(c=[(-.05, -.05, -.05)] * 4, spread=.13, th=(.9, .25)),
    point=dict(c=[(-1.2, -1.5, -1.2), (-1.2, -1.5, -1.2), (-1.1, -1.5, -1.2), (-.03, -.05, -.05)], spread=.05, th=(.4, 1.0)),
    fist=dict(c=[(-1.3, -1.6, -1.3)] * 4, spread=.03, th=(.2, 1.3)),
    grip=dict(c=[(-.8, -1.0, -.9)] * 4, spread=.04, th=(.5, .9)),
    thumb=dict(c=[(-1.3, -1.6, -1.3)] * 4, spread=.03, th=(1.4, .05)),
    # a phone being read lies along the palm and the fingers: they stay all but flat under it, the thumb up beside its edge
    tray=dict(c=[(-.06, -.1, -.1)] * 4, spread=.05, th=(1.4, .05)),
    # round a mug: the fingers lie on its wall, a finger's thickness out from it, and the thumb rests over the rim
    cup=dict(c=[(-.386, -.225, -.405)] * 4, spread=.04, th=(1.0, .2)),
    # a phone held to the ear: fingers lie along its back and curl over its far edge, the thumb holds the near edge
    cradle=dict(c=[(-.22, -.5, -.45)] * 4, spread=.05, th=(.85, .55)),
)
ZS = (-.066, -.024, .018, .058)        # knuckles across the palm: pinky to index, thumb side is +Z
LENS = (.82, .96, 1.0, .9)
# the pose the hand is sculpted in: fingers fanned apart so each is its own form, and the rig can close them
BASE = dict(c=[(-.04, -.04, -.04)] * 4, spread=.46, th=(1.0, .2))

def fvec(name):
    """A finger shape as one flat vector, so that shapes can be blended: 12 curls, spread, thumb abduct, thumb flex."""
    h = HAND[name] if isinstance(name, str) else name
    return np.array([x for f in h['c'] for x in f] + [h['spread'], h['th'][0], h['th'][1]], float)

def finger(i, c, spread):
    """Joints of one finger in unit hand space: knuckle, two knuckles along it, and the tip."""
    z, ln = ZS[i], LENS[i]
    zd = (z / .066) * spread * .6 + z * .9
    p = np.array((.10, 0., z * .92))
    pts = [p.copy()]
    ang = 0.
    for cu, L_ in zip(c, (.025 + .062 * ln, .05 * ln, .04 * ln)):
        ang += cu
        p = p + np.array((math.cos(ang) * L_, math.sin(ang) * L_, zd * L_))
        pts.append(p.copy())
    return np.array(pts)

def thumb(t0, t1):
    tb = np.array((.03, -.02, .058))
    tm = tb + np.array((.05 * math.cos(t1 * .6), -.025 - .02 * math.sin(t1), .055 * math.sin(t0)))
    tt = tm + np.array((.045 * math.cos(t1), -.012 - .02 * math.sin(t1), .05 * math.sin(t0)))
    return np.array((tb, tm, tt))

def chains(v):
    """All five chains for a shape vector, in unit hand space."""
    return [finger(i, v[i * 3:i * 3 + 3], v[12]) for i in range(4)] + [thumb(v[13], v[14])]

# bones: 0 is the palm, then three for each finger, then two for the thumb
NB = 15
def _bones():
    out, b = [], 1
    for n in (3, 3, 3, 3, 2):
        out.append(list(range(b, b + n)))
        b += n
    return out
BONES = _bones()

def _sm(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)

def skin(v, s, side):
    """Skin weights for the sculpted hand. Every vertex belongs to at most two neighbouring bones. Returns (n,2) bone ids and (n,) weight of the second."""
    P = np.array(v, float) / np.array((s, s, s * side))
    n = len(P)
    ch = chains(fvec(BASE))
    best = np.full(n, 1e9)
    b0 = np.zeros(n, np.int64)
    b1 = np.zeros(n, np.int64)
    w = np.zeros(n)
    for ci, J in enumerate(ch):
        seg = J[1:] - J[:-1]
        L = np.linalg.norm(seg, axis=1)
        cum = np.r_[0, np.cumsum(L)]
        # the closest point on the chain: distance, and how far along it
        dist = np.full(n, 1e9)
        along = np.zeros(n)
        for k in range(len(seg)):
            u = seg[k] / L[k]
            t = (P - J[k]) @ u
            # the chain carries on straight past both ends, so the hand's ball and the fingertip measure sensibly
            tc = np.clip(t, -.05 if k == 0 else 0, L[k] + (.05 if k == len(seg) - 1 else 0))
            q = J[k] + tc[:, None] * u
            dd = np.linalg.norm(P - q, axis=1)
            m = dd < dist
            dist[m] = dd[m]
            along[m] = cum[k] + tc[m]
        thumb_ = ci == 4
        rad = .036 if thumb_ else .030
        # a vertex on this chain, nearer it than to any other
        m = (dist - rad) < best
        best[m] = (dist - rad)[m]
        bones = BONES[ci]
        lo, hi = ((-.03, .035) if thumb_ else (-.018, .026))
        for i_ in np.nonzero(m)[0]:
            a_ = along[i_]
            if a_ < hi:
                b0[i_], b1[i_], w[i_] = 0, bones[0], _sm(lo, hi, a_)
                continue
            b0[i_], b1[i_], w[i_] = bones[-1], bones[-1], 0.
            for k in range(1, len(bones)):
                if a_ < cum[k] + .012:
                    b0[i_], b1[i_], w[i_] = bones[k - 1], bones[k], _sm(cum[k] - .012, cum[k] + .012, a_)
                    break
    # far from every chain is the palm itself
    far = best > .03
    b0[far], b1[far], w[far] = 0, 0, 0.
    return np.c_[b0, b1].astype(np.uint8), w.astype(np.float32)

def rotate_onto(a, b):
    """The smallest rotation taking direction a to direction b, as a 3x3."""
    a = a / (np.linalg.norm(a) + 1e-12)
    b = b / (np.linalg.norm(b) + 1e-12)
    v = np.cross(a, b)
    c = float(a @ b)
    if c < -.999999:
        return -np.eye(3)
    K = np.array(((0, -v[2], v[1]), (v[2], 0, -v[0]), (-v[1], v[0], 0)))
    return np.eye(3) + K + K @ K / (1 + c)

class Bones:
    """Posed bone matrices for one hand: the sculpted chains are fixed, the target chains come from a shape vector."""
    def __init__(s, size, side):
        s.k = np.array((size, size, size * side))
        s.base = [J * s.k for J in chains(fvec(BASE))]

    def pose(s, v):
        R = np.tile(np.eye(3), (NB, 1, 1))
        T = np.zeros((NB, 3))
        for ci, J in enumerate(chains(v)):
            J = J * s.k
            B = s.base[ci]
            for k, b in enumerate(BONES[ci]):
                Rk = rotate_onto(B[k + 1] - B[k], J[k + 1] - J[k])
                R[b] = Rk
                T[b] = J[k] - Rk @ B[k]
        return R, T

def deform(v0, bi, bw, R, T, wz, sw):
    """Pose the hand: fingers by their bones, then the wrist as a soft bend, so the skin stays one piece. wz is how much of the wrist
    bend each vertex takes (0 on the forearm side, 1 past the heel of the hand); sw is the wrist's rotation vector (0, wy, wz) in radians."""
    a = np.einsum('nij,nj->ni', R[bi[:, 0]], v0) + T[bi[:, 0]]
    b = np.einsum('nij,nj->ni', R[bi[:, 1]], v0) + T[bi[:, 1]]
    v = a + (b - a) * bw[:, None]
    th = float(np.linalg.norm(sw))
    if th > 1e-5:
        k = sw / th
        an = (th * wz)[:, None]
        v = v * np.cos(an) + np.cross(k, v) * np.sin(an) + k * (v @ k)[:, None] * (1 - np.cos(an))
    return v

def unit(v):
    return v / (np.linalg.norm(v) + 1e-12)

def ik(a, c, l1, l2, pole):
    d = c - a
    L = max(.02, min(np.linalg.norm(d), l1 + l2 - .002))
    u = unit(d)
    x = (l1 * l1 - l2 * l2 + L * L) / (2 * L)
    y = math.sqrt(max(0, l1 * l1 - x * x))
    p = pole - u * (pole @ u)
    p = unit(p) if np.linalg.norm(p) > 1e-4 else np.array((0, 0, -1.))
    return a + u * x + p * y, a + u * L

# Directions are carried round the sphere from one comfortable arm, forward and down, along the shortest way. A smooth field of directions
# around every arm line has to break somewhere (a hairy ball), so this one breaks in a single place: an arm raised behind the head.
_B = unit(np.array((0, -.55, -.83)))
def _carried(a, v):
    return rotate_onto(_B, a) @ v
_EB = np.array((.35, .80, -.53))
_EB = unit(_EB - _B * (_EB @ _B))                                             # the elbow: back, down, a little out
_TB = rotate_onto(np.array((0, 0, -1.)), _B) @ unit(np.array((-.22, -1., 0)))  # the thumb: forward at the side, a little in

def pole_for(sg, A, T, hint=None):
    """Where the elbow points, in actor space. Smooth wherever a hand goes and always square to the arm, so an arm can never swing through
    its own elbow direction: that is what made forearms spin. Hanging: back. Reaching forward: under the arm. Out to the side: back and down.
    Gestures that open the elbow (hands on hips, hands raised) add a hint."""
    m = np.array((sg, 1., 1.))
    # a hand close to the shoulder has no steady direction from it: lean on the comfortable arm until there is one
    a = unit((np.asarray(T, float) - np.asarray(A, float)) * m + .3 * _B)
    p = _carried(a, _EB) * m
    if hint is not None:
        # a hint only counts as far as it is square to the arm, so it can never bring back the case it is there to avoid
        a = a * m
        h = unit(np.array((sg * hint[0][0], hint[0][1], hint[0][2])))
        h = h - a * (h @ a)
        p = p + (unit(h) - p) * hint[1] * float(_sm(.3, .7, np.linalg.norm(h)))
    return p

def round_shoulder(sg, A, T):
    """A hand rising from the hip to the head does not pass through the shoulder: it swings out in front of it. Keeps the arm from folding flat on itself."""
    A = np.asarray(A, float)
    r = np.asarray(T, float) - A
    k = float(_sm(.5, .24, np.linalg.norm(r)))
    return A + r + k * np.array((sg * .14, -.34, -.04))

def neutral(A, E, C, pole, sg, Rot=None):
    """Forearm direction, and where the thumb points with no roll in the forearm: toward the inside of the elbow. With the arm near straight the
    elbow says little, so the thumb stays where the shoulder has carried it. Rot: actor to world."""
    d = unit(C - E)
    u = A - E
    n = u - d * (u @ d)
    I = np.eye(3) if Rot is None else Rot
    m = np.array((sg, 1., 1.))
    ref = I @ (_carried(unit((I.T @ -u) * m), _TB) * m)
    ref = ref - d * (ref @ d)
    # the elbow only has an opinion when it is really bent, one way or the other: straight, or folded right back on itself as a hand passes the
    # shoulder, its direction swings through nothing, and following it spins the hand
    b = np.linalg.norm(n) / (np.linalg.norm(u) + 1e-9)
    g = float(_sm(.12, .62, b))
    q = (n / (np.linalg.norm(n) + 1e-9)) * g + ref / (np.linalg.norm(ref) + 1e-9) * (1 - g * .75)
    if np.linalg.norm(q) < 1e-3:
        q = np.array((0, 0, 1.)) - d * d[2]
    q = q - d * (q @ d)
    return d, unit(q)

def forearm(d, t0, sg, pro):
    """The hand frame with the forearm rolled to pro and the wrist straight: columns +X along the fingers, +Y back of the hand, +Z."""
    a = sg * math.radians(pro)
    t = t0 * math.cos(a) + np.cross(d, t0) * math.sin(a)
    Z = sg * t
    return np.c_[d, np.cross(Z, d), Z]

def swing_vec(sg, ext, rad):
    """The wrist as a rotation vector in hand space."""
    return np.array((0, -sg * math.radians(rad), math.radians(ext)))

def rotvec(w):
    th = float(np.linalg.norm(w))
    if th < 1e-9:
        return np.eye(3)
    k = w / th
    K = np.array(((0, -k[2], k[1]), (k[2], 0, -k[0]), (-k[1], k[0], 0)))
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K

def clamp_joint(pro, ext, rad):
    pro = max(-SUP_MAX, min(PRO_MAX, pro))
    le = EXT_MAX if ext > 0 else FLEX_MAX
    lr = RAD_MAX if rad > 0 else ULN_MAX
    k = math.hypot(ext / le, rad / lr)
    if k > 1:
        ext, rad = ext / k, rad / k
    return pro, ext, rad

def _quat(R):
    t = R[0, 0] + R[1, 1] + R[2, 2]
    if t > 0:
        S = math.sqrt(t + 1) * 2
        return np.array((.25 * S, (R[2, 1] - R[1, 2]) / S, (R[0, 2] - R[2, 0]) / S, (R[1, 0] - R[0, 1]) / S))
    i = int(np.argmax((R[0, 0], R[1, 1], R[2, 2])))
    j, k = (i + 1) % 3, (i + 2) % 3
    S = math.sqrt(1 + R[i, i] - R[j, j] - R[k, k]) * 2
    q = np.zeros(4)
    q[0] = (R[k, j] - R[j, k]) / S
    q[1 + i] = .25 * S
    q[1 + j] = (R[j, i] + R[i, j]) / S
    q[1 + k] = (R[k, i] + R[i, k]) / S
    return q

def aim(d, t0, sg, fingers, back):
    """Joint state that puts the hand as near as anatomy allows to a wanted direction: fingers (None: straight on from the forearm), and the
    back of the hand. Twist goes to the forearm, the rest to the wrist. Returns (pro, ext, rad) unclamped, so an audit can see what was asked."""
    X = unit(np.asarray(fingers, float)) if fingers is not None else d
    Y = np.asarray(back, float)
    Y = unit(Y - X * (Y @ X))
    Hd = np.c_[X, Y, np.cross(X, Y)]
    Rr = forearm(d, t0, sg, 0).T @ Hd
    q = _quat(Rr)
    w, x = q[0], q[1]
    nrm = math.hypot(w, x) or 1
    tw = 2 * math.atan2(x / nrm, w / nrm)
    if tw > math.pi:
        tw -= 2 * math.pi
    if tw < -math.pi:
        tw += 2 * math.pi
    Sw = rotvec(np.array((tw, 0, 0))).T @ Rr
    qs = _quat(Sw)
    v = qs[1:]
    vn = np.linalg.norm(v)
    ang = 2 * math.atan2(vn, qs[0])
    if ang > math.pi:
        ang -= 2 * math.pi
    sw = v / (vn + 1e-12) * ang
    return sg * math.degrees(tw), math.degrees(sw[2]), -sg * math.degrees(sw[1])

# Every gesture's hands, in joint terms. A plain tuple is (pro, ext, rad) and goes wherever the arm goes. dict(f=fingers, b=back) names a
# direction in actor space, for hands that have to meet something (a face, a palm, a chest) or face someone; it is solved once per
# character into joint terms. Keys: both hands, or L / R.
REST = (14, -6, -5)
REST_AT = dict(L=(-.54, -.03, -1.02), R=(.54, -.03, -1.02))   # the table's hanging hand; each body's own is Puppet.place()
GJ = dict(
    rest=dict(B=REST),
    talk=dict(B=(26, 7, 0)), talkR=dict(R=(22, 9, 0)), talkL=dict(L=(22, 9, 0)), talkWide=dict(B=(-24, 8, 0)),
    point=dict(R=(52, 4, 0)), pointL=dict(L=(52, 4, 0)),
    shrug=dict(B=(-80, 14, 0)),
    cross=dict(B=(58, -14, 0)),
    chin=dict(R=dict(f=(-.26, .12, 1), b=(1, 0, 0)), L=(40, -8, 0)),
    head=dict(L=dict(f=(.26, .02, 1), b=(-1, .1, .1)), R=dict(f=(-.26, .02, 1), b=(1, .1, .1))),
    hips=dict(B=(38, -24, 0)),
    wave=dict(R=(0, 10, 0)),
    up=dict(B=(0, 10, 0)),
    present=dict(B=(-74, 6, 0)), presentR=dict(R=(-74, 6, 0)), presentL=dict(L=(-74, 6, 0)),
    scared=dict(L=dict(f=(.1, -.3, 1), b=(0, 1, 0)), R=dict(f=(-.1, -.3, 1), b=(0, 1, 0))),
    clasp=dict(B=(46, -10, -8)),
    pockets=dict(B=(10, 0, 0)),
    oops=dict(R=dict(f=(-.16, .08, 1), b=(0, -1, 0))),
    facepalm=dict(R=dict(f=(-.28, .22, 1), b=(0, -1, 0))),
    desk=dict(B=(80, 8, 0)), typing=dict(B=(82, 12, 0)),
    # palm on the phone's back, fingers up and back across it (the phone runs from the ear down toward the mouth)
    phone=dict(R=dict(f=(-.05, .5, .86), b=(1, -.1, -.1))),
    hold=dict(R=(4, 0, 0)), hold2=dict(B=(4, 0, 0)),
    carry=dict(R=(4, 0, 0)), sip=dict(R=(8, 6, 0)), read=dict(R=(-66, 12, 0)),
    thumb=dict(R=(-4, 0, 14)),
    offer=dict(R=(-78, 8, 0)),
    stop=dict(R=dict(f=(.02, -.14, 1), b=(0, 1, 0))),
    slump=dict(B=(14, -10, -6)),
    fish=dict(L=(4, 0, 0), R=(20, 5, 0)), fishup=dict(L=(4, 0, 0), R=(10, 5, 0)),
    armsout=dict(B=(52, 6, 0)),
    proud=dict(B=(38, -24, 0)),
    lean=dict(B=(70, 12, 0)),
    recoil=dict(L=dict(f=(.18, -.26, 1), b=(0, 1, 0)), R=dict(f=(-.18, -.26, 1), b=(0, 1, 0))),
    chest=dict(R=dict(f=(-1, -.12, .3), b=(0, -1, 0))),
    index=dict(R=(18, 6, 0)),
    palmsDown=dict(B=(80, 10, 0)),
    weigh=dict(B=(-74, 8, 0)),
    namaste=dict(L=dict(f=(.02, -.12, 1), b=(-1, 0, .1)), R=dict(f=(-.02, -.12, 1), b=(1, 0, .1))),
)
# hands that touch the face are placed in the head's own space, so they meet every character's face, and stay on it when the head moves
FACE = dict(chin=dict(R=(.134, -.515, -.098)), oops=dict(R=(.103, -.577, -.005)), facepalm=dict(R=(.175, -.62, .26)), phone=dict(R=(.525, -.12, .256)),
            head=dict(L=(-.54, -.02, .40), R=(.54, -.02, .40)))
# gestures whose elbow has somewhere particular to be: (out, back, down), blended over the natural swing
ELBOW = dict(hips=(1, .22, -.42), proud=(1, .22, -.42), head=(1, -.28, -.42), cross=(.8, .1, -.6), facepalm=(.3, -.25, -1), oops=(.35, -.1, -1), chin=(.3, -.05, -1),
             phone=(.75, .05, -.7), chest=(.7, .1, -.75), up=(1, .12, -.5), wave=(1, .12, -.5), scared=(.7, .1, -.8), recoil=(.8, .1, -.7), stop=(.5, .1, -.9),
             index=(.6, .1, -.85), namaste=(.7, .15, -.8), clasp=(.45, .25, -.9), hold=(.4, .2, -1), hold2=(.45, .2, -1),
             carry=(.4, .2, -1), sip=(.6, .1, -.8), read=(.35, .15, -1))

def elbow(name, side):
    if name not in ELBOW:
        return None
    g = GJ.get(name, {})
    return ELBOW[name] if 'B' in g or side in g else None

def gesture_hand(name, side):
    g = GJ.get(name, {})
    return g.get(side) or g.get('B') or REST
